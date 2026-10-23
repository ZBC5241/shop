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


def _local_notify(stage, code):
    """本机 macOS 通知兜底（不依赖企微群，2026-10-23 加）"""
    try:
        import subprocess
        subprocess.run(
            ["osascript", "-e",
             'display notification "{} 失败(rc={})，请查日志" with title "看板定时任务告警"'.format(stage, code)],
            timeout=5, capture_output=True)
    except Exception:
        pass


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
        print("⚠️ 告警留痕：企微 webhook 配置缺失/不可读（{}），转本机通知".format(CONF))
        _local_notify(a.stage, a.exit_code)
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
        print("✅ 告警已发企微群（stage={} rc={}）".format(a.stage, a.exit_code))
    except Exception as e:
        print("⚠️ 企微告警发送失败：{}，转本机通知".format(e))
        _local_notify(a.stage, a.exit_code)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
