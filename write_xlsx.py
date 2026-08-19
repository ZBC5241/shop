#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把用友云明细写回《李家村X月任务进度.xlsx》的 XS / RXS 工作表。

做法：直接改写 xlsx 内部的 sheet XML。
  - 只替换 XS / RXS 两张明细表的数据行
  - 图表、图片、公式、格式、条件格式、其它 20 张表 —— 一个字节都不动
  - 在 workbook.xml 打开 fullCalcOnLoad，WPS/Excel 一打开就全量重算

用法：
  python write_xlsx.py <明细.tsv> [目标.xlsx] [--day YYYY-MM-DD]
    --day 指定 RXS（当日明细）取哪一天，默认取明细里最后一天
"""
import datetime
import os
import re
import shutil
import sys
import zipfile

DEFAULT_XLSX = "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
EPOCH = datetime.date(1899, 12, 30)

EXPECT_HEADER = [
    "出库单号", "单据类型", "出库日期", "商品分类", "商品sku分类",
    "商品SKU编码", "商品名称", "入库属性", "数量", "单价", "原价",
    "折扣价", "金额", "毛利", "SO激励", "业务员", "库区",
    "销售出库单门店", "销售成本",
]
# 0-based 列类型
NUM_IDX = {8, 9, 10, 11, 12, 13, 14, 18}
DATE_IDX = {2}


def col_letter(i):
    """0-based 列号 -> 字母"""
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def to_serial(datestr):
    d = datetime.datetime.strptime(str(datestr)[:10], "%Y-%m-%d").date()
    return (d - EPOCH).days


def parse_tsv(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().rstrip("\n").split("\n")
    hdr = lines[0].split("\t")
    if hdr != EXPECT_HEADER:
        sys.exit("!! 用友云报表字段变了，已中止。\n   期望 %s\n   实际 %s"
                 % (EXPECT_HEADER, hdr))
    out = []
    for ln in lines[1:]:
        r = ln.split("\t")
        r = (r + [""] * 19)[:19]
        out.append([c.strip() for c in r])
    return out


def get_sheet_path(z, sheet_name):
    wbxml = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    # 逐个解析 Relationship，不依赖 Id/Target 的书写顺序（WPS 重存可能翻转顺序）
    rmap = {}
    for m in re.finditer(r'<Relationship\b([^>]*)/?>', rels):
        attrs = m.group(1)
        idm = re.search(r'Id="([^"]+)"', attrs)
        tgm = re.search(r'Target="([^"]+)"', attrs)
        if idm and tgm:
            rmap[idm.group(1)] = tgm.group(1)
    for m in re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wbxml):
        if m.group(1) == sheet_name:
            t = rmap[m.group(2)]
            # 归一化为 zip 内相对路径：兼容绝对(/xl/..)与相对(worksheets/..)两种 Target
            t = t.replace("\\", "/")
            if t.startswith("/"):
                t = t.lstrip("/")
            elif not t.startswith("xl/"):
                t = "xl/" + t.lstrip("./")
            return t
    sys.exit("!! 找不到工作表: " + sheet_name)


def extract_template(xml):
    """从第 2 行取样式模板：row 属性 + 各列 s 值"""
    m = re.search(r'<row r="2"([^>]*)>(.*?)</row>', xml, re.S)
    if not m:
        return "", {}
    rowattr = re.sub(r'\s*spans="[^"]*"', "", m.group(1))
    styles = {}
    for c in re.finditer(r'<c r="([A-Z]+)2"(?:\s+s="(\d+)")?', m.group(2)):
        styles[c.group(1)] = c.group(2)
    return rowattr, styles


def build_rows(rows, rowattr, styles, extra_cols):
    """生成数据行 XML，从第 2 行开始"""
    buf = []
    for n, r in enumerate(rows, start=2):
        cells = []
        for i in range(19):
            L = col_letter(i)
            s = styles.get(L)
            sa = ' s="%s"' % s if s else ""
            v = r[i]
            if v in ("", None):
                cells.append('<c r="%s%d"%s/>' % (L, n, sa))
            elif i in DATE_IDX:
                cells.append('<c r="%s%d"%s><v>%d</v></c>' % (L, n, sa, to_serial(v)))
            elif i in NUM_IDX:
                num = str(v).replace(",", "")
                try:
                    f = float(num)
                    num = ("%d" % f) if f == int(f) else repr(f)
                    cells.append('<c r="%s%d"%s><v>%s</v></c>' % (L, n, sa, num))
                except ValueError:
                    cells.append('<c r="%s%d"%s t="inlineStr"><is><t>%s</t></is></c>'
                                 % (L, n, sa, esc(v)))
            else:
                cells.append('<c r="%s%d"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                             % (L, n, sa, esc(v)))
        # 保留右侧空列的样式，外观不变
        for L in extra_cols:
            s = extra_cols[L]
            cells.append('<c r="%s%d"%s/>' % (L, n, (' s="%s"' % s) if s else ""))
        buf.append('<row r="%d"%s spans="1:49">%s</row>' % (n, rowattr, "".join(cells)))
    return "".join(buf)


# RXS 原生动态数组公式：从 XS 自动筛出日期最大的那一天
RXS_FORMULA = "_xlfn._xlws.FILTER(XS!A2:S3000,XS!C2:C3000=MAX(XS!C2:C3000))"


def restore_rxs_formula(xml, n_rows):
    """把 RXS 的 A2 还原成 FILTER 动态数组公式（保留缓存值，供不打开表格时读取）。

    RXS 本质是 XS 的派生视图，绝不能写死成静态数据，
    否则 XS 更新后「当日达成」不会跟着变。
    """
    ref = "A2:S%d" % (n_rows + 1)
    pat = re.compile(r'<c r="A2"([^>]*?)(?:\s*/>|>(.*?)</c>)', re.S)
    m = pat.search(xml)
    if not m:
        return xml
    attrs, inner = m.group(1), m.group(2) or ""
    style = re.search(r'\s*s="(\d+)"', attrs)
    sa = ' s="%s"' % style.group(1) if style else ""
    # 从 inlineStr 或 <v> 里取出缓存值
    cv = re.search(r"<t[^>]*>(.*?)</t>", inner, re.S) or re.search(r"<v>(.*?)</v>", inner, re.S)
    cache = cv.group(1) if cv else ""
    new = ('<c r="A2"%s t="str" cm="1"><f t="array" ref="%s">%s</f><v>%s</v></c>'
           % (sa, ref, RXS_FORMULA, cache))
    return xml[:m.start()] + new + xml[m.end():]


def rewrite_sheet(xml, rows):
    rowattr, styles = extract_template(xml)
    extra = {k: v for k, v in styles.items()
             if len(k) > 1 or k > "S"}  # T..AW
    extra = {k: styles[k] for k in sorted(
        [c for c in styles if (len(c) > 1 or c > "S")],
        key=lambda c: (len(c), c))}
    core = {k: v for k, v in styles.items() if k in
            [col_letter(i) for i in range(19)]}

    new_rows = build_rows(rows, rowattr, core, extra)

    # 保留第 1 行（表头），删掉其余所有行
    head = re.search(r'<row r="1"[^>]*>.*?</row>', xml, re.S)
    head_xml = head.group(0) if head else ""

    def repl(m):
        return "<sheetData>" + head_xml + new_rows + "</sheetData>"

    xml = re.sub(r"<sheetData>.*?</sheetData>", repl, xml, count=1, flags=re.S)
    # 更新 dimension
    xml = re.sub(r'<dimension ref="A1:[A-Z]+\d+"/>',
                 '<dimension ref="A1:AW%d"/>' % (len(rows) + 1), xml, count=1)
    # 视图锚点复位，避免打开时停在旧的滚动位置
    xml = re.sub(r'\s*topLeftCell="[^"]*"', "", xml, count=1)
    return xml


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    day = None
    for a in sys.argv[1:]:
        if a.startswith("--day"):
            day = a.split("=", 1)[1] if "=" in a else None
    if "--day" in sys.argv:
        i = sys.argv.index("--day")
        if i + 1 < len(sys.argv):
            day = sys.argv[i + 1]
            if day in args:
                args.remove(day)

    if not args:
        sys.exit("用法: python write_xlsx.py <明细.tsv> [目标.xlsx] [--day YYYY-MM-DD]")

    tsv = args[0]
    xlsx = args[1] if len(args) > 1 else DEFAULT_XLSX

    rows = parse_tsv(tsv)
    if not rows:
        sys.exit("!! 明细为空，已中止（防止清空表格）")

    dates = sorted({r[2][:10] for r in rows if r[2]})
    day = day or dates[-1]
    day_rows = [r for r in rows if r[2][:10] == day]

    print("→ 明细 %d 行，%s ~ %s" % (len(rows), dates[0], dates[-1]))
    print("→ 当日(%s) %d 行" % (day, len(day_rows)))

    # 备份
    bak_dir = os.path.join(os.path.dirname(xlsx), "_备份")
    os.makedirs(bak_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(xlsx))[0]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = os.path.join(bak_dir, "%s_备份%s.xlsx" % (base, stamp))
    shutil.copy2(xlsx, bak)
    print("→ 已备份:", os.path.basename(bak))
    keep = sorted(f for f in os.listdir(bak_dir) if f.startswith(base + "_备份"))
    for old in keep[:-10]:
        os.remove(os.path.join(bak_dir, old))

    zin = zipfile.ZipFile(xlsx)
    xs_path = get_sheet_path(zin, "XS")
    rxs_path = get_sheet_path(zin, "RXS")

    out = xlsx + ".tmp"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == xs_path:
                data = rewrite_sheet(data.decode("utf-8"), rows).encode("utf-8")
            elif item.filename == rxs_path:
                # RXS 是 XS 的派生视图：先写缓存值（供不打开表格时读取），
                # 再把 A2 还原成 FILTER 动态数组公式，保证 XS 变时 RXS 跟着变
                s = rewrite_sheet(data.decode("utf-8"), day_rows)
                s = restore_rxs_formula(s, len(day_rows))
                data = s.encode("utf-8")
            elif item.filename == "xl/workbook.xml":
                s = data.decode("utf-8")
                if "fullCalcOnLoad" not in s:
                    s = re.sub(r"<calcPr([^>]*?)/>",
                               r'<calcPr\1 fullCalcOnLoad="1"/>', s, count=1)
                data = s.encode("utf-8")
            zo.writestr(item, data)
    zin.close()

    os.replace(out, xlsx)
    # 清掉隔离标记，避免 Excel 进受保护视图
    os.system('xattr -c "%s" 2>/dev/null' % xlsx)

    print("✓ 已写入 XS(%d行) + RXS(%d行)" % (len(rows), len(day_rows)))
    print("  文件:", xlsx)
    print("  打开表格后所有公式自动重算")


if __name__ == "__main__":
    main()
