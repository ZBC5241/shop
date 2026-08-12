#!/bin/bash
# start_refresh_server.sh —— 启动看板本地刷新服务（常驻后台）
# 用途：让看板页面的「刷新键」能跑全流程自动拉数。
# 重启电脑后重新跑一次本脚本即可。
BASE="/Users/mac/WorkBuddy/Claw"
PIDF="$BASE/.refresh_server.pid"
PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3)"

# 已在跑则跳过
if [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  echo "✅ 刷新服务已在运行 (pid $(cat "$PIDF"))"
  exit 0
fi

cd "$BASE"
nohup "$PY" refresh_server.py > "$BASE/.refresh_server.log" 2>&1 &
echo $! > "$PIDF"
sleep 1
if kill -0 "$(cat "$PIDF")" 2>/dev/null; then
  echo "🚀 刷新服务已启动： http://localhost:8765/refresh  (pid $(cat "$PIDF"))"
  echo "   日志： $BASE/.refresh_server.log"
else
  echo "❌ 启动失败，查看日志："
  tail -20 "$BASE/.refresh_server.log"
fi
