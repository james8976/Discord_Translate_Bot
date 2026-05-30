# -*- coding: utf-8 -*-
"""
PongPong Bot — 資料庫模組
使用 aiosqlite 提供非同步 SQLite 操作
"""

import os
import aiosqlite
from datetime import datetime
from utils.logger import get_logger

logger = get_logger('database')

# 資料庫路徑
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
DB_PATH = os.path.join(DB_DIR, 'pongpong.db')


async def init_db() -> None:
    """初始化資料庫：建立所有資料表"""
    os.makedirs(DB_DIR, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        # 使用者語言偏好
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                default_lang TEXT DEFAULT 'zh-TW',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 翻譯紀錄
        await db.execute('''
            CREATE TABLE IF NOT EXISTS translation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                source_lang TEXT,
                target_lang TEXT NOT NULL,
                source_text TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 測驗分數
        await db.execute('''
            CREATE TABLE IF NOT EXISTS quiz_scores (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                correct_count INTEGER DEFAULT 0,
                total_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        # 每日單字頻道
        await db.execute('''
            CREATE TABLE IF NOT EXISTS daily_word_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                send_hour INTEGER DEFAULT 8,
                is_active INTEGER DEFAULT 1
            )
        ''')
        await db.commit()
    logger.info(f'資料庫初始化完成：{DB_PATH}')


# ── 使用者語言偏好 ─────────────────────────────────────────

async def get_user_lang(user_id: int) -> str:
    """取得使用者預設語言，若無設定則回傳 zh-TW"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            'SELECT default_lang FROM user_preferences WHERE user_id = ?',
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 'zh-TW'


async def set_user_lang(user_id: int, lang: str) -> None:
    """設定使用者預設語言"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO user_preferences (user_id, default_lang)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET default_lang = excluded.default_lang
        ''', (user_id, lang))
        await db.commit()
    logger.debug(f'使用者 {user_id} 預設語言已設為 {lang}')


# ── 翻譯紀錄 ───────────────────────────────────────────────

async def add_translation_history(
    user_id: int,
    source_lang: str | None,
    target_lang: str,
    source_text: str,
    translated_text: str,
) -> None:
    """新增一筆翻譯紀錄"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO translation_history
                (user_id, source_lang, target_lang, source_text, translated_text)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, source_lang, target_lang, source_text, translated_text))
        await db.commit()


async def get_translation_history(user_id: int, limit: int = 5) -> list[dict]:
    """取得使用者最近的翻譯紀錄"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT source_lang, target_lang, source_text, translated_text, created_at
            FROM translation_history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        ''', (user_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ── 測驗分數 ───────────────────────────────────────────────

async def update_quiz_score(user_id: int, guild_id: int, correct: bool) -> None:
    """更新測驗分數"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO quiz_scores (user_id, guild_id, correct_count, total_count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                correct_count = correct_count + ?,
                total_count = total_count + 1
        ''', (user_id, guild_id, 1 if correct else 0, 1 if correct else 0))
        await db.commit()


async def get_quiz_rankings(guild_id: int, limit: int = 10) -> list[dict]:
    """取得伺服器測驗排行榜"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('''
            SELECT user_id, correct_count, total_count
            FROM quiz_scores
            WHERE guild_id = ?
            ORDER BY correct_count DESC, total_count ASC
            LIMIT ?
        ''', (guild_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


# ── 每日單字頻道 ───────────────────────────────────────────

async def set_daily_channel(guild_id: int, channel_id: int, send_hour: int = 8) -> None:
    """設定每日單字頻道"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT INTO daily_word_channels (guild_id, channel_id, send_hour, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                send_hour = excluded.send_hour,
                is_active = 1
        ''', (guild_id, channel_id, send_hour))
        await db.commit()
    logger.info(f'伺服器 {guild_id} 設定每日單字頻道 {channel_id}')


async def disable_daily_channel(guild_id: int) -> None:
    """停用每日單字"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            'UPDATE daily_word_channels SET is_active = 0 WHERE guild_id = ?',
            (guild_id,)
        )
        await db.commit()


async def get_daily_channels() -> list[dict]:
    """取得所有啟用中的每日單字頻道"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            'SELECT guild_id, channel_id, send_hour FROM daily_word_channels WHERE is_active = 1'
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
