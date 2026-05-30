# -*- coding: utf-8 -*-
"""
PongPong Bot — 翻譯 Cog
提供 /tr 斜線指令、!tr 前綴指令、國旗反應翻譯、/setlang、/history
"""

import html
import datetime
import discord
from discord import app_commands
from discord.ext import commands

import config
from database import db as database
from utils.logger import get_logger

logger = get_logger('translate')

# ── 語言名稱 ───────────────────────────────────────────────
LANG_NAMES = {
    'zh-TW': '繁體中文', 'zh-CN': '簡體中文', 'ja': '日本語',
    'en': 'English', 'ko': '한국어', 'es': 'Español',
    'fr': 'Français', 'de': 'Deutsch', 'vi': 'Tiếng Việt',
    'it': 'Italiano', 'ru': 'Русский', 'pt': 'Português',
    'ar': 'العربية', 'hi': 'हिन्दी', 'id': 'Indonesia',
    'nl': 'Nederlands', 'sv': 'Svenska', 'tr': 'Türkçe', 'pl': 'Polski',
    'th': 'ไทย',
}

# ── 語言選項（用於 autocomplete）──────────────────────────
LANG_CHOICES = [
    app_commands.Choice(name=f'{config.LANGUAGE_FLAGS.get(code, "")} {name} ({code})', value=code)
    for code, name in LANG_NAMES.items()
]


