# -*- coding: utf-8 -*-
"""
PongPong Bot — 國旗猜謎 Cog
/flagquiz [count] 開始測驗、/quizrank 查看當前遊戲排行

支援 190+ 國家，答案可用中文 / 英文 / 日文
中文答案支援部分匹配（≥2 字元）
"""

import random
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime

import config
from utils.logger import get_logger
import database

logger = get_logger('flagquiz')

# ══════════════════════════════════════════════════════════════
# 國家資料：(國旗, 中文名, 英文名, 日文名)
# 依洲別分類，共 195 筆
# ══════════════════════════════════════════════════════════════

# ── 亞洲 (Asia) ───────────────────────────────────────────────
_ASIA = [
    ('🇯🇵', '日本', 'Japan', '日本'),
    ('🇰🇷', '韓國', 'South Korea', '韓国'),
    ('🇰🇵', '北韓', 'North Korea', '北朝鮮'),
    ('🇨🇳', '中國', 'China', '中国'),
    ('🇹🇼', '台灣', 'Taiwan', '台湾'),
    ('🇭🇰', '香港', 'Hong Kong', '香港'),
    ('🇲🇴', '澳門', 'Macau', 'マカオ'),
    ('🇲🇳', '蒙古', 'Mongolia', 'モンゴル'),
    ('🇮🇳', '印度', 'India', 'インド'),
    ('🇵🇰', '巴基斯坦', 'Pakistan', 'パキスタン'),
    ('🇧🇩', '孟加拉', 'Bangladesh', 'バングラデシュ'),
    ('🇱🇰', '斯里蘭卡', 'Sri Lanka', 'スリランカ'),
    ('🇳🇵', '尼泊爾', 'Nepal', 'ネパール'),
    ('🇧🇹', '不丹', 'Bhutan', 'ブータン'),
    ('🇲🇻', '馬爾地夫', 'Maldives', 'モルディブ'),
    ('🇦🇫', '阿富汗', 'Afghanistan', 'アフガニスタン'),
    ('🇮🇷', '伊朗', 'Iran', 'イラン'),
    ('🇮🇶', '伊拉克', 'Iraq', 'イラク'),
    ('🇸🇦', '沙烏地阿拉伯', 'Saudi Arabia', 'サウジアラビア'),
    ('🇦🇪', '阿拉伯聯合大公國', 'United Arab Emirates', 'アラブ首長国連邦'),
    ('🇶🇦', '卡達', 'Qatar', 'カタール'),
    ('🇰🇼', '科威特', 'Kuwait', 'クウェート'),
    ('🇧🇭', '巴林', 'Bahrain', 'バーレーン'),
    ('🇴🇲', '阿曼', 'Oman', 'オマーン'),
    ('🇾🇪', '葉門', 'Yemen', 'イエメン'),
    ('🇯🇴', '約旦', 'Jordan', 'ヨルダン'),
    ('🇱🇧', '黎巴嫩', 'Lebanon', 'レバノン'),
    ('🇸🇾', '敘利亞', 'Syria', 'シリア'),
    ('🇮🇱', '以色列', 'Israel', 'イスラエル'),
    ('🇵🇸', '巴勒斯坦', 'Palestine', 'パレスチナ'),
    ('🇹🇷', '土耳其', 'Turkey', 'トルコ'),
    ('🇬🇪', '喬治亞', 'Georgia', 'ジョージア'),
    ('🇦🇲', '亞美尼亞', 'Armenia', 'アルメニア'),
    ('🇦🇿', '亞塞拜然', 'Azerbaijan', 'アゼルバイジャン'),
    ('🇰🇿', '哈薩克', 'Kazakhstan', 'カザフスタン'),
    ('🇺🇿', '烏茲別克', 'Uzbekistan', 'ウズベキスタン'),
    ('🇹🇲', '土庫曼', 'Turkmenistan', 'トルクメニスタン'),
    ('🇹🇯', '塔吉克', 'Tajikistan', 'タジキスタン'),
    ('🇰🇬', '吉爾吉斯', 'Kyrgyzstan', 'キルギス'),
    ('🇹🇭', '泰國', 'Thailand', 'タイ'),
    ('🇻🇳', '越南', 'Vietnam', 'ベトナム'),
    ('🇲🇲', '緬甸', 'Myanmar', 'ミャンマー'),
    ('🇰🇭', '柬埔寨', 'Cambodia', 'カンボジア'),
    ('🇱🇦', '寮國', 'Laos', 'ラオス'),
    ('🇲🇾', '馬來西亞', 'Malaysia', 'マレーシア'),
    ('🇸🇬', '新加坡', 'Singapore', 'シンガポール'),
    ('🇮🇩', '印尼', 'Indonesia', 'インドネシア'),
    ('🇵🇭', '菲律賓', 'Philippines', 'フィリピン'),
    ('🇧🇳', '汶萊', 'Brunei', 'ブルネイ'),
    ('🇹🇱', '東帝汶', 'Timor-Leste', '東ティモール'),
    ('🇨🇾', '賽普勒斯', 'Cyprus', 'キプロス'),
]

