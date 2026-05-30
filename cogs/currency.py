# -*- coding: utf-8 -*-
"""
PongPong Bot — 匯率 Cog
提供 /cc、!cc 匯率轉換指令，使用 ExchangeRate-API v6
"""

import discord
import aiohttp
from discord import app_commands
from discord.ext import commands
from datetime import datetime

import config
from utils.logger import get_logger

logger = get_logger('currency')


# ── 常見貨幣 autocomplete ─────────────────────────────────
CURRENCY_CHOICES = [
    app_commands.Choice(name='🇺🇸 USD — 美元', value='USD'),
    app_commands.Choice(name='🇪🇺 EUR — 歐元', value='EUR'),
    app_commands.Choice(name='🇯🇵 JPY — 日圓', value='JPY'),
    app_commands.Choice(name='🇹🇼 TWD — 新台幣', value='TWD'),
    app_commands.Choice(name='🇨🇳 CNY — 人民幣', value='CNY'),
    app_commands.Choice(name='🇰🇷 KRW — 韓元', value='KRW'),
    app_commands.Choice(name='🇬🇧 GBP — 英鎊', value='GBP'),
    app_commands.Choice(name='🇦🇺 AUD — 澳幣', value='AUD'),
    app_commands.Choice(name='🇨🇦 CAD — 加幣', value='CAD'),
    app_commands.Choice(name='🇨🇭 CHF — 瑞士法郎', value='CHF'),
    app_commands.Choice(name='🇭🇰 HKD — 港幣', value='HKD'),
    app_commands.Choice(name='🇸🇬 SGD — 新加坡幣', value='SGD'),
    app_commands.Choice(name='🇮🇳 INR — 印度盧比', value='INR'),
    app_commands.Choice(name='🇹🇭 THB — 泰銖', value='THB'),
]


class CurrencyCog(commands.Cog, name='匯率'):
    """匯率轉換指令"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _convert(self, amount: float, source: str, target: str) -> tuple[float | None, dict | None, str | None]:
        """
        呼叫 ExchangeRate-API v6 進行匯率轉換。
        回傳 (結果金額, 完整資料, 錯誤訊息)
        """
        api_key = config.CURRENCY_API_KEY
        if not api_key:
            return None, None, '❌ 匯率服務的 API Key 尚未設定。'

        cache_key = f'cc:{source}:{target}:{amount}'
        cached = await self.bot.cache.get(cache_key)
        if cached:
            return cached['result'], cached['data'], None

        url = f'https://v6.exchangerate-api.com/v6/{api_key}/pair/{source}/{target}/{amount}'
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()

            if data.get('result') == 'success':
                result = float(data['conversion_result'])
                await self.bot.cache.set(cache_key, {'result': result, 'data': data}, ttl=300)
                return result, data, None
            else:
                err = data.get('error-type', '未知錯誤')
                return None, None, f'❌ API 查詢失敗：{err}'
        except asyncio.TimeoutError:
            return None, None, '❌ 匯率 API 回應逾時，請稍後再試。'
        except Exception as e:
            logger.error(f'匯率轉換錯誤: {e}')
            return None, None, f'❌ 請求錯誤：{e}'

    def _build_embed(self, amount: float, source: str, target: str, result: float, data: dict) -> discord.Embed:
        """建立漂亮的匯率 Embed"""
        src_flag = config.CURRENCY_FLAGS.get(source, '💰')
        tgt_flag = config.CURRENCY_FLAGS.get(target, '💰')
        rate = data.get('conversion_rate', result / amount if amount else 0)

        embed = discord.Embed(
            title='💱 匯率轉換',
            color=config.COLOR_CURRENCY,
        )
        embed.add_field(
            name=f'{src_flag} {source}',
            value=f'```{amount:,.2f}```',
            inline=True,
        )
        embed.add_field(
            name='➡️',
            value='\u200b',
            inline=True,
        )
        embed.add_field(
            name=f'{tgt_flag} {target}',
            value=f'```{result:,.2f}```',
            inline=True,
        )
        embed.add_field(
            name='📊 匯率',
            value=f'`1 {source}` = `{rate:,.4f} {target}`',
            inline=False,
        )

        update_time = data.get('time_last_update_utc', '')
        if update_time:
            embed.set_footer(text=f'匯率更新時間：{update_time[:25]}  •  PongPong {config.BOT_VERSION}')
        else:
            embed.set_footer(text=f'PongPong {config.BOT_VERSION}')

        return embed

    # ── /cc 斜線指令 ───────────────────────────────────
    @app_commands.command(name='cc', description='貨幣匯率轉換')
    @app_commands.describe(
        amount='金額',
        from_currency='來源貨幣',
        to_currency='目標貨幣',
    )
    @app_commands.choices(from_currency=CURRENCY_CHOICES, to_currency=CURRENCY_CHOICES)
    async def slash_convert(
        self,
        interaction: discord.Interaction,
        amount: float,
        from_currency: app_commands.Choice[str],
        to_currency: app_commands.Choice[str],
    ):
        await interaction.response.defer()

        result, data, err = await self._convert(amount, from_currency.value, to_currency.value)
        if err:
            embed = discord.Embed(description=err, color=config.COLOR_ERROR)
            await interaction.followup.send(embed=embed)
            return

        embed = self._build_embed(amount, from_currency.value, to_currency.value, result, data)
        await interaction.followup.send(embed=embed)

    # ── !cc 前綴指令（向下相容）─────────────────────────
    @commands.command(name='cc', help='匯率轉換。用法: !cc [金額] 來源-目標  或  !cc 來源-目標 [金額]')
    async def prefix_convert(self, ctx: commands.Context, *args):
        if not args:
            await ctx.send('❌ 用法：`!cc [金額] 來源-目標` 例如 `!cc 100 jpy-twd`')
            return

        src, tgt, amt_str = 'JPY', 'TWD', '1.0'

        # 解析參數（相容原始邏輯）
        if len(args) == 1:
            if '-' in args[0]:
                parts = args[0].split('-')
                if len(parts) == 2:
                    src, tgt = parts[0].upper(), parts[1].upper()
            else:
                amt_str = args[0]
        elif len(args) >= 2:
            if '-' in args[0]:
                parts = args[0].split('-')
                if len(parts) == 2:
                    src, tgt = parts[0].upper(), parts[1].upper()
                amt_str = args[1]
            elif '-' in args[1]:
                parts = args[1].split('-')
                if len(parts) == 2:
                    src, tgt = parts[0].upper(), parts[1].upper()
                amt_str = args[0]

        try:
            amount = float(amt_str)
        except ValueError:
            embed = discord.Embed(description='❌ 金額格式錯誤', color=config.COLOR_ERROR)
            await ctx.send(embed=embed)
            return

        result, data, err = await self._convert(amount, src, tgt)
        if err:
            await ctx.send(err)
            return

        embed = self._build_embed(amount, src, tgt, result, data)

        ref = ctx.message.reference
        await ctx.send(embed=embed, reference=ref, mention_author=False)


# 需要 import asyncio（_convert 裡用到 asyncio.TimeoutError）
import asyncio


async def setup(bot: commands.Bot):
    await bot.add_cog(CurrencyCog(bot))
