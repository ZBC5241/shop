#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
李家村门店业绩看板 —— 明细复算引擎
直接从用友云导出的销售明细复现《李家村销售》表的全部 SUMIFS 口径，生成 data.json。

为什么要复算？
    表格里的指标全是 SUMIFS 公式。脚本写完 XS/RXS 明细后，公式的「缓存值」
    要等 WPS/Excel 打开才会刷新。看板不能等人开表格，所以这里按同一套口径
    自己算一遍，做到「抓完数 → 看板立刻是新的」。

口径来源：逐格导出《李家村销售》表的真实公式，1:1 复现，不做任何自创逻辑。
    · 任务量  → 读「8月任务」表常量（纯手工填写，不受公式缓存影响）
    · 完成量  → 由明细复算
    · 手工项  → 乐机收(常量) / 太力回收(独立表) / 绩效(个人表) 直接读，它们不依赖明细

用法：
    python calc_data.py <明细文件> [--xlsx 路径] [--day YYYY-MM-DD] [-o data.json]
    明细文件支持 .tsv 和 .xlsx（导出按钮直接导出的原始数据xlsx，跳过TSV中转）
"""
import sys, os, re, json, csv, datetime, argparse, calendar
import openpyxl

# ---------- 明细列（与用友云导出、XS/RXS 完全一致的 19 列） ----------
# Excel 列字母 -> 0-based 下标
C = {c: i for i, c in enumerate("ABCDEFGHIJKLMNOPQRS")}
HEADERS = ["出库单号", "单据类型", "出库日期", "商品分类", "商品sku分类", "商品SKU编码",
           "商品名称", "入库属性", "数量", "单价", "原价", "折扣价", "金额", "毛利",
           "SO激励", "业务员", "库区", "销售出库单门店", "销售成本"]

# 人员名单（动态，由 load_people() 从底表「月任务」sheet B4:B7 读取）
PEOPLE_ORDER = []       # 全员（含张博晨，末尾追加）
TASK_PEOPLE = []        # 有任务的人员（不含张博晨）
TASK_ROW = {}           # {name: 月任务表行号}

# 9月任务表列：C=销售额 D=毛利 E=手机 F=增值 G=合约 H=PC I=平板 J=音频 K=穿戴 L=HD M=摄影课程 N=考核机
TASK_COL = {"销额": 3, "毛利": 4, "手机": 5, "增值": 6, "合约": 7,
            "PC": 8, "平板": 9, "音频": 10, "穿戴": 11, "HD": 12,
            "摄影课": 13, "考核机型": 14}

# 考核机型 SKU 前缀（李家村销售!S14 数组公式原样搬运）
KHJX_SKU = ["01.001.010.00*", "01.001.011.002*", "01.001.012.00*", "01.001.013.0*",
            "01.001.031.002*", "01.001.032.002*", "01.001.043.002*", "01.001.044.002*",
            "01.001.001.0*", "01.001.002.0*", "01.001.003*"]
# care+ 里计入的星联优享档位（G14 数组公式原样搬运）
XLYX = ["星联优享-499", "星联优享-699", "星联优享-999"]


# ============================ 基础工具 ============================
def num(v):
    """明细里的数字：带千分位、可能为空。"""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("¥", "").replace("￥", "")
    if not s or s.startswith("#"):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def wild(text, pat):
    """Excel 通配符匹配：* 任意长度，? 单字符，整体锚定，不区分大小写。"""
    rx = "".join(".*" if ch == "*" else "." if ch == "?" else re.escape(ch) for ch in pat)
    return re.fullmatch(rx, text, re.IGNORECASE) is not None


def hit(cell, cond):
    """复现 SUMIFS 单个条件。cond 支持 '>0' 这类比较式，和带通配符的文本。"""
    if isinstance(cond, (int, float)):
        return num(cell) == float(cond)
    cond = str(cond)
    m = re.fullmatch(r"(>=|<=|<>|>|<|=)\s*(-?[\d.]+)", cond)
    if m:
        op, rhs = m.group(1), float(m.group(2))
        x = num(cell)
        return {">": x > rhs, "<": x < rhs, ">=": x >= rhs,
                "<=": x <= rhs, "=": x == rhs, "<>": x != rhs}[op]
    s = "" if cell is None else str(cell).strip()
    if any(ch in cond for ch in "*?"):
        return wild(s, cond)
    return s.lower() == cond.strip().lower()


def sumifs(rows, sum_col, *conds):
    """SUMIFS(明细[sum_col], 条件对...)。conds 形如 ('P','邵乐乐'), ('D','01手机')"""
    total = 0.0
    for r in rows:
        if all(hit(r[C[col]], cond) for col, cond in conds):
            total += num(r[C[sum_col]])
    return total


def sumifs_any(rows, sum_col, base_conds, col, patterns):
    """数组常量版：SUM(SUMIFS(..., {p1,p2,...}))。同一行命中多个模式会重复计入（与 Excel 一致）。"""
    total = 0.0
    for p in patterns:
        total += sumifs(rows, sum_col, *base_conds, (col, p))
    return total


def roundup(x, digits=0):
    """Excel ROUNDUP：远离 0 取整。"""
    import math
    f = 10 ** digits
    return math.ceil(x * f) / f if x >= 0 else math.floor(x * f) / f


def div(a, b):
    """除法，分母为 0 返回 None（对应表格里的 #DIV/0!）。"""
    try:
        return a / b if b else None
    except (TypeError, ZeroDivisionError):
        return None


# ============================ 读明细 ============================
def load_tsv(path):
    # 兼容用友导出的 GBK/UTF-8 混合文件：先按 utf-8-sig 读，失败再回退 gbk
    raw = open(path, "rb").read()
    try:
        txt = raw.decode("utf-8-sig")
    except Exception:
        txt = raw.decode("gbk", "replace")
    rd = list(csv.reader(txt.splitlines(), delimiter="\t"))
    if not rd:
        sys.exit("❌ 明细文件是空的")
    head = [h.strip() for h in rd[0]]
    if head[:len(HEADERS)] != HEADERS:
        # 兼容16列TSV（浏览器提取缺库区/门店/销售成本）：表头前16列匹配即可
        if head[:16] == HEADERS[:16]:
            print("  [提示] 检测到16列TSV（浏览器提取版），自动补3空列→19列")
            head = head + HEADERS[16:]
            for i in range(1, len(rd)):
                if len(rd[i]) < 19:
                    rd[i] = rd[i] + [""] * (19 - len(rd[i]))
        else:
            sys.exit(f"❌ 明细表头与预期不符\n  期望: {HEADERS}\n  实际: {head}")
    rows = [r + [""] * (len(HEADERS) - len(r)) for r in rd[1:] if any(x.strip() for x in r)]
    return rows


