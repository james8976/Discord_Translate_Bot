# -*- coding: utf-8 -*-
"""
PongPong Bot — Keep-Alive Web 伺服器
提供 Flask 健康檢查端點 + Spotify OAuth 回呼端點
支援 HTTPS（自動偵測 SSL 憑證）
"""

from flask import Flask, jsonify, request
from threading import Thread
import os
import time
import json
import urllib.request
import urllib.parse
import threading
import ssl

app = Flask('')
_bot_ref = None
_start_time = time.time()

# ══════════════════════════════════════════════════════════════
#  Spotify OAuth — 共享 Token 儲存
# ══════════════════════════════════════════════════════════════
_pending_tokens: dict[str, dict] = {}  # state -> {token_data, timestamp}
_token_lock = threading.Lock()
_TOKEN_TTL = 300  # 5 分鐘後自動清除未領取的 token


def get_pending_token(state: str) -> dict | None:
    """取出待處理的 token（取出後刪除）— 供 cog 呼叫"""
    with _token_lock:
        entry = _pending_tokens.pop(state, None)
        if entry and time.time() - entry.get('_stored_at', 0) < _TOKEN_TTL:
            entry.pop('_stored_at', None)  # 移除內部時間戳
            return entry
        return None


def _store_token(state: str, token_data: dict):
    """儲存 token（帶時間戳，過期自動清除）"""
    with _token_lock:
        # 清除過期的 token 避免記憶體洩漏
        now = time.time()
        expired = [k for k, v in _pending_tokens.items()
                   if now - v.get('_stored_at', 0) > _TOKEN_TTL]
        for k in expired:
            del _pending_tokens[k]
        token_data['_stored_at'] = now
        _pending_tokens[state] = token_data


