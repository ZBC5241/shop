#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_card_color.py —— markdown旧版 + font颜色版（格式C）
不支持表格，用加粗+三种颜色（绿/灰/橙红）展示数据。
用法:
  python3 push_card_color.py          # 推送
  python3 push_card_color.py --dry    # 预览
"""
import json, os, sys, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data.json")
CONF = "/Users/mac/WorkBuddy/Claw/.wecom_webhook"
BOARD_URL = "https://zbc5241.github.io/shop/"

def load_webhook():
    v = os.environ.get("WECOM_WEBHOOK")
    if v: return v.strip()
    if os.path.exists(CONF): return open(CONF, encoding="utf-8").read().strip()
    return None

def wan(v):
    if v >= 10000: return "{:.1f}万".format(v / 10000)
    return "{:,.0f}".format(v)

def pct(v):
    if v is None: return "-"
    return "{:.0f}%".format(v * 100)

def color_rate(rate):
    """根据达成率返回带颜色的文本"""
    if rate >= 1:
        return '<font color="info">{}</font>'.format(pct(rate))    # 绿
    elif rate >= 0.6:
        return '<font color="comment">{}</font>'.format(pct(rate))  # 灰
    else:
        return '<font color="warning">{}</font>'.format(pct(rate))  # 橙红

def build(d):
    store = d.get("store", {})
    perf = store.get("performance", {})
    qcs = store.get("qcs", {})
    meta = d.get("meta", {})
    people = d.get("people", {})
    remain = meta.get("remainDays", 0)

    mli = perf.get("毛利", {})
    zz = qcs.get("增值", {})
    sj = perf.get("手机", {})
    hy = qcs.get("合约", {})
    zhb = perf.get("智慧办公", {})
    ypcd = perf.get("音频穿戴", {})

    rows = []
    for name, p in people.items():
        pp = p.get("performance", {})
        pq = p.get("qcs", {})
        m = pp.get("毛利", {})
        if (m.get("task", 0) or 0) == 0: continue
        rows.append({
            "name": name,
            "mli_done": m.get("done", 0) or 0, "mli_rate": m.get("rate") or 0,
            "sj_done": pp.get("手机", {}).get("done", 0) or 0,
            "zz_done": pq.get("增值", {}).get("done", 0) or 0,
        })
    rows.sort(key=lambda x: x["mli_done"], reverse=True)
    mvp = rows[0]

    L = []
    L.append("# 📊 门店达成进度")
    L.append("")
    L.append("距月底仅剩 **{}** 天".format(remain))
    L.append("")
    L.append("**毛利** {} / {} · {}".format(
        wan(mli.get("done", 0)), wan(mli.get("task", 0)), color_rate(mli.get("rate"))))
    L.append("")
    L.append("**增值** {} / {} · {}".format(
        wan(zz.get("done", 0)), wan(zz.get("task", 0)), color_rate(zz.get("rate"))))
    L.append("")
    L.append("**手机** {}台 / {}台 · {}".format(
        int(sj.get("done", 0)), int(sj.get("task", 0)), color_rate(sj.get("rate"))))
    L.append("")
    L.append("**合约** {}单 / {}单 · {}".format(
        int(hy.get("done", 0)), int(hy.get("task", 0)), color_rate(hy.get("rate"))))
    L.append("")
    L.append("**智慧办公** {}台 / {}台 · {}".format(
        int(zhb.get("done", 0)), int(zhb.get("task", 0)), color_rate(zhb.get("rate"))))
    L.append("")
    L.append("**音频穿戴** {}件 / {}件 · {}".format(
        int(ypcd.get("done", 0)), int(ypcd.get("task", 0)), color_rate(ypcd.get("rate"))))
    L.append("")
    L.append("---")
    L.append("")
    L.append("**🏆 MVP · {}**".format(mvp["name"]))
    L.append("> 毛利 {} · 手机 {}台 · 增值 {}".format(
        wan(mvp["mli_done"]), int(mvp["sj_done"]), wan(mvp["zz_done"])))
    L.append("")
    L.append("---")
    L.append("")

    medals = ["🥇", "🥈", "🥉", "4", "5"]
    for i, r in enumerate(rows):
        medal = medals[i] if i < len(medals) else str(i + 1)
        L.append("{} **{}** · 毛利 {} · {}".format(
            medal, r["name"], wan(r["mli_done"]), color_rate(r["mli_rate"])))

    L.append("")
    L.append("---")
    L.append("")
    L.append("[📊 查看实时看板]({})".format(BOARD_URL))

    return "\n".join(L)


def send_markdown(webhook, content):
    payload = json.dumps(
        {"msgtype": "markdown", "markdown": {"content": content}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    d = json.load(open(DATA, encoding="utf-8"))
    content = build(d)

    print(content)
    print("\n" + "=" * 60)

    if dry:
        print("（--dry 模式，未推送）")
        sys.exit(0)

    wh = load_webhook()
    if not wh:
        print("⚠️ 未配置 webhook，跳过推送")
        sys.exit(1)

    resp = send_markdown(wh, content)
    print("📤 推送结果:", resp)
