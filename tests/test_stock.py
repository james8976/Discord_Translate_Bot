# -*- coding: utf-8 -*-
"""
tests/test_stock.py
股票與加密貨幣功能單元測試 | Stock & crypto feature unit tests

測試範圍:
- 股票代碼類型偵測（台股/美股/加密貨幣）
- CRYPTO_SYMBOLS 映射
- 無效輸入處理
"""

import sys
import os
import re
import pytest

# 將 bot 根目錄加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ===== 股票代碼格式常數 =====

# 已知的加密貨幣代號（模擬 stock cog 中的 CRYPTO_SYMBOLS）
CRYPTO_SYMBOLS = {
    'BTC': 'bitcoin',
    'ETH': 'ethereum',
    'BNB': 'binancecoin',
    'SOL': 'solana',
    'XRP': 'ripple',
    'ADA': 'cardano',
    'DOGE': 'dogecoin',
    'DOT': 'polkadot',
    'AVAX': 'avalanche-2',
    'MATIC': 'matic-network',
    'LINK': 'chainlink',
    'UNI': 'uniswap',
    'ATOM': 'cosmos',
    'LTC': 'litecoin',
    'SHIB': 'shiba-inu',
}

# 台灣股票代碼格式：4 位數字
TW_STOCK_PATTERN = re.compile(r'^\d{4,6}$')

# 美股代碼格式：1-5 個英文字母（排除加密貨幣代號後）
US_STOCK_PATTERN = re.compile(r'^[A-Za-z]{1,5}$')


def detect_stock_type(code: str) -> str:
    """
    偵測股票代碼類型

    Returns:
        'crypto' - 加密貨幣
        'tw_stock' - 台灣股票（需要加 .TW 後綴）
        'us_stock' - 美國股票
        'invalid' - 無效輸入
    """
    if not code or not isinstance(code, str):
        return 'invalid'

    code_clean = code.strip()
    if not code_clean:
        return 'invalid'

    # 先檢查是否為加密貨幣（不分大小寫）
    if code_clean.upper() in CRYPTO_SYMBOLS:
        return 'crypto'

    # 檢查是否為台灣股票（純數字，4-6 位）
    if TW_STOCK_PATTERN.match(code_clean):
        return 'tw_stock'

    # 檢查是否為美股代碼（1-5 個英文字母）
    if US_STOCK_PATTERN.match(code_clean):
        return 'us_stock'

    return 'invalid'


def format_stock_code(code: str) -> str | None:
    """
    格式化股票代碼，台股自動加 .TW 後綴

    Returns:
        格式化後的代碼，無效則回傳 None
    """
    stock_type = detect_stock_type(code)

    if stock_type == 'invalid':
        return None
    elif stock_type == 'tw_stock':
        return f"{code.strip()}.TW"
    elif stock_type == 'crypto':
        return code.strip().upper()
    else:  # us_stock
        return code.strip().upper()


# ===== 股票代碼類型偵測測試 =====

class TestStockCodeTypeDetection:
    """測試股票代碼類型偵測"""

    # --- 台灣股票 ---

    def test_taiwan_stock_2330(self):
        """2330（台積電）應偵測為台灣股票"""
        assert detect_stock_type('2330') == 'tw_stock'

    def test_taiwan_etf_0050(self):
        """0050（元大台灣50 ETF）應偵測為台灣股票"""
        assert detect_stock_type('0050') == 'tw_stock'

    def test_taiwan_stock_2317(self):
        """2317（鴻海）應偵測為台灣股票"""
        assert detect_stock_type('2317') == 'tw_stock'

    def test_taiwan_stock_six_digits(self):
        """6 位數代碼也應為台灣股票（上櫃等）"""
        assert detect_stock_type('006208') == 'tw_stock'

    # --- 美國股票 ---

    def test_us_stock_aapl(self):
        """AAPL（Apple）應偵測為美國股票"""
        assert detect_stock_type('AAPL') == 'us_stock'

    def test_us_stock_tsla(self):
        """TSLA（Tesla）應偵測為美國股票"""
        assert detect_stock_type('TSLA') == 'us_stock'

    def test_us_stock_msft(self):
        """MSFT（Microsoft）應偵測為美國股票"""
        assert detect_stock_type('MSFT') == 'us_stock'

    def test_us_stock_lowercase(self):
        """小寫美股代碼也應正確偵測（不是加密貨幣的情況）"""
        assert detect_stock_type('aapl') == 'us_stock'
        assert detect_stock_type('tsla') == 'us_stock'

    def test_us_stock_single_char(self):
        """單字母代碼（如 Meta 的前身 F）應為美股"""
        assert detect_stock_type('F') == 'us_stock'

    # --- 加密貨幣 ---

    def test_crypto_btc(self):
        """BTC 應偵測為加密貨幣"""
        assert detect_stock_type('BTC') == 'crypto'

    def test_crypto_eth(self):
        """ETH 應偵測為加密貨幣"""
        assert detect_stock_type('ETH') == 'crypto'

    def test_crypto_btc_lowercase(self):
        """btc（小寫）也應偵測為加密貨幣"""
        assert detect_stock_type('btc') == 'crypto'

    def test_crypto_doge(self):
        """DOGE 應偵測為加密貨幣"""
        assert detect_stock_type('DOGE') == 'crypto'

    def test_crypto_sol(self):
        """SOL 應偵測為加密貨幣"""
        assert detect_stock_type('SOL') == 'crypto'

    def test_crypto_mixed_case(self):
        """混合大小寫也應正確偵測"""
        assert detect_stock_type('Btc') == 'crypto'
        assert detect_stock_type('eTH') == 'crypto'

    # --- 無效輸入 ---

    def test_invalid_empty_string(self):
        """空字串應為無效"""
        assert detect_stock_type('') == 'invalid'

    def test_invalid_none(self):
        """None 應為無效"""
        assert detect_stock_type(None) == 'invalid'

    def test_invalid_special_chars(self):
        """特殊字元應為無效"""
        assert detect_stock_type('!@#$') == 'invalid'
        assert detect_stock_type('2330.TW') == 'invalid'  # 已含後綴

    def test_invalid_mixed_alphanumeric(self):
        """混合英數字元應為無效（不是純數字也不是純英文）"""
        assert detect_stock_type('A123') == 'invalid'
        assert detect_stock_type('12AB') == 'invalid'

    def test_invalid_too_long(self):
        """超過 6 位的純數字應為無效"""
        assert detect_stock_type('1234567') == 'invalid'

    def test_invalid_too_long_alpha(self):
        """超過 5 個字母的非加密貨幣代碼應為無效"""
        assert detect_stock_type('ABCDEF') == 'invalid'

    def test_invalid_whitespace_only(self):
        """純空白應為無效"""
        assert detect_stock_type('   ') == 'invalid'


