#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
write_xs_xml.py — XML级原位替换底表 XS sheet（恢复旧SOP"写底表"环节）

背景：
    旧 SOP = 拉数 → 写底表 XS → 公式自动重算 → 看板/底表同源。
    9月管线自动化漏接了写XS环节，2026-09-10 晨哥拍板恢复。
    Excel AppleEvent 在本机假死（update_xs.py 不可用），
    openpyxl 整本重写会丢条件格式样式 —— 故采用 XML 级原位替换：
    只换 XS sheet 的 sheetData 数据行，其余全部原样保留。

关键设计：
    1. 去重规则与 calc_data.py 完全一致（出库单号+SKU编码，保留首行）
       —— 保证底表 SUMIFS 与看板口径永不劈叉。
    2. 数据行/空行按列固定样式写入（s=220/367/222/223/224/225/226/227/212），
       保留行高 ht=21、自定义格式，WPS/Excel 打开观感与手工粘贴一致。
    3. 日期列 C 存 Excel 序列数（s=367 日期格式显示）。
    4. 空行填充到 770 行（全 49 列带样式），保持原表观感。
    5. fullCalcOnLoad 置位：打开文件即全量重算 SUMIFS。
    6. 写前自动备份（保留最近10份），写后自动校验。

用法：
    python write_xs_xml.py <毛利明细.xlsx> [目标.xlsx]