class TranslateCog(commands.Cog, name='翻譯'):
    """多語言翻譯功能"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _translate(self, text: str, target: str, source: str = None):
        """核心翻譯函式"""
        if not self.bot.translate_client:
            return None, '抱歉，翻譯服務 (Google API) 目前無法使用。'
        try:
            result = self.bot.translate_client.translate(
                text, target_language=target, source_language=source
            )
            translated = html.unescape(result['translatedText'])
            detected_source = result.get('detectedSourceLanguage', source or '?')
            return {'text': translated, 'source': detected_source}, None
        except Exception as e:
            logger.error(f'翻譯錯誤: {e}')
            return None, f'翻譯錯誤：{e}'

    def _make_embed(self, original: str, translated: str, source_lang: str, target_lang: str):
        """建立翻譯結果 Embed"""
        src_flag = config.LANGUAGE_FLAGS.get(source_lang, '🌐')
        tgt_flag = config.LANGUAGE_FLAGS.get(target_lang, '🌐')
        src_name = LANG_NAMES.get(source_lang, source_lang)
        tgt_name = LANG_NAMES.get(target_lang, target_lang)

        embed = discord.Embed(
            title='🌐 翻譯結果',
            color=config.COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name='📝 原文', value=f'```{original[:1000]}```', inline=False)
        embed.add_field(name='📤 譯文', value=f'```{translated[:1000]}```', inline=False)
        embed.set_footer(text=f'{src_flag} {src_name} → {tgt_flag} {tgt_name}')
        return embed

    # ── Slash Command: /tr ────────────────────────────────
    @app_commands.command(name='tr', description='翻譯文字到指定語言')
    @app_commands.describe(
        target_lang='目標語言',
        text='要翻譯的文字'
    )
    @app_commands.choices(target_lang=LANG_CHOICES[:25])
    async def slash_tr(self, interaction: discord.Interaction, target_lang: str, text: str):
        await interaction.response.defer()

        result, err = await self._translate(text, target_lang)
        if err:
            await interaction.followup.send(f'❌ {err}')
            return

        embed = self._make_embed(text, result['text'], result['source'], target_lang)
        await interaction.followup.send(embed=embed)

        # 儲存翻譯紀錄
        try:
            await database.add_translation_history(
                interaction.user.id, result['source'], target_lang, text, result['text']
            )
        except Exception as e:
            logger.error(f'儲存翻譯紀錄失敗: {e}')

        logger.info(f'[/tr] {interaction.user} 翻譯 "{text[:30]}..." → {target_lang}')

    # ── Prefix Command: !tr ──────────────────────────────
    @commands.command(name='tr', help='翻譯文字。格式: !tr [來源-目標] 文字')
    async def prefix_tr(self, ctx: commands.Context, *args):
        if not args:
            await ctx.send('❌ 用法: `!tr [語言代碼] 文字` 或 `!tr [來源-目標] 文字`')
            return

        src, tgt, text_list = None, None, list(args)

        # 解析 !tr en-jp hello world 或 !tr hello world
        if '-' in args[0] and not args[0].startswith('-'):
            parts = args[0].split('-')
            if len(parts) == 2:
                s = config.normalize_lang_code(parts[0])
                t = config.normalize_lang_code(parts[1])
                if s and t:
                    src, tgt = s, t
                    text_list = args[1:]

        if not tgt:
            tgt = await database.get_user_lang(ctx.author.id)

        if not text_list:
            await ctx.send('❌ 請提供要翻譯的文字。')
            return

        text = ' '.join(text_list)
        result, err = await self._translate(text, tgt, src)

        if err:
            await ctx.send(f'❌ {err}')
            return

        embed = self._make_embed(text, result['text'], result['source'], tgt)
        ref = ctx.message.reference
        await ctx.send(embed=embed, reference=ref, mention_author=False)

        try:
            await database.add_translation_history(
                ctx.author.id, result['source'], tgt, text, result['text']
            )
        except Exception as e:
            logger.error(f'儲存翻譯紀錄失敗: {e}')

    # ── 國旗 Emoji 反應翻譯 ──────────────────────────────
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        emoji = payload.emoji.name
        if emoji not in config.EMOJI_TO_LANGUAGE:
            return

        tgt = config.EMOJI_TO_LANGUAGE[emoji]

        try:
            channel = self.bot.get_channel(payload.channel_id)
            if not channel:
                return
            msg = await channel.fetch_message(payload.message_id)
            if not msg.content or msg.author.id == self.bot.user.id:
                return

            result, err = await self._translate(msg.content, tgt)
            if err:
                return

            embed = self._make_embed(msg.content, result['text'], result['source'], tgt)
            await channel.send(embed=embed, reference=msg, mention_author=False)
            logger.info(f'[reaction] {emoji} 翻譯 → {tgt}')
        except Exception as e:
            logger.error(f'反應翻譯錯誤: {e}')

    # ── Slash Command: /setlang ──────────────────────────
    @app_commands.command(name='setlang', description='設定您的預設翻譯目標語言')
    @app_commands.describe(lang='要設定的預設語言')
    @app_commands.choices(lang=LANG_CHOICES[:25])
    async def slash_setlang(self, interaction: discord.Interaction, lang: str):
        await database.set_user_lang(interaction.user.id, lang)
        flag = config.LANGUAGE_FLAGS.get(lang, '🌐')
        name = LANG_NAMES.get(lang, lang)

        embed = discord.Embed(
            title='✅ 預設語言已更新',
            description=f'您的預設翻譯目標語言已設為 {flag} **{name}**',
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ── Slash Command: /history ──────────────────────────
    @app_commands.command(name='history', description='查看您的翻譯紀錄')
    @app_commands.describe(count='顯示筆數（最多 20）')
    async def slash_history(self, interaction: discord.Interaction, count: int = 5):
        count = min(max(count, 1), 20)
        records = await database.get_translation_history(interaction.user.id, limit=count)

        if not records:
            await interaction.response.send_message('📭 您還沒有翻譯紀錄。', ephemeral=True)
            return

        embed = discord.Embed(
            title='📋 翻譯紀錄',
            description=f'最近 {len(records)} 筆翻譯',
            color=config.COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )

        for i, r in enumerate(records, 1):
            src_flag = config.LANGUAGE_FLAGS.get(r['source_lang'] or '', '🌐')
            tgt_flag = config.LANGUAGE_FLAGS.get(r['target_lang'], '🌐')
            src_text = r['source_text'][:50] + ('...' if len(r['source_text']) > 50 else '')
            tgt_text = r['translated_text'][:50] + ('...' if len(r['translated_text']) > 50 else '')
            embed.add_field(
                name=f'#{i} {src_flag} → {tgt_flag}',
                value=f'`{src_text}`\n→ `{tgt_text}`',
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TranslateCog(bot))
