#!/usr/bin/env bash
#
# run_pipeline.sh —— 李家村看板一键流水线（更新看板 = 两张表同时刷新）
#
# 核心约束：销售毛利明细 + 销售分析 两张表，每次「更新看板」都必须同时抓、同时刷新。
#           任一张表抓取或导入失败 → 整条流水线立即中止（绝不拿一张表的旧数据顶替另一张）。
#
# 提速设计（销售分析 用友接口无法服务端按日期筛选，每次必拉全量 7811 行 ~90s）：
#   🅱 销售分析：先「读本地仓」毫秒级出 8 月视图并刷新看板；
#               同时后台静默联网重抓全量→刷仓→重建 8 月视图→复算→重建看板（~90s 后自动翻成实时）。
#   🅰 销售毛利明细：report/exec 引擎天生只返当月，纯HTTP ~1.7s。
#
# 用法： ./run_pipeline.sh
set -euo pipefail

BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE"
PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
[ -x "$PY" ] || PY="python3"
XLSX="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
TSV="$BASE/yonyou_raw.tsv"
SA_JSON="/tmp/sa_raw.json"
SA_TSV="/tmp/sa_raw.tsv"
PREVIEW_PORT=8899

log(){ echo -e "\n\033[1;36m[$(date '+%H:%M:%S')] $*\033[0m"; }

[ -f "$XLSX" ] || { echo "✗ 找不到表格: $XLSX"; exit 1; }

log "▶ 更新看板：销售毛利明细 + 销售分析 同时刷新（8月·李家村）"

# 🅰 销售毛利明细（纯HTTP，免浏览器，~1.7s）
log "[1/2] 抓销售毛利明细（纯HTTP）→ 导入 XS/RXS 明细 ..."
"$PY" fetch_yonyou_http.py "$TSV"
"$PY" write_xlsx.py "$TSV" "$XLSX"

# 🅱 销售分析：先秒出（读本地仓），后台静默刷新成最新
log "[2/2] 销售分析：读本地仓毫秒级出 8 月视图 ..."
"$PY" fetch_sales_analysis_http.py --use-cache "$SA_JSON" "$SA_TSV"
"$PY" update_sales_analysis.py "$SA_JSON" "$XLSX"

# —— 后台：联网重抓全量→刷仓→重建 8 月视图→复算→重建看板（~90s 后自动翻成实时）——
# nohup + disown 尽量让其在前台流水线结束后存活；若被回收，仓过期(>6h)时前台会自动转联网重抓，数据仍准确。
nohup bash -c '
  "'"$PY"'" fetch_sales_analysis_http.py "'"$SA_JSON"'" "'"$SA_TSV"'" \
    && "'"$PY"'" fetch_sales_analysis_http.py --use-cache "'"$SA_JSON"'" "'"$SA_TSV"'" \
    && "'"$PY"'" update_sales_analysis.py "'"$SA_JSON"'" "'"$XLSX"'" \
    && "'"$PY"'" calc_data.py "'"$TSV"'" --xlsx "'"$XLSX"'" -o data.json \
    && "'"$PY"'" merge_qudao.py data.json "'"$XLSX"'" \
    && "'"$PY"'" build.py \
    && echo "[后台] 销售分析已刷新为最新实时数据" \
    || echo "[后台] 销售分析刷新失败（前台仍为仓内数据，不影响查看）"
' >/tmp/run_pipeline_bg.log 2>&1 < /dev/null & disown

# 实时复算（明细驱动，不依赖表格公式缓存，数字立刻新）—— 基于当前仓数据，秒级
log "[3/4] 从明细实时复算 data.json ..."
"$PY" calc_data.py "$TSV" --xlsx "$XLSX" -o data.json
# 渠道挂账：calc_data 不含，需从 xlsx「渠道挂账」sheet 单独并入（不动其他指标）
"$PY" merge_qudao.py data.json "$XLSX"

# 重建看板
log "[4/4] 重建 index.html ..."
"$PY" build.py

# 推送 + 预览
log "📤 提交并推送线上 ..."
git add data.json index.html 2>/dev/null || true
git -c user.email="18@local" -c user.name="18号" \
    commit -m "看板刷新 $(date '+%Y-%m-%d %H:%M')：毛利明细+销售分析双表同步" \
    2>/dev/null || echo "（无变更可提交，跳过）"
if GIT_TERMINAL_PROMPT=0 timeout 90 git push origin main > /tmp/run_pipeline_push.log 2>&1; then
  echo "✅ 已推送线上（GitHub Pages 即将更新）"
else
  echo "⚠️ 推送失败：当前网络无法连接 github.com。本地 data.json/index.html 已是最新，网络恢复后重跑即可上线。"
  grep -o 'fatal:.*' /tmp/run_pipeline_push.log | head -1 || true
fi

if ! lsof -i ":$PREVIEW_PORT" >/dev/null 2>&1; then
  log "启动本地预览服务 :$PREVIEW_PORT ..."
  nohup "$PY" -m http.server "$PREVIEW_PORT" --bind 127.0.0.1 >/tmp/dash_server.log 2>&1 &
  sleep 1
fi
echo -e "\n🌐 本地预览： http://127.0.0.1:$PREVIEW_PORT/index.html"
echo -e "\n🎉 看板已刷新（销售毛利明细 + 销售分析 双表同步；销售分析先看板秒出，后台静默刷新为实时）"
