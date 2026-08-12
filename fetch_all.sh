#!/bin/bash
# fetch_all.sh —— 一次浏览器会话内抓取「门店毛利明细」+「销售分析」并导入 xlsx
# 用法: ./fetch_all.sh [TSV输出路径]
#
# 优化（2026-08-12 提速改造）：
#   🅰.1 两个报表合并到同一次浏览器会话，省一次启动 + 一次登录
#   🅱.5 --session-name yonyou 持久化登录态：打开后先试抓，成功即免登录；
#        失效(401)则自动重新登录兜底（比看 title 判定可靠）
#   🅰.2 收紧固定 sleep（4→3 / 7→4 / 3→2）
#   🅰.3 下载轮询 sleep 2→1、上限 40→30，下完即停
#   🅱.4 预留 SA_REPORT_ID：探到销售分析报表 ID 后切 report/exec API 直拿
set -e

BASE="/Users/mac/WorkBuddy/Claw"
XLSX="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
TSV="${1:-$BASE/yonyou_raw.tsv}"
DOWN="$HOME/Downloads"
ACCOUNT="18161914293"
PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
NODE="/Users/mac/.workbuddy/binaries/node/versions/22.22.2/bin/node"
SESSION="yonyou"
YY_BASE="https://c3.yonyoucloud.com"
YY_REPORT_ID="a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"   # 门店毛利明细表-华为终端
# 销售分析报表 ID：留空=走导出链；填了=走 report/exec API 直拿
SA_REPORT_ID="${SA_REPORT_ID:-}"

export AGENT_BROWSER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
export AGENT_BROWSER_SESSION_NAME="$SESSION"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY
AB="/Users/mac/.workbuddy/binaries/node/workspace/node_modules/.bin/agent-browser"

PASS="$(security find-generic-password -s yonyou -w 2>/dev/null)"
[ -z "$PASS" ] && { echo "✗ 钥匙串里没有用友密码"; exit 1; }

# yonyou 抓取 JS（report/exec API）
cat > /tmp/_yy_fetch.js <<JSEOF
(async () => {
  const url = '$YY_BASE/iuap-data-analytic/report/exec/$YY_REPORT_ID'
    + '?isAjax=1&hb=close&systenant=U8C3&havePublishPermission=true&browse=true'
    + '&newExec=true&sdkCode=$YY_REPORT_ID&locale=zh_CN&serviceCode=$YY_REPORT_ID';
  const r = await fetch(url, {credentials:'include'});
  if (r.status !== 200) return 'HTTP_' + r.status;
  const j = await r.json();
  const sh = j.data && j.data.analysisModel && j.data.analysisModel.sheets && j.data.analysisModel.sheets[0];
  if (!sh) return 'NO_SHEET';
  const dd = sh.datas[Object.keys(sh.datas)[0]];
  if (!dd || !dd.cells || !dd.cells.length) return 'NO_CELLS';
  const hdr = dd.cells[0].map(c => c ? c[0] : '').filter(x => x !== '');
  const n = hdr.length;
  const rows = dd.cells.slice(1).filter(r => r && r[0] && r[0][0]).map(r => r.slice(0, n).map(c => c ? String(c[0]) : ''));
  return [hdr.join('\t')].concat(rows.map(r => r.join('\t'))).join('\n');
})()
JSEOF
YY_JS="$(cat /tmp/_yy_fetch.js)"

# ---------- 函数 ----------
fetch_yy() {
  set +e
  agent-browser eval "$YY_JS" > /tmp/_yy_raw.txt 2>&1
  "$NODE" -e "
const fs=require('fs');
let s=fs.readFileSync('/tmp/_yy_raw.txt','utf8').trim();
let txt; try { txt = JSON.parse(s); } catch(e) { txt = s; }
if (/^(HTTP_|NO_SHEET|NO_CELLS|✗)/.test(txt)) { console.error('✗ yonyou抓取失败: ' + txt.slice(0,200)); process.exit(1); }
fs.writeFileSync('$TSV', txt);
const lines = txt.split('\n');
const dates = [...new Set(lines.slice(1).map(l => l.split('\t')[2]))].filter(Boolean).sort();
console.log('✓ 已保存: $TSV');
console.log('  明细行数: ' + (lines.length - 1));
console.log('  日期范围: ' + dates[0] + ' ~ ' + dates[dates.length-1]);
"
  rc=$?
  set -e
  return $rc
}

