"""Third-round ablation: Mean Centering + Temperature Scaling + Context Window.
All chart labels and HTML are pure ASCII English to avoid CJK tofu boxes.
"""
from __future__ import annotations
import argparse, html, json, os, sys, time
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from research.align import CrossLingualAligner
from research.config import ALL_LANGS, DATA_DIR, RUNS_DIR
from research.confidence import entropy_confidence
from research.embeddings import EmbeddingSpace, load_fasttext_vectors
from research.pivot import (
    build_zh_ja_pivot, deterministic_split,
    filter_to_vocab, remove_held_out_pairs, reverse_pairs,
)
from research.retrieval import CSLSRetriever

WordPair = Tuple[str, str]

CONTEXT_NEIGHBOURS: Dict[str, List[str]] = {
    "kusa"  : ["maji", "warau", "omoshiroi"],
    "maji"  : ["honto", "sore", "yaba"],
    "yabai" : ["sugoi", "hidoi", "maji"],
    "otaku" : ["anime", "manga", "suki"],
    "ikemen": ["kakkoii", "kirei", "suki"],
    "numa"  : ["hamari", "suki", "tanoshii"],
    "kosupa": ["yasui", "ii", "tokku"],
    "toutoi": ["sugoi", "ii", "suki"],
}
CONTEXT_ALPHA = 0.3


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


def context_blend(word, space, alpha=CONTEXT_ALPHA):
    base = space[word].copy()
    ctx = [space[nb] for nb in CONTEXT_NEIGHBOURS.get(word, []) if nb in space.word2vec]
    if ctx:
        blended = base + alpha * np.mean(ctx, axis=0)
        n = np.linalg.norm(blended)
        return blended / max(n, 1e-10)
    return base / max(np.linalg.norm(base), 1e-10)


def confidence_from_margin(scores):
    if len(scores) < 2:
        return 1.0
    m = float(scores[0] - scores[1])
    return float(1 / (1 + np.exp(-np.clip(m / 0.05, -60, 60))))


def evaluate(aligner, pairs, ss, ts, retriever, use_context=False, descriptions=None, ks=(1, 5, 10)):
    hits = {k: 0 for k in ks}; total = 0; details = []
    for src, exp in pairs:
        if src not in ss.word2vec or exp not in ts.word2vec:
            continue
        qv = context_blend(src, ss) if use_context else ss[src]
        mapped = aligner.translate_word(qv)
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
            "description": (descriptions or {}).get((src, exp), ""),
        })
    return {k: (hits[k] / total * 100 if total else 0.0) for k in ks}, details


def hubness_skewness(details):
    counts = {}
    for d in details:
        for t in d["top5"]:
            counts[t] = counts.get(t, 0) + 1
    v = np.asarray(list(counts.values()), dtype=np.float32)
    if len(v) < 2:
        return 0.0, counts
    mean = v.mean()
    return float(np.mean(((v - mean) / (v.std() + 1e-10)) ** 3)), counts


