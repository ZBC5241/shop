#!/bin/bash
# fetch_and_check.sh —— 自动抓数 + 判断今天是否上账 + 必要时提醒晨哥
#
# 逻辑（基于晨哥的两点分析）：
#   今天有上账           → 不提醒
#   今天 0 单：
#     近7天同时段都有销售 → 疑似"有卖未上账"，强提醒
#     近7天部分天有销售   → 可能没上账也可能真没卖，温和提醒
#     近7天也常无销售     → 可能真没卖，不提醒（真没卖=门店销售差，属看板可分析项）
#
# 用法:
#   ./fetch_and_check.sh          正常流程（先抓数再判断）
#   ./fetch_and_check.sh --no-fetch  不重新抓数，直接用现有 yonyou_raw.tsv 判断（测试用）
set -e
BASE="/Users/mac/WorkBuddy/Claw"
XLSX="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
TSV="$BASE/yonyou_raw.tsv"
PY="/Users/mac/.workbuddy/binaries/python/versions/3.13.12/bin/python3"
NO_FETCH=0
[ "$1" = "--no-fetch" ] && NO_FETCH=1
TODAY=$(date +%Y-%m-%d)

echo "🕐 [$(date '+%H:%M')] 开始检查 $TODAY 上账情况…"

# 1) 抓 XS 明细
if [ "$NO_FETCH" = "0" ]; then
  "$BASE/fetch_yonyou.sh" "$TSV" || { echo "❌ 抓取失败"; exit 1; }
  # 1.5) 同步抓「销售分析」并导入其 sheet（与 XS 导表逻辑一致）
  "$BASE/fetch_sales_analysis.sh" || echo "⚠️ 销售分析导入未成功（不影响主流程）"
fi

# 2) 复算（刷新 data.json，含 meta.isToday / lagDays）
"$PY" "$BASE/calc_data.py" "$TSV" --xlsx "$XLSX" >/dev/null

# 3) 今天是否已上账？
TODAY_HAS=$("$PY" -c "import json;print(1 if json.load(open('$BASE/data.json'))['meta'].get('isToday') else 0)")
if [ "$TODAY_HAS" = "1" ]; then
  echo "✅ 今天已上账"
else
  # 4) 今天 0 单 → 历史对比（近7天不含今天，每天是否有单）
  HIST=$("$PY" - "$TSV" "$TODAY" <<'PY'
import sys,csv,collections,datetime
rows=list(csv.reader(open(sys.argv[1],encoding='utf-8-sig'),delimiter='\t'))
body=[r for r in rows[1:] if r and r[0].strip()]
cnt=collections.Counter(r[2].strip()[:10] for r in body)
d=datetime.date.fromisoformat(sys.argv[2])
last7=[(d-datetime.timedelta(days=i)).isoformat() for i in range(1,8)]
print(sum(1 for x in last7 if cnt.get(x,0)>0))
PY
)

  if [ "$HIST" -ge 6 ]; then
    "$BASE/notify.sh" "⚠️ 李家村今日未上账" \
      "今天($TODAY)至今 0 单上账。近7天同时段每天都有销售，疑似未及时上账，请提醒店员尽快上账。"
  elif [ "$HIST" -ge 3 ]; then
    "$BASE/notify.sh" "📋 李家村今日暂无上账" \
      "今天($TODAY)至今 0 单。近7天有 $HIST 天有销售，可能还没上账，也可能今天确实没卖，留意一下。"
  else
    echo "今天 0 单，但近7天也常无销售（$HIST 天），可能真没卖，不提醒（属门店销售分析项）。"
  fi
fi

# 5) 推送今日战报到企业微信（定时任务反馈，手机可看）
"$PY" "$BASE/wecom_report.py" || true
