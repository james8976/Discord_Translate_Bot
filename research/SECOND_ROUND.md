# 第二輪實驗：Pivot、CSLS 與 LLM 輔助評估

本流程不會改動第一輪實驗。它建立新的中日訓練錨點，並保留直接日中詞典的 20% 作獨立評測。

## 研究設計

1. 固定亂數種子切分中英與英日詞典。
2. 只用兩個訓練分割的英文交集建立中→日錨點。
3. 只保留英文一對一交集，避免未標注的多義詞污染訓練。
4. 依 FastText 前 `max_words` 詞表過濾；測試詞對也從 Pivot 訓練集中移除。
5. 在相同對齊矩陣下比較 cosine 與 CSLS；CSLS 只改變最近鄰檢索。
6. 日→中時，固定標準詞與俚語 TSV 額外作盲測。LLM 評分是輔助標記，不能取代人工黃金標註。

## 執行

先確保第一輪已下載 `wiki.en.vec`、`wiki.zh.vec`、`wiki.ja.vec` 與三份詞典，再執行：

```powershell
cd bot
python research/run_second_round.py --skip-download --direction ja-zh --method both
```

精簡測試（只讀 FastText 前 50,000 詞）：

```powershell
python research/run_second_round.py --skip-download --small --direction ja-zh --method both
```

結果寫入 `research/results/runs/<timestamp>/second_round/ja-zh/`：

- `pivot_zh_ja_train.tsv`、`pivot_ja_zh_train.tsv`：可稽核的產生錨點。
- `W_pivot_*.pkl`：正交對齊矩陣。
- `results.json`：完整 P@K、候選詞與 hubness 數據。
- `report.html`：可直接開啟的摘要。

## 選用 LLM 語義評估

設定 `OPENAI_API_KEY` 與明確選擇模型後才會送出請求。它只送出至多 `--llm-max-items` 個詞條的來源詞、預期詞與模型候選詞；預設完全停用。

```powershell
$env:OPENAI_API_KEY = "your_api_key"
$env:OPENAI_MODEL = "your_model_name"
python research/run_second_round.py --skip-download --direction ja-zh --method both --llm-judge --llm-max-items 30
```

LLM 輸出為 `wrong`、`partial`、`equivalent` 與 0–2 分，寫入 `results.json` 的 `llm_special_judgements`。開始論文實驗前，應隨機抽樣至少 20% 結果由人類標註者複核，並回報一致性。
