#!/bin/bash
# run_scheduled.sh —— 由 launchd 定时触发，按排期分发推送模式
# 排期（2026-09-16 晨哥定稿"去刷屏"）：
#   14:07  progress  静默档（SKIP_WECOM=1：只上线看板，不推群）
#   18:07  progress  静默档
#   20:07  progress  静默档
#   22:27  progress  静默档
#   22:47  progress  静默档
#   23:01  report    收官战报（企微推群）
# 注：22:43 日清日结、库存每15分钟为独立 plist（guobu/kucunos）
# 变更历史：2026-09-13 撤 22:33 check 档；2026-09-13 23:18 收官 23:31→23:01；
#           2026-09-16 晨哥"去刷屏"定稿：进度档全部静默；
#           2026-09-24 11:50 17号重建（01:38 工作区文件被回滚成 9/10 版导致定时档将复推群，已纠正）
SHOP_DIR="/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/shop"
SCRIPT="$SHOP_DIR/daily_push.sh"

H=$(date +%H)
M=$(date +%M)

case "$H:$M" in
  14:07|18:07|20:07) MODE="progress"; export SKIP_WECOM=1 ;;
  22:27|22:47)       MODE="progress"; export SKIP_WECOM=1 ;;
  23:01)  MODE="report" ;;
  *)      MODE="report" ;;
esac

"$SCRIPT" push "$MODE"
