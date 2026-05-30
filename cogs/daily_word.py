# -*- coding: utf-8 -*-
"""
PongPong Bot — 每日單字推播 Cog
提供 /setdaily、/stopdaily 指令，每日自動推送多語言單字
"""

import random
import datetime
import discord
from discord import app_commands
from discord.ext import commands, tasks

import config
from database import db as database
from utils.logger import get_logger

logger = get_logger('daily_word')

# ── 單字資料庫（旅遊/日常主題）──────────────────────────────
WORD_LIST = [
    # 問候
    {'zh': '你好', 'en': 'Hello', 'ja': 'こんにちは', 'ko': '안녕하세요',
     'sentence_zh': '你好，請問這裡怎麼走？', 'sentence_en': 'Hello, how do I get there?'},
    {'zh': '謝謝', 'en': 'Thank you', 'ja': 'ありがとう', 'ko': '감사합니다',
     'sentence_zh': '非常感謝你的幫助！', 'sentence_en': 'Thank you so much for your help!'},
    {'zh': '對不起', 'en': 'Sorry', 'ja': 'すみません', 'ko': '죄송합니다',
     'sentence_zh': '對不起，我遲到了。', 'sentence_en': 'Sorry, I am late.'},
    {'zh': '再見', 'en': 'Goodbye', 'ja': 'さようなら', 'ko': '안녕히 가세요',
     'sentence_zh': '再見，下次見！', 'sentence_en': 'Goodbye, see you next time!'},
    {'zh': '早安', 'en': 'Good morning', 'ja': 'おはようございます', 'ko': '좋은 아침이에요',
     'sentence_zh': '早安，今天天氣真好。', 'sentence_en': 'Good morning, what a nice day.'},
    {'zh': '晚安', 'en': 'Good night', 'ja': 'おやすみなさい', 'ko': '안녕히 주무세요',
     'sentence_zh': '晚安，做個好夢。', 'sentence_en': 'Good night, sweet dreams.'},
    # 數字
    {'zh': '一', 'en': 'One', 'ja': '一 (いち)', 'ko': '하나',
     'sentence_zh': '請給我一杯水。', 'sentence_en': 'Please give me one glass of water.'},
    {'zh': '十', 'en': 'Ten', 'ja': '十 (じゅう)', 'ko': '열',
     'sentence_zh': '這個要十塊錢。', 'sentence_en': 'This costs ten dollars.'},
    {'zh': '百', 'en': 'Hundred', 'ja': '百 (ひゃく)', 'ko': '백',
     'sentence_zh': '這裡離車站一百公尺。', 'sentence_en': 'It is a hundred meters to the station.'},
    # 食物
    {'zh': '水', 'en': 'Water', 'ja': '水 (みず)', 'ko': '물',
     'sentence_zh': '請給我一杯水。', 'sentence_en': 'Can I have some water, please?'},
    {'zh': '飯', 'en': 'Rice', 'ja': 'ご飯 (ごはん)', 'ko': '밥',
     'sentence_zh': '我想吃一碗飯。', 'sentence_en': 'I would like a bowl of rice.'},
    {'zh': '咖啡', 'en': 'Coffee', 'ja': 'コーヒー', 'ko': '커피',
     'sentence_zh': '請給我一杯咖啡。', 'sentence_en': 'Can I get a coffee, please?'},
    {'zh': '茶', 'en': 'Tea', 'ja': 'お茶 (おちゃ)', 'ko': '차',
     'sentence_zh': '來一杯綠茶吧。', 'sentence_en': 'Let me have a green tea.'},
    {'zh': '麵包', 'en': 'Bread', 'ja': 'パン', 'ko': '빵',
     'sentence_zh': '早餐吃了麵包。', 'sentence_en': 'I had bread for breakfast.'},
    {'zh': '肉', 'en': 'Meat', 'ja': '肉 (にく)', 'ko': '고기',
     'sentence_zh': '這個肉很好吃。', 'sentence_en': 'This meat is delicious.'},
    {'zh': '魚', 'en': 'Fish', 'ja': '魚 (さかな)', 'ko': '생선',
     'sentence_zh': '日本的魚非常新鮮。', 'sentence_en': 'The fish in Japan is very fresh.'},
    # 交通
    {'zh': '車站', 'en': 'Station', 'ja': '駅 (えき)', 'ko': '역',
     'sentence_zh': '請問車站在哪裡？', 'sentence_en': 'Where is the station?'},
    {'zh': '機場', 'en': 'Airport', 'ja': '空港 (くうこう)', 'ko': '공항',
     'sentence_zh': '我要去機場。', 'sentence_en': 'I need to go to the airport.'},
    {'zh': '計程車', 'en': 'Taxi', 'ja': 'タクシー', 'ko': '택시',
     'sentence_zh': '請幫我叫一輛計程車。', 'sentence_en': 'Please call me a taxi.'},
    {'zh': '地鐵', 'en': 'Subway', 'ja': '地下鉄 (ちかてつ)', 'ko': '지하철',
     'sentence_zh': '搭地鐵比較快。', 'sentence_en': 'Taking the subway is faster.'},
    {'zh': '公車', 'en': 'Bus', 'ja': 'バス', 'ko': '버스',
     'sentence_zh': '公車幾點來？', 'sentence_en': 'What time does the bus come?'},
    # 購物
    {'zh': '多少錢', 'en': 'How much', 'ja': 'いくらですか', 'ko': '얼마예요',
     'sentence_zh': '這個多少錢？', 'sentence_en': 'How much is this?'},
    {'zh': '便宜', 'en': 'Cheap', 'ja': '安い (やすい)', 'ko': '싸다',
     'sentence_zh': '可以便宜一點嗎？', 'sentence_en': 'Can you make it cheaper?'},
    {'zh': '貴', 'en': 'Expensive', 'ja': '高い (たかい)', 'ko': '비싸다',
     'sentence_zh': '這個太貴了。', 'sentence_en': 'This is too expensive.'},
    {'zh': '買', 'en': 'Buy', 'ja': '買う (かう)', 'ko': '사다',
     'sentence_zh': '我想買這個。', 'sentence_en': 'I want to buy this.'},
    # 方向
    {'zh': '左邊', 'en': 'Left', 'ja': '左 (ひだり)', 'ko': '왼쪽',
     'sentence_zh': '請往左邊走。', 'sentence_en': 'Please go to the left.'},
    {'zh': '右邊', 'en': 'Right', 'ja': '右 (みぎ)', 'ko': '오른쪽',
     'sentence_zh': '在右邊那條路。', 'sentence_en': 'It is on the right.'},
    {'zh': '前面', 'en': 'Ahead', 'ja': '前 (まえ)', 'ko': '앞',
     'sentence_zh': '一直往前走就到了。', 'sentence_en': 'Go straight ahead.'},
    {'zh': '這裡', 'en': 'Here', 'ja': 'ここ', 'ko': '여기',
     'sentence_zh': '我現在在這裡。', 'sentence_en': 'I am here right now.'},
    {'zh': '那裡', 'en': 'There', 'ja': 'あそこ', 'ko': '거기',
     'sentence_zh': '請到那裡等我。', 'sentence_en': 'Please wait for me there.'},
    # 住宿
    {'zh': '飯店', 'en': 'Hotel', 'ja': 'ホテル', 'ko': '호텔',
     'sentence_zh': '我預訂了一間飯店。', 'sentence_en': 'I booked a hotel.'},
    {'zh': '房間', 'en': 'Room', 'ja': '部屋 (へや)', 'ko': '방',
     'sentence_zh': '請問還有空房間嗎？', 'sentence_en': 'Do you have any rooms available?'},
    # 緊急
    {'zh': '救命', 'en': 'Help', 'ja': '助けて (たすけて)', 'ko': '살려주세요',
     'sentence_zh': '救命！請幫幫我！', 'sentence_en': 'Help! Please help me!'},
    {'zh': '醫院', 'en': 'Hospital', 'ja': '病院 (びょういん)', 'ko': '병원',
     'sentence_zh': '最近的醫院在哪裡？', 'sentence_en': 'Where is the nearest hospital?'},
    {'zh': '警察', 'en': 'Police', 'ja': '警察 (けいさつ)', 'ko': '경찰',
     'sentence_zh': '請幫我叫警察。', 'sentence_en': 'Please call the police.'},
    # 天氣
    {'zh': '天氣', 'en': 'Weather', 'ja': '天気 (てんき)', 'ko': '날씨',
     'sentence_zh': '今天天氣怎麼樣？', 'sentence_en': 'How is the weather today?'},
    {'zh': '熱', 'en': 'Hot', 'ja': '暑い (あつい)', 'ko': '덥다',
     'sentence_zh': '今天好熱啊。', 'sentence_en': 'It is so hot today.'},
    {'zh': '冷', 'en': 'Cold', 'ja': '寒い (さむい)', 'ko': '춥다',
     'sentence_zh': '冬天很冷。', 'sentence_en': 'It is cold in winter.'},
    {'zh': '下雨', 'en': 'Rain', 'ja': '雨 (あめ)', 'ko': '비',
     'sentence_zh': '今天可能會下雨。', 'sentence_en': 'It might rain today.'},
    # 時間
    {'zh': '今天', 'en': 'Today', 'ja': '今日 (きょう)', 'ko': '오늘',
     'sentence_zh': '今天是星期幾？', 'sentence_en': 'What day is it today?'},
    {'zh': '明天', 'en': 'Tomorrow', 'ja': '明日 (あした)', 'ko': '내일',
     'sentence_zh': '明天見！', 'sentence_en': 'See you tomorrow!'},
    {'zh': '現在', 'en': 'Now', 'ja': '今 (いま)', 'ko': '지금',
     'sentence_zh': '現在幾點了？', 'sentence_en': 'What time is it now?'},
    # 日常
    {'zh': '美麗', 'en': 'Beautiful', 'ja': '美しい (うつくしい)', 'ko': '아름답다',
     'sentence_zh': '這個地方真美麗。', 'sentence_en': 'This place is so beautiful.'},
    {'zh': '好吃', 'en': 'Delicious', 'ja': '美味しい (おいしい)', 'ko': '맛있다',
     'sentence_zh': '這個料理真好吃！', 'sentence_en': 'This dish is delicious!'},
    {'zh': '朋友', 'en': 'Friend', 'ja': '友達 (ともだち)', 'ko': '친구',
     'sentence_zh': '你是我的好朋友。', 'sentence_en': 'You are my good friend.'},
    {'zh': '家', 'en': 'Home', 'ja': '家 (いえ)', 'ko': '집',
     'sentence_zh': '我想回家了。', 'sentence_en': 'I want to go home.'},
    {'zh': '學校', 'en': 'School', 'ja': '学校 (がっこう)', 'ko': '학교',
     'sentence_zh': '我在學校學日文。', 'sentence_en': 'I study Japanese at school.'},
    {'zh': '工作', 'en': 'Work', 'ja': '仕事 (しごと)', 'ko': '일',
     'sentence_zh': '今天工作很忙。', 'sentence_en': 'Work is busy today.'},
    {'zh': '旅行', 'en': 'Travel', 'ja': '旅行 (りょこう)', 'ko': '여행',
     'sentence_zh': '我喜歡去日本旅行。', 'sentence_en': 'I love traveling to Japan.'},
    {'zh': '照片', 'en': 'Photo', 'ja': '写真 (しゃしん)', 'ko': '사진',
     'sentence_zh': '可以幫我拍照嗎？', 'sentence_en': 'Can you take a photo for me?'},
    {'zh': '音樂', 'en': 'Music', 'ja': '音楽 (おんがく)', 'ko': '음악',
     'sentence_zh': '我喜歡聽音樂。', 'sentence_en': 'I like listening to music.'},
    {'zh': '電影', 'en': 'Movie', 'ja': '映画 (えいが)', 'ko': '영화',
     'sentence_zh': '我們去看電影吧。', 'sentence_en': 'Let us go watch a movie.'},
    {'zh': '禮物', 'en': 'Gift', 'ja': 'プレゼント', 'ko': '선물',
     'sentence_zh': '這是送你的禮物。', 'sentence_en': 'This is a gift for you.'},
    {'zh': '生日快樂', 'en': 'Happy Birthday', 'ja': 'お誕生日おめでとう', 'ko': '생일 축하해요',
     'sentence_zh': '祝你生日快樂！', 'sentence_en': 'Happy Birthday to you!'},
    {'zh': '新年快樂', 'en': 'Happy New Year', 'ja': '明けましておめでとう', 'ko': '새해 복 많이 받으세요',
     'sentence_zh': '祝大家新年快樂！', 'sentence_en': 'Happy New Year to everyone!'},
    {'zh': '加油', 'en': 'Go for it', 'ja': '頑張って (がんばって)', 'ko': '화이팅',
     'sentence_zh': '加油，你可以的！', 'sentence_en': 'Go for it, you can do it!'},
    {'zh': '沒問題', 'en': 'No problem', 'ja': '大丈夫 (だいじょうぶ)', 'ko': '괜찮아요',
     'sentence_zh': '沒問題，交給我吧。', 'sentence_en': 'No problem, leave it to me.'},
    {'zh': '我愛你', 'en': 'I love you', 'ja': '愛してる (あいしてる)', 'ko': '사랑해요',
     'sentence_zh': '我愛你，永遠愛你。', 'sentence_en': 'I love you, forever and always.'},
]


