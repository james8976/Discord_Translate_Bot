# -*- coding: utf-8 -*-
"""
下載四組實驗所需的 FastText 嵌入與 MUSE 詞典
"""

import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from research.config import ALL_DICT_PAIRS, ALL_LANGS, DATA_DIR, FASTTEXT_URL_TEMPLATE, MUSE_DICT_FALLBACK, MUSE_DICT_GITHUB


def download_file(url: str, dest_path: str) -> bool:
    if os.path.exists(dest_path):
        size_mb = os.path.getsize(dest_path) / 1024 / 1024
        print(f'[跳過] {os.path.basename(dest_path)} ({size_mb:.1f} MB)')
        return True
    print(f'下載: {url}')
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (PongPong Research)')]
    urllib.request.install_opener(opener)
    try:
        urllib.request.urlretrieve(url, dest_path)
        print(f'  完成 → {dest_path}')
        return True
    except Exception as e:
        print(f'  失敗: {e}')
        return False


def fetch_fasttext_vectors(langs, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    for lang in langs:
        url = FASTTEXT_URL_TEMPLATE.format(lang)
        dest = os.path.join(save_dir, f'wiki.{lang}.vec')
        download_file(url, dest)


def fetch_muse_dictionaries(pairs, save_dir):
    os.makedirs(save_dir, exist_ok=True)
    for src, tgt in pairs:
        dest = os.path.join(save_dir, f'{src}-{tgt}.txt')
        if os.path.exists(dest):
            print(f'[跳過] {src}-{tgt}.txt')
            continue
        url = MUSE_DICT_GITHUB.format(src, tgt)
        if not download_file(url, dest):
            fallback = MUSE_DICT_FALLBACK.format(src, tgt)
            download_file(fallback, dest)


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    print('下載四組實驗資料 (en, zh, ja)...')
    print(f'目標目錄: {DATA_DIR}')
    fetch_fasttext_vectors(ALL_LANGS, DATA_DIR)
    fetch_muse_dictionaries(ALL_DICT_PAIRS, DATA_DIR)
    print('全部完成！')