# ── 成功頁面 HTML ──────────────────────────────────────────
SUCCESS_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PongPong Radio - 登入成功</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'Segoe UI', -apple-system, sans-serif;
    background: #121212;
    color: #fff;
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
  }
  .card {
    text-align: center;
    padding: 48px 40px;
    background: linear-gradient(145deg, #1a1a2e 0%, #16213e 100%);
    border-radius: 20px;
    border: 1px solid rgba(29, 185, 84, 0.3);
    box-shadow: 0 20px 60px rgba(0,0,0,0.5), 0 0 40px rgba(29,185,84,0.1);
    max-width: 420px;
    width: 90%;
    animation: fadeIn 0.6s ease;
  }
  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(20px); }
    to { opacity: 1; transform: translateY(0); }
  }
  .check { font-size: 64px; margin-bottom: 16px; }
  h2 { font-size: 24px; margin-bottom: 12px; color: #1DB954; }
  p { font-size: 16px; color: #b3b3b3; line-height: 1.6; }
  .brand { color: #1DB954; font-weight: 600; }
  .hint { font-size: 13px; color: #666; margin-top: 24px; }
</style>
</head>
<body>
<div class="card">
  <div class="check">✅</div>
  <h2>Spotify 登入成功！</h2>
  <p>你的帳號已連接到<br><span class="brand">🎵 PongPong Radio</span></p>
  <p style="margin-top: 16px;">請回到 <strong>Discord</strong> 查看 ✨</p>
  <p class="hint">此頁面可以安全關閉</p>
</div>
</body>
</html>"""

ERROR_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>PongPong Radio - 錯誤</title>
<style>
  body {{
    font-family: 'Segoe UI', sans-serif;
    background: #121212; color: #fff;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh;
  }}
  .card {{
    text-align: center; padding: 48px 40px;
    background: #1a1a2e; border-radius: 20px;
    border: 1px solid rgba(237,66,69,0.3);
    max-width: 420px; width: 90%;
  }}
  h2 {{ color: #ED4245; }}
  p {{ color: #b3b3b3; margin-top: 12px; }}
</style>
</head>
<body>
<div class="card">
  <div style="font-size:64px">❌</div>
  <h2>驗證失敗</h2>
  <p>{message}</p>
  <p style="margin-top:16px;font-size:13px;color:#666">請回到 Discord 重新使用 /spotify connect</p>
</div>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════
#  Routes
# ══════════════════════════════════════════════════════════════

@app.route('/')
def home():
    return "PongPong Bot is alive! 🏓"


@app.route('/health')
def health():
    return jsonify({
        'status': 'healthy',
        'uptime_seconds': int(time.time() - _start_time),
        'version': 'v2.2'
    })


@app.route('/api/status')
def api_status():
    data = {
        'status': 'online',
        'uptime_seconds': int(time.time() - _start_time),
        'version': 'v2.2',
    }
    if _bot_ref and _bot_ref.is_ready():
        data['guilds'] = len(_bot_ref.guilds)
        data['users'] = sum(g.member_count or 0 for g in _bot_ref.guilds)
        data['latency_ms'] = round(_bot_ref.latency * 1000, 1)
    return jsonify(data)


# ── Spotify OAuth 回呼 ─────────────────────────────────────
@app.route('/spotify/callback')
def spotify_callback():
    """接收 Spotify OAuth 授權回呼"""
    code = request.args.get('code')
    state = request.args.get('state')
    error = request.args.get('error')

    if error:
        return ERROR_HTML_TEMPLATE.format(message=f'Spotify 回傳錯誤：{error}'), 400

    if not code or not state:
        return ERROR_HTML_TEMPLATE.format(message='缺少必要的授權參數'), 400

    try:
        import config
        token_url = 'https://accounts.spotify.com/api/token'
        post_data = urllib.parse.urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': config.SPOTIFY_REDIRECT_URI,
            'client_id': config.SPOTIFY_CLIENT_ID,
            'client_secret': config.SPOTIFY_CLIENT_SECRET,
        }).encode('utf-8')

        req = urllib.request.Request(
            token_url,
            data=post_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )

        with urllib.request.urlopen(req, timeout=15) as resp:
            token_data = json.loads(resp.read().decode('utf-8'))

        if 'access_token' not in token_data:
            return ERROR_HTML_TEMPLATE.format(message='未取得有效的 access token'), 500

        _store_token(state, token_data)
        return SUCCESS_HTML

    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='ignore')
        return ERROR_HTML_TEMPLATE.format(
            message=f'Token 交換失敗 (HTTP {e.code}): {body[:200]}'
        ), 500
    except Exception as e:
        return ERROR_HTML_TEMPLATE.format(
            message=f'伺服器內部錯誤: {str(e)[:200]}'
        ), 500


# ── Token 中繼（供外部 HTTPS 回呼使用）──────────────────────
@app.route('/spotify/token-relay', methods=['POST'])
def spotify_token_relay():
    """接收從外部 HTTPS 回呼轉發的 token"""
    try:
        data = request.get_json()
        state = data.get('state')
        if state and 'access_token' in data:
            _store_token(state, data)
            return jsonify({'ok': True})
        return jsonify({'error': 'missing data'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ══════════════════════════════════════════════════════════════

def _run():
    port = int(os.environ.get('PORT', 8080))

    # 自動偵測 SSL 憑證
    bot_dir = os.path.dirname(os.path.dirname(__file__))
    cert_file = os.path.join(bot_dir, 'certs', 'fullchain.pem')
    key_file = os.path.join(bot_dir, 'certs', 'key.pem')

    if os.path.exists(cert_file) and os.path.exists(key_file):
        # HTTPS 模式
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
        app.run(host='0.0.0.0', port=port, ssl_context=context)
    else:
        # HTTP 模式（無 SSL 憑證）
        app.run(host='0.0.0.0', port=port)


def keep_alive(bot=None):
    """在背景執行緒啟動 Flask 伺服器"""
    global _bot_ref
    _bot_ref = bot
    t = Thread(target=_run, daemon=True)
    t.start()
