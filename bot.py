# --- 0. 導入必要的函式庫 ---
import os
import json
import discord
import html
import requests
import asyncio # 用於計時等待
from discord.ext import commands
from google.cloud import translate_v2 as translate
from dotenv import load_dotenv
from keep_alive import keep_alive

# --- 1. 載入環境變數 ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CURRENCY_API_key = os.getenv('CURRENCY_API_key')
DEPLOY_HOOK_URL = os.getenv('RENDER_DEPLOY_HOOK') 

if not TOKEN:
    print("❌ 錯誤: 找不到 DISCORD_TOKEN。")
    exit()

# --- 2. 初始化 Google Cloud ---
google_creds_content = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')
if google_creds_content:
    try:
        cred_dict = json.loads(google_creds_content) 
        with open('credentials.json', 'w', encoding='utf-8') as f:
            json.dump(cred_dict, f)
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'credentials.json'
        translate_client = translate.Client()
        print("✅ Google Cloud Translation API 認證成功！")
    except Exception as e:
        print(f"❌ 建立 credentials.json 失敗: {e}")
        translate_client = None
else:
    if os.path.exists('credentials.json'):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'credentials.json'
        try:
            translate_client = translate.Client()
            print("✅ 使用本地 credentials.json 認證成功！")
        except Exception:
            translate_client = None
    else:
        translate_client = None

# --- 3. 設定 Discord ---
intents = discord.Intents.default()
intents.message_content = True  
intents.reactions = True 
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 4. 定義常數 ---
LANGUAGE_ALIASES = {
    'zh(tw)': 'zh-TW', 'tw': 'zh-TW', 'zh-tw': 'zh-TW', 'cn': 'zh-CN', 'zh-cn': 'zh-CN', 'zh': 'zh-CN',
    'jp': 'ja', 'ja': 'ja', 'en': 'en', 'ko': 'ko', 'kr': 'ko', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'vi': 'vi', 'it': 'it', 'ru': 'ru', 'pt': 'pt', 'ar': 'ar', 'hi': 'hi', 'id': 'id',
    'nl': 'nl', 'sv': 'sv', 'tr': 'tr', 'pl': 'pl'
}
CURRENCY_CODES = {'usd', 'eur', 'jpy', 'twd', 'cny', 'krw', 'gbp', 'aud', 'cad', 'chf', 'hkd', 'sgd', 'inr', 'rub'}
EMOJI_TO_LANGUAGE = {
    "🇹🇼": "zh-TW", "🇯🇵": "ja", "🇺🇸": "en",
    "🇰🇷": "ko", "🇨🇳": "zh-CN", "🇪🇸": "es", "🇫🇷": "fr",
}

def normalize_lang_code(code: str):
    if not code: return None
    return LANGUAGE_ALIASES.get(code.lower(), None)

# --- 5. 核心函式 ---
async def perform_translation(text, target, source=None):
    if not translate_client: return None, "翻譯服務未啟動"
    try:
        result = translate_client.translate(text, target_language=target, source_language=source)
        return html.unescape(result['translatedText']), None
    except Exception as e:
        return None, str(e)

async def perform_currency_conversion(amount, source, target):
    if not CURRENCY_API_key: return None, "匯率服務未設定"
    url = f"https://v6.exchangerate-api.com/v6/{CURRENCY_API_key}/pair/{source}/{target}/{amount}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        if data.get('result') == 'success':
            return float(data['conversion_result']), None
        return None, "API Error"
    except Exception as e:
        return None, str(e)

# --- 【修正後】背景維護任務 ---
async def background_maintenance():
    await bot.wait_until_ready()
    
    if not DEPLOY_HOOK_URL:
        print("⚠️ 未設定 RENDER_DEPLOY_HOOK，將不執行自動重啟。")
        return

    while not bot.is_closed():
        # 關鍵修正：先等待 24 小時 (86400秒)，再執行動作
        print("⏰ 計時開始：機器人將在 24 小時後自動重新部署以保持健康...")
        await asyncio.sleep(43200) 
        
        print("🚀 時間到！正在觸發 Render 重新部署...")
        try:
            requests.get(DEPLOY_HOOK_URL)
            print("✅ 已發送重新部署請求。")
            # 發送後等待一小段時間，避免重複觸發
            await asyncio.sleep(600) 
        except Exception as e:
            print(f"❌ 觸發重新部署失敗: {e}")
            # 如果失敗，等待 1 小時再試
            await asyncio.sleep(3600)

# --- 6. 啟動事件 ---
@bot.event
async def on_ready():
    print(f'✅ 機器人已登入為: {bot.user}')
    
    # 啟動背景任務
    bot.loop.create_task(background_maintenance())

# --- 7. 指令區 (保持不變) ---
@bot.command(name='cc')
async def cc(ctx, *args):
    if not args: return
    src, tgt, amt_str = "jpy", "twd", "1.0"
    if len(args) == 1:
        if '-' in args[0]: parts = args[0].split('-'); src, tgt = parts[0], parts[1]
        else: amt_str = args[0]
    elif len(args) >= 2:
        if '-' in args[0]: parts = args[0].split('-'); src, tgt = parts[0], parts[1]; amt_str = args[1]
        elif '-' in args[1]: parts = args[1].split('-'); src, tgt = parts[0], parts[1]; amt_str = args[0]
    try: amount = float(amt_str)
    except: await ctx.send("金額格式錯誤"); return
    res, err = await perform_currency_conversion(amount, src.upper(), tgt.upper())
    if err: await ctx.send(err)
    else:
        ref = ctx.message.reference
        auth = (await ctx.channel.fetch_message(ref.message_id)).author if ref else ctx.author
        await ctx.send(f"{auth.mention} : `{amount:,.2f} {src.upper()}` = `{res:,.2f} {tgt.upper()}`", reference=ref, mention_author=False)

@bot.command(name='tr')
async def tr(ctx, *args):
    if not args: return
    src, tgt, text_list = None, "zh-TW", list(args)
    if '-' in args[0] and not args[0].startswith('-'):
        parts = args[0].split('-')
        if len(parts) == 2:
            s, t = normalize_lang_code(parts[0]), normalize_lang_code(parts[1])
            if s and t: src, tgt, text_list = s, t, args[1:]
    if not text_list: return
    res, err = await perform_translation(" ".join(text_list), tgt, src)
    if err: await ctx.send(err)
    else:
        ref = ctx.message.reference
        auth = (await ctx.channel.fetch_message(ref.message_id)).author if ref else ctx.author
        await ctx.send(f"{auth.mention} : {res}", reference=ref, mention_author=False)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    emoji = payload.emoji.name
    if emoji not in EMOJI_TO_LANGUAGE: return
    try:
        ch = bot.get_channel(payload.channel_id)
        msg = await ch.fetch_message(payload.message_id)
        if not msg.content or msg.author.id == bot.user.id: return
        res, err = await perform_translation(msg.content, EMOJI_TO_LANGUAGE[emoji])
        if not err: await ch.send(f"{msg.author.mention} : {res}", reference=msg, mention_author=False)
    except: pass

# --- 8. 啟動 ---
try:
    keep_alive()
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ 啟動錯誤: {e}")