# ===== 股票代碼格式化測試 =====

class TestFormatStockCode:
    """測試股票代碼格式化"""

    def test_taiwan_stock_appends_tw(self):
        """台灣股票應自動加上 .TW 後綴"""
        assert format_stock_code('2330') == '2330.TW'
        assert format_stock_code('0050') == '0050.TW'

    def test_us_stock_uppercased(self):
        """美股代碼應轉大寫"""
        assert format_stock_code('aapl') == 'AAPL'
        assert format_stock_code('TSLA') == 'TSLA'

    def test_crypto_uppercased(self):
        """加密貨幣代碼應轉大寫"""
        assert format_stock_code('btc') == 'BTC'
        assert format_stock_code('eth') == 'ETH'

    def test_invalid_returns_none(self):
        """無效輸入應回傳 None"""
        assert format_stock_code('') is None
        assert format_stock_code(None) is None
        assert format_stock_code('!@#') is None


# ===== CRYPTO_SYMBOLS 映射測試 =====

class TestCryptoSymbols:
    """測試加密貨幣代碼映射"""

    def test_mapping_not_empty(self):
        """映射不應為空"""
        assert len(CRYPTO_SYMBOLS) > 0

    def test_btc_maps_to_bitcoin(self):
        """BTC 應對應到 bitcoin"""
        assert CRYPTO_SYMBOLS['BTC'] == 'bitcoin'

    def test_eth_maps_to_ethereum(self):
        """ETH 應對應到 ethereum"""
        assert CRYPTO_SYMBOLS['ETH'] == 'ethereum'

    def test_all_keys_are_uppercase(self):
        """所有 key 都應為大寫"""
        for key in CRYPTO_SYMBOLS:
            assert key == key.upper(), f"Key '{key}' is not uppercase"

    def test_all_values_are_lowercase(self):
        """所有 CoinGecko ID 都應為小寫（含連字號）"""
        for key, value in CRYPTO_SYMBOLS.items():
            assert value == value.lower(), \
                f"Value for '{key}' is not lowercase: '{value}'"

    def test_all_values_are_non_empty(self):
        """所有值都不應為空"""
        for key, value in CRYPTO_SYMBOLS.items():
            assert len(value) > 0, f"Empty value for key '{key}'"

    def test_no_duplicate_values(self):
        """CoinGecko ID 不應重複"""
        values = list(CRYPTO_SYMBOLS.values())
        assert len(values) == len(set(values)), \
            "Duplicate CoinGecko IDs found in CRYPTO_SYMBOLS"

    def test_common_cryptos_present(self):
        """常見的加密貨幣都應存在"""
        expected = ['BTC', 'ETH', 'SOL', 'XRP', 'DOGE', 'ADA']
        for symbol in expected:
            assert symbol in CRYPTO_SYMBOLS, \
                f"Missing common crypto symbol: {symbol}"

    def test_minimum_crypto_count(self):
        """應至少支援 10 種加密貨幣"""
        assert len(CRYPTO_SYMBOLS) >= 10, \
            f"Only {len(CRYPTO_SYMBOLS)} cryptos, expected >= 10"
