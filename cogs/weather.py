# -*- coding: utf-8 -*-
"""
PongPong Bot — 天氣 Cog
使用 OpenWeatherMap API 查詢即時天氣
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
    'thunderstorm': '雷暴', 'snow': '雪', 'light snow': '小雪',
    'mist': '薄霧', 'fog': '霧', 'haze': '霾',
    'drizzle': '毛毛雨', 'light intensity drizzle': '微雨',
}


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
    """天氣查詢指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _translate_city(self, city: str) -> str:
        """將非英文城市名稱翻譯為英文（用於 API 查詢）"""
        # 若看起來像英文就直接用
        if city.isascii():
            return city
        client = getattr(self.bot, 'translate_client', None)
        if not client:
            return city
        try:
            result = client.translate(city, target_language='en')
            import html as html_mod
            return html_mod.unescape(result['translatedText'])
        except Exception:
            return city

    async def _fetch_weather(self, city: str) -> dict | None:
        """呼叫 OpenWeatherMap API"""
        api_key = config.OPENWEATHER_API_KEY
        if not api_key:
            return None

        cache_key = f'weather:{city.lower()}'
        cached = await self.bot.cache.get(cache_key)
        if cached:
            return cached

        # 先嘗試翻譯城市名
        query_city = await self._translate_city(city)

        url = 'https://api.openweathermap.org/data/2.5/weather'
        params = {
            'q': query_city,
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

    @app_commands.command(name='weather', description='查詢城市即時天氣')
    @app_commands.describe(city='城市名稱（支援中文 / 英文 / 日文）')
    async def slash_weather(self, interaction: discord.Interaction, city: str):
        await interaction.response.defer()

        data = await self._fetch_weather(city)
        if not data or data.get('cod') != 200:
            embed = discord.Embed(
                description=f'❌ 找不到城市「{city}」的天氣資料，請確認名稱是否正確。',
                color=config.COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)
            return

        # 解析資料
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
        city_name = data.get('name', city)
        country = data.get('sys', {}).get('country', '')

        embed = discord.Embed(
            title=f'{icon} {city_name}, {country}',
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

        # 天氣圖示 URL
        embed.set_thumbnail(url=f'https://openweathermap.org/img/wn/{icon_code}@2x.png')
        embed.set_footer(text=f'PongPong {config.BOT_VERSION}  •  資料來源：OpenWeatherMap')

        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(WeatherCog(bot))