# ── 歐洲 (Europe) ────────────────────────────────────────────
_EUROPE = [
    ('🇬🇧', '英國', 'United Kingdom', 'イギリス'),
    ('🇫🇷', '法國', 'France', 'フランス'),
    ('🇩🇪', '德國', 'Germany', 'ドイツ'),
    ('🇮🇹', '義大利', 'Italy', 'イタリア'),
    ('🇪🇸', '西班牙', 'Spain', 'スペイン'),
    ('🇵🇹', '葡萄牙', 'Portugal', 'ポルトガル'),
    ('🇳🇱', '荷蘭', 'Netherlands', 'オランダ'),
    ('🇧🇪', '比利時', 'Belgium', 'ベルギー'),
    ('🇱🇺', '盧森堡', 'Luxembourg', 'ルクセンブルク'),
    ('🇨🇭', '瑞士', 'Switzerland', 'スイス'),
    ('🇦🇹', '奧地利', 'Austria', 'オーストリア'),
    ('🇮🇪', '愛爾蘭', 'Ireland', 'アイルランド'),
    ('🇮🇸', '冰島', 'Iceland', 'アイスランド'),
    ('🇳🇴', '挪威', 'Norway', 'ノルウェー'),
    ('🇸🇪', '瑞典', 'Sweden', 'スウェーデン'),
    ('🇩🇰', '丹麥', 'Denmark', 'デンマーク'),
    ('🇫🇮', '芬蘭', 'Finland', 'フィンランド'),
    ('🇪🇪', '愛沙尼亞', 'Estonia', 'エストニア'),
    ('🇱🇻', '拉脫維亞', 'Latvia', 'ラトビア'),
    ('🇱🇹', '立陶宛', 'Lithuania', 'リトアニア'),
    ('🇵🇱', '波蘭', 'Poland', 'ポーランド'),
    ('🇨🇿', '捷克', 'Czech Republic', 'チェコ'),
    ('🇸🇰', '斯洛伐克', 'Slovakia', 'スロバキア'),
    ('🇭🇺', '匈牙利', 'Hungary', 'ハンガリー'),
    ('🇷🇴', '羅馬尼亞', 'Romania', 'ルーマニア'),
    ('🇧🇬', '保加利亞', 'Bulgaria', 'ブルガリア'),
    ('🇬🇷', '希臘', 'Greece', 'ギリシャ'),
    ('🇭🇷', '克羅埃西亞', 'Croatia', 'クロアチア'),
    ('🇸🇮', '斯洛維尼亞', 'Slovenia', 'スロベニア'),
    ('🇷🇸', '塞爾維亞', 'Serbia', 'セルビア'),
    ('🇧🇦', '波士尼亞', 'Bosnia and Herzegovina', 'ボスニア・ヘルツェゴビナ'),
    ('🇲🇪', '蒙特內哥羅', 'Montenegro', 'モンテネグロ'),
    ('🇲🇰', '北馬其頓', 'North Macedonia', '北マケドニア'),
    ('🇦🇱', '阿爾巴尼亞', 'Albania', 'アルバニア'),
    ('🇽🇰', '科索沃', 'Kosovo', 'コソボ'),
    ('🇲🇩', '摩爾多瓦', 'Moldova', 'モルドバ'),
    ('🇺🇦', '烏克蘭', 'Ukraine', 'ウクライナ'),
    ('🇧🇾', '白俄羅斯', 'Belarus', 'ベラルーシ'),
    ('🇷🇺', '俄羅斯', 'Russia', 'ロシア'),
    ('🇲🇹', '馬爾他', 'Malta', 'マルタ'),
    ('🇲🇨', '摩納哥', 'Monaco', 'モナコ'),
    ('🇱🇮', '列支敦斯登', 'Liechtenstein', 'リヒテンシュタイン'),
    ('🇦🇩', '安道爾', 'Andorra', 'アンドラ'),
    ('🇸🇲', '聖馬利諾', 'San Marino', 'サンマリノ'),
    ('🇻🇦', '梵蒂岡', 'Vatican City', 'バチカン'),
]

