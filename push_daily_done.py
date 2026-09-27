#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_daily_done.py —— 钉钉日报提交成功后，往企微看板群推送「今日日报已交」一句话卡片。
样式沿用「日清日结」卡片（标题 Emoji + 灰色落款），正文仅一句话，不带任何数据。
用法：python3 push_daily_done.py --date 2026-09-26
webhook 读 /Users/mac/WorkBuddy/Claw/.wecom_webhook（看板群 fe438f09），只发看板群。
"""
import sys, os, json, urllib.request, subprocess, datetime

CONF = "/Users/mac/WorkBuddy/Claw/.wecom_webhook"
DWS = "/Users/mac/.workbuddy/binaries/node/cli-connector-packages/bin/dws"


def load_webhook():
    return open(CONF, encoding="utf-8").read().strip() if os.path.exists(CONF) else ""


def confirmed_submitted(date_str):
    """outbox 反查确认当日已提交（≥1 条），返回提交时间 HH:MM（取最新一条）。"""
    try:
        r = subprocess.run(
            [DWS, "report", "outbox", "list",
             "--start", f"{date_str}T00:00:00+08:00",
             "--end", f"{date_str}T23:59:59+08:00", "-y"],
            capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout)
        cmds = d.get("_internalDetailCommands", [])
        if not cmds:
            return False, None
        # 从 markdown 表格首行取「日期」列（形如 2026-09-26 23:16）
        md = d.get("agentDisplay", {}).get("markdown", "")
        import re
        m = re.search(r"\| (\d{4}-\d{2}-\d{2} \d{2}:\d{2}) \|", md)
        return True, (m.group(1)[-5:] if m else None)
    except Exception:
        return False, None


def build_card(date_str, submit_time=None):
    """日清日结样式：一句话「今日日报已交」+ 提交成功时间。"""
    md = date_str[5:7] + "-" + date_str[8:10]
    L = [f"**✅ 今日日报已交 · {md}**"]
    if submit_time:
        L.append(f"> <font color=\"comment\">提交成功时间：{submit_time}</font>")
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
    ok, submit_time = confirmed_submitted(date_str)
    if not ok:
        print(f"⚠️ 当日 outbox 无记录（{date_str}），可能未提交，不推送")
        return
    wh = load_webhook()
    if not wh:
        print("❌ 未配置 webhook")
        return
    card = build_card(date_str, submit_time)
    print(card)
    try:
        resp = send_markdown(wh, card)
        print("📤 推送结果:", resp)
    except Exception as e:
        print("❌ 推送失败:", e)


if __name__ == "__main__":
    main()