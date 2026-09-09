# -*- coding: utf-8 -*-
"""
跨語言對齊實驗設定 — 四組語言對 + 資料來源 URL
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
RESULTS_DIR = os.path.join(BASE_DIR, 'results')
RUNS_DIR = os.path.join(RESULTS_DIR, 'runs')
LATEST_DIR = os.path.join(RESULTS_DIR, 'latest')

FASTTEXT_URL_TEMPLATE = 'https://dl.fbaipublicfiles.com/fasttext/vectors-wiki/wiki.{}.vec'

MUSE_DICT_GITHUB = (
    'https://raw.githubusercontent.com/facebookresearch/MUSE/main'
    '/data/crosslingual/dictionaries/{}-{}.txt'
)
MUSE_DICT_FALLBACK = 'https://dl.fbaipublicfiles.com/arrival/dictionaries/{}-{}.0-5000.txt'

# 四組實驗：中英、中日、英日、中→日（中英日三語研究中的中文→日文）
EXPERIMENTS = {
    'zh-en': {
        'id': 'zh-en',
        'label': '中英',
        'title': '中文 → 英文',
        'src': 'zh',
        'tgt': 'en',
        'dict_file': 'zh-en.txt',
        'slang_file': None,
        'src_col': '中文',
        'tgt_col': '英文',
    },
    'ja-zh': {
        'id': 'ja-zh',
        'label': '中日',
        'title': '日文 → 中文',
        'src': 'ja',
        'tgt': 'zh',
        'dict_file': 'ja-zh.txt',
        'slang_file': 'slang_pairs_ja_zh.tsv',
        'src_col': '日文',
        'tgt_col': '中文',
    },
    'en-ja': {
        'id': 'en-ja',
        'label': '英日',
        'title': '英文 → 日文',
        'src': 'en',
        'tgt': 'ja',
        'dict_file': 'en-ja.txt',
        'slang_file': None,
        'src_col': '英文',
        'tgt_col': '日文',
    },
    'zh-ja': {
        'id': 'zh-ja',
        'label': '中英日',
        'title': '中文 → 日文（三語研究）',
        'src': 'zh',
        'tgt': 'ja',
        'dict_file': 'zh-ja.txt',
        'slang_file': None,
        'src_col': '中文',
        'tgt_col': '日文',
    },
}

ALL_LANGS = sorted({exp['src'] for exp in EXPERIMENTS.values()} | {exp['tgt'] for exp in EXPERIMENTS.values()})

ALL_DICT_PAIRS = sorted({(exp['src'], exp['tgt']) for exp in EXPERIMENTS.values()})

CHART_FILES = [
    'precision_comparison.png',
    'confidence_distribution.png',
    'hubness_distribution.png',
    'special_results_table.png',
]