# ── 非洲 (Africa) ────────────────────────────────────────────
_AFRICA = [
    ('🇪🇬', '埃及', 'Egypt', 'エジプト'),
    ('🇱🇾', '利比亞', 'Libya', 'リビア'),
    ('🇹🇳', '突尼西亞', 'Tunisia', 'チュニジア'),
    ('🇩🇿', '阿爾及利亞', 'Algeria', 'アルジェリア'),
    ('🇲🇦', '摩洛哥', 'Morocco', 'モロッコ'),
    ('🇲🇷', '茅利塔尼亞', 'Mauritania', 'モーリタニア'),
    ('🇸🇩', '蘇丹', 'Sudan', 'スーダン'),
    ('🇸🇸', '南蘇丹', 'South Sudan', '南スーダン'),
    ('🇪🇹', '衣索比亞', 'Ethiopia', 'エチオピア'),
    ('🇪🇷', '厄利垂亞', 'Eritrea', 'エリトリア'),
    ('🇩🇯', '吉布地', 'Djibouti', 'ジブチ'),
    ('🇸🇴', '索馬利亞', 'Somalia', 'ソマリア'),
    ('🇰🇪', '肯亞', 'Kenya', 'ケニア'),
    ('🇺🇬', '烏干達', 'Uganda', 'ウガンダ'),
    ('🇹🇿', '坦尚尼亞', 'Tanzania', 'タンザニア'),
    ('🇷🇼', '盧安達', 'Rwanda', 'ルワンダ'),
    ('🇧🇮', '蒲隆地', 'Burundi', 'ブルンジ'),
    ('🇨🇩', '剛果民主共和國', 'Democratic Republic of the Congo', 'コンゴ民主共和国'),
    ('🇨🇬', '剛果共和國', 'Republic of the Congo', 'コンゴ共和国'),
    ('🇬🇦', '加彭', 'Gabon', 'ガボン'),
    ('🇬🇶', '赤道幾內亞', 'Equatorial Guinea', '赤道ギニア'),
    ('🇨🇲', '喀麥隆', 'Cameroon', 'カメルーン'),
    ('🇳🇬', '奈及利亞', 'Nigeria', 'ナイジェリア'),
    ('🇳🇪', '尼日', 'Niger', 'ニジェール'),
    ('🇹🇩', '查德', 'Chad', 'チャド'),
    ('🇨🇫', '中非共和國', 'Central African Republic', '中央アフリカ'),
    ('🇲🇱', '馬利', 'Mali', 'マリ'),
    ('🇧🇫', '布吉納法索', 'Burkina Faso', 'ブルキナファソ'),
    ('🇸🇳', '塞內加爾', 'Senegal', 'セネガル'),
    ('🇬🇲', '甘比亞', 'Gambia', 'ガンビア'),
    ('🇬🇼', '幾內亞比索', 'Guinea-Bissau', 'ギニアビサウ'),
    ('🇬🇳', '幾內亞', 'Guinea', 'ギニア'),
    ('🇸🇱', '獅子山', 'Sierra Leone', 'シエラレオネ'),
    ('🇱🇷', '賴比瑞亞', 'Liberia', 'リベリア'),
    ('🇨🇮', '象牙海岸', 'Ivory Coast', 'コートジボワール'),
    ('🇬🇭', '迦納', 'Ghana', 'ガーナ'),
    ('🇹🇬', '多哥', 'Togo', 'トーゴ'),
    ('🇧🇯', '貝南', 'Benin', 'ベナン'),
    ('🇿🇦', '南非', 'South Africa', '南アフリカ'),
    ('🇳🇦', '納米比亞', 'Namibia', 'ナミビア'),
    ('🇧🇼', '波札那', 'Botswana', 'ボツワナ'),
    ('🇿🇼', '辛巴威', 'Zimbabwe', 'ジンバブエ'),
    ('🇿🇲', '尚比亞', 'Zambia', 'ザンビア'),
    ('🇲🇼', '馬拉威', 'Malawi', 'マラウイ'),
    ('🇲🇿', '莫三比克', 'Mozambique', 'モザンビーク'),
    ('🇲🇬', '馬達加斯加', 'Madagascar', 'マダガスカル'),
    ('🇲🇺', '模里西斯', 'Mauritius', 'モーリシャス'),
    ('🇰🇲', '葛摩', 'Comoros', 'コモロ'),
    ('🇸🇨', '塞席爾', 'Seychelles', 'セーシェル'),
    ('🇦🇴', '安哥拉', 'Angola', 'アンゴラ'),
    ('🇸🇿', '史瓦帝尼', 'Eswatini', 'エスワティニ'),
    ('🇱🇸', '賴索托', 'Lesotho', 'レソト'),
    ('🇨🇻', '維德角', 'Cape Verde', 'カーボベルデ'),
    ('🇸🇹', '聖多美普林西比', 'Sao Tome and Principe', 'サントメ・プリンシペ'),
]

