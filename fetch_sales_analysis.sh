#!/bin/bash
# fetch_sales_analysis.sh —— 自动从用友云「销售分析」报表导出 Excel，并写入
# 《李家村X月任务进度.xlsx》的「销售分析」工作表（清空 A3 起重贴）。
#
# 与 fetch_yonyou.sh（抓 XS 明细）并列：在 fetch_and_check.sh 里顺序调用，
# 即可在“导数据”流程中把销售分析也一并导进去，逻辑与 XS 导表一致。
#
# 依赖: agent-browser（已登录的用友云会话）、钥匙串 service=yonyou 密码
set -e

BASE="/Users/mac/WorkBuddy/Claw"
XLSX="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
DOWN="$HOME/Downloads"
ACCOUNT="18161914293"
PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
PASS="$(security find-generic-password -s yonyou -w 2>/dev/null)"

TODAY=$(date +%Y-%m-%d)
MFIRST=$(date +%Y-%m-01)

echo "🕐 [$(date '+%H:%M')] 开始抓取用友云「销售分析」报表（$MFIRST ~ $TODAY）…"

# 1) 打开用友云（复用已有登录态；若回到登录页则登录）
agent-browser open "https://c3.yonyoucloud.com/#/" >/dev/null 2>&1
sleep 4
TITLE="$(agent-browser get title 2>/dev/null | tail -1)"
if echo "$TITLE" | grep -qi "登录"; then
  echo "→ 未登录，执行登录…"
  agent-browser eval "
    var b=Array.from(document.querySelectorAll('button')).find(function(x){return x.textContent.trim()==='接受';});
    if(b) b.click(); 'ok';
  " >/dev/null 2>&1 || true
  sleep 1
  SNAP="$(agent-browser snapshot 2>/dev/null)"
  REF_ACC="$(echo "$SNAP" | grep '邮箱/账号/用户手机号' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_PWD="$(echo "$SNAP" | grep 'textbox "密码"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_BTN="$(echo "$SNAP" | grep 'button "登录"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  agent-browser fill "@$REF_ACC" "$ACCOUNT" >/dev/null 2>&1
  sleep 1
  agent-browser fill "@$REF_PWD" "$PASS" >/dev/null 2>&1
  sleep 1
  agent-browser click "@$REF_BTN" >/dev/null 2>&1
  sleep 10
fi

# 2) 进入「销售分析」报表（JS 点击文本，避免依赖固定 ref）
agent-browser eval "
(function(){
  var els=Array.from(document.querySelectorAll('span,div,a,li,generic'));
  var t=els.filter(function(e){return e.textContent && e.textContent.trim()==='销售分析';});
  function fire(el){while(el){if(el.getAttribute && (el.getAttribute('onclick')||(el.style&&el.style.cursor==='pointer'))){el.click();return true;}el=el.parentElement;}return false;}
  for(var i=0;i<t.length;i++){ if(fire(t[i])) return 'clicked'; }
  return 'none';
})()
" >/dev/null 2>&1
sleep 7

# 3) 设置日期范围（本月1日 ~ 今天）并触发查询
agent-browser eval "
(function(){
  // 日期范围是两个 el-input__inner（daterange 的两个输入框），取最后两个
  var ins=Array.from(document.querySelectorAll('input.el-input__inner'));
  if(ins.length<2) return 'NO_INPUT';
  var a=ins[ins.length-2], b=ins[ins.length-1];
  function setInput(el,val){
    var proto=Object.getPrototypeOf(el);
    var desc=Object.getOwnPropertyDescriptor(proto,'value');
    desc.set.call(el,val);
    el.dispatchEvent(new Event('input',{bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));
  }
  setInput(a,'$MFIRST');
  setInput(b,'$TODAY');
  return 'set '+a.value+'~'+b.value;
})()
" >/dev/null 2>&1
sleep 1

# 点查询（按钮文本精确为“查询”）
agent-browser eval "
(function(){
  var bs=Array.from(document.querySelectorAll('button'));
  var b=bs.find(function(x){return x.textContent.trim()==='查询';});
  if(b){ b.click(); return 'query'; }
  return 'no-query-btn';
})()
" >/dev/null 2>&1
sleep 7

# 4) 点导出 -> 选“带查询条件导出” -> 确认
agent-browser eval "
(function(){
  var bs=Array.from(document.querySelectorAll('button'));
  var b=bs.find(function(x){return x.textContent.trim()==='导出';});
  if(b){ b.click(); return 'export'; }
  return 'no-export-btn';
})()
" >/dev/null 2>&1
sleep 3

# 选“带查询条件导出”radio 并点对话框“确定”
agent-browser eval "
(function(){
  var radios=document.querySelectorAll('input[type=radio]');
  for(var i=0;i<radios.length;i++){
    var lab=radios[i].closest('label')||radios[i].parentElement;
    if(lab && lab.textContent.indexOf('带查询条件导出')>-1){ radios[i].click(); }
  }
  var bs=Array.from(document.querySelectorAll('button'));
  var ok=bs.find(function(x){return x.textContent.trim()==='确定';});
  if(ok) ok.click();
  return 'submit';
})()
" >/dev/null 2>&1
sleep 3

# 5) 确认“确定导出全部数据？”弹窗
agent-browser eval "
(function(){
  var bs=Array.from(document.querySelectorAll('button'));
  var ok=bs.find(function(x){return x.textContent.trim()==='确定';});
  if(ok) ok.click();
  return 'confirm';
})()
" >/dev/null 2>&1

# 6) 等待下载完成
echo "→ 等待导出下载完成…"
F=""
for i in $(seq 1 40); do
  F="$(ls -t "$DOWN"/销售分析_*.xlsx 2>/dev/null | grep -v crdownload | head -1)"
  [ -n "$F" ] && break
  sleep 2
done
if [ -z "$F" ]; then
  echo "!! 未找到导出的 销售分析_*.xlsx，抓取失败"
  exit 1
fi
echo "→ 已导出: $(basename "$F")"

# 7) 导入到 Excel 销售分析表（清空 A3 起重贴）
"$PY" "$BASE/update_sales_analysis.py" "$F" "$XLSX"
