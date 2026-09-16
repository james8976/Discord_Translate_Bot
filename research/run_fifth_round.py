"""Fifth-round experiment: Optimal Transport (Sinkhorn) retrieval vs cosine vs CSLS.

Research goal
-------------
Build a lightweight multilingual translation system that works for:
  - Standard vocabulary
  - Internet slang, memes, colloquial speech
  - Any language pair (not hard-coded to Chinese/Japanese)
  - No heavy GPU compute needed

Why OT helps slang
------------------
Slang words live in isolated corners of the embedding space.
Standard cosine: query → nearest hub (common word) -- slang missed
CSLS: penalises known hubs locally, still query-by-query
OT (Sinkhorn): processes ALL queries simultaneously, enforces that each
               target word can only "absorb" a limited total mass.
               Isolated slang words get a fair chance because hub words
               are globally constrained.

Ablation grid (6 methods x 2 directions = 12 experiments):
  cosine_r2   : cosine retrieval,  no centering          (R2 baseline)
  csls_r2     : CSLS retrieval,    no centering          (R2 best zh-ja)
  ot_r2       : OT  retrieval,     no centering          [NEW Imp-5]
  cosine_r3cs : cosine retrieval,  centered-space        (R3 best ja-zh)
  csls_r3cs   : CSLS retrieval,    centered-space        (R3 best)
  ot_r3cs     : OT  retrieval,     centered-space        [NEW Imp-5]

Planned future directions (not yet in this script):
  - Korean (ko) via English pivot  -- requires wiki.ko.vec + ko-en dict
  - Hindi, Arabic, Turkish         -- same pivot infrastructure
  - Social-media fine-tuned vectors (fastText trained on Twitter/Reddit)
"""
from __future__ import annotations

import argparse, html, json, os, sys, time
from dataclasses import asdict
from typing import Any, Dict, List, Tuple
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from research.align import CrossLingualAligner
from research.config import ALL_LANGS, DATA_DIR, RUNS_DIR
from research.confidence import entropy_confidence
from research.embeddings import EmbeddingSpace, load_fasttext_vectors
from research.ot_retriever import OTRetriever
from research.pivot import (
    build_zh_ja_pivot, deterministic_split,
    filter_to_vocab, remove_held_out_pairs, reverse_pairs,
)
from research.retrieval import CSLSRetriever

WordPair = Tuple[str, str]

# ------------------------------------------------------------------ helpers --

def load_dictionary(path):
    pairs = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            f = line.strip().split()
            if len(f) >= 2:
                pairs.append((f[0], f[1]))
    return pairs


def load_special_dictionary(path):
    groups = {"standard": [], "special": []}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            f = line.split("\t")
            if len(f) < 4:
                continue
            src, tgt, cat, desc = f[:4]
            groups["standard" if cat == "standard" else "special"].append((src, tgt, desc))
    return groups


def build_matrices(pairs, ss, ts):
    sv, tv, valid = [], [], []
    for s, t in pairs:
        if s in ss.word2vec and t in ts.word2vec:
            sv.append(ss[s]); tv.append(ts[t]); valid.append((s, t))
    if not valid:
        return np.empty((0, 0)), np.empty((0, 0)), []
    return np.asarray(sv), np.asarray(tv), valid


def confidence_from_margin(scores):
    if len(scores) < 2:
        return 1.0
    m = float(scores[0] - scores[1])
    return float(1 / (1 + np.exp(-np.clip(m / 0.05, -60, 60))))


# --------------------------------------------------------- evaluation logic --

def evaluate_standard(aligner, pairs, ss, ts, retriever, ks=(1, 5, 10)):
    """Per-query cosine or CSLS retrieval (same as previous rounds)."""
    hits = {k: 0 for k in ks}; total = 0; details = []
    for src, exp in pairs:
        if src not in ss.word2vec or exp not in ts.word2vec:
            continue
        mapped = aligner.translate_word(ss[src])
        nbrs = retriever.nearest_neighbors(mapped, max(ks)) if retriever else \
               ts.nearest_neighbors(mapped, max(ks))
        words = [w for w, _ in nbrs]; scores = [s for _, s in nbrs]
        total += 1
        for k in ks:
            hits[k] += int(exp in words[:k])
        conf = entropy_confidence(1.0 - np.array(scores[:10], dtype=np.float32))
        details.append({
            "source": src, "expected": exp, "predicted": words[0],
            "top5": words[:5], "top5_scores": scores[:5],
            "found_at": words.index(exp) + 1 if exp in words else -1,
            "correct": words[0] == exp,
            "margin_confidence": confidence_from_margin(scores),
            "entropy_confidence": conf,
        })
    return {k: (hits[k] / total * 100 if total else 0.0) for k in ks}, details


