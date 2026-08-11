#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
poster_build.py —— 动态生成当日「今日达成日报」高清海报 PNG。

读 data.json（看板复算）+ yonyou_raw.tsv（算每人单量），
按 poster_v3 的版式动态填当日真实数据，调用 render_poster.js 截成 2x 高清无框 PNG。

版式：横版单屏（手机横屏 19.5:9），CSS 1416x658 → 渲染 2x = 2832x1316。

用法:
  python3 poster_build.py                 # 生成 poster_today.png 并打印路径
  python3 poster_build.py --out xxx.png   # 指定输出路径
"""
import json
import csv
import os
import sys
import calendar
import subprocess

# 复用 wecom_report 的 渠道挂账 读取逻辑（同目录，单来源）
from wecom_report import read_qudao

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data.json")
TSV = os.path.join(BASE, "yonyou_raw.tsv")
RENDER_JS = os.path.join(BASE, "render_poster.js")
NODE = "/Users/mac/.workbuddy/binaries/node/versions/22.22.2/bin/node"
DAILY_VALUEADDED = 1600

# 人员头像底色（循环）
AVA_COLORS = ["#2f6bff", "#ff8a65", "#aa78e6", "#ff638c", "#46b87e"]


def num(s):
    s = (s or "").replace(",", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def money(x):
    try:
        return "¥{:,.0f}".format(float(x))
    except Exception:
        return str(x)


def pct(x):
    try:
        return "{:.0f}%".format(float(x) * 100)
    except Exception:
        return str(x)


def working_days(year, month):
    ndays = calendar.monthrange(year, month)[1]
    return sum(1 for d in range(1, ndays + 1) if calendar.weekday(year, month, d) < 5)


def today_rows(tsv, today):
    try:
        rows = list(csv.reader(open(tsv, encoding="utf-8-sig"), delimiter="\t"))
    except Exception:
        return []
    if not rows:
        return []
    hdr = rows[0]
    out = []
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        rec = {hdr[i]: (r[i] if i < len(r) else "") for i in range(len(hdr))}
        if rec.get("出库日期", "").strip()[:10] == today:
            out.append(rec)
    return out


def build_html(d):
    meta = d.get("meta", {})
    today = meta.get("date", "")
    dd = d.get("store", {}).get("dailyDone", {})
    perf = d.get("store", {}).get("performance", {})
    emp = meta.get("employees", [])

    rows = today_rows(TSV, today)
    cnt = {}
    for r in rows:
        e = (r.get("业务员", "") or "").strip() or "(未分配)"
        cnt[e] = cnt.get(e, 0) + 1

    amt = dd.get("销额", 0) or 0
    gp = dd.get("毛利", 0) or 0
    va = dd.get("增值", 0) or 0
    phone = dd.get("手机", 0) or 0
    gm = (gp / amt) if amt else 0

    y, m = int(today[:4]), int(today[5:7])
    wd = working_days(y, m)

    def dtask(k):
        if k == "增值":
            return float(DAILY_VALUEADDED)
        t = (perf.get(k, {}) or {}).get("task", 0) or 0
        return t / wd if wd else 0

    # 板块：name, done, task, fill-color
    blocks = [
        ("手机", phone, dtask("手机"), "#ffb24c,#f5a623"),
        ("增值", va, dtask("增值"), "#ff7a8a,#ff5b6e"),
        ("毛利", gp, dtask("毛利"), "#5b8cff,#2f6bff"),
        ("销额", amt, dtask("销额"), "#5b8cff,#2f6bff"),
    ]
    rates = [b[1] / b[2] * 100 for b in blocks if b[2]]
    overall = sum(rates) / len(rates) if rates else 0

    def rate_fmt(rate):
        return "{:.0f}%".format(rate)

    def fmt_block(done, task, is_phone):
        if is_phone:
            return "{:.0f} 台　/　{:.0f} 台".format(done, task)
        return "{}　/　{}".format(money(done), money(task))

    rows_html = ""
    for i, (name, done, task, color) in enumerate(blocks):
        rate = (done / task * 100) if task else 0
        is_phone = (name == "手机")
        meta_txt = fmt_block(done, task, is_phone)
        w = min(100, max(4, rate))
        rows_html += (
            '    <div class="row">\n'
            '      <div class="r-name">{}</div>\n'
            '      <div class="r-mid"><div class="meta">{}</div>'
            '<div class="track"><div class="fill" style="width:{}%;background:linear-gradient(90deg,{});"></div></div></div>\n'
        '      <div class="r-rate" style="color:{};">{}</div>\n'
        '    </div>\n'
    ).format(name, meta_txt, round(w), color, color.split(",")[1], rate_fmt(rate))

    # 人员（开单在前，按销额降序）
    people_sorted = sorted(
        emp,
        key=lambda x: -(d.get("people", {}).get(x, {}).get("dailyDone", {}).get("销额", 0) or 0)
    )
    people_html = ""
    for i, e in enumerate(people_sorted):
        pd = d.get("people", {}).get(e, {}).get("dailyDone", {})
        e_amt = pd.get("销额", 0) or 0
        e_gp = pd.get("毛利", 0) or 0
        n = cnt.get(e, 0)
        color = AVA_COLORS[i % len(AVA_COLORS)]
        if e_amt == 0:
            people_html += (
                '    <div class="p"><div class="ava" style="background:{};">{}</div>'
                '<div class="nm">{}</div><div class="pill zero">挂零</div></div>\n'
            ).format(color, e[0], e)
        else:
            people_html += (
                '    <div class="p"><div class="ava" style="background:{};">{}</div>'
                '<div class="nm">{}</div>'
                '<div class="info">销额 {}<br>毛利 {} · {}单</div></div>\n'
            ).format(color, e[0], e, money(e_amt), money(e_gp), n)

    # 复盘
    phone_rate = phone / dtask("手机") if dtask("手机") else 0
    va_rate = va / DAILY_VALUEADDED if DAILY_VALUEADDED else 0
    open_emp = [e for e in people_sorted if (d.get("people", {}).get(e, {}).get("dailyDone", {}).get("销额", 0) or 0) > 0]
    zero_emp = [e for e in people_sorted if e not in open_emp]
    review_txt = ("手机 {:.0f} 台达成 {}，增值仅 {}，电信 0 单；毛利率 {} 处低位。"
                  "{} 撑起今日，{} 挂零。").format(
        phone, pct(phone_rate), pct(va_rate), pct(gm),
        "、".join(open_emp), "、".join(zero_emp))

    # 渠道挂账（来自任务进度表独立 sheet，公式自动算好，直接读不计算）
    qd = read_qudao()
    qd_html = ""
    if qd:

        def qrate(s):
            try:
                f = float(str(s).replace("%", ""))
                if 0 < f < 1:
                    f *= 100
                return "{:.1f}%".format(f)
            except Exception:
                return str(s)

        lag = ""
        try:
            tr = float(str(qd["time_rate"]).replace("%", ""))
            if 0 < tr < 1:
                tr *= 100
            if qd["total_rate"] < tr:
                lag = " ⚠️落后"
        except Exception:
            pass
        date_short = qd["time_date"][5:] if len(qd["time_date"]) == 10 else qd["time_date"]
        qd_html += (
            '  <div class="qd">\n'
            '    <div class="qd-sum">渠道挂账　完成 <b>{}</b> ／ 任务 <b>{}</b> ／ 达成 <b>{:.1f}%</b>'
            '　·　时间进度 {} 已过 {}<span class="lag">{}</span></div>\n'
        ).format(
            money(qd["total_done"]), money(qd["total_task"]), qd["total_rate"],
            date_short, qrate(qd["time_rate"]), lag,
        )
        for p in qd["people"]:
            if p["task"] == 0 and p["done"] == 0:
                qd_html += (
                    '    <span class="qd-row zero">{} 无任务</span>\n'
                ).format(p["name"])
            elif p["done"] == 0:
                qd_html += (
                    '    <span class="qd-row zero">{} 挂零</span>\n'
                ).format(p["name"])
            else:
                qd_html += (
                    '    <span class="qd-row">{} {}（{}）</span>\n'
                ).format(p["name"], money(p["done"]), qrate(p["rate"]))
        qd_html += '  </div>\n'

    label = meta.get("todayLabel", today)
    # 今天未上账时（isToday=False），标题跟随实际数据日期，避免错位
    if not meta.get("isToday", False) and today:
        label = today[5:] if len(today) == 10 else today
    ftime = meta.get("fetchTime", "")

    html = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#f5f6f9; font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;
          display:flex; justify-content:center; -webkit-font-smoothing:antialiased; }}
  .phone {{ width:1416px; height:658px; background:#f5f6f9; display:flex; flex-direction:column; overflow:hidden; }}
  .hero {{ height:98px; flex:none; background:linear-gradient(135deg,#131c33 0%,#1f2f52 55%,#274072 100%);
           display:flex; align-items:center; justify-content:space-between; padding:0 38px; color:#fff; position:relative; }}
  .hero::after {{ content:""; position:absolute; right:-40px; top:-40px; width:160px; height:160px;
                 background:radial-gradient(circle,rgba(120,160,255,.16),transparent 70%); border-radius:50%; }}
  .hero .kicker {{ font-size:13px; letter-spacing:4px; color:#8fb0e6; font-weight:600; }}
  .hero h1 {{ font-size:30px; font-weight:800; margin-top:5px; letter-spacing:1px; }}
  .hero .sub {{ margin-top:4px; font-size:14px; color:#b6c6e6; font-weight:500; }}
  .ring {{ width:68px; height:68px; border-radius:50%; flex:none; position:relative;
           background:conic-gradient(#f5a623 0% {ov}%, rgba(255,255,255,.13) {ov}% 100%); }}
  .ring .in {{ position:absolute; inset:8px; border-radius:50%; background:#16203b;
               display:flex; flex-direction:column; align-items:center; justify-content:center; }}
  .ring .in b {{ font-size:21px; font-weight:800; color:#fff; line-height:1; }}
  .ring .in span {{ font-size:9px; color:#f5a623; margin-top:3px; font-weight:600; }}
  .body {{ flex:1; display:flex; gap:16px; padding:16px; overflow:hidden; }}
  .col-l {{ width:430px; flex:none; display:flex; flex-direction:column; gap:12px; }}
  .col-r {{ flex:1; display:flex; flex-direction:column; gap:10px; overflow:hidden; }}
  .kpis {{ display:grid; grid-template-columns:1fr 1fr; gap:12px; }}
  .kpi {{ background:#fff; border-radius:14px; padding:14px 18px; position:relative; box-shadow:0 6px 16px rgba(30,45,80,.06); }}
  .kpi::before {{ content:""; position:absolute; left:18px; top:0; width:28px; height:4px; border-radius:0 0 3px 3px; background:#2f6bff; }}
  .kpi .lab {{ font-size:15px; color:#9aa3b3; font-weight:600; }}
  .kpi .val {{ font-size:27px; font-weight:800; color:#1c2230; margin-top:4px; letter-spacing:.3px; }}
  .kpi .u {{ font-size:14px; color:#9aa3b3; font-weight:600; }}
  .sec-t {{ font-size:17px; font-weight:800; color:#1c2230; display:flex; align-items:center; gap:8px; margin-bottom:4px; }}
  .sec-t .bar {{ width:6px; height:16px; border-radius:3px; background:#2f6bff; }}
  .rows {{ background:#fff; border-radius:14px; padding:10px 18px; box-shadow:0 6px 16px rgba(30,45,80,.05); }}
  .row {{ display:flex; align-items:center; padding:7px 0; border-bottom:1px solid #eef0f4; }}
  .row:last-child {{ border-bottom:none; }}
  .r-name {{ width:52px; font-size:16px; font-weight:700; color:#2a3242; }}
  .r-mid {{ flex:1; padding:0 14px; }}
  .r-mid .meta {{ font-size:13px; color:#9aa3b3; margin-bottom:5px; }}
  .track {{ height:8px; border-radius:5px; background:#edeff4; overflow:hidden; }}
  .fill {{ height:100%; border-radius:5px; }}
  .r-rate {{ width:52px; text-align:right; font-size:17px; font-weight:800; }}
  .people {{ display:flex; gap:10px; flex-wrap:wrap; }}
  .p {{ display:flex; align-items:center; gap:9px; background:#fff; border-radius:12px; padding:9px 12px;
         box-shadow:0 5px 14px rgba(30,45,80,.05); }}
  .ava {{ width:36px; height:36px; border-radius:50%; color:#fff; font-size:16px; font-weight:800;
          display:flex; align-items:center; justify-content:center; flex:none; }}
  .p .nm {{ font-size:16px; font-weight:700; color:#1c2230; }}
  .p .info {{ font-size:12px; color:#8b94a6; line-height:1.35; }}
  .pill {{ font-size:13px; font-weight:800; padding:4px 11px; border-radius:16px; }}
  .ok {{ background:#e7f7ef; color:#1fb574; }}
  .zero {{ background:#fdeaec; color:#ff5b6e; }}
  .qd {{ background:#fff; border-radius:12px; padding:11px 16px; font-size:13px; color:#434a5c;
         box-shadow:0 5px 14px rgba(30,45,80,.05); }}
  .qd-sum {{ margin-bottom:7px; }}
  .qd-sum b {{ color:#1c2230; font-weight:800; }}
  .qd .lag {{ color:#ff5b6e; font-weight:800; }}
  .qd-row {{ display:inline-block; margin:2px 10px 2px 0; font-size:13px; }}
  .qd-nm {{ font-weight:700; color:#1c2230; }}
  .qd-st {{ color:#8b94a6; }}
  .qd-row.zero .qd-st {{ color:#ff5b6e; font-weight:800; }}
  .review {{ background:#fff; border-radius:12px; padding:12px 16px; border-left:5px solid #f5a623;
             box-shadow:0 5px 14px rgba(30,45,80,.05); }}
  .review h3 {{ font-size:15px; color:#b9802a; font-weight:800; margin-bottom:5px; }}
  .review p {{ font-size:13px; color:#434a5c; line-height:1.5; }}
</style></head>
<body>
<div class="phone">
  <div class="hero">
    <div>
      <div class="kicker">DAILY REPORT</div>
      <h1>李家村门店 · 今日达成</h1>
      <div class="sub">{label}　以已上账为准　·　更新 {ftime}</div>
    </div>
    <div class="ring"><div class="in"><b>{ov_pct}</b><span>综合达成</span></div></div>
  </div>
  <div class="body">
    <div class="col-l">
      <div class="kpis">
        <div class="kpi"><div class="lab">销额</div><div class="val">{amt}</div></div>
        <div class="kpi"><div class="lab">毛利</div><div class="val">{gp}</div></div>
        <div class="kpi"><div class="lab">增值</div><div class="val">{va}</div></div>
        <div class="kpi"><div class="lab">手机</div><div class="val">{phone}<span class="u"> 台</span></div></div>
      </div>
      <div class="sec-t"><span class="bar"></span>各板块达成 · 当日任务</div>
      <div class="rows">
{rows_html}      </div>
    </div>
    <div class="col-r">
      <div class="sec-t"><span class="bar"></span>人员战况</div>
      <div class="people">
{people_html}      </div>
{qd_html}
      <div class="review">
        <h3>核心复盘</h3>
        <p>{review_txt}</p>
      </div>
    </div>
  </div>
</div>
</body></html>""".format(
        ov=round(overall), label=label, ftime=ftime, ov_pct=rate_fmt(overall),
        amt=money(amt), gp=money(gp), va=money(va), phone="{:.0f}".format(phone),
        rows_html=rows_html, people_html=people_html, qd_html=qd_html,
        review_txt=review_txt,
    )
    return html


if __name__ == "__main__":
    out = "/Users/mac/WorkBuddy/Claw/poster_today.png"
    for i, a in enumerate(sys.argv):
        if a == "--out" and i + 1 < len(sys.argv):
            out = sys.argv[i + 1]
    d = json.load(open(DATA, encoding="utf-8"))
    html = build_html(d)
    tmp = os.path.join(BASE, "_poster_tmp.html")
    open(tmp, "w", encoding="utf-8").write(html)
    subprocess.run([NODE, RENDER_JS, tmp, out], check=True)
    print(out)
