#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把用友云「销售分析」报表导出的 Excel，写入《李家村X月任务进度.xlsx》的
「销售分析」工作表。

做法（与 write_xlsx.py 同思路，直接改写 xlsx 内部 sheet XML）：
  - 「销售分析」表 A1 是标题“销售分析”、A2 是 42 列字段表头（模板结构，保留）
  - 先清空 A3 起的旧数据，再把导出文件 A3 起的数据整块写入
  - 只动「销售分析」这一张表的 XML，其它 20+ 张表 / 图表 / 公式 / 格式 一个字节不变
  - 在 workbook.xml 打开 fullCalcOnLoad，Excel/WPS 一打开就全量重算

用法：
  python update_sales_analysis.py [源Excel] [目标.xlsx]
  源Excel 缺省自动取 ~/Downloads 中最新的「销售分析_*.xlsx」
"""
import os
import re
import sys
import json
import zipfile
import shutil
import datetime
import glob

DEFAULT_XLSX = "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"
SHEET = "销售分析"
NCOLS = 42  # A..AP


def find_latest_src():
    files = glob.glob(os.path.expanduser("~/Downloads/销售分析_*.xlsx"))
    return max(files, key=os.path.getmtime) if files else None


# ---------- 读源（导出 xlsx，zip 解析，绕过 openpyxl 样式缺陷）----------
def read_src(path):
    z = zipfile.ZipFile(path)
    ss = z.read("xl/sharedStrings.xml").decode("utf-8")
    strings = re.findall(r"<t[^>]*>(.*?)</t>", ss, re.S)

    def gs(i):
        try:
            return strings[int(i)]
        except Exception:
            return ""

    sheet = [n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)]
    if not sheet:
        return []
    xml = z.read(sheet[0]).decode("utf-8")

    def parse_row(rx):
        d = {}
        for c in re.finditer(r'<c r="([A-Z]+)\d+"([^>]*?)(?:/>|>([\s\S]*?)</c>)', rx):
            col = c.group(1)
            attr = c.group(2)
            inner = c.group(3) or ""
            if "inlineStr" in attr or "<is>" in inner:
                mt = re.search(r"<t[^>]*>(.*?)</t>", inner, re.S)
                d[col] = mt.group(1) if mt else ""
            else:
                v = re.search(r"<v>(.*?)</v>", inner, re.S)
                if v:
                    val = v.group(1)
                    if 't="s"' in attr:
                        val = gs(val)
                    d[col] = val
                else:
                    d[col] = ""  # 自闭合空单元格
        return d

    rows = []
    for r in range(3, 200000):
        m = re.search(r'<row r="%d"[^>]*>(.*?)</row>' % r, xml, re.S)
        if not m:
            break
        d = parse_row(m.group(1))
        if not any(d.values()):
            break  # 整行全空才停
        row = [d.get(col_letter(i), "") for i in range(NCOLS)]
        rows.append(row)
    z.close()
    return rows


# ---------- 读 JSON（纯HTTP销售分析，42列映射）----------
def _gv(rec, *keys, default=""):
    """取 record 中第一个非空字段值。"""
    for k in keys:
        v = rec.get(k)
        if v not in (None, "", []):
            return v
    return default


# 42 列（A..AP）取值函数；None 表示该列当前 API 无对应（回收/垫付/电信等，留空）。
# 列序严格对齐 wecom_report.py 读取语义：G(7)=姓名、P(16)=华为获客渠道名称、AM(39)=销售净额。
SA_COLMAP = [
    lambda r: _gv(r, "vouchdate"),                                      # A 单据日期
    lambda r: _gv(r, "dDate"),                                          # B 业务日期
    lambda r: _gv(r, "code"),                                           # C 单据编号
    lambda r: _gv(r, "store_code"),                                     # D 门店编码
    lambda r: _gv(r, "store_name"),                                     # E 门店名称
    lambda r: _gv(r, "iWarehouseid_name"),                              # F 仓库
    lambda r: _gv(r, "iEmployeeid_name"),                               # G 营业员名称
    lambda r: _gv(r, "iBusinesstypeid_name"),                           # H 业务类型名称
    lambda r: _gv(r, "iMemberid_name"),                                 # I 会员姓名
    lambda r: _gv(r, "iMemberid_cphone"),                               # J 会员手机号
    lambda r: _gv(r, "oid_userDefine_2425253761215627271"),             # K 品牌分类
    None,                                                                # L 上级商品分类(无对应)
    lambda r: _gv(r, "productClass_name"),                              # M 商品分类名称
    lambda r: _gv(r, "product_cName"),                                  # N 商品名称
    lambda r: _gv(r, "productsku_cCode"),                               # O 商品sku名称
    lambda r: _gv(r, "retailVouchHeaderDefineCharacter__HWHKQD_name"),  # P 华为获客渠道名称
    None,                                                                # Q 商场POS单号(与单据编号同,留空)
    None,                                                                # R 回收金额
    None,                                                                # S 回收机型
    None,                                                                # T 回收平台
    None,                                                                # U 未先进先出原因名称
    lambda r: _gv(r, "oid_userDefine_2470387991963500544"),             # V 垫付事业部
    None,                                                                # W 垫付原因名称
    None,                                                                # X 电信系统销售单号
    None,                                                                # Y 玲珑系统销售单号
    None,                                                                # Z 序列号
    None,                                                                # AA 华为手机SKU颜色
    lambda r: _gv(r, "iDeliveryState"),                                  # AB 交货状态
    lambda r: _gv(r, "iPayState"),                                       # AC 收款状态
    None,                                                                # AD 入库属性
    None,                                                                # AE 来源单据号
    lambda r: 1,                                                         # AF 单据数(每行1)
    lambda r: _gv(r, "fQuantity"),                                       # AG 销售数量
    lambda r: _gv(r, "fRetailMoney"),                                    # AH 零售金额
    lambda r: _gv(r, "fDiscount"),                                       # AI 折扣额
    lambda r: _gv(r, "fDiscountRate"),                                   # AJ 折扣率
    None,                                                                # AK 客单量
    None,                                                                # AL 客单价
    lambda r: _gv(r, "fNetMoney"),                                       # AM 销售净额
    None,                                                                # AN 预订
    None,                                                                # AO 垫付
    lambda r: _gv(r, "iNegative"),                                       # AP 普通
]


def read_json(json_path):
    d = json.load(open(json_path, encoding="utf-8"))
    recs = d.get("records", [])
    rows = []
    for rec in recs:
        row = [fn(rec) if fn else "" for fn in SA_COLMAP]
        rows.append(row)
    return rows


# ---------- 写目标 ----------
def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def is_num(s):
    s = str(s).replace(",", "").strip()
    if s in ("", "-", "—"):
        return False
    try:
        float(s)
        return True
    except Exception:
        return False


def num_val(s):
    s = str(s).replace(",", "").strip()
    try:
        f = float(s)
        if f != f or f in (float("inf"), float("-inf")):
            return ""  # inf / nan -> 视为空
        return repr(f)
    except Exception:
        return s


def get_sheet_path(z, sheet_name):
    wbxml = z.read("xl/workbook.xml").decode("utf-8")
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    rmap = {}
    for m in re.finditer(r"<Relationship\b([^>]*)/>", rels):
        attrs = m.group(1)
        idm = re.search(r'Id="([^"]+)"', attrs)
        tgm = re.search(r'Target="([^"]+)"', attrs)
        if idm and tgm:
            rmap[idm.group(1)] = tgm.group(1)
    for m in re.finditer(r'<sheet[^>]*name="([^"]+)"[^>]*r:id="([^"]+)"', wbxml):
        if m.group(1) == sheet_name:
            # WPS 生成的 rels Target 可能是绝对路径 "/xl/worksheets/sheetN.xml"，
            # 也可能是相对 "worksheets/sheetN.xml"；统一归一成包内相对路径。
            tgt = rmap[m.group(2)].lstrip("/")
            if not tgt.startswith("xl/"):
                tgt = "xl/" + tgt
            return tgt
    raise RuntimeError("找不到工作表: " + sheet_name)


def import_into(target, rows):
    zin = zipfile.ZipFile(target)
    path = get_sheet_path(zin, SHEET)
    xml = zin.read(path).decode("utf-8")

    # 数据行样式模板：优先用原 A3 数据行的列样式（保留日期/数字等格式），
    # 缺失列再用 A2 表头样式补齐（表头通常是常规文本格式）
    styles = {}
    rowattr = ""
    m3 = re.search(r'<row r="3"([^>]*)>(.*?)</row>', xml, re.S)
    if m3:
        rowattr = re.sub(r'\s*spans="[^"]*"', "", m3.group(1))
        rowattr = re.sub(r'\s*r="\d+"', "", rowattr)
        for c in re.finditer(r'<c r="([A-Z]+)3"(?:\s+s="(\d+)")?', m3.group(2)):
            if c.group(2):
                styles[c.group(1)] = c.group(2)
    m2 = re.search(r'<row r="2"([^>]*)>(.*?)</row>', xml, re.S)
    if not rowattr:
        rowattr = re.sub(r'\s*spans="[^"]*"', "", m2.group(1))
        rowattr = re.sub(r'\s*r="\d+"', "", rowattr)
    for c in re.finditer(r'<c r="([A-Z]+)2"(?:\s+s="(\d+)")?', m2.group(2)):
        if c.group(1) not in styles and c.group(2):
            styles[c.group(1)] = c.group(2)

    # A1 标题、A2 表头 原样保留
    head1 = re.search(r'<row r="1"[^>]*>.*?</row>', xml, re.S).group(0)
    head2 = m2.group(0)

    # 生成 A3 起数据行
    buf = []
    for n, row in enumerate(rows, start=3):
        cells = []
        for i in range(NCOLS):
            L = col_letter(i)
            s = styles.get(L)
            sa = ' s="%s"' % s if s else ""
            v = row[i]
            if v in ("", None):
                cells.append('<c r="%s%d"%s/>' % (L, n, sa))
            elif is_num(v):
                nv = num_val(v)
                if nv == "":
                    cells.append('<c r="%s%d"%s/>' % (L, n, sa))
                else:
                    cells.append('<c r="%s%d"%s><v>%s</v></c>' % (L, n, sa, nv))
            else:
                cells.append('<c r="%s%d"%s t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                             % (L, n, sa, esc(v)))
        buf.append('<row r="%d"%s spans="1:%d">%s</row>' % (n, rowattr, NCOLS, "".join(cells)))

    new_data = "<sheetData>" + head1 + head2 + "".join(buf) + "</sheetData>"
    xml = re.sub(r"<sheetData>.*?</sheetData>", new_data, xml, count=1, flags=re.S)
    xml = re.sub(r'<dimension ref="[^"]*"', '<dimension ref="A1:%s%d"' % (col_letter(NCOLS - 1), len(rows) + 2), xml, count=1)
    xml = re.sub(r'\s*topLeftCell="[^"]*"', "", xml, count=1)

    out = target + ".tmp"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == path:
                data = xml.encode("utf-8")
            elif item.filename == "xl/workbook.xml":
                s = data.decode("utf-8")
                if "fullCalcOnLoad" not in s:
                    s = re.sub(r"<calcPr([^>]*?)/>", r'<calcPr\1 fullCalcOnLoad="1"/>', s, count=1)
                data = s.encode("utf-8")
            zo.writestr(item, data)
    zin.close()
    os.replace(out, target)
    os.system('xattr -c "%s" 2>/dev/null' % target)


def main():
    src = sys.argv[1] if len(sys.argv) >= 2 else find_latest_src()
    xlsx = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_XLSX
    if not src or not os.path.exists(src):
        print("!! 找不到源（JSON或xlsx）"); sys.exit(1)
    if not os.path.exists(xlsx):
        print("!! 找不到目标表格:", xlsx); sys.exit(1)

    if src.lower().endswith(".json"):
        print("→ 源为纯HTTP销售分析 JSON，按42列映射转换…")
        rows = read_json(src)
    else:
        print("→ 源为导出 xlsx，按原逻辑读取…")
        rows = read_src(src)
    if not rows:
        print("!! 源数据为空，已中止（防止清空表格）"); sys.exit(1)
    print("→ 源数据 %d 行" % len(rows))

    # 备份
    bak_dir = os.path.join(os.path.dirname(xlsx), "_备份")
    os.makedirs(bak_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    base = os.path.splitext(os.path.basename(xlsx))[0]
    bak = os.path.join(bak_dir, "%s_备份%s.xlsx" % (base, stamp))
    shutil.copy2(xlsx, bak)
    print("→ 已备份:", os.path.basename(bak))
    for old in sorted([f for f in os.listdir(bak_dir) if f.startswith(base + "_备份")])[:-10]:
        os.remove(os.path.join(bak_dir, old))

    print("→ 写入「销售分析」(保留标题+A2表头，清空A3起重贴)…")
    import_into(xlsx, rows)
    print("✓ 完成，写入 %d 条数据（含标题+表头共 %d 行）" % (len(rows), len(rows) + 2))
    print("  文件:", xlsx)


if __name__ == "__main__":
    main()
