# --- 0. 導入必要的函式庫 ---
import os
import json
import discord
import html  # 用於解碼 HTML 特殊字元
import requests  # 用於貨幣轉換的 HTTP 請求
from discord.ext import commands
from google.cloud import translate_v2 as translate
from dotenv import load_dotenv
from keep_alive import keep_alive  # 確保這行在

# --- 1. 載入環境變數 ---
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
CURRENCY_API_key = os.getenv('CURRENCY_API_key')

if not TOKEN:
    print("❌ 錯誤: 找不到 DISCORD_TOKEN。請檢查您的 .env 檔案或 Render 環境變數。")
    exit()
if not CURRENCY_API_key:
    print("⚠️ 警告: 找不到 CURRENCY_API_key。 !cc 匯率指令將無法運作。")

# --- 2. 初始化 Google Cloud Translation (Python 寫入版) ---
# 嘗試從環境變數讀取 JSON 內容
google_creds_content = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_JSON')

if google_creds_content:
    try:
        print("🔄 正在從環境變數建立 credentials.json 檔案...")
        # 驗證內容是否為有效的 JSON
        cred_dict = json.loads(google_creds_content) 
        
        # 將內容寫入檔案
        with open('credentials.json', 'w', encoding='utf-8') as f:
            json.dump(cred_dict, f)
        print("✅ credentials.json 檔案建立成功。")
        
        # 設定環境變數指向這個新建立的檔案
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'credentials.json'
        
        # 初始化客戶端
        translate_client = translate.Client()
        print("✅ Google Cloud Translation API 認證成功！")
        
    except Exception as e:
        print(f"❌ 建立 credentials.json 失敗: {e}")
        translate_client = None
else:
    # 如果沒有環境變數，嘗試直接讀取本地檔案 (例如在筆電測試時)
    if os.path.exists('credentials.json'):
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'credentials.json'
        try:
            translate_client = translate.Client()
            print("✅ 使用本地 credentials.json 認證成功！")
        except Exception as e:
            print(f"❌ 本地檔案認證失敗: {e}")
            translate_client = None
    else:
        print("⚠️ 警告：找不到 Google 憑證，翻譯功能將無法使用。")
        translate_client = None

# --- 3. 設定 Discord 機器人權限 ---
intents = discord.Intents.default()
intents.message_content = True  
intents.reactions = True 

bot = commands.Bot(command_prefix='!', intents=intents)

# --- 4. 建立代碼別名與清單 ---
LANGUAGE_ALIASES = {
    'zh(tw)': 'zh-TW', 'tw': 'zh-TW', 'zh-tw': 'zh-TW',
    'cn': 'zh-CN', 'zh-cn': 'zh-CN', 'zh': 'zh-CN',
    'jp': 'ja', 'ja': 'ja', 'en': 'en',
    'ko': 'ko', 'kr': 'ko', 'es': 'es', 'fr': 'fr',
    'de': 'de', 'vi': 'vi', 'it': 'it', 'ru': 'ru',
    'pt': 'pt', 'ar': 'ar', 'hi': 'hi', 'id': 'id',
    'nl': 'nl', 'sv': 'sv', 'tr': 'tr', 'pl': 'pl',
}

CURRENCY_CODES = set([
    'usd', 'eur', 'jpy', 'twd', 'cny', 'krw', 'gbp', 'aud', 'cad', 'chf',
    'hkd', 'sgd', 'inr', 'rub'
])

def normalize_lang_code(code: str) -> str | None:
    if not code: return None
    return LANGUAGE_ALIASES.get(code.lower(), None)

# --- 5. 表情符號對應 ---
EMOJI_TO_LANGUAGE = {
    "🇹🇼": "zh-TW", "🇯🇵": "ja", "🇺🇸": "en",
    "🇰🇷": "ko", "🇨🇳": "zh-CN", "🇪🇸": "es", "🇫🇷": "fr",
}

# --- 6. 核心翻譯函式 ---
async def perform_translation(text, target, source=None):
    if not translate_client:
        return None, "抱歉, 翻譯服務 (Google API) 目前無法使用。"
    try:
        result = translate_client.translate(
            text, target_language=target, source_language=source
        )
        return html.unescape(result['translatedText']), None
    except Exception as e:
        print(f"翻譯錯誤: {e}")
        return None, f"翻譯錯誤: {e}"