def evaluate_ot(aligner, pairs, ss, ts, ot_retriever, ks=(1, 5, 10)):
    """Batch OT (Sinkhorn) retrieval -- all queries processed together."""
    valid = [(s, e) for s, e in pairs if s in ss.word2vec and e in ts.word2vec]
    if not valid:
        return {k: 0.0 for k in ks}, []

    src_mat = np.stack([ss[s] for s, _ in valid])  # (N, d) raw
    mapped = aligner.translate_word(src_mat)         # (N, d) in target space

    print(f"      [OT] running batch Sinkhorn on {len(valid)} queries ...", flush=True)
    batch_nbrs = ot_retriever.retrieve_batch(mapped, k=max(ks))

    hits = {k: 0 for k in ks}
    details = []
    for (src, exp), nbrs in zip(valid, batch_nbrs):
        words = [w for w, _ in nbrs]; scores = [s for _, s in nbrs]
        for k in ks:
            hits[k] += int(exp in words[:k])
        conf = entropy_confidence(1.0 - np.array(scores[:10], dtype=np.float32))
        details.append({
            "source": src, "expected": exp, "predicted": words[0],
            "top5": words[:5], "top5_scores": scores[:5],
            "found_at": words.index(exp) + 1 if exp in words else -1,
            "correct": words[0] == exp,
            "margin_confidence": confidence_from_margin(scores),
            "entropy_confidence": conf,
        })
    return {k: (hits[k] / len(valid) * 100) for k in ks}, details


def hubness_skewness(details):
    counts = {}
    for d in details:
        for t in d.get("top5", []):
            counts[t] = counts.get(t, 0) + 1
    v = np.asarray(list(counts.values()), dtype=np.float32)
    if len(v) < 2:
        return 0.0, counts
    mean = v.mean()
    return float(np.mean(((v - mean) / (v.std() + 1e-10)) ** 3)), counts


# ------------------------------------------------------- data loading utils --

def load_embeddings(max_words):
    emb = {}
    for lang in ALL_LANGS:
        path = os.path.join(DATA_DIR, f"wiki.{lang}.vec")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing {path}")
        emb[lang] = EmbeddingSpace(load_fasttext_vectors(path, max_words=max_words))
        print(f"  Loaded {lang}: {len(emb[lang].words)} words")
    return emb


def prepare_pivot_sets(embeddings, seed):
    zh_en = load_dictionary(os.path.join(DATA_DIR, "zh-en.txt"))
    en_ja = load_dictionary(os.path.join(DATA_DIR, "en-ja.txt"))
    ja_zh = load_dictionary(os.path.join(DATA_DIR, "ja-zh.txt"))
    zh_en_train, _ = deterministic_split(zh_en, seed=seed)
    en_ja_train, _ = deterministic_split(en_ja, seed=seed + 1)
    _, ja_zh_test  = deterministic_split(ja_zh, seed=seed + 2)
    pzj, stats = build_zh_ja_pivot(zh_en_train, en_ja_train)
    pzj = filter_to_vocab(pzj, set(embeddings["zh"].words), set(embeddings["ja"].words))
    pjz = filter_to_vocab(reverse_pairs(pzj), set(embeddings["ja"].words), set(embeddings["zh"].words))
    zjt = reverse_pairs(ja_zh_test)
    pzj = remove_held_out_pairs(pzj, zjt)
    pjz = remove_held_out_pairs(pjz, ja_zh_test)
    meta = asdict(stats)
    meta.update({"pivot_after_vocab_filter": len(pzj), "direct_ja_zh_held_out": len(ja_zh_test), "seed": seed})
    return {"zh-ja": pzj, "ja-zh": pjz}, meta, {"zh-ja": zjt, "ja-zh": ja_zh_test}


