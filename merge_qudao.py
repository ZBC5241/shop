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
    """按【员工 × 华为获客渠道】聚合 8 月李家村销售分析，供「渠道挂账·逐人」下拉展示。

    口径：剔除业务类型 ∈ {垫付, 预订}（与用户 Excel「不含垫付预订」表一致）。
    来源：sa_aug_cache.json（纯HTTP 抓取的 8 月切片）。
    返回：{ 员工名: [ {channel, amount, bills}, ... 按金额降序 ] }
    这样点击某员工即可看到「他走了哪些渠道、各渠道多少金额」，回答“显示哪个渠道的”。
    """
    emp = {}
    if not os.path.exists(AUG_CACHE):
        return emp
    try:
        recs = json.load(open(AUG_CACHE, encoding="utf-8")).get("records", [])
    except Exception as e:
        print("  [员工×渠道] sa_aug_cache 读取失败: %s" % e)
        return emp
    for r in recs:
        bt = str(r.get("iBusinesstypeid_name") or "").strip()
        if bt in EXCLUDE_BTYPE:
            continue
        p = str(r.get("iEmployeeid_name") or "").strip()
        c = str(r.get("retailVouchHeaderDefineCharacter__HWHKQD_name") or "").strip()
        if not p or not c:
            continue
        d = emp.setdefault(p, {}).setdefault(c, {"amount": 0.0, "bills": 0})
        d["amount"] += _num(r.get("fNetMoney"))
        d["bills"]  += 1
    out = {}
    # 渠道展示白名单：仅展示用户指定的获客渠道（与其余渠道明细保持一致口径）
    CHANNEL_WHITELIST = ["三大地图", "小红书", "大众点评", "异业", "社区", "企业上门购"]
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


def main():
    if not os.path.exists(DATA):
        print("✗ 找不到 data.json，请先运行 calc_data.py")
        return 1
    if not os.path.exists(XLSX):
        print("✗ 找不到表格: %s" % XLSX)
        return 1

    wb = openpyxl.load_workbook(XLSX, data_only=True)
    wb_f = openpyxl.load_workbook(XLSX, data_only=False)
    qd = bd.read_qudao(wb, wb_f)
    if not qd:
        print("[渠道] 未找到「渠道挂账」数据，跳过")
        return 0

    # 渠道明细（按【华为获客渠道名称】聚合 8 月李家村销售分析）
    channels = read_channels()
    if channels:
        qd["channels"] = channels
        top_amt = channels[0]["amount"]
        print("[渠道明细] 已聚合 %d 个获客渠道（按销额降序），Top: %s=%.0f"
              % (len(channels), channels[0]["name"], top_amt))
    else:
        print("[渠道明细] 未取到销售分析渠道数据（销售分析表为空？）")

    # 员工 × 渠道 聚合（供逐人下拉展示“走了哪些渠道、各多少金额”）
    emp_ch = read_emp_channel()
    if emp_ch:
        qd["empChannel"] = emp_ch
        print("[员工×渠道] 已聚合 %d 名员工的渠道明细" % len(emp_ch))

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
