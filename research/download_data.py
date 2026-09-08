import os
import urllib.request
import tarfile
import gzip
import shutil
from typing import List

# 常量定义，包含待下载的数据链接
FASTTEXT_URL_TEMPLATE = "https://dl.fbaipublicfiles.com/fasttext/vectors-wiki/wiki.{}.vec"
MUSE_DICT_URL_TEMPLATE = "https://dl.fbaipublicfiles.com/arrival/dictionaries/{}-{}.txt"

def download_file(url: str, dest_path: str) -> None:
    """
    从指定 URL 下载文件到本地路径，包含简单的进度提示。
    
    Args:
        url (str): 下载链接。
        dest_path (str): 本地保存路径。
    """
    if os.path.exists(dest_path):
        print(f"[{dest_path}] 已经存在，跳过下载。")
        return
        
    print(f"正在下载: {url}")
    print(f"保存至: {dest_path}")
    try:
        # 使用 urllib 进行下载
        urllib.request.urlretrieve(url, dest_path)
        print("下载完成！")
    except Exception as e:
        print(f"下载失败: {e}")

def fetch_fasttext_vectors(langs: List[str], save_dir: str) -> None:
    """
    批量下载指定语言的 FastText 词向量文件。
    
    Args:
        langs (List[str]): 语言代码列表，如 ['en', 'zh']。
        save_dir (str): 保存目录。
    """
    os.makedirs(save_dir, exist_ok=True)
    for lang in langs:
        url = FASTTEXT_URL_TEMPLATE.format(lang)
        dest_path = os.path.join(save_dir, f"wiki.{lang}.vec")
        download_file(url, dest_path)

def fetch_muse_dictionaries(lang_pairs: List[tuple], save_dir: str) -> None:
    """
    批量下载 MUSE 跨语言词典（双语平行词表）。
    
    Args:
        lang_pairs (List[tuple]): 语言对元组列表，如 [('en', 'zh'), ('zh', 'en')]。
        save_dir (str): 保存目录。
    """
    os.makedirs(save_dir, exist_ok=True)
    for src, tgt in lang_pairs:
        url = MUSE_DICT_URL_TEMPLATE.format(src, tgt)
        dest_path = os.path.join(save_dir, f"{src}-{tgt}.txt")
        download_file(url, dest_path)

if __name__ == "__main__":
    """主程序：执行示例下载流程。"""
    # 设定默认保存目录为 data/research/
    base_dir = os.path.join(os.path.dirname(__file__), "..", "data", "research")
    os.makedirs(base_dir, exist_ok=True)
    
    print("开始获取跨语言研究数据...")
    
    # 示例：下载英文和中文的单语词向量
    target_langs = ['en', 'zh']
    fetch_fasttext_vectors(target_langs, base_dir)
    
    # 示例：下载英中和中英的双语词典
    pairs = [('en', 'zh'), ('zh', 'en')]
    fetch_muse_dictionaries(pairs, base_dir)
    
    print("所有数据下载任务处理完毕！")
