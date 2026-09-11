#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_board.py — 李家村看板一键更新（SOP 脚本化）

完整流程（5步，对应 SKILL.md 标准流程）：
  1. fetch_yonyou_http.py        → 拉取毛利明细（report/exec，HTTP直连，500行截断版）
  2. fetch_sales_analysis_http.py → 拉取销售分析（report/list，HTTP直连，含去重+8月切片）
  3. 检查行数 → 500行截断时自动回退到浏览器提取版 yonyou_full_512.tsv
  4. calc_data.py                  → 复算 data.json（1:1复现Excel SUMIFS口径）
  5. merge_qudao.py                → 合并渠道挂账数据
  6. build.py                      → 打包 index.html（parts/* + data.json → 单文件）

用法：
  python3 update_board.py              # 全量更新（联网拉取最新数据）
  python3 update_board.py --use-cache  # 快速更新（仅用本地缓存，不联网）

前置条件：
  - 用友云登录态有效（~/.agent-browser/sessions/yonyou-default.json）
  - 桌面表格存在（/Users/mac/Desktop/李家村销售/李家村9月任务进度.xlsx）
  - 若登录态失效（HTTP 401），需先用 agent-browser 重新登录用友云

退出码：0 成功 / 1 失败
"""
import subprocess, sys, os, time

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# ---------- 配置 ----------
XLSX = "/Users/mac/Desktop/李家村销售/李家村9月任务进度.xlsx"
YONYOU_TSV = os.path.join(BASE, "yonyou_raw.tsv")           # HTTP截断版（500行）
FULL_TSV = os.path.join(BASE, "yonyou_full_512.tsv")         # 浏览器提取版（512行，完整）
SA_CACHE = os.path.join(BASE, "sa_aug_cache.json")           # 8月销售分析切片
INDEX_HTML = os.path.join(BASE, "index.html")
HTML_COPY = os.path.join(os.path.dirname(BASE), "华为门店业绩看板.html")


def run(cmd, label, timeout=120):
    """运行子进程，实时打印输出，返回退出码。"""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    t0 = time.time()
    r = subprocess.run(cmd, cwd=BASE, timeout=timeout,
                       capture_output=True, text=True)
    dt = time.time() - t0
    # 打印 stdout（正常输出）
    if r.stdout:
        print(r.stdout.rstrip())
    if r.stderr:
        print(r.stderr.rstrip())
    print(f"  [计时] {dt:.1f}s | 退出码 {r.returncode}")
    return r.returncode


def count_tsv_rows(path):
    """数 TSV 数据行数（不含表头）。"""
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8-sig") as f:
        return sum(1 for line in f if line.strip()) - 1


def max_tsv_date(path):
    """扫描日期列（第3列出库日期），返回最大日期 YYYY-MM-DD；无数据返回 None。"""
    if not os.path.exists(path):
        return None
    best = None
    with open(path, encoding="utf-8-sig") as f:
        for i, line in enumerate(f):
            if i == 0:
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            d = parts[2].strip()[:10]
            if len(d) == 10 and d[4] == "-" and d > (best or ""):
                best = d
    return best


def main():
    use_cache = "--use-cache" in sys.argv
    t_total = time.time()

    # ===== Step 1: 拉取毛利明细 =====
    if use_cache:
        print("\n[Step 1] --use-cache 模式，跳过联网拉取毛利明细")
    else:
        rc = run([PY, "fetch_yonyou_http.py"], "Step 1/5: 拉取毛利明细（report/exec）")
        if rc != 0:
            print("⚠️ 毛利明细拉取失败（可能登录态失效），尝试用已有数据继续")

    # ===== Step 2: 拉取销售分析 =====
    if use_cache:
        print("\n[Step 2] --use-cache 模式，跳过联网拉取销售分析")
    else:
        rc = run([PY, "fetch_sales_analysis_http.py"], "Step 2/5: 拉取销售分析（report/list）", timeout=180)
        if rc != 0:
            print("⚠️ 销售分析拉取失败，尝试用已有数据继续")

    # ===== Step 3: 选择数据源（按日期新鲜度，行数仅参考）=====
    # 2026-09-11 修复：旧逻辑按"行数多者胜"，导致8月遗留快照 yonyou_full_512.tsv(512行)
    # 覆盖 9 月实时数据(211行)。改为按数据最大日期选源：日期旧的一律淘汰。
    print(f"\n{'='*60}")
    print("  Step 3/5: 检查数据源（按日期新鲜度）")
    print(f"{'='*60}")
    http_rows = count_tsv_rows(YONYOU_TSV)
    full_rows = count_tsv_rows(FULL_TSV)
    http_date = max_tsv_date(YONYOU_TSV)
    full_date = max_tsv_date(FULL_TSV)
    print(f"  HTTP实时版 yonyou_raw.tsv: {http_rows} 行 | 最大日期 {http_date or '—'}")
    print(f"  浏览器快照 yonyou_full_512.tsv: {full_rows} 行 | 最大日期 {full_date or '—'}")

    def later(d1, d2):
        if not d1: return False
        if not d2: return True
        return d1 > d2

    if http_rows == 0 and full_rows == 0:
        print("❌ 没有可用的毛利明细数据")
        return 1
    # 快照不存在/无数据 → 直接用 HTTP
    if full_rows == 0 or not full_date:
        tsv_path = YONYOU_TSV
        print(f"  ✅ 使用HTTP实时版（快照不存在或过期）")
    elif later(full_date, http_date):
        tsv_path = FULL_TSV
        print(f"  ✅ 使用浏览器快照（{full_date} 晚于 HTTP {http_date}）")
    elif http_rows > 0:
        tsv_path = YONYOU_TSV
        print(f"  ✅ 使用HTTP实时版（{http_date} ≥ 快照 {full_date}，快照为旧月份遗留数据，淘汰）")
    else:
        tsv_path = FULL_TSV
        print(f"  ✅ HTTP版无数据，回退浏览器快照")

    # ===== Step 4: 复算 data.json =====
    rc = run([PY, "calc_data.py", tsv_path], "Step 4/5: 复算 data.json（SUMIFS 1:1复现）")
    if rc != 0:
        print("❌ calc_data.py 复算失败")
        return 1

    # ===== Step 5: 合并渠道挂账 =====
    rc = run([PY, "merge_qudao.py"], "Step 5/5: 合并渠道挂账（merge_qudao）")
    if rc != 0:
        print("⚠️ merge_qudao 失败（渠道数据可能缺失，看板仍可用）")

    # ===== Step 6: 打包 =====
    rc = run([PY, "build.py"], "Step 6/5: 打包 index.html")
    if rc != 0:
        print("❌ build.py 打包失败")
        return 1

    # ===== 复制到工作目录 =====
    if os.path.exists(INDEX_HTML):
        import shutil
        shutil.copy2(INDEX_HTML, HTML_COPY)
        print(f"\n✅ 已复制到工作目录: {HTML_COPY}")

    dt = time.time() - t_total
    print(f"\n{'='*60}")
    print(f"  看板更新完成！总耗时 {dt:.0f}s")
    print(f"  数据源: {tsv_path}")
    print(f"  看板文件: {INDEX_HTML}")
    print(f"  工作目录副本: {HTML_COPY}")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