def load_xlsx(path):
    """直接读取用友云导出按钮导出的原始数据xlsx，跳过TSV中转。
    xlsx结构：第1行表头，第2行起数据，A-S共19列（与HEADERS完全一致）。
    含空行和重复行，需过滤去重（出库单号+SKU编码）。
    """
    import warnings
    warnings.filterwarnings("ignore", message="Workbook contains no default style")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    all_rows = list(ws.iter_rows(min_row=1, max_row=ws.max_row, values_only=True))
    if not all_rows:
        sys.exit("❌ xlsx明细文件是空的")
    head = [str(h).strip() if h is not None else "" for h in all_rows[0]]
    if head[:len(HEADERS)] != HEADERS:
        sys.exit(f"❌ xlsx表头与预期不符\n  期望: {HEADERS}\n  实际: {head[:19]}")
    # 过滤空行 + 去重（出库单号+SKU编码），所有值统一转字符串（与TSV行为一致）
    seen = set()
    rows = []
    for r in all_rows[1:]:
        if not r[0] or not str(r[0]).strip():
            continue  # 跳过空行
        cells = []
        for i, c in enumerate(r[:19]):
            if c is None:
                cells.append("")
            elif isinstance(c, datetime.datetime):
                cells.append(c.strftime("%Y-%m-%d"))
            else:
                cells.append(str(c))
        key = (cells[0].strip(), cells[5].strip())  # 出库单号 + SKU编码
        if key in seen:
            continue  # 跳过重复行
        seen.add(key)
        rows.append(cells)
    return rows


