# -*- coding: utf-8 -*-
"""
PongPong Bot — 旅遊資訊 Cog
/travel 指令整合天氣、時間、匯率、常用語
支援中英文城市搜尋（透過 OpenWeatherMap Geocoding API）
"""

import html as html_mod
import discord
import aiohttp
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import asyncio

import config
from utils.logger import get_logger

logger = get_logger('travel')

# ── 國家代碼 → 貨幣 / 語言 對照 ────────────────────────────
# 覆蓋常見國家，找不到時使用預設值
COUNTRY_INFO: dict[str, tuple[str, str]] = {
    # country_code -> (currency, language_code)
    'JP': ('JPY', 'ja'), 'KR': ('KRW', 'ko'), 'TW': ('TWD', 'zh-TW'),
    'CN': ('CNY', 'zh-CN'), 'HK': ('HKD', 'zh-TW'), 'MO': ('MOP', 'zh-TW'),
    'SG': ('SGD', 'en'), 'TH': ('THB', 'th'), 'VN': ('VND', 'vi'),
    'PH': ('PHP', 'en'), 'MY': ('MYR', 'ms'), 'ID': ('IDR', 'id'),
    'IN': ('INR', 'hi'), 'AE': ('AED', 'ar'), 'SA': ('SAR', 'ar'),
    'TR': ('TRY', 'tr'), 'IL': ('ILS', 'he'), 'KH': ('KHR', 'km'),
    'MM': ('MMK', 'my'), 'LA': ('LAK', 'lo'), 'NP': ('NPR', 'ne'),
    'BD': ('BDT', 'bn'), 'LK': ('LKR', 'si'), 'PK': ('PKR', 'ur'),
    'US': ('USD', 'en'), 'CA': ('CAD', 'en'), 'MX': ('MXN', 'es'),
    'BR': ('BRL', 'pt'), 'AR': ('ARS', 'es'), 'CL': ('CLP', 'es'),
    'CO': ('COP', 'es'), 'PE': ('PEN', 'es'),
    'GB': ('GBP', 'en'), 'FR': ('EUR', 'fr'), 'DE': ('EUR', 'de'),
    'IT': ('EUR', 'it'), 'ES': ('EUR', 'es'), 'PT': ('EUR', 'pt'),
    'NL': ('EUR', 'nl'), 'BE': ('EUR', 'fr'), 'AT': ('EUR', 'de'),
    'CH': ('CHF', 'de'), 'SE': ('SEK', 'sv'), 'NO': ('NOK', 'no'),
    'DK': ('DKK', 'da'), 'FI': ('EUR', 'fi'), 'PL': ('PLN', 'pl'),
    'CZ': ('CZK', 'cs'), 'HU': ('HUF', 'hu'), 'RO': ('RON', 'ro'),
    'GR': ('EUR', 'el'), 'RU': ('RUB', 'ru'), 'UA': ('UAH', 'uk'),
    'IE': ('EUR', 'en'), 'IS': ('ISK', 'is'),
    'AU': ('AUD', 'en'), 'NZ': ('NZD', 'en'),
    'EG': ('EGP', 'ar'), 'ZA': ('ZAR', 'en'), 'KE': ('KES', 'sw'),
    'NG': ('NGN', 'en'), 'MA': ('MAD', 'ar'), 'TN': ('TND', 'ar'),
    'GH': ('GHS', 'en'), 'ET': ('ETB', 'am'),
}

# ── 國家代碼 → 時區前綴（用於自動推測）────────────────────
COUNTRY_TIMEZONE: dict[str, str] = {
    'JP': 'Asia/Tokyo', 'KR': 'Asia/Seoul', 'TW': 'Asia/Taipei',
    'CN': 'Asia/Shanghai', 'HK': 'Asia/Hong_Kong', 'SG': 'Asia/Singapore',
    'TH': 'Asia/Bangkok', 'VN': 'Asia/Ho_Chi_Minh', 'PH': 'Asia/Manila',
    'MY': 'Asia/Kuala_Lumpur', 'ID': 'Asia/Jakarta', 'IN': 'Asia/Kolkata',
    'AE': 'Asia/Dubai', 'SA': 'Asia/Riyadh', 'TR': 'Europe/Istanbul',
    'IL': 'Asia/Jerusalem', 'US': 'America/New_York', 'CA': 'America/Toronto',
    'MX': 'America/Mexico_City', 'BR': 'America/Sao_Paulo',
    'AR': 'America/Argentina/Buenos_Aires', 'CL': 'America/Santiago',
    'GB': 'Europe/London', 'FR': 'Europe/Paris', 'DE': 'Europe/Berlin',
    'IT': 'Europe/Rome', 'ES': 'Europe/Madrid', 'PT': 'Europe/Lisbon',
    'NL': 'Europe/Amsterdam', 'CH': 'Europe/Zurich', 'SE': 'Europe/Stockholm',
    'NO': 'Europe/Oslo', 'DK': 'Europe/Copenhagen', 'FI': 'Europe/Helsinki',
    'PL': 'Europe/Warsaw', 'CZ': 'Europe/Prague', 'HU': 'Europe/Budapest',
    'RO': 'Europe/Bucharest', 'GR': 'Europe/Athens', 'RU': 'Europe/Moscow',
    'UA': 'Europe/Kiev', 'IE': 'Europe/Dublin', 'IS': 'Atlantic/Reykjavik',
    'AU': 'Australia/Sydney', 'NZ': 'Pacific/Auckland',
    'EG': 'Africa/Cairo', 'ZA': 'Africa/Johannesburg', 'KE': 'Africa/Nairobi',
    'NG': 'Africa/Lagos', 'MA': 'Africa/Casablanca',
}

