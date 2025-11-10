# --- 0. 導入必要的函式庫 ---
import os
from keep_alive import keep_alive
import json
import discord
import html  # 用於解碼 HTML 特殊字元 (例如 '&#39;')
import requests  # 用於貨幣轉換的 HTTP 請求
from discord.ext import commands
from google.cloud import translate_v2 as translate

# --- 1. 載入環境變數 (您的 Token) ---
TOKEN = os.getenv('DISCORD_TOKEN')
# 您的 .env 檔案中變數名稱是 'CURRENCY_API_key'
CURRENCY_API_key = os.getenv('CURRENCY_API_key')

if not TOKEN:
    print("❌ 錯誤:找不到 DISCORD_TOKEN。請檢查您的 .env 檔案。")
    exit()
if not CURRENCY_API_key:
    # 讓程式繼續運行,但在啟動時給予警告
    print("⚠️ 警告:找不到 CURRENCY_API_key。 !cc 匯率指令將無法運作。")

# --- 2. 初始化 Google Cloud Translation ---
try:
    # 從環境變數讀取 Google Cloud 憑證 JSON
    google_creds_json = os.getenv('GOOGLE_CLOUD_CREDENTIALS')

    if google_creds_json:
        # 將 JSON 字串解析為字典
        credentials_dict = json.loads(google_creds_json)

        # 使用 google.oauth2.service_account 從字典創建憑證
        from google.oauth2 import service_account
        credentials = service_account.Credentials.from_service_account_info(
            credentials_dict)

        # 使用憑證創建翻譯客戶端
        translate_client = translate.Client(credentials=credentials)
        print("✅ Google Cloud Translation API 認證成功!")
    elif os.path.exists('credentials.json'):
        # 向後兼容:如果環境變數不存在,但本地有 credentials.json,則使用它
        print(
            "⚠️ 警告:正在使用本地 credentials.json 檔案。建議將憑證移至環境變數 GOOGLE_CLOUD_CREDENTIALS。"
        )
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'credentials.json'
        translate_client = translate.Client()
        print("✅ Google Cloud Translation API 認證成功!")
    else:
        print(
            "⚠️ 警告:找不到 GOOGLE_CLOUD_CREDENTIALS 環境變數或 credentials.json 檔案。翻譯功能將無法運作。"
        )
        translate_client = None
except Exception as e:
    print(f"❌ Google API 認證失敗:{e}")
    translate_client = None

# --- 3. 設定 Discord 機器人權限 (Intents) ---
intents = discord.Intents.default()
intents.message_content = True  # 允許讀取訊息內容 (給 !tr 和 !cc 指令用)
intents.reactions = True  # 允許讀取表情符號反應

# 設定指令前綴為 '!'
bot = commands.Bot(command_prefix='!', intents=intents)

# --- 4. 建立代碼別名與清單 ---

# 語言代碼別名 (用於 !tr 指令)
LANGUAGE_ALIASES = {
    'zh(tw)': 'zh-TW',
    'tw': 'zh-TW',
    'zh-tw': 'zh-TW',
    'cn': 'zh-CN',
    'zh-cn': 'zh-CN',
    'zh': 'zh-CN',
    'jp': 'ja',
    'ja': 'ja',
    'en': 'en',
    'ko': 'ko',
    'kr': 'ko',
    'es': 'es',
    'fr': 'fr',
    'de': 'de',
    'vi': 'vi',
    'it': 'it',
    'ru': 'ru',
    'pt': 'pt',
    'ar': 'ar',
    'hi': 'hi',
    'id': 'id',
    'nl': 'nl',
    'sv': 'sv',
    'ru': 'ru',
    'tr': 'tr',
    'pl': 'pl',
}

# 支援的貨幣代碼 (用於 !cc 指令)
# 使用 set() 集合可以讓查詢速度更快 (O(1))
CURRENCY_CODES = set([
    'usd', 'eur', 'jpy', 'twd', 'cny', 'krw', 'gbp', 'aud', 'cad', 'chf',
    'hkd', 'sgd', 'inr', 'rub'
    # 您可以在此新增更多支援的貨幣代碼
])


