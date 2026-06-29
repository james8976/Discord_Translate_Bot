# -*- coding: utf-8 -*-
"""
PongPong Bot — Spotify Connect 模組 (spotify_connect.py)
使用 librespot 作為 Spotify Connect 接收器
讓 Discord 語音頻道變成 Spotify 音響

v2.2 — 多用戶 OAuth 支援：
  任何 Discord 使用者都能登入自己的 Spotify 帳號
  → 點擊連結 → 瀏覽器授權 → 自動連接

原理：
  手機 Spotify App → 選擇裝置 "PongPong Radio {伺服器名}"
  → librespot 接收 Spotify 原始音源 (44.1kHz S16 PCM)
  → FFmpeg 轉為 48kHz → Discord 語音頻道播放
"""

import asyncio
import base64
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
from typing import Optional

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import config
from utils.logger import get_logger
from web.keep_alive import get_pending_token

logger = get_logger('spotify_connect')

# ── 路徑設定 ───────────────────────────────────────────────
LIBRESPOT_PATH = os.environ.get(
    'LIBRESPOT_PATH',
    os.path.expanduser('~/.cargo/bin/librespot')
)
FFMPEG_PATH = '/usr/bin/ffmpeg'
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'spotify_cache')

# Spotify Track URI regex
SPOTIFY_URI_RE = re.compile(r'spotify:track:([A-Za-z0-9]{22})')

# OAuth 等待超時（秒）
OAUTH_TIMEOUT = 120



# ── Spotify Connect Session ────────────────────────────────
class SpotifySession:
    """管理單一伺服器的 Spotify Connect 會話"""

    def __init__(self):
        self.librespot_proc: Optional[subprocess.Popen] = None
        self.ffmpeg_proc: Optional[subprocess.Popen] = None
        self.text_channel: Optional[discord.TextChannel] = None
        self.is_active: bool = False
        self.is_authenticating: bool = False  # 正在等待 OAuth
        self.monitor_thread: Optional[threading.Thread] = None

        # 使用者資訊
        self.connected_user_name: Optional[str] = None  # Spotify 顯示名稱
        self.connected_discord_user: Optional[str] = None  # Discord 使用者名稱
        self.device_name: str = 'PongPong Radio'
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None

        # 曲目資訊
        self.current_track_id: Optional[str] = None
        self.track_start_time: Optional[float] = None
        self.now_playing_msg: Optional[discord.Message] = None
        self.track_duration_sec: int = 0
        self.track_name: Optional[str] = None
        self.track_artists: Optional[str] = None
        self.track_album: Optional[str] = None
        self.track_album_art: Optional[str] = None
        self.track_url: Optional[str] = None
        self.np_update_task: Optional[asyncio.Task] = None

    def cleanup(self):
        """清理所有子程序"""
        self.is_active = False
        self.is_authenticating = False
        for proc in [self.ffmpeg_proc, self.librespot_proc]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self.librespot_proc = None
        self.ffmpeg_proc = None
        self.current_track_id = None
        self.track_start_time = None
        self.track_duration_sec = 0
        self.track_name = None
        self.track_artists = None
        self.track_album = None
        self.track_album_art = None
        self.track_url = None
        self.access_token = None
        if self.np_update_task and not self.np_update_task.done():
            self.np_update_task.cancel()
        self.np_update_task = None


