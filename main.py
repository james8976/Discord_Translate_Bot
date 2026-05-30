# -*- coding: utf-8 -*-
"""
PongPong Bot v2.0 — 主程式入口
載入所有 Cog 模組、初始化資料庫與快取、啟動 Bot
"""

import asyncio
import discord
from discord.ext import commands

import config
from config import setup_google_credentials
from utils.logger import get_logger
from utils.cache import TTLCache
from database import db as database
from web.keep_alive import keep_alive

logger = get_logger('main')

# ── 要載入的 Cog 列表 ──────────────────────────────────────
COG_EXTENSIONS = [
    'cogs.translate',
    'cogs.currency',
    'cogs.stock',
    'cogs.weather',
    'cogs.travel',
    'cogs.flagquiz',
    'cogs.daily_word',
    'cogs.fun',
]


async def main():
    # ── 初始化 Google 翻譯客戶端 ──────────────────────────
    translate_client = setup_google_credentials()
    if translate_client:
        logger.info('✅ Google Cloud Translation API 認證成功')
    else:
        logger.warning('⚠️ Google 翻譯服務不可用，翻譯功能將停用')

    # ── 設定 Discord Bot ──────────────────────────────────
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    intents.members = True

    bot = commands.Bot(
        command_prefix=config.BOT_PREFIX,
        intents=intents,
        help_command=None,
    )

    # ── 將共用資源掛載到 bot 實例 ─────────────────────────
    bot.translate_client = translate_client
    bot.cache = TTLCache(default_ttl=config.CACHE_EXPIRY_SECONDS)
    bot.version = config.BOT_VERSION

    # ── on_ready 事件 ─────────────────────────────────────
    @bot.event
    async def on_ready():
        logger.info(f'✅ 機器人已登入為: {bot.user} (ID: {bot.user.id})')
        logger.info(f'✅ 已連線到 {len(bot.guilds)} 個伺服器')

        # 初始化資料庫
        await database.init_db()

        # 設定 Bot 活動狀態
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f'/tr /cc /stock | {len(bot.guilds)} 個伺服器'
        )
        await bot.change_presence(activity=activity)

        # 同步 Slash Commands
        try:
            synced = await bot.tree.sync()
            logger.info(f'✅ 已同步 {len(synced)} 個斜線指令')
        except Exception as e:
            logger.error(f'❌ 同步指令失敗: {e}')

    # ── 全域錯誤處理 ──────────────────────────────────────
    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return  # 忽略未知指令
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send('❌ 你沒有執行此指令的權限。')
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f'⏳ 指令冷卻中，請 {error.retry_after:.1f} 秒後再試。')
        else:
            logger.error(f'指令錯誤: {error}', exc_info=True)
            await ctx.send('❌ 發生未預期的錯誤，請稍後再試。')

    @bot.tree.error
    async def on_app_command_error(interaction: discord.Interaction, error):
        logger.error(f'Slash 指令錯誤: {error}', exc_info=True)
        try:
            if interaction.response.is_done():
                await interaction.followup.send('❌ 發生錯誤，請稍後再試。', ephemeral=True)
            else:
                await interaction.response.send_message('❌ 發生錯誤，請稍後再試。', ephemeral=True)
        except Exception:
            pass

    # ── 載入所有 Cog ──────────────────────────────────────
    for ext in COG_EXTENSIONS:
        try:
            await bot.load_extension(ext)
            logger.info(f'  ✅ 已載入: {ext}')
        except Exception as e:
            logger.error(f'  ❌ 載入失敗 {ext}: {e}')

    # ── 啟動 Keep-Alive 伺服器 ────────────────────────────
    keep_alive(bot)
    logger.info('✅ Keep-Alive 伺服器已啟動 (port 8080)')

    # ── 啟動 Bot ──────────────────────────────────────────
    logger.info('🚀 正在啟動 PongPong Bot...')
    await bot.start(config.DISCORD_TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
