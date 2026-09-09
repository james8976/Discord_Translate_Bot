# -*- coding: utf-8 -*-
"""
實驗報告產生器 — 本機 Markdown / HTML（圖文合一，可離線開啟）
"""

import json
import os
import shutil
import time
from typing import Any, Dict, List, Optional

import numpy as np

from research.config import CHART_FILES, EXPERIMENTS


def _fmt_pct(value: float) -> str:
    return f'{value:.1f}%'


def _fmt_conf(value: float) -> str:
    return f'{value:.1%}'


def _avg_conf(values: List[float]) -> str:
    if not values:
        return 'N/A'
    return _fmt_conf(float(np.mean(values)))


def generate_pair_markdown(
    results_data: Dict[str, Any],
    output_dir: str,
    exp_config: Dict[str, str],
) -> str:
    """產生單一語言對的 REPORT.md（含圖片相對路徑）"""
    exp_id = exp_config['id']
    lines = [
        f"# PongPong 跨語言對齊實驗 — {exp_config['label']} ({exp_config['title']})",
        '',
        f'- **實驗 ID**: `{exp_id}`',
        f'- **產生時間**: {results_data.get("generated_at", time.strftime("%Y-%m-%d %H:%M:%S"))}',
        f'- **詞彙上限**: {results_data.get("max_words", "N/A"):,}',
        f'- **有效訓練對**: {results_data.get("train_pairs", "N/A")}',
        f'- **有效測試對**: {results_data.get("test_pairs", "N/A")}',
        '',
        '## Precision@K',
        '',
        '| 類別 | P@1 | P@5 | P@10 |',
        '|------|-----|-----|------|',
    ]

    for label, key in [('MUSE 測試集', 'precision_test'), ('標準詞', 'precision_standard'), ('特殊詞/俚語', 'precision_special')]:
        prec = results_data.get(key, {})
        if prec:
            lines.append(
                f'| {label} | {_fmt_pct(prec.get(1, 0))} | {_fmt_pct(prec.get(5, 0))} | {_fmt_pct(prec.get(10, 0))} |'
            )

    lines.extend([
        '',
        '## 信心分數',
        '',
        f'- 標準詞平均信心: {_avg_conf(results_data.get("confidence_standard", []))}',
        f'- 特殊詞平均信心: {_avg_conf(results_data.get("confidence_special", []))}',
        f'- Hubness 偏度: {results_data.get("hubness_skewness", 0):.2f}（>1 表示可能有 hubness 問題）',
        '',
        '## 圖表',
        '',
    ])

    for img in CHART_FILES:
        img_path = os.path.join(output_dir, img)
        if os.path.exists(img_path):
            lines.extend([f'### {img}', '', f'![{img}]({img})', ''])

    special = results_data.get('special_details', [])
    if special:
        lines.extend([
            '## 特殊詞彙翻譯明細',
            '',
            f'| {exp_config["src_col"]} | 預期 | 預測 | 信心 | 結果 | 說明 |',
            '|------|------|------|------|------|------|',
        ])
        for row in special[:40]:
            mark = '✓' if row.get('correct') else '✗'
            lines.append(
                f'| {row["source"]} | {row["expected"]} | {row["predicted"]} '
                f'| {_fmt_conf(row["confidence"])} | {mark} | {row.get("desc", "")} |'
            )
        lines.append('')

    report_path = os.path.join(output_dir, 'REPORT.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return report_path


def generate_pair_html(
    results_data: Dict[str, Any],
    output_dir: str,
    exp_config: Dict[str, str],
) -> str:
    """產生單一語言對的 report.html（本機可直接用瀏覽器開啟）"""
    exp_id = exp_config['id']
    generated = results_data.get('generated_at', time.strftime('%Y-%m-%d %H:%M:%S'))

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PongPong Research — {exp_config['label']}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; padding: 2rem; max-width: 1100px; margin: 0 auto; }}
  h1 {{ color: #5865F2; margin-bottom: 0.5rem; }}
  h2 {{ color: #57F287; margin: 2rem 0 1rem; border-bottom: 2px solid #333; padding-bottom: 0.5rem; }}
  .meta {{ color: #999; margin-bottom: 1.5rem; }}
  .card {{ background: #2C2F33; border-radius: 12px; padding: 1.5rem; margin: 1rem 0; }}
  .metric {{ display: inline-block; background: #36393f; border-radius: 8px; padding: 1rem 1.5rem; margin: 0.5rem; text-align: center; min-width: 100px; }}
  .metric .value {{ font-size: 1.8rem; font-weight: bold; color: #5865F2; }}
  .metric .label {{ font-size: 0.85rem; color: #999; margin-top: 4px; }}
  img {{ max-width: 100%; border-radius: 8px; margin: 1rem 0; border: 1px solid #444; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; font-size: 0.95rem; }}
  th {{ background: #5865F2; color: white; padding: 0.7rem; text-align: left; }}
  td {{ padding: 0.5rem 0.7rem; border-bottom: 1px solid #444; }}
  tr:hover td {{ background: #36393f; }}
  .correct {{ color: #57F287; font-weight: bold; }}
  .wrong {{ color: #ED4245; font-weight: bold; }}
  .conf-high {{ color: #57F287; }}
  .conf-low {{ color: #ED4245; }}
  .note {{ background: #36393f; padding: 1rem; border-radius: 8px; color: #ccc; margin-top: 1rem; }}
</style>
</head>
<body>
<h1>{exp_config['label']} — {exp_config['title']}</h1>
<p class="meta">實驗 ID: {exp_id} · 產生時間: {generated}</p>
"""

    html += '<h2>Precision@K</h2><div class="card">'
    for label, key in [('MUSE 測試集', 'precision_test'), ('標準詞', 'precision_standard'), ('特殊詞/俚語', 'precision_special')]:
        prec = results_data.get(key, {})
        if not prec:
            continue
        html += f'<h3>{label}</h3>'
        for k, v in sorted(prec.items()):
            color = '#57F287' if v > 50 else '#FEE75C' if v > 20 else '#ED4245'
            html += (
                f'<div class="metric"><div class="value" style="color:{color}">{v:.1f}%</div>'
                f'<div class="label">P@{k}</div></div>'
            )
    html += '</div>'

    html += '<h2>信心分數</h2><div class="card">'
    std_conf = results_data.get('confidence_standard', [])
    special_conf = results_data.get('confidence_special', [])
    if std_conf:
        html += f'<div class="metric"><div class="value">{_avg_conf(std_conf)}</div><div class="label">標準詞平均</div></div>'
    if special_conf:
        html += f'<div class="metric"><div class="value">{_avg_conf(special_conf)}</div><div class="label">特殊詞平均</div></div>'
    html += (
        f'<div class="metric"><div class="value">{results_data.get("hubness_skewness", 0):.2f}</div>'
        f'<div class="label">Hubness 偏度</div></div></div>'
    )

    html += '<h2>圖表</h2><div class="card">'
    for img in CHART_FILES:
        if os.path.exists(os.path.join(output_dir, img)):
            html += f'<h3>{img}</h3><img src="{img}" alt="{img}">'
    html += '</div>'

    special = results_data.get('special_details', [])
    if special:
        html += (
            f'</div><h2>特殊詞彙明細</h2><div class="card"><table>'
            f'<tr><th>{exp_config["src_col"]}</th><th>預期</th><th>預測</th>'
            f'<th>信心</th><th>結果</th><th>說明</th></tr>'
        )
        for row in special:
            cls = 'correct' if row.get('correct') else 'wrong'
            conf_cls = 'conf-high' if row.get('confidence', 0) > 0.5 else 'conf-low'
            html += (
                f'<tr><td>{row["source"]}</td><td>{row["expected"]}</td><td>{row["predicted"]}</td>'
                f'<td class="{conf_cls}">{_fmt_conf(row["confidence"])}</td>'
                f'<td class="{cls}">{"✓" if row.get("correct") else "✗"}</td>'
                f'<td>{row.get("desc", "")}</td></tr>'
            )
        html += '</table></div>'

    html += (
        '<p class="note">💡 此報告可離線開啟。所有圖片與本 HTML 在同一資料夾內，'
        '可直接從檔案總管雙擊 report.html 查看。</p></body></html>'
    )

    report_path = os.path.join(output_dir, 'report.html')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return report_path


def generate_summary_markdown(
    run_dir: str,
    all_results: Dict[str, Dict[str, Any]],
    run_id: str,
) -> str:
    """產生四組實驗總覽 SUMMARY.md"""
    lines = [
        '# PongPong 跨語言對齊 — 四組實驗總覽',
        '',
        f'- **Run ID**: `{run_id}`',
        f'- **產生時間**: {time.strftime("%Y-%m-%d %H:%M:%S")}',
        '',
        '## 實驗列表',
        '',
        '| 語言對 | 標題 | P@1 (MUSE) | P@5 | P@10 | 報告 |',
        '|--------|------|------------|-----|------|------|',
    ]

    for exp_id, exp in EXPERIMENTS.items():
        data = all_results.get(exp_id, {})
        prec = data.get('precision_test', {})
        rel = f'{exp_id}/REPORT.md'
        lines.append(
            f'| {exp["label"]} | {exp["title"]} | {_fmt_pct(prec.get(1, 0))} '
            f'| {_fmt_pct(prec.get(5, 0))} | {_fmt_pct(prec.get(10, 0))} | [{exp_id}]({rel}) |'
        )

    lines.extend(['', '## 各組圖表預覽', ''])

    for exp_id, exp in EXPERIMENTS.items():
        pair_dir = os.path.join(run_dir, exp_id)
        img = os.path.join(pair_dir, 'precision_comparison.png')
        if os.path.exists(img):
            lines.extend([
                f'### {exp["label"]} — {exp["title"]}',
                '',
                f'![{exp_id} precision]({exp_id}/precision_comparison.png)',
                '',
            ])

    lines.extend([
        '## 本機查看方式',
        '',
        '1. 用 VS Code / Cursor 開啟此 `SUMMARY.md`（可預覽 Markdown 與圖片）',
        '2. 雙擊各子資料夾的 `report.html` 查看完整圖文報告',
        '3. 從 VM 拉回結果：`powershell -File research/fetch_results.ps1`',
        '',
    ])

    path = os.path.join(run_dir, 'SUMMARY.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return path


def generate_summary_html(run_dir: str, all_results: Dict[str, Dict[str, Any]], run_id: str) -> str:
    """產生四組實驗總覽 SUMMARY.html"""
    rows = ''
    cards = ''
    for exp_id, exp in EXPERIMENTS.items():
        data = all_results.get(exp_id, {})
        prec = data.get('precision_test', {})
        rows += (
            f'<tr><td><strong>{exp["label"]}</strong></td><td>{exp["title"]}</td>'
            f'<td>{_fmt_pct(prec.get(1, 0))}</td><td>{_fmt_pct(prec.get(5, 0))}</td>'
            f'<td>{_fmt_pct(prec.get(10, 0))}</td>'
            f'<td><a href="{exp_id}/report.html">查看報告</a></td></tr>'
        )
        img_rel = f'{exp_id}/precision_comparison.png'
        if os.path.exists(os.path.join(run_dir, img_rel)):
            cards += f'<h3>{exp["label"]}</h3><img src="{img_rel}" alt="{exp_id}">'

    html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>PongPong Research — 四組實驗總覽</title>
<style>
  body {{ background: #1a1a2e; color: #e0e0e0; font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif; padding: 2rem; max-width: 1100px; margin: 0 auto; }}
  h1 {{ color: #5865F2; }} h2 {{ color: #57F287; margin-top: 2rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
  th {{ background: #5865F2; padding: 0.7rem; text-align: left; }}
  td {{ padding: 0.6rem; border-bottom: 1px solid #444; }}
  a {{ color: #7289da; }} img {{ max-width: 100%; border-radius: 8px; margin: 1rem 0; }}
  .note {{ background: #2C2F33; padding: 1rem; border-radius: 8px; margin-top: 2rem; }}
</style>
</head>
<body>
<h1>PongPong 跨語言對齊 — 四組實驗總覽</h1>
<p>Run ID: {run_id} · {time.strftime("%Y-%m-%d %H:%M:%S")}</p>
<h2>中英 · 中日 · 英日 · 中英日</h2>
<table>
<tr><th>語言對</th><th>方向</th><th>P@1</th><th>P@5</th><th>P@10</th><th>報告</th></tr>
{rows}
</table>
<h2>圖表預覽</h2>
{cards}
<p class="note">💡 本檔案可離線開啟。從 PowerShell 執行 <code>research/fetch_results.ps1</code> 可從 Oracle VM 拉回最新結果到本機。</p>
</body></html>"""

    path = os.path.join(run_dir, 'SUMMARY.html')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return path


def write_manifest(run_dir: str, run_id: str) -> str:
    """寫入 manifest.json 供 fetch_results.ps1 與驗證使用"""
    files: List[str] = []
    for root, _, filenames in os.walk(run_dir):
        for name in filenames:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, run_dir).replace('\\', '/')
            files.append(rel)
    manifest = {
        'run_id': run_id,
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'file_count': len(files),
        'files': sorted(files),
    }
    path = os.path.join(run_dir, 'manifest.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return path


def publish_latest(run_dir: str) -> str:
    """複製本次 run 到 results/latest/ 供網頁 /research/ 使用"""
    from research.config import LATEST_DIR

    if os.path.exists(LATEST_DIR):
        shutil.rmtree(LATEST_DIR)
    shutil.copytree(run_dir, LATEST_DIR)

    # 向後相容：舊版單一 ja-zh report.html 連結
    legacy = os.path.join(LATEST_DIR, 'report.html')
    if not os.path.exists(legacy):
        src = os.path.join(LATEST_DIR, 'SUMMARY.html')
        if os.path.exists(src):
            shutil.copy2(src, legacy)

    return LATEST_DIR


def print_local_instructions(run_dir: str, run_id: str) -> None:
    """在終端機印出本機查看路徑"""
    summary_md = os.path.join(run_dir, 'SUMMARY.md')
    summary_html = os.path.join(run_dir, 'SUMMARY.html')
    print('\n' + '=' * 60)
    print('  ✅ 實驗完成 — 本機紀錄已儲存')
    print('=' * 60)
    print(f'\n  Run ID:     {run_id}')
    print(f'  資料夾:     {run_dir}')
    print(f'\n  📄 文字+圖片總覽 (Markdown):')
    print(f'     {summary_md}')
    print(f'\n  🌐 圖文報告 (雙擊開啟，無需登入網站):')
    print(f'     {summary_html}')
    print('\n  各語言對報告:')
    for exp_id, exp in EXPERIMENTS.items():
        pair_html = os.path.join(run_dir, exp_id, 'report.html')
        if os.path.exists(pair_html):
            print(f'     [{exp["label"]}] {pair_html}')
    print('\n  💡 在 PowerShell 開啟總覽:')
    print(f'     Start-Process "{summary_html}"')
    print('\n  💡 從 Oracle VM 拉回結果到本機:')
    print('     powershell -File research/fetch_results.ps1')
    print('=' * 60)
