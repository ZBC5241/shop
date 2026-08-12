#!/usr/bin/env bash
#
# daily_report.sh —— 李家村门店日报一键流水线
# 一条命令完成：用友云抓取 → 复算 data.json → 生成日报 HTML → 保存到工作区
#
# 用法：
#   ./daily_report.sh              # 默认输出到工作区
#   ./daily_report.sh /path/out    # 指定输出目录
#
# 依赖：
#   - agent-browser CLI（已安装，在 PATH 中）
#   - macOS 钥匙串中存有用友密码（service=yonyou）
#   - python3 + openpyxl
#
set -euo pipefail

# ========== 配置 ==========
SHOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE="/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间"
OUT_DIR="${1:-$WORKSPACE}"
ACCOUNT="18161914293"
REPORT_ID="a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"   # 门店毛利明细表-华为终端
BASE="https://c3.yonyoucloud.com"
TODAY=$(date '+%Y-%m-%d')
MONTH_START=$(date '+%Y-%m')"-01"
TSV="$SHOP_DIR/yonyou_raw.tsv"
DATA_JSON="$SHOP_DIR/data.json"

log(){ echo -e "\n\033[1;36m[$(date '+%H:%M:%S')] $*\033[0m"; }

# ========== Step 1: 抓取用友云数据 ==========
log "▶ [1/3] 抓取用友云门店毛利明细 ($MONTH_START ~ $TODAY) ..."

# 走 agent-browser，复用 shop/fetch_yonyou.sh 的逻辑
# 但本脚本自包含，不依赖外部脚本
export AGENT_BROWSER_EXECUTABLE_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY

agent-browser close --all 2>/dev/null || true

PASS="$(security find-generic-password -s yonyou -w 2>/dev/null)"
if [ -z "$PASS" ]; then
  echo "✗ 钥匙串里没有用友密码。先执行："
  echo "  security add-generic-password -s yonyou -a $ACCOUNT -w 110110"
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
  SNAP="$(agent-browser snapshot 2>/dev/null)"
  REF_ACC="$(echo "$SNAP" | grep '邮箱/账号/用户手机号' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_PWD="$(echo "$SNAP" | grep 'textbox "密码"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  REF_BTN="$(echo "$SNAP" | grep 'button "登录"' | grep -o 'ref=e[0-9]*' | head -1 | cut -d= -f2)"
  if [ -z "$REF_ACC" ] || [ -z "$REF_PWD" ] || [ -z "$REF_BTN" ]; then
    echo "✗ 找不到登录表单，可能页面改版或出现验证码"
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

# 解析并保存 TSV
python3 -c "
import sys, json
with open('/tmp/_yy_raw.txt') as f:
    s = f.read().strip()
try:
    txt = json.loads(s)
except:
    txt = s
if txt.startswith('HTTP_') or txt.startswith('NO_'):
    print(f'✗ 抓取失败: {txt[:200]}'); sys.exit(1)
with open('$TSV', 'w') as f:
    f.write(txt)
lines = txt.split('\n')
dates = sorted(set(l.split('\t')[2] for l in lines[1:] if l.split('\t')[2]))
print(f'✓ 已保存: $TSV')
print(f'  明细行数: {len(lines)-1}')
print(f'  日期范围: {dates[0]} ~ {dates[-1]}')
"

# ========== Step 2: 复算 data.json ==========
log "▶ [2/3] 复算 data.json ..."
python3 "$SHOP_DIR/calc_data.py" "$TSV" --xlsx "$SHOP_DIR/../李家村8月任务进度.xlsx" --day "$TODAY" -o "$DATA_JSON" 2>&1 || {
  # 如果没有 xlsx 任务进度表，用纯明细复算（不依赖 xlsx）
  log "  无任务进度表，用纯明细模式复算…"
  python3 "$SHOP_DIR/calc_data.py" "$TSV" -o "$DATA_JSON" 2>&1
}

# ========== Step 3: 生成日报 HTML ==========
log "▶ [3/3] 生成日报 HTML ..."
python3 "$SHOP_DIR/gen_daily_html.py" "$DATA_JSON" "$OUT_DIR"

log "🎉 日报流水线完成！"