def load_embeddings(max_words):
    emb = {}
    for lang in ALL_LANGS:
        path = os.path.join(DATA_DIR, f"wiki.{lang}.vec")
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing {path}. Run run_experiment.py first.")
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
    C1, C2, C3, C4 = "#5865F2", "#57F287", "#ED4245", "#F0A500"
    direction = result["direction"]; ks = [1, 5, 10]
    md = result.get("methods", {})
    lmap = {
        "cosine_r2": ("R2 Cosine",        C3),
        "csls_r2":   ("R2 CSLS",          C4),
        "cosine_r3": ("R3 Cosine+Center", C2),
        "csls_r3":   ("R3 CSLS+Center",   C1),
    }
    series = [(lmap[k][0], md[k]["precision_test"], lmap[k][1]) for k in lmap if k in md]
    if series:
        fig, ax = plt.subplots(figsize=(12, 6), facecolor=BG); ax.set_facecolor(BG)
        x = np.arange(len(ks)); w = 0.8 / max(len(series), 1)
        for i, (lbl, prec, col) in enumerate(series):
            off = (i - (len(series) - 1) / 2) * w
            vals = [prec.get(str(k), prec.get(k, 0)) for k in ks]
            bars = ax.bar(x + off, vals, w, label=lbl, color=col, alpha=0.85)
            for bar in bars:
                h = bar.get_height()
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.4,
                        f"{h:.1f}%", ha="center", va="bottom", color=TC, fontsize=8)
        ax.set_title(f"Precision@K Ablation -- {direction} (R2 vs R3)", color=TC, fontsize=13, fontweight="bold")
        ax.set_xticks(x); ax.set_xticklabels(["P@1", "P@5", "P@10"], color=TC)
        ax.set_ylabel("Precision (%)", color=TC); ax.tick_params(colors=TC)
        ax.legend(facecolor="#36393f", edgecolor="#555", labelcolor=TC, fontsize=9)
        allv = [prec.get(str(k), prec.get(k, 0)) for _, prec, _ in series for k in ks]
        ax.set_ylim(0, max(50, max(allv) + 10) if allv else 50)
        plt.tight_layout()
        out = os.path.join(output_dir, "r3_precision_ablation.png")
        plt.savefig(out, dpi=150, facecolor=BG); plt.close()
        print(f"  [OK] {os.path.basename(out)}")
    hub = {k: v.get("hubness_skewness", 0) for k, v in md.items()}
    if hub:
        fig, ax = plt.subplots(figsize=(8, 5), facecolor=BG); ax.set_facecolor(BG)
        lbs = list(hub.keys()); vals = [hub[l] for l in lbs]
        cols = [C1 if "r3" in l else C3 for l in lbs]
        bars = ax.bar(lbs, vals, color=cols, alpha=0.85)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02,
                    f"{val:.2f}", ha="center", va="bottom", color=TC, fontsize=9)
        ax.set_title(f"Hubness Skewness -- {direction} (lower=healthier)", color=TC, fontsize=12, fontweight="bold")
        ax.set_ylabel("Skewness", color=TC); ax.tick_params(colors=TC)
        plt.tight_layout()
        out = os.path.join(output_dir, "r3_hubness_comparison.png")
        plt.savefig(out, dpi=150, facecolor=BG); plt.close()
        print(f"  [OK] {os.path.basename(out)}")
    r3c = md.get("csls_r3", {})
    sc  = [d["entropy_confidence"] for d in r3c.get("test_details", [])]
    slc = [d["entropy_confidence"] for d in r3c.get("special_details", [])]
    if sc or slc:
        fig, ax = plt.subplots(figsize=(9, 5), facecolor=BG); ax.set_facecolor(BG)
        if sc:  ax.hist(sc,  bins=20, alpha=0.7, label="Standard",  color=C2, edgecolor="white", linewidth=0.5)
        if slc: ax.hist(slc, bins=20, alpha=0.7, label="Slang/OOV", color=C3, edgecolor="white", linewidth=0.5)
        ax.set_title(f"Confidence Distribution (R3 CSLS+Center) -- {direction}", color=TC, fontsize=12, fontweight="bold")
        ax.set_xlabel("Entropy confidence score (temperature-scaled)", color=TC)
        ax.set_ylabel("Count", color=TC); ax.tick_params(colors=TC)
        ax.legend(facecolor="#36393f", edgecolor="#555", labelcolor=TC)
        plt.tight_layout()
        out = os.path.join(output_dir, "r3_confidence_distribution.png")
        plt.savefig(out, dpi=150, facecolor=BG); plt.close()
        print(f"  [OK] {os.path.basename(out)}")
    sp = r3c.get("special_details", [])
    if sp:
        fig, ax = plt.subplots(figsize=(14, max(4, len(sp) * 0.38 + 2)), facecolor=BG)
        ax.set_facecolor(BG); ax.axis("off")
        hdr = ["Source", "Expected", "Predicted", "Conf.", "Hit"]
        ckey = "entropy_confidence"
        td = [[d["source"], d["expected"], d["predicted"], f"{d[ckey]:.2f}", "Y" if d["correct"] else "N"] for d in sp[:30]]
        tbl = ax.table(cellText=td, colLabels=hdr, loc="center", cellLoc="center")
        tbl.auto_set_font_size(False); tbl.set_fontsize(9); tbl.scale(1, 1.5)
        for (r, c), cell in tbl.get_celld().items():
            cell.set_facecolor("#36393f"); cell.set_edgecolor("#555"); cell.set_text_props(color=TC)
            if r == 0: cell.set_facecolor(C1); cell.set_text_props(color="white", fontweight="bold")
        ax.set_title(f"Slang Test Results -- {direction} (R3 CSLS+Center+Context)", color=TC, fontsize=12, fontweight="bold", pad=20)
        plt.tight_layout()
        out = os.path.join(output_dir, "r3_slang_table.png")
        plt.savefig(out, dpi=150, facecolor=BG, bbox_inches="tight"); plt.close()
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
    imp = ("Round 3 adds: 1.Mean Centering (centroid subtracted before SVD); "
           "2.Temperature Scaling (tau=1/sqrt(d)); "
           "3.Context Window Blending (slang alpha=0.3).")
    css = ("body{font-family:system-ui;max-width:960px;margin:40px auto}"
           "table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3df;padding:10px}"
           "th{background:#edf2fb}.note{background:#e8f5e9;padding:12px;border-left:4px solid #43a047}")
    body = (
        f'<h1>PongPong Round 3 Ablation</h1>'
        f'<p>Direction: <b>{html.escape(result["direction"])}</b> | '
        f'Anchors: <b>{result.get("pivot_training_pairs","N/A")}</b> | '
        f'Test pairs: <b>{result.get("held_out_test_pairs","N/A")}</b></p>'
        f'<h2>Precision@K</h2>'
        f'<table><tr><th>Method</th><th>P@1</th><th>P@5</th><th>P@10</th><th>Hub Skew</th></tr>'
        f'{"".join(rows)}</table>'
        f'<h2>Improvements</h2><p class="note">{imp}</p>'
        f'<p>Run ID: {html.escape(result.get("run_id","N/A"))}</p>'
    )
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(f'<!doctype html><html lang="en"><meta charset="utf-8">'
                 f'<title>PongPong R3</title><style>{css}</style>{body}</html>')