def normalize_lang_code(code: str) -> str | None:
    """將 !tr 指令中的語言別名 (如 'jp') 轉換為標準代碼 (如 'ja')"""
    if not code:
        return None
    return LANGUAGE_ALIASES.get(code.lower(), None)


# --- 5. 建立表情符號 -> 語言的觸發器 ---
# 用於表情符號翻譯功能
EMOJI_TO_LANGUAGE = {
    # --- 標準 Unicode 表情符號 (範例) ---
    "🇹🇼": "zh-TW",  # 台灣 -> 繁中
    "🇯🇵": "ja",  # 日本 -> 日文
    "🇺🇸": "en",  # 美國 -> 英文
    "🇰🇷": "ko",  # 韓國 -> 韓文
    "🇨🇳": "zh-CN",  # 中國 -> 簡中
    "🇪🇸": "es",  # 西班牙 -> 西班牙文
    "🇫🇷": "fr",  # 法國 -> 法文

    # --- 您自訂的表情符號 (範例) ---
    # 'your_jp_emoji_name': 'ja',
}


# --- 6. 核心翻譯函式 ---
async def perform_translation(
        text_to_translate: str,
        target_lang_code: str,
        source_lang_code: str = None) -> tuple[str | None, str | None]:
    """
    執行翻譯。
    :return: (translated_text, None) 成功時
    :return: (None, error_message) 失敗時
    """
    if not translate_client:
        return None, "抱歉,翻譯服務 (Google API) 目前無法使用。"

    try:
        result = translate_client.translate(
            text_to_translate,
            target_language=target_lang_code,
            source_language=source_lang_code  # 若為 None,Google 會自動偵測
        )
        translated_text = html.unescape(result['translatedText'])
        return translated_text, None
    except Exception as e:
        print(f"翻譯時發生錯誤: {e}")
        return None, f"翻譯時發生錯誤。請確認您的語言代碼是否正確。\n錯誤訊息: `{e}`"


# --- 7. 核心匯率函式 ---
async def perform_currency_conversion(
        amount: float, source_currency: str,
        target_currency: str) -> tuple[float | None, str | None]:
    """
    執行貨幣轉換。
    :return: (converted_amount, None) 成功時
    :return: (None, error_message) 失敗時
    """
    if not CURRENCY_API_key:
        return None, "抱歉,匯率服務 (API Key) 尚未設定。"

    # 使用 ExchangeRate-API 的 /pair 端點
    request_str = f"https://v6.exchangerate-api.com/v6/{CURRENCY_API_key}/pair/{source_currency}/{target_currency}/{amount}"

    try:
        response = requests.get(request_str)
        response.raise_for_status()  # 如果狀態碼不是 200 (例如 404, 500),會在此拋出錯誤
        data = response.json()  # 自動解析 JSON

        if data.get('result') == 'success':
            conversion_result = data.get("conversion_result")
            if conversion_result is not None:
                return float(conversion_result), None
            else:
                # 雖然 result 是 'success' 但沒有 'conversion_result',這不應該發生
                return None, "API 回應中缺少 'conversion_result' 欄位。"
        else:
            # API 回應 'result' != 'success' (例如金鑰錯誤、貨幣代碼錯誤)
            error_type = data.get('error-type', '未知錯誤')
            return None, f"API 查詢失敗: {error_type}"

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP 錯誤: {http_err}")
        return None, f"API 請求失敗,請檢查您的貨幣代碼是否正確。 ({http_err})"
    except Exception as e:
        print(f"Error during exchange rate request: {e}")
        return None, f"請求時發生網路錯誤: {e}"


# --- 8. 機器人啟動事件 ---
@bot.event
async def on_ready():
    """當機器人成功連線到 Discord 時觸發"""
    print(f'✅ 機器人已登入為: {bot.user}')
    print(f'✅ 已載入 {len(EMOJI_TO_LANGUAGE)} 個表情符號翻譯觸發器。')
    print('------')
    if not translate_client:
        print("⚠️ 警告:Google 翻譯服務未啟動。")


