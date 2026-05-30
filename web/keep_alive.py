# -*- coding: utf-8 -*-
"""
PongPong Bot — Keep-Alive Web 伺服器
提供 Flask 健康檢查端點，供 Render / UptimeRobot 使用
"""

from flask import Flask, jsonify
from threading import Thread
import os
import time

app = Flask('')
_bot_ref = None
_start_time = time.time()


@app.route('/')
def home():
    return "PongPong Bot is alive! 🏓"


@app.route('/health')
def health():
    """健康檢查端點"""
    return jsonify({
        'status': 'healthy',
        'uptime_seconds': int(time.time() - _start_time),
        'version': 'v2.0'
    })


@app.route('/api/status')
def api_status():
    """Bot 狀態 API（供網站顯示用）"""
    data = {
        'status': 'online',
        'uptime_seconds': int(time.time() - _start_time),
        'version': 'v2.0',
    }
    if _bot_ref and _bot_ref.is_ready():
        data['guilds'] = len(_bot_ref.guilds)
        data['users'] = sum(g.member_count or 0 for g in _bot_ref.guilds)
        data['latency_ms'] = round(_bot_ref.latency * 1000, 1)
    return jsonify(data)


def _run():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)


def keep_alive(bot=None):
    """在背景執行緒啟動 Flask 伺服器"""
    global _bot_ref
    _bot_ref = bot
    t = Thread(target=_run, daemon=True)
    t.start()
