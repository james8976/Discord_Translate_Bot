# -*- coding: utf-8 -*-
"""
PongPong Bot — 旅遊資訊 Cog
/travel 指令整合天氣、時間、匯率、常用語
"""

import html as html_mod
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import pytz

import config
from utils.logger import get_logger

logger = get_logger('travel')

# ── 城市資料庫 ─────────────────────────────────────────────
# (timezone, country_code, currency, language_code)
CITY_DATABASE: dict[str, tuple[str, str, str, str]] = {
    'tokyo':      ('Asia/Tokyo',          'JP', 'JPY', 'ja'),
    'osaka':      ('Asia/Tokyo',          'JP', 'JPY', 'ja'),
    'kyoto':      ('Asia/Tokyo',          'JP', 'JPY', 'ja'),
    'seoul':      ('Asia/Seoul',          'KR', 'KRW', 'ko'),
    'busan':      ('Asia/Seoul',          'KR', 'KRW', 'ko'),
    'taipei':     ('Asia/Taipei',         'TW', 'TWD', 'zh-TW'),
    'kaohsiung':  ('Asia/Taipei',         'TW', 'TWD', 'zh-TW'),
    'beijing':    ('Asia/Shanghai',       'CN', 'CNY', 'zh-CN'),
    'shanghai':   ('Asia/Shanghai',       'CN', 'CNY', 'zh-CN'),
    'hong kong':  ('Asia/Hong_Kong',      'HK', 'HKD', 'zh-TW'),
    'singapore':  ('Asia/Singapore',      'SG', 'SGD', 'en'),
    'bangkok':    ('Asia/Bangkok',        'TH', 'THB', 'th'),
    'new york':   ('America/New_York',    'US', 'USD', 'en'),
    'los angeles':('America/Los_Angeles', 'US', 'USD', 'en'),
    'london':     ('Europe/London',       'GB', 'GBP', 'en'),
    'paris':      ('Europe/Paris',        'FR', 'EUR', 'fr'),
    'berlin':     ('Europe/Berlin',       'DE', 'EUR', 'de'),
    'rome':       ('Europe/Rome',         'IT', 'EUR', 'it'),
    'madrid':     ('Europe/Madrid',       'ES', 'EUR', 'es'),
    'sydney':     ('Australia/Sydney',    'AU', 'AUD', 'en'),
    'melbourne':  ('Australia/Melbourne', 'AU', 'AUD', 'en'),
    'dubai':      ('Asia/Dubai',          'AE', 'AED', 'ar'),
    'mumbai':     ('Asia/Kolkata',        'IN', 'INR', 'hi'),
    'hanoi':      ('Asia/Ho_Chi_Minh',    'VN', 'VND', 'vi'),
    'ho chi minh':('Asia/Ho_Chi_Minh',    'VN', 'VND', 'vi'),
    'manila':     ('Asia/Manila',         'PH', 'PHP', 'en'),
    'kuala lumpur':('Asia/Kuala_Lumpur',  'MY', 'MYR', 'ms'),
    'jakarta':    ('Asia/Jakarta',        'ID', 'IDR', 'id'),
}

# 旅遊常用語
TRAVEL_PHRASES = [
    ('你好', 'Hello'),
    ('謝謝', 'Thank you'),
    ('多少錢？', 'How much?'),
]


