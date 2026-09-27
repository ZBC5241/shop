#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
push_daily_done.py —— 钉钉日报提交成功后，往企微看板群推送一条「今日日报已交」。
用法：python3 push_daily_done.py --date 2026-09-26
调用方：写日报.sh（dd_fill_daily 提交+终验通过后调用）
webhook 读 /Users/mac/WorkBuddy/Claw/.wecom_webhook（看板群 fe438f09），沿用去刷屏约定只发看板群。
"""
import sys, os, json, urllib.request, subprocess, datetime

WORKDIR = "/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/dingtalk_fill"
SHOP_DIR = "/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/shop"
CONF = "/Users/mac/WorkBuddy/Claw/.wecom_webhook"


def load_webhook():
    if os.path.exists(CONF):
        return open(CONF, encoding="utf-8").read().strip()
    return ""


def send_markdown(webhook, content):
    payload = json.dumps(
        {"msgtype": "markdown_v2", "markdown_v2": {"content": content}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(webhook, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")


def main():
    date_str = datetime.date.today().isoformat()
    args = sys.argv[1:]
    for i, a in enumerate(args):
        if a == "--date" and i + 1 < len(args):
            date_str = args[i + 1]
    # 从 outbox 反查确认当日已提交（终验一致性）
    DWS = "/Users/mac/.workbuddy/binaries/node/cli-connector-packages/bin/dws"
    try:
        r = subprocess.run(
            [DWS, "report", "outbox", "list",
             "--start", f"{date_str}T00:00:00+08:00",
             "--end", f"{date_str}T23:59:59+08:00", "-y"],
            capture_output=True, text=True, timeout=60)
        d = json.loads(r.stdout)
        n = len(d.get("_internalDetailCommands", []))
    except Exception as e:
        print(f"⚠️ outbox 反查失败（{e}），不推送"); return
    if n < 1:
        print(f"⚠️ 当日 outbox 无记录（{date_str} n={n}），可能未提交，不推送"); return

    wh = load_webhook()
    if not wh:
        print("❌ 未配置 webhook"); return
    now = datetime.datetime.now().strftime("%H:%M")
    content = f"✅ **今日日报已交**（{date_str} {now}）"
    try:
        resp = send_markdown(wh, content)
        print(f"📤 推送结果: {resp}")
    except Exception as e:
        print(f"❌ 推送失败: {e}")


if __name__ == "__main__":
    main()