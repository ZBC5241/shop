#!/bin/bash
# notify.sh —— 提醒通道
# 用法: notify.sh "<标题>" "<内容>"
# 默认走 macOS 系统通知；如需企业微信群机器人，在 WECOM_WEBHOOK 里填 webhook 地址即可自动同步推送
set -e
TITLE="${1:-李家村门店提醒}"
BODY="${2:-}"
BASE="/Users/mac/WorkBuddy/Claw"

# 1) macOS 系统通知（本机弹窗，最稳）
osascript -e "display notification \"$BODY\" with title \"$TITLE\"" 2>/dev/null || true
echo "🔔 系统通知已发送: $TITLE — $BODY"

# 2) 企业微信群机器人（可选；WECOM_WEBHOOK 环境变量优先，否则读 .wecom_webhook 配置）
WEBHOOK="${WECOM_WEBHOOK:-}"
if [ -z "$WEBHOOK" ] && [ -f "$BASE/.wecom_webhook" ]; then
  WEBHOOK="$(cat "$BASE/.wecom_webhook")"
fi
if [ -n "$WEBHOOK" ]; then
  /usr/bin/curl -s -o /dev/null -X POST "$WEBHOOK" \
    -H "Content-Type: application/json" \
    -d "{\"msgtype\":\"text\",\"text\":{\"content\":\"【$TITLE】\n$BODY\"}}" \
    && echo "📲 企业微信已推送" || echo "⚠️ 企业微信推送失败"
fi