# ══════════════════════════════════════════════════════════════
#  Spotify Connect Cog
# ══════════════════════════════════════════════════════════════
class SpotifyConnect(commands.Cog, name='📡 Spotify Connect'):
    """Spotify Connect — 讓 Discord 語音頻道變成 Spotify 音響"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sessions: dict[int, SpotifySession] = {}
        self.sp = None  # spotipy 客戶端（用於歌曲資訊查詢）
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._init_spotipy()

    def _init_spotipy(self):
        """初始化 Spotify Web API 客戶端（查詢歌曲資訊用）"""
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            sp_id = config.SPOTIFY_CLIENT_ID
            sp_secret = config.SPOTIFY_CLIENT_SECRET
            if sp_id and sp_secret:
                self.sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
                    client_id=sp_id, client_secret=sp_secret
                ))
                logger.info('Spotify Web API 客戶端已初始化')
            else:
                logger.warning('Spotify Client ID/Secret 未設定')
        except ImportError:
            logger.warning('spotipy 未安裝，Now Playing 將使用簡化顯示')
        except Exception as e:
            logger.error(f'spotipy 初始化失敗: {e}')

    def get_session(self, guild_id: int) -> SpotifySession:
        if guild_id not in self.sessions:
            self.sessions[guild_id] = SpotifySession()
        return self.sessions[guild_id]

    # ── 指令群組 ───────────────────────────────────────────
    spotify = app_commands.Group(
        name='spotify',
        description='🎧 Spotify Connect — 把語音頻道變成 Spotify 音響',
    )

    # ────────────────────────────────────────────────────────
    #  /spotify connect — 登入 Spotify + 啟動 Connect
    # ────────────────────────────────────────────────────────
    @spotify.command(
        name='connect',
        description='📡 登入你的 Spotify 帳號並啟動音響',
    )
    async def connect(self, interaction: discord.Interaction):
        # 檢查語音頻道
        if not interaction.user.voice:
            return await interaction.response.send_message(
                '❌ 請先加入一個語音頻道！', ephemeral=True
            )

        voice_channel = interaction.user.voice.channel
        session = self.get_session(interaction.guild.id)

        # 檢查是否已在運行
        if session.is_active:
            return await interaction.response.send_message(
                f'⚠️ Spotify Connect 已在使用中！\n'
                f'👤 目前連接者：**{session.connected_discord_user or "未知"}**\n'
                f'使用 `/spotify disconnect` 先停止。',
                ephemeral=True,
            )

        # 檢查是否有人正在認證
        if session.is_authenticating:
            return await interaction.response.send_message(
                '⏳ 有人正在進行 Spotify 認證，請稍候...', ephemeral=True
            )

        # 檢查 librespot
        if not os.path.isfile(LIBRESPOT_PATH):
            return await interaction.response.send_message(
                '❌ 伺服器尚未安裝 librespot。', ephemeral=True
            )

        # 檢查 Spotify App 設定
        if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
            return await interaction.response.send_message(
                '❌ Spotify App 未設定。請聯繫管理員。', ephemeral=True
            )

        await interaction.response.defer(thinking=True)

        session.is_authenticating = True
        session.connected_discord_user = interaction.user.display_name

        try:
            # 產生 OAuth state
            state = f"{interaction.guild.id}:{interaction.user.id}:{secrets.token_hex(8)}"
            oauth_url = self._build_oauth_url(state)

            # 發送登入連結
            embed = discord.Embed(
                title='🔗 登入 Spotify',
                description=(
                    '點擊下方按鈕登入你的 **Spotify 帳號**\n'
                    '授權後音響會自動啟動！\n\n'
                    f'⏱️ 請在 **{OAUTH_TIMEOUT} 秒**內完成登入'
                ),
                color=0x1DB954,
            )
            embed.set_footer(text='🔒 你的密碼不會被記錄，僅使用 OAuth 安全授權')

            view = discord.ui.View(timeout=OAUTH_TIMEOUT)
            view.add_item(discord.ui.Button(
                label='🎵 登入 Spotify',
                url=oauth_url,
                style=discord.ButtonStyle.link,
            ))

            login_msg = await interaction.followup.send(embed=embed, view=view)

            # 等待 Flask 回呼收到 token
            token_data = None
            for _ in range(OAUTH_TIMEOUT // 2):  # 每 2 秒檢查一次
                await asyncio.sleep(2)
                token_data = get_pending_token(state)
                if token_data:
                    break

            if not token_data:
                session.is_authenticating = False
                session.connected_discord_user = None
                await interaction.followup.send(
                    '❌ 登入逾時！請重新使用 `/spotify connect`'
                )
                # 清理登入訊息
                try:
                    await login_msg.delete()
                except Exception:
                    pass
                return

            # 取得使用者資訊
            access_token = token_data['access_token']
            refresh_token = token_data.get('refresh_token')
            session.access_token = access_token
            session.refresh_token = refresh_token

            spotify_user = await self._get_spotify_user(access_token)
            display_name = spotify_user.get('display_name') or spotify_user.get('id', '未知')
            session.connected_user_name = display_name

            # ── Premium 檢查（librespot 只支援 Premium）──────
            product = spotify_user.get('product', 'free')
            if product != 'premium':
                session.is_authenticating = False
                session.connected_discord_user = None
                await interaction.followup.send(
                    f'❌ **抱歉，{display_name}**\n\n'
                    '🚫 Spotify Connect (librespot) 僅支援 **Spotify Premium** 帳號。\n'
                    '這是 librespot 官方限制，免費帳號無法使用。\n\n'
                    f'💡 你的方案：`{product}`'
                )
                try:
                    await login_msg.delete()
                except Exception:
                    pass
                return

            # 清理登入訊息
            try:
                await login_msg.delete()
            except Exception:
                pass

            # 加入語音頻道
            vc = interaction.guild.voice_client
            if not vc:
                vc = await voice_channel.connect()
            elif vc.channel != voice_channel:
                await vc.move_to(voice_channel)

            # 設定裝置名稱（含伺服器名）
            guild_name = interaction.guild.name[:20]  # 限制長度
            device_name = f'PongPong Radio {guild_name}'
            session.device_name = device_name

            # ── 準備 librespot credentials ─────────────────────
            # librespot CLI 不接受 --access-token 參數
            # 正確做法：把 OAuth access_token 寫入 credentials.json
            # 使用 AUTHENTICATION_SPOTIFY_TOKEN (auth_type=3) 格式
            import shutil
            cache_path = os.path.join(CACHE_DIR, f'guild_{interaction.guild.id}')
            os.makedirs(cache_path, exist_ok=True)

            # 取得 Spotify user ID（librespot credentials 需要 username）
            spotify_username = spotify_user.get('id', 'unknown')

            # 寫入 credentials.json
            # auth_type 對應 librespot AuthenticationType protobuf enum:
            #   0 = AUTHENTICATION_USER_PASS
            #   1 = AUTHENTICATION_STORED_SPOTIFY_CREDENTIALS (Zeroconf blob)
            #   3 = AUTHENTICATION_SPOTIFY_TOKEN (OAuth access token) ← 我們用這個
            creds = {
                'username': spotify_username,
                'auth_type': 3,
                'auth_data': base64.b64encode(access_token.encode('utf-8')).decode('utf-8'),
            }
            creds_file = os.path.join(cache_path, 'credentials.json')
            with open(creds_file, 'w') as f:
                json.dump(creds, f)
            logger.info(f'已寫入 librespot credentials (user={spotify_username}, type=SPOTIFY_TOKEN)')

            # ── 啟動 librespot → FFmpeg pipeline ──────────────
            librespot_cmd = [
                LIBRESPOT_PATH,
                '--name', device_name,
                '--backend', 'pipe',
                '--format', 'S16',
                '--bitrate', '320',
                '--initial-volume', '100',
                '--device-type', 'speaker',
                '--enable-volume-normalisation',
                '--disable-discovery',
                '--cache', cache_path,          # ★ 指向含 credentials.json 的目錄
            ]

            logger.info(f'啟動 librespot: {" ".join(librespot_cmd)}')

            session.librespot_proc = subprocess.Popen(
                librespot_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # 等待 librespot 初始化（給 3 秒，認證需要時間）
            await asyncio.sleep(3)
            if session.librespot_proc.poll() is not None:
                # librespot 已退出，讀取 stderr 查看錯誤
                stderr_out = session.librespot_proc.stderr.read().decode('utf-8', errors='ignore')
                logger.error(f'librespot 啟動失敗: {stderr_out}')
                session.cleanup()
                await interaction.followup.send(
                    f'❌ librespot 啟動失敗：\n```\n{stderr_out[:800]}\n```'
                )
                return

            # FFmpeg: -re 強制實時讀取 + aresample=async 做時鐘漂移補償
            # 這是 librespot pipe backend 的著名 bug (issue #340) 的修復方案
            ffmpeg_cmd = [
                FFMPEG_PATH,
                '-re',                     # ★ 強制實時速率讀取（時鐘主宰）
                '-f', 's16le',
                '-ar', '44100',
                '-ac', '2',
                '-i', 'pipe:0',
                '-af', 'aresample=async=1000:first_pts=0',  # ★ 時鐘漂移補償
                '-f', 's16le',
                '-ar', '48000',
                '-ac', '2',
                '-loglevel', 'warning',
                'pipe:1',
            ]

            session.ffmpeg_proc = subprocess.Popen(
                ffmpeg_cmd,
                stdin=session.librespot_proc.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

            # 注意：不做 drain！
            # librespot 剛啟動時還沒有人播音樂，FFmpeg 沒有資料輸出。
            # stdout.read() 會無限期阻塞（已知 bug — 之前卡了 23.8 秒甚至永久卡住）。
            # FFmpeg 的 -re 已經強制實時速率讀取，不需要手動 drain。

            source = discord.PCMAudio(session.ffmpeg_proc.stdout)
            source = discord.PCMVolumeTransformer(source, volume=1.0)

            def after_callback(error):
                if error:
                    logger.error(f'Spotify Connect 播放錯誤: {error}')
                else:
                    logger.info('Spotify Connect 音頻源結束（可能是 librespot 閒置或暫停）')
                # 檢查 librespot 是否真的退出了
                if session.librespot_proc and session.librespot_proc.poll() is not None:
                    # librespot 已退出，讀取 stderr
                    exit_code = session.librespot_proc.returncode
                    try:
                        stderr_out = session.librespot_proc.stderr.read().decode('utf-8', errors='ignore')[:500]
                    except Exception:
                        stderr_out = '(無法讀取)'
                    logger.error(f'librespot 已退出 (exit_code={exit_code}): {stderr_out}')
                    asyncio.run_coroutine_threadsafe(
                        self._auto_cleanup(interaction.guild),
                        self.bot.loop,
                    )
                else:
                    # librespot 還在運行，只是沒有音頻資料（閒置狀態）
                    # 重新換一個 source 繼續讀取
                    logger.info('librespot 仍在運行，重新掛載音頻源...')
                    try:
                        new_source = discord.PCMAudio(session.ffmpeg_proc.stdout)
                        new_source = discord.PCMVolumeTransformer(new_source, volume=1.0)
                        if interaction.guild.voice_client and not interaction.guild.voice_client.is_playing():
                            interaction.guild.voice_client.play(new_source, after=after_callback)
                    except Exception as e:
                        logger.error(f'重新掛載音頻源失敗: {e}')

            vc.play(source, after=after_callback)

            session.text_channel = interaction.channel
            session.is_active = True
            session.is_authenticating = False

            # 啟動 stderr 監控
            session.monitor_thread = threading.Thread(
                target=self._monitor_stderr,
                args=(session, interaction.guild.id),
                daemon=True,
            )
            session.monitor_thread.start()

            # 成功訊息
            user_avatar = None
            try:
                # 嘗試取得 Spotify 頭像
                images = spotify_user.get('images', [])
                if images:
                    user_avatar = images[0].get('url')
            except Exception:
                pass

            embed = discord.Embed(
                title='📡 Spotify Connect 已啟動！',
                description=(
                    f'👤 **{session.connected_user_name}** 已登入\n\n'
                    f'🔊 **裝置名稱**：`{device_name}`\n\n'
                    '📱 **使用方式**：\n'
                    '> 1️⃣ 開啟 **Spotify** App\n'
                    '> 2️⃣ 點擊播放器的 **裝置圖示** 🔊\n'
                    f'> 3️⃣ 選擇 **{device_name}**\n'
                    '> 4️⃣ 播放任意歌曲 🎵\n\n'
                    '🔄 切歌、暫停、調音量都會即時同步'
                ),
                color=0x1DB954,
            )
            embed.add_field(name='🎵 音質', value='320 kbps', inline=True)
            embed.add_field(name='📍 語音頻道', value=voice_channel.mention, inline=True)
            if user_avatar:
                embed.set_thumbnail(url=user_avatar)
            embed.set_footer(text='使用 /spotify disconnect 停止')

            await interaction.followup.send(embed=embed)
            logger.info(
                f'Spotify Connect 已啟動 (guild={interaction.guild.id}, '
                f'user={session.connected_user_name}, device={device_name})'
            )

        except Exception as e:
            session.cleanup()
            logger.error(f'Spotify Connect 啟動失敗: {e}', exc_info=True)
            await interaction.followup.send(f'❌ 啟動失敗: {str(e)[:200]}')

    # ────────────────────────────────────────────────────────
    #  /spotify disconnect — 停止
    # ────────────────────────────────────────────────────────
    @spotify.command(
        name='disconnect',
        description='⏹️ 停止 Spotify Connect 並離開語音頻道',
    )
    async def disconnect(self, interaction: discord.Interaction):
        session = self.get_session(interaction.guild.id)

        if not session.is_active:
            return await interaction.response.send_message(
                '❌ Spotify Connect 目前未啟動。', ephemeral=True
            )

        user_name = session.connected_discord_user or '未知'

        # 先回應再清理，避免 Discord 3 秒超時
        embed = discord.Embed(
            title='⏹️ Spotify Connect 已停止',
            description=f'👤 **{user_name}** 的連線已斷開。',
            color=0xED4245,
        )
        await interaction.response.send_message(embed=embed)

        try:
            await self._stop_session(interaction.guild)
        except Exception as e:
            logger.error(f'disconnect 清理錯誤: {e}', exc_info=True)

    # ────────────────────────────────────────────────────────
    #  /spotify status — 查看狀態
    # ────────────────────────────────────────────────────────
    @spotify.command(
        name='status',
        description='📡 查看 Spotify Connect 目前狀態',
    )
    async def status(self, interaction: discord.Interaction):
        session = self.get_session(interaction.guild.id)

        if session.is_authenticating:
            embed = discord.Embed(
                title='📡 Spotify Connect 狀態',
                description='🟡 **等待使用者登入 Spotify 中...**',
                color=0xFEE75C,
            )
            await interaction.response.send_message(embed=embed)
            return

        if session.is_active:
            embed = discord.Embed(
                title='📡 Spotify Connect 狀態',
                color=0x1DB954,
            )

            vc = interaction.guild.voice_client
            is_playing = vc.is_playing() if vc else False
            status_text = '🟢 串流中' if is_playing else '🟡 等待播放...'

            embed.add_field(name='狀態', value=status_text, inline=True)
            embed.add_field(
                name='👤 連接帳號',
                value=session.connected_user_name or '未知',
                inline=True,
            )
            embed.add_field(
                name='🎮 Discord 使用者',
                value=session.connected_discord_user or '未知',
                inline=True,
            )
            embed.add_field(
                name='🔊 裝置名稱',
                value=f'`{session.device_name}`',
                inline=True,
            )
            if vc:
                embed.add_field(
                    name='📍 語音頻道',
                    value=vc.channel.mention,
                    inline=True,
                )

            # 顯示目前播放的歌曲
            if session.current_track_id and self.sp:
                try:
                    track = await asyncio.get_running_loop().run_in_executor(
                        None, self.sp.track, session.current_track_id
                    )
                    artist = ', '.join(a['name'] for a in track['artists'])
                    embed.description = f'🎵 **{track["name"]}** — {artist}'
                except Exception:
                    embed.description = '📱 開啟 Spotify → 裝置選擇 → 選擇音響'
            else:
                embed.description = '📱 開啟 Spotify → 裝置選擇 → 選擇音響'

        else:
            embed = discord.Embed(
                title='📡 Spotify Connect 狀態',
                description=(
                    '🔴 **未啟動**\n\n'
                    '使用 `/spotify connect` 登入並開始'
                ),
                color=0x95a5a6,
            )

        await interaction.response.send_message(embed=embed)

    # ────────────────────────────────────────────────────────
    #  /spotify volume — 調整音量
    # ────────────────────────────────────────────────────────
    @spotify.command(
        name='volume',
        description='🔊 調整 Spotify Connect 音量 (0-200)',
    )
    @app_commands.describe(level='音量大小 (0-200，100=正常，200=加倍)')
    async def volume(self, interaction: discord.Interaction, level: int):
        if level < 0 or level > 200:
            return await interaction.response.send_message(
                '❌ 音量範圍為 0-200', ephemeral=True
            )

        vc = interaction.guild.voice_client
        if vc and vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
            vc.source.volume = level / 100
            icon = '🔇' if level == 0 else '🔈' if level < 50 else '🔉' if level < 100 else '🔊'
            await interaction.response.send_message(
                f'{icon} Spotify Connect 音量已設為 **{level}%**'
            )
        else:
            await interaction.response.send_message(
                '❌ Spotify Connect 未啟動', ephemeral=True
            )

    # ────────────────────────────────────────────────────────
    #  /spotify np — Now Playing 查看正在播放
    # ────────────────────────────────────────────────────────
    @spotify.command(
        name='np',
        description='🎵 查看目前正在播放的 Spotify 曲目',
    )
    async def now_playing(self, interaction: discord.Interaction):
        session = self.get_session(interaction.guild.id)

        if not session.is_active:
            return await interaction.response.send_message(
                '❌ Spotify Connect 未啟動。使用 `/spotify connect` 開始。',
                ephemeral=True,
            )

        vc = interaction.guild.voice_client
        if not vc or not vc.is_playing():
            embed = discord.Embed(
                title='🎵 Now Playing',
                description='⏸️ 目前沒有正在播放的曲目。\n\n'
                            '請在 Spotify App 中選擇裝置 '
                            f'**{session.device_name}** 並播放音樂。',
                color=0x95a5a6,
            )
            embed.set_footer(text=f'📡 {session.device_name}')
            return await interaction.response.send_message(embed=embed)

        # 有曲目資訊時使用 Spotify API 取得詳細資料
        if session.current_track_id and self.sp:
            try:
                track = await asyncio.get_running_loop().run_in_executor(
                    None, self.sp.track, session.current_track_id
                )

                name = track['name']
                artists = ', '.join(a['name'] for a in track['artists'])
                album = track['album']['name']
                duration_ms = track['duration_ms']
                album_art = track['album']['images'][0]['url'] if track['album']['images'] else None
                track_url = track['external_urls'].get('spotify', '')
                release_date = track['album'].get('release_date', '')

                total_sec = duration_ms // 1000
                dur_min, dur_sec = divmod(total_sec, 60)

                # 計算已播放時間
                elapsed_sec = 0
                if session.track_start_time:
                    elapsed_sec = int(time.time() - session.track_start_time)
                    elapsed_sec = min(elapsed_sec, total_sec)
                el_min, el_sec = divmod(elapsed_sec, 60)

                progress_bar = self._format_progress_bar(elapsed_sec, total_sec)

                embed = discord.Embed(
                    title=name,
                    url=track_url,
                    color=0x1DB954,
                )
                embed.set_author(
                    name='🎵 Now Playing — Spotify Connect',
                    icon_url='https://i.imgur.com/dJNlb5N.png',
                )
                embed.add_field(name='🎤 歌手', value=artists, inline=True)
                embed.add_field(name='💿 專輯', value=album, inline=True)
                embed.add_field(
                    name='📅 發行',
                    value=release_date[:4] if release_date else '—',
                    inline=True,
                )
                embed.add_field(
                    name='',
                    value=f'`{el_min}:{el_sec:02d}` {progress_bar} `{dur_min}:{dur_sec:02d}`',
                    inline=False,
                )

                if album_art:
                    embed.set_thumbnail(url=album_art)

                # Volume info
                vol = 100
                if vc.source and isinstance(vc.source, discord.PCMVolumeTransformer):
                    vol = int(vc.source.volume * 100)
                vol_icon = '🔇' if vol == 0 else '🔈' if vol < 50 else '🔉' if vol < 100 else '🔊'

                embed.set_footer(
                    text=f'📡 {session.device_name}  •  '
                         f'👤 {session.connected_user_name}  •  '
                         f'🎧 320 kbps  •  {vol_icon} {vol}%'
                )

                # 加入「在 Spotify 打開」按鈕
                view = discord.ui.View()
                if track_url:
                    view.add_item(discord.ui.Button(
                        label='在 Spotify 打開',
                        url=track_url,
                        style=discord.ButtonStyle.link,
                        emoji='🎵',
                    ))
                view.add_item(discord.ui.Button(
                    label=f'{session.device_name}',
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    emoji='📡',
                ))

                await interaction.response.send_message(embed=embed, view=view)
                return

            except Exception as e:
                logger.warning(f'Now Playing 查詢失敗: {e}')

        # 簡化版（無法取得曲目資訊時）
        embed = discord.Embed(
            title='🎵 Now Playing',
            description=(
                '🎶 **音樂播放中**\n\n'
                f'Track ID: `{session.current_track_id or "unknown"}`\n\n'
                '💡 無法取得詳細曲目資訊。\n'
                '請確認 Spotify Client ID/Secret 已正確設定。'
            ),
            color=0x1DB954,
        )
        embed.set_footer(
            text=f'📡 {session.device_name}  •  👤 {session.connected_user_name}'
        )
        await interaction.response.send_message(embed=embed)


    # ══════════════════════════════════════════════════════════
    #  內部方法
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _build_oauth_url(state: str) -> str:
        """構建 Spotify OAuth 授權 URL"""
        params = {
            'client_id': config.SPOTIFY_CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': config.SPOTIFY_REDIRECT_URI,
            'scope': config.SPOTIFY_SCOPES,
            'state': state,
            'show_dialog': 'true',  # 每次都顯示授權頁面，支援切換帳號
        }
        return 'https://accounts.spotify.com/authorize?' + urllib.parse.urlencode(params)

    @staticmethod
    async def _get_spotify_user(access_token: str) -> dict:
        """用 access token 取得 Spotify 使用者資訊"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/me',
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.warning(f'取得 Spotify 使用者資訊失敗: {e}')
        return {'display_name': '未知', 'id': 'unknown'}

    def _monitor_stderr(self, session: SpotifySession, guild_id: int):
        """在背景執行緒中監控 librespot stderr"""
        try:
            while session.is_active and session.librespot_proc:
                if session.librespot_proc.poll() is not None:
                    logger.info('librespot 程序已結束')
                    break

                line = session.librespot_proc.stderr.readline()
                if not line:
                    break

                text = line.decode('utf-8', errors='ignore').strip()
                if not text:
                    continue

                logger.info(f'[librespot] {text}')

                # 用 regex 提取 Spotify track URI
                match = SPOTIFY_URI_RE.search(text)
                if match and ('Loading' in text or 'loading' in text):
                    track_id = match.group(1)
                    if track_id != session.current_track_id:
                        session.current_track_id = track_id
                        session.track_start_time = time.time()
                        if session.text_channel:
                            asyncio.run_coroutine_threadsafe(
                                self._send_track_notification(session, track_id),
                                self.bot.loop,
                            )

                # 偵測認證錯誤
                if 'Authentication failed' in text or ('authentication' in text.lower() and 'error' in text.lower()):
                    logger.error(f'Spotify 認證失敗: {text}')
                    if session.text_channel:
                        asyncio.run_coroutine_threadsafe(
                            session.text_channel.send(
                                '❌ Spotify 認證已過期或無效。\n'
                                '請使用 `/spotify disconnect` 後重新 `/spotify connect`。'
                            ),
                            self.bot.loop,
                        )

        except Exception as e:
            logger.error(f'librespot 監控錯誤: {e}')

    async def _send_track_notification(self, session: SpotifySession, track_id: str):
        """發送美化的曲目切換通知 + 啟動進度條自動更新"""
        # 取消上一首的進度更新
        if session.np_update_task and not session.np_update_task.done():
            session.np_update_task.cancel()
            session.np_update_task = None

        # 刪除上一首的 Now Playing
        if session.now_playing_msg:
            try:
                await session.now_playing_msg.delete()
            except Exception:
                pass
            session.now_playing_msg = None

        # 用 Spotify Web API 取得歌曲資訊
        if self.sp:
            try:
                track = await asyncio.get_running_loop().run_in_executor(
                    None, self.sp.track, track_id
                )

                name = track['name']
                artists = ', '.join(a['name'] for a in track['artists'])
                album = track['album']['name']
                duration_ms = track['duration_ms']
                album_art = track['album']['images'][0]['url'] if track['album']['images'] else None
                track_url = track['external_urls'].get('spotify', '')

                total_sec = duration_ms // 1000
                dur_min, dur_sec = divmod(total_sec, 60)
                progress_bar = self._format_progress_bar(0, total_sec)

                # 儲存曲目資訊到 session（給 /spotify np 和進度更新使用）
                session.track_name = name
                session.track_artists = artists
                session.track_album = album
                session.track_duration_sec = total_sec
                session.track_album_art = album_art
                session.track_url = track_url

                embed = discord.Embed(
                    title=name,
                    url=track_url,
                    color=0x1DB954,
                )
                embed.set_author(name='🎵 正在播放', icon_url='https://i.imgur.com/dJNlb5N.png')
                embed.add_field(name='🎤 歌手', value=artists, inline=True)
                embed.add_field(name='💿 專輯', value=album, inline=True)
                embed.add_field(
                    name='⏱️ 時長',
                    value=f'`{dur_min}:{dur_sec:02d}`',
                    inline=True,
                )
                embed.add_field(
                    name='',
                    value=f'`0:00` {progress_bar} `{dur_min}:{dur_sec:02d}`',
                    inline=False,
                )

                if album_art:
                    embed.set_thumbnail(url=album_art)

                embed.set_footer(
                    text=f'📡 {session.device_name}  •  👤 {session.connected_user_name}  •  🎧 320 kbps'
                )

                # 加入「在 Spotify 打開」按鈕
                view = discord.ui.View()
                if track_url:
                    view.add_item(discord.ui.Button(
                        label='在 Spotify 打開',
                        url=track_url,
                        style=discord.ButtonStyle.link,
                        emoji='🎵',
                    ))

                session.now_playing_msg = await session.text_channel.send(embed=embed, view=view)

                # 啟動進度條自動更新任務
                session.np_update_task = asyncio.create_task(
                    self._update_progress_loop(session, total_sec)
                )
                return

            except Exception as e:
                logger.warning(f'Spotify API 查詢失敗: {e}')

        # 簡化版
        embed = discord.Embed(
            title='🎵 正在播放',
            description=f'Track ID: `{track_id}`',
            color=0x1DB954,
        )
        embed.set_footer(text=f'📡 {session.device_name}')
        session.now_playing_msg = await session.text_channel.send(embed=embed)

    async def _update_progress_loop(self, session: SpotifySession, total_sec: int):
        """每 15 秒自動更新 Now Playing 嵌入的進度條"""
        try:
            dur_min, dur_sec = divmod(total_sec, 60)

            while session.is_active and session.now_playing_msg and total_sec > 0:
                await asyncio.sleep(15)

                if not session.is_active or not session.now_playing_msg:
                    break

                elapsed_sec = 0
                if session.track_start_time:
                    elapsed_sec = int(time.time() - session.track_start_time)

                # 如果超過歌曲時長，停止更新（等下一首觸發）
                if elapsed_sec >= total_sec:
                    break

                el_min, el_sec = divmod(elapsed_sec, 60)
                progress_bar = self._format_progress_bar(elapsed_sec, total_sec)

                try:
                    embed = session.now_playing_msg.embeds[0].copy()

                    # 更新進度條欄位（最後一個 field）
                    if embed.fields:
                        last_idx = len(embed.fields) - 1
                        embed.set_field_at(
                            last_idx,
                            name='',
                            value=f'`{el_min}:{el_sec:02d}` {progress_bar} `{dur_min}:{dur_sec:02d}`',
                            inline=False,
                        )

                    await session.now_playing_msg.edit(embed=embed)
                except discord.NotFound:
                    # 訊息被刪除了
                    session.now_playing_msg = None
                    break
                except Exception as e:
                    logger.debug(f'進度更新失敗: {e}')
                    break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug(f'進度更新循環結束: {e}')

    @staticmethod
    def _format_progress_bar(current_sec: int, total_sec: int, length: int = 16) -> str:
        """產生文字進度條"""
        if total_sec <= 0:
            return '━' * length
        ratio = min(current_sec / total_sec, 1.0)
        filled = int(ratio * length)
        bar = '━' * filled + '🔘' + '─' * (length - filled)
        return bar

    async def _stop_session(self, guild: discord.Guild):
        """停止 Spotify Connect 會話"""
        session = self.get_session(guild.id)

        if guild.voice_client:
            try:
                guild.voice_client.stop()
                await guild.voice_client.disconnect()
            except Exception as e:
                logger.warning(f'斷開語音連線時出錯: {e}')

        session.cleanup()

        if guild.id in self.sessions:
            del self.sessions[guild.id]

        logger.info(f'Spotify Connect 已停止 (guild={guild.id})')

    async def _auto_cleanup(self, guild: discord.Guild):
        """自動清理（當 librespot 退出時）"""
        session = self.get_session(guild.id)
        if session.is_active:
            if session.librespot_proc and session.librespot_proc.poll() is not None:
                exit_code = session.librespot_proc.returncode
                logger.info(f'auto_cleanup: librespot 已退出 (exit_code={exit_code})')
                await self._stop_session(guild)
                if session.text_channel:
                    try:
                        await session.text_channel.send(
                            f'📡 Spotify Connect 已自動斷開（librespot exit_code={exit_code}）'
                        )
                    except Exception:
                        pass
            else:
                logger.info('auto_cleanup: librespot 仍在運行，不清理')

    # ── Cog 卸載 ───────────────────────────────────────────
    def cog_unload(self):
        for guild_id in list(self.sessions.keys()):
            session = self.sessions[guild_id]
            session.cleanup()
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client:
                asyncio.run_coroutine_threadsafe(
                    guild.voice_client.disconnect(), self.bot.loop
                )
        self.sessions.clear()


async def setup(bot: commands.Bot):
    await bot.add_cog(SpotifyConnect(bot))