# --- 9. 匯率轉換指令 !cc ---
@bot.command(
    name='cc',
    help=
    "轉換貨幣。\n用法 1: !cc <金額> (預設 JPY -> TWD)\n用法 2: !cc <來源-目標> <金額> (例如: !cc usd-twd 100)"
)
async def cc(ctx, *args):

    # --- 參數解析邏輯 ---
    source_currency_code = "jpy"  # 預設來源貨幣
    target_currency_code = "twd"  # 預設目標貨幣
    amount_to_convert_str = "1.0"  # 預設金額

    if not args:
        # 情況 1: !cc (沒有參數)
        # 使用所有預設值: 1.0 JPY -> TWD
        pass

    elif len(args) == 1:
        arg = args[0]
        if '-' in arg and not arg.startswith('-'):
            # 情況 2: !cc jpy-usd (只有貨幣對)
            parts = arg.split('-')
            if len(parts) == 2 and parts[0].lower(
            ) in CURRENCY_CODES and parts[1].lower() in CURRENCY_CODES:
                source_currency_code = parts[0]
                target_currency_code = parts[1]
                # amount_to_convert_str 保持 "1.0"
            else:
                # 情況 3: !cc 100 (只有金額)
                amount_to_convert_str = arg
                # source/target 保持預設 jpy-twd
        else:
            # 情況 3: !cc 100 (只有金額)
            amount_to_convert_str = arg
            # source/target 保持預設 jpy-twd

    elif len(args) >= 2:
        # 情況 4: !cc jpy-usd 100
        arg0 = args[0]
        arg1 = args[1]
        if '-' in arg0 and not arg0.startswith('-'):
            parts = arg0.split('-')
            if len(parts) == 2 and parts[0].lower(
            ) in CURRENCY_CODES and parts[1].lower() in CURRENCY_CODES:
                source_currency_code = parts[0]
                target_currency_code = parts[1]
                amount_to_convert_str = arg1
            else:
                await ctx.send("指令格式錯誤。請使用 `!cc <金額>` 或 `!cc <來源-目標> <金額>`")
                return
        # 情況 5: !cc 100 jpy-usd (順序顛倒)
        elif '-' in arg1 and not arg1.startswith('-'):
            parts = arg1.split('-')
            if len(parts) == 2 and parts[0].lower(
            ) in CURRENCY_CODES and parts[1].lower() in CURRENCY_CODES:
                source_currency_code = parts[0]
                target_currency_code = parts[1]
                amount_to_convert_str = arg0
            else:
                await ctx.send("指令格式錯誤。請使用 `!cc <金額>` 或 `!cc <來源-目標> <金額>`")
                return
        else:
            await ctx.send("指令格式錯誤。")
            return

    # --- 參數解析結束 ---

    # 嘗試將金額轉換為浮點數
    try:
        float_amount = float(amount_to_convert_str)
    except ValueError:
        await ctx.send(f"金額 '{amount_to_convert_str}' 不是一個有效的數字。")
        return

    # --- 呼叫核心函式 ---
    converted_amount, error = await perform_currency_conversion(
        float_amount, source_currency_code.upper(),
        target_currency_code.upper())

    if error:
        await ctx.send(error)
    else:
        # --- 回覆邏輯 ---
        reply_reference = ctx.message.reference
        author_to_mention = ctx.author

        if reply_reference:
            try:
                replied_to_message = await ctx.channel.fetch_message(
                    reply_reference.message_id)
                author_to_mention = replied_to_message.author
            except Exception as e:
                print(f"抓取被回覆的訊息時出錯: {e}")

        # 格式化訊息 (標記正確的人,並顯示轉換結果)
        response_message = (
            f"{author_to_mention.mention} : "
            f"`{float_amount:,.2f} {source_currency_code.upper()}` "
            f" = `{converted_amount:,.2f} {target_currency_code.upper()}`")

        await ctx.send(response_message,
                       reference=reply_reference,
                       mention_author=False)