# ── 北美洲 (North America) ───────────────────────────────────
_NORTH_AMERICA = [
    ('🇺🇸', '美國', 'United States', 'アメリカ'),
    ('🇨🇦', '加拿大', 'Canada', 'カナダ'),
    ('🇲🇽', '墨西哥', 'Mexico', 'メキシコ'),
    ('🇬🇹', '瓜地馬拉', 'Guatemala', 'グアテマラ'),
    ('🇧🇿', '貝里斯', 'Belize', 'ベリーズ'),
    ('🇭🇳', '宏都拉斯', 'Honduras', 'ホンジュラス'),
    ('🇸🇻', '薩爾瓦多', 'El Salvador', 'エルサルバドル'),
    ('🇳🇮', '尼加拉瓜', 'Nicaragua', 'ニカラグア'),
    ('🇨🇷', '哥斯大黎加', 'Costa Rica', 'コスタリカ'),
    ('🇵🇦', '巴拿馬', 'Panama', 'パナマ'),
    ('🇨🇺', '古巴', 'Cuba', 'キューバ'),
    ('🇯🇲', '牙買加', 'Jamaica', 'ジャマイカ'),
    ('🇭🇹', '海地', 'Haiti', 'ハイチ'),
    ('🇩🇴', '多明尼加', 'Dominican Republic', 'ドミニカ共和国'),
    ('🇹🇹', '千里達及托巴哥', 'Trinidad and Tobago', 'トリニダード・トバゴ'),
    ('🇧🇧', '巴貝多', 'Barbados', 'バルバドス'),
    ('🇧🇸', '巴哈馬', 'Bahamas', 'バハマ'),
    ('🇦🇬', '安地卡及巴布達', 'Antigua and Barbuda', 'アンティグア・バーブーダ'),
    ('🇩🇲', '多米尼克', 'Dominica', 'ドミニカ国'),
    ('🇬🇩', '格瑞那達', 'Grenada', 'グレナダ'),
    ('🇰🇳', '聖克里斯多福及尼維斯', 'Saint Kitts and Nevis', 'セントクリストファー・ネイビス'),
    ('🇱🇨', '聖露西亞', 'Saint Lucia', 'セントルシア'),
    ('🇻🇨', '聖文森及乳格那丁', 'Saint Vincent and the Grenadines', 'セントビンセント・グレナディーン'),
]

# ── 南美洲 (South America) ───────────────────────────────────
_SOUTH_AMERICA = [
    ('🇧🇷', '巴西', 'Brazil', 'ブラジル'),
    ('🇦🇷', '阿根廷', 'Argentina', 'アルゼンチン'),
    ('🇨🇱', '智利', 'Chile', 'チリ'),
    ('🇨🇴', '哥倫比亞', 'Colombia', 'コロンビア'),
    ('🇻🇪', '委內瑞拉', 'Venezuela', 'ベネズエラ'),
    ('🇵🇪', '秘魯', 'Peru', 'ペルー'),
    ('🇪🇨', '厄瓜多', 'Ecuador', 'エクアドル'),
    ('🇧🇴', '玻利維亞', 'Bolivia', 'ボリビア'),
    ('🇵🇾', '巴拉圭', 'Paraguay', 'パラグアイ'),
    ('🇺🇾', '烏拉圭', 'Uruguay', 'ウルグアイ'),
    ('🇬🇾', '蓋亞那', 'Guyana', 'ガイアナ'),
    ('🇸🇷', '蘇利南', 'Suriname', 'スリナム'),
]