# --- 7. 核心匯率函式 ---
async def perform_currency_conversion(amount, source, target):
    if not CURRENCY_API_key:
        return None, "抱歉, 匯率服務 (API Key) 尚未設定。"
    
    url = f"https://v6.exchangerate-api.com/v6/{CURRENCY_API_key}/pair/{source}/{target}/{amount}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get('result') == 'success':
            return float(data['conversion_result']), None
        return None, f"API 查詢失敗: {data.get('error-type', '未知錯誤')}"
    except Exception as e:
        return None, f"請求錯誤: {e}"

# --- 8. 啟動事件 ---
@bot.event
async def on_ready():
    print(f'✅ 機器人已登入為: {bot.user}')
    print(f'✅ 已載入 {len(EMOJI_TO_LANGUAGE)} 個表情符號翻譯觸發器。')

# --- 9. !cc 匯率指令 ---
@bot.command(name='cc', help="轉換貨幣。")
async def cc(ctx, *args):
    if not args: return
    
    src, tgt, amt_str = "jpy", "twd", "1.0"
    
    # 簡易參數解析
    if len(args) == 1:
        if '-' in args[0]: # cc jpy-usd
            parts = args[0].split('-')
            if len(parts) == 2: src, tgt = parts[0], parts[1]
        else: # cc 100
            amt_str = args[0]
    elif len(args) >= 2:
        if '-' in args[0]: # cc jpy-usd 100
            parts = args[0].split('-')
            if len(parts) == 2: src, tgt = parts[0], parts[1]
            amt_str = args[1]
        elif '-' in args[1]: # cc 100 jpy-usd
            parts = args[1].split('-')
            if len(parts) == 2: src, tgt = parts[0], parts[1]
            amt_str = args[0]

    try:
        amount = float(amt_str)
    except:
        await ctx.send("金額格式錯誤")
        return

    res, err = await perform_currency_conversion(amount, src.upper(), tgt.upper())
    if err:
        await ctx.send(err)
    else:
        ref = ctx.message.reference
        author = ctx.author
        if ref:
            try: author = (await ctx.channel.fetch_message(ref.message_id)).author
            except: pass
        await ctx.send(f"{author.mention} : `{amount:,.2f} {src.upper()}` = `{res:,.2f} {tgt.upper()}`", reference=ref, mention_author=False)

# --- 10. !tr 翻譯指令 ---
@bot.command(name='tr', help="翻譯文字。")
async def tr(ctx, *args):
    if not args: return
    
    src, tgt, text_list = None, "zh-TW", list(args)
    
    if '-' in args[0] and not args[0].startswith('-'):
        parts = args[0].split('-')
        if len(parts) == 2:
            s, t = normalize_lang_code(parts[0]), normalize_lang_code(parts[1])
            if s and t:
                src, tgt = s, t
                text_list = args[1:]
    
    if not text_list: return
    text = " ".join(text_list)
    
    res, err = await perform_translation(text, tgt, src)
    
    if err:
        await ctx.send(err)
    else:
        ref = ctx.message.reference
        author = ctx.author
        if ref:
            try: author = (await ctx.channel.fetch_message(ref.message_id)).author
            except: pass
        await ctx.send(f"{author.mention} : {res}", reference=ref, mention_author=False)

# --- 11. 表情符號翻譯 ---
@bot.event
async def on_raw_reaction_add(payload):
    if payload.user_id == bot.user.id: return
    
    emoji = payload.emoji.name
    if emoji not in EMOJI_TO_LANGUAGE: return
    
    tgt = EMOJI_TO_LANGUAGE[emoji]
    
    try:
        channel = bot.get_channel(payload.channel_id)
        msg = await channel.fetch_message(payload.message_id)
        if not msg.content or msg.author.id == bot.user.id: return
        
        res, err = await perform_translation(msg.content, tgt)
        
        if not err:
            await channel.send(f"{msg.author.mention} : {res}", reference=msg, mention_author=False)
    except Exception as e:
        print(f"Reaction error: {e}")

# --- 12. 啟動 ---
try:
    keep_alive()
    bot.run(TOKEN)
except Exception as e:
    print(f"❌ 啟動錯誤: {e}")
