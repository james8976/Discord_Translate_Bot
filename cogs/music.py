# -*- coding: utf-8 -*-
"""
PongPong Bot — 音樂播放模組 (music.py)
使用 yt-dlp + FFmpeg 在 Discord 語音頻道播放音樂
支援 YouTube / SoundCloud / Spotify URL 搜尋播放
"""

import asyncio
import random
import re
import time
from collections import deque
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils.logger import get_logger

logger = get_logger('music')

# ── yt-dlp 與 FFmpeg 設定 ─────────────────────────────────
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch5',
    'source_address': '0.0.0.0',
    'extract_flat': False,
    'nocheckcertificate': True,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn',
}

# 自動偵測 FFmpeg 路徑
import shutil
FFMPEG_PATH = shutil.which('ffmpeg') or '/usr/bin/ffmpeg'

# ── Spotify URL 正規表達式 ─────────────────────────────────
SPOTIFY_TRACK_RE = re.compile(r'open\.spotify\.com/track/([a-zA-Z0-9]+)')
SPOTIFY_PLAYLIST_RE = re.compile(r'open\.spotify\.com/playlist/([a-zA-Z0-9]+)')
SPOTIFY_ALBUM_RE = re.compile(r'open\.spotify\.com/album/([a-zA-Z0-9]+)')


# ── 歌曲資料類別 ───────────────────────────────────────────
class Song:
    """代表一首歌曲"""
    def __init__(self, title: str, url: str, stream_url: str,
                 duration: int, thumbnail: str, requester: discord.Member):
        self.title = title
        self.url = url
        self.stream_url = stream_url
        self.duration = duration  # 秒
        self.thumbnail = thumbnail
        self.requester = requester
        self.start_time: float = 0

    @property
    def duration_str(self) -> str:
        """格式化時長 mm:ss"""
        m, s = divmod(self.duration, 60)
        h, m = divmod(m, 60)
        if h:
            return f'{h}:{m:02d}:{s:02d}'
        return f'{m}:{s:02d}'


# ── 佇列管理 ───────────────────────────────────────────────
class MusicQueue:
    """每個伺服器的音樂佇列"""
    def __init__(self):
        self.queue: deque[Song] = deque()
        self.current: Optional[Song] = None
        self.loop_mode: str = 'off'  # off / single / all
        self.volume: float = 0.5

    def add(self, song: Song):
        self.queue.append(song)

    def next(self) -> Optional[Song]:
        if self.loop_mode == 'single' and self.current:
            return self.current
        if self.loop_mode == 'all' and self.current:
            self.queue.append(self.current)
        if self.queue:
            self.current = self.queue.popleft()
            return self.current
        self.current = None
        return None

    def shuffle(self):
        songs = list(self.queue)
        random.shuffle(songs)
        self.queue = deque(songs)

    def clear(self):
        self.queue.clear()
        self.current = None

    def remove(self, index: int) -> Optional[Song]:
        if 0 <= index < len(self.queue):
            songs = list(self.queue)
            removed = songs.pop(index)
            self.queue = deque(songs)
            return removed
        return None

    def __len__(self):
        return len(self.queue)


# ── 進度條生成 ──────────────────────────────────────────────
def make_progress_bar(current: float, total: float, length: int = 15) -> str:
    """生成音樂進度條"""
    if total <= 0:
        return '🔘' + '▬' * (length - 1)
    filled = int(length * current / total)
    filled = min(filled, length - 1)
    bar = '▬' * filled + '🔘' + '▬' * (length - filled - 1)
    return bar


def format_time(seconds: float) -> str:
    """格式化秒數為 mm:ss"""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'


