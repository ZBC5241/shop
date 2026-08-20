#!/bin/bash
# ============================================================================
# start_tunnel.sh —— 李家村看板：把本地刷新服务(8765)穿透到公网
# 目的：手机在任何网络下点刷新键都能真拉用友实时数据
# 前置：Mac 已装 cloudflared（brew install cloudflared）
# 用法：
#   ① 零账号临时通道（推荐先跑通）：
#      REFRESH_TOKEN="$(openssl rand -hex 16)" bash start_tunnel.sh
#   ② 固定域名通道（域名永久不变，需先 cloudflared login + tunnel create）：
#      REFRESH_TOKEN="你的令牌" bash start_tunnel.sh --named ljc-shop
# 安全：REFRESH_TOKEN 仅经环境变量传入，绝不写进脚本/仓库
# ============================================================================
set -e
BASE="$(cd "$(dirname "$0")" && pwd)"
PORT=8765

# 0) 检查 cloudflared
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "❌ 未安装 cloudflared，先执行：  brew install cloudflared"
  exit 1
fi

# 1) 鉴权令牌（不设则公网无保护，强烈建议随机生成）
if [ -z "$REFRESH_TOKEN" ]; then
  echo "⚠️  未设置 REFRESH_TOKEN，公网将无鉴权！建议这样启动："
  echo "   REFRESH_TOKEN=\"$(openssl rand -hex 16)\" bash start_tunnel.sh"
  echo "   继续以无鉴权模式启动（仅本机回环相对安全，公网暴露有风险）…"
fi

# 2) 保活刷新服务（带令牌；服务未起才拉起）
if ! curl -s -o /dev/null "http://127.0.0.1:$PORT/status" 2>/dev/null; then
  echo "▶ 启动刷新服务(8765)…"
  REFRESH_TOKEN="$REFRESH_TOKEN" nohup python3 "$BASE/refresh_server.py" \
    > "$BASE/.refresh_server.log" 2>&1 &
  sleep 2
  if ! curl -s -o /dev/null "http://127.0.0.1:$PORT/status" 2>/dev/null; then
    echo "❌ 刷新服务启动失败，看日志： tail -20 $BASE/.refresh_server.log"
    exit 1
  fi
  echo "   ✅ 刷新服务在线"
else
  echo "   ℹ️  刷新服务已在运行"
fi

# 3) 启动穿透
if [ "$1" = "--named" ] && [ -n "$2" ]; then
  NAME="$2"
  echo "▶ 固定域名隧道启动（需已 cloudflared login 且 tunnel create $NAME）"
  echo "   域名将固定为 $NAME.cfargotunnel.com"
  cloudflared tunnel run "$NAME"
else
  echo "▶ quick tunnel 启动（零账号，域名每次重启会变）…"
  echo "   下面会出现 https://xxxx.trycloudflare.com ，复制它"
  cloudflared tunnel --url "http://localhost:$PORT"
fi