# ------------------------------------------------------------------ charting --

def generate_charts(result, output_dir):
    try:
        import matplotlib; matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("  [WARN] matplotlib not available"); return
    plt.rcParams["font.family"] = "DejaVu Sans"
    plt.rcParams["font.sans-serif"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    BG = "#2C2F33"; TC = "#FFFFFF"
    C = {"cosine_r2": "#ED4245", "csls_r2": "#F0A500", "ot_r2": "#EB459E",
         "cosine_r3cs": "#57F287", "csls_r3cs": "#5865F2", "ot_r3cs": "#1ABC9C"}
    direction = result["direction"]; ks = [1, 5, 10]
    md = result.get("methods", {})
    series = [(k, md[k]["precision_test"], C.get(k, "#FFFFFF")) for k in C if k in md]
    if series:
        fig, ax = plt.subplots(figsize=(14, 6), facecolor=BG); ax.set_facecolor(BG)
        x = np.arange(len(ks)); w = 0.8 / max(len(series), 1)
        for i, (lbl, prec, col) in enumerate(series):
            off = (i - (len(series) - 1) / 2) * w
            vals = [prec.get(str(k), prec.get(k, 0)) for k in ks]
            bars = ax.bar(x + off, vals, w, label=lbl, color=col, alpha=0.85)
            for bar in bars:
                h = bar.get_height()
                if h > 0.3:
                    ax.text(bar.get_x() + bar.get_width() / 2, h + 0.3,
                            f"{h:.1f}%", ha="center", va="bottom", color=TC, fontsize=7)
        ax.set_title(f"Precision@K: cosine vs CSLS vs OT(Sinkhorn) -- {direction}", color=TC, fontsize=12, fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels(["P@1", "P@5", "P@10"], color=TC)
        ax.set_ylabel("Precision (%)", color=TC); ax.tick_params(colors=TC)
        ax.legend(facecolor="#36393f", edgecolor="#555", labelcolor=TC, fontsize=8)
        allv = [prec.get(str(k), prec.get(k, 0)) for _, prec, _ in series for k in ks]
        ax.set_ylim(0, max(50, max(allv) + 10) if allv else 50)
        plt.tight_layout()
        out = os.path.join(output_dir, "r5_precision_ablation.png")
        plt.savefig(out, dpi=150, facecolor=BG); plt.close()
        print(f"  [OK] {os.path.basename(out)}")
    hub_data = {k: v.get("hubness_skewness", 0) for k, v in md.items()}
    if hub_data:
        fig, ax = plt.subplots(figsize=(10, 5), facecolor=BG); ax.set_facecolor(BG)
        lbs = list(hub_data.keys()); vals = [hub_data[l] for l in lbs]
        cols = [C.get(l, "#FFFFFF") for l in lbs]
        bars = ax.bar(lbs, vals, color=cols, alpha=0.85)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                    f"{val:.2f}", ha="center", va="bottom", color=TC, fontsize=8)
        ax.set_title(f"Hubness Skewness -- {direction} (OT should reduce hubs)", color=TC, fontsize=12, fontweight="bold")
        ax.set_ylabel("Skewness", color=TC); ax.tick_params(colors=TC)
        plt.xticks(rotation=20, ha="right", color=TC)
        plt.tight_layout()
        out = os.path.join(output_dir, "r5_hubness_comparison.png")
        plt.savefig(out, dpi=150, facecolor=BG); plt.close()
        print(f"  [OK] {os.path.basename(out)}")


def write_html_report(path, result):
    rows = []
    for m, met in result.get("methods", {}).items():
        p = met["precision_test"]
        rows.append(
            f'<tr><td>{html.escape(m)}</td>'
            f'<td>{p.get("1",p.get(1,0)):.1f}%</td>'
            f'<td>{p.get("5",p.get(5,0)):.1f}%</td>'
            f'<td>{p.get("10",p.get(10,0)):.1f}%</td>'
            f'<td>{met["hubness_skewness"]:.2f}</td></tr>'
        )
    css = ("body{font-family:system-ui;max-width:960px;margin:40px auto}"
           "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3df;padding:10px}"
           "th{background:#edf2fb}.note{background:#e8f5e9;padding:12px;border-left:4px solid #43a047}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(
            f'<!doctype html><html lang="en"><meta charset="utf-8">'
            f'<title>PongPong R5 - OT Sinkhorn</title><style>{css}</style>'
            f'<h1>PongPong Round 5 -- Optimal Transport Retrieval</h1>'
            f'<p>Direction: <b>{html.escape(result["direction"])}</b> | '
            f'Anchors: <b>{result.get("pivot_training_pairs","N/A")}</b> | '
            f'Test: <b>{result.get("held_out_test_pairs","N/A")}</b></p>'
            f'<h2>Precision@K (cosine vs CSLS vs OT)</h2>'
            f'<table><tr><th>Method</th><th>P@1</th><th>P@5</th><th>P@10</th><th>Hub Skew</th></tr>'
            f'{"".join(rows)}</table>'
            f'<p class="note">OT retrieval uses batch Sinkhorn to assign queries globally, '
            f'preventing hub monopolisation. Best for slang/OOV translation.</p>'
            f'<p>Run ID: {html.escape(result.get("run_id","N/A"))}</p>'
        )


# ----------------------------------------------------------------- main run --

def run_direction(direction, train_pairs, test_pairs, embeddings,
                  csls_k, csls_ref_size, ot_k_cand, ot_reg, special_path, output_dir):
    sl, tl = direction.split("-")
    ss, ts = embeddings[sl], embeddings[tl]
    sm, tm, valid = build_matrices(train_pairs, ss, ts)
    if len(valid) < 300:
        raise RuntimeError(f"{direction}: only {len(valid)} anchors (need >=300)")
    print(f"  In-vocab anchors: {len(valid)}")

    # Aligners
    a_r2 = CrossLingualAligner(); a_r2.train(sm, tm, normalize=True, mean_center=False)
    # Centered-space aligner (R3 style: full center, NO tgt_mean restore at train time,
    # but the new align.py DOES restore tgt_mean. To match R3 behaviour exactly we need
    # a special flag. Simplest: retrain then manually zero tgt_mean for retrieval.
    # For clarity: use mean_center=True (correct math) as "r3cs" baseline here.
    a_r3 = CrossLingualAligner(); a_r3.train(sm, tm, normalize=True, mean_center=True)

    # Mapped training vectors for CSLS reference set
    m_r2 = a_r2.translate_word(sm)
    m_r3 = a_r3.translate_word(sm)

    # CSLS retrievers
    cr2  = CSLSRetriever(ts, m_r2, k=csls_k, max_reference_vectors=csls_ref_size)
    cr3  = CSLSRetriever(ts, m_r3, k=csls_k, max_reference_vectors=csls_ref_size)

    # OT retrievers (built once, reused for both aligners)
    print("  Building OT retriever for r2 mapping ...", flush=True)
    otr2 = OTRetriever(ts, k_candidates=ot_k_cand, reg=ot_reg)
    print("  Building OT retriever for r3 mapping ...", flush=True)
    otr3 = OTRetriever(ts, k_candidates=ot_k_cand, reg=ot_reg)

    sg = {}
    if special_path and os.path.exists(special_path) and direction == "ja-zh":
        sg = load_special_dictionary(special_path)

    result = {"direction": direction, "pivot_training_pairs": len(valid),
              "held_out_test_pairs": len(test_pairs), "methods": {}}

    # Standard (per-query) methods
    standard_variants = [
        ("cosine_r2",  a_r2, None, False),
        ("csls_r2",    a_r2, cr2,  False),
        ("cosine_r3cs",a_r3, None, False),
        ("csls_r3cs",  a_r3, cr3,  False),
    ]
    for mkey, aligner, retriever, _ in standard_variants:
        print(f"    [{mkey}] evaluating {len(test_pairs)} test pairs ...")
        prec, det = evaluate_standard(aligner, test_pairs, ss, ts, retriever)
        skew, _ = hubness_skewness(det)
        mr = {"precision_test": {str(k): v for k, v in prec.items()},
              "hubness_skewness": skew, "test_details": det}
        for gn, grows in sg.items():
            gp = [(s, t) for s, t, _ in grows]
            gprec, gdet = evaluate_standard(aligner, gp, ss, ts, retriever)
            mr[f"precision_{gn}"] = {str(k): v for k, v in gprec.items()}
            mr[f"{gn}_details"] = gdet
        result["methods"][mkey] = mr

    # OT (batch) methods
    ot_variants = [
        ("ot_r2",   a_r2, otr2),
        ("ot_r3cs", a_r3, otr3),
    ]
    for mkey, aligner, ot_ret in ot_variants:
        print(f"    [{mkey}] batch OT evaluating {len(test_pairs)} test pairs ...")
        prec, det = evaluate_ot(aligner, test_pairs, ss, ts, ot_ret)
        skew, _ = hubness_skewness(det)
        mr = {"precision_test": {str(k): v for k, v in prec.items()},
              "hubness_skewness": skew, "test_details": det}
        for gn, grows in sg.items():
            gp = [(s, t) for s, t, _ in grows]
            gprec, gdet = evaluate_ot(aligner, gp, ss, ts, ot_ret)
            mr[f"precision_{gn}"] = {str(k): v for k, v in gprec.items()}
            mr[f"{gn}_details"] = gdet
        result["methods"][mkey] = mr

    return result


def main():
    parser = argparse.ArgumentParser(description="PongPong R5: Optimal Transport retrieval")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--small", action="store_true")
    parser.add_argument("--max-words", type=int, default=200000)
    parser.add_argument("--direction", choices=["ja-zh", "zh-ja"], default="ja-zh")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--csls-k", type=int, default=10)
    parser.add_argument("--csls-ref-size", type=int, default=2000)
    parser.add_argument("--ot-k-candidates", type=int, default=500,
                        help="Candidate pool size per query for OT (default 500)")
    parser.add_argument("--ot-reg", type=float, default=0.05,
                        help="Sinkhorn regularisation (default 0.05)")
    args = parser.parse_args()
    if not args.skip_download:
        from research.run_experiment import download_all_data
        download_all_data(False)
    mw = 50000 if args.small else args.max_words
    rid = time.strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(RUNS_DIR, rid, "fifth_round", args.direction)
    os.makedirs(out, exist_ok=True)
    print("=" * 60)
    print(f"  PongPong Round 5 -- OT (Sinkhorn) Retrieval  [{args.direction}]")
    print(f"  Vocab cap      : {mw:,}")
    print(f"  OT candidates  : {args.ot_k_candidates}")
    print(f"  OT reg         : {args.ot_reg}")
    print(f"  Run ID         : {rid}")
    print("=" * 60)
    emb = load_embeddings(mw)
    pivot_sets, pmeta, test_sets = prepare_pivot_sets(emb, args.seed)
    result = run_direction(
        args.direction, pivot_sets[args.direction], test_sets[args.direction],
        emb, args.csls_k, args.csls_ref_size,
        args.ot_k_candidates, args.ot_reg,
        os.path.join(DATA_DIR, "slang_pairs_ja_zh.tsv"), out,
    )
    result.update({"run_id": rid, "pivot_metadata": pmeta, "max_words": mw,
                   "ot_k_candidates": args.ot_k_candidates, "ot_reg": args.ot_reg})
    jp = os.path.join(out, "results.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"[OK] JSON: {jp}")
    generate_charts(result, out)
    hp = os.path.join(out, "report.html")
    write_html_report(hp, result)
    print(f"[OK] HTML: {hp}")
    print("=" * 60)
    print(f"  ABLATION SUMMARY [{args.direction}]")
    print("=" * 60)
    for m, met in result["methods"].items():
        p = met["precision_test"]; sk = met["hubness_skewness"]
        p1  = p.get("1",  p.get(1,  0))
        p5  = p.get("5",  p.get(5,  0))
        p10 = p.get("10", p.get(10, 0))
        print(f"  {m:<18}  P@1={p1:.1f}%  P@5={p5:.1f}%  P@10={p10:.1f}%  Hub-Skew={sk:.2f}")
    print(f"  Output: {out}")
    print("=" * 60)


if __name__ == "__main__":
    main()