# ══════════════════════════════════════════════════════════════
#  Music Cog
# ══════════════════════════════════════════════════════════════
class Music(commands.Cog, name='🎵 音樂'):
    """Discord 語音頻道音樂播放"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: dict[int, MusicQueue] = {}  # guild_id -> MusicQueue
        # 嘗試導入 spotipy（可選）
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            import config
            sp_id = getattr(config, 'SPOTIFY_CLIENT_ID', '')
            sp_secret = getattr(config, 'SPOTIFY_CLIENT_SECRET', '')
            if sp_id and sp_secret:
                self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                    client_id=sp_id, client_secret=sp_secret
                ))
                logger.info('✅ Spotify API 連線成功')
            else:
                self.sp = None
                logger.info('ℹ️ 未設定 Spotify API，Spotify URL 將使用標題搜尋')
        except ImportError:
            self.sp = None
            logger.info('ℹ️ spotipy 未安裝，Spotify URL 將使用標題搜尋')

    def get_queue(self, guild_id: int) -> MusicQueue:
        if guild_id not in self.queues:
            self.queues[guild_id] = MusicQueue()
        return self.queues[guild_id]

    # ── 搜尋歌曲 ───────────────────────────────────────────
    async def search_song(self, query: str, requester: discord.Member) -> Optional[Song]:
        """使用 yt-dlp 搜尋歌曲"""
        import yt_dlp
        loop = asyncio.get_running_loop()

        def _extract():
            with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                info = ydl.extract_info(query, download=False)
                if info is None:
                    return None
                if 'entries' in info:
                    entries = [e for e in info['entries'] if e]
                    if not entries:
                        return None
                    info = entries[0]
                return info

        try:
            info = await loop.run_in_executor(None, _extract)
            if not info:
                return None
            return Song(
                title=info.get('title', '未知歌曲'),
                url=info.get('webpage_url', ''),
                stream_url=info.get('url', ''),
                duration=info.get('duration', 0) or 0,
                thumbnail=info.get('thumbnail', ''),
                requester=requester,
            )
        except Exception as e:
            logger.error(f'搜尋歌曲失敗: {e}', exc_info=True)
            return None

    async def search_songs_list(self, query: str, requester: discord.Member, max_results: int = 5) -> list[Song]:
        """搜尋多首歌曲供選擇"""
        import yt_dlp
        loop = asyncio.get_event_loop()
        opts = {**YDL_OPTIONS, 'default_search': f'ytsearch{max_results}', 'extract_flat': True}

        def _extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(query, download=False)
                return info.get('entries', [])

        try:
            entries = await loop.run_in_executor(None, _extract)
            songs = []
            for e in entries[:max_results]:
                songs.append(Song(
                    title=e.get('title', '未知歌曲'),
                    url=e.get('url', e.get('webpage_url', '')),
                    stream_url='',  # 稍後獲取
                    duration=e.get('duration', 0) or 0,
                    thumbnail=e.get('thumbnail', ''),
                    requester=requester,
                ))
            return songs
        except Exception as e:
            logger.error(f'搜尋歌曲列表失敗: {e}')
            return []

    # ── Spotify URL 解析 ───────────────────────────────────
    async def resolve_spotify(self, url: str) -> list[str]:
        """解析 Spotify URL，回傳歌曲搜尋字串列表"""
        if not self.sp:
            # 從 URL 無法直接取得歌名，回傳空
            return []
        try:
            track_match = SPOTIFY_TRACK_RE.search(url)
            if track_match:
                track = self.sp.track(track_match.group(1))
                artist = track['artists'][0]['name']
                title = track['name']
                return [f'{artist} - {title}']

            playlist_match = SPOTIFY_PLAYLIST_RE.search(url)
            if playlist_match:
                results = []
                playlist = self.sp.playlist_tracks(playlist_match.group(1), limit=50)
                for item in playlist['items']:
                    t = item.get('track')
                    if t:
                        artist = t['artists'][0]['name']
                        title = t['name']
                        results.append(f'{artist} - {title}')
                return results

            album_match = SPOTIFY_ALBUM_RE.search(url)
            if album_match:
                results = []
                album = self.sp.album_tracks(album_match.group(1), limit=50)
                album_info = self.sp.album(album_match.group(1))
                for t in album['items']:
                    artist = t['artists'][0]['name']
                    title = t['name']
                    results.append(f'{artist} - {title}')
                return results
        except Exception as e:
            logger.error(f'Spotify 解析失敗: {e}')
        return []

    # ── 播放下一首 ──────────────────────────────────────────
    def play_next(self, guild: discord.Guild):
        """播放佇列中的下一首歌"""
        queue = self.get_queue(guild.id)
        song = queue.next()

        if song and guild.voice_client:
            def after_playing(error):
                if error:
                    logger.error(f'播放錯誤: {error}')
                # 使用 bot loop 來排程下一首
                asyncio.run_coroutine_threadsafe(
                    self._play_next_async(guild), self.bot.loop
                )

            try:
                source = discord.FFmpegPCMAudio(
                    song.stream_url,
                    executable=FFMPEG_PATH,
                    **FFMPEG_OPTIONS
                )
                source = discord.PCMVolumeTransformer(source, volume=queue.volume)
                guild.voice_client.play(source, after=after_playing)
                song.start_time = time.time()
            except Exception as e:
                logger.error(f'播放失敗: {e}')

    async def _play_next_async(self, guild: discord.Guild):
        """非同步版本的播放下一首"""
        queue = self.get_queue(guild.id)
        song = queue.next()

        if song and guild.voice_client:
            # 需要重新獲取串流 URL（可能過期）
            refreshed = await self.search_song(song.title, song.requester)
            if refreshed:
                song.stream_url = refreshed.stream_url

            def after_playing(error):
                if error:
                    logger.error(f'播放錯誤: {error}')
                asyncio.run_coroutine_threadsafe(
                    self._play_next_async(guild), self.bot.loop
                )

            try:
                source = discord.FFmpegPCMAudio(
                    song.stream_url,
                    executable=FFMPEG_PATH,
                    **FFMPEG_OPTIONS
                )
                source = discord.PCMVolumeTransformer(source, volume=queue.volume)
                guild.voice_client.play(source, after=after_playing)
                song.start_time = time.time()

                # 發送正在播放通知
                embed = self._now_playing_embed(song, queue)
                # 找到最後使用的文字頻道
                for ch in guild.text_channels:
                    if ch.permissions_for(guild.me).send_messages:
                        await ch.send(embed=embed)
                        break
            except Exception as e:
                logger.error(f'播放失敗: {e}')
        elif guild.voice_client:
            # 佇列空了，等待 5 分鐘後自動離開
            await asyncio.sleep(300)
            if guild.voice_client and not guild.voice_client.is_playing():
                await guild.voice_client.disconnect()
                if guild.id in self.queues:
                    del self.queues[guild.id]

    # ── 建立「正在播放」Embed ──────────────────────────────
    def _now_playing_embed(self, song: Song, queue: MusicQueue) -> discord.Embed:
        elapsed = time.time() - song.start_time if song.start_time else 0
        progress = make_progress_bar(elapsed, song.duration)
        time_str = f'{format_time(elapsed)} / {song.duration_str}'

        loop_icons = {'off': '➡️', 'single': '🔂', 'all': '🔁'}
        loop_text = loop_icons.get(queue.loop_mode, '➡️')

        embed = discord.Embed(
            title='🎵 正在播放',
            description=f'**[{song.title}]({song.url})**',
            color=0x1DB954,  # Spotify 綠
        )
        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
        embed.add_field(
            name='進度',
            value=f'{progress}\n`{time_str}`',
            inline=False,
        )
        vol_pct = int(queue.volume * 100)
        embed.add_field(name='🔊 音量', value=f'{vol_pct}%', inline=True)
        embed.add_field(name='📋 佇列', value=f'{len(queue)} 首', inline=True)
        embed.add_field(name='循環', value=loop_text, inline=True)
        embed.set_footer(text=f'由 {song.requester.display_name} 點播', icon_url=song.requester.display_avatar.url)
        return embed

    # ══════════════════════════════════════════════════════════
    #  Slash Commands
    # ══════════════════════════════════════════════════════════

    @app_commands.command(name='play', description='🎵 播放音樂 — 輸入歌名、YouTube 或 Spotify URL')
    @app_commands.describe(query='歌曲名稱、YouTube URL 或 Spotify URL')
    async def play(self, interaction: discord.Interaction, query: str):
        # 檢查使用者是否在語音頻道
        if not interaction.user.voice:
            return await interaction.response.send_message(
                '❌ 請先加入一個語音頻道！', ephemeral=True
            )

        voice_channel = interaction.user.voice.channel
        await interaction.response.defer(thinking=True)

        # 連接語音頻道
        vc = interaction.guild.voice_client
        if not vc:
            vc = await voice_channel.connect()
        elif vc.channel != voice_channel:
            await vc.move_to(voice_channel)

        queue = self.get_queue(interaction.guild.id)

        # 檢查是否為 Spotify URL
        is_spotify = 'open.spotify.com' in query
        if is_spotify:
            search_queries = await self.resolve_spotify(query)
            if not search_queries:
                return await interaction.followup.send('❌ 無法解析 Spotify 連結。請確認連結是否正確。')

            # 多首歌（播放清單/專輯）
            if len(search_queries) > 1:
                added = 0
                embed = discord.Embed(
                    title='📋 正在載入 Spotify 播放清單...',
                    description=f'共 {len(search_queries)} 首歌曲',
                    color=0x1DB954,
                )
                msg = await interaction.followup.send(embed=embed)

                for sq in search_queries:
                    song = await self.search_song(sq, interaction.user)
                    if song:
                        queue.add(song)
                        added += 1

                embed = discord.Embed(
                    title='✅ Spotify 播放清單已載入',
                    description=f'成功加入 **{added}** / {len(search_queries)} 首歌曲到佇列',
                    color=0x1DB954,
                )
                await msg.edit(embed=embed)

                if not vc.is_playing():
                    self.play_next(interaction.guild)
                return

            query = search_queries[0]

        # 單首歌搜尋
        song = await self.search_song(query, interaction.user)
        if not song:
            return await interaction.followup.send('❌ 找不到歌曲，請嘗試其他關鍵字。')

        if vc.is_playing() or vc.is_paused():
            # 加入佇列
            queue.add(song)
            embed = discord.Embed(
                title='📋 已加入佇列',
                description=f'**[{song.title}]({song.url})**\n⏱️ 時長: `{song.duration_str}`',
                color=0x5865F2,
            )
            embed.add_field(name='📋 佇列位置', value=f'第 {len(queue)} 首', inline=True)
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            embed.set_footer(text=f'由 {interaction.user.display_name} 點播', icon_url=interaction.user.display_avatar.url)
            await interaction.followup.send(embed=embed)
        else:
            # 直接播放
            queue.current = song
            try:
                source = discord.FFmpegPCMAudio(song.stream_url, executable=FFMPEG_PATH, **FFMPEG_OPTIONS)
                source = discord.PCMVolumeTransformer(source, volume=queue.volume)

                def after_playing(error):
                    if error:
                        logger.error(f'播放錯誤: {error}')
                    asyncio.run_coroutine_threadsafe(
                        self._play_next_async(interaction.guild), self.bot.loop
                    )

                vc.play(source, after=after_playing)
                song.start_time = time.time()

                embed = self._now_playing_embed(song, queue)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                logger.error(f'播放失敗: {e}')
                await interaction.followup.send(f'❌ 播放失敗: {str(e)[:100]}')

    @app_commands.command(name='pause', description='⏸️ 暫停音樂')
    async def pause(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message('⏸️ 已暫停播放')
        else:
            await interaction.response.send_message('❌ 目前沒有正在播放的音樂', ephemeral=True)

    @app_commands.command(name='resume', description='▶️ 繼續播放音樂')
    async def resume(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message('▶️ 繼續播放')
        else:
            await interaction.response.send_message('❌ 音樂並未暫停', ephemeral=True)

    @app_commands.command(name='skip', description='⏭️ 跳過目前歌曲')
    async def skip(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc and (vc.is_playing() or vc.is_paused()):
            queue = self.get_queue(interaction.guild.id)
            current = queue.current
            vc.stop()  # 會觸發 after callback → 播放下一首
            title = current.title if current else '目前歌曲'
            await interaction.response.send_message(f'⏭️ 已跳過 **{title}**')
        else:
            await interaction.response.send_message('❌ 目前沒有正在播放的音樂', ephemeral=True)

    @app_commands.command(name='stop', description='⏹️ 停止播放並離開語音頻道')
    async def stop(self, interaction: discord.Interaction):
        vc = interaction.guild.voice_client
        if vc:
            queue = self.get_queue(interaction.guild.id)
            queue.clear()
            queue.loop_mode = 'off'
            vc.stop()
            await vc.disconnect()
            if interaction.guild.id in self.queues:
                del self.queues[interaction.guild.id]
            await interaction.response.send_message('⏹️ 已停止播放並離開語音頻道')
        else:
            await interaction.response.send_message('❌ 機器人不在任何語音頻道中', ephemeral=True)

    @app_commands.command(name='queue', description='📋 查看播放佇列')
    async def queue_cmd(self, interaction: discord.Interaction):
        queue = self.get_queue(interaction.guild.id)

        if not queue.current and len(queue) == 0:
            return await interaction.response.send_message('📋 佇列是空的', ephemeral=True)

        embed = discord.Embed(title='📋 播放佇列', color=0x5865F2)

        # 正在播放
        if queue.current:
            elapsed = time.time() - queue.current.start_time if queue.current.start_time else 0
            progress = make_progress_bar(elapsed, queue.current.duration, 12)
            embed.add_field(
                name='🎵 正在播放',
                value=f'**{queue.current.title}**\n{progress} `{format_time(elapsed)}/{queue.current.duration_str}`',
                inline=False,
            )

        # 佇列列表（最多顯示 10 首）
        if queue.queue:
            lines = []
            for i, song in enumerate(list(queue.queue)[:10]):
                lines.append(f'`{i+1}.` **{song.title}** — `{song.duration_str}`')
            if len(queue) > 10:
                lines.append(f'... 還有 {len(queue) - 10} 首')
            embed.add_field(name=f'接下來 ({len(queue)} 首)', value='\n'.join(lines), inline=False)

        loop_icons = {'off': '➡️ 不循環', 'single': '🔂 單曲循環', 'all': '🔁 全部循環'}
        embed.set_footer(text=f'循環: {loop_icons[queue.loop_mode]} | 音量: {int(queue.volume*100)}%')
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='np', description='🎵 顯示正在播放的歌曲')
    async def now_playing(self, interaction: discord.Interaction):
        queue = self.get_queue(interaction.guild.id)
        if not queue.current:
            return await interaction.response.send_message('❌ 目前沒有正在播放的音樂', ephemeral=True)

        embed = self._now_playing_embed(queue.current, queue)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='volume', description='🔊 調整音量 (0-100)')
    @app_commands.describe(level='音量大小 (0-100)')
    async def volume(self, interaction: discord.Interaction, level: int):
        if level < 0 or level > 100:
            return await interaction.response.send_message('❌ 音量範圍為 0-100', ephemeral=True)

        queue = self.get_queue(interaction.guild.id)
        queue.volume = level / 100

        vc = interaction.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = queue.volume

        # 音量圖示
        if level == 0:
            icon = '🔇'
        elif level < 30:
            icon = '🔈'
        elif level < 70:
            icon = '🔉'
        else:
            icon = '🔊'

        await interaction.response.send_message(f'{icon} 音量已設為 **{level}%**')

    @app_commands.command(name='shuffle', description='🔀 隨機排列佇列')
    async def shuffle(self, interaction: discord.Interaction):
        queue = self.get_queue(interaction.guild.id)
        if len(queue) < 2:
            return await interaction.response.send_message('❌ 佇列歌曲不足，無法隨機排列', ephemeral=True)
        queue.shuffle()
        await interaction.response.send_message(f'🔀 已隨機排列 **{len(queue)}** 首歌曲')

    @app_commands.command(name='loop', description='🔁 切換循環模式 (關閉/單曲/全部)')
    async def loop(self, interaction: discord.Interaction):
        queue = self.get_queue(interaction.guild.id)
        modes = ['off', 'single', 'all']
        names = {'off': '➡️ 關閉循環', 'single': '🔂 單曲循環', 'all': '🔁 全部循環'}
        current_idx = modes.index(queue.loop_mode)
        queue.loop_mode = modes[(current_idx + 1) % 3]
        await interaction.response.send_message(f'已切換為: {names[queue.loop_mode]}')

    @app_commands.command(name='remove', description='🗑️ 從佇列中移除指定歌曲')
    @app_commands.describe(position='要移除的歌曲編號（從 1 開始）')
    async def remove(self, interaction: discord.Interaction, position: int):
        queue = self.get_queue(interaction.guild.id)
        removed = queue.remove(position - 1)
        if removed:
            await interaction.response.send_message(f'🗑️ 已移除: **{removed.title}**')
        else:
            await interaction.response.send_message(f'❌ 找不到編號 {position} 的歌曲', ephemeral=True)

    @app_commands.command(name='seek', description='⏩ 跳轉到指定時間（秒）')
    @app_commands.describe(seconds='要跳轉到的秒數')
    async def seek(self, interaction: discord.Interaction, seconds: int):
        vc = interaction.guild.voice_client
        queue = self.get_queue(interaction.guild.id)
        if not vc or not queue.current:
            return await interaction.response.send_message('❌ 目前沒有正在播放的音樂', ephemeral=True)

        song = queue.current
        if seconds < 0 or seconds > song.duration:
            return await interaction.response.send_message(
                f'❌ 時間範圍為 0 - {song.duration} 秒', ephemeral=True
            )

        # 重新播放，從指定時間開始
        vc.stop()
        ffmpeg_opts = {
            'before_options': f'-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -ss {seconds}',
            'options': '-vn',
        }

        def after_playing(error):
            if error:
                logger.error(f'播放錯誤: {error}')
            asyncio.run_coroutine_threadsafe(
                self._play_next_async(interaction.guild), self.bot.loop
            )

        try:
            source = discord.FFmpegPCMAudio(song.stream_url, executable=FFMPEG_PATH, **ffmpeg_opts)
            source = discord.PCMVolumeTransformer(source, volume=queue.volume)
            vc.play(source, after=after_playing)
            song.start_time = time.time() - seconds
            await interaction.response.send_message(f'⏩ 已跳轉到 `{format_time(seconds)}`')
        except Exception as e:
            await interaction.response.send_message(f'❌ 跳轉失敗: {str(e)[:100]}', ephemeral=True)

    # ── Cog 卸載時清理 ─────────────────────────────────────
    def cog_unload(self):
        for guild_id in list(self.queues.keys()):
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                asyncio.run_coroutine_threadsafe(
                    guild.voice_client.disconnect(), self.bot.loop
                )
        self.queues.clear()


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
