#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notify_fail.py — launchd 定时任务通用失败告警（企微群机器人 webhook）

用法：
    python3 notify_fail.py --stage "日清日结(22:43)" --exit-code 1 --log /path/to/log --tail 12
"""
import argparse
import datetime
import json
import os
import sys
import urllib.request

CONF = "/Users/mac/WorkBuddy/Claw/.wecom_webhook"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--exit-code", type=int, default=1)
    ap.add_argument("--log", default="")
    ap.add_argument("--tail", type=int, default=12)
    a = ap.parse_args()

    try:
        key = open(CONF, encoding="utf-8").read().strip()
    except Exception:
        return 2

    tail = ""
    if a.log and os.path.exists(a.log):
        lines = open(a.log, encoding="utf-8", errors="ignore").read().splitlines()
        tail = "\n".join("· " + l[:80] for l in lines[-a.tail:])

    now = datetime.datetime.now().strftime("%m-%d %H:%M")
    L = []
    L.append("⚠️ **定时任务失败告警**")
    L.append("")
    L.append("> 任务：**{}**".format(a.stage))
    L.append("> 时间：{} · 退出码：{}".format(now, a.exit_code))
    if tail:
        L.append("")
        L.append("日志尾部：")
        L.append(tail)
    L.append("")
    L.append("请让 17号 排查补跑")
    msg = "\n".join(L)
    data = json.dumps({"msgtype": "markdown", "markdown": {"content": msg}}).encode("utf-8")
    req = urllib.request.Request(
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=" + key,
        data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
