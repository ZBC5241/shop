#!/bin/bash
# daily_push.sh —— 门店每日战报推送全流程
# 用法: ./daily_push.sh [push|check] [task|progress|report]
#   push                       = 拉数据→处理→看板上线→智能选片推送（默认）
#   push task                  = 推送「今日任务」卡片
#   push progress              = 推送「当日达成进度」卡片
#   push report                = 推送「今日总达成」战报（无救援卡）
#   check                      = 仅检查不上账并推送提醒
#
# 定时任务时间点（新排期 2026-09-01）：
#   10:00  push task      今日任务
#   12:00  push progress  当日进度
#   16:00  push progress  当日进度
#   20:00  push progress  当日进度
#   22:00  push progress  当日进度
#   22:45  push report    今日总达成战报

set -e -o pipefail

PYTHON="/Users/mac/.local/share/TeleAgent/runtimes/python/bin/python3"
SHOP_DIR="/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/shop"
FETCH_SCRIPT="$SHOP_DIR/fetch_yonyou_fast.py"
PIPELINE_SCRIPT="$SHOP_DIR/run_pipeline.py"
PUSH_SCRIPT="$SHOP_DIR/push_card.py"
DOWNLOAD_DIR="/Users/mac/.local/share/TeleAgent/playwright-mcp"
TODAY=$(date +%m%d)

MODE="${1:-push}"
CARD_MODE="${2:-}"
PUSH_ARGS=""
if [ -n "$CARD_MODE" ]; then
  PUSH_ARGS="--mode=$CARD_MODE"
fi

# ---- 失败告警：跟踪当前环节，异常退出自动推企微告警 ----
STAGE="启动"
ALERT_SCRIPT="$SHOP_DIR/alert_failure.py"
on_exit() {
  local code=$1
  if [ "$code" -ne 0 ]; then
    echo "" >&2
    echo "🚨 检测到失败（环节: $STAGE，退出码 $code），推送企微告警..." >&2
    "${PYTHON}" "${ALERT_SCRIPT}" --stage "${MODE}: ${STAGE}" --exit-code "$code" \
      || echo "  ⚠️ 告警推送也失败（网络/webhook异常），详见日志" >&2
  fi
}
trap 'on_exit $?' EXIT

echo "================================================"
echo "  门店战报推送 · $(date '+%Y-%m-%d %H:%M:%S')"
echo "  模式: $MODE"
echo "================================================"

if [ "$MODE" = "check" ]; then
    # 不上账检查模式：先拉数据，再检查
    echo ""
    echo "▶ 1. 拉取用友云数据"
    STAGE="1.拉取用友云数据"
    eval $("${PYTHON}" "${FETCH_SCRIPT}" --account store 2>&1 | grep "^PROFIT_FILE\|^SALES_FILE")
    echo "  ✅ 毛利明细表: ${PROFIT_FILE##*/}"
    echo "  ✅ 销售分析: ${SALES_FILE##*/}"

    echo ""
    echo "▶ 2. 处理数据 + 更新看板"
    STAGE="2.处理数据+更新看板"
    "${PYTHON}" "${PIPELINE_SCRIPT}" "${PROFIT_FILE}" "${SALES_FILE}" --no-push 2>&1 | tail -5

    echo ""
    echo "▶ 3. 检查不上账"
    STAGE="3.检查不上账"
    "${PYTHON}" "${PUSH_SCRIPT}" --check-no-data

    STAGE="完成"
    echo ""
    echo "================================================"
    echo "  ✅ 不上账检查完成 · $(date '+%H:%M:%S')"
    echo "================================================"
    exit 0
fi

# 默认 push 模式
echo ""
echo "▶ 1. 拉取用友云数据（店长账号）"
STAGE="1.拉取用友云数据"
eval $("${PYTHON}" "${FETCH_SCRIPT}" --account store 2>&1 | grep "^PROFIT_FILE\|^SALES_FILE")
echo "  ✅ 毛利明细表: ${PROFIT_FILE##*/}"
echo "  ✅ 销售分析: ${SALES_FILE##*/}"
if [ -z "$PROFIT_FILE" ] || [ -z "$SALES_FILE" ] || [ ! -f "$PROFIT_FILE" ] || [ ! -f "$SALES_FILE" ]; then
  echo "  ❌ 导出失败（文件缺失），终止推送，避免推送旧数据"
  exit 1
fi

echo ""
echo "▶ 2. 处理数据 + 生成看板 + 推送GitHub上线"
STAGE="2.处理数据+生成看板+推送上线"
"${PYTHON}" "${PIPELINE_SCRIPT}" "${PROFIT_FILE}" "${SALES_FILE}" 2>&1 | tail -10

echo ""
echo "▶ 3. 推送卡片（模式: ${CARD_MODE:-智能选片}）"
STAGE="3.推送卡片"
"${PYTHON}" "${PUSH_SCRIPT}" ${PUSH_ARGS}

STAGE="完成"
echo ""
echo "================================================"
echo "  ✅ 全流程完成 · $(date '+%H:%M:%S')"
echo "================================================"
