#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_qudao.py —— 把《李家村X月任务进度.xlsx》的「渠道挂账」sheet 抽取后并入 data.json。

为什么需要它：
  run_pipeline 主复算走 calc_data.py（从明细实时复算，数字最准），但 calc_data 不含渠道挂账；
  渠道挂账只有 build_data.py 的 read_qudao 抽。本脚本只补 qudao 字段，不动 calc_data 的其他指标，
  避免“为了接渠道而退回公式缓存口径”的旧问题。

用法：
  python merge_qudao.py [data.json] [xlsx路径]
"""
import sys, os, json
import openpyxl
import build_data as bd

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1] if len(sys.argv) > 1 else os.path.join(BASE, "data.json")
XLSX = sys.argv[2] if len(sys.argv) > 2 else "/Users/mac/Desktop/李家村销售/李家村8月任务进度.xlsx"

AUG_CACHE = os.path.join(BASE, "sa_aug_cache.json")   # 8 月李家村切片（纯HTTP 抓取后本地筛得）


def _num(v):
    try:
        f = float(v)
        return f if f == f else 0.0
    except Exception:
        return 0.0


# 业务类型黑名单：与《李家村销售分析_销售净额_不含垫付预订》口径一致，
# 渠道/业绩统计均剔除「垫付」「预订」（产品订金、非MSC垫付等不计入销售净额）。
EXCLUDE_BTYPE = {"垫付", "预订"}


def read_channels():
    """按【华为获客渠道名称】聚合 8 月李家村销售分析的渠道明细。

    口径：剔除业务类型 ∈ {垫付, 预订} 的记录（与用户 Excel「不含垫付预订」表一致）。

    来源优先级：
      1) sa_aug_cache.json（纯HTTP 抓取的 8 月切片，最干净、最可靠）
      2) xlsx「销售分析」sheet（列 P=渠道名, J=业务类型, AM=销售净额, AI=销售数量）
    返回按销额净额降序的列表：[{name, amount, qty, bills, share}]
    """
    outset = []
    # —— 来源 1：sa_aug_cache.json ——
    if os.path.exists(AUG_CACHE):
        try:
            recs = json.load(open(AUG_CACHE, encoding="utf-8")).get("records", [])
            agg = {}
            for r in recs:
                bt = str(r.get("iBusinesstypeid_name") or "").strip()
                if bt in EXCLUDE_BTYPE:
                    continue
                c = r.get("retailVouchHeaderDefineCharacter__HWHKQD_name") or ""
                c = str(c).strip()
                if not c:
                    continue
                d = agg.setdefault(c, {"amount": 0.0, "qty": 0.0, "bills": 0})
                d["amount"] += _num(r.get("fNetMoney"))
                d["qty"]    += _num(r.get("fQuantity"))
                d["bills"]  += 1
            outset = agg
        except Exception as e:
            print("  [渠道明细] sa_aug_cache 读取失败，转 xlsx: %s" % e)

    # —— 来源 2：xlsx「销售分析」sheet 兜底 ——
    if not outset:
        try:
            wb = openpyxl.load_workbook(XLSX, data_only=True)
            if "销售分析" in wb.sheetnames:
                ws = wb["销售分析"]
                agg = {}
                for r in range(3, ws.max_row + 1):
                    bt = str(ws.cell(r, 10).value or "").strip()   # J 列 = 业务类型名称
                    if bt in EXCLUDE_BTYPE:
                        continue
                    c = ws.cell(r, 16).value      # P 列 = 华为获客渠道名称
                    if c is None:
                        continue
                    c = str(c).strip()
                    if not c:
                        continue
                    d = agg.setdefault(c, {"amount": 0.0, "qty": 0.0, "bills": 0})
                    d["amount"] += _num(ws.cell(r, 39).value)   # AM = 销售净额
                    d["qty"]    += _num(ws.cell(r, 35).value)   # AI = 销售数量
                    d["bills"]  += 1
                outset = agg
        except Exception as e:
            print("  [渠道明细] xlsx 读取失败: %s" % e)

    if not outset:
        return []

    total = sum(d["amount"] for d in outset.values())
    rows = []
    for name, d in outset.items():
        rows.append({
            "name": name,
            "amount": round(d["amount"], 2),
            "qty": round(d["qty"], 2),
            "bills": d["bills"],
            "share": (d["amount"] / total) if total else 0.0,
        })

    # —— 渠道展示白名单：仅展示用户指定的获客渠道（其余不列入明细）——
    # 白名单内但本期无数据的渠道补 0 行展示；占比基于白名单合计。
    CHANNEL_WHITELIST = ["三大地图", "小红书", "大众点评", "异业", "社区", "企业上门购"]
    by_name = {r["name"]: r for r in rows}
    out_rows = []
    for name in CHANNEL_WHITELIST:
        if name in by_name:
            out_rows.append(by_name[name])
        else:
            out_rows.append({"name": name, "amount": 0.0, "qty": 0.0, "bills": 0, "share": 0.0})
    wl_total = sum(r["amount"] for r in out_rows)
    for r in out_rows:
        r["share"] = (r["amount"] / wl_total) if wl_total else 0.0
    return out_rows


def read_emp_channel():
    """按【员工 × 华为获客渠道】聚合桌面 xlsx「销售分析」sheet（8 月李家村）。

    口径：剔除业务类型 ∈ {垫付, 预订}（与用户 Excel「不含垫付预订」表一致）；
          仅白名单获客渠道；按业务日期过滤 8 月切片。
    来源：直接读桌面《李家村8月任务进度.xlsx》的「销售分析」sheet（用户导出，全程按表格走）。
    返回：{ 员工名: [ {channel, amount, bills}, ... 按白名单顺序 ] }
    """
    emp = {}
    if not os.path.exists(XLSX):
        print("  [员工×渠道] 找不到 xlsx: %s" % XLSX)
        return emp
    try:
        wb = openpyxl.load_workbook(XLSX, data_only=True)
        if "销售分析" not in wb.sheetnames:
            print("  [员工×渠道] 未找到「销售分析」sheet")
            return emp
        ws = wb["销售分析"]
        # 表头在第 2 行，动态定位关键列
        hdr = {}
        for c in range(1, ws.max_column + 1):
            v = ws.cell(2, c).value
            if v:
                hdr[str(v).strip()] = c
        COL_P  = hdr.get("华为获客渠道名称")   # 渠道
        COL_G  = hdr.get("营业员名称")         # 员工
        COL_H  = hdr.get("业务类型名称")        # 业务类型（剔除垫付/预订）
        COL_N  = hdr.get("销售净额")           # 净额
        COL_BD = hdr.get("业务日期")           # 过滤 8 月
        if not (COL_G and COL_P and COL_H and COL_N):
            print("  [员工×渠道] 销售分析缺少关键列（员工/渠道/业务类型/净额）")
            return emp
        import datetime as _dt
        for r in range(3, ws.max_row + 1):
            bt = str(ws.cell(r, COL_H).value or "").strip()
            if bt in EXCLUDE_BTYPE:
                continue
            bd = ws.cell(r, COL_BD).value if COL_BD else None
            if isinstance(bd, (_dt.datetime, _dt.date)):
                if not (bd.year == 2026 and bd.month == 8):
                    continue
            p = str(ws.cell(r, COL_G).value or "").strip()
            c = str(ws.cell(r, COL_P).value or "").strip()
            if not p or not c:
                continue
            d = emp.setdefault(p, {}).setdefault(c, {"amount": 0.0, "bills": 0})
            d["amount"] += _num(ws.cell(r, COL_N).value)
            d["bills"]  += 1
    except Exception as e:
        print("  [员工×渠道] 销售分析读取失败: %s" % e)
        return emp
    # 渠道展示白名单：仅展示用户指定的获客渠道
    CHANNEL_WHITELIST = ["三大地图", "小红书", "大众点评", "异业", "社区", "企业上门购"]
    out = {}
    for p, chans in emp.items():
        rows = []
        for ch in CHANNEL_WHITELIST:
            d = chans.get(ch)
            rows.append({
                "channel": ch,
                "amount": round(d["amount"], 2) if d else 0.0,
                "bills": d["bills"] if d else 0,
            })
        out[p] = rows
    return out


def refresh_qudao_done(xlsx):
    """【最新拉取】从销售分析 sheet 实时复算完成额，写入「渠道挂账」sheet C 列(落表)。

    这样每日定时任务跑时 C 列永远是最新拉取到的值，日报 read_qudao 读 C 列即「最新拉取的数据」，
    而非冻结的首拉快照。仅当整列 C 为空才回退（已在 read_qudao 内兜底）。
    返回写入的 {姓名: 完成额}，失败返回 None。
    """
    try:
        wb = openpyxl.load_workbook(xlsx, data_only=True)
        agg = bd._agg_qudao_done(wb)
    except Exception as e:
        print("  [渠道刷新] 复算失败: %s" % e)
        return None
    if not agg:
        print("  [渠道刷新] 无聚合结果，跳过写入 C 列")
        return None
    try:
        wb_f = openpyxl.load_workbook(xlsx, data_only=False)
        ws = wb_f["渠道挂账"]
        hrow = None
        for r in range(1, min(ws.max_row, 40) + 1):
            if (str(ws.cell(r, 2).value or "").strip() == "任务"
                    and str(ws.cell(r, 3).value or "").strip() == "完成"):
                hrow = r
                break
        if not hrow:
            print("  [渠道刷新] 未找到表头行，跳过写入")
            return None
        written = {}
        for r in range(hrow + 1, ws.max_row + 1):
            nm = ws.cell(r, 1).value
            if not nm:
                continue
            nm = str(nm).strip()
            if nm in ("", "合计"):
                continue
            v = round(agg.get(nm, 0.0), 2)
            ws.cell(r, 3).value = v
            written[nm] = v
        wb_f.save(xlsx)
        print("  [渠道刷新] 已写入 C 列(最新拉取): %s" % written)
        return written
    except Exception as e:
        print("  [渠道刷新] 写入失败: %s" % e)
        return None


def main():
    if not os.path.exists(DATA):
        print("✗ 找不到 data.json，请先运行 calc_data.py")
        return 1
    if not os.path.exists(XLSX):
        print("✗ 找不到表格: %s" % XLSX)
        return 1

    # Step A：最新拉取——先复算最新完成额写入渠道挂账 sheet C 列（落表）
    refresh_qudao_done(XLSX)

    # Step B：重新读取（含最新写入的 C 列）做合并
    wb = openpyxl.load_workbook(XLSX, data_only=True)
    wb_f = openpyxl.load_workbook(XLSX, data_only=False)
    qd = bd.read_qudao(wb, wb_f)
    if not qd:
        print("[渠道] 未找到「渠道挂账」数据，跳过")
        return 0

    # 渠道挂账完成额/任务额/达成/逐人：全部按用户 xlsx「渠道挂账」sheet 公式提取
    # （read_qudao 已读到表格公式值，如合计 24539 / 杨丽华 0）。
    # 逐人下钻的【各渠道明细】则从桌面 xlsx「销售分析」sheet 聚合（同样剔除垫付/预订），
    # 全程数据源都是用户桌面文件，不再经过用友抓取缓存。
    emp_ch = read_emp_channel()
    if emp_ch:
        qd["empChannel"] = emp_ch
        print("[员工×渠道] 已聚合 %d 名员工的渠道明细（来自桌面销售分析 sheet）" % len(emp_ch))

    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)
    d["qudao"] = qd
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)

    t = qd.get("total") or {}
    print("[渠道] 已并入 data.json：完成 %s / 任务 %s / 达成 %.1f%%（时间进度 %.1f%%）" % (
        t.get("done"), t.get("task"),
        (t.get("rate") or 0) * 100, (qd.get("timeRate") or 0) * 100))
    return 0


if __name__ == "__main__":
    sys.exit(main())