class DailyWordCog(commands.Cog, name='每日單字'):
    """每日多語言單字推播"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Cog 載入時啟動排程"""
        self.daily_task.start()
        logger.info('每日單字推播排程已啟動')

    async def cog_unload(self):
        """Cog 卸載時停止排程"""
        self.daily_task.cancel()

    # ── 排程任務：每日推播 ────────────────────────────────
    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))  # UTC 00:00 = UTC+8 08:00
    async def daily_task(self):
        """每天早上 8 點 (UTC+8) 推送每日單字"""
        channels = await database.get_daily_channels()
        if not channels:
            return

        word = random.choice(WORD_LIST)
        embed = self._make_word_embed(word)

        for ch_info in channels:
            try:
                channel = self.bot.get_channel(ch_info['channel_id'])
                if channel:
                    await channel.send(embed=embed)
                    logger.info(f'每日單字已推送到伺服器 {ch_info["guild_id"]}')
            except Exception as e:
                logger.error(f'推送失敗 (伺服器 {ch_info["guild_id"]}): {e}')

    @daily_task.before_loop
    async def before_daily(self):
        await self.bot.wait_until_ready()

    def _make_word_embed(self, word: dict) -> discord.Embed:
        """建立每日單字 Embed"""
        embed = discord.Embed(
            title='📅 今日多語言單字',
            color=config.COLOR_PRIMARY,
            timestamp=datetime.datetime.now(datetime.timezone.utc)
        )
        embed.add_field(name='🇹🇼 繁體中文', value=f'**{word["zh"]}**', inline=True)
        embed.add_field(name='🇺🇸 English', value=f'**{word["en"]}**', inline=True)
        embed.add_field(name='🇯🇵 日本語', value=f'**{word["ja"]}**', inline=True)
        embed.add_field(name='🇰🇷 한국어', value=f'**{word["ko"]}**', inline=True)
        embed.add_field(name='\u200b', value='\u200b', inline=True)  # 佔位
        embed.add_field(name='\u200b', value='\u200b', inline=True)  # 佔位

        if word.get('sentence_zh') and word.get('sentence_en'):
            embed.add_field(
                name='📝 例句',
                value=f'🇹🇼 {word["sentence_zh"]}\n🇺🇸 {word["sentence_en"]}',
                inline=False
            )

        embed.set_footer(text='PongPong Bot — 每天學一個新單字！')
        return embed

    # ── Slash Command: /setdaily ──────────────────────────
    @app_commands.command(name='setdaily', description='設定每日單字推播頻道')
    @app_commands.describe(channel='要接收每日單字的頻道')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slash_setdaily(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await database.set_daily_channel(interaction.guild_id, channel.id)

        embed = discord.Embed(
            title='✅ 每日單字已設定',
            description=f'每天早上 8:00 (UTC+8) 將在 {channel.mention} 推送今日單字',
            color=config.COLOR_SUCCESS,
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f'[/setdaily] 伺服器 {interaction.guild_id} 設定頻道 {channel.id}')

    # ── Slash Command: /stopdaily ─────────────────────────
    @app_commands.command(name='stopdaily', description='停止每日單字推播')
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slash_stopdaily(self, interaction: discord.Interaction):
        await database.disable_daily_channel(interaction.guild_id)

        embed = discord.Embed(
            title='🛑 每日單字已停止',
            description='此伺服器的每日單字推播已停用。',
            color=config.COLOR_ERROR,
        )
        await interaction.response.send_message(embed=embed)
        logger.info(f'[/stopdaily] 伺服器 {interaction.guild_id} 停止推播')

    # ── Slash Command: /word ─────────────────────────────
    @app_commands.command(name='word', description='立即獲取一個隨機多語言單字')
    async def slash_word(self, interaction: discord.Interaction):
        word = random.choice(WORD_LIST)
        embed = self._make_word_embed(word)
        await interaction.response.send_message(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyWordCog(bot))
