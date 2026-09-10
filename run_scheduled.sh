#!/bin/bash
# run_scheduled.sh —— 由 launchd 定时触发，按排期分发推送模式
# 排期（2026-09-10 晨哥更新：下午3档进度+闭店催账+深夜收官）：
#   14:07  progress  进度推送①
#   18:07  progress  进度推送②
#   20:07  progress  进度推送③
#   22:33  check     闭店上账检查（0上账催账）
#   23:31  report    今日收官战报（无救援卡）
# 注：22:43 日清日结、库存每15分钟为独立 plist（guobu/kucunos）
SHOP_DIR="/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/shop"
SCRIPT="$SHOP_DIR/daily_push.sh"

H=$(date +%H)
M=$(date +%M)

case "$H:$M" in
  14:07|18:07|20:07) MODE="progress" ;;
  22:33)  "${SCRIPT}" check; exit 0 ;;
  23:31)  MODE="report" ;;
  *)      MODE="report" ;;
esac

"$SCRIPT" push "$MODE"
