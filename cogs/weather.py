# -*- coding: utf-8 -*-
"""
PongPong Bot — 天氣 Cog
使用 OpenWeatherMap Geocoding API + Weather API
支援中文、英文、日文等多語言城市 / 區域搜尋
"""

import discord
import aiohttp
from discord import app_commands
from discord.ext import commands
from datetime import datetime

import config
from utils.logger import get_logger

logger = get_logger('weather')

# ── 天氣圖示對應 ──────────────────────────────────────────
WEATHER_ICONS: dict[str, str] = {
    '01d': '☀️', '01n': '🌙',
    '02d': '⛅', '02n': '☁️',
    '03d': '☁️', '03n': '☁️',
    '04d': '☁️', '04n': '☁️',
    '09d': '🌧️', '09n': '🌧️',
    '10d': '🌦️', '10n': '🌧️',
    '11d': '⛈️', '11n': '⛈️',
    '13d': '🌨️', '13n': '🌨️',
    '50d': '🌫️', '50n': '🌫️',
}

# ── 天氣狀態中文對照 ──────────────────────────────────────
WEATHER_DESC_ZH: dict[str, str] = {
    'clear sky': '晴朗', 'few clouds': '少雲', 'scattered clouds': '多雲',
    'broken clouds': '陰天', 'overcast clouds': '陰天',
    'shower rain': '陣雨', 'rain': '雨', 'light rain': '小雨',
    'moderate rain': '中雨', 'heavy intensity rain': '大雨',
    'very heavy rain': '暴雨', 'extreme rain': '極端暴雨',
    'thunderstorm': '雷暴', 'thunderstorm with rain': '雷陣雨',
    'thunderstorm with heavy rain': '雷暴大雨',
    'snow': '雪', 'light snow': '小雪', 'heavy snow': '大雪',
    'sleet': '雨夾雪', 'freezing rain': '凍雨',
    'mist': '薄霧', 'fog': '霧', 'haze': '霾',
    'drizzle': '毛毛雨', 'light intensity drizzle': '微雨',
    'smoke': '煙霧', 'dust': '塵', 'sand': '沙塵',
    'tornado': '龍捲風', 'squalls': '狂風',
}

# ── 國家代碼 → 國旗 ────────────────────────────────────────
def country_flag(code: str) -> str:
    """將國家代碼轉為國旗 emoji"""
    if not code or len(code) != 2:
        return '🌍'
    return ''.join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code.upper())


def _temp_color(temp_c: float) -> int:
    """依據溫度回傳 Embed 顏色"""
    if temp_c <= 5:
        return 0x5865F2   # 寒冷 → 藍色
    elif temp_c <= 15:
        return 0x3498DB   # 涼爽 → 淺藍
    elif temp_c <= 25:
        return 0x57F287   # 舒適 → 綠色
    elif temp_c <= 33:
        return 0xF1C40F   # 溫暖 → 橘黃
    else:
        return 0xED4245   # 炎熱 → 紅色


