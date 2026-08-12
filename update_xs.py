#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把用友云抓取的明细写回《李家村X月任务进度.xlsx》的 XS 工作表。

关键设计：
  不用 openpyxl 写入（会破坏图表/透视表/条件格式），
  而是驱动本机 Microsoft Excel 完成写入 —— 公式、格式、图表全部原样保留，
  写入后 Excel 自动重算所有 SUMIFS，整本表的数据跟着变。

用法：
  python update_xs.py <明细.tsv> [目标.xlsx]
"""
import csv
import os
import re
import subprocess
import sys
import shutil
import datetime

DEFAULT_XLSX = "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
SHEET = "XS"
TMP_CSV = "/tmp/_xs_import.csv"

# 需要转成纯数字的列（0-based）
NUM_COLS = {8, 9, 10, 11, 12, 13, 14, 18}
# 日期列
DATE_COLS = {2}

EXPECT_HEADER = [
    "出库单号", "单据类型", "出库日期", "商品分类", "商品sku分类",
    "商品SKU编码", "商品名称", "入库属性", "数量", "单价", "原价",
    "折扣价", "金额", "毛利", "SO激励", "业务员", "库区",
    "销售出库单门店", "销售成本",
]


def clean_num(s):
    s = str(s or "").replace(",", "").strip()
    if s in ("", "-", "—"):
        return ""
    try:
        f = float(s)
        return str(int(f)) if f == int(f) else str(f)
    except ValueError:
        return s


def load_tsv(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().rstrip("\n").split("\n")
    rows = [ln.split("\t") for ln in lines]
    hdr, data = rows[0], rows[1:]

    if hdr != EXPECT_HEADER:
        print("!! 表头与 XS 不一致，已中止（用友云报表字段可能改了）")
        print("   期望:", EXPECT_HEADER)
        print("   实际:", hdr)
        sys.exit(1)

    out = []
    for r in data:
        r = (r + [""] * len(hdr))[: len(hdr)]
        for i in range(len(r)):
            if i in NUM_COLS:
                r[i] = clean_num(r[i])
            elif i in DATE_COLS:
                r[i] = re.sub(r"\s.*$", "", str(r[i]).strip())  # 去掉时间部分
        out.append(r)
    return hdr, out


APPLESCRIPT = r'''
on run argv
    set targetPath to item 1 of argv
    set csvPath to item 2 of argv
    set sheetName to item 3 of argv
    set lastRow to (item 4 of argv) as integer

    tell application "Microsoft Excel"
        set displayAlerts to false
        set screen updating to false

        set tgt to open workbook workbook file name targetPath
        set src to open workbook workbook file name csvPath

        -- 从 CSV 复制整块数据
        tell src
            set srcSheet to worksheet 1
            set srcRange to used range of srcSheet
            copy range srcRange
        end tell

        -- 清空 XS 旧数据（保留表头第 1 行）
        tell tgt
            set xs to worksheet sheetName
            activate object xs
            clear contents range ("A2:AW5000") of xs
            select range "A2" of xs
            paste worksheet xs
        end tell

        close src saving no

        -- 强制全量重算
        calculate
        delay 1
        save tgt
        set n to (count of rows of used range of (worksheet sheetName of tgt))

        set screen updating to true
        set displayAlerts to true
        close tgt saving no
        return n
    end tell
end run
'''


def main():
    if len(sys.argv) < 2:
        print("用法: python update_xs.py <明细.tsv> [目标.xlsx]")
        sys.exit(1)

    tsv = sys.argv[1]
    xlsx = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_XLSX

    if not os.path.exists(tsv):
        print("!! 找不到明细文件:", tsv)
        sys.exit(1)
    if not os.path.exists(xlsx):
        print("!! 找不到目标表格:", xlsx)
        sys.exit(1)

    hdr, rows = load_tsv(tsv)
    print("→ 读取明细 %d 行" % len(rows))

    # 备份（只备份真实目标，测试副本跳过）
    if xlsx == DEFAULT_XLSX:
        bak_dir = os.path.join(os.path.dirname(xlsx), "_备份")
        os.makedirs(bak_dir, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.splitext(os.path.basename(xlsx))[0]
        bak = os.path.join(bak_dir, "%s_备份%s.xlsx" % (base, stamp))
        shutil.copy2(xlsx, bak)
        print("→ 已备份:", bak)
        # 只保留最近 10 份备份
        baks = sorted(
            [f for f in os.listdir(bak_dir) if f.startswith(base + "_备份")]
        )
        for old in baks[:-10]:
            os.remove(os.path.join(bak_dir, old))

    # 写中间 CSV（不含表头，从 A2 开始贴）
    with open(TMP_CSV, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f).writerows(rows)
    print("→ 中转 CSV 就绪")

    scpt = "/tmp/_xs_update.applescript"
    with open(scpt, "w", encoding="utf-8") as f:
        f.write(APPLESCRIPT)

    print("→ 驱动 Excel 写入 XS 并重算…")
    res = subprocess.run(
        ["osascript", scpt, xlsx, TMP_CSV, SHEET, str(len(rows) + 1)],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        print("!! Excel 写入失败:")
        print(res.stderr.strip()[:600])
        sys.exit(1)

    print("✓ 写入完成，XS 现有 %s 行（含表头）" % res.stdout.strip())
    print("  目标文件:", xlsx)


if __name__ == "__main__":
    main()
