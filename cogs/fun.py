# -*- coding: utf-8 -*-
"""
PongPong Bot — 趣味 Cog
提供 /roll 骰子、/pick 抽籤功能
"""

import random
import datetime
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.logger import get_logger

logger = get_logger('fun')


class FunCog(commands.Cog, name='趣味'):
    """骰子和抽籤功能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ── Slash Command: /roll ──────────────────────────────
    @app_commands.command(name='roll', description='擲骰子，隨機產生一個數字')
    @app_commands.describe(max_value='最大值（預設 100）')
    async def slash_roll(self, interaction: discord.Interaction, max_value: int = 100):
        if max_value < 1:
            max_value = 100

        result = random.randint(1, max_value)

        # 根據結果選擇表情
        if result == max_value:
            emoji = '🎉'
            comment = '滿分！太幸運了！'
        elif result == 1:
            emoji = '😱'
            comment = '最低點...再試一次吧！'
        elif result > max_value * 0.8:
            emoji = '🔥'
            comment = '運氣不錯！'
        elif result > max_value * 0.5:
            emoji = '😊'
            comment = '還可以！'
        else:
            emoji = '🍀'
            comment = '下次會更好的！'

        embed = discord.Embed(
            title=f'🎲 擲骰子 (1-{max_value})',
            color=config.COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.description = f'# {emoji} {result}\n\n*{comment}*'
        embed.set_footer(text=f'{interaction.user.display_name} 擲了骰子')
        await interaction.response.send_message(embed=embed)
        logger.info(f'[/roll] {interaction.user} 擲出 {result}/{max_value}')

    # ── Slash Command: /pick ──────────────────────────────
    @app_commands.command(name='pick', description='從選項中隨機抽籤')
    @app_commands.describe(options='選項（用逗號或空格分隔）')
    async def slash_pick(self, interaction: discord.Interaction, options: str):
        # 先嘗試逗號分隔，再嘗試空格
        if ',' in options:
            choices = [o.strip() for o in options.split(',') if o.strip()]
        else:
            choices = [o.strip() for o in options.split() if o.strip()]

        if len(choices) < 2:
            await interaction.response.send_message(
                '❌ 請提供至少 2 個選項（用逗號或空格分隔）。\n'
                '例如: `/pick 吃火鍋, 吃拉麵, 吃壽司`',
                ephemeral=True
            )
            return

        picked = random.choice(choices)

        embed = discord.Embed(
            title='🎰 抽籤結果',
            color=config.COLOR_SUCCESS,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        # 顯示所有選項
        options_display = '\n'.join(
            f'{"👉 **" if c == picked else "　　"}{c}{"**" if c == picked else ""}'
            for c in choices
        )
        embed.add_field(name='📋 所有選項', value=options_display, inline=False)
        embed.add_field(name='✨ 結果', value=f'# 🎯 {picked}', inline=False)
        embed.set_footer(text=f'{interaction.user.display_name} 進行了抽籤')

        await interaction.response.send_message(embed=embed)
        logger.info(f'[/pick] {interaction.user} 從 {len(choices)} 個選項中抽到 "{picked}"')

    # ── Prefix Command: !roll ────────────────────────────
    @commands.command(name='roll', help='擲骰子。格式: !roll [最大值]')
    async def prefix_roll(self, ctx: commands.Context, max_value: int = 100):
        if max_value < 1:
            max_value = 100
        result = random.randint(1, max_value)

        embed = discord.Embed(
            title=f'🎲 擲骰子 (1-{max_value})',
            description=f'# 🎯 {result}',
            color=config.COLOR_PRIMARY,
        )
        await ctx.send(embed=embed)

    # ── Prefix Command: !pick ────────────────────────────
    @commands.command(name='pick', help='隨機抽籤。格式: !pick 選項1 選項2 ...')
    async def prefix_pick(self, ctx: commands.Context, *args):
        if len(args) < 2:
            await ctx.send('❌ 請提供至少 2 個選項。例如: `!pick 火鍋 拉麵 壽司`')
            return

        picked = random.choice(args)
        embed = discord.Embed(
            title='🎰 抽籤結果',
            description=f'# 🎯 {picked}',
            color=config.COLOR_SUCCESS,
        )
        embed.add_field(
            name='📋 候選',
            value=' / '.join(args),
            inline=False
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(FunCog(bot))
