#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update_sa_cache.py — 从销售分析导出的xlsx提取渠道数据，写入 sa_aug_cache.json。

替代手动操作（原93s），脚本化后<5s。
用zipfile+XML直接解析（openpyxl无法读取用友导出的xlsx样式）。

用法：
    python update_sa_cache.py <销售分析.xlsx> [-o sa_aug_cache.json]
"""
import sys, os, json, zipfile, datetime, argparse
import xml.etree.ElementTree as ET

BASE = os.path.dirname(os.path.abspath(__file__))

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

# xlsx列字母 → merge_qudao需要的字段名
EXTRACT_MAP = {
    "G":  "iEmployeeid_name",
    "H":  "iBusinesstypeid_name",
    "P":  "retailVouchHeaderDefineCharacter__HWHKQD_name",
    "AM": "fNetMoney",
    "AG": "fQuantity",
    "B":  "dDate",
    "C":  "code",
    "N":  "product_cName",
    "O":  "productsku_cCode",
    "I":  "iMemberid_name",
    "J":  "iMemberid_cphone",
}


def col_letter(ref):
    return "".join(ch for ch in ref if ch.isalpha())


def parse_xlsx(path):
    """用zipfile+ET解析xlsx，返回records列表。"""
    z = zipfile.ZipFile(path)

    # sharedStrings
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        tree = ET.parse(z.open("xl/sharedStrings.xml"))
        for si in tree.getroot():
            t = "".join(node.text or "" for node in si.iter(f"{NS}t"))
            shared.append(t)

    tree = ET.parse(z.open("xl/worksheets/sheet1.xml"))
    root = tree.getroot()
    rows = root.findall(f".//{NS}row")

    # 第5行=表头，第6行起=数据，末行=合计
    records = []
    for row in rows[5:]:  # 跳过前5行(标题信息+表头)
        rec = {}
        for c in row.findall(f"{NS}c"):
            ref = c.get("r")
            t_attr = c.get("t")
            v = c.find(f"{NS}v")
            val = v.text if v is not None else ""
            if t_attr == "s":
                val = shared[int(val)] if val else ""
            col = col_letter(ref)
            if col not in EXTRACT_MAP:
                continue
            field = EXTRACT_MAP[col]
            if field in ("fNetMoney", "fQuantity"):
                try:
                    val = float(val) if val else 0.0
                except ValueError:
                    val = 0.0
            elif field == "dDate":
                # Excel日期序列号 → ISO日期
                try:
                    serial = float(val)
                    dt = datetime.date(1900, 1, 1) + datetime.timedelta(days=serial - 2)
                    val = dt.isoformat()
                except (ValueError, OverflowError):
                    pass
            rec[field] = val
        # 跳过合计行（无单据编号且无业务员）
        if rec.get("code") or rec.get("iEmployeeid_name"):
            records.append(rec)

    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", help="销售分析导出xlsx路径")
    ap.add_argument("-o", "--out", default=os.path.join(BASE, "sa_aug_cache.json"))
    a = ap.parse_args()

    if not os.path.exists(a.xlsx):
        sys.exit(f"❌ 文件不存在: {a.xlsx}")

    records = parse_xlsx(a.xlsx)
    total_net = sum(r.get("fNetMoney", 0) for r in records)
    total_qty = sum(r.get("fQuantity", 0) for r in records)

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"records": records}, f, ensure_ascii=False, indent=1)

    print(f"✅ sa_cache更新 → {a.out}")
    print(f"   记录 {len(records)} 条 | 销售净额 ¥{total_net:,.2f} | 数量 {total_qty:.0f}")


if __name__ == "__main__":
    main()