class TravelCog(commands.Cog, name='旅遊'):
    """旅遊資訊查詢"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _get_weather_brief(self, city: str) -> str:
        """取得簡短天氣描述"""
        api_key = config.OPENWEATHER_API_KEY
        if not api_key:
            return '⚠️ 天氣服務未設定'

        url = 'https://api.openweathermap.org/data/2.5/weather'
        params = {'q': city, 'appid': api_key, 'units': 'metric', 'lang': 'en'}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return '❌ 無法取得天氣資料'
                    data = await resp.json()
            temp = data['main']['temp']
            desc = data['weather'][0].get('description', '')
            icon_code = data['weather'][0].get('icon', '01d')
            from cogs.weather import WEATHER_ICONS, WEATHER_DESC_ZH
            icon = WEATHER_ICONS.get(icon_code, '🌍')
            desc_zh = WEATHER_DESC_ZH.get(desc, desc)
            return f'{icon} {temp:.1f}°C — {desc_zh}'
        except Exception as e:
            logger.warning(f'天氣查詢失敗 ({city}): {e}')
            return '❌ 天氣查詢失敗'

    async def _get_exchange_rate(self, currency: str) -> str:
        """取得該貨幣兌換台幣的匯率"""
        api_key = config.CURRENCY_API_KEY
        if not api_key or currency == 'TWD':
            return '—'
        url = f'https://v6.exchangerate-api.com/v6/{api_key}/pair/{currency}/TWD/1'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    data = await resp.json()
            if data.get('result') == 'success':
                rate = data['conversion_result']
                return f'1 {currency} = {rate:,.2f} TWD'
            return '❌ 查詢失敗'
        except Exception:
            return '❌ 查詢失敗'

    async def _translate_phrases(self, target_lang: str) -> list[tuple[str, str]]:
        """翻譯旅遊常用語到目標語言"""
        client = getattr(self.bot, 'translate_client', None)
        if not client or target_lang in ('zh-TW', 'zh-CN'):
            # 中文就不用翻了，直接回傳原始
            return [(zh, en) for zh, en in TRAVEL_PHRASES]

        results = []
        for zh, en in TRAVEL_PHRASES:
            try:
                result = client.translate(zh, target_language=target_lang)
                translated = html_mod.unescape(result['translatedText'])
                results.append((zh, translated))
            except Exception:
                results.append((zh, en))
        return results

    @app_commands.command(name='travel', description='查詢目的地旅遊資訊（天氣、時間、匯率、常用語）')
    @app_commands.describe(city='城市名稱（英文）')
    async def slash_travel(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()

        city_key = city.lower().strip()
        city_info = CITY_DATABASE.get(city_key)

        if not city_info:
            # 嘗試模糊比對
            for key in CITY_DATABASE:
                if city_key in key or key in city_key:
                    city_info = CITY_DATABASE[key]
                    city_key = key
                    break

        if not city_info:
            embed = discord.Embed(
                description=f'❌ 找不到城市「{city}」的旅遊資料。\n\n'
                            f'**支援的城市：**\n'
                            + ', '.join(f'`{k.title()}`' for k in sorted(CITY_DATABASE.keys())),
                color=config.COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)
            return

        tz_name, country_code, currency, lang_code = city_info

        # 並行取得資料
        import asyncio
        weather_task = asyncio.create_task(self._get_weather_brief(city_key.title()))
        rate_task = asyncio.create_task(self._get_exchange_rate(currency))
        phrase_task = asyncio.create_task(self._translate_phrases(lang_code))

        weather_str = await weather_task
        rate_str = await rate_task
        phrases = await phrase_task

        # 當地時間
        tz = pytz.timezone(tz_name)
        local_time = datetime.now(tz)
        time_str = local_time.strftime('%Y-%m-%d %H:%M:%S (%A)')

        # 組合 Embed
        flag = config.CURRENCY_FLAGS.get(currency, '🌍')
        embed = discord.Embed(
            title=f'✈️ {city_key.title()}, {country_code} {flag}',
            description='旅遊實用資訊一覽',
            color=config.COLOR_PRIMARY,
        )
        embed.add_field(name='🕐 當地時間', value=f'```{time_str}```', inline=False)
        embed.add_field(name='🌤️ 天氣', value=weather_str, inline=False)
        embed.add_field(name='💱 匯率（→ TWD）', value=f'`{rate_str}`', inline=False)

        # 常用語
        phrase_lines = []
        for zh, translated in phrases:
            phrase_lines.append(f'**{zh}** → {translated}')
        lang_flag = config.LANGUAGE_FLAGS.get(lang_code, '🌐')
        embed.add_field(
            name=f'🗣️ 常用語（{lang_flag} {lang_code}）',
            value='\n'.join(phrase_lines),
            inline=False,
        )

        embed.set_footer(text=f'PongPong {config.BOT_VERSION}  •  {datetime.now().strftime("%H:%M:%S")}')
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(TravelCog(bot))