# 旅遊常用語
TRAVEL_PHRASES = [
    ('你好', 'Hello'),
    ('謝謝', 'Thank you'),
    ('多少錢？', 'How much?'),
    ('請問廁所在哪裡？', 'Where is the restroom?'),
    ('好吃', 'Delicious'),
]


def country_flag(code: str) -> str:
    """將國家代碼轉為國旗 emoji"""
    if not code or len(code) != 2:
        return '🌍'
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code.upper())


class TravelCog(commands.Cog, name='旅遊'):
    """旅遊資訊查詢 — 支援中英文城市搜尋"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _geocode(self, query: str) -> dict | None:
        """用 Geocoding API 解析城市名"""
        api_key = config.OPENWEATHER_API_KEY
        if not api_key:
            return None

        url = 'https://api.openweathermap.org/geo/1.0/direct'
        params = {'q': query, 'limit': 1, 'appid': api_key}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            return data[0] if data else None
        except Exception as e:
            logger.error(f'Geocoding 失敗: {e}')
            return None

    async def _get_weather_brief(self, lat: float, lon: float) -> str:
        """用經緯度取得簡短天氣描述"""
        api_key = config.OPENWEATHER_API_KEY
        if not api_key:
            return '⚠️ 天氣服務未設定'

        url = 'https://api.openweathermap.org/data/2.5/weather'
        params = {'lat': lat, 'lon': lon, 'appid': api_key, 'units': 'metric', 'lang': 'en'}
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
            feels = data['main']['feels_like']
            humidity = data['main']['humidity']
            return f'{icon} **{temp:.1f}°C** ({desc_zh})\n體感 {feels:.1f}°C ・ 濕度 {humidity}%'
        except Exception as e:
            logger.warning(f'天氣查詢失敗: {e}')
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

    @app_commands.command(name='travel', description='查詢目的地旅遊資訊（支援中英文搜尋）')
    @app_commands.describe(city='城市名稱（如：屏東、Paris、東京、Houston TX）')
    async def slash_travel(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()

        # Step 1: Geocoding
        loc = await self._geocode(city)
        if not loc:
            embed = discord.Embed(
                description=(
                    f'❌ 找不到「**{city}**」的位置資訊。\n\n'
                    '💡 **搜尋提示**：\n'
                    '> • 中文：`屏東`、`台北`、`東京`、`巴黎`\n'
                    '> • 英文：`Houston`、`London`、`Sydney`\n'
                    '> • 精確搜尋：`Houston, TX, US`'
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)
            return

        lat = loc['lat']
        lon = loc['lon']
        country_code = loc.get('country', '')
        state = loc.get('state', '')
        local_names = loc.get('local_names', {})
        display_name = local_names.get('zh', '') or local_names.get('ja', '') or loc.get('name', city)
        eng_name = loc.get('name', '')

        # 取得國家資訊
        currency, lang_code = COUNTRY_INFO.get(country_code, ('USD', 'en'))
        tz_name = COUNTRY_TIMEZONE.get(country_code, 'UTC')

        # Step 2: 並行取得所有資料
        weather_task = asyncio.create_task(self._get_weather_brief(lat, lon))
        rate_task = asyncio.create_task(self._get_exchange_rate(currency))
        phrase_task = asyncio.create_task(self._translate_phrases(lang_code))

        weather_str = await weather_task
        rate_str = await rate_task
        phrases = await phrase_task

        # 當地時間
        try:
            import pytz
            tz = pytz.timezone(tz_name)
            local_time = datetime.now(tz)
            time_str = local_time.strftime('%Y-%m-%d %H:%M:%S (%A)')
        except Exception:
            time_str = '無法取得當地時間'

        # 組合標題
        flag = country_flag(country_code)
        location_parts = [display_name]
        if state and state != display_name:
            location_parts.append(state)
        location_parts.append(country_code)
        title_str = ', '.join(location_parts)
        if eng_name and eng_name != display_name:
            title_str += f' ({eng_name})'

        embed = discord.Embed(
            title=f'✈️ {flag} {title_str}',
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

        embed.set_footer(
            text=f'📍 {lat:.2f}°N, {lon:.2f}°E  •  PongPong {config.BOT_VERSION}'
        )
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(TravelCog(bot))
