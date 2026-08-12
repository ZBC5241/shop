#!/bin/bash
# fetch_all.sh —— 抓取「门店毛利明细」+「销售分析」并导入 xlsx
# 用法: ./fetch_all.sh [TSV输出路径]
#
# 提速改造（2026-08-12，最终版）：
#   🅰 门店毛利明细 = 纯 HTTP 直连 report/exec API（fetch_yonyou_http.py），
#      完全不启动浏览器 → 接口耗时 ~1.3~1.8s（服务端生成报表的固有下限）。
#   🅱 登录态来自 agent-browser 持久化的 session 文件（yht_access_token / XSRF-TOKEN），
#      浏览器仅在「纯HTTP返回401=登录态失效」时兜底启动一次重登录。
#   🅱.4 销售分析：纯 HTTP 直连 yonbip-mkt-retailweb/report/list（POST billnum=rm_saleanalysis），
#       免浏览器；落盘原始 JSON/TSV。不在看板刷新关键路径，失败不阻塞。
set -e

BASE="/Users/mac/WorkBuddy/Claw"
XLSX="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
TSV="${1:-$BASE/yonyou_raw.tsv}"
DOWN="$HOME/Downloads"
ACCOUNT="18161914293"
PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
SESSION="yonyou"
YY_BASE="https://c3.yonyoucloud.com"
YY_REPORT_ID="a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"
SA_REPORT_ID="${SA_REPORT_ID:-}"
export AGENT_BROWSER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
export AGENT_BROWSER_SESSION_NAME="$SESSION"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY
AB="/Users/mac/.workbuddy/binaries/node/workspace/node_modules/.bin/agent-browser"
PASS="$(security find-generic-password -s yonyou -w 2>/dev/null)"
[ -z "$PASS" ] && { echo "✗ 钥匙串里没有用友密码"; exit 1; }

# ---------- 函数 ----------
fetch_yy() {
  # 纯 HTTP 直连（免浏览器）。失败(含401)返回非0。
  "$PY" "$BASE/fetch_yonyou_http.py" "$TSV"
}

login() {
  echo "→ 执行登录（登录态失效，重新登录）…"
  agent-browser eval "var b=Array.from(document.querySelectorAll('button')).find(function(x){return x.textContent.trim()==='接受';}); if(b) b.click(); 'ok'" >/dev/null 2>&1 || true
  sleep 1
  SNAP="$(agent-browser snapshot 2>/dev/null)"
  REF_ACC="$(echo "$SNAP" | grep '邮箱/账号/用户手机号' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_PWD="$(echo "$SNAP" | grep 'textbox "密码"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_BTN="$(echo "$SNAP" | grep 'button "登录"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  agent-browser fill "@$REF_ACC" "$ACCOUNT" >/dev/null
  sleep 1
  agent-browser fill "@$REF_PWD" "$PASS" >/dev/null
  sleep 1
  agent-browser click "@$REF_BTN" >/dev/null
  sleep 8
  echo "  登录后标题: $(agent-browser get title 2>/dev/null | tail -1)"
}

fetch_sa() {
  # 销售分析：纯 HTTP 直连 yonbip-mkt-retailweb/report/list（🅱.4 落地，免浏览器）
  # 实测：pageSize=5000 → 全量约 2 页、~26s（服务端生成报表固有下限）。
  # 落盘原始 JSON/TSV 到 /tmp，再按 42 列映射写入桌面「销售分析」sheet（供企微日报/海报用）。
  # 仅为「销售分析」sheet（不在看板刷新关键路径）服务，失败不阻塞主流程。
  echo "→ 纯HTTP直连销售分析(report/list)…"
  if "$PY" "$BASE/fetch_sales_analysis_http.py" /tmp/sa_raw.json /tmp/sa_raw.tsv; then
    echo "→ 销售分析原始数据已落盘 /tmp/sa_raw.{json,tsv}"
    echo "→ 按42列映射写入「销售分析」sheet…"
    "$PY" "$BASE/update_sales_analysis.py" /tmp/sa_raw.json "$XLSX" \
      && echo "→ 销售分析已写入: $XLSX（企微日报/海报自动可用）" \
      || echo "⚠️ 销售分析写入模板失败（不阻塞主流程）"
  else
    echo "⚠️ 销售分析纯HTTP抓取失败（不阻塞主流程）"
  fi
}

# ---------- 主流程 ----------
echo "→ [1/2] 抓门店毛利明细（纯HTTP直连，免浏览器）…"
if fetch_yy; then
  echo "→ 登录态有效，无需浏览器"
else
  echo "→ 登录态失效，启动浏览器兜底重登录…"
  agent-browser open "$YY_BASE/#/" >/dev/null
  sleep 3
  login
  sleep 2
  agent-browser close 2>/dev/null || true
  fetch_yy || { echo "✗ 重登录后仍抓取失败"; exit 1; }
fi

echo "→ [2/2] 抓销售分析（纯HTTP，免浏览器）…"
fetch_sa

echo "✓ fetch_all 完成"
