# -*- coding: utf-8 -*-
"""
PongPong Bot — 全域設定檔
載入環境變數、初始化 Google Cloud 憑證、定義常數
"""

import os
import json
from dotenv import load_dotenv

# ── 載入 .env ──────────────────────────────────────────────
load_dotenv()

# ── Discord ────────────────────────────────────────────────
DISCORD_TOKEN: str = os.getenv('DISCORD_TOKEN', '')
BOT_PREFIX: str = '!'
BOT_VERSION: str = 'v2.0'

# ── API Keys ───────────────────────────────────────────────
CURRENCY_API_KEY: str = os.getenv('CURRENCY_API_key', '')
OPENWEATHER_API_KEY: str = os.getenv('OPENWEATHER_API_KEY', '')
GOOGLE_APPLICATION_CREDENTIALS_JSON: str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON', '')

# ── 快取 ───────────────────────────────────────────────────
CACHE_EXPIRY_SECONDS: int = 300  # 5 分鐘

# ── 預設語言 ───────────────────────────────────────────────
DEFAULT_LANGUAGE: str = 'zh-TW'

# ── Embed 顏色 ─────────────────────────────────────────────
COLOR_PRIMARY   = 0x5865F2   # Discord Blurple
COLOR_SUCCESS   = 0x57F287   # 綠色
COLOR_ERROR     = 0xED4245   # 紅色
COLOR_WARNING   = 0xFEE75C   # 黃色
COLOR_CURRENCY  = 0x57F287   # 綠色（匯率）
COLOR_STOCK_UP  = 0x57F287   # 股票漲（美股）
COLOR_STOCK_DOWN = 0xED4245  # 股票跌
COLOR_TW_UP     = 0xED4245   # 台股漲 → 紅色（台灣慣例）
COLOR_TW_DOWN   = 0x57F287   # 台股跌 → 綠色

# ── 語言別名 ───────────────────────────────────────────────
LANGUAGE_ALIASES: dict[str, str] = {
    'zh(tw)': 'zh-TW', 'tw': 'zh-TW', 'zh-tw': 'zh-TW',
    'cn': 'zh-CN', 'zh-cn': 'zh-CN', 'zh': 'zh-CN',
    'jp': 'ja', 'ja': 'ja', 'en': 'en',
    'ko': 'ko', 'kr': 'ko', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'vi': 'vi', 'it': 'it', 'ru': 'ru',
    'pt': 'pt', 'ar': 'ar', 'hi': 'hi', 'id': 'id',
    'nl': 'nl', 'sv': 'sv', 'tr': 'tr', 'pl': 'pl',
}

# ── 貨幣代碼 ───────────────────────────────────────────────
CURRENCY_CODES: set[str] = {
    'usd', 'eur', 'jpy', 'twd', 'cny', 'krw', 'gbp', 'aud',
    'cad', 'chf', 'hkd', 'sgd', 'inr', 'rub', 'thb', 'vnd',
    'myr', 'php', 'idr', 'nzd', 'sek', 'nok', 'dkk', 'mxn',
}

# ── 表情符號 → 語言 ────────────────────────────────────────
EMOJI_TO_LANGUAGE: dict[str, str] = {
    '🇹🇼': 'zh-TW', '🇯🇵': 'ja', '🇺🇸': 'en',
    '🇰🇷': 'ko', '🇨🇳': 'zh-CN', '🇪🇸': 'es', '🇫🇷': 'fr',
    '🇩🇪': 'de', '🇻🇳': 'vi', '🇮🇹': 'it', '🇷🇺': 'ru',
    '🇵🇹': 'pt', '🇹🇭': 'th', '🇮🇩': 'id',
}

# ── 語言旗幟（用於 Embed 顯示）─────────────────────────────
LANGUAGE_FLAGS: dict[str, str] = {
    'zh-TW': '🇹🇼', 'zh-CN': '🇨🇳', 'ja': '🇯🇵', 'en': '🇺🇸',
    'ko': '🇰🇷', 'es': '🇪🇸', 'fr': '🇫🇷', 'de': '🇩🇪',
    'vi': '🇻🇳', 'it': '🇮🇹', 'ru': '🇷🇺', 'pt': '🇵🇹',
    'ar': '🇸🇦', 'hi': '🇮🇳', 'id': '🇮🇩', 'nl': '🇳🇱',
    'sv': '🇸🇪', 'tr': '🇹🇷', 'pl': '🇵🇱', 'th': '🇹🇭',
}

# ── 貨幣旗幟（用於 Embed 顯示）─────────────────────────────
CURRENCY_FLAGS: dict[str, str] = {
    'USD': '🇺🇸', 'EUR': '🇪🇺', 'JPY': '🇯🇵', 'TWD': '🇹🇼',
    'CNY': '🇨🇳', 'KRW': '🇰🇷', 'GBP': '🇬🇧', 'AUD': '🇦🇺',
    'CAD': '🇨🇦', 'CHF': '🇨🇭', 'HKD': '🇭🇰', 'SGD': '🇸🇬',
    'INR': '🇮🇳', 'RUB': '🇷🇺', 'THB': '🇹🇭', 'VND': '🇻🇳',
    'MYR': '🇲🇾', 'PHP': '🇵🇭', 'IDR': '🇮🇩', 'NZD': '🇳🇿',
    'SEK': '🇸🇪', 'NOK': '🇳🇴', 'DKK': '🇩🇰', 'MXN': '🇲🇽',
}


# ── Google Cloud Translation 初始化 ───────────────────────
def setup_google_credentials():
    """
    從環境變數或本地檔案建立 Google Cloud 憑證，
    回傳 translate.Client 實例 (或 None)。
    """
    from google.cloud import translate_v2 as translate

    creds_json = GOOGLE_APPLICATION_CREDENTIALS_JSON
    if creds_json:
        try:
            cred_dict = json.loads(creds_json)
            cred_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
            with open(cred_path, 'w', encoding='utf-8') as f:
                json.dump(cred_dict, f)
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = cred_path
            client = translate.Client()
            return client
        except Exception as e:
            print(f'❌ Google 憑證初始化失敗: {e}')
            return None
    else:
        cred_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
        if os.path.exists(cred_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = cred_path
            try:
                client = translate.Client()
                return client
            except Exception as e:
                print(f'❌ 本地憑證認證失敗: {e}')
                return None
        else:
            print('⚠️ 找不到 Google 憑證，翻譯功能將無法使用。')
            return None


def normalize_lang_code(code: str) -> str | None:
    """將使用者輸入的語言代碼正規化為 Google API 格式"""
    if not code:
        return None
    return LANGUAGE_ALIASES.get(code.lower().strip(), None)
