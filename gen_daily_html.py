#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
门店日报 HTML 生成器
从 data.json 生成独立日报页面（单文件 HTML，双击可开）

用法：
    python gen_daily_html.py <data.json> [输出目录]
"""
import sys, os, json, datetime

def main():
    if len(sys.argv) < 2:
        print("用法: python gen_daily_html.py <data.json> [输出目录]")
        sys.exit(1)

    data_path = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(data_path)

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    store_name = meta.get("storeName", "华为李家村万达授权体验店")

    # ===== 无人上账检测（配合每2小时定时更新） =====
    # 数据里出库日期只有「天」粒度，无法直接判断2小时。改用「两次抓取边界对比」：
    # 用友每15分钟刷新，只要有人开单，下次抓取(≤2h)最大出库日期就会前进。
    # 本周期该日期没前进 = 这2小时没人开单 → 提示。营业时段(9-22点)才提示，避开凌晨误报。
    import os as _os
    STATE_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".daily_alert_state.json")
    biz_date = (meta.get("date") or "").strip()[:10]          # 明细里最大出库日期
    today_str = datetime.date.today().isoformat()
    now = datetime.datetime.now()
    in_biz = 9 <= now.hour < 22
    # 今日累计销额（取当日 dailyDone["销额"]，能反映当天新开单，不受「日期粒度」限制）
    _store = data.get("store", {})
    _dd = _store.get("dailyDone", {}) or {}
    try:
        today_amt = float(_dd.get("销额", 0) or 0)
    except Exception:
        today_amt = 0.0
    no_post_html = ""
    msg = ""
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            _st = json.load(f)
    except Exception:
        _st = {}
    prev_max = (_st.get("lastMaxDate") or "").strip()[:10]
    prev_amt = float(_st.get("lastTodayAmt") or 0)
    if not prev_max:
        # 首次运行，重置基线
        new_state = {"lastMaxDate": biz_date, "lastTodayAmt": today_amt,
                     "lastCheckAt": now.strftime("%Y-%m-%d %H:%M:%S")}
    elif biz_date > prev_max:
        # 跨到了新的一天
        if today_amt > 0:
            # 新的一天且今日已开单 → 重置基线，不告警
            new_state = {"lastMaxDate": biz_date, "lastTodayAmt": today_amt,
                         "lastCheckAt": now.strftime("%Y-%m-%d %H:%M:%S")}
        else:
            # 新的一天但今日还没开单 → 提示
            msg = "今日（{}）暂无上账，请确认门店是否已营业/开单".format(today_str)
            no_post_html = f'<div class="alert">⏰ <b>{msg}</b></div>'
            new_state = {"lastMaxDate": biz_date, "lastTodayAmt": today_amt,
                         "lastCheckAt": now.strftime("%Y-%m-%d %H:%M:%S")}
    elif not in_biz:
        # 非营业时段（22点后~次日9点）不告警
        new_state = {"lastMaxDate": biz_date, "lastTodayAmt": today_amt,
                     "lastCheckAt": now.strftime("%Y-%m-%d %H:%M:%S")}
    elif today_amt == 0:
        # 今天一单都没开（今日累计销额为 0）→ 今日尚未上账
        msg = "今日（{}）暂无上账，请确认门店是否已营业/开单".format(today_str)
        no_post_html = f'<div class="alert">⏰ <b>{msg}</b></div>'
        new_state = {"lastMaxDate": biz_date, "lastTodayAmt": today_amt,
                     "lastCheckAt": now.strftime("%Y-%m-%d %H:%M:%S")}
    else:
        # 今天已开单：对比上一周期今日累计金额是否增长
        if today_amt > prev_amt:
            new_state = {"lastMaxDate": biz_date, "lastTodayAmt": today_amt,
                         "lastCheckAt": now.strftime("%Y-%m-%d %H:%M:%S")}
        else:
            msg = "近2小时无新上账，请关注（用友每15分钟刷新一次）"
            no_post_html = f'<div class="alert">⏰ <b>{msg}</b></div>'
            new_state = {"lastMaxDate": biz_date, "lastTodayAmt": today_amt,
                         "lastCheckAt": now.strftime("%Y-%m-%d %H:%M:%S")}
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(new_state, f, ensure_ascii=False, indent=1)
    except Exception:
        pass
    # 企微群推送标记：触发无人上账时写 .daily_alert_msg，daily_report.sh 读它调 notify.sh
    _alert_file = _os.path.join(_os.path.dirname(STATE_FILE), ".daily_alert_msg")
    try:
        if no_post_html and msg:
            with open(_alert_file, "w", encoding="utf-8") as f:
                f.write(msg)
        elif _os.path.exists(_alert_file):
            _os.remove(_alert_file)
    except Exception:
        pass
    date_str = meta.get("date", datetime.date.today().strftime("%Y-%m-%d"))
    fetch_time = meta.get("fetchTime", datetime.datetime.now().strftime("%H:%M"))
    time_progress = meta.get("timeProgress", 0)
    store = data.get("store", {})
    people = data.get("people", {})

    # 核心指标
    perf = store.get("performance", {})
    mli = perf.get("毛利", {})
    mli_task = mli.get("task") or 205000
    mli_done = mli.get("done") or 0
    mli_rate = mli_done / mli_task if mli_task else 0
    mli_gap = mli_task - mli_done
    days_left = max(0, (datetime.date.today().replace(day=1) +
                 datetime.timedelta(days=28) - datetime.date.today()).days)
    # 简单估算剩余天数：月末-今天
    import calendar
    today = datetime.date.today()
    last_day = calendar.monthrange(today.year, today.month)[1]
    days_left = last_day - today.day
    daily_need = mli_gap / days_left if days_left > 0 else 0

    sale = perf.get("销额", {})
    sale_done = sale.get("done") or 0

    # 手机/穿戴/平板/PC
    cats = {}
    for cat_name in ["手机", "PC", "平板", "穿戴", "音频", "HD"]:
        cat_data = perf.get(cat_name, {})
        cats[cat_name] = {"task": cat_data.get("task") or 0,
                          "done": cat_data.get("done") or 0,
                          "gap": cat_data.get("gap") or 0,
                          "rate": cat_data.get("rate") or 0}

    # 业务员毛利排名
    person_mli = []
    for name, pdata in people.items():
        p_perf = pdata.get("performance", {})
        p_mli = p_perf.get("毛利", {})
        person_mli.append({"name": name, "done": p_mli.get("done") or 0,
                           "task": p_mli.get("task") or 0})

    # 全科生/增值
    qcs = store.get("qcs", {})
    dfh = qcs.get("电信积分", {})
    zz = qcs.get("增值", {})

    # 当日达成
    daily_done = store.get("dailyDone", {})

    # 进度条颜色
    def rate_color(r):
        if r >= 0.9: return "#4CAF50"
        if r >= 0.7: return "#FF9800"
        return "#F44336"

    # 生成业务员行
    person_rows = ""
    for p in sorted(person_mli, key=lambda x: x["done"], reverse=True):
        r = p["done"] / p["task"] if p["task"] else 0
        person_rows += f"""
        <tr>
          <td>{p['name']}</td>
          <td style="text-align:right">¥{p['done']:,.0f}</td>
          <td style="text-align:right">¥{p['task']:,.0f}</td>
          <td>
            <div class="progress-bar"><div class="progress-fill" style="width:{r*100:.0f}%;background:{rate_color(r)}"></div></div>
          </td>
          <td style="text-align:right;color:{rate_color(r)}">{r:.1%}</td>
        </tr>"""

    # 品类行
    cat_rows = ""
    cat_colors = {"手机":"#3B82F6","PC":"#8B5CF6","平板":"#06B6D4","穿戴":"#10B981","音频":"#F59E0B","HD":"#EF4444"}
    for cn, cd in cats.items():
        r = cd["rate"]
        cat_rows += f"""
        <tr>
          <td><span class="cat-dot" style="background:{cat_colors.get(cn,'#888')}"></span>{cn}</td>
          <td style="text-align:right">¥{cd['done']:,.0f}</td>
          <td style="text-align:right">¥{cd['task']:,.0f}</td>
          <td>
            <div class="progress-bar"><div class="progress-fill" style="width:{r*100:.0f}%;background:{rate_color(r)}"></div></div>
          </td>
          <td style="text-align:right;color:{rate_color(r)}">{r:.1%}</td>
        </tr>"""

    # 每日达成摘要
    daily_items = ""
    for k, v in daily_done.items():
        if isinstance(v, (int, float)) and v != 0:
            daily_items += f'<span class="daily-tag">{k}: <b>¥{v:,.0f}</b></span>'

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{store_name} 日报 {date_str}</title>
<style>
  :root {{
    --bg: #F0F4F8; --card: #FFFFFF; --text: #1E293B; --muted: #64748B;
    --primary: #3B82F6; --accent: #8B5CF6; --danger: #EF4444; --success: #4CAF50;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--text); padding:16px; }}
  .header {{ background:linear-gradient(135deg,var(--primary),var(--accent));
             color:#fff; padding:20px 24px; border-radius:16px; margin-bottom:16px; }}
  .header h1 {{ font-size:22px; margin-bottom:4px; }}
  .header .sub {{ font-size:13px; opacity:.85; }}
  .kpi-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr));
               gap:12px; margin-bottom:16px; }}
  .kpi-card {{ background:var(--card); border-radius:12px; padding:16px;
               box-shadow:0 1px 3px rgba(0,0,0,.06); }}
  .kpi-card .label {{ font-size:12px; color:var(--muted); margin-bottom:4px; }}
  .kpi-card .value {{ font-size:24px; font-weight:700; }}
  .kpi-card .sub {{ font-size:12px; color:var(--muted); margin-top:2px; }}
  .section {{ background:var(--card); border-radius:12px; padding:16px;
              box-shadow:0 1px 3px rgba(0,0,0,.06); margin-bottom:16px; }}
  .section h2 {{ font-size:15px; margin-bottom:12px; color:var(--primary); }}
  table {{ width:100%; border-collapse:collapse; font-size:13px; }}
  th {{ text-align:left; padding:8px 6px; border-bottom:2px solid var(--bg);
       font-size:12px; color:var(--muted); font-weight:500; }}
  td {{ padding:8px 6px; border-bottom:1px solid #F1F5F9; }}
  .progress-bar {{ height:8px; background:#E2E8F0; border-radius:4px; overflow:hidden; min-width:60px; }}
  .progress-fill {{ height:100%; border-radius:4px; transition:width .6s; }}
  .cat-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%;
             margin-right:6px; vertical-align:middle; }}
  .daily-tag {{ display:inline-block; background:#EFF6FF; color:var(--primary);
                padding:4px 10px; border-radius:6px; font-size:12px; margin:3px; }}
  .alert {{ background:#FEF2F2; border:1px solid #FECACA; border-radius:8px;
            padding:12px 16px; margin-bottom:16px; color:#991B1B; font-size:13px; }}
  .alert b {{ color:var(--danger); }}
  .float-btn {{ position:fixed; right:16px; bottom:20px; z-index:999;
    background:linear-gradient(135deg,var(--primary),var(--accent)); color:#fff;
    padding:12px 18px; border-radius:24px; font-size:13px; font-weight:600;
    box-shadow:0 4px 12px rgba(59,130,246,.35); cursor:pointer; text-decoration:none;
    display:flex; align-items:center; gap:5px; transition:transform .2s; }}
  .float-btn:active {{ transform:scale(.95); }}
  @media (max-width:480px) {{
    .kpi-grid {{ grid-template-columns:1fr 1fr; }}
    .header h1 {{ font-size:18px; }}
    .kpi-card .value {{ font-size:20px; }}
  }}
</style>
</head>
<body>

<div class="header">
  <h1>{store_name}</h1>
  <div class="sub">门店日报 · {date_str} · 生成于 {fetch_time}</div>
</div>

{no_post_html}
<!-- 核心指标 -->
<div class="kpi-grid">
  <div class="kpi-card">
    <div class="label">月累计毛利</div>
    <div class="value">¥{mli_done:,.0f}</div>
    <div class="sub">目标 ¥{mli_task:,.0f}</div>
  </div>
  <div class="kpi-card">
    <div class="label">达成率</div>
    <div class="value" style="color:{rate_color(mli_rate)}">{mli_rate:.1%}</div>
    <div class="sub">时间进度 {time_progress:.1%}</div>
  </div>
  <div class="kpi-card">
    <div class="label">毛利缺口</div>
    <div class="value" style="color:var(--danger)">¥{mli_gap:,.0f}</div>
    <div class="sub">剩余 {days_left} 天</div>
  </div>
  <div class="kpi-card">
    <div class="label">日均需完成</div>
    <div class="value">¥{daily_need:,.0f}</div>
    <div class="sub">月累计销额 ¥{sale_done:,.0f}</div>
  </div>
</div>

<!-- 预警 -->
{f'''<div class="alert">⚠️ <b>毛利落后约 ¥{max(0,mli_task*time_progress - mli_done):,.0f}</b>，时间进度 {time_progress:.1%}，达成率仅 {mli_rate:.1%}，日均需 ¥{daily_need:,.0f} 才能追回</div>''' if mli_rate < time_progress else ''}

<!-- 当日达成 -->
{f'''<div class="section"><h2>当日达成</h2><div>{daily_items}</div></div>''' if daily_items else ''}

<!-- 品类达成 -->
<div class="section">
  <h2>品类毛利达成</h2>
  <table>
    <tr><th>品类</th><th>完成</th><th>任务</th><th>进度</th><th>达成率</th></tr>
    {cat_rows}
  </table>
</div>

<!-- 业务员毛利排名 -->
<div class="section">
  <h2>业务员毛利排名</h2>
  <table>
    <tr><th>姓名</th><th>完成</th><th>任务</th><th>进度</th><th>达成率</th></tr>
    {person_rows}
  </table>
</div>

<!-- 全科生/增值 -->
<div class="section">
  <h2>全科生考核</h2>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="label">电信积分</div>
      <div class="value">{dfh.get('done',0) or 0:.0f}</div>
      <div class="sub">任务 {dfh.get('task',0) or 0:.0f}</div>
    </div>
    <div class="kpi-card">
      <div class="label">增值服务</div>
      <div class="value">¥{zz.get('done',0) or 0:,.0f}</div>
      <div class="sub">任务 ¥{zz.get('task',0) or 0:,.0f}</div>
    </div>
  </div>
</div>

<div style="text-align:center;font-size:11px;color:var(--muted);padding:12px">
  数据来源：用友云 · 自动生成 · {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
</div>

<a href="./" class="float-btn">
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>
  详细看板
</a>

</body>
</html>"""

    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"门店日报_{date_str.replace('-','')}.html")
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 已生成门店日报: {out_file}")
    print(f"   数据日期: {date_str}")
    print(f"   月累计毛利: ¥{mli_done:,.0f} / 达成率: {mli_rate:.1%}")

    # 企微群每周期摘要：写 .daily_summary_msg，daily_report.sh 读它调 notify.sh 推送
    _summary_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".daily_summary_msg")
    _summary = (f"【李家村门店日报 {date_str}】\n"
                f"月毛利 ¥{mli_done:,.0f} / 达成 {mli_rate:.1%}"
                f"（任务¥{mli_task:,.0f}，时间进度{time_progress:.1%}）\n"
                f"销额 ¥{sale_done:,.0f} ｜ 增值 ¥{zz.get('done', 0) or 0:,.0f}")
    try:
        with open(_summary_file, "w", encoding="utf-8") as f:
            f.write(_summary)
    except Exception:
        pass


if __name__ == "__main__":
    main()