# --- 10. 文字翻譯指令 !tr ---
@bot.command(
    name='tr',
    help=
    "翻譯文字。\n用法 1: !tr <要翻譯的文字> (自動偵測 -> 繁中)\n用法 2: !tr <來源-目標> <要翻譯的文字> (例如: !tr en-ja hello)"
)
async def tr(ctx, *args):

    if not args:
        await ctx.send(
            "請輸入要翻譯的文字。\n用法 1: `!tr <要翻譯的文字>`\n用法 2: `!tr <來源-目標> <要翻譯的文字>`")
        return

    # --- 參數解析 ---
    source_lang_code = None
    target_lang_code = "zh-TW"
    text_to_translate_list = list(args)
    first_arg = args[0]

    if '-' in first_arg and not first_arg.startswith('-'):
        parts = first_arg.split('-')
        if len(parts) == 2:
            temp_source = normalize_lang_code(parts[0])
            temp_target = normalize_lang_code(parts[1])
            if temp_source and temp_target:
                source_lang_code = temp_source
                target_lang_code = temp_target
                text_to_translate_list = list(args[1:])

    if not text_to_translate_list:
        await ctx.send("請在語言代碼後輸入要翻譯的文字。")
        return
    text_to_translate = " ".join(text_to_translate_list)
    # --- 參數解析結束 ---

    # --- 呼叫核心函式 ---
    translated_text, error = await perform_translation(text_to_translate,
                                                       target_lang_code,
                                                       source_lang_code)

    if error:
        await ctx.send(error)
    else:
        # --- 回覆邏輯 ---
        reply_reference = ctx.message.reference
        author_to_mention = ctx.author

        if reply_reference:
            try:
                replied_to_message = await ctx.channel.fetch_message(
                    reply_reference.message_id)
                author_to_mention = replied_to_message.author
            except Exception as e:
                print(f"抓取被回覆的訊息時出錯: {e}")

        response_message = f"{author_to_mention.mention} : {translated_text}"
        await ctx.send(response_message,
                       reference=reply_reference,
                       mention_author=False)


# --- 11. 表情符號翻譯監聽器 ---
@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    """
    當有使用者對「任何」訊息 (包含舊訊息) 加上表情符號時觸發
    """

    if payload.user_id == bot.user.id:
        return  # 忽略機器人自己的反應

    # .name 屬性對 Unicode (e.g. "🇹🇼") 和 自訂 (e.g. "my_jp_flag") 都有效
    trigger_key = payload.emoji.name

    if trigger_key not in EMOJI_TO_LANGUAGE:
        return  # 如果這個表情符號不在我們的字典中,就忽略

    target_lang_code = EMOJI_TO_LANGUAGE[trigger_key]

    try:
        # 抓取觸發事件的頻道和訊息
        channel = bot.get_channel(payload.channel_id)
        if not channel:
            return

        message = await channel.fetch_message(payload.message_id)
        text_to_translate = message.content

        if not text_to_translate:
            return  # 忽略沒有文字的訊息 (例如只有圖片)

        if message.author.id == bot.user.id:
            return  # 忽略對機器人自己訊息的反應

    except discord.errors.NotFound:
        print("找不到訊息 (可能已被刪除)")
        return
    except Exception as e:
        print(f"擷取訊息時發生錯誤: {e}")
        return

    member = payload.member  # member 是「按下表情符號的人」
    if not member:
        return

    # --- 呼叫核心函式 ---
    translated_text, error = await perform_translation(
        text_to_translate,
        target_lang_code,
        source_lang_code=None  # 自動偵測來源
    )

    if not error:
        # --- 回覆邏輯 ---
        # 標記「原始訊息的作者」 (例如 @開開)
        response_message = f"{message.author.mention} : {translated_text}"

        # 「回覆」那則原始訊息
        await channel.send(response_message,
                           reference=message,
                           mention_author=False)
    else:
        # 失敗時也一樣要回覆,並標記「按下表情符號的人」
        await channel.send(f"{member.mention},翻譯失敗: {error}",
                           reference=message,
                           mention_author=False)


# --- 12. 啟動機器人 ---
try:
    keep_alive()
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("❌ 登入失敗:Discord Token 不正確。請檢查 .env 檔案中的 DISCORD_TOKEN。")
except Exception as e:
    print(f"❌ 啟動時發生未預期的錯誤: {e}")
