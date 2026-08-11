#!/usr/bin/env bash
#
# run_pipeline.sh —— 李家村看板一键流水线
# 一条命令跑完：抓用友云 → 更新表格 → 刷新看板 → 推送线上(GitHub Pages)
#
# 用法：
#   ./run_pipeline.sh
# 说明：
#   - 抓 XS 明细 + 销售分析（导入桌面 xlsx 的对应 sheet）
#   - 重抽 data.json（B1=TODAY() 自动按今天取值，无需手改日期）
#   - 重建 index.html
#   - 提交并 git push 到 origin/main 上线
#   - 末尾确保本地预览服务(127.0.0.1:8899)在跑，方便即时查看
# 注意：企微推送不在此脚本内（已按需求暂停）。

set -euo pipefail

# 切到脚本所在目录，保证相对路径/资源正确
BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$BASE"

PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
[ -x "$PY" ] || PY="python3"
XLSX="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
TSV="$BASE/yonyou_raw.tsv"
PREVIEW_PORT=8899

log(){ echo -e "\n\033[1;36m[$(date '+%H:%M:%S')] $*\033[0m"; }

log "▶ 李家村看板一键流水线启动"

# 1) 抓用友云 XS 明细
log "[1/5] 抓取用友云 XS 明细 ..."
./fetch_yonyou.sh "$TSV" || { echo "❌ XS 抓取失败，终止"; exit 1; }

# 2) 抓用友云 销售分析 并导入桌面 sheet（失败不阻断主流程）
log "[2/5] 抓取用友云 销售分析 并导入 ..."
./fetch_sales_analysis.sh || { echo "⚠️ 销售分析抓取失败（非阻断），继续"; }

# 3) 重抽 data.json（B1=TODAY() 自动取今天）
log "[3/5] 重抽 data.json ..."
"$PY" build_data.py "$XLSX" data.json || { echo "❌ 数据抽取失败，终止"; exit 1; }

# 4) 重建 index.html
log "[4/5] 重建 index.html ..."
"$PY" build.py || { echo "❌ 看板构建失败，终止"; exit 1; }

# 5) 提交并推送线上（GitHub Pages）
log "[5/5] 提交并推送线上 ..."
git add build_data.py data.json index.html 2>/dev/null || true
git -c user.email="18@local" -c user.name="18号" \
    commit -m "看板刷新 $(date '+%Y-%m-%d %H:%M')：用友最新数据 + B1=TODAY()" \
    2>/dev/null || echo "（无变更可提交，跳过）"

if GIT_TERMINAL_PROMPT=0 git push origin main > /tmp/run_pipeline_push.log 2>&1; then
  echo "✅ 已推送线上（GitHub Pages 即将更新）"
  tail -3 /tmp/run_pipeline_push.log
else
  echo "⚠️ 推送失败：当前网络无法连接 github.com（代理 502 / 超时）。"
  echo "   本地 data.json / index.html 已是最新；网络恢复后重跑本脚本即可上线。"
  grep -o 'fatal:.*' /tmp/run_pipeline_push.log | head -1 || true
fi

# 6) 确保本地预览服务在跑（方便即时查看）
if ! lsof -i ":$PREVIEW_PORT" >/dev/null 2>&1; then
  log "启动本地预览服务 :$PREVIEW_PORT ..."
  nohup "$PY" -m http.server "$PREVIEW_PORT" --bind 127.0.0.1 >/tmp/dash_server.log 2>&1 &
  sleep 1
fi
echo -e "\n🌐 本地预览： http://127.0.0.1:$PREVIEW_PORT/index.html"

echo -e "\n🎉 流水线完成（表格 + 看板已刷新；线上推送取决于网络）。"
