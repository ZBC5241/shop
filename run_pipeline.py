#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_pipeline.py — 看板全流程一键串联（方案A+B优化）

替代手动分步操作，消除全部间隙：
  calc_data.py (直读xlsx) → merge_qudao.py → build.py → push_board.sh

用法：
    python run_pipeline.py <毛利明细.xlsx> <销售分析.xlsx> [--task-xlsx 路径]

示例：
    python run_pipeline.py \
        ~/Downloads/门店毛利明细表-华为终端.xlsx \
        ~/Downloads/销售分析-0829.xlsx
"""
import sys, os, subprocess, time, argparse, json

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(cmd, label):
    """执行命令并计时。"""
    print(f"\n{'='*60}")
    print(f"▶ {label}")
    print(f"  {' '.join(cmd)}")
    print(f"{'='*60}")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=BASE)
    dt = time.time() - t0
    status = "✅" if r.returncode == 0 else "❌"
    print(f"{status} {label} ({dt:.1f}s)")
    if r.returncode != 0:
        sys.exit(f"❌ {label} 失败，终止流水线")
    return dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("maoli_xlsx", help="毛利明细表xlsx路径")
    ap.add_argument("sa_xlsx", help="销售分析xlsx路径")
    ap.add_argument("--task-xlsx", default="/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx",
                    help="任务进度xlsx（手工项来源）")
    ap.add_argument("--no-push", action="store_true", help="不推送GitHub")
    ap.add_argument("--no-sa", action="store_true", help="跳过销售分析更新")
    args = ap.parse_args()

    total_start = time.time()
    timings = {}

    # Step 1: 更新sa_cache（从销售分析xlsx提取渠道数据）
    if not args.no_sa:
        timings["sa_cache"] = run(
            [PY, os.path.join(BASE, "update_sa_cache.py"), args.sa_xlsx],
            "更新销售分析缓存"
        )

    # Step 2: calc_data（直读毛利xlsx，跳过TSV中转）
    data_json = os.path.join(BASE, "data.json")
    timings["calc"] = run(
        [PY, os.path.join(BASE, "calc_data.py"), args.maoli_xlsx,
         "--xlsx", args.task_xlsx, "-o", data_json],
        "复算明细(直读xlsx)"
    )

    # Step 3: merge_qudao（渠道挂账合并）
    timings["merge"] = run(
        [PY, os.path.join(BASE, "merge_qudao.py"), data_json, args.task_xlsx],
        "渠道挂账合并"
    )

    # Step 4: build（打包index.html）
    timings["build"] = run(
        [PY, os.path.join(BASE, "build.py")],
        "打包看板"
    )

    # Step 5: push（推送GitHub上线）
    if not args.no_push:
        push_script = os.path.join(BASE, "push_board.sh")
        push_msg = f"看板更新 {time.strftime('%Y-%m-%d_%H:%M')}"
        timings["push"] = run(
            ["bash", push_script, push_msg],
            "推送GitHub上线"
        )

    total = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"🏁 全流程完成！总耗时 {total:.1f}s ({total/60:.1f}min)")
    print(f"{'='*60}")
    for step, dt in timings.items():
        print(f"  {step}: {dt:.1f}s")
    print(f"  总计: {total:.1f}s ({total/60:.1f}min)")

    # 读data.json展示关键数据
    try:
        with open(data_json, encoding="utf-8") as f:
            data = json.load(f)
        meta = data.get("meta", {})
        store = data.get("store", {})
        g = store.get("performance", {}).get("毛利", {})
        sales = store.get("performance", {}).get("销额", {})
        phone = store.get("performance", {}).get("手机", {})
        print(f"\n📊 数据概览:")
        print(f"  日期: {meta.get('date')} | 明细 {meta.get('sourceRows')} 行")
        print(f"  毛利: ¥{g.get('done',0):,.0f} / ¥{g.get('task',0):,.0f} ({(g.get('rate') or 0):.1%})")
        print(f"  销额: ¥{sales.get('done',0):,.0f} | 手机: {phone.get('done',0):.0f}台")
        print(f"  线上: https://zbc5241.github.io/shop/")
    except Exception:
        pass


if __name__ == "__main__":
    main()
