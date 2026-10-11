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
    # 拉数文件隔离（防 storyos 每5分钟拉数覆盖共享下载目录，见 push 模式注释）
    RAW_DIR="$SHOP_DIR/data_raw"
    mkdir -p "$RAW_DIR"
    [ -n "$PROFIT_FILE" ] && [ -f "$PROFIT_FILE" ] && cp -f "$PROFIT_FILE" "$RAW_DIR/门店毛利明细表-华为终端.xlsx" && PROFIT_FILE="$RAW_DIR/门店毛利明细表-华为终端.xlsx"
    [ -n "$SALES_FILE" ] && [ -f "$SALES_FILE" ] && cp -f "$SALES_FILE" "$RAW_DIR/销售分析.xlsx" && SALES_FILE="$RAW_DIR/销售分析.xlsx"

    echo ""
    echo "▶ 2. 处理数据 + 更新看板"
    STAGE="2.处理数据+更新看板"
    "${PYTHON}" "${PIPELINE_SCRIPT}" "${PROFIT_FILE}" "${SALES_FILE}" --no-push 2>&1 | tail -5

    echo ""
    echo "▶ 3. 检查不上账"
    STAGE="3.检查不上账"
    if [ "${SKIP_WECOM:-1}" = "1" ]; then
      echo "    （SKIP_WECOM=1，不上账提醒仅本地检查，不推企微群）"
      "${PYTHON}" "${PUSH_SCRIPT}" --check-no-data --dry
    else
      "${PYTHON}" "${PUSH_SCRIPT}" --check-no-data
    fi

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

# ---- 拉数文件隔离（2026-10-11 23:45 事故修复）----
# playwright-mcp 下载目录与 storyos（多店看板，每5分钟拉数）共享同名文件，
# storyos 会把刚拉的李家村单店明细覆盖成 17店全量（9029行事故）。
# 拉完立即拷贝到 shop 专属 data_raw/，管线从隔离副本读。
RAW_DIR="$SHOP_DIR/data_raw"
mkdir -p "$RAW_DIR"
cp -f "$PROFIT_FILE" "$RAW_DIR/门店毛利明细表-华为终端.xlsx"
cp -f "$SALES_FILE"  "$RAW_DIR/销售分析.xlsx"
PROFIT_FILE="$RAW_DIR/门店毛利明细表-华为终端.xlsx"
SALES_FILE="$RAW_DIR/销售分析.xlsx"
echo "  🔒 已隔离至 data_raw/（防 storyos 覆盖）"

echo ""
echo "▶ 2. 处理数据 + 生成看板 + 推送GitHub上线"
STAGE="2.处理数据+生成看板+推送上线"
"${PYTHON}" "${PIPELINE_SCRIPT}" "${PROFIT_FILE}" "${SALES_FILE}" 2>&1 | tail -10

echo ""
if [ "${SKIP_WECOM:-1}" = "1" ]; then
  echo "▶ 3. 企微推送：默认跳过（SKIP_WECOM=1，晨哥 2026-09-28 指令：看板不推企微群）"
else
  echo "▶ 3. 推送卡片（模式: ${CARD_MODE:-智能选片}）"
  STAGE="3.推送卡片"
  "${PYTHON}" "${PUSH_SCRIPT}" ${PUSH_ARGS}
fi

STAGE="完成"
echo ""
echo "================================================"
echo "  ✅ 全流程完成 · $(date '+%H:%M:%S')"
echo "================================================"
