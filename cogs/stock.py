# -*- coding: utf-8 -*-
"""
PongPong Bot — 股票 & 加密貨幣 Cog
自動辨識台股/美股/加密貨幣，使用 yfinance + CoinGecko API
"""

import io
import asyncio
import discord
import aiohttp
import yfinance as yf
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timedelta

import config
from utils.logger import get_logger
from utils.chart import generate_stock_chart

logger = get_logger('stock')

# ── 加密貨幣代碼對應 CoinGecko ID ─────────────────────────
CRYPTO_SYMBOLS: dict[str, str] = {
    'btc': 'bitcoin', 'eth': 'ethereum', 'doge': 'dogecoin',
    'sol': 'solana', 'xrp': 'ripple', 'ada': 'cardano',
    'dot': 'polkadot', 'matic': 'matic-network', 'avax': 'avalanche-2',
    'link': 'chainlink', 'usdt': 'tether', 'usdc': 'usd-coin',
    'bnb': 'binancecoin', 'shib': 'shiba-inu', 'trx': 'tron',
    'ton': 'the-open-network', 'atom': 'cosmos', 'near': 'near',
    'apt': 'aptos', 'sui': 'sui',
}


def _detect_input_type(code: str) -> tuple[str, str]:
    """
    自動辨識輸入類型。
    回傳 (type, normalized_code)
    type: 'tw_stock', 'us_stock', 'crypto'
    """
    code_lower = code.lower().strip()

    # 加密貨幣
    if code_lower in CRYPTO_SYMBOLS:
        return 'crypto', code_lower

    # 純數字 → 台股
    if code.strip().isdigit():
        return 'tw_stock', code.strip()

    # 數字 + .TW / .TWO
    if code.upper().endswith('.TW') or code.upper().endswith('.TWO'):
        return 'tw_stock', code.upper()

    # 其餘視為美股
    return 'us_stock', code.upper().strip()