def load_detail(path):
    """统一入口：根据文件扩展名自动选择TSV或xlsx读取方式。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        print(f"  [模式] 直读xlsx（跳过TSV中转）")
        return load_xlsx(path)
    else:
        return load_tsv(path)


def day_of(r):
    v = r[C["C"]]
    if isinstance(v, datetime.datetime):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()[:10]


# ============================ 动态读取人员名单 ============================
def load_people(xlsx):
    """从底表「月任务」sheet B4:B7 动态读取人员名单（空名跳过）。
    张博晨固定追加（不背任务）。设置模块级 PEOPLE_ORDER / TASK_PEOPLE / TASK_ROW。
    """
    global PEOPLE_ORDER, TASK_PEOPLE, TASK_ROW
    wbf = openpyxl.load_workbook(xlsx, data_only=False)
    tk = wbf[[s for s in wbf.sheetnames if s.endswith("月任务") or s.endswith("度任务")][0]]
    task_people, task_row = [], {}
    for r in range(4, 8):                   # B4~B7
        nm = tk.cell(r, 2).value             # B 列 = 姓名
        if nm and str(nm).strip():
            nm = str(nm).strip()
            # 底表「合计」行是汇总值（已并入 store.qcs 顶层），不当人员 tab
            if nm == "合计":
                continue
            task_people.append(nm)
            task_row[nm] = r
    PEOPLE_ORDER = task_people + ["张博晨"]
    TASK_PEOPLE = task_people
    TASK_ROW = task_row


# ============================ 读表格里的手工项 ============================
def load_manual(xlsx):
    """任务量、乐机收、太力回收、绩效——这几样不来自明细，从表格取。"""
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    wbf = openpyxl.load_workbook(xlsx, data_only=False)

    # --- 任务量：8月任务表，纯常量 ---
    tk = wbf[[s for s in wbf.sheetnames if s.endswith("月任务") or s.endswith("度任务")][0]]
    tasks = {}
    for name, row in TASK_ROW.items():
        tasks[name] = {k: num(tk.cell(row, col).value) for k, col in TASK_COL.items()}
    tasks["张博晨"] = {k: 0.0 for k in TASK_COL}          # 张博晨不背任务

    # --- 乐机收（底表 2026-09 已从"乐回收"改名，T12 标题以底表为准，本脚本不写标题）：
    #     李家村销售 T/U 列固定单元格常量（数据持久化由 xlsx 文件承担）
    #     行号动态映射：月任务行号 + 10，张博晨固定 18（人员变动只改底表）
    #     T13=单量, U13=增值；T19/U19 是 SUM 公式（不必动），自动求和
    ws = wbf["李家村销售"]
    P2_ROWS = {n: r + 10 for n, r in TASK_ROW.items()}
    P2_ROWS["张博晨"] = 18
    lehui = {}
    for name, row in P2_ROWS.items():
        lehui[name] = {"orders": num(ws.cell(row, 20).value),    # T 单量
                       "amount": num(ws.cell(row, 21).value),    # U 增值（公司净利）
                       "增值":   num(ws.cell(row, 22).value)}    # V 增值率（备用，可空）

    # --- 太力回收：独立表，按业务员汇总（不依赖明细，实时算） ---
    tl = wb["太力回收"]
    taili = {n: {"orders": 0.0, "amount": 0.0} for n in PEOPLE_ORDER}
    for r in range(2, tl.max_row + 1):
        state = str(tl.cell(r, 10).value or "").strip()       # J 回收单状态
        who = str(tl.cell(r, 22).value or "").strip()         # V 销售员姓名
        if who in taili:
            if state == "已付款":
                taili[who]["orders"] += num(tl.cell(r, 28).value)   # AB 数量（W14 公式：SUMIFS(AB,V,姓名,J,"已付款")）
            taili[who]["amount"] += num(tl.cell(r, 29).value)       # AC 回收价（X14 公式：SUMIF(V,姓名,AC)，不筛状态）
    for n in taili:
        taili[n]["增值"] = taili[n]["amount"] * 0.14

    # --- 绩效：各人表 L18（=SUM(L4:L17)，与明细无关） ---
    # 注意：原表《李家村销售》AP 列引用错位（邵乐乐行→杨丽华表、杨丽华行→李泽表…），
    #       且邵乐乐表 L 列公式为 #REF!。这里按「每人读自己的表」的正确逻辑取值，
    #       取不到就给 None（看板显示「—」），不拿别人的数顶替。
    perf = {}
    for n in PEOPLE_ORDER:
        if n not in wb.sheetnames:
            perf[n] = None
            continue
        v = wb[n].cell(18, 12).value
        if v is None or (isinstance(v, str) and (v.strip() == "" or v.startswith("#"))):
            perf[n] = None                       # #REF! / 空 —— 数据坏了，如实标记
        else:
            perf[n] = num(v)

    # --- 兜底：底表带 fullCalcOnLoad="1"，openpyxl 读不到公式缓存值（L18 恒为 None）。
    #     此时按底表公式原样精算（perf_score.py），口径与个人表逐项对齐、不臆造。
    if any(v is None for v in perf.values()):
        try:
            from perf_score import compute_perf
            alt = compute_perf(xlsx)
            fixed = []
            for n in perf:
                if perf[n] is None and alt.get(n) is not None:
                    perf[n] = alt[n]
                    fixed.append(n)
            if fixed:
                print("   ↳ 绩效按底表公式重算: " + "、".join(
                    "%s=%.2f" % (n, perf[n]) for n in fixed))
        except Exception as e:
            print("   ⚠️ 绩效公式重算失败（看板该卡将空缺）:", e)

    # --- 表头标签（静态文本） ---
    lab_day = [ws.cell(26, c).value for c in range(2, 16)]
    lab_gap = [ws.cell(36, c).value for c in range(2, 16)]
    # 晨哥口径：底表「今日达成/每日任务」部分标签仍写「电信积分」，
    # 但 9 月新底表已改按「合约」考核（当日达成 K28=SUMIFS(RXS!M,E:*入网*)=入网积分，
    # 每日任务 K38 引用 $D14=合约缺口单数）。代码层统一映射为「合约」（不碰桌面真表）。
    lab_day = [('合约' if (c and '电信积分' in str(c)) else c) for c in lab_day]
    lab_gap = [('合约' if (c and '电信积分' in str(c)) else c) for c in lab_gap]
    return tasks, lehui, taili, perf, lab_day, lab_gap


# ============================ 复算：业绩考核 ============================
def calc_perf(xs, name, task):
    P = ("P", name)
    毛利 = sumifs(xs, "N", P)
    手机 = sumifs(xs, "I", P, ("D", "01手机"))
    PC = sumifs(xs, "I", P, ("D", "05电脑"))
    平板 = sumifs(xs, "I", P, ("D", "06平板电脑"))
    穿戴 = sumifs(xs, "I", P, ("D", "08穿戴"))
    音频 = sumifs(xs, "I", P, ("D", "07音频"))
    HD = sumifs(xs, "I", P, ("F", "12*"))
    销额 = sumifs(xs, "M", P)

    def blk(t, d, on_zero=None):
        # on_zero：任务为 0 时的完成率。HD 列公式是 IFERROR(...,"100%")，照搬。
        return {"task": t, "done": d, "gap": d - t,
                "rate": div(d, t) if t else on_zero}

    return {
        "毛利":     blk(task["毛利"], 毛利),
        "手机":     blk(task["手机"], 手机),
        "PC":       blk(task["PC"], PC),
        "平板":     blk(task["平板"], 平板),
        "穿戴":     blk(task["穿戴"], 穿戴),
        "音频":     blk(task["音频"], 音频),
        "HD":       blk(task["HD"], HD, on_zero=1.0),
        "智慧办公": blk(task["PC"] + task["平板"], PC + 平板),
        "音频穿戴": blk(task["穿戴"] + task["音频"], 穿戴 + 音频),
        "销额":     blk(task["销额"], 销额),
    }


# ============================ 复算：品类销售明细（点击展开用）============================
# 复用 calc_perf 的归类口径，把每一行出库明细归入对应品类，供前端「品类达成」点击下钻。
DET_CATS = {
    "手机":     lambda r: r[C["D"]] == "01手机",
    "PC":       lambda r: r[C["D"]] == "05电脑",
    "平板":     lambda r: r[C["D"]] == "06平板电脑",
    "穿戴":     lambda r: r[C["D"]] == "08穿戴",
    "音频":     lambda r: r[C["D"]] == "07音频",
    "HD":       lambda r: (r[C["F"]] or "").startswith("12"),
    "智慧办公": lambda r: r[C["D"]] in ("05电脑", "06平板电脑"),
    "音频穿戴": lambda r: r[C["D"]] in ("08穿戴", "07音频"),
    "增值":     lambda r: "增值" in (r[C["D"]] or ""),
}

def row_detail(r):
    amt = num(r[C["M"]])   # 金额
    pf  = num(r[C["N"]])   # 毛利
    gpr = round(pf / amt, 4) if amt else None   # 毛利率 = 毛利 / 金额
    return {
        "date":      r[C["C"]],
        "name":      r[C["G"]],
        "qty":       num(r[C["I"]]),
        "origPrice": num(r[C["K"]]),   # 原价
        "discPrice": num(r[C["L"]]),   # 折扣价
        "amount":    amt,
        "profit":    pf,
        "gpr":       gpr,              # 毛利率（自算）
        "so":        (r[C["O"]] or "").strip(),  # SO激励
        "cost":      num(r[C["S"]]),   # 销售成本
        "emp":       r[C["P"]],
        "sku":       r[C["F"]],
    }

def build_details(xs):
    out = {}
    for cat, cond in DET_CATS.items():
        rows = [row_detail(r) for r in xs if cond(r)]
        rows.sort(key=lambda x: (x["date"] or ""), reverse=True)
        out[cat] = rows
    return out


# ============================ 复算：全科生 / 增值 ============================
def calc_qcs(xs, name, task, perf, lehui, taili):
    P = ("P", name)
    手机 = perf["手机"]["done"]
    智慧办公 = perf["智慧办公"]["done"]
    穿戴 = perf["穿戴"]["done"]
    毛利 = perf["毛利"]["done"]
    销额 = perf["销额"]["done"]

    # 合约单数（新口径 2026-09-08，照搬底表 C14 公式）：
    #   C14 = SUMIFS(XS!$I:$I, XS!$P:$P, 姓名, XS!$E:$E, "合约入网")
    #   按「商品sku分类=合约入网」对数量列求和（取代旧「单卡新入网且金额>0」口径）。
    合约单数 = int(round(sumifs(xs, "I", P, ("E", "合约入网"))))
    合约任务 = task["合约"]

    # 会员搭售（care+）
    care = sumifs(xs, "I", P, ("G", "*Care*"), ("N", ">0")) + \
           sumifs_any(xs, "I", [P], "G", XLYX)
    care_gap = care - roundup(手机 * 0.30)

    # 回收搭售
    回收 = sumifs(xs, "I", P, ("G", "*回收*")) + taili[name]["orders"] + lehui[name]["orders"]
    回收_gap = 回收 - roundup(手机 * 0.20)

    # 贴膜
    贴膜 = sumifs(xs, "I", P, ("G", "*膜*"), ("N", ">0")) + sumifs(xs, "I", P, ("G", "*贴膜套包"))
    贴膜基数 = 手机 + 智慧办公 + 穿戴
    贴膜_gap = 贴膜 - roundup(贴膜基数 * 0.50)

    # 考核机型：完成 = 各 SKU 前缀命中之和；表格里 S 列存的是「缺口 = 完成 - 任务」
    考核完成 = sumifs_any(xs, "I", [P], "F", KHJX_SKU)
    考核任务 = task["考核机型"]

    # 增值（新口径 2026-09-08，照搬底表 AA14 公式）：
    #   AA14 = SUM(SUMIFS(XS!$N:$N, 姓名, D={"*增值*","*运营商业*"})) + Y14(太力增值) + U14(乐机收)
    #   运营商业务毛利直接计入增值，「电信积分×4」已从底表移除。
    增值完成 = sumifs_any(xs, "N", [P], "D", ["*增值*", "*运营商业*"]) + taili[name]["增值"] + lehui[name]["amount"]
    增值任务 = task["增值"]

    # 健康度
    优惠券 = sumifs(xs, "L", P)

    # 星联会员
    优享 = sumifs(xs, "I", P, ("G", "*会员*")) + sumifs(xs, "I", P, ("G", "星联优享*"))
    尊享 = sumifs(xs, "I", P, ("G", "*储值*")) + sumifs(xs, "I", P, ("G", "星联尊享*"))

    return {
        "合约":       {"task": 合约任务, "done": 合约单数,
                     "gap": 合约单数 - 合约任务, "rate": div(合约单数, 合约任务)},
        "会员搭售率": {"terminal": 手机, "care": care, "gap": care_gap, "rate": div(care, 手机)},
        "回收搭售率": {"orders": 回收, "gap": 回收_gap, "rate": div(回收, 手机)},
        "贴膜率":     {"orders": 贴膜, "gap": 贴膜_gap, "rate": div(贴膜, 贴膜基数)},
        "考核机型":   {"task": 考核任务, "done": 考核完成, "gap": 考核完成 - 考核任务},
        "乐机收":     dict(lehui[name]),
        "太力回收":   {"orders": taili[name]["orders"], "amount": taili[name]["amount"],
                     "增值": taili[name]["增值"]},
        "增值":       {"task": 增值任务, "done": 增值完成,
                     "gap": 增值完成 - 增值任务, "rate": div(增值完成, 增值任务)},
        "健康度":     {"coupon": 优惠券, "ratio": div(优惠券, 毛利),
                     "grossMargin": div(毛利, 销额), "增值率": div(增值完成, 销额)},
        "星联会员":   {"优享": 优享, "尊享": 尊享, "合计": 优享 + 尊享},
    }


# ============================ 复算：当日达成 ============================
def calc_daily(rxs, name, labels):
    P = ("P", name)
    # 严格对齐《李家村销售》sheet「今日达成」区块(行28-33)的 SUMIFS 公式：
    #   增值=毛利列且(分类∈{*增值*,*运营商*})；会员=Care+会员+星联优享*；
    #   贴膜=*膜*&毛利>0+贴膜套包+会员；摄影课=*大师课*&毛利>0；滞销=KHJX_SKU数组
    v = {
        "手机":     sumifs(rxs, "I", P, ("F", "01.001*")),
        "毛利":     sumifs(rxs, "N", P),
        "增值":     sumifs(rxs, "N", P, ("D", "*增值*")) + sumifs(rxs, "N", P, ("D", "*运营商*")),
        "智慧办公": sumifs(rxs, "I", P, ("F", "05.001*")) + sumifs(rxs, "I", P, ("F", "06.001*")),
        "音频穿戴": sumifs(rxs, "I", P, ("F", "08.001*")) + sumifs(rxs, "I", P, ("F", "07.001*")),
        "HD":       sumifs(rxs, "I", P, ("F", "12*")),
        "会员":     sumifs(rxs, "I", P, ("G", "*Care*")) + sumifs(rxs, "I", P, ("G", "*会员*")) + sumifs(rxs, "I", P, ("G", "星联优享*")),
        "回收":     sumifs(rxs, "I", P, ("G", "*回收*")),
        "贴膜":     sumifs(rxs, "I", P, ("G", "*膜*"), ("N", ">0")) + sumifs(rxs, "I", P, ("G", "*贴膜套包")) + sumifs(rxs, "I", P, ("G", "*会员*")),
        # 当日合约：底表 K28=SUMIFS(RXS!M,E:*入网*) 计「积分」（99/单），
        # 但月度 C14/每日任务 K38 均为「单数」口径；为与任务侧单数对齐，按 C14 公式结构对当日明细计数
        "合约":     int(round(sumifs(rxs, "I", P, ("E", "合约入网")))),
        "滞销":     sumifs_any(rxs, "I", [P], "F", KHJX_SKU),
        "摄影课":   sumifs(rxs, "I", P, ("G", "*大师课*"), ("N", ">0")),
        "优享/会员": sumifs(rxs, "I", P, ("G", "*新自由*")) + sumifs(rxs, "I", P, ("G", "星联优享*")),
    }
    # 严格按表格「今日达成」品类标签(B26:N26)输出（含原被误排除的「摄影课」）
    out = {k: v.get(k, 0.0) for k in labels if k}
    out["销额"] = sumifs(rxs, "M", P)   # 表格「今日达成」无销额行，但日报总览/板块依赖，保留
    return out


# ============================ 复算：每日缺口 ============================
def remain_days(base):
    """剩余天数 = 月底 - 当日 + 1（包含今天），按自然月算，不扣休假。"""
    last = calendar.monthrange(base.year, base.month)[1]
    return last - base.day + 1


def calc_gap(perf, qcs, rd, labels):
    """每日缺口 = ROUNDUP(|该项缺口| / 剩余工作天数)。
    与底表「每日任务」行38-41公式一致，覆盖14品类。
    底表 D4=C4-B4（完成-任务），未完成时为负数，每日任务=ROUNDUP(负数/天数)。
    openpyxl 对负数 ROUNDUP 是向上取整（往0靠），Python 用 math.ceil 对负数也往0靠。
    我们取绝对值再除：每日任务 = ROUNDUP(|缺口|/天数)。"""
    src = {
        "手机":      perf["手机"]["gap"],
        "毛利":      perf["毛利"]["gap"],
        "增值":      qcs["增值"]["gap"],
        "智慧办公":  perf["智慧办公"]["gap"],
        "音频穿戴":  perf["音频穿戴"]["gap"],
        "HD":        perf["HD"]["gap"],
        "Care+":     qcs["会员搭售率"]["gap"],
        "回收":      qcs["回收搭售率"]["gap"],
        "贴膜":      qcs["贴膜率"]["gap"],
        "合约":      qcs["合约"]["gap"],
        "滞销":      qcs["考核机型"]["gap"],
        "摄影课":     0,   # 底表引用 Q14 = SUMIFS大师课，缺口动态；暂设0
        "优享/会员":  0,   # 底表 N38=1（固定值）
        "尊享/储值":  0,   # 底表 O38=1（固定值）
    }
    out = {}
    for k in labels:
        if not k:
            continue
        if k in ("优享/会员", "尊享/储值"):
            out[k] = 1  # 固定每日1单
        elif k in src:
            gap = src[k]
            # gap < 0 = 未完成（还差 |gap|），gap > 0 = 已超额（今日任务0）
            need = abs(gap) if gap < 0 else 0
            if need > 0:
                out[k] = roundup(need / rd)
            else:
                out[k] = 0
    return out


# ============================ 汇总 ============================
def total_perf(people):
    ref = people[PEOPLE_ORDER[0]]["performance"]
    keys = [k for k, v in ref.items() if isinstance(v, dict)]   # 绩效是标量，单独汇总
    out = {}
    for k in keys:
        t = sum(people[n]["performance"][k]["task"] for n in PEOPLE_ORDER)
        d = sum(people[n]["performance"][k]["done"] for n in PEOPLE_ORDER)
        out[k] = {"task": t, "done": d, "gap": d - t, "rate": div(d, t)}
    return out


def total_qcs(people, sp):
    S = lambda k, f: sum(people[n]["qcs"][k][f] for n in PEOPLE_ORDER)
    手机, 智慧办公, 穿戴 = sp["手机"]["done"], sp["智慧办公"]["done"], sp["穿戴"]["done"]
    毛利, 销额 = sp["毛利"]["done"], sp["销额"]["done"]
    care, 回收, 贴膜 = S("会员搭售率", "care"), S("回收搭售率", "orders"), S("贴膜率", "orders")
    贴膜基数 = 手机 + 智慧办公 + 穿戴
    jf_t, jf_d = S("合约", "task"), S("合约", "done")
    kh_t, kh_d = S("考核机型", "task"), S("考核机型", "done")
    zz_t, zz_d = S("增值", "task"), S("增值", "done")
    优惠券 = S("健康度", "coupon")
    # 合计行的三个「缺口」不是各人相加，而是拿合计量重算（表格 H19/K19/N19 原样搬运）：
    #   care  = G19 - ROUNDUP(F19*30%)   回收 = J19 - ROUNDUP(G9*20%)
    #   贴膜  = M19 - ROUNDUP(G9*50%)    ← 合计行基数只取手机，与个人行口径不同
    return {
        "合约":       {"task": jf_t, "done": jf_d, "gap": jf_d - jf_t, "rate": div(jf_d, jf_t)},
        "会员搭售率": {"terminal": 手机, "care": care,
                     "gap": care - roundup(手机 * 0.30), "rate": div(care, 手机)},
        "回收搭售率": {"orders": 回收, "gap": 回收 - roundup(手机 * 0.20), "rate": div(回收, 手机)},
        "贴膜率":     {"orders": 贴膜, "gap": 贴膜 - roundup(手机 * 0.50), "rate": div(贴膜, 贴膜基数)},
        "考核机型":   {"task": kh_t, "done": kh_d, "gap": kh_d - kh_t},
        "乐机收":     {f: S("乐机收", f) for f in ("orders", "amount", "增值")},
        "太力回收":   {f: S("太力回收", f) for f in ("orders", "amount", "增值")},
        "增值":       {"task": zz_t, "done": zz_d, "gap": zz_d - zz_t, "rate": div(zz_d, zz_t)},
        "健康度":     {"coupon": 优惠券, "ratio": div(优惠券, 毛利),
                     "grossMargin": div(毛利, 销额), "增值率": div(zz_d, 销额)},
        "星联会员":   {f: S("星联会员", f) for f in ("优享", "尊享", "合计")},
    }


# ============================ 店长洞察 ============================
# 看板品类 → 明细筛选条件（用于算最后成交日 / 断销天数）
CAT_FILTER = {
    "手机":  ("D", "01手机"),
    "PC":    ("D", "05电脑"),
    "平板":  ("D", "06平板电脑"),
    "穿戴":  ("D", "08穿戴"),
    "音频":  ("D", "07音频"),
    "HD":    ("F", "12*"),
}
CAT_UNIT = {"手机": "台", "PC": "台", "平板": "台", "穿戴": "件", "音频": "件", "HD": "台"}
CAT_ALIAS = {"PC": "电脑", "HD": "HD 智慧屏"}


def last_sold(xs, cond, name=None):
    """某品类（可限定业务员）最后一次成交的日期。没卖过返回 None。"""
    col, pat = cond
    best = None
    for r in xs:
        if not hit(r[C[col]], pat):
            continue
        if name and r[C["P"]].strip() != name:
            continue
        if num(r[C["I"]]) <= 0:          # 只认正向出货，退货不算动销
            continue
        d = day_of(r)
        if best is None or d > best:
            best = d
    return best


def build_insights(xs, rxs, people, store, ref, tp, rd):
    """把明细 + 复算结果，翻译成店长看得懂的判断和建议。"""

    # ---------- 1. 品类体检 ----------
    cats = []
    for key, cond in CAT_FILTER.items():
        b = store["performance"].get(key) or {}
        task, done = b.get("task", 0), b.get("done", 0)
        rate = b.get("rate") or 0
        ld = last_sold(xs, cond)
        cold = (ref - datetime.date.fromisoformat(ld)).days if ld else None
        # 谁卖过这个品类
        sellers = {}
        for n in TASK_PEOPLE:
            v = people[n]["performance"].get(key, {}).get("done", 0)
            if v:
                sellers[n] = v
        if task <= 0:
            level = "none"
        elif done <= 0:
            level = "danger"                 # 整月零成交
        elif rate < tp * 0.5:
            level = "danger"                 # 进度不到时间的一半
        elif rate < tp * 0.85:
            level = "warn"
        elif rate >= tp:
            level = "good"
        else:
            level = "mid"
        cats.append({
            "key": key,
            "name": CAT_ALIAS.get(key, key),
            "unit": CAT_UNIT.get(key, ""),
            "task": task, "done": done, "rate": rate,
            "lag": rate - tp,
            "level": level,
            "lastDate": ld,
            "coldDays": cold,
            "needPerDay": roundup(max(0, task - done) / rd) if task else 0,
            "sellers": sellers,
            "zeroPeople": [n for n in TASK_PEOPLE
                           if people[n]["performance"].get(key, {}).get("task", 0) > 0
                           and not people[n]["performance"].get(key, {}).get("done", 0)],
        })
    cats.sort(key=lambda c: (c["level"] not in ("danger", "warn"), c["rate"]))

    # ---------- 2. 员工体检 ----------
    W = {"毛利": 0.5, "手机": 0.3}          # 综合分权重：毛利为主，手机为辅
    plist = []
    for n in TASK_PEOPLE:
        pp, pq = people[n]["performance"], people[n]["qcs"]
        r_gross = pp["毛利"].get("rate") or 0
        r_phone = pp["手机"].get("rate") or 0
        r_add = (pq.get("增值") or {}).get("rate") or 0
        score = r_gross * W["毛利"] + r_phone * W["手机"] + r_add * 0.2
        weak = [CAT_ALIAS.get(k, k) for k in CAT_FILTER
                if pp.get(k, {}).get("task", 0) > 0 and (pp[k].get("rate") or 0) < tp * 0.5]
        strong = [CAT_ALIAS.get(k, k) for k in CAT_FILTER
                  if pp.get(k, {}).get("task", 0) > 0 and (pp[k].get("rate") or 0) >= tp]
        plist.append({
            "name": n, "score": score,
            "毛利": {"done": pp["毛利"]["done"], "task": pp["毛利"]["task"], "rate": r_gross},
            "手机": {"done": pp["手机"]["done"], "task": pp["手机"]["task"], "rate": r_phone},
            "增值": {"done": (pq.get("增值") or {}).get("done", 0),
                    "task": (pq.get("增值") or {}).get("task", 0), "rate": r_add},
            "毛利率": (pq.get("健康度") or {}).get("grossMargin"),
            "券占比": (pq.get("健康度") or {}).get("ratio"),
            "strong": strong, "weak": weak,
            "todayGross": people[n]["dailyDone"].get("毛利", 0),
            "todayPhone": people[n]["dailyDone"].get("手机", 0),
        })
    plist.sort(key=lambda x: -x["score"])
    for i, p in enumerate(plist):
        p["rank"] = i + 1
        p["level"] = "good" if p["score"] >= tp else ("warn" if p["score"] >= tp * 0.6 else "danger")

    # ---------- 3. 今日谁卖了谁没卖 ----------
    orders, gross = {}, {}
    for r in rxs:
        n = r[C["P"]].strip()
        orders[n] = orders.get(n, 0) + 1
        gross[n] = gross.get(n, 0.0) + num(r[C["N"]])
    sold = sorted(({"name": n, "orders": orders[n], "gross": gross[n]}
                   for n in orders if n in PEOPLE_ORDER),
                  key=lambda x: -x["gross"])
    idle = [n for n in TASK_PEOPLE if n not in orders]

    # ---------- 4. 自动建议 ----------
    adv = []

    zero_cat = [c for c in cats if c["task"] > 0 and c["done"] <= 0]
    if zero_cat:
        names = "、".join(f"{c['name']}（任务 {c['task']:.0f}{c['unit']}）" for c in zero_cat)
        adv.append({"level": "danger", "icon": "🚨", "title": "整月零成交品类",
                    "body": f"{names} 本月一台没出。建议今天就定人盯：指定专人负责，"
                            f"每天至少推 3 组客户，样机摆到主动线。"})

    cold = [c for c in cats if c["coldDays"] and c["coldDays"] >= 3 and c["done"] > 0]
    if cold:
        s = "、".join(f"{c['name']}（{c['coldDays']}天，最后 {c['lastDate'][5:]}）" for c in cold)
        adv.append({"level": "warn", "icon": "🧊", "title": "断销品类",
                    "body": f"{s} 已经连续多天零动销。先查三件事：样机是否在位、"
                            f"有没有货、店员会不会讲卖点。"})

    behind = [c for c in cats if c["task"] > 0 and 0 < c["rate"] < tp * 0.6]
    if behind:
        s = "；".join(f"{c['name']} 还差 {c['task']-c['done']:.0f}{c['unit']}，"
                      f"日均要 {c['needPerDay']:.0f}{c['unit']}" for c in behind[:3])
        adv.append({"level": "warn", "icon": "📉", "title": f"进度落后（时间已过 {tp:.0%}）",
                    "body": f"{s}。建议把这几项拆到人头，早会点名报进度。"})

    lag_p = [p for p in plist if p["level"] == "danger"]
    if lag_p:
        s = "、".join(f"{p['name']}（毛利 {p['毛利']['rate']:.0%}）" for p in lag_p)
        adv.append({"level": "warn", "icon": "👤", "title": "需要重点帮扶",
                    "body": f"{s} 综合进度明显掉队。别只催结果，先看是客流少、"
                            f"接待量少，还是成交率低——三种病不同药。"})

    if idle:
        adv.append({"level": "warn", "icon": "⏰", "title": "今日还没开单",
                    "body": f"{'、'.join(idle)} 今天暂无上账记录。"
                            f"先确认是没卖还是没及时上账，卖了要立刻补账。"})

    top = plist[0] if plist else None
    if top and top["score"] >= tp:
        adv.append({"level": "good", "icon": "🏆", "title": "本月标杆",
                    "body": f"{top['name']} 综合进度领先（毛利 {top['毛利']['rate']:.0%}"
                            f"、手机 {top['手机']['rate']:.0%}）。"
                            f"让他在早会讲两句怎么谈的，比店长讲管用。"})

    gm = (store["qcs"].get("健康度") or {}).get("grossMargin")
    cp = (store["qcs"].get("健康度") or {}).get("ratio")
    if gm is not None and gm < 0.13:
        adv.append({"level": "warn", "icon": "💰", "title": "毛利率偏低",
                    "body": f"全店毛利率 {gm:.1%}，低于 13% 参考线。"
                            + (f"优惠券占比 {cp:.0%} 偏高，" if cp and cp > 0.3 else "")
                            + "多推增值和配件搭售，比单纯冲机器数划算。"})

    hot = [c for c in cats if c["level"] == "good"]
    if hot:
        adv.append({"level": "good", "icon": "✅", "title": "进度健康",
                    "body": "、".join(f"{c['name']} {c['rate']:.0%}" for c in hot)
                            + " 已跑赢时间进度，保持节奏就行。"})

    return {"categories": cats, "people": plist,
            "today": {"sold": sold, "idle": idle,
                      "totalOrders": len(rxs),
                      "totalGross": sum(gross.values())},
            "advices": adv,
            "dealAnalysis": build_deal_analysis(xs, rxs, people, plist, ref),
            "weekPlan": build_week_plan(),
            "timeProgress": tp, "remainDays": rd}


def build_deal_analysis(xs, rxs, people, plist, ref):
    """深度成交分析：结合毛利明细表 + dayDetails 数据，分析每笔成交和员工模式。"""

    # ---------- 5a. 今日成交流水 ----------
    # 从 rxs（当日明细）构建，补充渠道/会员/折扣等信息（毛利表没有的字段留空，由销售分析表补充）
    deals = []
    for r in rxs:
        orig = num(r[C["K"]])
        disc = num(r[C["L"]])
        amt  = num(r[C["M"]])
        profit = num(r[C["N"]])
        cost  = num(r[C["S"]])
        emp   = str(r[C["P"]]).strip()
        prod  = str(r[C["G"]]).strip()
        code  = str(r[C["A"]]).strip()
        cat   = day_cat(r)
        is_return = amt < 0 or num(r[C["I"]]) < 0

        # 折扣额和折扣率
        discount = orig - amt if orig > 0 and amt > 0 else 0
        disc_rate = discount / orig if orig > 0 and discount > 0 else 0
        # 成本率
        cost_ratio = cost / amt if amt > 0 else None
        # 搭售判断：同一出库单号有多行 = 搭售
        bundle_codes = {}
        for r2 in rxs:
            c2 = str(r2[C["A"]]).strip()
            if c2:
                bundle_codes[c2] = bundle_codes.get(c2, 0) + 1
        is_bundle = bundle_codes.get(code, 0) > 1

        deals.append({
            "emp": emp,
            "product": prod,
            "code": code,
            "channel": "自然客流",   # 毛利表无渠道字段，默认自然客流；有销售分析表时补充
            "bizType": "",
            "member": "",
            "origPrice": orig,
            "discount": discount if discount > 0 else 0,
            "discountRate": disc_rate if disc_rate > 0 else 0,
            "amount": amt,
            "profit": profit,
            "cost": cost,
            "costRatio": cost_ratio,
            "cat": cat,
            "isReturn": is_return,
            "isBundle": is_bundle,
        })

    # 按业务员+金额排序
    deals.sort(key=lambda d: (d["emp"], -d["amount"]))
    total_amount = sum(d["amount"] for d in deals)

    # ---------- 5b. 员工成交模式诊断 ----------
    patterns = []
    # 按员工统计月度数据
    for p in plist:
        name = p["name"]
        # 月度订单数 = 明细中该员工的出库单号去重数
        emp_rows = [r for r in xs if str(r[C["P"]]).strip() == name]
        emp_codes = set(str(r[C["A"]]).strip() for r in emp_rows if str(r[C["A"]]).strip())
        total_orders = len(emp_codes)

        # 客单价 = 总金额 / 订单数
        total_amt = sum(num(r[C["M"]]) for r in emp_rows if num(r[C["M"]]) > 0)
        avg_price = total_amt / total_orders if total_orders > 0 else 0

        # 搭售率 = 有多行的单号占比
        code_count = {}
        for r in emp_rows:
            c = str(r[C["A"]]).strip()
            if c:
                code_count[c] = code_count.get(c, 0) + 1
        bundle_codes = sum(1 for c, n in code_count.items() if n > 1)
        bundle_rate = bundle_codes / total_orders if total_orders > 0 else 0

        # 平均折扣率（只看有折扣的正向成交）
        discounts = []
        for r in emp_rows:
            orig = num(r[C["K"]])
            amt = num(r[C["M"]])
            if orig > 0 and amt > 0 and orig > amt:
                discounts.append((orig - amt) / orig)
        avg_discount = sum(discounts) / len(discounts) if discounts else 0

        # 当日订单
        today_orders = len([d for d in deals if d["emp"] == name])

        # 生成 badge 和行动建议
        score = p.get("score", 0)
        if score >= 0.067:  # 时间进度
            badge = "达标"
            badge_color = "var(--red)"
        elif score >= 0.067 * 0.5:
            badge = "需追赶"
            badge_color = "var(--amber)"
        else:
            badge = "落后"
            badge_color = "var(--green)"

        # 行动建议生成
        actions = []
        if today_orders == 0:
            actions.append("今日暂无开单，先检查样机在位和话术准备")
        if avg_price > 0 and avg_price < 3000:
            actions.append(f"客单价 {avg_price:.0f} 元偏低，多推中高端机型提升毛利")
        if bundle_rate < 0.3 and total_orders > 0:
            actions.append("搭售率偏低，每单必问配件/Care+/贴膜")
        if avg_discount > 0.05:
            actions.append(f"平均折扣 {avg_discount:.0%}，注意控制让利节奏")
        if not actions:
            actions.append("成交模式健康，保持节奏")
        action_text = "；".join(actions)

        patterns.append({
            "name": name,
            "badge": badge,
            "badgeColor": badge_color,
            "orders": total_orders,
            "avgPrice": avg_price,
            "bundleRate": bundle_rate,
            "avgDiscount": avg_discount,
            "todayOrders": today_orders,
            "action": action_text,
        })

    # ---------- 5c. 问题诊断与行动 ----------
    issues = []

    # 退货检测
    returns = [d for d in deals if d["isReturn"]]
    if returns:
        names = "、".join(d["product"] for d in returns)
        issues.append({"level": "danger", "icon": "⚠️", "title": "今日有退货",
                       "body": f"{names}，退货影响毛利。了解退货原因（质量/价格/冲动消费），做好售后挽留。"})

    # 无人开单（今日没有正向成交的员工）
    today_sellers = set(d["emp"] for d in deals if not d["isReturn"])
    idle_emps = [p["name"] for p in plist if p["name"] not in today_sellers]
    if idle_emps and len(idle_emps) >= 1:
        issues.append({"level": "warn", "icon": "⏰", "title": "多人未开单",
                       "body": f"{'、'.join(idle_emps)} 今日暂无正向成交。"
                               f"没顾客时主动回访老客户，至少打 5 通电话。"})

    # 折扣力度大的成交
    heavy_disc = [d for d in deals if d["discountRate"] > 0.1 and not d["isReturn"]]
    if heavy_disc:
        issues.append({"level": "warn", "icon": "💰", "title": "高折扣成交",
                       "body": f"有 {len(heavy_disc)} 笔成交折扣超 10%，"
                               f"检查是否必要让利，能用赠品替代的别直接降价。"})

    # 搭售率低的员工
    low_bundle = [p for p in patterns if p["bundleRate"] < 0.3 and p["orders"] > 2]
    if low_bundle:
        names = "、".join(p["name"] for p in low_bundle)
        issues.append({"level": "warn", "icon": "📦", "title": "搭售率偏低",
                       "body": f"{names} 搭售率低于 30%。每单成交后必须推配件或 Care+，"
                               f"话术：「配个贴膜/壳，一起拿更划算」。"})

    # 客单价偏低的员工
    low_price = [p for p in patterns if 0 < p["avgPrice"] < 3000]
    if low_price:
        names = "、".join(p["name"] for p in low_price)
        issues.append({"level": "warn", "icon": "📊", "title": "客单价偏低",
                       "body": f"{names} 客单价低于 3000 元。引导体验中高端机型，"
                               f"先讲卖点再报价格，别一上来就谈价格。"})

    return {
        "deals": deals,
        "totalAmount": total_amount,
        "patterns": patterns,
        "issues": issues,
    }


def build_week_plan():
    """周计划板块：运营反馈制度（固定清单+按天轮值+周指标+渠道分工）。"""
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    friday = monday + datetime.timedelta(days=4)
    if monday.month == friday.month:
        week_label = f"{monday.month}月{monday.day}-{friday.day}日"
    else:
        week_label = f"{monday.month}月{monday.day}日-{friday.month}月{friday.day}日"

    # ---- 1. 每日必做（用户经营：带量化指标） ----
    daily_user = [
        {"name": "企微拉新", "target": "5个/人", "icon": "👥"},
        {"name": "群拉新",   "target": "2个/人", "icon": "💬"},
        {"name": "WPS链接上传", "target": "3个/人", "icon": "📎"},
    ]
    # ---- 2. 每日基础运营（打卡项） ----
    daily_base = [
        {"name": "标签合规", "icon": "🏷️"},
        {"name": "激活照上传反馈", "icon": "📸"},
        {"name": "朋友圈反馈", "icon": "📱"},
    ]
    # ---- 3. 每周指标 ----
    weekly_kpi = [
        {"name": "ERP渠道挂账", "target": "1万/人", "icon": "💼"},
        {"name": "V3新增", "target": "1个/人", "icon": "🆕"},
        {"name": "华为会员日", "target": "4个/人", "icon": "⭐", "note": "扫码报名/贴膜拍照"},
    ]
    # ---- 4. 按天轮值（周一~周五） ----
    # 人员从动态名单取，至少3人时: 第1人负责库房、第2人负责渠道填表、全名单负责周五反馈
    _p0 = TASK_PEOPLE[0] if len(TASK_PEOPLE) > 0 else ""
    _p1 = TASK_PEOPLE[1] if len(TASK_PEOPLE) > 1 else ""
    _p2 = TASK_PEOPLE[2] if len(TASK_PEOPLE) > 2 else ""
    duty_days = [
        {"label": "周一", "date": f"{monday.month:02d}-{monday.day:02d}",
         "duties": [{"name": "大扫除", "who": "全员", "star": False}]},
        {"label": "周二", "date": f"{(monday+datetime.timedelta(days=1)).month:02d}-{(monday+datetime.timedelta(days=1)).day:02d}",
         "duties": [{"name": "膜类/礼品盘点", "who": _p2 or _p1, "star": False}]},
        {"label": "周三", "date": f"{(monday+datetime.timedelta(days=2)).month:02d}-{(monday+datetime.timedelta(days=2)).day:02d}",
         "duties": [{"name": "盘库/库房卫生/货品维护", "who": _p2 or _p1, "star": False}]},
        {"label": "周四", "date": f"{(monday+datetime.timedelta(days=3)).month:02d}-{(monday+datetime.timedelta(days=3)).day:02d}",
         "duties": []},
        {"label": "周五", "date": f"{friday.month:02d}-{friday.day:02d}",
         "duties": [
             {"name": "渠道运营填表/收集图片", "who": _p0, "star": True},
             {"name": "渠道周报反馈截止 14:00", "who": "/".join(TASK_PEOPLE), "star": True},
         ]},
    ]
    # ---- 5. 渠道运营分工（每周五14:00前反馈） ----
    _platforms = ["大众点评", "高德地图", "美团店铺"]
    channel_ops = []
    for i, n in enumerate(TASK_PEOPLE):
        if i < len(_platforms):
            channel_ops.append({"name": n, "platform": _platforms[i], "task": "评论8条"})
        else:
            break
    # ---- 6. 即时零售 ----
    instant = {"who": _p0}

    return {
        "weekLabel": week_label,
        "dailyUser": daily_user,
        "dailyBase": daily_base,
        "weeklyKpi": weekly_kpi,
        "dutyDays": duty_days,
        "channelOps": channel_ops,
        "instant": instant,
        "rules": "每日反馈·月度闭环 · 每晚11点前反馈 · 超时/漏反馈每项考核10 · 闭环时间20号",
    }


def day_cat(r):
    """当日明细的单行品类（叶子归类，不重叠）：手机/PC/平板/穿戴/音频/HD/增值/其他。"""
    d = str(r[C["D"]] or "")
    f = str(r[C["F"]] or "")
    if d == "01手机":   return "手机"
    if d == "05电脑":   return "PC"
    if d == "06平板电脑": return "平板"
    if d == "08穿戴":   return "穿戴"
    if d == "07音频":   return "音频"
    if f.startswith("12"): return "HD"
    if "增值" in d:     return "增值"
    if "运营商" in d:    return "增值"
    return "其他"


def build_day_details(rxs):
    """当日达成明细：RXS 逐行（商品/业务员/金额/毛利/毛利率/成本 + 品类）。"""
    out = []
    for r in rxs:
        amt = num(r[C["M"]])
        gross = num(r[C["N"]])
        out.append({
            "code": str(r[C["A"]]).strip(),
            "type": str(r[C["E"]]).strip(),
            "emp": str(r[C["P"]]).strip(),
            "product": str(r[C["G"]]).strip(),
            "sku": str(r[C["F"]]).strip(),
            "qty": num(r[C["I"]]),
            "origPrice": num(r[C["K"]]),
            "discPrice": num(r[C["L"]]),
            "amount": amt,
            "profit": gross,
            "cost": num(r[C["S"]]),
            "gpr": (gross / amt) if amt else None,
            "cat": day_cat(r),
        })
    out.sort(key=lambda x: (x["emp"], x["code"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("detail", help="明细文件路径（.tsv 或 .xlsx）")
    ap.add_argument("--xlsx", default="/Users/mac/Desktop/李家村销售/李家村9月任务进度.xlsx")
    ap.add_argument("--day", help="当日达成基准日，默认取明细里的最大日期")
    ap.add_argument("-o", "--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data.json"))
    a = ap.parse_args()

    xs = load_detail(a.detail)
    if not xs:
        sys.exit("❌ 明细里没有数据行")

    # 当日达成严格锚定「今天」：不把昨天的数据顶上来当今天的日报。
    # data_max=明细里最新出库日；同月且今天≥数据日时 day=今天，否则回退 data_max（跨月/时钟异常）。
    data_max = max(day_of(r) for r in xs)
    today = datetime.date.today()
    base0 = datetime.date.fromisoformat(data_max)
    ref = today if (today.year, today.month) == (base0.year, base0.month) and today >= base0 else base0
    day = a.day or ref.isoformat()
    rxs = [r for r in xs if day_of(r) == day]
    base = datetime.date.fromisoformat(day)
    last_day = calendar.monthrange(base.year, base.month)[1]
    rd = remain_days(ref)

    load_people(a.xlsx)
    tasks, lehui, taili, perf_score, lab_day, lab_gap = load_manual(a.xlsx)
    # 乐机收：直接读《李家村销售》T14:U18（持久化由 xlsx 文件承载；用户每次写入就是最新值）

    people = {}
    for n in PEOPLE_ORDER:
        p = calc_perf(xs, n, tasks[n])
        q = calc_qcs(xs, n, tasks[n], p, lehui, taili)
        p["绩效"] = perf_score[n]
        people[n] = {
            "performance": p,
            "qcs": q,
            "dailyDone": calc_daily(rxs, n, lab_day),
            "dailyGap": calc_gap(p, q, rd, lab_gap) if n in TASK_PEOPLE else {},
        }

    sp = total_perf(people)
    _ps = [v for v in perf_score.values() if v is not None]      # 合计行是 AVERAGE，忽略空值
    sp["绩效"] = sum(_ps) / len(_ps) if _ps else None
    sq = total_qcs(people, sp)
    store = {
        "performance": sp,
        "qcs": sq,
        "dailyDone": {k: sum(people[n]["dailyDone"].get(k, 0) for n in PEOPLE_ORDER)
                      for k in people[PEOPLE_ORDER[0]]["dailyDone"]},
        "dailyGap": {k: sum(people[n]["dailyGap"].get(k, 0) for n in TASK_PEOPLE)
                     for k in (people[TASK_PEOPLE[0]]["dailyGap"] if TASK_PEOPLE else {})},
    }

    data = {
        "meta": {
            "storeName": "华为李家村万达授权体验店",
            "date": day,
            "dayTitle": f"{base.month:02d}-{base.day:02d}达成",
            "timeProgress": ref.day / last_day,
            "remainDays": rd,
            "refDate": ref.isoformat(),
            # 上账时效：店员销售后才上账，可能滞后，但当天必补齐
            "isToday": base == ref,
            "lagDays": (ref - base).days,
            "todayLabel": f"{ref.month:02d}-{ref.day:02d}",
            "fetchTime": datetime.datetime.now().strftime("%H:%M"),
            "employees": PEOPLE_ORDER,
            "sourceFile": os.path.basename(a.detail),
            "sourceRows": len(xs),
            "dayRows": len(rxs),
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "store": store,
        "people": people,
        "insights": build_insights(xs, rxs, people, store, ref, ref.day / last_day, rd),
        "details": build_details(xs),
        "dayDetails": build_day_details(rxs),
    }

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    # ---- 体检 ----
    print(f"✅ 复算完成 → {a.out}")
    print(f"   明细 {len(xs)} 行 | 基准日 {day}（当日 {len(rxs)} 行）"
          f" | 时间进度 {base.day/last_day:.1%} | 剩余 {rd} 天")
    g = sp["毛利"]
    print(f"   门店毛利 任务 {g['task']:,.0f} 完成 {g['done']:,.0f} 达成 {(g['rate'] or 0):.1%}")
    print(f"   门店销额 完成 {sp['销额']['done']:,.0f} | 手机 {sp['手机']['done']:.0f} 台"
          f" | 增值 {sq['增值']['done']:,.0f}")
    for n in PEOPLE_ORDER:
        pg = people[n]["performance"]["毛利"]
        tag = " （未分配任务）" if not pg["task"] else ""
        print(f"   - {n:4s} 毛利 {pg['done']:>9,.0f}  当日 {people[n]['dailyDone'].get('毛利',0):>8,.0f}{tag}")


if __name__ == "__main__":
    main()