login() {
  echo "→ 执行登录（session 失效，重新登录）…"
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
  # 销售分析：进报表 → 设日期本月1~今天 → 查询 → 导出带条件 → 下载 → 导入
  TODAY=$(date +%Y-%m-%d); MFIRST=$(date +%Y-%m-01)
  # 导出前先把 Downloads 里旧的销售分析文件移走（备份到 /tmp），强制本次真下载，避免复用旧数据
  mv "$DOWN"/销售分析_*.xlsx /tmp/ 2>/dev/null || true
  # 进销售分析报表：SA_EL 已确认销售分析报表项 = data-id=101。
  # 用真实点击（agent-browser click 触发框架 addEventListener），轮询检测"查询"按钮（SPA 报表页特征，非 iframe）
  hasq="NO"
  for a in 1 2 3 4 5 6; do
    agent-browser click "[data-id='101']" >/dev/null 2>&1 || \
    agent-browser eval "(function(){var el=document.querySelector('[data-id=\"101\"]');if(el){el.click();return 'clicked';}return 'none';})()" >/dev/null 2>&1
    sleep 3
    hasq="$(agent-browser eval "(function(){var bs=Array.from(document.querySelectorAll('button'));return bs.some(function(x){return x.textContent.trim()==='查询';})?'YES':'NO';})()" 2>/dev/null | tail -1)"
    echo "  [debug] 进销售分析尝试$a: 查询按钮=$hasq"
    [ "$hasq" = "YES" ] && break
  done
  # 进报表后抓 reportId（UUID）：报表页 HTML 内 36位 uuid（供🅱.4 API 直拿用）
  cat > /tmp/_sa_uuid.js <<'JSEOF'
(function(){
  try{
    var h=document.documentElement.outerHTML;
    var m=h.match(/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/g);
    return 'PAGE_REPORTID:'+(m?JSON.stringify(m.slice(0,5)):'none');
  }catch(e){return 'ERR:'+e;}
})()
JSEOF
  agent-browser eval "$(cat /tmp/_sa_uuid.js)" 2>/dev/null | tail -1
  if [ "$hasq" != "YES" ]; then
    echo "⚠️ 未进入销售分析报表（查询按钮未出现），跳过本次销售分析"
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
    echo "⚠️ 未找到导出的销售分析 xlsx（本次真下载未成功），跳过"
  fi
}

# ---------- 主流程 ----------
agent-browser close --all 2>/dev/null || true
echo "→ 打开用友云（session=$SESSION）…"
agent-browser open "$YY_BASE/#/" >/dev/null
sleep 3

echo "→ [1/2] 抓门店毛利明细（先试抓，session 有效则免登录）…"
if fetch_yy; then
  echo "→ session 登录态有效，跳过登录"
else
  login
  fetch_yy || { echo "✗ 登录后仍抓取失败"; exit 1; }
fi

# 登录后进入工作台（左侧菜单才有销售分析等报表入口，否则停在公司首页点不到）
agent-browser eval "(function(){var els=Array.from(document.querySelectorAll('a,span,div,li'));var t=els.filter(function(e){return e.textContent && e.textContent.trim()==='我的工作台';});if(t[0]){t[0].click();return 'clicked';}return 'none';})()" >/dev/null 2>&1
sleep 5

# [debug] 登录后打印页面含 分析/报表/工作台 的菜单文本，定位销售分析入口
echo "  [debug] 登录后可见菜单(分析/报表/工作台/销售/中心):"
agent-browser eval "(function(){var els=Array.from(document.querySelectorAll('a,button,li,div,span'));var ks=els.map(function(e){return (e.textContent||'').trim();}).filter(function(t){return t && /分析|报表|工作台|销售|门户|中心/.test(t);});return 'MENU:'+JSON.stringify([...new Set(ks)].slice(0,30));})()" 2>/dev/null | tail -1

echo "→ [2/2] 抓销售分析…"
if [ -n "$SA_REPORT_ID" ]; then
  echo "  [API 模式] SA_REPORT_ID=$SA_REPORT_ID"
  # TODO 🅱.4: report/exec API 直拿 + update_sales_analysis.py --tsv
  fetch_sa   # 暂仍走导出链，拿到 ID 后切换
else
  fetch_sa
fi

agent-browser close --all 2>/dev/null || true
echo "✓ fetch_all 完成"
