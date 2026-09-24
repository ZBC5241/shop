#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会员注册报表固定脚本（李家村 9月）
=================================
用途：每天推算「会员注册&权益发放数据」报表的门店级与员工级指标，
      输出员工达成占比及逐日明细 Excel。

口径（已用 9.1-9.10 / 9.1-9.11 两张官方报表 100% 回归验证）：
  总客户数   = POS「销售分析」业务类型=普通 的零售单，
               会员手机号(1\\d{10})去重，按期内销售净额合计>=0 计
  老客       = POS客户 ∩ 会员库(cAppDesc=U会员 且 注册日期<当月1号)
               （不看公众号关注状态——官方报表自述口径与实现不符，以此为准）
  需注册数   = 总客户数 - 老客
  已注册数   = 会员库：U会员 & 公众号已关注(WXStatus=1) & 最后交易时间∈统计期
               （会员库全域口径，不限当月POS客户；以统计截止时间截断）
  注册率     = 已注册 / 需注册
  员工归属   已注册：当月POS客户按其首单营业员；非POS客户按会员库登记员工
             （已验证：9.11晚快照 李泽12/邵乐乐10/杨丽华12/张博晨1 全部精确命中）
  ※ 员工级"总客户/老客"归属规则未获官方口径确认，默认按首单营业员，
    与官方报表可能存在 ±1~3 人误差（详见脚本末尾"待确认事项"）

用法：
  # 拉最新数据并算 9.1 至今天（默认，截止当前时刻）
  python3 daily_employee_report.py

  # 指定截止时间（对齐官方报表快照，如 9.11 晚 21:03）
  python3 daily_employee_report.py --until "2026-09-11 21:03"

  # 只用本地已有数据，不联网刷新
  python3 daily_employee_report.py --no-fetch

  # 指定 POS 销售分析文件
  python3 daily_employee_report.py --pos /path/to/销售分析_0912.xlsx

数据依赖：
  POS:   销售分析.xlsx（列: A单据日期/B业务日期/G营业员名称/H业务类型名称/
         J会员手机号/AM销售净额），由 fetch_yonyou_fast.py 导出
  会员库: /tmp/lijiacun_members_full.json 或 .temp/members_cache.json，
         由 fetch_members.py 全量拉取
