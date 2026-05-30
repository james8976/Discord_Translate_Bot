# -*- coding: utf-8 -*-
"""
PongPong Bot — 國旗猜謎 Cog
/flagquiz 開始測驗、/quizrank 查看排行榜
"""

import random
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

import config
from database import db
from utils.logger import get_logger

logger = get_logger('flagquiz')

# ── 國家資料 ───────────────────────────────────────────────
# flag_emoji, names: {zh, en, ja}, currency, capital, greeting
COUNTRY_DATA: list[dict] = [
    {'flag': '🇯🇵', 'names': {'zh': '日本', 'en': 'japan', 'ja': '日本'}, 'currency': 'JPY', 'capital': '東京', 'greeting': 'こんにちは'},
    {'flag': '🇰🇷', 'names': {'zh': '韓國', 'en': 'south korea', 'ja': '韓国'}, 'currency': 'KRW', 'capital': '首爾', 'greeting': '안녕하세요'},
    {'flag': '🇺🇸', 'names': {'zh': '美國', 'en': 'united states', 'ja': 'アメリカ'}, 'currency': 'USD', 'capital': '華盛頓', 'greeting': 'Hello'},
    {'flag': '🇬🇧', 'names': {'zh': '英國', 'en': 'united kingdom', 'ja': 'イギリス'}, 'currency': 'GBP', 'capital': '倫敦', 'greeting': 'Hello'},
    {'flag': '🇫🇷', 'names': {'zh': '法國', 'en': 'france', 'ja': 'フランス'}, 'currency': 'EUR', 'capital': '巴黎', 'greeting': 'Bonjour'},
    {'flag': '🇩🇪', 'names': {'zh': '德國', 'en': 'germany', 'ja': 'ドイツ'}, 'currency': 'EUR', 'capital': '柏林', 'greeting': 'Hallo'},
    {'flag': '🇮🇹', 'names': {'zh': '義大利', 'en': 'italy', 'ja': 'イタリア'}, 'currency': 'EUR', 'capital': '羅馬', 'greeting': 'Ciao'},
    {'flag': '🇪🇸', 'names': {'zh': '西班牙', 'en': 'spain', 'ja': 'スペイン'}, 'currency': 'EUR', 'capital': '馬德里', 'greeting': 'Hola'},
    {'flag': '🇹🇼', 'names': {'zh': '台灣', 'en': 'taiwan', 'ja': '台湾'}, 'currency': 'TWD', 'capital': '台北', 'greeting': '你好'},
    {'flag': '🇨🇳', 'names': {'zh': '中國', 'en': 'china', 'ja': '中国'}, 'currency': 'CNY', 'capital': '北京', 'greeting': '你好'},
    {'flag': '🇹🇭', 'names': {'zh': '泰國', 'en': 'thailand', 'ja': 'タイ'}, 'currency': 'THB', 'capital': '曼谷', 'greeting': 'สวัสดี'},
    {'flag': '🇻🇳', 'names': {'zh': '越南', 'en': 'vietnam', 'ja': 'ベトナム'}, 'currency': 'VND', 'capital': '河內', 'greeting': 'Xin chào'},
    {'flag': '🇸🇬', 'names': {'zh': '新加坡', 'en': 'singapore', 'ja': 'シンガポール'}, 'currency': 'SGD', 'capital': '新加坡', 'greeting': 'Hello'},
    {'flag': '🇲🇾', 'names': {'zh': '馬來西亞', 'en': 'malaysia', 'ja': 'マレーシア'}, 'currency': 'MYR', 'capital': '吉隆坡', 'greeting': 'Selamat'},
    {'flag': '🇮🇩', 'names': {'zh': '印尼', 'en': 'indonesia', 'ja': 'インドネシア'}, 'currency': 'IDR', 'capital': '雅加達', 'greeting': 'Halo'},
    {'flag': '🇵🇭', 'names': {'zh': '菲律賓', 'en': 'philippines', 'ja': 'フィリピン'}, 'currency': 'PHP', 'capital': '馬尼拉', 'greeting': 'Kamusta'},
    {'flag': '🇮🇳', 'names': {'zh': '印度', 'en': 'india', 'ja': 'インド'}, 'currency': 'INR', 'capital': '新德里', 'greeting': 'नमस्ते'},
    {'flag': '🇦🇺', 'names': {'zh': '澳洲', 'en': 'australia', 'ja': 'オーストラリア'}, 'currency': 'AUD', 'capital': '坎培拉', 'greeting': "G'day"},
    {'flag': '🇳🇿', 'names': {'zh': '紐西蘭', 'en': 'new zealand', 'ja': 'ニュージーランド'}, 'currency': 'NZD', 'capital': '威靈頓', 'greeting': 'Kia ora'},
    {'flag': '🇨🇦', 'names': {'zh': '加拿大', 'en': 'canada', 'ja': 'カナダ'}, 'currency': 'CAD', 'capital': '渥太華', 'greeting': 'Hello'},
    {'flag': '🇲🇽', 'names': {'zh': '墨西哥', 'en': 'mexico', 'ja': 'メキシコ'}, 'currency': 'MXN', 'capital': '墨西哥城', 'greeting': 'Hola'},
    {'flag': '🇧🇷', 'names': {'zh': '巴西', 'en': 'brazil', 'ja': 'ブラジル'}, 'currency': 'BRL', 'capital': '巴西利亞', 'greeting': 'Olá'},
    {'flag': '🇷🇺', 'names': {'zh': '俄羅斯', 'en': 'russia', 'ja': 'ロシア'}, 'currency': 'RUB', 'capital': '莫斯科', 'greeting': 'Привет'},
    {'flag': '🇹🇷', 'names': {'zh': '土耳其', 'en': 'turkey', 'ja': 'トルコ'}, 'currency': 'TRY', 'capital': '安卡拉', 'greeting': 'Merhaba'},
    {'flag': '🇪🇬', 'names': {'zh': '埃及', 'en': 'egypt', 'ja': 'エジプト'}, 'currency': 'EGP', 'capital': '開羅', 'greeting': 'مرحبا'},
    {'flag': '🇿🇦', 'names': {'zh': '南非', 'en': 'south africa', 'ja': '南アフリカ'}, 'currency': 'ZAR', 'capital': '普利托利亞', 'greeting': 'Hallo'},
    {'flag': '🇳🇱', 'names': {'zh': '荷蘭', 'en': 'netherlands', 'ja': 'オランダ'}, 'currency': 'EUR', 'capital': '阿姆斯特丹', 'greeting': 'Hallo'},
    {'flag': '🇸🇪', 'names': {'zh': '瑞典', 'en': 'sweden', 'ja': 'スウェーデン'}, 'currency': 'SEK', 'capital': '斯德哥爾摩', 'greeting': 'Hej'},
    {'flag': '🇨🇭', 'names': {'zh': '瑞士', 'en': 'switzerland', 'ja': 'スイス'}, 'currency': 'CHF', 'capital': '伯恩', 'greeting': 'Grüezi'},
    {'flag': '🇵🇹', 'names': {'zh': '葡萄牙', 'en': 'portugal', 'ja': 'ポルトガル'}, 'currency': 'EUR', 'capital': '里斯本', 'greeting': 'Olá'},
]


