#!/bin/bash
# 用友云「门店毛利明细表-华为终端」自动抓取
# 用法: ./fetch_yonyou.sh [输出路径]
# 依赖: agent-browser CLI、macOS 钥匙串中已存 service=yonyou 的密码
set -e

# [auto-fix 1] macOS 12.7.6 上 agent-browser 自带的 Chrome 151 因 VideoToolbox 符号缺失无法启动，
# 改用系统已装的 Chrome 150；同时走直连用友云（已验证直连可达），避免本地代理偶发 ERR_NO_SUPPORTED_PROXIES。
export AGENT_BROWSER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY

# [auto-fix 2] agent-browser 会给 Chrome 注入自带拦截代理(--proxy-server=127.0.0.1:53564)，
# 导致对 c3/euc.yonyoucloud.com 的 fetch 网络层失败("Failed to fetch")。
# 用 AGENT_BROWSER_PROXY_BYPASS 环境变量让 yonyoucloud 流量全局直连，避免每次命令重复带
# --proxy-bypass 触发 "daemon already running / ignored" 警告污染输出。
export AGENT_BROWSER_PROXY_BYPASS="*.yonyoucloud.com"

agent-browser close --all 2>/dev/null || true

OUT="${1:-/Users/mac/WorkBuddy/Claw/yonyou_raw.tsv}"
ACCOUNT="18161914293"
REPORT_ID="a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"   # 门店毛利明细表-华为终端
BASE="https://c3.yonyoucloud.com"
NODE="/Users/mac/.workbuddy/binaries/node/versions/22.22.2/bin/node"

PASS="$(security find-generic-password -s yonyou -w 2>/dev/null)"
if [ -z "$PASS" ]; then
  echo "✗ 钥匙串里没有用友密码。先执行："
  echo "  security add-generic-password -s yonyou -a $ACCOUNT -w"
  exit 1
fi

echo "→ 打开用友云…"
agent-browser set viewport 1920 1080 >/dev/null 2>&1 || true
agent-browser open "$BASE/#/" >/dev/null
sleep 4

TITLE="$(agent-browser get title 2>/dev/null | tail -1)"
URL_NOW="$(agent-browser get url 2>/dev/null | tail -1)"
if echo "$TITLE" | grep -qi "登录" || echo "$URL_NOW" | grep -qi "cas/login"; then
  echo "→ 工作台未登录，执行 yonbip 登录…"
  agent-browser eval "
    var b=Array.from(document.querySelectorAll('button')).find(function(x){return x.textContent.trim()==='接受'});
    if(b) b.click(); 'ok'
  " >/dev/null 2>&1 || true
  sleep 1
  SNAP="$(agent-browser snapshot 2>/dev/null)"
  REF_ACC="$(echo "$SNAP" | grep '邮箱/账号/用户手机号' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_PWD="$(echo "$SNAP" | grep 'textbox "密码"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_BTN="$(echo "$SNAP" | grep 'button "登录"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  if [ -n "$REF_ACC" ] && [ -n "$REF_PWD" ] && [ -n "$REF_BTN" ]; then
    agent-browser fill "@$REF_ACC" "$ACCOUNT" >/dev/null
    sleep 1
    agent-browser fill "@$REF_PWD" "$PASS" >/dev/null
    sleep 1
    agent-browser click "@$REF_BTN" >/dev/null
    sleep 10
  fi
fi

# 关键：进入报表分析应用，触发 data-analytic 服务独立鉴权（该服务 SSO 与会工作台不同，常需单独 CAS 登录）
echo "→ 打开报表分析页（触发 data-analytic 鉴权）…"
agent-browser open "$BASE/iuap-data-analytic/index.html#/report/$REPORT_ID?browse=true" >/dev/null
sleep 8

URL2="$(agent-browser get url 2>/dev/null | tail -1)"
if echo "$URL2" | grep -qi "euc.yonyoucloud.com/cas\|cas/login"; then
  echo "→ 报表服务需 CAS 登录，执行…"
  cat > /tmp/_yy_cas.js <<JSEOF
(() => {
  const u = document.querySelector('#username');
  const p = document.querySelector('#password');
  const btn = document.querySelector('#submit_btn_login');
  if(!u||!p||!btn) return 'NO_FORM';
  function set(el,v){ const d=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set; d.call(el,v); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); }
  set(u, '$ACCOUNT'); set(p, '$PASS'); btn.click();
  return 'CLICKED';
})()
JSEOF
  agent-browser eval "$(cat /tmp/_yy_cas.js)" >/dev/null 2>&1
  rm -f /tmp/_yy_cas.js
  sleep 12
  agent-browser open "$BASE/iuap-data-analytic/index.html#/report/$REPORT_ID?browse=true" >/dev/null
  sleep 8
fi

echo "→ 调用报表接口…"
cat > /tmp/_yy_fetch.js <<JSEOF
(async () => {
  const url = '$BASE/iuap-data-analytic/report/exec/$REPORT_ID'
    + '?isAjax=1&hb=close&systenant=U8C3&havePublishPermission=true&browse=true'
    + '&newExec=true&sdkCode=$REPORT_ID&locale=zh_CN&serviceCode=$REPORT_ID';
  const r = await fetch(url, {credentials:'include'});
  if (r.status !== 200) return 'HTTP_' + r.status;
  const j = await r.json();
  const sh = j.data && j.data.analysisModel && j.data.analysisModel.sheets && j.data.analysisModel.sheets[0];
  if (!sh) return 'NO_SHEET';
  const dd = sh.datas[Object.keys(sh.datas)[0]];
  if (!dd || !dd.cells || !dd.cells.length) return 'NO_CELLS';
  const hdr = dd.cells[0].map(c => c ? c[0] : '').filter(x => x !== '');
  const n = hdr.length;
  const rows = dd.cells.slice(1)
    .filter(r => r && r[0] && r[0][0])
    .map(r => r.slice(0, n).map(c => c ? String(c[0]) : ''));
  return [hdr.join('\t')].concat(rows.map(r => r.join('\t'))).join('\n');
})()
JSEOF

# 注意：daemon 已在启动时带 bypass，这里 eval 不要再带 --proxy-bypass，避免 "ignored" 警告污染输出
JS_CODE="$(cat /tmp/_yy_fetch.js)"
agent-browser eval "$JS_CODE" > /tmp/_yy_raw.txt 2>&1

"$NODE" -e "
const fs=require('fs');
let s=fs.readFileSync('/tmp/_yy_raw.txt','utf8').trim();
let txt; try { txt = JSON.parse(s); } catch(e) { txt = s; }
if (/^(HTTP_|NO_SHEET|NO_CELLS|✗)/.test(txt)) { console.error('✗ 抓取失败: ' + txt.slice(0,200)); process.exit(1); }
fs.writeFileSync('$OUT', txt);
const lines = txt.split('\n');
const dates = [...new Set(lines.slice(1).map(l => l.split('\t')[2]))].filter(Boolean).sort();
console.log('✓ 已保存: $OUT');
console.log('  明细行数: ' + (lines.length - 1));
console.log('  日期范围: ' + dates[0] + ' ~ ' + dates[dates.length-1]);
"