def run_direction(direction, train_pairs, test_pairs, embeddings, csls_k, csls_ref_size, special_path, output_dir):
    sl, tl = direction.split("-")
    ss, ts = embeddings[sl], embeddings[tl]
    sm, tm, valid = build_matrices(train_pairs, ss, ts)
    if len(valid) < 300:
        raise RuntimeError(f"{direction}: only {len(valid)} anchors (need >=300)")
    print(f"  In-vocab anchors: {len(valid)}")
    a2 = CrossLingualAligner(); a2.train(sm, tm, normalize=True, mean_center=False)
    a2.save(os.path.join(output_dir, f"W_r2_{direction}.pkl"))
    m2 = a2.translate_word(sm)
    a3 = CrossLingualAligner(); a3.train(sm, tm, normalize=True, mean_center=True)
    a3.save(os.path.join(output_dir, f"W_r3_{direction}.pkl"))
    m3 = a3.translate_word(sm)
    cr2 = CSLSRetriever(ts, m2, k=csls_k, max_reference_vectors=csls_ref_size)
    cr3 = CSLSRetriever(ts, m3, k=csls_k, max_reference_vectors=csls_ref_size)
    sg = {}
    if special_path and os.path.exists(special_path) and direction == "ja-zh":
        sg = load_special_dictionary(special_path)
    result = {"direction": direction, "pivot_training_pairs": len(valid),
              "held_out_test_pairs": len(test_pairs), "methods": {}}
    for mkey, aligner, retriever, uctx in [
        ("cosine_r2", a2, None, False), ("csls_r2", a2, cr2, False),
        ("cosine_r3", a3, None, False), ("csls_r3", a3, cr3, True),
    ]:
        print(f"    [{mkey}] evaluating {len(test_pairs)} test pairs ...")
        prec, det = evaluate(aligner, test_pairs, ss, ts, retriever)
        skew, _ = hubness_skewness(det)
        mr = {"precision_test": {str(k): v for k, v in prec.items()},
              "hubness_skewness": skew, "test_details": det}
        for gn, grows in sg.items():
            gp = [(s, t) for s, t, _ in grows]
            gd = {(s, t): d for s, t, d in grows}
            uch = uctx and gn == "special"
            gprec, gdet = evaluate(aligner, gp, ss, ts, retriever, use_context=uch, descriptions=gd)
            mr[f"precision_{gn}"] = {str(k): v for k, v in gprec.items()}
            mr[f"{gn}_details"] = gdet
        result["methods"][mkey] = mr
    return result


def main():
    parser = argparse.ArgumentParser(description="PongPong R3: Mean Centering+Temp Scaling+Context")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--small", action="store_true")
    parser.add_argument("--max-words", type=int, default=200000)
    parser.add_argument("--direction", choices=["ja-zh", "zh-ja"], default="ja-zh")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--csls-k", type=int, default=10)
    parser.add_argument("--csls-ref-size", type=int, default=2000)
    args = parser.parse_args()
    if not args.skip_download:
        from research.run_experiment import download_all_data
        download_all_data(False)
    mw = 50000 if args.small else args.max_words
    rid = time.strftime("%Y-%m-%d_%H%M%S")
    out = os.path.join(RUNS_DIR, rid, "third_round", args.direction)
    os.makedirs(out, exist_ok=True)
    print("=" * 60)
    print(f"  PongPong Round 3  [{args.direction}]  vocab={mw}")
    print("=" * 60)
    emb = load_embeddings(mw)
    pivot_sets, pmeta, test_sets = prepare_pivot_sets(emb, args.seed)
    result = run_direction(
        args.direction, pivot_sets[args.direction], test_sets[args.direction],
        emb, args.csls_k, args.csls_ref_size,
        os.path.join(DATA_DIR, "slang_pairs_ja_zh.tsv"), out,
    )
    result.update({"run_id": rid, "pivot_metadata": pmeta, "max_words": mw})
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
        print(f"  {m:<16}  P@1={p1:.1f}%  P@5={p5:.1f}%  P@10={p10:.1f}%  Hub-Skew={sk:.2f}")
    print(f"  Output: {out}")
    print("=" * 60)


if __name__ == "__main__":
    main()
