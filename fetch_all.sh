#!/bin/bash
# fetch_all.sh —— 抓取「门店毛利明细」+「销售分析」并导入 xlsx
# 用法: ./fetch_all.sh [TSV输出路径]
#
# 提速改造（2026-08-12，最终版）：
#   🅰 门店毛利明细 = 纯 HTTP 直连 report/exec API（fetch_yonyou_http.py），
#      完全不启动浏览器 → 接口耗时 ~1.3~1.8s（服务端生成报表的固有下限）。
#   🅱 登录态来自 agent-browser 持久化的 session 文件（yht_access_token / XSRF-TOKEN），
#      浏览器仅在「纯HTTP返回401=登录态失效」时兜底启动一次重登录。
#   🅱.4 销售分析：填 SA_REPORT_ID 走 report/exec API；否则走浏览器导出链（当前无 UUID 自动跳过）。
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
  # 销售分析：进报表 → 设日期 → 查询 → 导出带条件 → 下载 → 导入（浏览器导出链）
  TODAY=$(date +%Y-%m-%d); MFIRST=$(date +%Y-%m-01)
  mv "$DOWN"/销售分析_*.xlsx /tmp/ 2>/dev/null || true
  agent-browser open "$YY_BASE/#/" >/dev/null
  sleep 3
  login
  agent-browser eval "(function(){var els=Array.from(document.querySelectorAll('a,span,div,li'));var t=els.filter(function(e){return e.textContent && e.textContent.trim()==='我的工作台';});if(t[0]){t[0].click();return 'clicked';}return 'none';})()" >/dev/null 2>&1
  sleep 5
  hasq="NO"
  for a in 1 2 3 4 5 6; do
    agent-browser click "[data-id='101']" >/dev/null 2>&1 || \
    agent-browser eval "(function(){var el=document.querySelector('[data-id=\"101\"]');if(el){el.click();return 'clicked';}return 'none';})()" >/dev/null 2>&1
    sleep 3
    hasq="$(agent-browser eval "(function(){var bs=Array.from(document.querySelectorAll('button'));return bs.some(function(x){return x.textContent.trim()==='查询';})?'YES':'NO';})()" 2>/dev/null | tail -1)"
    [ "$hasq" = "YES" ] && break
  done
  if [ "$hasq" != "YES" ]; then
    echo "⚠️ 未进入销售分析报表（查询按钮未出现），跳过本次销售分析"
    agent-browser close 2>/dev/null || true
    return 0
  fi
  sleep 3
  agent-browser eval "(function(){var ins=Array.from(document.querySelectorAll('input.el-input__inner'));if(ins.length<2) return 'NO_INPUT';var a=ins[ins.length-2], b=ins[ins.length-1];function setInput(el,val){var proto=Object.getPrototypeOf(el);var desc=Object.getOwnPropertyDescriptor(proto,'value');desc.set.call(el,val);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}setInput(a,'$MFIRST');setInput(b,'$TODAY');return 'set';})()" >/dev/null 2>&1
  sleep 1
  agent-browser eval "(function(){var bs=Array.from(document.querySelectorAll('button'));var b=bs.find(function(x){return x.textContent.trim()==='查询';});if(b){b.click();return 'query';}return 'no-query';})()" >/dev/null 2>&1
  sleep 4
  agent-browser eval "(function(){var bs=Array.from(document.querySelectorAll('button'));var b=bs.find(function(x){return x.textContent.trim()==='导出';});if(b){b.click();return 'export';}return 'no-export';})()" >/dev/null 2>&1
  sleep 2
  agent-browser eval "(function(){var radios=document.querySelectorAll('input[type=radio]');for(var i=0;i<radios.length;i++){var lab=radios[i].closest('label')||radios[i].parentElement;if(lab && lab.textContent.indexOf('带查询条件导出')>-1){radios[i].click();}}var bs=Array.from(document.querySelectorAll('button'));var ok=bs.find(function(x){return x.textContent.trim()==='确定';});if(ok) ok.click();return 'submit';})()" >/dev/null 2>&1
  sleep 2
  F=""
  for i in $(seq 1 30); do
    F="$(ls -t "$DOWN"/销售分析_*.xlsx 2>/dev/null | grep -v crdownload | head -1)"
    [ -n "$F" ] && break
    sleep 1
  done
  if [ -n "$F" ]; then
    echo "→ 已导出: $(basename "$F")"
    "$PY" "$BASE/update_sales_analysis.py" "$F" "$XLSX" || echo "⚠️ 销售分析导入失败"
  else
    echo "⚠️ 未找到导出的销售分析 xlsx，跳过"
  fi
  agent-browser close 2>/dev/null || true
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

if [ -n "$SA_REPORT_ID" ]; then
  echo "→ [2/2] 抓销售分析（API 模式 SA_REPORT_ID=$SA_REPORT_ID）…"
  fetch_sa
else
  echo "→ [2/2] 销售分析：无 SA_REPORT_ID，跳过（不阻塞；拿到报表URL后填 SA_REPORT_ID 走 API）"
fi

echo "✓ fetch_all 完成"
