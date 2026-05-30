# -*- coding: utf-8 -*-
"""
tests/test_translate.py
翻譯功能單元測試 | Translation feature unit tests

測試範圍:
- normalize_lang_code 函式的正確性
- 語言別名映射
- 表情符號對應的語言代碼有效性
"""

import sys
import os
import pytest

# 將 bot 根目錄加入 sys.path，以便 import bot.py 中的函式
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from bot import normalize_lang_code, LANGUAGE_ALIASES, EMOJI_TO_LANGUAGE


# ===== normalize_lang_code 測試 =====

class TestNormalizeLangCode:
    """測試語言代碼正規化函式"""

    def test_valid_chinese_traditional(self):
        """繁體中文 - 多種寫法都應正確對應"""
        assert normalize_lang_code('tw') == 'zh-TW'
        assert normalize_lang_code('zh(tw)') == 'zh-TW'
        assert normalize_lang_code('zh-tw') == 'zh-TW'

    def test_valid_chinese_simplified(self):
        """簡體中文 - 多種寫法都應正確對應"""
        assert normalize_lang_code('cn') == 'zh-CN'
        assert normalize_lang_code('zh-cn') == 'zh-CN'
        assert normalize_lang_code('zh') == 'zh-CN'

    def test_valid_japanese(self):
        """日文 - jp 和 ja 都應對應到 ja"""
        assert normalize_lang_code('jp') == 'ja'
        assert normalize_lang_code('ja') == 'ja'

    def test_valid_korean(self):
        """韓文 - ko 和 kr 都應對應到 ko"""
        assert normalize_lang_code('ko') == 'ko'
        assert normalize_lang_code('kr') == 'ko'

    def test_valid_english(self):
        """英文"""
        assert normalize_lang_code('en') == 'en'

    def test_valid_european_languages(self):
        """歐洲語言"""
        assert normalize_lang_code('es') == 'es'
        assert normalize_lang_code('fr') == 'fr'
        assert normalize_lang_code('de') == 'de'
        assert normalize_lang_code('it') == 'it'
        assert normalize_lang_code('ru') == 'ru'
        assert normalize_lang_code('pt') == 'pt'
        assert normalize_lang_code('nl') == 'nl'
        assert normalize_lang_code('sv') == 'sv'
        assert normalize_lang_code('tr') == 'tr'
        assert normalize_lang_code('pl') == 'pl'

    def test_valid_asian_languages(self):
        """亞洲語言"""
        assert normalize_lang_code('vi') == 'vi'
        assert normalize_lang_code('hi') == 'hi'
        assert normalize_lang_code('id') == 'id'
        assert normalize_lang_code('ar') == 'ar'

    def test_case_insensitive(self):
        """應不分大小寫"""
        assert normalize_lang_code('TW') == 'zh-TW'
        assert normalize_lang_code('JP') == 'ja'
        assert normalize_lang_code('EN') == 'en'
        assert normalize_lang_code('Zh-TW') == 'zh-TW'

    def test_invalid_code_returns_none(self):
        """無效的語言代碼應回傳 None"""
        assert normalize_lang_code('xyz') is None
        assert normalize_lang_code('abc') is None
        assert normalize_lang_code('123') is None
        assert normalize_lang_code('zzzz') is None

    def test_empty_string_returns_none(self):
        """空字串應回傳 None"""
        assert normalize_lang_code('') is None

    def test_none_input_returns_none(self):
        """None 輸入應回傳 None"""
        assert normalize_lang_code(None) is None


# ===== 語言別名映射測試 =====

