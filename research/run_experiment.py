# -*- coding: utf-8 -*-
"""
PongPong 跨語言語意對齊 — 完整實驗流程
========================================
一鍵執行：下載資料 → 訓練對齊 → 評估 → 產生圖表

使用方式：
  python research/run_experiment.py              # 完整實驗（需下載 ~3GB）
  python research/run_experiment.py --small       # 精簡模式（前 50000 詞）
  python research/run_experiment.py --skip-download  # 跳過下載（已有資料）

結果會輸出到 research/results/ 目錄
"""

import argparse
import os
import sys
import time
import json
import urllib.request
import numpy as np

# 確保能 import research 模組
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from research.align import CrossLingualAligner, procrustes_align
from research.embeddings import load_fasttext_vectors, EmbeddingSpace
from research.confidence import entropy_confidence, ConfidenceEstimator

# ── 路徑設定 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')

# ── 資料 URL ──
FASTTEXT_URLS = {
    'ja': 'https://dl.fbaipublicfiles.com/fasttext/vectors-wiki/wiki.ja.vec',
    'zh': 'https://dl.fbaipublicfiles.com/fasttext/vectors-wiki/wiki.zh.vec',
}
MUSE_DICT_URLS = {
    'ja-zh': 'https://dl.fbaipublicfiles.com/arrival/dictionaries/ja-zh.txt',
    'zh-ja': 'https://dl.fbaipublicfiles.com/arrival/dictionaries/zh-ja.txt',
}


def download_with_progress(url, dest):
    """下載檔案並顯示進度"""
    if os.path.exists(dest):
        size_mb = os.path.getsize(dest) / 1024 / 1024
        print(f'  [跳過] {os.path.basename(dest)} 已存在 ({size_mb:.1f} MB)')
        return
    print(f'  下載中: {os.path.basename(dest)}...')
    start = time.time()

    def progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 / total_size)
            mb = downloaded / 1024 / 1024
            total_mb = total_size / 1024 / 1024
            elapsed = time.time() - start
            speed = mb / elapsed if elapsed > 0 else 0
            print(f'\r    {pct:5.1f}% ({mb:.1f}/{total_mb:.1f} MB) {speed:.1f} MB/s', end='', flush=True)

    urllib.request.urlretrieve(url, dest, progress)
    elapsed = time.time() - start
    size_mb = os.path.getsize(dest) / 1024 / 1024
    print(f'\r    完成！{size_mb:.1f} MB ({elapsed:.0f}s)')


def load_bilingual_dict(path):
    """載入 MUSE 雙語詞典（格式：src_word tgt_word 一行一對）"""
    pairs = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                pairs.append((parts[0], parts[1]))
    return pairs


def load_slang_dict(path):
    """載入俚語測試集"""
    pairs = {'slang': [], 'standard': []}
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) >= 4:
                ja, zh, category, desc = parts[0], parts[1], parts[2], parts[3]
                key = 'standard' if category == 'standard' else 'slang'
                pairs[key].append((ja, zh, desc))
    return pairs


def build_matrices(dict_pairs, src_emb, tgt_emb):
    """從詞典對建立訓練矩陣（只保留兩邊都有嵌入的詞對）"""
    X, Y, valid_pairs = [], [], []
    for src_w, tgt_w in dict_pairs:
        if src_w in src_emb.word2vec and tgt_w in tgt_emb.word2vec:
            X.append(src_emb[src_w])
            Y.append(tgt_emb[tgt_w])
            valid_pairs.append((src_w, tgt_w))
    return np.array(X), np.array(Y), valid_pairs


def evaluate_precision(aligner, test_pairs, src_emb, tgt_emb, ks=[1, 5, 10]):
    """計算 Precision@K"""
    results = {k: 0 for k in ks}
    total = 0
    details = []

    for src_w, tgt_w in test_pairs:
        if src_w not in src_emb.word2vec or tgt_w not in tgt_emb.word2vec:
            continue
        total += 1
        src_vec = src_emb[src_w]
        aligned = aligner.translate_word(src_vec)
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
    """Hubness 分析：計算每個目標詞被當成最近鄰的次數"""
    neighbor_count = {}
    for src_w in test_words:
        if src_w not in src_emb.word2vec:
            continue
        aligned = aligner.translate_word(src_emb[src_w])
        neighbors = tgt_emb.nearest_neighbors(aligned, k=k)
        for w, _ in neighbors:
            neighbor_count[w] = neighbor_count.get(w, 0) + 1

    counts = list(neighbor_count.values())
    if not counts:
        return 0, 0, {}
    mean_k = np.mean(counts)
    skewness = float(np.mean(((np.array(counts) - mean_k) / (np.std(counts) + 1e-10)) ** 3))
    return mean_k, skewness, neighbor_count


