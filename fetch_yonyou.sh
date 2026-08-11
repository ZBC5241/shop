#!/bin/bash
# 用友云「门店毛利明细表-华为终端」自动抓取
# 用法: ./fetch_yonyou.sh [输出路径]
# 依赖: agent-browser CLI、macOS 钥匙串中已存 service=yonyou 的密码
set -e

# [auto-fix] macOS 12.7.6 上 agent-browser 自带的 Chrome 151 因 VideoToolbox 符号缺失无法启动，
# 改用系统已装的 Chrome 150；同时走直连用友云（已验证直连可达），避免本地代理偶发 ERR_NO_SUPPORTED_PROXIES。
export AGENT_BROWSER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY
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
if [ "$TITLE" = "数字化工作台" ] || echo "$TITLE" | grep -qi "登录"; then
  echo "→ 未登录，执行登录…"
  agent-browser eval "
    var b=Array.from(document.querySelectorAll('button')).find(function(x){return x.textContent.trim()==='接受'});
    if(b) b.click(); 'ok'
  " >/dev/null 2>&1 || true
  sleep 1
  # 登录表单在 yonbip_login iframe 里，用 snapshot 的 ref 定位
  SNAP="$(agent-browser snapshot 2>/dev/null)"
  REF_ACC="$(echo "$SNAP" | grep '邮箱/账号/用户手机号' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_PWD="$(echo "$SNAP" | grep 'textbox "密码"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_BTN="$(echo "$SNAP" | grep 'button "登录"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  if [ -z "$REF_ACC" ] || [ -z "$REF_PWD" ] || [ -z "$REF_BTN" ]; then
    echo "✗ 找不到登录表单（账号:$REF_ACC 密码:$REF_PWD 按钮:$REF_BTN）"
    echo "  可能是页面改版或出现了验证码，需人工介入。"
    exit 1
  fi
  agent-browser fill "@$REF_ACC" "$ACCOUNT" >/dev/null
  sleep 1
  agent-browser fill "@$REF_PWD" "$PASS" >/dev/null
  sleep 1
  agent-browser click "@$REF_BTN" >/dev/null
  sleep 10
  TITLE="$(agent-browser get title 2>/dev/null | tail -1)"
  echo "  登录后标题: $TITLE"
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
