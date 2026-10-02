#!/bin/bash
# ============================================================
# sync_xs_scheduled.sh —— 底表 XS 专职同步（launchd 定时触发）
# 建：2026-10-03（18号，晨哥指令"把底表断更问题彻底解决"）
#
# 背景：shop 旧 dailypush（14:07/18:07... 六档）10-01 被停后，
#       storyos fetch_round 是 --no-xs 模式、不写底表 → 底表 XS
#       明细断更（10-02 数据缺失，杨丽华增值等底表公式算不全）。
#
# 方案：沿用旧 dailypush 档位，专职调 write_xs_xml.py（XML 级
#       原位替换，零公式/条件格式损伤，写前自动备份）把最新明细
#       喂进底表 XS。
#       不拉数（直接用 storyos fetch_round 每15分钟刷新的明细缓存）、
#       不重算、不推送 —— 与 storyos/shop 链路零冲突，单次约 6 秒。
#
# 档位（com.lijiacun.dashboard.xssync，同旧 dailypush）：
#   14:07 / 18:07 / 20:07 / 22:27 / 22:47 / 23:01
# ============================================================
set -u
SHOP="/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/shop"
DL="/Users/mac/.local/share/TeleAgent/playwright-mcp"
PROFIT="$DL/ljc/李家村门店毛利明细表-华为终端.xlsx"
LOG="$SHOP/logs/xssync.log"
NOTIFY="$SHOP/notify_fail.py"
PY="/Users/mac/.local/share/TeleAgent/runtimes/python/bin/python3"
export HOME=/Users/mac
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
mkdir -p "$(dirname "$LOG")"
[ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 1048576 ] && : > "$LOG"

# ---- 互斥锁（mkdir 原子锁，stale 10min 自动释放）----
LOCK_DIR="/tmp/ljc_xssync.lock.d"
if [ -d "$LOCK_DIR" ]; then
  if [ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then
    rm -rf "$LOCK_DIR"
  else
    echo "🔒 上一轮仍在运行，跳过 $(date '+%F %T')" >> "$LOG"
    exit 0
  fi
fi
mkdir "$LOCK_DIR" 2>/dev/null || exit 0
trap 'rm -rf "$LOCK_DIR" 2>/dev/null' EXIT

{
  echo "── 底表XS同步 · $(date '+%F %T') ──"
  if [ ! -f "$PROFIT" ]; then
    echo "❌ 明细缓存不存在: $PROFIT"
    exit 1
  fi
  AGE=$(( $(date +%s) - $(stat -f%m "$PROFIT") ))
  echo "  明细缓存: $(basename "$PROFIT") | 更新于 ${AGE}s 前"
  cd "$SHOP"
  "$PY" write_xs_xml.py "$PROFIT"
  RC=$?
  echo "  write_xs_xml RC=$RC"
  exit "$RC"
} >> "$LOG" 2>&1
RC=$?
if [ "$RC" -ne 0 ]; then
  /usr/bin/python3 "$NOTIFY" --stage "底表XS同步" --exit-code "$RC" --log "$LOG" --tail 10 >> "$LOG" 2>&1
fi
exit "$RC"