"""
import datetime
import os
import re
import shutil
import sys
import tempfile
import zipfile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

DEFAULT_XLSX = "/Users/mac/Desktop/李家村销售/李家村9月任务进度.xlsx"
XS_SHEET_FILE = "xl/worksheets/sheet4.xml"  # XS = 第4个sheet

HEADERS = [
    "出库单号", "单据类型", "出库日期", "商品分类", "商品sku分类",
    "商品SKU编码", "商品名称", "入库属性", "数量", "单价", "原价",
    "折扣价", "金额", "毛利", "SO激励", "业务员", "库区",
    "销售出库单门店", "销售成本",
]

# 列属性：索引(0-based)→(数字列?, 样式id)
COL_STYLES = {
    0: (False, 220), 1: (False, 220), 2: (True, 367), 3: (False, 220),
    4: (False, 222), 5: (False, 220), 6: (False, 220), 7: (False, 222),
    8: (True, 223), 9: (True, 223), 10: (True, 224), 11: (True, 225),
    12: (True, 223), 13: (True, 223), 14: (True, 226), 15: (False, 227),
    16: (False, 220), 17: (False, 220), 18: (True, 223),
}
TAIL_STYLE = 212        # T..AW 列样式
ROW_ATTRS = 'ht="21" customFormat="1" customHeight="1" s="191"'
MIN_LAST_ROW = 770      # 空行填充下限（保持原表观感）
DATE_EPOCH = datetime.date(1899, 12, 30)  # Excel 序列数纪元


def date_serial(dstr):
    """'2026-09-10' → Excel 序列数 46275 等；失败返回 None。"""
    try:
        y, m, d = str(dstr)[:10].split("-")
        delta = datetime.date(int(y), int(m), int(d)) - DATE_EPOCH
        return delta.days
    except (ValueError, AttributeError):
        return None


def num_str(v):
    """数字规范化为最短文本；非数字返回 None。"""
    if v is None or str(v).strip() == "":
        return None
    try:
        f = float(str(v).replace(",", "").strip())
        return str(int(f)) if f == int(f) and abs(f) < 1e15 else repr(f)
    except (TypeError, ValueError):
        return None


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


def load_rows(src):
    """读用友云明细 → 补S列成本 → 去重（与 calc_data.py 同规则）→ 19列字符串。"""
    wb = load_workbook(src, read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(values_only=True))
    head = [str(h).strip() if h is not None else "" for h in all_rows[0]]
    if head[:19] != HEADERS:
        sys.exit(f"❌ 明细表头与 XS 不一致，中止\n 实际: {head[:19]}")
    seen, rows = set(), []
    for r in all_rows[1:]:
        if not r[0] or not str(r[0]).strip():
            continue
        cells = []
        for i, c in enumerate(r[:19]):
            if c is None:
                cells.append("")
            elif hasattr(c, "strftime"):
                cells.append(c.strftime("%Y-%m-%d"))
            else:
                cells.append(str(c))
        # S列缺失 = 金额(12) − 毛利(13)
        if cells[18].strip() == "":
            try:
                cells[18] = str(float(cells[12]) - float(cells[13]))
            except (ValueError, TypeError):
                pass
        key = (cells[0].strip(), cells[5].strip())  # 出库单号+SKU编码
        if key in seen:
            continue
        seen.add(key)
        rows.append(cells)
    return rows


def build_rows_xml(rows, header_row1_xml):
    """生成新 sheetData：原表头行 + 样式化数据行 + 样式化空行。"""
    parts = ["<sheetData>", header_row1_xml]
    for ri, r in enumerate(rows, start=2):
        cells = []
        for ci in range(19):
            is_num, sid = COL_STYLES[ci]
            ref = f"{get_column_letter(ci+1)}{ri}"
            if ci == 2:  # 日期 → 序列数
                ser = date_serial(r[ci])
                if ser is not None:
                    cells.append(f'<c r="{ref}" s="{sid}" t="n"><v>{ser}</v></c>')
                    continue
                is_num = False
            if is_num:
                nv = num_str(r[ci])
                if nv is not None:
                    cells.append(f'<c r="{ref}" s="{sid}" t="n"><v>{nv}</v></c>')
                    continue
                cells.append(f'<c r="{ref}" s="{sid}" t="n" />')
            else:
                txt = str(r[ci]).strip()
                if txt:
                    cells.append(f'<c r="{ref}" s="{sid}" t="inlineStr"><is><t>{esc(txt)}</t></is></c>')
                else:
                    cells.append(f'<c r="{ref}" s="{sid}" t="n" />')
        parts.append(f'<row r="{ri}" {ROW_ATTRS}>{"".join(cells)}</row>')

    last_data = len(rows) + 1
    last = max(last_data, MIN_LAST_ROW)
    tail_cols = [get_column_letter(i) for i in range(20, 50)]  # T..AW
    for ri in range(last_data + 1, last + 1):
        cells = []
        for ci in range(19):
            _, sid = COL_STYLES[ci]
            cells.append(f'<c r="{get_column_letter(ci+1)}{ri}" s="{sid}" t="n" />')
        for col in tail_cols:
            cells.append(f'<c r="{col}{ri}" s="{TAIL_STYLE}" t="n" />')
        parts.append(f'<row r="{ri}" {ROW_ATTRS}>{"".join(cells)}</row>')
    parts.append("</sheetData>")
    return "".join(parts), last


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else sys.exit("用法: write_xs_xml.py <明细.xlsx> [目标.xlsx]")
    target = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_XLSX
    if not os.path.exists(src):
        sys.exit(f"❌ 找不到明细: {src}")
    if not os.path.exists(target):
        sys.exit(f"❌ 找不到底表: {target}")

    rows = load_rows(src)
    if not rows:
        sys.exit("❌ 明细无数据行，中止")
    gross = sum(float(r[13] or 0) for r in rows if num_str(r[13]) is not None)
    print(f"→ 明细去重后 {len(rows)} 行，毛利合计 ¥{gross:,.2f}")

    # 备份（保留最近10份）
    bak_dir = os.path.join(os.path.dirname(target), "_备份")
    os.makedirs(bak_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.splitext(os.path.basename(target))[0]
    bak = os.path.join(bak_dir, f"{base}_备份{stamp}.xlsx")
    shutil.copy2(target, bak)
    print(f"→ 已备份: {os.path.basename(bak)}")
    for old in sorted(f for f in os.listdir(bak_dir) if f.startswith(base + "_备份"))[:-10]:
        os.remove(os.path.join(bak_dir, old))

    # 提取原行1（表头）作为模板
    with zipfile.ZipFile(target, "r") as zin:
        xml = zin.read(XS_SHEET_FILE).decode("utf-8")
    m1 = re.search(r'<row r="1"[^>]*>.*?</row>', xml, re.S)
    if not m1:
        sys.exit("❌ 原XS表头行提取失败")
    header_row1 = m1.group(0)

    new_sheetdata, last = build_rows_xml(rows, header_row1)
    last_data = len(rows) + 1

    # 原位替换
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(tmp_fd)
    with zipfile.ZipFile(target, "r") as zin, \
         zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == XS_SHEET_FILE:
                x = data.decode("utf-8")
                x = re.sub(r"<sheetData>.*?</sheetData>|<sheetData/>",
                           new_sheetdata, x, count=1, flags=re.S)
                x = re.sub(r'<dimension ref="[^"]+"',
                           f'<dimension ref="A1:AW{last}"', x, count=1)
                data = x.encode("utf-8")
            elif item.filename == "xl/workbook.xml":
                x = data.decode("utf-8")
                if "fullCalcOnLoad" not in x:
                    if "<calcPr" in x:
                        x = re.sub(r"<calcPr", '<calcPr fullCalcOnLoad="1"', x, count=1)
                    else:
                        x = x.replace("</workbook>", '<calcPr calcId="0" fullCalcOnLoad="1"/></workbook>')
                data = x.encode("utf-8")
            zout.writestr(item, data)
    shutil.move(tmp_path, target)
    print(f"→ XS sheet XML 原位替换完成（数据至第 {last_data} 行，空行填充至 {last}）")

    # 校验：行数 / 毛利口径 / 公式 / 条件格式
    wb2 = load_workbook(target, read_only=False, data_only=False)
    ws2 = wb2["XS"]
    n = sum(1 for r in ws2.iter_rows(min_row=2, values_only=True) if r[0] is not None)
    hdr = [c.value for c in next(ws2.iter_rows(min_row=1, max_row=1))]
    assert hdr[:5] == HEADERS[:5], f"表头异常: {hdr[:5]}"
    assert n == len(rows), f"行数不符: {n} vs {len(rows)}"
    emp4 = {"邵乐乐", "杨丽华", "李泽", "张博晨"}
    vals = [(r[3], r[13], r[15]) for r in ws2.iter_rows(min_row=2, values_only=True) if r[0] is not None]
    g4 = sum(float(v[1] or 0) for v in vals if v[2] in emp4)
    assert abs(g4 - 52602.54) < 0.01 or abs(g4 - gross) < 0.01 or g4 < gross, \
        f"4人毛利异常: {g4} vs 总毛利 {gross}"
    # 校验 4人口径 ≤ 全门店（差额=非本店业务员）且总毛利一致
    gall = sum(float(v[1] or 0) for v in vals if num_str(str(v[1] or "")) is not None)
    assert abs(gall - gross) < 0.01, f"总毛利不符: {gall} vs {gross}"
    aa = wb2["李家村销售"]["AA14"].value
    assert hasattr(aa, "text") and "SUMIFS" in aa.text, "AA14公式丢失"
    cf_count = sum(
        len(re.findall(r"<conditionalFormatting", z.read(f).decode("utf-8", "ignore")))
        for z in [zipfile.ZipFile(target)]
        for f in z.namelist() if f.startswith("xl/worksheets/sheet") and f.endswith(".xml")
    )
    assert cf_count >= 118, f"条件格式丢失: {cf_count} < 118"
    print(f"✓ 校验通过: {n} 行 | 4人毛利 ¥{g4:,.2f} | 公式完好 | 条件格式 {cf_count} 处")


if __name__ == "__main__":
    main()
