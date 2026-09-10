#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
alert_failure.py — 门店战报推送失败企微告警

daily_push.sh 异常退出时，自动向企微群推送失败告警卡片：
  · 失败时间、失败环节、退出码
  · 日志尾部摘录（脱敏后）
  · 常见原因提示

用法：
    python alert_failure.py --stage "渠道挂账合并" --exit-code 1
    python alert_failure.py --stage "拉取用友云数据" --exit-code 1 --log-tail 30
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_OUT = os.path.join(BASE, "logs", "dailypush.out")
LOG_ERR = os.path.join(BASE, "logs", "dailypush.err")
CONF = "/Users/mac/WorkBuddy/Claw/.wecom_webhook"
BOARD_URL = "https://zbc5241.github.io/shop/"

MAX_LINES = 20          # 日志尾部最多摘录行数
MAX_LINE_LEN = 80       # 单行最长截断
TAIL_CHARS = 1800       # 摘录总字符上限（企微 markdown 限 4096 字节，留余量给正文）
SENSITIVE = re.compile(
    r"(password|passwd|pwd|token|secret|key|Authorization|cookie|session)"
    r"\s*[=:：]\s*\S+",
    re.I,
)


def load_webhook():
    v = os.environ.get("WECOM_WEBHOOK")
    if v:
        return v.strip()
    if os.path.exists(CONF):
        return open(CONF, encoding="utf-8").read().strip()
    return None


def desensitize(text):
    """脱敏：密码/token/secret/key 等敏感赋值。"""
    return "\n".join(SENSITIVE.sub(r"\1=***", ln) for ln in text.splitlines())


def tail_log(lines=MAX_LINES):
    """取两个日志文件的尾部，脱敏、截断。"""
    chunks = []
    for path in (LOG_OUT, LOG_ERR):
        if os.path.exists(path):
            try:
                txt = subprocess.run(
                    ["tail", "-n", str(lines), path],
                    capture_output=True, text=True, timeout=5,
                ).stdout
                if txt.strip():
                    chunks.append(txt.strip())
            except Exception:
                pass
    txt = "\n".join(chunks).strip()
    if not txt:
        return "(日志为空或不可读)"
    txt = desensitize(txt)
    fixed = []
    for line in txt.splitlines():
        line = line.rstrip()
        if len(line) > MAX_LINE_LEN:
            line = line[:MAX_LINE_LEN] + "…"
        fixed.append(line)
    txt = "\n".join(fixed)
    if len(txt) > TAIL_CHARS:
        txt = "…(前面已截断)\n" + txt[-TAIL_CHARS:]
    return txt


def build_content(stage, exit_code):
    now = datetime.now().strftime("%m-%d %H:%M:%S")
    tail = tail_log()
    lines = []
    lines.append("# 🚨 战报推送失败告警")
    lines.append("")
    lines.append(f"> **时间**: {now}")
    lines.append(f"> **环节**: {stage}")
    lines.append(f"> **退出码**: {exit_code}")
    lines.append("")
    lines.append("**日志尾部**:")
    lines.append(f"> {tail}")
    lines.append("")
    lines.append("---")
    lines.append("**常见原因**: 数据拉取超时/页面结构变化/网络波动，可手动重试：")
    lines.append(f"`{os.path.join(BASE, 'daily_push.sh')} push`")
    lines.append("")
    lines.append(f"> 线上看板仍是上一时点数据，恢复后自动回补: [线上看板]({BOARD_URL})")
    lines.append("")
    return "\n".join(lines)


def send(content, dry=False):
    if dry:
        print("[dry 模式] 不实际发送，内容预览:")
        print("-" * 50)
        print(content)
        print("-" * 50)
        return True
    wh = load_webhook()
    if not wh:
        print("❌ 未找到企微 webhook 配置: %s" % CONF)
        return False
    payload = json.dumps(
        {"msgtype": "markdown_v2", "markdown_v2": {"content": content}},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        wh, data=payload, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = resp.read().decode("utf-8")
    print("📤 告警推送结果:", result)
    return '"errcode":0' in result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, help="失败环节名称")
    ap.add_argument("--exit-code", type=int, default=1, help="退出码")
    ap.add_argument("--log-tail", type=int, default=MAX_LINES, help="日志尾部行数")
    ap.add_argument("--dry", action="store_true", help="仅预览内容，不实际发送")
    args = ap.parse_args()
    content = build_content(args.stage, args.exit_code)
    ok = send(content, dry=args.dry)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
