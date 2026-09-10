#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_card.py —— 读取 data.json，用 markdown_v2 格式推送门店战报。

营业时间：10:00 - 22:00
推送格式：markdown_v2（原生表格，满屏宽）

5种卡片 + 智能选片 + 不上账提醒 + 倒推时薪 + 缺口拆解

选片规则（优先级从高到低）：
  1. 任何人增值达成率 < 当天时间进度 且 15点后 → ⑤救援
  2. 任何人增值达成率 < 当天时间进度 且 15点前 → ②语录版
  3. 10-12点  → ①完整战报
  4. 12-15点  → ④全员排行
  5. 15-18点  → ④排行（有人落后则⑤救援）
  6. 18-22点  → ⑤救援或②语录随机
  7. 22点后   → ①完整战报（总结版）
  8. 其他时段 → 5种随机

用法:
  python3 push_card.py                # 智能选片推送
  python3 push_card.py --dry          # 智能选片预览
  python3 push_card.py --card=1       # 指定卡片(1-5)
  python3 push_card.py --dry --card=3 # 预览指定卡片
  python3 push_card.py --check-no-data # 仅检查不上账并推送提醒
"""
import json, os, sys, random, urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data.json")
CONF = "/Users/mac/WorkBuddy/Claw/.wecom_webhook"
BOARD_URL = "https://zbc5241.github.io/shop/"

STORE_OPEN = 10
STORE_CLOSE = 22
ACCOUNT_LOCK = 22   # 22:00后为上账时间
ACCOUNT_DEADLINE = 22.5  # 22:30 最后催账

# 店长工号，无销售任务，有数据=上错账
SKIP_NAMES = {"张博晨"}


def load_webhook():
    v = os.environ.get("WECOM_WEBHOOK")
    if v:
        return v.strip()
    if os.path.exists(CONF):
        return open(CONF, encoding="utf-8").read().strip()
    return None


def wan(v):
    if v is None:
        return "0"
    v = v or 0
    if abs(v) >= 10000:
        return "{:.1f}万".format(v / 10000)
    return "{:,.0f}".format(v)


def pct(v):
    if v is None:
        return "-"
    return "{:.0f}%".format(v * 100)


def now_str():
    return datetime.now().strftime("%H:%M")


def now_hour():
    return datetime.now().hour


def remain_hours():
    now = datetime.now()
    close = now.replace(hour=STORE_CLOSE, minute=0, second=0, microsecond=0)
    diff = close - now
    if diff.total_seconds() <= 0:
        return 0
    return round(diff.total_seconds() / 3600, 1)


def has_today_data(d):
    meta = d.get("meta", {})
    return meta.get("dayRows", 0) > 0


def get_time_progress(d):
    meta = d.get("meta", {})
    return meta.get("timeProgress", 0) or 0


def get_remain_days(d):
    meta = d.get("meta", {})
    return meta.get("remainDays", 0)


# ========== 数据提取 ==========

def get_today_7cats(d):
    store = d.get("store", {})
    dd = store.get("dailyDone", {})
    dg = store.get("dailyGap", {})
    cats = [
        ("毛利", "毛利", "毛利"),
        ("手机", "手机", "手机"),
        ("增值", "增值", "增值"),
        ("合约", "合约", "合约"),
        ("滞销机", "滞销", "滞销"),
        ("智慧办公", "智慧办公", "智慧办公"),
        ("音频穿戴", "音频穿戴", "音频穿戴"),
    ]
    rows = []
    for label, dk, gk in cats:
        done = dd.get(dk, 0) or 0
        # dailyGap 口径：正数=今日任务，负数=旧版缺口
        gap = dg.get(gk, 0) or 0
        task = gap if gap > 0 else done
        rate = done / task if task > 0 else 0
        if gap <= 0 and done > 0:
            rate = 1.0
        rows.append({"label": label, "done": done, "task": task, "gap": gap, "rate": rate})
    return rows


def get_month_7cats(d):
    store = d.get("store", {})
    perf = store.get("performance", {})
    qcs = store.get("qcs", {})
    cats = [
        ("毛利", perf.get("毛利", {})),
        ("手机", perf.get("手机", {})),
        ("增值", qcs.get("增值", {})),
        ("合约", qcs.get("合约", {})),
        ("滞销机", qcs.get("滞销", {})),
        ("智慧办公", perf.get("智慧办公", {})),
        ("音频穿戴", perf.get("音频穿戴", {})),
    ]
    rows = []
    for label, obj in cats:
        done = obj.get("done", 0) or 0
        task = obj.get("task", 0) or 0
        gap = obj.get("gap", 0) or 0
        rate = obj.get("rate", 0) or 0
        rows.append({"label": label, "done": done, "task": task, "gap": gap, "rate": rate})
    return rows


# ========== 14品类数据（全量展示）==========

CAT14 = [
    ("毛利",      "毛利",      "毛利",      "元"),
    ("手机",      "手机",      "手机",      "台"),
    ("增值",      "增值",      "增值",      "元"),
    ("智慧办公",  "智慧办公",  "智慧办公",  "台"),
    ("音频穿戴",  "音频穿戴",  "音频穿戴",  "件"),
    ("HD",        "HD",        "HD",        "台"),
    ("Care+",     "会员",      "Care+",     "件"),
    ("回收",      "回收",      "回收",      "件"),
    ("贴膜",      "贴膜",      "贴膜",      "件"),
    ("合约",      "合约",      "合约",      "单"),
    ("滞销",      "滞销",      "滞销",      "台"),
    ("摄影课",    "摄影课",    "摄影课",    "件"),
    ("优享/会员", "优享/会员", "优享/会员", "件"),
    ("尊享/储值", "尊享/储值", "尊享/储值", "件"),
]

def fmt_14val(v, unit):
    if v is None:
        v = 0
    if unit == "元":
        return wan(v)
    elif unit == "分":
        return "{}分".format(int(v))
    else:
        return "{}{}".format(int(v), unit)


def get_today_14cats(d):
    store = d.get("store", {})
    dd = store.get("dailyDone", {})
    dg = store.get("dailyGap", {})
    rows = []
    for label, dk, gk, unit in CAT14:
        done = dd.get(dk, 0) or 0
        task = dg.get(gk, 0) or 0
        rate = done / task if task and task > 0 else None
        rows.append({"label": label, "done": done, "task": task, "rate": rate, "unit": unit})
    return rows


def get_today_gap14_per_person(d):
    people = d.get("people", {})
    meta = d.get("meta", {})
    emps = [e for e in meta.get("employees", list(people.keys())) if e not in SKIP_NAMES]
    rows = []
    for name in emps:
        p = people.get(name, {})
        dg = p.get("dailyGap", {})
        gaps = {}
        for label, dk, gk, unit in CAT14:
            gaps[label] = dg.get(gk, 0) or 0
        rows.append({"name": name, "gaps": gaps})
    rows.sort(key=lambda x: x["gaps"].get("毛利", 0), reverse=True)
    return rows


def get_today_people14(d):
    people = d.get("people", {})
    meta = d.get("meta", {})
    emps = [e for e in meta.get("employees", list(people.keys())) if e not in SKIP_NAMES]
    rows = []
    for name in emps:
        p = people.get(name, {})
        dd = p.get("dailyDone", {})
        dg = p.get("dailyGap", {})
        cats = {}
        for label, dk, gk, unit in CAT14:
            done = dd.get(dk, 0) or 0
            task = dg.get(gk, 0) or 0
            rate = done / task if task and task > 0 else None
            cats[label] = {"done": done, "task": task, "rate": rate, "unit": unit}
        mli_done = dd.get("毛利", 0) or 0
        mli_task = dg.get("毛利", 0) or 0
        rows.append({
            "name": name,
            "cats": cats,
            "mli_done": mli_done,
            "mli_task": mli_task,
            "mli_rate": mli_done / mli_task if mli_task and mli_task > 0 else 0,
            "opened": mli_done > 0 or (dd.get("手机", 0) or 0) > 0,
        })
    rows.sort(key=lambda x: (x["opened"], x["mli_done"]), reverse=True)
    return rows


def get_today_sold(d):
    meta = d.get("meta", {})
    today = meta.get("date", datetime.now().strftime("%Y-%m-%d"))
    det = d.get("details", {})
    sold = []
    for cat, items in det.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if item.get("date", "") == today:
                sold.append({
                    "emp": item.get("emp", ""),
                    "name": item.get("name", ""),
                    "cat": cat,
                    "qty": item.get("qty", 1),
                    "profit": item.get("profit", 0),
                })
    # 排除店长工号
    sold = [s for s in sold if s["emp"] not in SKIP_NAMES]
    return sold


def get_today_people(d):
    people = d.get("people", {})
    meta = d.get("meta", {})
    emps = [e for e in meta.get("employees", list(people.keys())) if e not in SKIP_NAMES]
    rows = []
    for name in emps:
        p = people.get(name, {})
        dd = p.get("dailyDone", {})
        dg = p.get("dailyGap", {})
        # dailyGap 口径：正数=今日任务（calc_data.calc_gap），负数=旧版缺口
        m_done = dd.get("毛利", 0) or 0
        m_task = dg.get("毛利", 0) or 0
        if m_task <= 0:
            m_task = m_done  # 无任务时任务=完成
        s_done = dd.get("手机", 0) or 0
        s_task = dg.get("手机", 0) or 0
        if s_task <= 0:
            s_task = s_done
        zz_done = dd.get("增值", 0) or 0
        zz_task = dg.get("增值", 0) or 0
        if zz_task <= 0:
            zz_task = zz_done
        rows.append({
            "name": name,
            "mli_done": m_done, "mli_task": m_task, "mli_rate": m_done / m_task if m_task > 0 else 0,
            "sj_done": s_done, "sj_task": s_task,
            "zz_done": zz_done, "zz_task": zz_task,
            "opened": m_done > 0 or s_done > 0,
        })
    rows.sort(key=lambda x: (x["opened"], x["mli_done"]), reverse=True)
    return rows


def get_month_people(d):
    people = d.get("people", {})
    meta = d.get("meta", {})
    emps = [e for e in meta.get("employees", list(people.keys())) if e not in SKIP_NAMES]
    rows = []
    for name in emps:
        p = people.get(name, {})
        pp = p.get("performance", {})
        pq = p.get("qcs", {})
        m = pp.get("毛利", {})
        rows.append({
            "name": name,
            "mli_done": m.get("done", 0) or 0,
            "mli_task": m.get("task", 0) or 0,
            "mli_rate": m.get("rate", 0) or 0,
            "sj_done": pp.get("手机", {}).get("done", 0) or 0,
            "sj_task": pp.get("手机", {}).get("task", 0) or 0,
            "sj_rate": pp.get("手机", {}).get("rate", 0) or 0,
            "zz_done": pq.get("增值", {}).get("done", 0) or 0,
            "zz_task": pq.get("增值", {}).get("task", 0) or 0,
            "zz_rate": pq.get("增值", {}).get("rate", 0) or 0,
        })
    rows.sort(key=lambda x: x["mli_done"], reverse=True)
    return rows


def get_today_gap_per_person(d):
    """今日每人任务（用于10点开门战报）。dailyGap：正数=今日任务。"""
    people = d.get("people", {})
    meta = d.get("meta", {})
    emps = [e for e in meta.get("employees", list(people.keys())) if e not in SKIP_NAMES]
    rows = []
    for name in emps:
        p = people.get(name, {})
        dg = p.get("dailyGap", {})
        m_gap = dg.get("毛利", 0) or 0
        s_gap = dg.get("手机", 0) or 0
        zz_gap = dg.get("增值", 0) or 0
        hy_gap = dg.get("合约", 0) or 0
        rows.append({
            "name": name,
            "mli_gap": m_gap if m_gap > 0 else 0,
            "sj_gap": s_gap if s_gap > 0 else 0,
            "zz_gap": zz_gap if zz_gap > 0 else 0,
            "hy_gap": hy_gap if hy_gap > 0 else 0,
        })
    # 按毛利任务降序
    rows.sort(key=lambda x: x["mli_gap"], reverse=True)
    return rows


def get_insights_advices(d):
    """提取智能建议中的关键信息"""
    ins = d.get("insights", {})
    advs = ins.get("advices", [])
    if not isinstance(advs, list):
        return []
    return advs


def get_hourly_target(d, remain_h):
    """倒推时薪：剩余每小时需完成多少毛利
    dailyGap 口径：正数=今日任务（calc_data.calc_gap）。"""
    store = d.get("store", {})
    done = store.get("dailyDone", {}).get("毛利", 0) or 0
    task = store.get("dailyGap", {}).get("毛利", 0) or 0
    remaining = max(task - done, 0)
    if remain_h <= 0:
        return {"need": remaining, "per_hour": 0, "remain_h": 0}
    return {"need": remaining, "per_hour": remaining / remain_h, "remain_h": remain_h}


# ========== 不上账提醒 ==========

def build_no_data_alert(d):
    """不上账提醒消息"""
    now = now_str()
    hour = now_hour()
    meta = d.get("meta", {})
    remain_days = get_remain_days(d)

    if hour < 12:
        level = "📊"
        msg = "上午数据待上账，请导购及时录单"
    elif hour < 15:
        level = "⚠️"
        msg = "今日仍无上账记录，请导购尽快录单"
    elif hour < 19:
        level = "🚨"
        msg = "今日0上账！请立即检查是否漏单"
    elif hour < 22:
        level = "🚨"
        msg = "今日0上账！请立即检查是否漏单"
    else:
        level = "🚨"
        msg = "闭店上账提醒：请导购30分钟内完成录单"

    L = []
    L.append("# {} 数据提醒 · {}".format(level, now))
    L.append("")
    L.append("> {}".format(msg))
    L.append("")
    L.append("📊 [查看实时看板]({})".format(BOARD_URL))
    return "\n".join(L)


# ========== 5种卡片模板 ==========

def fmt_cat_row(c):
    if c["label"] in ("毛利", "增值"):
        done_s, task_s = wan(c["done"]), wan(c["task"])
    elif c["label"] == "合约":
        done_s, task_s = "{}分".format(int(c["done"])), "{}分".format(int(c["task"]))
    else:
        unit = "台" if c["label"] in ("手机", "智慧办公") else "件"
        done_s, task_s = "{}{}".format(int(c["done"]), unit), "{}{}".format(int(c["task"]), unit)
    return "| {} | {} | {} | {} |".format(c["label"], task_s, done_s, pct(c["rate"]))


def card_1(d, rows_t, rows_m, meta_info):
    """① 完整战报 — 7品类+全员排行+缺口拆解+行动建议"""
    now = now_str()
    rh = remain_hours()
    is_today = has_today_data(d)
    remain_days = get_remain_days(d)
    cats = get_today_7cats(d) if is_today else get_month_7cats(d)
    rows = rows_t if is_today else rows_m
    ins_advs = get_insights_advices(d)
    rh_info = get_hourly_target(d, rh) if is_today else None

    L = []
    if is_today:
        L.append("# 📊 今日战报 · {}".format(now))
        L.append("")
        if rh > 0:
            L.append("> 距闭店剩余 **{}** 小时 · 月底剩余 **{}** 天".format(rh, remain_days))
        else:
            L.append("> 今日已闭店 · 月底剩余 **{}** 天".format(remain_days))
    else:
        L.append("# 📊 开门战报 · {}".format(now))
        L.append("")
        if rh > 0:
            L.append("> 距闭店剩余 **{}** 小时 · 月底剩余 **{}** 天".format(rh, remain_days))
        else:
            L.append("> 月底剩余 **{}** 天".format(remain_days))
    L.append("")
    L.append("---")
    L.append("")

    # 7品类进度（任务→达成→达成率）
    L.append("## 📈 {}7品类进度".format("今日" if is_today else "月度"))
    L.append("")
    L.append("| 品类 | 任务 | 达成 | 达成率 |")
    L.append("|------|------|------|--------|")
    for c in cats:
        L.append(fmt_cat_row(c))
    L.append("")
    L.append("---")
    L.append("")

    # 今日成交明细（仅有当日数据时）
    if is_today:
        today_sold = get_today_sold(d)
        if today_sold:
            L.append("## 🛒 今日成交明细")
            L.append("")
            L.append("| 导购 | 产品 | 品类 | 毛利 |")
            L.append("|------|------|------|------|")
            for s in today_sold[:15]:
                pname = s["name"]
                if len(pname) > 20:
                    pname = pname[:18] + ".."
                L.append("| {} | {} | {} | {} |".format(s["emp"], pname, s["cat"], wan(s["profit"])))
            if len(today_sold) > 15:
                L.append("| ... | 共{}笔 | | |".format(len(today_sold)))
            L.append("")
            L.append("---")
            L.append("")

    # 全员排行
    if is_today:
        L.append("## 👥 今日全员进度")
        L.append("")
        L.append("| # | 姓名 | 今日毛利 | 今日手机 | 状态 |")
        L.append("|---|------|----------|----------|------|")
        for i, r in enumerate(rows):
            status = "✅已开单" if r["opened"] else "🚨未开单"
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
            L.append("| {} | {} | {} | {}台 | {} |".format(
                medal, r["name"], wan(r["mli_done"]), int(r["sj_done"]), status))
    else:
        L.append("## 👥 全员毛利排行")
        L.append("")
        L.append("| # | 姓名 | 毛利 | 任务 | 达成率 |")
        L.append("|---|------|------|------|--------|")
        for i, r in enumerate(rows):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
            if r["mli_rate"] >= 1:
                status = "✅达标"
            elif r["mli_rate"] >= 0.6:
                status = "⚡加油"
            else:
                status = "🚨援救"
            L.append("| {} | {} | {} | {} | {} {} |".format(
                medal, r["name"], wan(r["mli_done"]), wan(r["mli_task"]),
                pct(r["mli_rate"]), status))
    L.append("")
    L.append("---")
    L.append("")

    # 10点开门战报：今日缺口拆解
    if not is_today and now_hour() < 12:
        gaps = get_today_gap_per_person(d)
        L.append("## 📋 今日每人任务")
        L.append("")
        L.append("| 姓名 | 毛利缺口 | 手机缺口 | 增值缺口 | 合约缺口 |")
        L.append("|------|----------|----------|----------|----------|")
        for g in gaps:
            L.append("| {} | {} | {}台 | {} | {}分 |".format(
                g["name"], wan(g["mli_gap"]), int(g["sj_gap"]),
                wan(g["zz_gap"]), int(g["hy_gap"])))
        L.append("")
        L.append("---")
        L.append("")

    # 倒推时薪（今日模式且有剩余时间）
    if is_today and rh_info and rh_info["remain_h"] > 0 and rh_info["need"] > 0:
        L.append("## ⏰ 倒推时薪")
        L.append("")
        L.append("> 剩余毛利缺口 **{}** · 距闭店 **{}** 小时".format(
            wan(rh_info["need"]), rh_info["remain_h"]))
        L.append(">")
        L.append("> 每小时保底成交 **{}**".format(wan(rh_info["per_hour"])))
        L.append("")
        L.append("---")
        L.append("")

    # 行动建议
    advices = build_advices(d, cats, rows, is_today, rh)
    L.append("## 🎯 下一步行动")
    L.append("")
    for a in advices:
        L.append("> {}".format(a))
    L.append("")
    L.append("---")
    L.append("")
    L.append("📊 [查看实时看板]({})".format(BOARD_URL))
    return "\n".join(L)


def card_2(d, rows_t, rows_m, meta_info):
    """② 语录版 — MVP表格 + 主力引用块带语录 + 救援引用块"""
    now = now_str()
    rh = remain_hours()
    is_today = has_today_data(d)
    remain_days = get_remain_days(d)
    rows = rows_t if is_today else rows_m

    L = []
    L.append("# 📊 战报语录 · {}".format(now))
    L.append("")
    if rh > 0:
        L.append("> 距闭店剩余 **{}** 小时".format(rh))
    else:
        L.append("> 今日已闭店")
    L.append("")
    L.append("---")
    L.append("")

    if not rows:
        L.append("> 暂无人员数据")
        L.append("")
        L.append("---")
        L.append("")
        L.append("📊 [查看实时看板]({})".format(BOARD_URL))
        return "\n".join(L)

    # MVP：只从毛利达标（达成率≥100%）的人里选
    qualified = [r for r in rows if r.get("mli_task", 0) > 0 and r.get("mli_rate", 0) >= 1.0]
    mvp = max(qualified, key=lambda x: x["mli_done"]) if qualified else None

    if mvp:
        L.append("## 🏆 MVP · {}".format(mvp["name"]))
        L.append("")
        L.append("| 品类 | 完成 | 任务 | 达成率 |")
        L.append("|------|------|------|------|")
        if is_today:
            L.append("| 毛利 | {} | {} | {} |".format(wan(mvp["mli_done"]), wan(mvp["mli_task"]), pct(mvp["mli_rate"])))
            L.append("| 手机 | {}台 | {}台 | - |".format(int(mvp["sj_done"]), int(mvp["sj_task"])))
            L.append("| 增值 | {} | {} | - |".format(wan(mvp["zz_done"]), wan(mvp["zz_task"])))
        else:
            L.append("| 毛利 | {} | {} | {} |".format(wan(mvp["mli_done"]), wan(mvp["mli_task"]), pct(mvp["mli_rate"])))
            L.append("| 手机 | {}台 | {}台 | {} |".format(int(mvp["sj_done"]), int(mvp["sj_task"]), pct(mvp["sj_rate"])))
            L.append("| 增值 | {} | {} | {} |".format(wan(mvp["zz_done"]), wan(mvp["zz_task"]), pct(mvp["zz_rate"])))
    else:
        L.append("## 📊 今日暂无达标")
        L.append("")
        L.append("> 还没有人完成今日毛利任务，继续加油！")
    L.append("")
    L.append("---")
    L.append("")

    # 主力输出：只夸达标的人
    L.append("## 🔥 主力输出")
    L.append("")
    praise = [r for r in rows[:3] if r.get("mli_rate", 0) >= 1.0] if is_today else \
             [r for r in rows[:3] if r.get("mli_rate", 0) >= 1.0]
    if praise:
        for i, r in enumerate(praise):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
            quote = "实力扛鼎，超额完成" if i == 0 else "稳扎稳打，达标稳了" if i == 1 else "咬牙坚持，达成在望"
            L.append("> {} **{}** · 毛利 {}（{}）".format(
                medal, r["name"], wan(r["mli_done"]), pct(r.get("mli_rate", 0))))
            L.append(">")
            L.append("> \"{}\"".format(quote))
            L.append("")
    else:
        L.append("> 今日尚无达标，全员冲刺！")
        L.append("")
    L.append("---")
    L.append("")

    # 需要关注：达成率最低的人
    if rows:
        worst = min(rows, key=lambda x: x.get("mli_rate", 0))
        if worst.get("mli_rate", 0) < 1.0:
            L.append("## 📌 重点关注")
            L.append("")
            L.append("> **{}** 达成率 {}".format(worst["name"], pct(worst.get("mli_rate", 0))))
            L.append(">")
            if is_today:
                L.append("> 今日毛利缺口 {} · 手机缺口 {}台".format(
                    wan(abs(worst.get("mli_task", 0) - worst.get("mli_done", 0))),
                    int(abs(worst.get("sj_task", 0) - worst.get("sj_done", 0)))))
            else:
                L.append("> 毛利缺口 {} · 手机缺口 {}台".format(
                    wan(worst["mli_task"] - worst["mli_done"]),
                    int(worst["sj_task"] - worst["sj_done"])))
            L.append("")
            L.append("---")
            L.append("")

    L.append("📊 [查看实时看板]({})".format(BOARD_URL))
    return "\n".join(L)


def card_3(d, rows_t, rows_m, meta_info):
    """③ MVP卡片 — 只选达标者，无达标则出全店概览"""
    now = now_str()
    is_today = has_today_data(d)
    rows = rows_t if is_today else rows_m

    if not rows:
        return "> 暂无人员数据\n\n📊 [查看实时看板]({})".format(BOARD_URL)

    # MVP：只从毛利达标者中选，超额越多越优先
    qualified = [r for r in rows if r.get("mli_task", 0) > 0 and r.get("mli_rate", 0) >= 1.0]
    mvp = max(qualified, key=lambda x: x["mli_done"]) if qualified else None

    L = []
    if mvp:
        L.append("# 🏆 MVP · {}".format(mvp["name"]))
        L.append("")
        L.append("| 品类 | 完成 | 任务 | 达成率 |")
        L.append("|------|------|------|------|")
        if is_today:
            L.append("| 毛利 | {} | {} | {} |".format(wan(mvp["mli_done"]), wan(mvp["mli_task"]), pct(mvp["mli_rate"])))
            L.append("| 手机 | {}台 | {}台 | - |".format(int(mvp["sj_done"]), int(mvp["sj_task"])))
            L.append("| 增值 | {} | {} | - |".format(wan(mvp["zz_done"]), wan(mvp["zz_task"])))
        else:
            L.append("| 毛利 | {} | {} | {} |".format(wan(mvp["mli_done"]), wan(mvp["mli_task"]), pct(mvp["mli_rate"])))
            L.append("| 手机 | {}台 | {}台 | {} |".format(int(mvp["sj_done"]), int(mvp["sj_task"]), pct(mvp["sj_rate"])))
            L.append("| 增值 | {} | {} | {} |".format(wan(mvp["zz_done"]), wan(mvp["zz_task"]), pct(mvp["zz_rate"])))
        L.append("")
        L.append("> 实力扛鼎，超额完成，当之无愧！")
    else:
        L.append("# 📊 全店概览 · {}".format(now))
        L.append("")
        L.append("> 今日尚无人达标，全员继续冲刺！")
        L.append("")
        L.append("| # | 姓名 | 毛利 | 达成率 | 状态 |")
        L.append("|---|------|------|--------|------|")
        for i, r in enumerate(rows):
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
            rate = r.get("mli_rate", 0)
            if is_today:
                status = "✅已开单" if r["opened"] else "🚨未开单"
            else:
                status = "✅达标" if rate >= 1 else ("⚡加油" if rate >= 0.6 else "🚨落后")
            L.append("| {} | {} | {} | {} | {} |".format(medal, r["name"], wan(r["mli_done"]), pct(rate), status))
    L.append("")
    L.append("---")
    L.append("")
    L.append("📊 [查看实时看板]({})".format(BOARD_URL))
    return "\n".join(L)


def card_4(d, rows_t, rows_m, meta_info):
    """④ 全员实力排行 — 单表格+引用+链接"""
    now = now_str()
    rh = remain_hours()
    is_today = has_today_data(d)
    remain_days = get_remain_days(d)
    rows = rows_t if is_today else rows_m

    L = []
    if is_today:
        L.append("# 📊 今日全员排行 · {}".format(now))
        L.append("")
        if rh > 0:
            L.append("> 距闭店剩余 **{}** 小时".format(rh))
        else:
            L.append("> 今日已闭店")
    else:
        L.append("# 📊 全员实力排行 · {}".format(now))
        L.append("")
        L.append("> 月底剩余 **{}** 天".format(remain_days))
    L.append("")
    L.append("---")
    L.append("")
    L.append("| # | 姓名 | 毛利 | 达成率 | 状态 |")
    L.append("|---|------|------|--------|------|")
    for i, r in enumerate(rows):
        medal = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
        rate = r.get("mli_rate", 0)
        if is_today:
            if r["opened"]:
                status = "✅已开单"
            else:
                status = "🚨未开单"
        else:
            if rate >= 1:
                status = "✅达标"
            elif rate >= 0.6:
                status = "⚡加油"
            else:
                status = "🚨援救"
        L.append("| {} | {} | {} | {} | {} |".format(medal, r["name"], wan(r["mli_done"]), pct(rate), status))
    L.append("")
    L.append("---")
    L.append("")

    # 今日模式：加倒推时薪
    if is_today and rh > 0:
        rh_info = get_hourly_target(d, rh)
        if rh_info["need"] > 0:
            L.append("> ⏰ 剩余毛利缺口 {} · 每小时保底 {}".format(
                wan(rh_info["need"]), wan(rh_info["per_hour"])))
            L.append("")
            L.append("---")
            L.append("")

    L.append("📊 [查看实时看板]({})".format(BOARD_URL))
    return "\n".join(L)


def card_5(d, rows_t, rows_m, meta_info):
    """⑤ 救援卡片 — 救援人员表格+加粗喊话+引用+链接"""
    now = now_str()
    rh = remain_hours()
    is_today = has_today_data(d)
    remain_days = get_remain_days(d)
    rows = rows_t if is_today else rows_m

    if not rows:
        return "> 暂无人员数据\n\n📊 [查看实时看板]({})".format(BOARD_URL)

    rescue = sorted(rows, key=lambda x: x.get("mli_rate", 0))[0]

    L = []
    L.append("# 🚨 需要救援 · {}".format(now))
    L.append("")
    if rh > 0:
        L.append("> 距闭店剩余 **{}** 小时".format(rh))
    else:
        L.append("> 今日已闭店")
    L.append("")
    L.append("---")
    L.append("")
    L.append("**{}** 达成率仅 **{}**，需要支援！".format(rescue["name"], pct(rescue.get("mli_rate", 0))))
    L.append("")
    L.append("| 品类 | 完成 | 任务 | 缺口 |")
    L.append("|------|------|------|------|")
    L.append("| 毛利 | {} | {} | -{} |".format(
        wan(rescue["mli_done"]), wan(rescue["mli_task"]),
        wan(rescue["mli_task"] - rescue["mli_done"])))
    L.append("| 手机 | {}台 | {}台 | -{}台 |".format(
        int(rescue["sj_done"]), int(rescue["sj_task"]),
        int(rescue["sj_task"] - rescue["sj_done"])))
    L.append("| 增值 | {} | {} | -{} |".format(
        wan(rescue["zz_done"]), wan(rescue["zz_task"]),
        wan(rescue["zz_task"] - rescue["zz_done"])))
    L.append("")
    L.append("> {} 加油！还有 {} 天，翻盘有机会 💪".format(rescue["name"], remain_days))
    L.append("")
    L.append("---")
    L.append("")

    # 倒推时薪
    if is_today and rh > 0:
        rh_info = get_hourly_target(d, rh)
        if rh_info["need"] > 0:
            L.append("> ⏰ 全店剩余毛利缺口 {} · 每小时保底 {}".format(
                wan(rh_info["need"]), wan(rh_info["per_hour"])))
            L.append("")
            L.append("---")
            L.append("")

    L.append("📊 [查看实时看板]({})".format(BOARD_URL))
    return "\n".join(L)


# ========== 行动建议 ==========

def build_advices(d, cats, rows, is_today, rh):
    advices = []
    remain_days = get_remain_days(d)
    tp = get_time_progress(d)

    if is_today:
        # 今日模式
        # dailyGap 口径：正数=今日任务（calc_data.calc_gap），缺口=task-done
        worst = min(cats, key=lambda x: x["rate"]) if cats else None
        if worst and worst["task"] > 0 and worst["rate"] < 0.5:
            remain = worst["task"] - worst["done"]
            if worst["label"] in ("毛利", "增值"):
                gap_s = wan(remain)
            else:
                gap_s = "{}{}".format(int(remain), "台" if worst["label"] in ("手机", "智慧办公") else "件/分")
            advices.append("📌 {} 今日进度仅 {}，缺口 {}，重点推".format(
                worst["label"], pct(worst["rate"]), gap_s))

        idle = [r["name"] for r in rows if not r["opened"]]
        if idle and rh > 0:
            advices.append("🚨 {} 今日尚未开单，优先安排接待".format("、".join(idle)))

        # MVP：只从今日毛利达标（达成率≥100%）的人里选，超额越多越优先
        qualified = [r for r in rows if r["mli_task"] > 0 and r["mli_rate"] >= 1.0]
        if qualified:
            mvp = max(qualified, key=lambda x: x["mli_done"])
            if mvp["mli_rate"] >= 1.0:
                advices.append("🏆 MVP {} 今日毛利 {}（{}），超额完成！".format(
                    mvp["name"], wan(mvp["mli_done"]), pct(mvp["mli_rate"])))

        if 0 < rh <= 2:
            advices.append("⏰ 距闭店仅剩 {} 小时，冲刺开单".format(rh))
        elif rh == 0:
            advices.append("🌙 今日已闭店，复盘明日计划")
    else:
        # 月度模式
        worst_p = min(rows, key=lambda x: x["mli_rate"]) if rows else None
        if worst_p and worst_p["mli_task"] > 0 and worst_p["mli_rate"] < 0.5:
            gap = worst_p["mli_task"] - worst_p["mli_done"]
            advices.append("📌 {} 毛利达成仅 {}，缺口 {}，需重点帮扶".format(
                worst_p["name"], pct(worst_p["mli_rate"]), wan(gap)))

        # 月度模式：MVP只选达标者
        qualified_m = [r for r in rows if r["mli_task"] > 0 and r["mli_rate"] >= 1.0]
        if qualified_m:
            mvp_p = max(qualified_m, key=lambda x: x["mli_done"])
            advices.append("🏆 {} 毛利 {} 领跑全店（{}），达标！".format(
                mvp_p["name"], wan(mvp_p["mli_done"]), pct(mvp_p["mli_rate"])))

        if remain_days > 0:
            advices.append("⏰ 月底剩余 {} 天，抓紧上账冲量".format(remain_days))

        if rh > 0:
            advices.append("📊 今日数据待上账，催导购及时录单")

    # insights 中的零成交品类
    ins_advs = get_insights_advices(d)
    for adv in ins_advs:
        if adv.get("level") == "danger" and "零成交" in adv.get("title", ""):
            advices.append("⚠️ {}".format(adv.get("body", "")[:40]))
            break

    if not advices:
        advices.append("✅ 进度正常，保持节奏")

    return advices


# ========== 智能选片 ==========

CARDS = [card_1, card_2, card_3, card_4, card_5]
CARD_NAMES = ["①完整战报", "②语录版", "③MVP卡片", "④全员排行", "⑤救援卡片"]


# ========== 固定卡片：今日任务 / 当日进度 / 今日总达成 ==========

def build_task_advice(d, cats14, gaps14):
    advices = []
    n = len(gaps14) if gaps14 else 1
    for c in cats14:
        label, task, unit = c["label"], c["task"], c["unit"]
        if not task or task <= 0:
            continue
        per = task / n
        if label == "毛利":
            advices.append("💰 今日毛利目标 {}，每人约 {}".format(
                fmt_14val(task, unit), fmt_14val(per, unit)))
        elif label == "手机":
            advices.append("📱 今日手机 {} 台，每人 {} 台".format(
                int(task), int(per)))
        elif label == "增值":
            advices.append("💎 增值今日 {}，配件+服务搭售冲".format(
                fmt_14val(task, unit)))
        elif label == "智慧办公":
            advices.append("💻 智慧办公 {} 台，PC+平板主推".format(int(task)))
        elif label == "音频穿戴":
            advices.append("🎧 音频穿戴 {} 件，手环耳机搭售".format(int(task)))
        elif label == "HD":
            advices.append("📺 HD {} 台，智慧屏场景演示".format(int(task)))
        elif label == "Care+":
            advices.append("🛡️ Care+ {} 单，每3台手机搭1单".format(int(task)))
        elif label == "回收":
            advices.append("♻️ 回收 {} 单，以旧换新主动问".format(int(task)))
        elif label == "贴膜":
            advices.append("📐 贴膜 {} 件，每台机器配膜".format(int(task)))
        elif label == "合约":
            advices.append("📡 合约 {} 单，办卡入网冲量".format(int(task)))
        elif label == "滞销":
            advices.append("⚠️ 滞销机 {} 台，专人盯样机".format(int(task)))
        elif label == "摄影课":
            advices.append("📸 摄影课 {} 场，大师课邀约".format(int(task)))
        elif label == "优享/会员":
            advices.append("⭐ 优享会员 {} 单，会员体系推".format(int(task)))
        elif label == "尊享/储值":
            advices.append("🔷 尊享储值 {} 单，高净值客户推".format(int(task)))
    if not advices:
        advices.append("✅ 各品类均已达标，保持节奏")
    advices.append("💪 今日努力，月度无忧，加油！")
    return advices


def card_task(d, rows_t, rows_m, meta_info):
    """今日任务卡（10:00推送）——14品类全量+每人任务+店长寄语"""
    now = now_str()
    remain_days = get_remain_days(d)
    cats14 = get_today_14cats(d)
    gaps14 = get_today_gap14_per_person(d)

    L = []
    L.append("# 🎯 今日任务 · {}".format(now))
    L.append("")
    L.append("> 月底剩余 **{}** 天 · 营业时间 10:00-22:00".format(remain_days))
    L.append("")
    L.append("---")
    L.append("")

    # 全店今日任务
    L.append("## 📋 今日任务")
    L.append("")
    L.append("| 品类 | 今日任务 |")
    L.append("|------|---------|")
    for c in cats14:
        t_s = fmt_14val(c["task"], c["unit"]) if c["task"] else "✅"
        L.append("| {} | {} |".format(c["label"], t_s))
    L.append("")
    L.append("---")
    L.append("")

    # 每人任务（转置表：品类为行，人为列）
    L.append("## 👤 每人今日任务")
    L.append("")
    names = [g["name"] for g in gaps14]
    header = "| 品类 |" + "|".join(" {} ".format(n) for n in names) + "| 全店 |"
    sep = "|------|" + "|".join("------" for _ in names) + "|------|"
    L.append(header)
    L.append(sep)
    store_dg = d.get("store", {}).get("dailyGap", {})
    for label, dk, gk, unit in CAT14:
        cells = ["| {} |".format(label)]
        for g in gaps14:
            v = g["gaps"].get(label, 0)
            cells.append(" {} |".format(fmt_14val(v, unit) if v else "—"))
        sv = store_dg.get(gk, 0) or 0
        cells.append(" {} |".format(fmt_14val(sv, unit) if sv else "—"))
        L.append("".join(cells))
    L.append("")
    L.append("---")
    L.append("")

    # 今日重点
    L.append("## 💬 今日重点")
    L.append("")
    advice = build_task_advice(d, cats14, gaps14)
    for a in advice:
        L.append("> {}".format(a))
        L.append(">")
    L.append("")
    return "\n".join(L)


def card_progress(d, rows_t, rows_m, meta_info):
    """当日进度卡（12/16/20/22推送）——14品类今日进度+全员排行+倒推时薪+行动建议"""
    now = now_str()
    rh = remain_hours()
    is_today = has_today_data(d)
    cats14 = get_today_14cats(d) if is_today else []
    people14 = get_today_people14(d) if is_today else []

    L = []
    L.append("# 📈 当日进度 · {}".format(now))
    L.append("")
    if rh > 0:
        L.append("> 距闭店剩余 **{}** 小时".format(rh))
    else:
        L.append("> 今日已闭店")
    L.append("")
    L.append("---")
    L.append("")

    if is_today and cats14:
        # 今日品类进度
        L.append("## 📊 今日品类进度")
        L.append("")
        L.append("| 品类 | 任务 | 达成 | 达成率 |")
        L.append("|------|------|------|--------|")
        for c in cats14:
            t_s = fmt_14val(c["task"], c["unit"]) if c["task"] else "✅"
            d_s = fmt_14val(c["done"], c["unit"])
            r_s = pct(c["rate"]) if c["rate"] is not None else "—"
            L.append("| {} | {} | {} | {} |".format(c["label"], t_s, d_s, r_s))
        L.append("")
        L.append("---")
        L.append("")

    if is_today and people14:
        # 全员今日进度
        L.append("## 👥 全员今日进度")
        L.append("")
        L.append("| # | 姓名 | 毛利 | 手机 | 增值 | 合约 | 状态 |")
        L.append("|---|------|------|------|------|------|------|")
        for i, p in enumerate(people14):
            mli = p["cats"].get("毛利", {})
            sj = p["cats"].get("手机", {})
            zz = p["cats"].get("增值", {})
            hy = p["cats"].get("合约", {})
            status = "✅已开单" if p["opened"] else "🚨未开单"
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
            L.append("| {} | {} | {} | {} | {} | {} | {} |".format(
                medal, p["name"],
                fmt_14val(mli["done"], "元"),
                fmt_14val(sj["done"], "台"),
                fmt_14val(zz["done"], "元"),
                fmt_14val(hy["done"], "单"),
                status))
        L.append("")
        L.append("---")
        L.append("")

    # 倒推时薪
    if is_today and rh > 0:
        rh_info = get_hourly_target(d, rh)
        if rh_info["need"] > 0:
            L.append("## ⏰ 倒推时薪")
            L.append("")
            L.append("> 距闭店 **{}** 小时 · 剩余毛利缺口 **{}**".format(rh_info["remain_h"], wan(rh_info["need"])))
            L.append(">")
            L.append("> 每小时保底成交 **{}**".format(wan(rh_info["per_hour"])))
            L.append("")
            L.append("---")
            L.append("")

    # 行动建议
    rows = rows_t if is_today else rows_m
    cats_7 = get_today_7cats(d) if is_today else get_month_7cats(d)
    advices = build_advices(d, cats_7, rows, is_today, rh)
    L.append("## 🎯 行动建议")
    L.append("")
    for a in advices[:3]:
        L.append("> {}".format(a))
        L.append(">")
    L.append("")
    return "\n".join(L)


def card_report(d, rows_t, rows_m, meta_info):
    """今日总战报（22:45推送）——14品类总达成+全员排行+MVP+帮扶策略"""
    now = now_str()
    is_today = has_today_data(d)
    remain_days = get_remain_days(d)
    cats14 = get_today_14cats(d) if is_today else []
    people14 = get_today_people14(d) if is_today else []

    L = []
    L.append("# 📊 今日战报 · {}".format(now))
    L.append("")
    rh = remain_hours()
    if rh > 0:
        L.append("> 距闭店剩余 **{}** 小时 · 月底剩余 **{}** 天".format(rh, remain_days))
    else:
        L.append("> 今日已闭店 · 月底剩余 **{}** 天".format(remain_days))
    L.append("")
    L.append("---")
    L.append("")

    if is_today and cats14:
        # 今日品类总达成
        L.append("## 📊 今日品类达成")
        L.append("")
        L.append("| 品类 | 任务 | 达成 | 达成率 |")
        L.append("|------|------|------|--------|")
        for c in cats14:
            t_s = fmt_14val(c["task"], c["unit"]) if c["task"] else "✅"
            d_s = fmt_14val(c["done"], c["unit"])
            r_s = pct(c["rate"]) if c["rate"] is not None else "—"
            L.append("| {} | {} | {} | {} |".format(c["label"], t_s, d_s, r_s))
        L.append("")
        L.append("---")
        L.append("")

    if is_today and people14:
        # 全员今日排行
        L.append("## 👥 全员今日排行")
        L.append("")
        L.append("| # | 姓名 | 毛利 | 毛利达成率 | 手机 | 增值 |")
        L.append("|---|------|------|-----------|------|------|")
        for i, p in enumerate(people14):
            mli = p["cats"].get("毛利", {})
            sj = p["cats"].get("手机", {})
            zz = p["cats"].get("增值", {})
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else str(i + 1)
            r_s = pct(mli["rate"]) if mli["rate"] is not None else "—"
            L.append("| {} | {} | {} | {} | {} | {} |".format(
                medal, p["name"],
                fmt_14val(mli["done"], "元"), r_s,
                fmt_14val(sj["done"], "台"),
                fmt_14val(zz["done"], "元")))
        L.append("")
        L.append("---")
        L.append("")

        # MVP（只从毛利达标者中选）
        L.append("## 🏆 今日MVP")
        L.append("")
        qualified = [p for p in people14 if p["mli_task"] and p["mli_task"] > 0 and p["mli_rate"] >= 1.0]
        if qualified:
            mvp = max(qualified, key=lambda x: x["mli_done"])
            L.append("> 🏆 **{}** 今日毛利 {}（{}），超额完成！".format(
                mvp["name"], wan(mvp["mli_done"]), pct(mvp["mli_rate"])))
        else:
            L.append("> 今日暂无达标，全员冲刺！")
        L.append("")
        L.append("---")
        L.append("")

        # 帮扶策略（未达标者）
        L.append("## 📌 帮扶策略")
        L.append("")
        unqualified = [p for p in people14 if p["mli_task"] and p["mli_task"] > 0 and p["mli_rate"] < 1.0]
        if unqualified:
            worst = min(unqualified, key=lambda x: x["mli_rate"])
            gap = worst["mli_task"] - worst["mli_done"]
            L.append("> 📌 **{}** 毛利达成 {}，缺口 {}，明日重点帮扶".format(
                worst["name"], pct(worst["mli_rate"]), wan(gap)))
            L.append(">")
            L.append("> 💡 先确认是客流少、接待量少还是成交率低，对症帮扶")
        else:
            L.append("> ✅ 全员达标，保持节奏")
        L.append("")
    else:
        L.append("> 今日无上账数据")
        L.append("")

    L.append("---")
    L.append("")
    L.append("📊 [查看实时看板]({})".format(BOARD_URL))
    L.append("")
    return "\n".join(L)


def pick_card(d, rows_t, rows_m, meta_info, hour=None):
    """
    选片规则（优先级从高到低）：
    1. 任何人增值达成率 < 当天时间进度 且 15点后 → ⑤救援
    2. 任何人增值达成率 < 当天时间进度 且 15点前 → ②语录版
    3. 10-12点  → ①完整战报
    4. 12-15点  → ④全员排行
    5. 15-18点  → ④排行（有人落后则⑤救援）
    6. 18-22点  → ⑤救援或②语录随机
    7. 22点后   → ①完整战报（总结版）
    8. 其他时段 → 5种随机
    """
    if hour is None:
        hour = now_hour()

    tp = get_time_progress(d)
    rows = rows_t if has_today_data(d) else rows_m

    # 检查任何人增值达成率 < 时间进度
    zz_behind = any(r.get("zz_rate", 0) < tp for r in rows) if rows else False

    if zz_behind and hour >= 15:
        return card_5
    if zz_behind and hour < 15:
        return card_2
    if 10 <= hour < 12:
        return card_1
    elif 12 <= hour < 15:
        return card_4
    elif 15 <= hour < 18:
        return card_4
    elif 18 <= hour < 22:
        return random.choice([card_5, card_2])
    elif hour >= 22:
        return card_1
    else:
        return random.choice(CARDS)


# ========== 推送 ==========

def send_markdown_v2(webhook, content):
    payload = json.dumps(
        {"msgtype": "markdown_v2", "markdown_v2": {"content": content}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    check_no_data = "--check-no-data" in sys.argv
    card_num = None
    fixed_mode = None
    for arg in sys.argv[1:]:
        if arg.startswith("--card="):
            try:
                card_num = int(arg.split("=", 1)[1])
            except ValueError:
                pass
        elif arg.startswith("--mode="):
            m = arg.split("=", 1)[1].strip().lower()
            if m in ("task", "progress", "report"):
                fixed_mode = m

    d = json.load(open(DATA, encoding="utf-8"))
    rows_t = get_today_people(d)
    rows_m = get_month_people(d)
    meta_info = {
        "remain_days": get_remain_days(d),
        "time_progress": get_time_progress(d),
        "is_today": has_today_data(d),
    }

    # 不上账提醒模式
    if check_no_data:
        if not has_today_data(d):
            content = build_no_data_alert(d)
            print(content)
            print("\n" + "=" * 60)
            if dry:
                print("（--dry 模式，未推送）")
                sys.exit(0)
            wh = load_webhook()
            if not wh:
                print("⚠️ 未配置 webhook")
                sys.exit(1)
            resp = send_markdown_v2(wh, content)
            print("📤 推送结果:", resp)
        else:
            print("✅ 今日有上账数据，无需提醒")
        sys.exit(0)

    # 固定模式（新排期）：task=今日任务 / progress=当日进度 / report=总战报
    if fixed_mode == "task":
        func = card_task
    elif fixed_mode == "progress":
        func = card_progress
    elif card_num and 1 <= card_num <= 5:
        func = CARDS[card_num - 1]
    elif fixed_mode == "report":
        func = card_report
    else:
        func = pick_card(d, rows_t, rows_m, meta_info)

    content = func(d, rows_t, rows_m, meta_info)

    print(content)
    print("\n" + "=" * 60)
    mode_name = {"task": "🎯今日任务卡", "progress": "📈当日进度卡", "report": "📊今日总战报"}.get(fixed_mode)
    if mode_name:
        print("卡片类型: {}".format(mode_name))
    else:
        print("卡片类型: {}".format(CARD_NAMES[CARDS.index(func)] if func in CARDS else "自定义"))

    if dry:
        print("（--dry 模式，未推送）")
        sys.exit(0)

    wh = load_webhook()
    if not wh:
        print("⚠️ 未配置 webhook")
        sys.exit(1)

    resp = send_markdown_v2(wh, content)
    print("📤 推送结果:", resp)
