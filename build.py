#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
看板打包器：parts/*  +  data.json  ->  index.html（单文件，双击可开）

用法：
    python build.py                     # 用当前 data.json
    python build.py --xlsx <表格路径>    # 先重新抽取数据，再打包
"""
import os, sys, json, subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
PARTS = os.path.join(BASE, "parts")
ORDER = ["01_head.html", "02_body.html",
         "03_js_core.js", "04_js_views.js", "05_js_data.js", "06_js_ui.js"]
PY = sys.executable


def main():
    # V2.9 主页模式：主页固定为 AI洞察行动指南 V2.9（晨哥手搓，fetch data.json 驱动）。
    # 看板更新不再重建 index.html，避免覆盖 V2.9。存在 .homepage_v29 标记即跳过生成。
    if os.path.exists(os.path.join(BASE, ".homepage_v29")):
        print("⏭️ V2.9 主页模式：跳过 index.html 生成（主页固定为 V2.9，看板更新仅刷新 data.json）")
        return
    data_path = os.path.join(BASE, "data.json")

    if "--xlsx" in sys.argv:
        xlsx = sys.argv[sys.argv.index("--xlsx") + 1]
        print("→ 重新抽取数据…")
        r = subprocess.run([PY, os.path.join(BASE, "build_data.py"), xlsx, data_path])
        if r.returncode != 0:
            sys.exit(1)

    if not os.path.exists(data_path):
        print("❌ 找不到 data.json，请先运行 build_data.py")
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    chunks = []
    for name in ORDER:
        p = os.path.join(PARTS, name)
        if not os.path.exists(p):
            print(f"❌ 缺少组件 {name}")
            sys.exit(1)
        with open(p, encoding="utf-8") as f:
            chunks.append(f.read())

    html = "\n".join(chunks)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if "__DATA__" not in html:
        print("❌ 模板里找不到 __DATA__ 占位符")
        sys.exit(1)
    html = html.replace("__DATA__", payload)

    out = os.path.join(BASE, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 已生成 {out}  ({len(html)/1024:.0f} KB)")
    print(f"   数据日期 {data['meta'].get('date','?')} · 时间进度 "
          f"{(data['meta'].get('timeProgress') or 0):.1%}")


if __name__ == "__main__":
    main()
