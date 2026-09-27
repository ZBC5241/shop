#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_daily_done.py —— 钉钉日报提交成功后，往企微看板群推送「今日日报已交」卡片。
卡片样式沿用「日清日结」卡片（2026-09-16 晨哥定稿样式）：
  **📊 标题 · MM-DD**
  > 数据行：<font color="info/warning">**数值**</font> 单位
  > <font color="comment">灰色落款</font>
数据源：gen_fields.py --json（收入/毛利/手机/增值/合约）+ outbox 反查确认已交。
用法：python3 push_daily_done.py --date 2026-09-26
webhook 读 /Users/mac/WorkBuddy/Claw/.wecom_webhook（看板群 fe438f09），只发看板群。
"""
import sys, os, json, urllib.request, subprocess, datetime

WORKDIR = "/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/dingtalk_fill"
GEN_FIELDS = "/Users/mac/.workbuddy/skills/dingtalk-daily-report/scripts/gen_fields.py"
CONF = "/Users/mac/WorkBuddy/Claw/.wecom_webhook"
DWS = "/Users/mac/.workbuddy/binaries/node/cli-connector-packages/bin/dws"


def load_webhook():
    return open(CONF, encoding="utf-8").read().strip() if os.path.exists(CONF) else ""


def gen_values(date_str):
    """调用 gen_fields.py --json 取日报核心数据。"""
    r = subprocess.run(
        ["/Users/mac/.workbuddy/binaries/python/envs/default/bin/python3",
         GEN_FIELDS, "--date", date_str, "--json"],
        capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError("gen_fields 失败: " + (r.stderr or r.stdout or "")[-200:])
    return json.loads(r.stdout)


def confirmed_submitted(date_str):
    """outbox 反查确认当日已提交（≥1 条才推）。"""
    try:
        r = subprocess.run(
            [DWS, "report", "outbox", "list",
             "--start", f"{date_str}T00:00:00+08:00",
             "--end", f"{date_str}T23:59:59+08:00", "-y"],
            capture_output=True, text=True, timeout=60)
        return len(json.loads(r.stdout).get("_internalDetailCommands", [])) >= 1
    except Exception:
        return False


def fmt(n, dec=2):
    """金额去¥去逗号（与日清日结一致）。"""
    return ("%.*f" % (dec, float(n))).replace(",", "")


def build_card(d):
    """日清日结卡片样式：标题Emoji + 引用行 + 单色 + 灰色落款。"""
    md = d["date"][5:7] + "-" + d["date"][8:10]
    L = []
    L.append(f"**✅ 今日日报已交 · {md}**")
    L.append("> 收入：<font color=\"info\">**{}**</font> 元".format(fmt(d["收入"])))
    L.append("> 毛利：<font color=\"warning\">**{}**</font> 元".format(fmt(d["毛利"])))
    L.append("> 手机达成：<font color=\"info\">**{}**</font> 台".format(int(d["手机达成"])))
    L.append("> 增值：<font color=\"info\">**{}**</font> 元".format(fmt(d["增值"])))
    L.append("> 合约月累计：<font color=\"info\">**{}**</font> 单".format(int(d["合约累计"])))
    L.append("> <font color=\"comment\">李家村·华为</font>")
    return "\n".join(L)


def send_markdown(wh, content):
    payload = json.dumps(
        {"msgtype": "markdown", "markdown": {"content": content}},
        ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(wh, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def main():
    date_str = datetime.date.today().isoformat()
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--date" and i + 1 < len(args):
            date_str = args[i + 1]
    if not confirmed_submitted(date_str):
        print(f"⚠️ 当日 outbox 无记录（{date_str}），可能未提交，不推送")
        return
    try:
        d = gen_values(date_str)
    except Exception as e:
        print(f"⚠️ 出数失败（{e}），退化为纯文本提示")
        wh = load_webhook()
        if wh:
            send_markdown(wh, f"✅ **今日日报已交**（{date_str}）")
        return
    wh = load_webhook()
    if not wh:
        print("❌ 未配置 webhook")
        return
    card = build_card(d)
    print(card)
    try:
        resp = send_markdown(wh, card)
        print("📤 推送结果:", resp)
    except Exception as e:
        print("❌ 推送失败:", e)


if __name__ == "__main__":
    main()