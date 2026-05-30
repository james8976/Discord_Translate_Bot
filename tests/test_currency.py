# -*- coding: utf-8 -*-
"""
tests/test_currency.py
匯率功能單元測試 | Currency exchange feature unit tests

測試範圍:
- 幣別代碼驗證
- 金額解析（有效浮點數、無效輸入）
- 快取過期邏輯
"""

import sys
import os
import time
import pytest

# 將 bot 根目錄加入 sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot import CURRENCY_CODES


# ===== 幣別代碼驗證測試 =====

class TestCurrencyCodeValidation:
    """測試幣別代碼的有效性"""

    def test_currency_codes_not_empty(self):
        """幣別清單不應為空"""
        assert len(CURRENCY_CODES) > 0

    def test_common_currencies_exist(self):
        """常見幣別都應存在"""
        common = ['usd', 'eur', 'jpy', 'twd', 'cny', 'krw', 'gbp']
        for code in common:
            assert code in CURRENCY_CODES, f"Missing common currency: {code}"

    def test_all_codes_are_lowercase(self):
        """所有幣別代碼應為小寫"""
        for code in CURRENCY_CODES:
            assert code == code.lower(), f"Currency code '{code}' is not lowercase"

    def test_all_codes_are_three_chars(self):
        """所有幣別代碼應為 3 個字元（ISO 4217）"""
        for code in CURRENCY_CODES:
            assert len(code) == 3, f"Currency code '{code}' is not 3 characters"

    def test_all_codes_are_alpha(self):
        """所有幣別代碼應只包含英文字母"""
        for code in CURRENCY_CODES:
            assert code.isalpha(), f"Currency code '{code}' contains non-alpha characters"

    def test_invalid_code_not_in_set(self):
        """無效的幣別代碼不應在清單中"""
        assert 'xxx' not in CURRENCY_CODES
        assert 'abc' not in CURRENCY_CODES
        assert '123' not in CURRENCY_CODES
        assert '' not in CURRENCY_CODES

    def test_asian_currencies_exist(self):
        """亞洲常見幣別都應存在"""
        asian = ['jpy', 'twd', 'cny', 'krw', 'hkd', 'sgd']
        for code in asian:
            assert code in CURRENCY_CODES, f"Missing Asian currency: {code}"

    def test_minimum_currency_count(self):
        """應至少支援 10 種幣別"""
        assert len(CURRENCY_CODES) >= 10, \
            f"Only {len(CURRENCY_CODES)} currencies supported, expected >= 10"


# ===== 金額解析測試 =====

class TestAmountParsing:
    """測試金額字串轉浮點數的解析"""

    def test_valid_integer(self):
        """整數應能成功解析"""
        assert float("100") == 100.0
        assert float("1") == 1.0
        assert float("999999") == 999999.0

    def test_valid_float(self):
        """浮點數應能成功解析"""
        assert float("100.50") == 100.50
        assert float("0.01") == 0.01
        assert float("1234.5678") == 1234.5678

    def test_valid_negative(self):
        """負數應能成功解析（雖然匯率轉換不太會用到）"""
        assert float("-100") == -100.0
        assert float("-0.5") == -0.5

    def test_valid_zero(self):
        """零應能成功解析"""
        assert float("0") == 0.0
        assert float("0.0") == 0.0

    def test_valid_scientific_notation(self):
        """科學記號應能成功解析"""
        assert float("1e3") == 1000.0
        assert float("1.5e2") == 150.0

    def test_invalid_text_raises_error(self):
        """文字應拋出 ValueError"""
        with pytest.raises(ValueError):
            float("abc")

    def test_invalid_empty_raises_error(self):
        """空字串應拋出 ValueError"""
        with pytest.raises(ValueError):
            float("")

    def test_invalid_special_chars_raises_error(self):
        """特殊字元應拋出 ValueError"""
        with pytest.raises(ValueError):
            float("$100")
        with pytest.raises(ValueError):
            float("100,000")  # 逗號分隔的數字無法直接 float()

    def test_invalid_multiple_dots_raises_error(self):
        """多個小數點應拋出 ValueError"""
        with pytest.raises(ValueError):
            float("1.2.3")

    def test_whitespace_handling(self):
        """前後空白應能成功解析"""
        assert float(" 100 ") == 100.0
        assert float("\t50.5\n") == 50.5


# ===== 快取過期邏輯測試 =====

class TestCacheExpiry:
    """測試快取過期邏輯

    模擬一個簡單的 TTL 快取機制，
    這是 currency cog 中會用到的模式。
    """

    def setup_method(self):
        """每個測試前初始化一個簡單的快取"""
        self.cache = {}
        self.cache_ttl = 1  # 1 秒的 TTL（僅供測試用）

    def _get_cached(self, key):
        """從快取取值，過期則回傳 None"""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.cache_ttl:
                return value
            else:
                del self.cache[key]  # 過期，清除
        return None

    def _set_cached(self, key, value):
        """設定快取值"""
        self.cache[key] = (value, time.time())

    def test_cache_hit(self):
        """快取命中 - 設定後立即取值應成功"""
        self._set_cached('USD_TWD', 31.5)
        result = self._get_cached('USD_TWD')
        assert result == 31.5

    def test_cache_miss(self):
        """快取未命中 - 未設定的 key 應回傳 None"""
        result = self._get_cached('EUR_JPY')
        assert result is None

    def test_cache_expired(self):
        """快取過期 - 超過 TTL 應回傳 None"""
        self._set_cached('USD_TWD', 31.5)
        time.sleep(1.1)  # 等待超過 TTL
        result = self._get_cached('USD_TWD')
        assert result is None

    def test_cache_update(self):
        """快取更新 - 重新設定應覆蓋舊值"""
        self._set_cached('USD_TWD', 31.5)
        self._set_cached('USD_TWD', 32.0)
        result = self._get_cached('USD_TWD')
        assert result == 32.0

    def test_cache_multiple_keys(self):
        """多個快取 key 應互不影響"""
        self._set_cached('USD_TWD', 31.5)
        self._set_cached('EUR_TWD', 34.2)
        self._set_cached('JPY_TWD', 0.22)

        assert self._get_cached('USD_TWD') == 31.5
        assert self._get_cached('EUR_TWD') == 34.2
        assert self._get_cached('JPY_TWD') == 0.22

    def test_cache_cleanup_on_expiry(self):
        """過期時應清除快取 entry"""
        self._set_cached('USD_TWD', 31.5)
        time.sleep(1.1)
        self._get_cached('USD_TWD')  # 觸發清除
        assert 'USD_TWD' not in self.cache