# ── 大洋洲 (Oceania) ─────────────────────────────────────────
_OCEANIA = [
    ('🇦🇺', '澳洲', 'Australia', 'オーストラリア'),
    ('🇳🇿', '紐西蘭', 'New Zealand', 'ニュージーランド'),
    ('🇵🇬', '巴布亞紐幾內亞', 'Papua New Guinea', 'パプアニューギニア'),
    ('🇫🇯', '斐濟', 'Fiji', 'フィジー'),
    ('🇸🇧', '索羅門群島', 'Solomon Islands', 'ソロモン諸島'),
    ('🇻🇺', '萬那杜', 'Vanuatu', 'バヌアツ'),
    ('🇼🇸', '薩摩亞', 'Samoa', 'サモア'),
    ('🇹🇴', '東加', 'Tonga', 'トンガ'),
    ('🇰🇮', '吉里巴斯', 'Kiribati', 'キリバス'),
    ('🇲🇭', '馬紹爾群島', 'Marshall Islands', 'マーシャル諸島'),
    ('🇫🇲', '密克羅尼西亞', 'Micronesia', 'ミクロネシア'),
    ('🇵🇼', '帛琉', 'Palau', 'パラオ'),
    ('🇳🇷', '諾魯', 'Nauru', 'ナウル'),
    ('🇹🇻', '吐瓦魯', 'Tuvalu', 'ツバル'),
]

# ── 合併所有國家資料 ─────────────────────────────────────────
COUNTRY_DATA: list[tuple[str, str, str, str]] = (
    _ASIA + _EUROPE + _AFRICA + _NORTH_AMERICA + _SOUTH_AMERICA + _OCEANIA
)

logger.info('已載入 %d 個國家/地區的國旗資料', len(COUNTRY_DATA))


# ══════════════════════════════════════════════════════════════
# 答案比對邏輯
# ══════════════════════════════════════════════════════════════

def _match_answer(answer: str, country: tuple[str, str, str, str]) -> bool:
    """
    檢查使用者的答案是否正確。

    比對規則：
    - 英文：完全匹配（不分大小寫）
    - 日文：完全匹配
    - 中文：完全匹配，或部分匹配（≥2 字元且為子字串）
    """
    _, zh_name, en_name, ja_name = country
    answer_clean = answer.strip()
    answer_lower = answer_clean.lower()

    # 英文完全匹配（不分大小寫）
    if answer_lower == en_name.lower():
        return True

    # 日文完全匹配
    if answer_clean == ja_name:
        return True

    # 中文完全匹配
    if answer_clean == zh_name:
        return True

    # 中文部分匹配（≥2 字元）
    if len(answer_clean) >= 2 and answer_clean in zh_name:
        return True

    return False


# ══════════════════════════════════════════════════════════════
# Cog 主體
# ══════════════════════════════════════════════════════════════

