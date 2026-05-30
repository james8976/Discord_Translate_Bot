# -*- coding: utf-8 -*-
"""
PongPong Bot — 日誌模組
提供統一的 logging 設定，同時輸出到 console 和檔案
"""

import os
import logging
from logging.handlers import RotatingFileHandler

# 日誌目錄
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOG_DIR, 'pongpong.log')
LOG_FORMAT = '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# 是否已初始化根 logger
_initialized = False


def _setup_root_logger() -> None:
    """初始化根 logger（只執行一次）"""
    global _initialized
    if _initialized:
        return

    root = logging.getLogger('pongpong')
    root.setLevel(logging.DEBUG)

    # ── Console Handler ────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    )

    # ── File Handler（自動輪替，最多 5 MB × 3 份）─────
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    )

    root.addHandler(console_handler)
    root.addHandler(file_handler)
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    取得子 logger。
    用法: logger = get_logger(__name__)
    """
    _setup_root_logger()
    return logging.getLogger(f'pongpong.{name}')
