#!/bin/bash
# 李家村看板全自动流水线：用友云 → 表格自动更新 → 看板自动刷新
set -e

BASE="/Users/mac/WorkBuddy/Claw"
XLSX="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
TSV="$BASE/yonyou_raw.tsv"
PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"

# 1. 从用友云抓本月累计 + 当日明细
"$BASE/fetch_yonyou.sh" "$TSV"

# 2. 把明细写进 xlsx 的 XS（月累计）和 RXS（当日），表格里的公式打开即刷新
"$PY" "$BASE/write_xlsx.py" "$TSV" "$XLSX"

# 3. 同时让看板直接按 SUMIFS 口径复算，避免等表格重算
"$PY" "$BASE/calc_data.py" "$TSV" --xlsx "$XLSX"

# 4. 打包成单文件 index.html
"$PY" "$BASE/build.py"

echo ""
echo "✅ 流水线完成。看板已基于最新用友云数据刷新。"
echo "   本地文件：$BASE/index.html"
echo "   表格文件：$XLSX"
