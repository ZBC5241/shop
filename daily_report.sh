#!/usr/bin/env bash
#
# daily_report.sh —— 李家村门店日报一键流水线
# 一条命令完成：用友云抓取 → 复算 data.json → 生成日报 HTML → 保存到工作区
#
# ⏱ 更新频率：每 2 小时跑一次（用友后台 15 分钟刷新一次数据）。
#    已挂 launchd（见 com.claw.daily.plist），或 crontab：  0 */2 * * *
#    企微群推送（见 gen_daily_html.py + notify.sh）：营业时段(9-22点)每周期推日报摘要；
#    若触发「近 2 小时无人上账」则把提醒合并到摘要前一起推。
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
LOG="$SHOP_DIR/daily_report.log"
# 日志轮转：超过 300KB 归档为 .1，避免无限增长
if [ -f "$LOG" ] && [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 307200 ]; then
  mv -f "$LOG" "$LOG.1"
fi

log(){ echo -e "\n\033[1;36m[$(date '+%H:%M:%S')] $*\033[0m"; }
# 全程日志落盘（同时保留终端输出），今日达成/渠道数字对不上时可追溯
exec > >(tee -a "$LOG") 2>&1

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

# ========== Step 1.5: 抓取销售分析（刷新渠道口径数据源 sa_aug_cache.json） ==========
log "▶ [1.5] 抓取销售分析（刷新渠道挂账口径，剔除垫付/预订）…"
cat > /tmp/_yy_sa.js <<JSEOF
(async () => {
  const url = 'https://c3.yonyoucloud.com/yonbip-mkt-retailweb/report/list';
  const begin = '$MONTH_START', end = '$TODAY';
  let all = [], page = 1;
  while (true) {
    const r = await fetch(url, {method:'POST', credentials:'include',
      headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
      body: JSON.stringify({billnum:'rm_saleanalysis', page:{pageIndex:page,pageSize:5000},
        queryParams:[{name:'beginDate',value:begin},{name:'endDate',value:end}]})});
    if (r.status !== 200) return 'HTTP_'+r.status;
    const j = await r.json();
    if (!j.data || !j.data.recordList) return 'NO_LIST';
    const recs = j.data.recordList;
    all = all.concat(recs);
    if (!recs.length || recs.length < 5000) break;
    if (page > 60) break;
    page++;
  }
  const ym = begin.slice(0,7);
  const filtered = all.filter(x => x.dDate && String(x.dDate).startsWith(ym));
  return JSON.stringify({filtered_at: Date.now(), begin: begin, end: end, raw_total: all.length, records: filtered});
})()
JSEOF
JS_SA="$(cat /tmp/_yy_sa.js)"
agent-browser eval "$JS_SA" > /tmp/_yy_sa.txt 2>&1 || true
python3 -c "
import sys, json
s=open('/tmp/_yy_sa.txt').read().strip()
try:
    txt=json.loads(s)
except Exception:
    txt=s
if isinstance(txt,str) and (txt.startswith('HTTP_') or txt.startswith('NO_')):
    print('  [警告] 销售分析抓取失败:', txt[:120], '→ 沿用旧 sa_aug_cache.json')
else:
    if isinstance(txt,str):
        try: txt=json.loads(txt)
        except Exception: txt=None
    if isinstance(txt,dict) and 'records' in txt:
        json.dump(txt, open('$SHOP_DIR/sa_aug_cache.json','w'), ensure_ascii=False)
        print('  [渠道] 已刷新 sa_aug_cache.json，本月 %d 行' % len(txt['records']))
    else:
        print('  [警告] 销售分析返回结构异常 → 沿用旧 sa_aug_cache.json')
"

# ========== Step 2: 复算 data.json ==========
log "▶ [2/3] 复算 data.json ..."
python3 "$SHOP_DIR/calc_data.py" "$TSV" --xlsx "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx" -o "$DATA_JSON" 2>&1 || {
  # 如果没有 xlsx 任务进度表，用纯明细复算（不依赖 xlsx）
  log "  无任务进度表，用纯明细模式复算…"
  python3 "$SHOP_DIR/calc_data.py" "$TSV" -o "$DATA_JSON" 2>&1
}

# ========== Step 2.4: 刷新《李家村销售》"今日达成"区块并取值注入 data.json ==========
# 做法：把当日明细写入 RXS 明细表(公式数据源) → 真实引擎(soffice/Excel)重算整本
#       → 读「今日达成」区块刷新出来的缓存值 → 覆盖 data.json 的 dailyDone。
# 这样日报"当日达成"严格等于表格公式结果，不再由 Python 近似复算。
log "▶ [2.4] 刷新今日达成区块(写RXS→重算→读刷新值) …"
python3 "$SHOP_DIR/refresh_today_block.py" \
  --tsv "$TSV" \
  --xlsx "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx" \
  --data "$DATA_JSON" 2>&1 \
  || echo "  [警告] 今日达成区块刷新失败，沿用 calc_data 复算值"

# ========== Step 2.5: 最新拉取渠道口径 → 写渠道挂账C列 → 注入 data.json ==========
# merge_qudao 内部先复算最新完成额写入「渠道挂账」sheet C 列(落表)，再读 C 列，
# 实现「取渠道挂账 sheet 表、最新拉取的数据」——定时任务每次跑都会刷新该值。
log "▶ [2.5] 最新拉取渠道口径(复算→写C列→读回)注入 data.json …"
python3 "$SHOP_DIR/merge_qudao.py" "$DATA_JSON" "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx" 2>&1 \
  || echo "  [警告] 渠道合并失败，渠道挂账可能用旧数据"

# ========== Step 3: 生成日报 HTML ==========
log "▶ [3/3] 生成日报 HTML ..."
python3 "$SHOP_DIR/gen_daily_html.py" "$DATA_JSON" "$OUT_DIR"

# ========== Step 4: 企微群推送（详细日报 wecom_report，含无人上账提醒） ==========
# 营业时段(9-22点)才推，避免凌晨刷屏。wecom_report 自己读 .daily_alert_msg 合并⏰提醒。
HOUR=$(date +%H)
if [ "$HOUR" -ge 9 ] && [ "$HOUR" -lt 22 ]; then
  log "▶ [4/4] 企微群推送详细日报（wecom_report）…"
  python3 "$SHOP_DIR/wecom_report.py" || true
else
  echo "非营业时段，跳过企微推送"
fi
# 清理可能残留的纯摘要标记（旧逻辑遗留，已不再推送）
rm -f "$SHOP_DIR/.daily_summary_msg"

log "🎉 日报流水线完成！"