def confidence_analysis(aligner, test_pairs, src_emb, tgt_emb):
    """信心分數分析"""
    estimator = ConfidenceEstimator(threshold=0.5)
    results = []

    for src_w, tgt_w, *rest in test_pairs:
        if src_w not in src_emb.word2vec:
            continue
        aligned = aligner.translate_word(src_emb[src_w])
        neighbors = tgt_emb.nearest_neighbors(aligned, k=20)
        distances = np.array([1 - sim for _, sim in neighbors])
        conf = entropy_confidence(distances)
        top1 = neighbors[0][0]
        correct = (top1 == tgt_w)
        desc = rest[0] if rest else ''
        results.append({
            'source': src_w, 'expected': tgt_w, 'predicted': top1,
            'confidence': conf, 'correct': correct, 'desc': desc,
        })
    return results


def generate_charts(results_data, output_dir):
    """產生所有論文用圖表"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    
    # 嘗試載入中文字體
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    DARK_BG = '#2C2F33'
    TEXT_COLOR = '#FFFFFF'
    ACCENT_1 = '#5865F2'  # Discord 藍
    ACCENT_2 = '#57F287'  # 綠
    ACCENT_3 = '#ED4245'  # 紅
    ACCENT_4 = '#FEE75C'  # 黃

    # ── 圖 1：Precision@K 對比（標準詞 vs 俚語）──
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    ks = [1, 5, 10]
    std_prec = results_data.get('precision_standard', {})
    slang_prec = results_data.get('precision_slang', {})
    x = np.arange(len(ks))
    width = 0.35
    bars1 = ax.bar(x - width/2, [std_prec.get(k, 0) for k in ks], width,
                   label='Standard', color=ACCENT_2, alpha=0.85)
    bars2 = ax.bar(x + width/2, [slang_prec.get(k, 0) for k in ks], width,
                   label='Slang', color=ACCENT_3, alpha=0.85)
    ax.set_xlabel('K', color=TEXT_COLOR, fontsize=13)
    ax.set_ylabel('Precision (%)', color=TEXT_COLOR, fontsize=13)
    ax.set_title('Precision@K: Standard vs Slang', color=TEXT_COLOR, fontsize=15, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels([f'P@{k}' for k in ks], color=TEXT_COLOR)
    ax.tick_params(colors=TEXT_COLOR)
    ax.legend(facecolor='#36393f', edgecolor='#555', labelcolor=TEXT_COLOR)
    ax.set_ylim(0, 105)
    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{bar.get_height():.1f}%', ha='center', va='bottom', color=TEXT_COLOR, fontsize=10)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1,
                f'{bar.get_height():.1f}%', ha='center', va='bottom', color=TEXT_COLOR, fontsize=10)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'precision_comparison.png'), dpi=150, facecolor=DARK_BG)
    plt.close()
    print('  [OK] precision_comparison.png')

    # ── 圖 2：信心分數分佈（標準 vs 俚語）──
    fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK_BG)
    ax.set_facecolor(DARK_BG)
    std_conf = results_data.get('confidence_standard', [])
    slang_conf = results_data.get('confidence_slang', [])
    if std_conf:
        ax.hist(std_conf, bins=20, alpha=0.7, label='Standard', color=ACCENT_2, edgecolor='white', linewidth=0.5)
    if slang_conf:
        ax.hist(slang_conf, bins=20, alpha=0.7, label='Slang', color=ACCENT_3, edgecolor='white', linewidth=0.5)
    ax.set_xlabel('Confidence Score', color=TEXT_COLOR, fontsize=13)
    ax.set_ylabel('Count', color=TEXT_COLOR, fontsize=13)
    ax.set_title('Confidence Distribution: Standard vs Slang', color=TEXT_COLOR, fontsize=15, fontweight='bold')
    ax.tick_params(colors=TEXT_COLOR)
    ax.legend(facecolor='#36393f', edgecolor='#555', labelcolor=TEXT_COLOR)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, 'confidence_distribution.png'), dpi=150, facecolor=DARK_BG)
    plt.close()
    print('  [OK] confidence_distribution.png')

    # ── 圖 3：Hubness 分佈 ──
    hub_counts = results_data.get('hubness_counts', {})
    if hub_counts:
        fig, ax = plt.subplots(figsize=(10, 6), facecolor=DARK_BG)
        ax.set_facecolor(DARK_BG)
        counts_arr = list(hub_counts.values())
        ax.hist(counts_arr, bins=30, color=ACCENT_1, alpha=0.85, edgecolor='white', linewidth=0.5)
        skew = results_data.get('hubness_skewness', 0)
        ax.set_xlabel('k-occurrence (times as nearest neighbor)', color=TEXT_COLOR, fontsize=13)
        ax.set_ylabel('Number of words', color=TEXT_COLOR, fontsize=13)
        ax.set_title(f'Hubness Distribution (Skewness={skew:.2f})', color=TEXT_COLOR, fontsize=15, fontweight='bold')
        ax.tick_params(colors=TEXT_COLOR)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'hubness_distribution.png'), dpi=150, facecolor=DARK_BG)
        plt.close()
        print('  [OK] hubness_distribution.png')

    # ── 圖 4：俚語翻譯案例表 ──
    slang_details = results_data.get('slang_details', [])
    if slang_details:
        fig, ax = plt.subplots(figsize=(14, max(4, len(slang_details) * 0.4 + 2)), facecolor=DARK_BG)
        ax.set_facecolor(DARK_BG)
        ax.axis('off')
        headers = ['Japanese', 'Expected', 'Predicted', 'Conf.', 'Correct']
        table_data = []
        for d in slang_details[:30]:
            table_data.append([
                d['source'], d['expected'], d['predicted'],
                f"{d['confidence']:.1%}", 'O' if d['correct'] else 'X'
            ])
        table = ax.table(cellText=table_data, colLabels=headers,
                         loc='center', cellLoc='center')
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1, 1.5)
        for (r, c), cell in table.get_celld().items():
            cell.set_facecolor('#36393f')
            cell.set_edgecolor('#555')
            cell.set_text_props(color=TEXT_COLOR)
            if r == 0:
                cell.set_facecolor(ACCENT_1)
                cell.set_text_props(color='white', fontweight='bold')
        ax.set_title('Slang Translation Results', color=TEXT_COLOR, fontsize=15,
                     fontweight='bold', pad=20)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, 'slang_results_table.png'), dpi=150,
                    facecolor=DARK_BG, bbox_inches='tight')
        plt.close()
        print('  [OK] slang_results_table.png')


def generate_html_report(results_data, output_dir):
    """產生 HTML 報告方便在瀏覽器中查看"""
    html = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>PongPong Research - Experiment Results</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; padding: 2rem; }
  h1 { color: #5865F2; margin-bottom: 1rem; }
  h2 { color: #57F287; margin: 2rem 0 1rem; border-bottom: 2px solid #333; padding-bottom: 0.5rem; }
  .card { background: #2C2F33; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; }
  .metric { display: inline-block; background: #36393f; border-radius: 8px; padding: 1rem 1.5rem; margin: 0.5rem; text-align: center; }
  .metric .value { font-size: 2rem; font-weight: bold; color: #5865F2; }
  .metric .label { font-size: 0.85rem; color: #999; }
  img { max-width: 100%; border-radius: 8px; margin: 1rem 0; }
  table { width: 100%; border-collapse: collapse; margin: 1rem 0; }
  th { background: #5865F2; color: white; padding: 0.7rem; }
  td { padding: 0.5rem 0.7rem; border-bottom: 1px solid #444; }
  tr:hover td { background: #36393f; }
  .correct { color: #57F287; } .wrong { color: #ED4245; }
  .conf-high { color: #57F287; } .conf-low { color: #ED4245; }
</style>
</head>
<body>
<h1>PongPong Cross-lingual Alignment Experiment Results</h1>
<p>Generated: """ + time.strftime('%Y-%m-%d %H:%M:%S') + """</p>

<h2>Precision@K</h2>
<div class="card">
"""
    # Precision metrics
    for label, key in [('Standard Words', 'precision_standard'), ('Slang Words', 'precision_slang')]:
        prec = results_data.get(key, {})
        html += f'<h3>{label}</h3>'
        for k, v in prec.items():
            color = '#57F287' if v > 50 else '#FEE75C' if v > 20 else '#ED4245'
            html += f'<div class="metric"><div class="value" style="color:{color}">{v:.1f}%</div><div class="label">P@{k}</div></div>'

    html += '</div><h2>Confidence Analysis</h2><div class="card">'
    std_conf = results_data.get('confidence_standard', [])
    slang_conf = results_data.get('confidence_slang', [])
    if std_conf:
        html += f'<div class="metric"><div class="value">{np.mean(std_conf):.1%}</div><div class="label">Avg Confidence (Standard)</div></div>'
    if slang_conf:
        html += f'<div class="metric"><div class="value">{np.mean(slang_conf):.1%}</div><div class="label">Avg Confidence (Slang)</div></div>'

    html += '</div><h2>Charts</h2><div class="card">'
    for img in ['precision_comparison.png', 'confidence_distribution.png', 'hubness_distribution.png', 'slang_results_table.png']:
        if os.path.exists(os.path.join(output_dir, img)):
            html += f'<img src="{img}" alt="{img}">'

    # Slang details table
    html += '</div><h2>Slang Translation Details</h2><div class="card"><table><tr><th>Japanese</th><th>Expected</th><th>Predicted</th><th>Confidence</th><th>Result</th><th>Description</th></tr>'
    for d in results_data.get('slang_details', []):
        cls = 'correct' if d['correct'] else 'wrong'
        conf_cls = 'conf-high' if d['confidence'] > 0.5 else 'conf-low'
        html += f'<tr><td>{d["source"]}</td><td>{d["expected"]}</td><td>{d["predicted"]}</td>'
        html += f'<td class="{conf_cls}">{d["confidence"]:.1%}</td>'
        html += f'<td class="{cls}">{"O" if d["correct"] else "X"}</td>'
        html += f'<td>{d.get("desc","")}</td></tr>'

    html += '</table></div></body></html>'

    report_path = os.path.join(output_dir, 'report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'  [OK] report.html')
    return report_path


# ══════════════════════════════════════════════════════════════
#  主程序
# ══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description='PongPong Cross-lingual Alignment Experiment')
    parser.add_argument('--small', action='store_true', help='Use smaller vocabulary (50K words)')
    parser.add_argument('--skip-download', action='store_true', help='Skip downloading data')
    parser.add_argument('--max-words', type=int, default=200000, help='Max words to load')
    args = parser.parse_args()

    max_words = 50000 if args.small else args.max_words
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RESULTS_DIR, exist_ok=True)

    print('=' * 60)
    print('  PongPong Cross-lingual Alignment Experiment')
    print(f'  Mode: {"Small (50K)" if args.small else f"Full ({max_words:,} words)"}')
    print('=' * 60)

    # ── 1. 下載資料 ──
    if not args.skip_download:
        print('\n[1/6] Downloading data...')
        for lang, url in FASTTEXT_URLS.items():
            dest = os.path.join(DATA_DIR, f'wiki.{lang}.vec')
            download_with_progress(url, dest)
        for name, url in MUSE_DICT_URLS.items():
            dest = os.path.join(DATA_DIR, f'{name}.txt')
            download_with_progress(url, dest)
    else:
        print('\n[1/6] Skipping download...')

    # ── 2. 載入嵌入向量 ──
    print(f'\n[2/6] Loading embeddings (max {max_words:,} words)...')
    ja_vec_path = os.path.join(DATA_DIR, 'wiki.ja.vec')
    zh_vec_path = os.path.join(DATA_DIR, 'wiki.zh.vec')

    if not os.path.exists(ja_vec_path) or not os.path.exists(zh_vec_path):
        print('  [ERROR] Embedding files not found! Run without --skip-download first.')
        return

    t0 = time.time()
    ja_vecs = load_fasttext_vectors(ja_vec_path, max_words=max_words)
    print(f'  Japanese: {len(ja_vecs):,} words ({time.time()-t0:.1f}s)')
    t0 = time.time()
    zh_vecs = load_fasttext_vectors(zh_vec_path, max_words=max_words)
    print(f'  Chinese:  {len(zh_vecs):,} words ({time.time()-t0:.1f}s)')

    ja_space = EmbeddingSpace(ja_vecs)
    zh_space = EmbeddingSpace(zh_vecs)

    # ── 3. 載入詞典 & 訓練對齊 ──
    print('\n[3/6] Training Procrustes alignment...')
    dict_path = os.path.join(DATA_DIR, 'ja-zh.txt')
    if not os.path.exists(dict_path):
        print('  [ERROR] Dictionary not found!')
        return

    all_pairs = load_bilingual_dict(dict_path)
    print(f'  Dictionary pairs loaded: {len(all_pairs):,}')

    # 分 80% 訓練 / 20% 測試
    np.random.seed(42)
    indices = np.random.permutation(len(all_pairs))
    split = int(len(all_pairs) * 0.8)
    train_pairs = [all_pairs[i] for i in indices[:split]]
    test_pairs = [all_pairs[i] for i in indices[split:]]

    X_train, Y_train, valid_train = build_matrices(train_pairs, ja_space, zh_space)
    print(f'  Valid training pairs: {len(valid_train):,} (of {len(train_pairs):,})')

    aligner = CrossLingualAligner()
    aligner.train(X_train, Y_train)
    print(f'  Rotation matrix W: {aligner.W.shape}')
    print(f'  W is orthogonal: {np.allclose(aligner.W @ aligner.W.T, np.eye(aligner.W.shape[0]), atol=1e-4)}')

    # 儲存 W 矩陣
    aligner.save(os.path.join(RESULTS_DIR, 'W_ja_zh.pkl'))

    # ── 4. 評估 Precision@K ──
    print('\n[4/6] Evaluating Precision@K...')
    prec_test, n_test, test_details = evaluate_precision(aligner, test_pairs, ja_space, zh_space)
    print(f'  Test set: {n_test} valid pairs')
    for k, v in prec_test.items():
        print(f'  Precision@{k} = {v:.1f}%')

    # ── 5. 俚語測試 ──
    print('\n[5/6] Evaluating slang translation...')
    slang_path = os.path.join(DATA_DIR, 'slang_pairs_ja_zh.tsv')
    results_data = {
        'precision_standard': {}, 'precision_slang': {},
        'confidence_standard': [], 'confidence_slang': [],
        'slang_details': [], 'standard_details': [],
        'hubness_counts': {}, 'hubness_skewness': 0,
    }

    if os.path.exists(slang_path):
        slang_dict = load_slang_dict(slang_path)
        slang_pairs = [(ja, zh) for ja, zh, _ in slang_dict.get('slang', [])]
        std_pairs = [(ja, zh) for ja, zh, _ in slang_dict.get('standard', [])]

        if slang_pairs:
            prec_slang, n_slang, _ = evaluate_precision(aligner, slang_pairs, ja_space, zh_space)
            print(f'  Slang pairs: {n_slang} valid')
            for k, v in prec_slang.items():
                print(f'    Slang P@{k} = {v:.1f}%')
            results_data['precision_slang'] = prec_slang

            slang_conf_results = confidence_analysis(aligner, slang_dict['slang'], ja_space, zh_space)
            results_data['slang_details'] = slang_conf_results
            results_data['confidence_slang'] = [r['confidence'] for r in slang_conf_results]

        if std_pairs:
            prec_std, n_std, _ = evaluate_precision(aligner, std_pairs, ja_space, zh_space)
            print(f'  Standard pairs: {n_std} valid')
            for k, v in prec_std.items():
                print(f'    Standard P@{k} = {v:.1f}%')
            results_data['precision_standard'] = prec_std

            std_conf_results = confidence_analysis(aligner, slang_dict['standard'], ja_space, zh_space)
            results_data['standard_details'] = std_conf_results
            results_data['confidence_standard'] = [r['confidence'] for r in std_conf_results]
    else:
        print('  [SKIP] Slang test file not found')
        results_data['precision_standard'] = prec_test

    # Hubness 分析
    print('\n  Running hubness analysis...')
    test_words = [p[0] for p in test_pairs[:500]]
    mean_k, skew, hub_counts = hubness_analysis(aligner, test_words, ja_space, zh_space)
    results_data['hubness_skewness'] = skew
    results_data['hubness_counts'] = hub_counts
    print(f'  Hubness skewness: {skew:.2f} (>1 = problematic)')

    # ── 6. 產生圖表 & 報告 ──
    print('\n[6/6] Generating charts and report...')
    generate_charts(results_data, RESULTS_DIR)
    report_path = generate_html_report(results_data, RESULTS_DIR)

    # 儲存原始數據
    save_data = {k: v for k, v in results_data.items() if k != 'hubness_counts'}
    save_data['hubness_skewness'] = results_data['hubness_skewness']
    with open(os.path.join(RESULTS_DIR, 'results.json'), 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2, default=str)

    print('\n' + '=' * 60)
    print('  Experiment complete!')
    print('=' * 60)
    print(f'\n  Results saved to: {RESULTS_DIR}/')
    print(f'  Open report:      {report_path}')
    print(f'\n  Quick view: open the report.html in your browser!')


if __name__ == '__main__':
    main()
