# -*- coding: utf-8 -*-
"""
PongPong 研究模組 — Demo 測試腳本
用合成資料驗證整個 Procrustes 對齊 + 信心分數流程
不需要下載任何外部資料即可執行
"""

import numpy as np
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from research.align import CrossLingualAligner, procrustes_align
from research.confidence import entropy_confidence, ConfidenceEstimator
from research.embeddings import EmbeddingSpace

np.random.seed(42)

print("=" * 60)
print("  PongPong 跨語言語意對齊 — Demo 測試")
print("=" * 60)

# ── Step 1：建立模擬的詞嵌入空間 ──
print("\n📦 Step 1：建立模擬詞嵌入（300 維）...")

DIM = 300
N_WORDS = 500
N_ANCHOR = 200  # 種子詞典大小

# 中文空間（目標語言）：隨機產生 500 個詞向量
zh_words = [f"zh_word_{i}" for i in range(N_WORDS)]
zh_vecs = np.random.randn(N_WORDS, DIM).astype(np.float32)
# 正規化
zh_vecs /= np.linalg.norm(zh_vecs, axis=1, keepdims=True)

# 日文空間（源語言）：把中文空間旋轉 + 加噪音 = 模擬日文
# 產生一個隨機正交矩陣作為「真實旋轉」
random_matrix = np.random.randn(DIM, DIM)
Q, _ = np.linalg.qr(random_matrix)  # QR 分解得到正交矩陣

ja_words = [f"ja_word_{i}" for i in range(N_WORDS)]
ja_vecs_clean = zh_vecs @ Q.T  # 旋轉（完美對應）
noise = np.random.randn(N_WORDS, DIM) * 0.05  # 加一點噪音
ja_vecs = (ja_vecs_clean + noise).astype(np.float32)
ja_vecs /= np.linalg.norm(ja_vecs, axis=1, keepdims=True)

print(f"  中文空間：{len(zh_words)} 個詞 × {DIM} 維")
print(f"  日文空間：{len(ja_words)} 個詞 × {DIM} 維")

# ── Step 2：用種子詞典訓練 Procrustes 對齊 ──
print(f"\n🧮 Step 2：用 {N_ANCHOR} 對種子詞典訓練 Procrustes 對齊...")

X_anchor = ja_vecs[:N_ANCHOR]  # 日文錨點
Y_anchor = zh_vecs[:N_ANCHOR]  # 中文錨點

aligner = CrossLingualAligner()
aligner.train(X_anchor, Y_anchor)

print(f"  旋轉矩陣 W 形狀：{aligner.W.shape}")
print(f"  W 是否為正交矩陣：{np.allclose(aligner.W @ aligner.W.T, np.eye(DIM), atol=1e-5)}")

# ── Step 3：測試翻譯（用未參與訓練的詞）──
print(f"\n🔍 Step 3：在 {N_WORDS - N_ANCHOR} 個未見過的測試詞上評估...")

zh_space = EmbeddingSpace(dict(zip(zh_words, zh_vecs)))

correct_at_1 = 0
correct_at_5 = 0
test_count = N_WORDS - N_ANCHOR

for i in range(N_ANCHOR, N_WORDS):
    ja_vec = ja_vecs[i]
    aligned = aligner.translate_word(ja_vec)
    neighbors = zh_space.nearest_neighbors(aligned, k=5)
    
    expected = zh_words[i]  # 正確答案
    top1 = neighbors[0][0]
    top5_words = [w for w, _ in neighbors]
    
    if top1 == expected:
        correct_at_1 += 1
    if expected in top5_words:
        correct_at_5 += 1

p_at_1 = correct_at_1 / test_count * 100
p_at_5 = correct_at_5 / test_count * 100

print(f"  Precision@1 = {p_at_1:.1f}% ({correct_at_1}/{test_count})")
print(f"  Precision@5 = {p_at_5:.1f}% ({correct_at_5}/{test_count})")

# ── Step 4：信心分數 Demo ──
print(f"\n📊 Step 4：信心分數計算...")

estimator = ConfidenceEstimator(threshold=0.6)

# 高信心案例：第 250 個詞（有明確對應）
ja_vec_clear = ja_vecs[250]
aligned_clear = aligner.translate_word(ja_vec_clear)
neighbors_clear = zh_space.nearest_neighbors(aligned_clear, k=10)
distances_clear = np.array([1 - sim for _, sim in neighbors_clear])
conf_clear = entropy_confidence(distances_clear)
print(f"  案例 A（正常詞）：信心 = {conf_clear:.1%} → {estimator.classify(conf_clear)}")
print(f"    Top 3 候選：{[(w, f'{s:.3f}') for w, s in neighbors_clear[:3]]}")

# 低信心案例：用隨機向量（模擬俚語/OOV）
random_vec = np.random.randn(DIM).astype(np.float32)
random_vec /= np.linalg.norm(random_vec)
aligned_random = aligner.translate_word(random_vec)
neighbors_random = zh_space.nearest_neighbors(aligned_random, k=10)
distances_random = np.array([1 - sim for _, sim in neighbors_random])
conf_random = entropy_confidence(distances_random)
print(f"  案例 B（隨機/俚語）：信心 = {conf_random:.1%} → {estimator.classify(conf_random)}")
print(f"    Top 3 候選：{[(w, f'{s:.3f}') for w, s in neighbors_random[:3]]}")

# ── 結果總結 ──
print("\n" + "=" * 60)
print("  ✅ Demo 完成！所有模組正常運作")
print("=" * 60)
print(f"""
下一步：
  1. 執行 python research/download_data.py 下載真實嵌入資料
  2. 用真實的 FastText 嵌入重跑實驗
  3. 加入俚語測試集評估邊界效能
""")