class FlagQuizCog(commands.Cog, name='國旗猜謎'):
    """國旗猜謎遊戲 — 猜出國旗對應的國家名稱"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # 正在進行測驗的頻道 → 遊戲狀態
        # {channel_id: {'scores': {user_id: int}, 'total': int, 'current': int}}
        self._active_quizzes: dict[int, dict] = {}

    # ── /flagquiz ─────────────────────────────────────────────
    @app_commands.command(name='flagquiz', description='開始國旗猜謎遊戲')
    @app_commands.describe(count='題目數量 (5-20)')
    async def slash_flagquiz(
        self,
        interaction: discord.Interaction,
        count: int = 10,
    ):
        channel = interaction.channel

        # 防止同一頻道重複開局
        if channel.id in self._active_quizzes:
            await interaction.response.send_message(
                '⚠️ 此頻道已有猜謎進行中！請等目前的遊戲結束。',
                ephemeral=True,
            )
            return

        # 限制題目數量範圍 5–20
        count = max(5, min(20, count))

        # 初始化遊戲狀態
        self._active_quizzes[channel.id] = {
            'scores': {},   # {user_id: 得分}
            'total': count,
            'current': 0,
        }

        logger.info(
            '頻道 %s 開始國旗猜謎，共 %d 題',
            channel.id, count,
        )

        # 開場 Embed
        await interaction.response.send_message(
            embed=discord.Embed(
                title='🏁 國旗猜謎開始！',
                description=(
                    f'共 **{count}** 題，每題 **30** 秒\n'
                    '回答國家名稱（中文／英文／日文皆可）\n'
                    '最先答對者得分！'
                ),
                color=config.COLOR_PRIMARY,
            )
        )

        # 隨機抽取不重複題目
        questions = random.sample(
            COUNTRY_DATA,
            min(count, len(COUNTRY_DATA)),
        )

        quiz_state = self._active_quizzes[channel.id]
        scores = quiz_state['scores']

        try:
            for i, country in enumerate(questions, 1):
                quiz_state['current'] = i
                flag, zh_name, en_name, ja_name = country

                # 出題 Embed
                q_embed = discord.Embed(
                    title=f'第 {i}/{count} 題',
                    description=f'\n{flag}\n\n這是哪個國家？',
                    color=config.COLOR_WARNING,
                )
                q_embed.set_footer(text='⏱️ 30 秒內回答！')
                await channel.send(embed=q_embed)

                # 等待正確回答
                def check(m: discord.Message) -> bool:
                    return (
                        m.channel.id == channel.id
                        and not m.author.bot
                        and _match_answer(m.content, country)
                    )

                try:
                    msg = await self.bot.wait_for(
                        'message', check=check, timeout=30.0,
                    )
                    # 答對
                    winner = msg.author
                    scores[winner.id] = scores.get(winner.id, 0) + 1

                    result_embed = discord.Embed(
                        title=f'✅ {winner.display_name} 答對了！',
                        description=(
                            f'{flag} **{zh_name}**（{en_name}）\n'
                            f'🇯🇵 {ja_name}'
                        ),
                        color=config.COLOR_SUCCESS,
                    )
                    await channel.send(embed=result_embed)

                except asyncio.TimeoutError:
                    # 超時
                    timeout_embed = discord.Embed(
                        title='⏰ 時間到！',
                        description=(
                            f'正確答案是 {flag} **{zh_name}**（{en_name}）\n'
                            f'🇯🇵 {ja_name}'
                        ),
                        color=config.COLOR_ERROR,
                    )
                    await channel.send(embed=timeout_embed)

                # 題目間隔（最後一題不等待）
                if i < count:
                    await asyncio.sleep(2)

            # ── 結算 ──────────────────────────────────────────
            final_embed = discord.Embed(
                title='🏆 猜謎結束！',
                color=config.COLOR_PRIMARY,
                timestamp=datetime.utcnow(),
            )

            if scores:
                sorted_scores = sorted(
                    scores.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
                medals = ['🥇', '🥈', '🥉']
                lines: list[str] = []
                for idx, (uid, sc) in enumerate(sorted_scores[:10]):
                    prefix = medals[idx] if idx < 3 else f'`#{idx + 1}`'
                    user = self.bot.get_user(uid)
                    name = user.display_name if user else f'User#{uid}'
                    lines.append(f'{prefix} **{name}** — {sc} 分')
                final_embed.description = '\n'.join(lines)
            else:
                final_embed.description = '😅 沒有人答對任何題目...'

            final_embed.set_footer(text=f'PongPong {config.BOT_VERSION}')
            await channel.send(embed=final_embed)

        finally:
            # 無論如何都要清除遊戲狀態
            self._active_quizzes.pop(channel.id, None)

    # ── /quizrank（當前遊戲排行）──────────────────────────────
    @app_commands.command(
        name='quizrank',
        description='查看目前正在進行的國旗猜謎即時排行',
    )
    async def slash_quizrank(self, interaction: discord.Interaction):
        channel = interaction.channel

        quiz_state = self._active_quizzes.get(channel.id)
        if not quiz_state:
            await interaction.response.send_message(
                '📭 目前沒有正在進行的猜謎，使用 `/flagquiz` 開始一場吧！',
                ephemeral=True,
            )
            return

        scores = quiz_state['scores']
        current = quiz_state['current']
        total = quiz_state['total']

        embed = discord.Embed(
            title='📊 當前猜謎即時排行',
            color=config.COLOR_PRIMARY,
        )
        embed.set_footer(text=f'進度：{current}/{total} 題')

        if scores:
            sorted_scores = sorted(
                scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )
            medals = ['🥇', '🥈', '🥉']
            lines: list[str] = []
            for idx, (uid, sc) in enumerate(sorted_scores[:10]):
                prefix = medals[idx] if idx < 3 else f'`#{idx + 1}`'
                user = self.bot.get_user(uid)
                name = user.display_name if user else f'User#{uid}'
                lines.append(f'{prefix} **{name}** — {sc} 分')
            embed.description = '\n'.join(lines)
        else:
            embed.description = '目前還沒有人答對任何題目。'

        await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════════════════════
# Cog 載入入口
# ══════════════════════════════════════════════════════════════

async def setup(bot: commands.Bot):
    await bot.add_cog(FlagQuizCog(bot))