def _match_answer(answer: str, country: dict) -> bool:
    """檢查答案是否正確（支援 zh/en/ja）"""
    answer_clean = answer.lower().strip()
    for lang_name in country['names'].values():
        if answer_clean == lang_name.lower():
            return True
    # 允許部分匹配（如 "美" 匹配 "美國"）
    zh_name = country['names']['zh']
    if len(answer_clean) >= 2 and answer_clean in zh_name:
        return True
    return False


class FlagQuizCog(commands.Cog, name='國旗猜謎'):
    """國旗猜謎遊戲"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._active_quizzes: set[int] = set()  # 正在進行測驗的頻道

    @app_commands.command(name='flagquiz', description='開始國旗猜謎遊戲（5 題）')
    async def slash_flagquiz(self, interaction: discord.Interaction):
        channel = interaction.channel

        if channel.id in self._active_quizzes:
            await interaction.response.send_message('⚠️ 此頻道已有猜謎進行中！', ephemeral=True)
            return

        self._active_quizzes.add(channel.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title='🏁 國旗猜謎開始！',
                description='共 **5** 題，每題 **30** 秒\n回答國家名稱（中文/英文/日文皆可）\n最先答對者得分！',
                color=config.COLOR_PRIMARY,
            )
        )

        questions = random.sample(COUNTRY_DATA, min(5, len(COUNTRY_DATA)))
        scores: dict[int, int] = {}  # user_id -> score

        try:
            for i, country in enumerate(questions, 1):
                embed = discord.Embed(
                    title=f'第 {i}/5 題',
                    description=f'\n{country["flag"]}\n\n這是哪個國家？',
                    color=config.COLOR_WARNING,
                )
                embed.set_footer(text='⏱️ 30 秒內回答！')
                await channel.send(embed=embed)

                def check(m):
                    return (
                        m.channel.id == channel.id
                        and not m.author.bot
                        and _match_answer(m.content, country)
                    )

                try:
                    msg = await self.bot.wait_for('message', check=check, timeout=30.0)
                    # 答對
                    winner = msg.author
                    scores[winner.id] = scores.get(winner.id, 0) + 1

                    result_embed = discord.Embed(
                        title=f'✅ {winner.display_name} 答對了！',
                        color=config.COLOR_SUCCESS,
                    )
                    result_embed.add_field(name='🏳️ 國家', value=f'{country["flag"]} **{country["names"]["zh"]}** ({country["names"]["en"].title()})', inline=False)
                    result_embed.add_field(name='🏛️ 首都', value=country['capital'], inline=True)
                    result_embed.add_field(name='💰 貨幣', value=country['currency'], inline=True)
                    result_embed.add_field(name='👋 打招呼', value=country['greeting'], inline=True)
                    await channel.send(embed=result_embed)

                    # 更新資料庫
                    if interaction.guild:
                        await db.update_quiz_score(winner.id, interaction.guild.id, correct=True)

                except asyncio.TimeoutError:
                    timeout_embed = discord.Embed(
                        title='⏰ 時間到！',
                        description=f'正確答案是 {country["flag"]} **{country["names"]["zh"]}** ({country["names"]["en"].title()})',
                        color=config.COLOR_ERROR,
                    )
                    await channel.send(embed=timeout_embed)

                # 題目間隔
                if i < 5:
                    await asyncio.sleep(2)

            # 結算
            final_embed = discord.Embed(
                title='🏆 猜謎結束！',
                color=config.COLOR_PRIMARY,
            )
            if scores:
                sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
                medal = ['🥇', '🥈', '🥉']
                lines = []
                for idx, (uid, sc) in enumerate(sorted_scores[:10]):
                    m = medal[idx] if idx < 3 else f'#{idx+1}'
                    user = self.bot.get_user(uid)
                    name = user.display_name if user else f'User#{uid}'
                    lines.append(f'{m} **{name}** — {sc} 分')
                final_embed.description = '\n'.join(lines)
            else:
                final_embed.description = '😅 沒有人答對任何題目...'

            await channel.send(embed=final_embed)

        finally:
            self._active_quizzes.discard(channel.id)

    @app_commands.command(name='quizrank', description='查看本伺服器的國旗猜謎排行榜')
    async def slash_quizrank(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message('❌ 此指令只能在伺服器中使用。', ephemeral=True)
            return

        rankings = await db.get_quiz_rankings(interaction.guild.id, limit=10)
        if not rankings:
            embed = discord.Embed(
                description='📭 目前沒有排行紀錄，快用 `/flagquiz` 開始第一場！',
                color=config.COLOR_WARNING,
            )
            await interaction.response.send_message(embed=embed)
            return

        embed = discord.Embed(
            title=f'🏆 {interaction.guild.name} — 國旗猜謎排行榜',
            color=config.COLOR_PRIMARY,
        )
        medal = ['🥇', '🥈', '🥉']
        lines = []
        for idx, r in enumerate(rankings):
            m = medal[idx] if idx < 3 else f'`#{idx+1}`'
            user = self.bot.get_user(r['user_id'])
            name = user.display_name if user else f'User#{r["user_id"]}'
            rate = (r['correct_count'] / r['total_count'] * 100) if r['total_count'] > 0 else 0
            lines.append(f'{m} **{name}** — ✅ {r["correct_count"]}/{r["total_count"]}（{rate:.0f}%）')

        embed.description = '\n'.join(lines)
        embed.set_footer(text=f'PongPong {config.BOT_VERSION}')
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(FlagQuizCog(bot))
