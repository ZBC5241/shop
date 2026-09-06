#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_v29.py — V2.9 主页数据注入器（芯不动、只换壳）

每次数据管线跑完，把最新 data.json 注入 v29_template.html 的
__V29DATA__ 占位符，生成 index.html 作为主页。

设计要点：
- 数据为启动首屏内嵌（无跳变），loadRemote() 静默兜底再确认一次
- 模板占位符单一、整行替换，校验：无残留占位符 + 内嵌数据日期/行数与 data.json 一致
- 注入的 JSON 用 ensure_ascii=False + 紧凑分隔符，保持与原 build 流程一致
"""
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(BASE, "v29_template.html")
OUT = os.path.join(BASE, "index.html")
DATA = os.path.join(BASE, "data.json")

PLACEHOLDER_LINE_RE = re.compile(r"^const EMBEDDED_DATA = __V29DATA__;$")


def main():
    with open(DATA, encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    date = str(meta.get("date") or "")
    rows = meta.get("sourceRows")
    fetch_time = str(meta.get("fetchTime") or "")

    with open(TEMPLATE, encoding="utf-8") as f:
        tpl = f.read()

    lines = tpl.split("\n")
    hits = [i for i, l in enumerate(lines) if PLACEHOLDER_LINE_RE.match(l)]
    if len(hits) != 1:
        sys.exit(f"❌ v29_template.html 占位符异常：命中 {len(hits)} 行（应为 1）")

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    lines[hits[0]] = "const EMBEDDED_DATA = " + payload + ";"

    out = "\n".join(lines)

    # 校验1：输出无残留占位符
    if "__V29DATA__" in out:
        sys.exit("❌ 构建失败：输出中残留 __V29DATA__ 占位符")

    # 校验2：内嵌数据的日期/行数与 data.json 一致（防旧快照回流）
    if f'"date":"{date}"' not in payload:
        sys.exit("❌ 构建失败：内嵌数据日期与 data.json 不一致")
    if rows is not None and f'"sourceRows":{rows}' not in payload:
        sys.exit("❌ 构建失败：内嵌数据 sourceRows 与 data.json 不一致")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)

    size_mb = os.path.getsize(OUT) / 1024 / 1024
    print(f"✅ build_v29: index.html 已生成（数据 {date} {fetch_time} | {rows} 行 | {size_mb:.2f} MB）")


if __name__ == "__main__":
    main()