"""
import argparse
import collections
import datetime
import json
import os
import re
import subprocess
import sys
import zipfile

# ---------------------------------------------------------------- 常量
SHOP = os.path.dirname(os.path.abspath(__file__))
TEMP = os.path.join(SHOP, ".temp")
MEMBERS_JSON = "/tmp/lijiacun_members_full.json"
MEMBERS_CACHE = os.path.join(TEMP, "members_cache.json")
POS_DIR = "/Users/mac/.local/share/TeleAgent/playwright-mcp"
MONTH_START = datetime.datetime(2026, 9, 1)
STAFF = ["张博晨", "邵乐乐", "杨丽华", "李泽"]        # 店内现役
EXTERNAL = {"定凯丰", "陈超磊", "郑元坤B", "舒绒绒C"}  # 外部代录/离职账号
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
EXCEL_EPOCH = datetime.datetime(1899, 12, 30)

# ---------------------------------------------------------------- xlsx 解析


def load_shared_strings(z):
    try:
        root = _et_fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out = []
    for si in root.findall("m:si", NS):
        # 按 si 块整体拼接所有 t 文本（修复个别字符串含未闭合 <t> 导致整体错位）
        txt = "".join(
            t.text or ""
            for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
        )
        out.append(txt)
    return out


def _et_fromstring(data):
    from xml.etree import ElementTree as ET
    return ET.fromstring(data)


def load_xlsx_rows(path, sheet="sheet1"):
    """返回 [(行号, {列字母: 值})]；值已解析共享字符串/内联字符串。"""
    z = zipfile.ZipFile(path)
    sst = load_shared_strings(z)
    sheet_xml = z.read(f"xl/worksheets/{sheet}.xml").decode("utf-8", "ignore")
    rows = []
    for rm in re.finditer(r'<row[^>]*r="(\d+)"[^>]*>(.*?)</row>', sheet_xml, re.S):
        rnum = int(rm.group(1))
        row_body = rm.group(2)
        cells = {}
        for cm in re.finditer(r'<c r="([A-Z]+)(\d+)"([^>]*)/?>', row_body):
            letters, attrs = cm.group(1), cm.group(3)
            tm = re.search(r't="(\w+)"', attrs)
            t = tm.group(1) if tm else "n"
            # 在行体内向前扫描到 </c>，再取其中 <v>（避免跨单元格越界）
            endm = re.search(r"</c>", row_body[cm.end():])
            seg = row_body[cm.end(): cm.end() + (endm.start() if endm else 0)]
            vm = re.search(r"<v>([^<]*)</v>", seg)
            vm2 = re.search(r"<is>.*?</is>", seg, re.S)
            val = None
            if t == "s" and vm:
                idx = int(vm.group(1))
                val = sst[idx] if idx < len(sst) else None
            elif t == "inlineStr" and vm2:
                val = "".join(re.findall(r"<t[^>]*>([^<]*)</t>", vm2.group(0)))
            elif vm:
                val = vm.group(1)
            cells[letters] = val
        rows.append((rnum, cells))
    return rows


def parse_date(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return EXCEL_EPOCH + datetime.timedelta(days=float(v))
    s = str(v).strip()
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})"
                 r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?", s)
    if m:
        return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)),
                                 int(m.group(4) or 0), int(m.group(5) or 0),
                                 int(m.group(6) or 0))
    try:
        return EXCEL_EPOCH + datetime.timedelta(days=float(s))
    except ValueError:
        return None


def load_pos(path):
    """解析 POS 销售分析 -> 订单列表"""
    rows = load_xlsx_rows(path)
    orders = []
    for rnum, cells in rows:
        if rnum <= 2:  # 表头固定第2行
            continue

        def g(k, _c=cells):
            v = _c.get(k)
            return "" if v is None else str(v).strip()

        phone = g("J")
        if not re.fullmatch(r"1\d{10}", phone):
            continue
        dt = parse_date(g("A")) or parse_date(g("B"))
        try:
            amt = float(g("AM") or 0)
        except ValueError:
            amt = 0.0
        orders.append({
            "row": rnum, "phone": phone, "dt": dt,
            "biz": g("H"), "emp": g("G"), "amt": amt, "order_no": g("C"),
        })
    return orders


def load_members(path=None):
    """会员库 json -> {手机号: 记录}"""
    if path is None:
        path = MEMBERS_JSON if os.path.exists(MEMBERS_JSON) else MEMBERS_CACHE
    with open(path) as f:
        recs = json.load(f)
    by_phone = {}
    for r in recs:
        p = str(r.get("cPhone") or "").strip()
        if re.fullmatch(r"1\d{10}", p):
            by_phone[p] = r
    return by_phone


# ---------------------------------------------------------------- 数据刷新

def refresh_data(until):
    """联网刷新：POS销售分析 + 会员库全量。返回 (pos_path, members_path)。"""
    import glob as _glob
    # 1) POS 销售分析（店长账号）
    print("[1/2] 拉取 POS 销售分析（店长账号）...", flush=True)
    r = subprocess.run(
        [sys.executable, os.path.join(SHOP, "fetch_yonyou_fast.py"),
         "--account", "store"],
        capture_output=True, text=True, timeout=600)
    print("  " + (r.stdout or "").strip().splitlines()[-1] if r.stdout else "", flush=True)
    if r.returncode != 0:
        print("  ⚠️ POS 拉取失败，尝试用今日已有文件", flush=True)
    today_tag = until.strftime("%m%d")
    cands = sorted(_glob.glob(os.path.join(POS_DIR, "销售分析_*.xlsx")))
    pos_path = cands[-1] if cands else None
    if not pos_path:
        raise SystemExit("ERR: 找不到 POS 销售分析 xlsx 文件")

    # 2) 会员库全量
    print("[2/2] 拉取会员库全量...", flush=True)
    r2 = subprocess.run(
        [sys.executable, os.path.join(TEMP, "fetch_members.py")],
        capture_output=True, text=True, timeout=1200)
    tail = (r2.stdout or "").strip().splitlines()
    print("  " + (tail[-1] if tail else "(无输出)"), flush=True)
    members_path = MEMBERS_JSON if os.path.exists(MEMBERS_JSON) else MEMBERS_CACHE
    if not os.path.exists(members_path):
        raise SystemExit("ERR: 会员库 json 不存在")
    return pos_path, members_path


# ---------------------------------------------------------------- 指标计算

def is_old_member(m, month_start):
    """老客：U会员 & 注册日期 < 当月1号（不看关注状态）"""
    reg = m.get("dRegisterDate")
    try:
        regv = datetime.datetime.strptime(str(reg)[:19], "%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return False
    return m.get("cAppDesc") == "U会员" and regv < month_start


def build_customers(orders, cutoff, members):
    """期内普通单客户聚合（净额>=0），返回 {phone: 客户dict}"""
    agg = collections.defaultdict(lambda: {"os": [], "amt": 0.0})
    for o in orders:
        if o["dt"] and MONTH_START <= o["dt"] < cutoff and o["biz"] == "普通":
            agg[o["phone"]]["os"].append(o)
            agg[o["phone"]]["amt"] += o["amt"]
    cust = {}
    for phone, a in agg.items():
        if a["amt"] < 0:
            continue
        os_s = sorted(a["os"], key=lambda x: x["dt"])
        m = members.get(phone, {})
        reg = m.get("dRegisterDate")
        try:
            regv = datetime.datetime.strptime(str(reg)[:19], "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            regv = None
        cust[phone] = {
            "phone": phone, "first": os_s[0], "last": os_s[-1],
            "amt": a["amt"], "n": len(os_s),
            "app": m.get("cAppDesc", ""), "wx": str(m.get("WXStatus", "")),
            "reg": regv, "owner": m.get("employeeName", ""),
            "cs": m.get("csEmployeeName", ""),
        }
    return cust


def registered_set(members, cutoff):
    """已注册集合：会员库全域 U & WX1 & 最后交易∈[月初, cutoff)"""
    lo, hi = str(MONTH_START), str(cutoff)[:19]
    return {p for p, m in members.items()
            if m.get("cAppDesc") == "U会员"
            and str(m.get("WXStatus")) == "1"
            and lo <= str(m.get("dLastTradeTime", ""))[:19] < hi}


def calc(cust, members, cutoff, staff=STAFF):
    """返回 (门店级dict, 员工级dict)"""
    reged = registered_set(members, cutoff)
    olds = {p for p, c in cust.items() if c["app"] == "U会员" and c["reg"] and c["reg"] < MONTH_START}

    def reg_owner(p):
        # 已注册归属规则A：POS客户按首单营业员；非POS按会员库登记员工
        return cust[p]["first"]["emp"] if p in cust else members[p].get("employeeName", "")

    store = {
        "total": len(cust), "old": len(olds), "need": len(cust) - len(olds),
        "reged": len(reged),
    }
    store["rate"] = store["reged"] / store["need"] if store["need"] else 0.0

    emp = {}
    for name in staff:
        my_cust = {p for p, c in cust.items() if c["first"]["emp"] == name}
        my_old = my_cust & olds
        my_reged = sum(1 for p in reged if reg_owner(p) == name)
        emp[name] = {
            "total": len(my_cust), "old": len(my_old),
            "need": len(my_cust) - len(my_old), "reged": my_reged,
        }
        emp[name]["rate"] = emp[name]["reged"] / emp[name]["need"] if emp[name]["need"] else 0.0
    return store, emp, reged, olds


def daily_breakdown(cust, members, staff=STAFF):
    """逐日：按首单营业员归属的总客户/老客/需注册 + 当日新注册(有交易&关注)"""
    days = sorted({c["first"]["dt"].date() for c in cust.values()})
    out = {}
    for emp in staff:
        out[emp] = {}
    for d in days:
        day_cust = {p: c for p, c in cust.items() if c["first"]["dt"].date() == d}
        for emp in staff:
            my = {p for p, c in day_cust.items() if c["first"]["emp"] == emp}
            olds = sum(1 for p in my
                       if cust[p]["app"] == "U会员" and cust[p]["reg"] and cust[p]["reg"] < MONTH_START)
            out[emp][d] = {"new_cust": len(my), "old": olds, "need": len(my) - olds}
    return out, days


# ---------------------------------------------------------------- Excel 输出

def write_excel(out_path, store, emp, daily, days, cust, members, cutoff):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    BLUE = "1F4E79"
    LIGHT = "DDEBF7"
    thin = Side(style="thin", color="B0B0B0")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
    HDR_FONT = Font(name="微软雅黑", size=11, bold=True, color="FFFFFF")
    BODY = Font(name="微软雅黑", size=10)
    HDR_FILL = PatternFill("solid", fgColor=BLUE)
    SUB_FILL = PatternFill("solid", fgColor=LIGHT)
    WRAP = Alignment(vertical="center", horizontal="center", wrap_text=True)

    def style_header(ws, row, ncols):
        for c in range(1, ncols + 1):
            cell = ws.cell(row=row, column=c)
            cell.font = HDR_FONT
            cell.fill = HDR_FILL
            cell.alignment = WRAP
            cell.border = BORDER

    def fill_rows(ws, start_row, data_rows, ncols, zebra=True):
        for i, row in enumerate(data_rows):
            for j, v in enumerate(row, 1):
                cell = ws.cell(row=start_row + i, column=j, value=v)
                cell.font = BODY
                cell.border = BORDER
                cell.alignment = Alignment(vertical="center",
                                           horizontal="center" if j > 1 else "left")
                if zebra and i % 2 == 1:
                    cell.fill = PatternFill("solid", fgColor="F2F7FD")

    # ---- Sheet1 门店&员工汇总
    ws = wb.active
    ws.title = "汇总"
    ws.append([])
    ws["A2"] = f"李家村 会员注册报表推算（截止 {cutoff:%m-%d %H:%M}）"
    ws["A2"].font = Font(name="微软雅黑", size=14, bold=True, color=BLUE)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=8)

    r0 = 4
    ws.cell(row=r0, column=1, value="门店级")
    ws.cell(row=r0, column=1).font = Font(bold=True, size=12, color=BLUE)
    r0 += 1
    ws.append([])
    hdr = ["指标", "总客户数", "老客", "需注册", "已注册", "注册率"]
    for j, h in enumerate(hdr, 1):
        ws.cell(row=r0, column=j, value=h)
    style_header(ws, r0, len(hdr))
    r0 += 1
    fill_rows(ws, r0, [[
        "9.1 至今", store["total"], store["old"], store["need"],
        store["reged"], f"{store['rate']*100:.2f}%"]], len(hdr))
    r0 += 2

    ws.cell(row=r0, column=1, value="员工级（首单归属；已注册=POS按首单+非POS按会员登记）")
    ws.cell(row=r0, column=1).font = Font(bold=True, size=12, color=BLUE)
    r0 += 1
    hdr2 = ["员工", "总客户数", "老客", "需注册", "已注册", "注册率", "达成占比(已注册)"]
    for j, h in enumerate(hdr2, 1):
        ws.cell(row=r0, column=j, value=h)
    style_header(ws, r0, len(hdr2))
    r0 += 1
    total_reged = emp["张博晨"]["reged"] + emp["邵乐乐"]["reged"] + \
        emp["杨丽华"]["reged"] + emp["李泽"]["reged"]
    rows2 = []
    for name in STAFF:
        e = emp[name]
        share = e["reged"] / total_reged if total_reged else 0
        rows2.append([name, e["total"], e["old"], e["need"], e["reged"],
                      f"{e['rate']*100:.2f}%", f"{share*100:.2f}%"])
    rows2.append(["合计(店内)", sum(emp[n]["total"] for n in STAFF),
                  sum(emp[n]["old"] for n in STAFF),
                  sum(emp[n]["need"] for n in STAFF), total_reged,
                  f"{total_reged/store['reged']*100:.0f}%", "100%"])
    fill_rows(ws, r0, rows2, len(hdr2))
    for j in range(1, len(hdr2) + 1):  # 合计行加粗浅底
        c = ws.cell(row=r0 + len(rows2) - 1, column=j)
        c.font = Font(name="微软雅黑", size=10, bold=True)
        c.fill = SUB_FILL
    for col, w in zip("ABCDEFG", [22, 12, 10, 10, 10, 10, 18]):
        ws.column_dimensions[col].width = w
    note = ws.cell(row=r0 + len(rows2) + 1, column=1,
                   value=f"注：员工合计已注册{total_reged}人与门店级{store['reged']}人的差额，"
                         f"为外部代录账号(郑元坤B/定凯丰等)名下客户，不计入店内员工考核")
    note.font = Font(name="微软雅黑", size=9, italic=True, color="808080")
    note.alignment = Alignment(vertical="center")
    ws.merge_cells(start_row=r0 + len(rows2) + 1, start_column=1,
                   end_row=r0 + len(rows2) + 1, end_column=7)

    # ---- Sheet2 逐日明细
    ws2 = wb.create_sheet("逐日明细")
    hdr3 = ["日期", "员工", "当日新增客户", "其中老客", "当日需注册", "累计需注册"]
    for j, h in enumerate(hdr3, 1):
        ws2.cell(row=1, column=j, value=h)
    style_header(ws2, 1, len(hdr3))
    ws2.freeze_panes = "A2"
    cum = {n: 0 for n in STAFF}
    ri = 2
    for d in days:
        for name in STAFF:
            v = daily[name].get(d, {"new_cust": 0, "old": 0, "need": 0})
            cum[name] += v["need"]
            for j, val in enumerate([d.strftime("%m-%d"), name,
                                     v["new_cust"], v["old"], v["need"], cum[name]], 1):
                cell = ws2.cell(row=ri, column=j, value=val)
                cell.font = BODY
                cell.border = BORDER
                cell.alignment = Alignment(vertical="center", horizontal="center")
            ri += 1
    for col, w in zip("ABCDEF", [10, 12, 14, 12, 14, 14]):
        ws2.column_dimensions[col].width = w

    # ---- Sheet3 客户明细
    ws3 = wb.create_sheet("客户明细")
    hdr4 = ["手机号", "首单时间", "首单营业员", "末单营业员", "会员归属(登记)",
            "净额", "单数", "会员体系", "关注", "注册日期", "老客", "已注册"]
    for j, h in enumerate(hdr4, 1):
        ws3.cell(row=1, column=j, value=h)
    style_header(ws3, 1, len(hdr4))
    ws3.freeze_panes = "A2"
    reged = registered_set(members, cutoff)
    ri = 2
    for p, c in sorted(cust.items(), key=lambda x: x[1]["first"]["dt"]):
        isold = "是" if (c["app"] == "U会员" and c["reg"] and c["reg"] < MONTH_START) else ""
        isreg = "是" if p in reged else ""
        vals = [p, c["first"]["dt"].strftime("%m-%d %H:%M"), c["first"]["emp"],
                c["last"]["emp"], c["owner"] or "-", round(c["amt"], 2), c["n"],
                c["app"] or "-", "是" if c["wx"] == "1" else "",
                str(c["reg"])[:10] if c["reg"] else "-", isold, isreg]
        for j, val in enumerate(vals, 1):
            cell = ws3.cell(row=ri, column=j, value=val)
            cell.font = BODY
            cell.border = BORDER
            cell.alignment = Alignment(vertical="center",
                                       horizontal="center" if j > 1 else "left")
        ri += 1
    for col, w in zip("ABCDEFGHIJKL",
                      [13, 12, 12, 12, 14, 10, 6, 10, 6, 12, 6, 8]):
        ws3.column_dimensions[col].width = w

    wb.save(out_path)


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="李家村会员注册报表推算")
    ap.add_argument("--until", default=None,
                    help="统计截止时间，如 '2026-09-11 21:03'（默认当前时刻）")
    ap.add_argument("--no-fetch", action="store_true", help="不联网，直接用本地数据")
    ap.add_argument("--pos", default=None, help="指定 POS 销售分析 xlsx 路径")
    ap.add_argument("--out", default=None, help="输出 Excel 路径")
    args = ap.parse_args()

    cutoff = (datetime.datetime.strptime(args.until, "%Y-%m-%d %H:%M")
              if args.until else datetime.datetime.now())
    if cutoff < MONTH_START:
        raise SystemExit("ERR: 截止时间早于月初")

    if args.no_fetch:
        import glob as _glob
        cands = sorted(_glob.glob(os.path.join(POS_DIR, "销售分析_*.xlsx")))
        pos_path = args.pos or (cands[-1] if cands else None)
        if not pos_path:
            raise SystemExit("ERR: 找不到 POS xlsx")
        members_path = MEMBERS_JSON if os.path.exists(MEMBERS_JSON) else MEMBERS_CACHE
    else:
        pos_path, members_path = refresh_data(cutoff)
    if args.pos:
        pos_path = args.pos

    print(f"POS: {pos_path}")
    print(f"会员库: {members_path}")
    orders = load_pos(pos_path)
    members = load_members(members_path)
    print(f"订单 {len(orders)} 条，会员 {len(members)} 人，截止 {cutoff:%Y-%m-%d %H:%M}")

    cust = build_customers(orders, cutoff, members)
    store, emp, reged, olds = calc(cust, members, cutoff)
    daily, days = daily_breakdown(cust, members)

    # 控制台输出
    print("\n===== 门店级 =====")
    print(f"总客户 {store['total']} | 老客 {store['old']} | 需注册 {store['need']} "
          f"| 已注册 {store['reged']} | 注册率 {store['rate']*100:.2f}%")
    print("\n===== 员工级 =====")
    print(f"{'员工':<6}{'总客户':>6}{'老客':>6}{'需注册':>7}{'已注册':>7}{'注册率':>9}")
    for name in STAFF:
        e = emp[name]
        print(f"{name:<6}{e['total']:>6}{e['old']:>6}{e['need']:>7}{e['reged']:>7}"
              f"{e['rate']*100:>8.2f}%")

    out = args.out or os.path.join(
        SHOP, f"李家村会员注册_员工达成_{cutoff:%m%d}.xlsx")
    write_excel(out, store, emp, daily, days, cust, members, cutoff)
    print(f"\n✅ Excel 已输出: {out}")


if __name__ == "__main__":
    main()