class WeatherCog(commands.Cog, name='天氣'):
    """天氣查詢指令 — 支援中英文城市 / 區域搜尋"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _geocode(self, query: str, limit: int = 5) -> list[dict] | None:
        """使用 OpenWeatherMap Geocoding API 解析城市名稱 → 經緯度
        支援中文、英文、日文等多語言輸入
        """
        api_key = config.OPENWEATHER_API_KEY
        if not api_key:
            return None

        url = 'https://api.openweathermap.org/geo/1.0/direct'
        params = {
            'q': query,
            'limit': limit,
            'appid': api_key,
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            return data if data else None
        except Exception as e:
            logger.error(f'Geocoding API 錯誤: {e}')
            return None

    async def _fetch_weather_by_coords(self, lat: float, lon: float) -> dict | None:
        """用經緯度查詢天氣"""
        api_key = config.OPENWEATHER_API_KEY
        if not api_key:
            return None

        cache_key = f'weather:{lat:.4f},{lon:.4f}'
        cached = await self.bot.cache.get(cache_key)
        if cached:
            return cached

        url = 'https://api.openweathermap.org/data/2.5/weather'
        params = {
            'lat': lat,
            'lon': lon,
            'appid': api_key,
            'units': 'metric',
            'lang': 'en',
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            await self.bot.cache.set(cache_key, data, ttl=300)
            return data
        except Exception as e:
            logger.error(f'天氣 API 錯誤: {e}')
            return None

    @app_commands.command(name='weather', description='查詢城市 / 地區即時天氣（支援中英文搜尋）')
    @app_commands.describe(city='城市或地區名稱（如：屏東、Houston TX、東京、Paris）')
    async def slash_weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()

        # Step 1: Geocoding — 將城市名稱轉為經緯度
        locations = await self._geocode(city)

        if not locations:
            embed = discord.Embed(
                description=(
                    f'❌ 找不到「**{city}**」的位置資訊。\n\n'
                    '💡 **搜尋提示**：\n'
                    '> • 中文：`屏東`、`台北`、`東京`、`紐約`\n'
                    '> • 英文：`Houston`、`London`、`Sydney`\n'
                    '> • 精確搜尋：`Houston, TX, US`、`屏東, TW`\n'
                    '> • 地區搜尋：`Shibuya`、`Manhattan`'
                ),
                color=config.COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)
            return

        # 取第一個匹配結果
        loc = locations[0]
        lat = loc['lat']
        lon = loc['lon']
        loc_country = loc.get('country', '')
        # 取得在地化名稱
        local_names = loc.get('local_names', {})
        display_name = local_names.get('zh', '') or local_names.get('ja', '') or loc.get('name', city)
        eng_name = loc.get('name', '')
        state = loc.get('state', '')

        # Step 2: 用經緯度查天氣
        data = await self._fetch_weather_by_coords(lat, lon)
        if not data:
            embed = discord.Embed(
                description=f'❌ 無法取得「{display_name}」的天氣資料。',
                color=config.COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)
            return

        # 解析天氣資料
        main = data['main']
        wind = data.get('wind', {})
        weather = data['weather'][0]
        icon_code = weather.get('icon', '01d')
        icon = WEATHER_ICONS.get(icon_code, '🌍')
        desc_en = weather.get('description', '')
        desc = WEATHER_DESC_ZH.get(desc_en, desc_en)

        temp = main['temp']
        feels_like = main['feels_like']
        humidity = main['humidity']
        wind_speed = wind.get('speed', 0)

        # 組合標題
        flag = country_flag(loc_country)
        location_parts = [display_name]
        if state and state != display_name:
            location_parts.append(state)
        location_parts.append(loc_country)
        title_str = ', '.join(location_parts)
        if eng_name and eng_name != display_name:
            title_str += f' ({eng_name})'

        embed = discord.Embed(
            title=f'{icon} {flag} {title_str}',
            description=f'**{desc}**',
            color=_temp_color(temp),
        )
        embed.add_field(name='🌡️ 溫度', value=f'`{temp:.1f}°C`', inline=True)
        embed.add_field(name='🤒 體感', value=f'`{feels_like:.1f}°C`', inline=True)
        embed.add_field(name='💧 濕度', value=f'`{humidity}%`', inline=True)
        embed.add_field(name='💨 風速', value=f'`{wind_speed} m/s`', inline=True)

        temp_min = main.get('temp_min', temp)
        temp_max = main.get('temp_max', temp)
        embed.add_field(name='📉 最低', value=f'`{temp_min:.1f}°C`', inline=True)
        embed.add_field(name='📈 最高', value=f'`{temp_max:.1f}°C`', inline=True)

        # 如果有多個匹配結果，顯示其他選項
        if len(locations) > 1:
            others = []
            for loc2 in locations[1:4]:  # 最多顯示 3 個其他選項
                name2 = loc2.get('name', '')
                state2 = loc2.get('state', '')
                country2 = loc2.get('country', '')
                parts = [name2]
                if state2:
                    parts.append(state2)
                parts.append(country2)
                others.append(', '.join(parts))
            if others:
                embed.add_field(
                    name='🔍 你是不是在找...',
                    value='\n'.join(f'• `{o}`' for o in others),
                    inline=False,
                )

        embed.set_thumbnail(url=f'https://openweathermap.org/img/wn/{icon_code}@2x.png')
        embed.set_footer(text=f'📍 {lat:.2f}°N, {lon:.2f}°E  •  PongPong {config.BOT_VERSION}  •  OpenWeatherMap')

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WeatherCog(bot))