class StockCog(commands.Cog, name='股票'):
    """股票 & 加密貨幣查詢指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ────────────────────────────────────────────────────
    # yfinance 查詢（在執行緒中執行以避免阻塞）
    # ────────────────────────────────────────────────────
    async def _fetch_stock(self, symbol: str) -> dict | None:
        """使用 yfinance 取得股票資料"""
        def _get():
            ticker = yf.Ticker(symbol)
            info = ticker.info
            if not info or info.get('regularMarketPrice') is None:
                # 備用：嘗試從 history 取
                hist = ticker.history(period='5d')
                if hist.empty:
                    return None
                last_close = float(hist['Close'].iloc[-1])
                prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else last_close
                return {
                    'name': info.get('shortName', symbol),
                    'symbol': symbol,
                    'price': last_close,
                    'prev_close': prev_close,
                    'open': float(hist['Open'].iloc[-1]),
                    'high': float(hist['High'].iloc[-1]),
                    'low': float(hist['Low'].iloc[-1]),
                    'close': last_close,
                    'volume': int(hist['Volume'].iloc[-1]),
                    'currency': info.get('currency', 'USD'),
                }
            return {
                'name': info.get('shortName', info.get('longName', symbol)),
                'symbol': symbol,
                'price': info.get('regularMarketPrice', 0),
                'prev_close': info.get('regularMarketPreviousClose', info.get('previousClose', 0)),
                'open': info.get('regularMarketOpen', info.get('open', 0)),
                'high': info.get('regularMarketDayHigh', info.get('dayHigh', 0)),
                'low': info.get('regularMarketDayLow', info.get('dayLow', 0)),
                'close': info.get('regularMarketPrice', 0),
                'volume': info.get('regularMarketVolume', info.get('volume', 0)),
                'currency': info.get('currency', 'USD'),
            }
        try:
            return await asyncio.to_thread(_get)
        except Exception as e:
            logger.error(f'yfinance 查詢失敗 ({symbol}): {e}')
            return None

    # ────────────────────────────────────────────────────
    # CoinGecko 查詢
    # ────────────────────────────────────────────────────
    async def _fetch_crypto(self, coin_id: str) -> dict | None:
        """使用 CoinGecko API 取得加密貨幣資料"""
        cache_key = f'crypto:{coin_id}'
        cached = await self.bot.cache.get(cache_key)
        if cached:
            return cached

        url = 'https://api.coingecko.com/api/v3/coins/markets'
        params = {
            'vs_currency': 'usd',
            'ids': coin_id,
            'order': 'market_cap_desc',
            'per_page': 1,
            'page': 1,
            'sparkline': 'false',
            'price_change_percentage': '24h,7d',
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        logger.error(f'CoinGecko API 回應 {resp.status}')
                        return None
                    data = await resp.json()

            if not data:
                return None

            coin = data[0]
            result = {
                'name': coin.get('name', ''),
                'symbol': coin.get('symbol', '').upper(),
                'price': coin.get('current_price', 0),
                'change_24h': coin.get('price_change_24h', 0),
                'change_pct_24h': coin.get('price_change_percentage_24h', 0),
                'high_24h': coin.get('high_24h', 0),
                'low_24h': coin.get('low_24h', 0),
                'market_cap': coin.get('market_cap', 0),
                'volume': coin.get('total_volume', 0),
                'circulating_supply': coin.get('circulating_supply', 0),
                'image': coin.get('image', ''),
                'ath': coin.get('ath', 0),
            }
            await self.bot.cache.set(cache_key, result, ttl=120)
            return result
        except Exception as e:
            logger.error(f'CoinGecko 查詢失敗 ({coin_id}): {e}')
            return None

    # ────────────────────────────────────────────────────
    # 圖表資料取得
    # ────────────────────────────────────────────────────
    async def _fetch_chart_data(self, input_type: str, code: str, days: int) -> tuple[list, list, str]:
        """取得圖表用的歷史資料，回傳 (dates, prices, title)"""
        if input_type == 'crypto':
            coin_id = CRYPTO_SYMBOLS.get(code, code)
            url = f'https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart'
            params = {'vs_currency': 'usd', 'days': days}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
            prices_raw = data.get('prices', [])
            dates = [datetime.fromtimestamp(p[0] / 1000) for p in prices_raw]
            prices = [p[1] for p in prices_raw]
            return dates, prices, f'{coin_id.upper()} — {days}D'
        else:
            # yfinance
            symbol = f'{code}.TW' if input_type == 'tw_stock' and not code.endswith(('.TW', '.TWO')) else code
            period = f'{days}d' if days <= 30 else f'{min(days, 365)}d'

            def _get():
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=period)
                return hist

            hist = await asyncio.to_thread(_get)
            if hist.empty:
                return [], [], ''
            dates = list(hist.index.to_pydatetime())
            prices = list(hist['Close'].values)
            return dates, prices, f'{symbol} — {days}D'

    # ────────────────────────────────────────────────────
    # /stock 斜線指令
    # ────────────────────────────────────────────────────
    @app_commands.command(name='stock', description='查詢股票或加密貨幣即時價格')
    @app_commands.describe(code='股票代碼 / 加密貨幣代碼（例如: 2330, AAPL, BTC）')
    async def slash_stock(self, interaction: discord.Interaction, code: str):
        await interaction.response.defer()

        input_type, normalized = _detect_input_type(code)

        try:
            if input_type == 'crypto':
                coin_id = CRYPTO_SYMBOLS.get(normalized, normalized)
                data = await self._fetch_crypto(coin_id)
                if not data:
                    embed = discord.Embed(
                        description=f'❌ 找不到加密貨幣 `{code}`，請確認代碼是否正確。',
                        color=config.COLOR_ERROR,
                    )
                    await interaction.followup.send(embed=embed)
                    return
                embed = self._build_crypto_embed(data)
            else:
                # 股票
                symbol = f'{normalized}.TW' if input_type == 'tw_stock' and not normalized.endswith(('.TW', '.TWO')) else normalized
                data = await self._fetch_stock(symbol)
                if not data:
                    embed = discord.Embed(
                        description=f'❌ 找不到股票 `{code}`，請確認代碼是否正確。',
                        color=config.COLOR_ERROR,
                    )
                    await interaction.followup.send(embed=embed)
                    return
                is_tw = input_type == 'tw_stock'
                embed = self._build_stock_embed(data, is_tw=is_tw)

            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f'股票查詢錯誤 ({code}): {e}')
            embed = discord.Embed(
                description=f'❌ 查詢時發生錯誤：{e}',
                color=config.COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)

    # ────────────────────────────────────────────────────
    # /chart 圖表指令
    # ────────────────────────────────────────────────────
    @app_commands.command(name='chart', description='顯示股票或加密貨幣價格走勢圖')
    @app_commands.describe(
        code='股票代碼 / 加密貨幣代碼',
        days='天數（預設 30）',
    )
    async def slash_chart(self, interaction: discord.Interaction, code: str, days: int = 30):
        await interaction.response.defer()
        days = max(1, min(days, 365))

        input_type, normalized = _detect_input_type(code)

        try:
            dates, prices, title = await self._fetch_chart_data(input_type, normalized, days)
            if not dates:
                embed = discord.Embed(
                    description=f'❌ 無法取得 `{code}` 的歷史資料。',
                    color=config.COLOR_ERROR,
                )
                await interaction.followup.send(embed=embed)
                return

            currency_sym = 'NT$' if input_type == 'tw_stock' else '$'
            buf = await generate_stock_chart(
                symbol=normalized.upper(),
                dates=dates,
                prices=prices,
                title=title,
                currency_symbol=currency_sym,
            )
            file = discord.File(buf, filename=f'{normalized}_chart.png')
            embed = discord.Embed(
                title=f'📈 {title} 走勢圖',
                color=config.COLOR_PRIMARY,
            )
            embed.set_image(url=f'attachment://{normalized}_chart.png')
            embed.set_footer(text=f'PongPong {config.BOT_VERSION}  •  資料期間：{days} 天')

            await interaction.followup.send(embed=embed, file=file)
        except Exception as e:
            logger.error(f'圖表產生錯誤 ({code}): {e}')
            embed = discord.Embed(
                description=f'❌ 圖表產生失敗：{e}',
                color=config.COLOR_ERROR,
            )
            await interaction.followup.send(embed=embed)

    # ────────────────────────────────────────────────────
    # Embed 建構
    # ────────────────────────────────────────────────────
    def _build_stock_embed(self, data: dict, is_tw: bool = False) -> discord.Embed:
        """建立股票 Embed"""
        price = data['price']
        prev_close = data['prev_close'] or price
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0

        # 台股：紅漲綠跌；美股：綠漲紅跌
        if change >= 0:
            arrow = '▲'
            color = config.COLOR_TW_UP if is_tw else config.COLOR_STOCK_UP
        else:
            arrow = '▼'
            color = config.COLOR_TW_DOWN if is_tw else config.COLOR_STOCK_DOWN

        currency = data.get('currency', 'USD')
        cur_sym = 'NT$' if currency == 'TWD' else ('¥' if currency == 'JPY' else '$')

        embed = discord.Embed(
            title=f'{"🇹🇼" if is_tw else "🇺🇸"} {data["name"]}（{data["symbol"]}）',
            color=color,
        )
        embed.add_field(
            name='💰 現價',
            value=f'```{cur_sym}{price:,.2f}```',
            inline=True,
        )
        embed.add_field(
            name=f'{arrow} 漲跌',
            value=f'```diff\n{"+" if change >= 0 else ""}{change:,.2f} ({change_pct:+.2f}%)```',
            inline=True,
        )
        embed.add_field(name='\u200b', value='\u200b', inline=True)

        embed.add_field(name='📂 開盤', value=f'`{cur_sym}{data["open"]:,.2f}`', inline=True)
        embed.add_field(name='📈 最高', value=f'`{cur_sym}{data["high"]:,.2f}`', inline=True)
        embed.add_field(name='📉 最低', value=f'`{cur_sym}{data["low"]:,.2f}`', inline=True)

        vol = data.get('volume', 0)
        vol_str = f'{vol / 1_000_000:,.1f}M' if vol >= 1_000_000 else f'{vol / 1_000:,.1f}K' if vol >= 1_000 else str(vol)
        embed.add_field(name='📊 成交量', value=f'`{vol_str}`', inline=True)
        embed.add_field(name='💵 昨收', value=f'`{cur_sym}{prev_close:,.2f}`', inline=True)
        embed.add_field(name='\u200b', value='\u200b', inline=True)

        embed.set_footer(text=f'PongPong {config.BOT_VERSION}  •  {datetime.now().strftime("%Y-%m-%d %H:%M")}')
        return embed

    def _build_crypto_embed(self, data: dict) -> discord.Embed:
        """建立加密貨幣 Embed"""
        price = data['price']
        change = data['change_24h']
        change_pct = data['change_pct_24h']

        if change >= 0:
            arrow = '▲'
            color = config.COLOR_STOCK_UP
        else:
            arrow = '▼'
            color = config.COLOR_STOCK_DOWN

        embed = discord.Embed(
            title=f'🪙 {data["name"]}（{data["symbol"]}）',
            color=color,
        )

        if data.get('image'):
            embed.set_thumbnail(url=data['image'])

        embed.add_field(
            name='💰 現價 (USD)',
            value=f'```${price:,.2f}```' if price >= 1 else f'```${price:,.6f}```',
            inline=True,
        )
        embed.add_field(
            name=f'{arrow} 24h 漲跌',
            value=f'```diff\n{"+" if change >= 0 else ""}{change:,.2f} ({change_pct:+.2f}%)```',
            inline=True,
        )
        embed.add_field(name='\u200b', value='\u200b', inline=True)

        embed.add_field(name='📈 24h 最高', value=f'`${data["high_24h"]:,.2f}`', inline=True)
        embed.add_field(name='📉 24h 最低', value=f'`${data["low_24h"]:,.2f}`', inline=True)
        embed.add_field(name='🏆 歷史最高', value=f'`${data["ath"]:,.2f}`', inline=True)

        # 市值 & 供應量格式化
        mcap = data.get('market_cap', 0)
        mcap_str = f'${mcap / 1e9:,.2f}B' if mcap >= 1e9 else f'${mcap / 1e6:,.2f}M'
        vol = data.get('volume', 0)
        vol_str = f'${vol / 1e9:,.2f}B' if vol >= 1e9 else f'${vol / 1e6:,.2f}M'
        supply = data.get('circulating_supply', 0)
        supply_str = f'{supply / 1e6:,.1f}M' if supply >= 1e6 else f'{supply:,.0f}'

        embed.add_field(name='🏦 市值', value=f'`{mcap_str}`', inline=True)
        embed.add_field(name='📊 24h 交易量', value=f'`{vol_str}`', inline=True)
        embed.add_field(name='🔄 流通量', value=f'`{supply_str}`', inline=True)

        embed.set_footer(text=f'資料來源：CoinGecko  •  PongPong {config.BOT_VERSION}')
        return embed


async def setup(bot: commands.Bot):
    await bot.add_cog(StockCog(bot))
