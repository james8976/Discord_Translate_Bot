# -*- coding: utf-8 -*-
"""
PongPong 跨語言語意對齊 — 四組實驗流程
========================================
一鍵執行：下載資料 → 訓練對齊 → 評估 → 產生本機圖文報告

語言對：中英 (zh-en) · 中日 (ja-zh) · 英日 (en-ja) · 中英日 (zh-ja)

使用方式：
  python research/run_experiment.py                    # 四組完整實驗
  python research/run_experiment.py --small            # 精簡模式（50K 詞）
  python research/run_experiment.py --skip-download    # 跳過下載
  python research/run_experiment.py --pair ja-zh       # 只跑單一語言對
  python research/run_experiment.py --pair zh-en --pair en-ja

本機結果：research/results/runs/<timestamp>/
           research/results/latest/  （供網頁 /research/ 使用）
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from research.align import CrossLingualAligner
from research.confidence import ConfidenceEstimator, entropy_confidence
from research.config import (
    ALL_DICT_PAIRS,
    ALL_LANGS,
    DATA_DIR,
    EXPERIMENTS,
    FASTTEXT_URL_TEMPLATE,
    MUSE_DICT_FALLBACK,
    MUSE_DICT_GITHUB,
    RUNS_DIR,
)
from research.embeddings import EmbeddingSpace, load_fasttext_vectors
from research.report import (
    generate_pair_html,
    generate_pair_markdown,
    generate_summary_html,
    generate_summary_markdown,
    print_local_instructions,
    publish_latest,
    write_manifest,
)


def download_with_progress(url: str, dest: str) -> bool:
    """下載檔案並顯示進度"""
    if os.path.exists(dest):
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f'  [跳過] {os.path.basename(dest)} 已存在 ({size_mb:.1f} MB)')
        return True

    print(f'  下載中: {os.path.basename(dest)}...')
    start = time.time()
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (PongPong Research)')]
    urllib.request.install_opener(opener)

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 / total_size)
            mb = downloaded / 1024 / 1024
            total_mb = total_size / 1024 / 1024
            elapsed = time.time() - start
            speed = mb / elapsed if elapsed > 0 else 0
            print(f'\r    {pct:5.1f}% ({mb:.1f}/{total_mb:.1f} MB) {speed:.1f} MB/s', end='', flush=True)

    try:
        urllib.request.urlretrieve(url, dest, progress)
    except urllib.error.HTTPError as e:
        print(f'\r    [WARN] {e.code} {e.reason}')
        return False

    elapsed = time.time() - start
    size_mb = os.path.getsize(dest) / 1024 / 1024
    print(f'\r    完成！{size_mb:.1f} MB ({elapsed:.0f}s)')
    return True


def download_dict(src: str, tgt: str, dest: str) -> bool:
    """下載 MUSE 雙語詞典（GitHub 優先，失敗用備用 URL）"""
    if os.path.exists(dest):
        print(f'  [跳過] {os.path.basename(dest)} 已存在')
        return True
    url = MUSE_DICT_GITHUB.format(src, tgt)
    if download_with_progress(url, dest):
        return True
    fallback = MUSE_DICT_FALLBACK.format(src, tgt)
    return download_with_progress(fallback, dest)


def load_bilingual_dict(path: str) -> List[Tuple[str, str]]:
    pairs = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                pairs.append((parts[0], parts[1]))
    return pairs


def load_special_dict(path: str) -> Dict[str, List[Tuple[str, str, str]]]:
    """載入特殊詞/俚語測試集（TSV: src, tgt, category, desc）"""
    pairs: Dict[str, List[Tuple[str, str, str]]] = {'special': [], 'standard': []}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 4:
                src, tgt, category, desc = parts[0], parts[1], parts[2], parts[3]
                key = 'standard' if category == 'standard' else 'special'
                pairs[key].append((src, tgt, desc))
    return pairs


def build_matrices(dict_pairs, src_emb, tgt_emb):
    X, Y, valid_pairs = [], [], []
    for src_w, tgt_w in dict_pairs:
        if src_w in src_emb.word2vec and tgt_w in tgt_emb.word2vec:
            X.append(src_emb[src_w])
            Y.append(tgt_emb[tgt_w])
            valid_pairs.append((src_w, tgt_w))
    if not X:
        return np.empty((0, 0)), np.empty((0, 0)), []
    return np.array(X), np.array(Y), valid_pairs


def evaluate_precision(aligner, test_pairs, src_emb, tgt_emb, ks=(1, 5, 10)):
    results = {k: 0 for k in ks}
    total = 0
    details = []

    for src_w, tgt_w in test_pairs:
        if src_w not in src_emb.word2vec or tgt_w not in tgt_emb.word2vec:
            continue
        total += 1
        aligned = aligner.translate_word(src_emb[src_w])
        neighbors = tgt_emb.nearest_neighbors(aligned, k=max(ks))
        neighbor_words = [w for w, _ in neighbors]
        for k in ks:
            if tgt_w in neighbor_words[:k]:
                results[k] += 1
        details.append({
            'source': src_w,
            'expected': tgt_w,
            'top5': neighbor_words[:5],
            'found_at': neighbor_words.index(tgt_w) + 1 if tgt_w in neighbor_words else -1,
        })

    precisions = {k: (v / total * 100 if total > 0 else 0) for k, v in results.items()}
    return precisions, total, details


def hubness_analysis(aligner, test_words, src_emb, tgt_emb, k=10):
    neighbor_count = {}
    for src_w in test_words:
        if src_w not in src_emb.word2vec:
            continue
        aligned = aligner.translate_word(src_emb[src_w])
        for w, _ in tgt_emb.nearest_neighbors(aligned, k=k):
            neighbor_count[w] = neighbor_count.get(w, 0) + 1
    counts = list(neighbor_count.values())
    if not counts:
        return 0, 0, {}
    mean_k = np.mean(counts)
    skewness = float(np.mean(((np.array(counts) - mean_k) / (np.std(counts) + 1e-10)) ** 3))
    return mean_k, skewness, neighbor_count


def confidence_analysis(aligner, test_pairs, src_emb, tgt_emb):
    results = []
    for src_w, tgt_w, *rest in test_pairs:
        if src_w not in src_emb.word2vec:
            continue
        aligned = aligner.translate_word(src_emb[src_w])
        neighbors = tgt_emb.nearest_neighbors(aligned, k=20)
        distances = np.array([1 - sim for _, sim in neighbors])
        conf = entropy_confidence(distances)
        top1 = neighbors[0][0]
        results.append({
            'source': src_w,
            'expected': tgt_w,
            'predicted': top1,
            'confidence': conf,
            'correct': top1 == tgt_w,
            'desc': rest[0] if rest else '',
        })
    return results


def generate_charts(results_data: Dict[str, Any], output_dir: str, exp_config: Dict[str, str]) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    DARK_BG = '#2C2F33'
    TEXT_COLOR = '#FFFFFF'
    ACCENT_1, ACCENT_2, ACCENT_3 = '#5865F2', '#57F287', '#ED4245'
    ks = [1, 5, 10]
    title_suffix = f'{exp_config["label"]} ({exp_config["title"]})'

    std_prec = results_data.get('precision_standard', {})
    special_prec = results_data.get('precision_special', {})
    test_prec = results_data.get('precision_test', {})

    # 圖 1：Precision@K
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    series = []
    if test_prec:
        series.append(('MUSE Test', test_prec, ACCENT_1))
    if std_prec:
        series.append(('Standard', std_prec, ACCENT_2))
    if special_prec:
        series.append(('Special/Slang', special_prec, ACCENT_3))

    x = np.arange(len(ks))
    width = 0.8 / max(len(series), 1)
    for i, (label, prec, color) in enumerate(series):
        offset = (i - (len(series) - 1) / 2) * width
        bars = ax.bar(x + offset, [prec.get(k, 0) for k in ks], width, label=label, color=color, alpha=0.85)
        for bar in bars:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    f'{bar.get_height():.1f}%', ha='center', va='bottom', color=TEXT_COLOR, fontsize=9)

    ax.set_title(f'Precision@K — {title_suffix}', color=TEXT_COLOR, fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'P@{k}' for k in ks], color=TEXT_COLOR)
    ax.set_ylabel('Precision (%)', color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    ax.legend(facecolor='#36393f', edgecolor='#555', labelcolor=TEXT_COLOR)
    ax.set_ylim(0, 105)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'precision_comparison.png'), dpi=150, facecolor=DARK_BG)
    plt.close()
    print('  [OK] precision_comparison.png')

    # 圖 2：信心分數
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    std_conf = results_data.get('confidence_standard', [])
    special_conf = results_data.get('confidence_special', [])
    if std_conf:
        ax.hist(std_conf, bins=20, alpha=0.7, label='Standard', color=ACCENT_2, edgecolor='white', linewidth=0.5)
    if special_conf:
        ax.hist(special_conf, bins=20, alpha=0.7, label='Special/Slang', color=ACCENT_3, edgecolor='white', linewidth=0.5)
    ax.set_title(f'Confidence — {title_suffix}', color=TEXT_COLOR, fontsize=14, fontweight='bold')
    ax.set_xlabel('Confidence', color=TEXT_COLOR)
    ax.set_ylabel('Count', color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    ax.legend(facecolor='#36393f', edgecolor='#555', labelcolor=TEXT_COLOR)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'confidence_distribution.png'), dpi=150, facecolor=DARK_BG)
    plt.close()
    print('  [OK] confidence_distribution.png')

    # 圖 3：Hubness
    hub_counts = results_data.get('hubness_counts', {})
    if hub_counts:
        fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK_BG)
        ax.set_facecolor(DARK_BG)
        ax.hist(list(hub_counts.values()), bins=30, color=ACCENT_1, alpha=0.85, edgecolor='white', linewidth=0.5)
        skew = results_data.get('hubness_skewness', 0)
        ax.set_title(f'Hubness (skew={skew:.2f}) — {title_suffix}', color=TEXT_COLOR, fontsize=14, fontweight='bold')
        ax.tick_params(colors=TEXT_COLOR)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'hubness_distribution.png'), dpi=150, facecolor=DARK_BG)
        plt.close()
        print('  [OK] hubness_distribution.png')

    # 圖 4：特殊詞表
    special_details = results_data.get('special_details', [])
    if special_details:
        fig, ax = plt.subplots(figsize=(14, max(4, len(special_details) * 0.35 + 2)), facecolor=DARK_BG)
        ax.set_facecolor(DARK_BG)
        ax.axis('off')
        headers = [exp_config['src_col'], 'Expected', 'Predicted', 'Conf.', 'OK']
        table_data = [
            [d['source'], d['expected'], d['predicted'], f"{d['confidence']:.1%}", 'O' if d['correct'] else 'X']
            for d in special_details[:30]
        ]
        table = ax.table(cellText=table_data, colLabels=headers, loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1, 1.4)
        for (r, c), cell in table.get_celld().items():
            cell.set_facecolor('#36393f')
            cell.set_edgecolor('#555')
            cell.set_text_props(color=TEXT_COLOR)
            if r == 0:
                cell.set_facecolor(ACCENT_1)
                cell.set_text_props(color='white', fontweight='bold')
        ax.set_title(f'Special Words — {title_suffix}', color=TEXT_COLOR, fontsize=14, fontweight='bold', pad=20)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'special_results_table.png'), dpi=150, facecolor=DARK_BG, bbox_inches='tight')
        plt.close()
        print('  [OK] special_results_table.png')


def run_single_experiment(
    exp_id: str,
    exp_config: Dict[str, str],
    embedding_cache: Dict[str, EmbeddingSpace],
    output_dir: str,
    max_words: int,
) -> Dict[str, Any]:
    """執行單一語言對實驗"""
    src, tgt = exp_config['src'], exp_config['tgt']
    print(f'\n{"─" * 60}')
    print(f'  實驗: {exp_config["label"]} — {exp_config["title"]} ({exp_id})')
    print(f'{"─" * 60}')

    os.makedirs(output_dir, exist_ok=True)
    src_space = embedding_cache[src]
    tgt_space = embedding_cache[tgt]

    dict_path = os.path.join(DATA_DIR, exp_config['dict_file'])
    if not os.path.exists(dict_path):
        raise FileNotFoundError(f'詞典不存在: {dict_path}')

    all_pairs = load_bilingual_dict(dict_path)
    print(f'  詞典對數: {len(all_pairs):,}')

    np.random.seed(42)
    indices = np.random.permutation(len(all_pairs))
    split = int(len(all_pairs) * 0.8)
    train_pairs = [all_pairs[i] for i in indices[:split]]
    test_pairs = [all_pairs[i] for i in indices[split:]]

    X_train, Y_train, valid_train = build_matrices(train_pairs, src_space, tgt_space)
    if len(valid_train) < 10:
        raise RuntimeError(f'有效訓練對不足 ({len(valid_train)})，請確認嵌入與詞典語言一致')
    print(f'  有效訓練對: {len(valid_train):,}')

    aligner = CrossLingualAligner()
    aligner.train(X_train, Y_train)
    aligner.save(os.path.join(output_dir, f'W_{exp_id}.pkl'))
    print(f'  W 矩陣: {aligner.W.shape}')

    prec_test, n_test, _ = evaluate_precision(aligner, test_pairs, src_space, tgt_space)
    print(f'  MUSE 測試集 ({n_test} 對):')
    for k, v in prec_test.items():
        print(f'    P@{k} = {v:.1f}%')

    results_data: Dict[str, Any] = {
        'experiment_id': exp_id,
        'label': exp_config['label'],
        'title': exp_config['title'],
        'src_lang': src,
        'tgt_lang': tgt,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'max_words': max_words,
        'train_pairs': len(valid_train),
        'test_pairs': n_test,
        'precision_test': prec_test,
        'precision_standard': {},
        'precision_special': {},
        'confidence_standard': [],
        'confidence_special': [],
        'special_details': [],
        'standard_details': [],
        'hubness_skewness': 0,
        'hubness_counts': {},
    }

    slang_path = exp_config.get('slang_file')
    if slang_path:
        full_slang = os.path.join(DATA_DIR, slang_path)
        if os.path.exists(full_slang):
            special_dict = load_special_dict(full_slang)
            special_pairs = [(a, b) for a, b, _ in special_dict.get('special', [])]
            std_pairs = [(a, b) for a, b, _ in special_dict.get('standard', [])]

            if special_pairs:
                prec_sp, n_sp, _ = evaluate_precision(aligner, special_pairs, src_space, tgt_space)
                results_data['precision_special'] = prec_sp
                sp_conf = confidence_analysis(aligner, special_dict['special'], src_space, tgt_space)
                results_data['special_details'] = sp_conf
                results_data['confidence_special'] = [r['confidence'] for r in sp_conf]
                print(f'  特殊詞 ({n_sp} 對): P@1={prec_sp.get(1, 0):.1f}%')

            if std_pairs:
                prec_std, n_std, _ = evaluate_precision(aligner, std_pairs, src_space, tgt_space)
                results_data['precision_standard'] = prec_std
                std_conf = confidence_analysis(aligner, special_dict['standard'], src_space, tgt_space)
                results_data['standard_details'] = std_conf
                results_data['confidence_standard'] = [r['confidence'] for r in std_conf]
                print(f'  標準詞 ({n_std} 對): P@1={prec_std.get(1, 0):.1f}%')
        else:
            print(f'  [SKIP] 特殊詞檔不存在: {full_slang}')
    else:
        results_data['precision_standard'] = prec_test

    test_words = [p[0] for p in test_pairs[:500]]
    _, skew, hub_counts = hubness_analysis(aligner, test_words, src_space, tgt_space)
    results_data['hubness_skewness'] = skew
    results_data['hubness_counts'] = hub_counts
    print(f'  Hubness 偏度: {skew:.2f}')

    print('  產生圖表與報告...')
    generate_charts(results_data, output_dir, exp_config)
    generate_pair_html(results_data, output_dir, exp_config)
    generate_pair_markdown(results_data, output_dir, exp_config)

    save_data = {k: v for k, v in results_data.items() if k != 'hubness_counts'}
    with open(os.path.join(output_dir, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)

    return results_data


def download_all_data(skip_download: bool) -> None:
    if skip_download:
        print('\n[1/4] 跳過下載...')
        return

    print('\n[1/4] 下載 FastText 嵌入與 MUSE 詞典...')
    os.makedirs(DATA_DIR, exist_ok=True)

    for lang in ALL_LANGS:
        dest = os.path.join(DATA_DIR, f'wiki.{lang}.vec')
        download_with_progress(FASTTEXT_URL_TEMPLATE.format(lang), dest)

    for src, tgt in ALL_DICT_PAIRS:
        dest = os.path.join(DATA_DIR, f'{src}-{tgt}.txt')
        if not download_dict(src, tgt, dest):
            print(f'  [ERROR] 無法下載詞典 {src}-{tgt}')
            sys.exit(1)


def load_embeddings(max_words: int) -> Dict[str, EmbeddingSpace]:
    print(f'\n[2/4] 載入嵌入向量 (max {max_words:,} 詞)...')
    cache: Dict[str, EmbeddingSpace] = {}
    for lang in ALL_LANGS:
        vec_path = os.path.join(DATA_DIR, f'wiki.{lang}.vec')
        if not os.path.exists(vec_path):
            print(f'  [ERROR] 缺少 wiki.{lang}.vec，請先執行下載')
            sys.exit(1)
        t0 = time.time()
        vecs = load_fasttext_vectors(vec_path, max_words=max_words)
        cache[lang] = EmbeddingSpace(vecs)
        print(f'  {lang}: {len(vecs):,} 詞 ({time.time() - t0:.1f}s)')
    return cache


def main():
    parser = argparse.ArgumentParser(description='PongPong 四組跨語言對齊實驗')
    parser.add_argument('--small', action='store_true', help='精簡模式 (50K 詞)')
    parser.add_argument('--skip-download', action='store_true', help='跳過下載')
    parser.add_argument('--max-words', type=int, default=200000, help='最大詞彙量')
    parser.add_argument(
        '--pair', action='append', choices=list(EXPERIMENTS.keys()),
        help='只跑指定語言對（可多次指定）',
    )
    args = parser.parse_args()

    max_words = 50000 if args.small else args.max_words
    run_id = time.strftime('%Y-%m-%d_%H%M%S')
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    pair_ids = args.pair or list(EXPERIMENTS.keys())

    print('=' * 60)
    print('  PongPong 跨語言對齊 — 四組實驗')
    print(f'  模式: {"Small (50K)" if args.small else f"Full ({max_words:,} words)"}')
    print(f'  語言對: {", ".join(pair_ids)}')
    print(f'  Run ID: {run_id}')
    print('=' * 60)

    download_all_data(args.skip_download)
    embedding_cache = load_embeddings(max_words)

    print('\n[3/4] 執行各語言對實驗...')
    all_results: Dict[str, Dict[str, Any]] = {}
    failed: List[str] = []

    for exp_id in pair_ids:
        exp_config = EXPERIMENTS[exp_id]
        pair_dir = os.path.join(run_dir, exp_id)
        try:
            all_results[exp_id] = run_single_experiment(
                exp_id, exp_config, embedding_cache, pair_dir, max_words,
            )
        except Exception as e:
            print(f'  [FAILED] {exp_id}: {e}')
            failed.append(exp_id)

    if not all_results:
        print('\n[ERROR] 所有實驗均失敗')
        sys.exit(1)

    print('\n[4/4] 產生總覽報告...')
    generate_summary_markdown(run_dir, all_results, run_id)
    generate_summary_html(run_dir, all_results, run_id)
    write_manifest(run_dir, run_id)

    meta = {
        'run_id': run_id,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'max_words': max_words,
        'pairs': pair_ids,
        'failed': failed,
        'results': {
            exp_id: {
                'label': EXPERIMENTS[exp_id]['label'],
                'precision_test': data.get('precision_test', {}),
            }
            for exp_id, data in all_results.items()
        },
    }
    with open(os.path.join(run_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    latest_dir = publish_latest(run_dir)
    print_local_instructions(run_dir, run_id)
    print(f'\n  網頁檢視 (保留): https://hijiri4005.duckdns.org:8080/research/')
    print(f'  latest 目錄:     {latest_dir}')

    if failed:
        print(f'\n  [WARN] 失敗的實驗: {", ".join(failed)}')
        sys.exit(1)


if __name__ == '__main__':
    main()
