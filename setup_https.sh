#!/bin/bash
# ══════════════════════════════════════════════════════════════
# PongPong Bot — HTTPS 設定腳本
# 使用 DuckDNS + acme.sh 取得免費 SSL 憑證
# ══════════════════════════════════════════════════════════════

set -e

echo "╔══════════════════════════════════════════╗"
echo "║   PongPong Bot — HTTPS 設定助手          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. 取得參數 ─────────────────────────────────────────
if [ -z "$1" ] || [ -z "$2" ]; then
    echo "使用方式："
    echo "  bash setup_https.sh <duckdns子域名> <duckdns_token>"
    echo ""
    echo "範例："
    echo "  bash setup_https.sh pongpong-bot abc12345-6789-0000-1111-222233334444"
    echo ""
    echo "步驟："
    echo "  1. 去 https://www.duckdns.org 免費註冊"
    echo "  2. 新增一個子域名（例如 pongpong-bot）"
    echo "  3. 將你的 VM IP 155.248.173.141 設為該子域名的 IP"
    echo "  4. 複製你的 DuckDNS token"
    echo "  5. 執行本腳本"
    exit 1
fi

SUBDOMAIN="$1"
DUCKDNS_TOKEN="$2"
DOMAIN="${SUBDOMAIN}.duckdns.org"
BOT_DIR="$HOME/bot"
CERT_DIR="$BOT_DIR/certs"

echo "🔧 域名: ${DOMAIN}"
echo "🔧 Bot 目錄: ${BOT_DIR}"
echo ""

# ── 2. 更新 DuckDNS IP ─────────────────────────────────
echo "📡 [1/4] 更新 DuckDNS IP..."
RESULT=$(curl -s "https://www.duckdns.org/update?domains=${SUBDOMAIN}&token=${DUCKDNS_TOKEN}&ip=")
if [ "$RESULT" = "OK" ]; then
    echo "  ✅ DuckDNS IP 已更新"
else
    echo "  ❌ DuckDNS 更新失敗，請檢查子域名和 token"
    exit 1
fi

# ── 3. 安裝 acme.sh ────────────────────────────────────
echo ""
echo "📦 [2/4] 安裝 acme.sh..."
if [ ! -d "$HOME/.acme.sh" ]; then
    curl -sL https://get.acme.sh | sh -s email=pongpong@bot.local
    echo "  ✅ acme.sh 已安裝"
else
    echo "  ✅ acme.sh 已存在"
fi

# ── 4. 取得 SSL 憑證（DNS 驗證，不需要開 port 80）───────
echo ""
echo "🔐 [3/4] 取得 Let's Encrypt SSL 憑證..."
export DuckDNS_Token="${DUCKDNS_TOKEN}"

$HOME/.acme.sh/acme.sh --issue \
    --dns dns_duckdns \
    -d "${DOMAIN}" \
    --server letsencrypt \
    --force \
    2>&1 | tail -5

# ── 5. 安裝憑證到 bot/certs ────────────────────────────
echo ""
echo "📂 [4/4] 安裝憑證..."
mkdir -p "$CERT_DIR"

$HOME/.acme.sh/acme.sh --install-cert -d "${DOMAIN}" \
    --cert-file "${CERT_DIR}/cert.pem" \
    --key-file "${CERT_DIR}/key.pem" \
    --fullchain-file "${CERT_DIR}/fullchain.pem" \
    2>&1 | tail -3

# ── 6. 更新 .env ───────────────────────────────────────
echo ""
echo "📝 更新 .env 設定..."

# 移除舊的 SPOTIFY_REDIRECT_URI（如果有）
if grep -q "SPOTIFY_REDIRECT_URI" "$BOT_DIR/.env" 2>/dev/null; then
    sed -i '/SPOTIFY_REDIRECT_URI/d' "$BOT_DIR/.env"
fi

# 新增 HTTPS redirect URI
echo "SPOTIFY_REDIRECT_URI=https://${DOMAIN}:8080/spotify/callback" >> "$BOT_DIR/.env"
echo "  ✅ 已新增 SPOTIFY_REDIRECT_URI=https://${DOMAIN}:8080/spotify/callback"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ HTTPS 設定完成！                                      ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  🌐 你的 HTTPS 網址：                                     ║"
echo "║     https://${DOMAIN}:8080                               ║"
echo "║                                                          ║"
echo "║  📋 接下來你需要做的：                                     ║"
echo "║                                                          ║"
echo "║  1️⃣  去 Spotify Developer Dashboard:                      ║"
echo "║     https://developer.spotify.com/dashboard              ║"
echo "║     → 你的 App → Settings → Redirect URIs               ║"
echo "║     → 刪除舊的 http://... URI                            ║"
echo "║     → 新增：                                             ║"
echo "║     https://${DOMAIN}:8080/spotify/callback              ║"
echo "║                                                          ║"
echo "║  2️⃣  重啟 Bot：                                           ║"
echo "║     sudo systemctl restart pongpong                      ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
