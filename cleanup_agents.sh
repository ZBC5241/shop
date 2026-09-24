#!/bin/bash
# cleanup_agents.sh —— 17号/18号双智能体磁盘保鲜清理（晨哥说"清理垃圾"时手动跑，无定时任务）
# 原则：只清可再生垃圾（快照/旧导出/日志/缓存），核心资产不动（长期记忆/脚本/登录态/底表）。
# 用法：bash cleanup_agents.sh          实际清理
#       bash cleanup_agents.sh --dry-run   只预览不删除
set -u
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
now=$(date +%s)

TA="/Users/mac/.local/share/TeleAgent"
WB="/Users/mac/WorkBuddy"
KUCUNOS="$WB/2026-08-31-14-14-00/kucunos"
TOTAL=0

hr() { # bytes -> MB
  echo $(( $1 / 1024 / 1024 ))MB
}
del_files() { # $1=目录 $2=天数 $3=描述 $4=文件名pattern(可选)
  local dir="$1" days="$2" desc="$3" pat="${4:-*}"
  [ -d "$dir" ] || { echo "  ⊘ $desc：目录不存在，跳过"; return; }
  local freed=0
  while IFS= read -r -d '' f; do
    local sz=$(stat -f%z "$f" 2>/dev/null || echo 0)
    freed=$((freed + sz))
    if [ "$DRY" = "0" ]; then rm -f "$f"; fi
  done < <(find "$dir" -name "$pat" -type f -mtime +"$days" -print0 2>/dev/null)
  echo "  ✓ $desc：清 mtime>+${days}d，回收 $(hr $freed)"
  TOTAL=$((TOTAL + freed))
}
del_dir() { # $1=目录 $2=描述
  local dir="$1" desc="$2"
  [ -e "$dir" ] || { echo "  ⊘ $desc：不存在，跳过"; return; }
  local sz=$(du -sk "$dir" 2>/dev/null | cut -f1)
  [ -z "$sz" ] && sz=0
  if [ "$DRY" = "0" ]; then rm -rf "$dir"; fi
  echo "  ✓ $desc：回收 $((sz / 1024))MB"
  TOTAL=$((TOTAL + sz * 1024))
}

echo "═══ A档：TeleAgent 可再生垃圾 ═══"
del_files "$TA/Cache" 7 "应用缓存 Cache"
del_files "$TA/log" 3 "运行日志 log"
del_files "$TA/js-log" 3 "js-log(.old.log)" "*.old.log"
del_files "$TA/js-log" 7 "js-log(7天前)"
del_files "$TA/.temp" 7 "工作空间 .temp"
del_files "$TA/TeleAgent的工作空间/.temp" 7 "shop .temp"
del_files "$TA/TeleAgent的工作空间/shop/.temp" 7 "shop/.temp"
del_files "$TA/playwright-mcp" 14 "playwright-mcp 截图/快照"
del_files "$TA/playwright-mcp" 14 "playwright-mcp 日志" "*.log"

echo ""
echo "═══ B档：旧数据快照 ═══"
del_files "$WB/Claw" 14 "Claw 现存量CSV(>14天)" "现存量_*.csv"
del_files "$WB/Claw" 14 "Claw 收据CSV(>14天)" "收据_*.csv"
# 旧 sa_warehouse.json：按 mtime，30天未更新视为死副本
del_files "$WB/Claw" 30 "Claw 旧 sa_warehouse.json" "sa_warehouse.json"

echo ""
echo "═══ C档：git gc 压缩（不丢历史） ═══"
for repo in "$KUCUNOS" "/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/shop"; do
  if [ -d "$repo/.git" ]; then
    local_before=$(du -sk "$repo/.git" 2>/dev/null | cut -f1)
    [ -z "$local_before" ] && local_before=0
    if [ "$DRY" = "0" ]; then
      git -C "$repo" gc --prune=now >/dev/null 2>&1
    fi
    local_after=$(du -sk "$repo/.git" 2>/dev/null | cut -f1)
    [ -z "$local_after" ] && local_after=$local_before
    echo "  ✓ $(basename $repo)：.git ${local_before}K -> ${local_after}K"
  fi
done

echo ""
echo "═══ 永不清理（核心资产，仅提醒） ═══"
echo "  · 长期记忆: $TA/memory"
echo "  · 工作空间/脚本: $TA/TeleAgent的工作空间"
echo "  · 用友登录态: ~/.agent-browser/sessions"
echo "  · 桌面底表: ~/Desktop/李家村销售/"
echo "  · kucunos 现役CSV: $KUCUNOS/现存量_*.csv（当天数据）"
echo ""
if [ "$DRY" = "1" ]; then
  echo "（预览模式，未实际删除）"
fi
echo "═══ 本次合计回收：$(hr $TOTAL) ═══"
