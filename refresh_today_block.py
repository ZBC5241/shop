#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_today_block.py —— 刷新《李家村销售》表「今日达成」区块并取值注入 data.json

流程：
  1. 从用友毛利明细 TSV 取“最新出库日期”的当日行
  2. 写入桌面包 RXS 明细表（公式数据源），数值列去千分位逗号并转 float
  3. 用真实表格引擎（LibreOffice/soffice 优先，否则 Microsoft Excel via AppleScript）重算整本
  4. 读「今日达成」区块（李家村销售!B28:N33）刷新出来的缓存值
  5. 注入 data.json：store.dailyDone + 各营业员 dailyDone，并把 meta.date 对齐真实数据日

这样日报“当日达成”严格等于表格公式重算后的结果，不再由 Python 近似复算。

用法：
  python3 refresh_today_block.py --tsv yonyou_raw.tsv \
      --xlsx "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx" \
      --data data.json
"""
import argparse, csv, json, os, shutil, subprocess, sys, datetime, time

# RXS 表头顺序（列 A~S）：出库单号/单据类型/出库日期/商品分类/商品sku分类/商品SKU编码/
#   商品名称/入库属性/数量/单价/原价/折扣价/金额/毛利/SO激励/业务员/库区/销售出库单门店/销售成本
NUM_COLS_1B = {9, 10, 11, 12, 13, 14, 15, 19}   # 数值列(1-based)：数量/单价/原价/折扣价/金额/毛利/SO激励/销售成本

# 「今日达成」区块位置（李家村销售 sheet）
BLOCK_SHEET = "李家村销售"
LABEL_ROW = 26          # B26:N26 品类标签
FIRST_DATA_ROW = 28     # B28 起 5 位营业员
N_PEOPLE = 5
TOTAL_ROW = 33          # B33 合计
BLOCK_COLS = range(2, 15)   # B~N
PEOPLE = ["邵乐乐", "杨丽华", "李泽", "陈超磊", "张博晨"]


def num(v):
    if v is None:
        return None
    s = str(v).replace(",", "").replace("，", "").strip()
    if s == "":
        return None
    try:
        return float(s)
    except Exception:
        return s


def data_day_of(tsv):
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    dates = [r[2][:10] for r in rows[1:] if len(r) > 2 and r[2]]
    return max(dates) if dates else None


def write_rxs(xlsx, tsv, day):
    """把 day 当日明细写入 RXS（清空旧数据行），返回写入行数。"""
    rows = list(csv.reader(open(tsv, encoding="utf-8"), delimiter="\t"))
    today = [r for r in rows[1:] if len(r) > 2 and r[2][:10] == day]
    import openpyxl
    wb = openpyxl.load_workbook(xlsx)
    rx = wb["RXS"]
    for r in range(2, rx.max_row + 1):
        for c in range(1, 20):
            rx.cell(r, c).value = None
    for i, tr in enumerate(today):
        r = 2 + i
        for c in range(1, 20):
            raw = tr[c - 1] if c - 1 < len(tr) else None
            rx.cell(r, c).value = num(raw) if c in NUM_COLS_1B else raw
    try:
        wb.calculation.fullCalcOnLoad = True
    except Exception:
        pass
    wb.save(xlsx)
    return len(today)


def recalc_xlsx(xlsx):
    """用真实引擎重算整本。优先 soffice，否则 Excel。返回 True/False。"""
    # 1) LibreOffice headless（若有）
    for bin_ in ("soffice", "libreoffice"):
        p = shutil.which(bin_)
        if p:
            try:
                subprocess.run([p, "--headless", "--calc", "--convert-to", "xlsx",
                                "--outdir", os.path.dirname(xlsx), xlsx],
                               check=True, timeout=120,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except Exception:
                pass
    # 2) Microsoft Excel via AppleScript（macOS）
    scpt = '''
    set f to POSIX file "%s"
    tell application "Microsoft Excel"
        launch
        open f
        delay 5
        save active workbook
        close active workbook
    end tell
    ''' % xlsx
    try:
        subprocess.run(["osascript", "-e", scpt], check=True, timeout=120,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception as e:
        sys.stderr.write("  [警告] Excel 重算失败: %s\n" % e)
        return False


def read_block(xlsx):
    """读「今日达成」区块刷新值（data_only）。返回 (labels, per_person, total, sales_by, sales_total)。"""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    ws = wb[BLOCK_SHEET]
    labels = [ws.cell(LABEL_ROW, c).value for c in BLOCK_COLS]
    per_person = {}
    for i, p in enumerate(PEOPLE):
        rr = FIRST_DATA_ROW + i
        vals = {}
        for c in BLOCK_COLS:
            v = ws.cell(rr, c).value
            vals[labels[c - 2]] = 0.0 if v is None else float(v)
        per_person[p] = vals
    total = {}
    for c in BLOCK_COLS:
        v = ws.cell(TOTAL_ROW, c).value
        total[labels[c - 2]] = 0.0 if v is None else float(v)
    # 销额（区块无此行）：RXS 金额列(M,13) 按业务员合计
    rx = wb["RXS"]
    sales_total = 0.0
    sales_by = {}
    for r in range(2, rx.max_row + 1):
        p = rx.cell(r, 16).value
        m = rx.cell(r, 13).value
        if isinstance(m, (int, float)):
            sales_total += m
            sales_by[p] = sales_by.get(p, 0.0) + m
    return labels, per_person, total, sales_by, sales_total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tsv", required=True)
    ap.add_argument("--xlsx", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--no-excel", action="store_true", help="跳过真实引擎重算（仅开放pycel兜底时才有意义）")
    a = ap.parse_args()

    day = data_day_of(a.tsv)
    if not day:
        sys.stderr.write("✗ TSV 无有效日期，跳过今日达成刷新\n")
        return 1
    print("  数据日(最新出库日期): %s" % day)

    # 备份 RXS（仅保留一份轮换备份）
    bak = a.xlsx + ".bak_rxs"
    shutil.copy(a.xlsx, bak)

    n = write_rxs(a.xlsx, a.tsv, day)
    print("  ✓ 已写 RXS 当日明细 %d 行（备份 %s）" % (n, os.path.basename(bak)))

    ok = True
    if not a.no_excel:
        ok = recalc_xlsx(a.xlsx)
        if ok:
            print("  ✓ Excel/soffice 已重算整本")
        else:
            print("  [警告] 真实引擎重算不可用，区块值可能非最新")

    labels, per_person, total, sales_by, sales_total = read_block(a.xlsx)
    store_daily = dict(total)
    store_daily["销额"] = sales_total

    d = json.load(open(a.data, encoding="utf-8"))
    d["store"]["dailyDone"] = store_daily
    for p in PEOPLE:
        pd = dict(per_person[p])
        pd["销额"] = sales_by.get(p, 0.0)
        d["people"][p]["dailyDone"] = pd
    # 对齐真实数据日
    d["meta"]["date"] = day
    d["meta"]["dayTitle"] = day
    d["meta"]["refDate"] = day
    json.dump(d, open(a.data, "w", encoding="utf-8"), ensure_ascii=False)

    print("  ✓ 已注入 data.json：当日达成 = 销额 %d / 毛利 %d / 手机 %d"
          % (round(sales_total), round(store_daily["毛利"]), round(store_daily["手机"])))
    print("    逐人毛利: " + "  ".join("%s %d" % (p, round(per_person[p]["毛利"]))
                                        for p in PEOPLE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