class TestLanguageAliases:
    """測試 LANGUAGE_ALIASES 映射的完整性"""

    def test_aliases_not_empty(self):
        """別名映射不應為空"""
        assert len(LANGUAGE_ALIASES) > 0

    def test_all_values_are_strings(self):
        """所有映射值都應為字串"""
        for key, value in LANGUAGE_ALIASES.items():
            assert isinstance(value, str), f"Key '{key}' has non-string value: {value}"

    def test_all_keys_are_lowercase(self):
        """所有 key 都應為小寫（因為 normalize 會做 .lower()）"""
        for key in LANGUAGE_ALIASES:
            assert key == key.lower(), f"Key '{key}' is not lowercase"

    def test_zh_tw_has_multiple_aliases(self):
        """繁體中文至少要有 3 種寫法"""
        tw_aliases = [k for k, v in LANGUAGE_ALIASES.items() if v == 'zh-TW']
        assert len(tw_aliases) >= 3, f"zh-TW only has {len(tw_aliases)} aliases: {tw_aliases}"

    def test_zh_cn_has_multiple_aliases(self):
        """簡體中文至少要有 2 種寫法"""
        cn_aliases = [k for k, v in LANGUAGE_ALIASES.items() if v == 'zh-CN']
        assert len(cn_aliases) >= 2, f"zh-CN only has {len(cn_aliases)} aliases: {cn_aliases}"


# ===== 表情符號對應測試 =====

class TestEmojiToLanguage:
    """測試表情符號到語言的映射"""

    # Google Cloud Translation API 支援的語言代碼
    VALID_LANGUAGE_CODES = {
        'zh-TW', 'zh-CN', 'ja', 'en', 'ko', 'es', 'fr', 'de',
        'it', 'ru', 'pt', 'ar', 'hi', 'id', 'vi', 'nl', 'sv',
        'tr', 'pl', 'th', 'uk', 'cs', 'da', 'fi', 'el', 'he',
        'hu', 'no', 'ro', 'sk', 'bg', 'ca', 'hr', 'lt', 'lv',
        'ms', 'sl', 'sr', 'sw', 'ta', 'te', 'ur', 'bn', 'gu',
        'kn', 'ml', 'mr', 'pa', 'af', 'am', 'az', 'be', 'bs',
        'cy', 'et', 'eu', 'fa', 'fy', 'ga', 'gl', 'ha', 'haw',
        'hmn', 'ht', 'hy', 'ig', 'is', 'jw', 'ka', 'kk', 'km',
        'ku', 'ky', 'la', 'lb', 'lo', 'mg', 'mi', 'mk', 'mn',
        'mt', 'my', 'ne', 'ny', 'or', 'ps', 'rw', 'sd', 'si',
        'sm', 'sn', 'so', 'sq', 'st', 'su', 'tg', 'tl', 'tk',
        'tt', 'ug', 'uz', 'xh', 'yi', 'yo', 'zu',
    }

    def test_emoji_mapping_not_empty(self):
        """表情符號映射不應為空"""
        assert len(EMOJI_TO_LANGUAGE) > 0

    def test_all_values_are_valid_language_codes(self):
        """所有表情符號對應的語言代碼都應為有效的 Google Translate 代碼"""
        for emoji, lang_code in EMOJI_TO_LANGUAGE.items():
            assert lang_code in self.VALID_LANGUAGE_CODES, \
                f"Emoji {emoji} maps to invalid language code: '{lang_code}'"

    def test_taiwan_flag_maps_to_zh_tw(self):
        """🇹🇼 應對應到繁體中文"""
        assert EMOJI_TO_LANGUAGE.get("🇹🇼") == "zh-TW"

    def test_japan_flag_maps_to_ja(self):
        """🇯🇵 應對應到日文"""
        assert EMOJI_TO_LANGUAGE.get("🇯🇵") == "ja"

    def test_us_flag_maps_to_en(self):
        """🇺🇸 應對應到英文"""
        assert EMOJI_TO_LANGUAGE.get("🇺🇸") == "en"

    def test_korea_flag_maps_to_ko(self):
        """🇰🇷 應對應到韓文"""
        assert EMOJI_TO_LANGUAGE.get("🇰🇷") == "ko"

    def test_china_flag_maps_to_zh_cn(self):
        """🇨🇳 應對應到簡體中文"""
        assert EMOJI_TO_LANGUAGE.get("🇨🇳") == "zh-CN"

    def test_no_duplicate_language_codes(self):
        """不同的表情符號不應對應到相同的語言代碼"""
        values = list(EMOJI_TO_LANGUAGE.values())
        assert len(values) == len(set(values)), \
            "Duplicate language codes found in EMOJI_TO_LANGUAGE"
