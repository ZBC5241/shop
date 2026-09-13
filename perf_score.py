#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
绩效得分重算器 —— 按《李家村月度任务进度.xlsx》个人表的公式原样精算。

背景：底表带 <calcPr fullCalcOnLoad="1"/>，不含公式缓存值；而管线里的
      update_xs / update_sales_analysis 等脚本用 openpyxl 回写底表后，
      公式缓存会被彻底清空 → openpyxl 的 data_only 读 L18(=SUM(L4:L17)) 恒为 None，
      看板「绩效」因此长期空缺。

本模块不改底表，只按底表公式逐项还原：

  个人表（邵乐乐/杨丽华/李泽…）行 4~11 —— 8 个考核项，每项 L = 得分：
      L = MIN((K/C)*M, M)              （r9/r10/r11 为 IF(C=0, 5, MIN(...))）
      K = 该项「完成量」，C = 月度任务!对应列（任务量），M = 权重
      r4 毛利     K=SUMIFS(XS!N, 业务员)                      C=月度任务!D  M=35
      r5 手机     K=SUMIFS(XS!I, 业务员, 分类="01手机")          C=月度任务!E  M=15
      r6 增值     K=SUMIFS(XS!N,分类含增值/运营商业) + 太力*0.14 + 乐机收U
                                                             C=月度任务!F  M=20
      r7 智慧办公  K=SUMIFS(分类="05电脑")+SUMIFS(分类="06平板电脑")
                                                             C=月度任务!H+I M=5
      r8 音频穿戴  K=SUMIFS(分类="08穿戴")+SUMIFS(分类="07音频")  C=月度任务!J+K M=5
      r9 HD      K=SUMIFS(SKU编码="12*")                       C=月度任务!L  M=5
      r10 合约    K=SUMIFS(sku分类="合约入网")                   C=月度任务!G  M=5
      r11 课程    K=SUMIFS(名称含"大师课" 且 毛利>0)              C=月度任务!M  M=5
  行 12~17 为人工项（投诉/执行力/学习/晨读/全科生加减分），直接取个人表 L 列常量。
  L18 = SUM(L4:L17) → 即绩效得分。

  店长（张博晨）取「店长」表 J4:J22 常量之和（= 店长!J24）。

用法：
    from perf_score import compute_perf
    res = compute_perf("/path/李家村9月任务进度.xlsx")   # -> {姓名: 分数 or None}
"""
import openpyxl

# 权重（个人表 M4:M11）
W = [35, 15, 20, 5, 5, 5, 5, 5]
# 月度任务表：C..M 列 → 列号
TC = {"收入": 3, "毛利": 4, "手机": 5, "增值": 6, "合约": 7,
      "智慧办公a": 8, "智慧办公b": 9, "音频穿戴a": 10, "音频穿戴b": 11,
      "HD": 12, "课程": 13}
MANAGER_SHEET = "店长"


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s == "" or s.startswith("#"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _task_sheet(wb):
    for s in wb.sheetnames:
        if s.endswith("月任务") or s.endswith("度任务"):
            return wb[s]
    raise KeyError("底表缺少「X月任务 / 月度任务」sheet")


def compute_perf(xlsx):
    """返回 {姓名: 绩效分}；算不出的给 None。绝不修改 xlsx。"""
    wb = openpyxl.load_workbook(xlsx, data_only=True)

    # ---------- 1. 人员 & 任务量 ----------
    tk = _task_sheet(wb)
    people = []                                  # [(姓名, 月度任务行号)]
    for r in range(4, 8):
        nm = tk.cell(r, 2).value
        if nm and str(nm).strip() and str(nm).strip() != "合计":
            people.append((str(nm).strip(), r))
    if not people:
        return {}

    def task(r, key):
        return _num(tk.cell(r, TC[key]).value)

    # ---------- 2. XS 明细单遍聚合 ----------
    names = {n for n, _ in people}
    agg = {n: dict(maoli=0.0, phone=0.0, pc=0.0, pad=0.0, wear=0.0, audio=0.0,
                   hd=0.0, hetong=0.0, kecheng=0.0, zz=0.0) for n in names}
    if "XS" in wb.sheetnames:
        xs = wb["XS"]
        for row in range(2, xs.max_row + 1):
            who = str(xs.cell(row, 16).value or "").strip()   # P 业务员
            if who not in agg:
                continue
            qty = _num(xs.cell(row, 9).value) or 0.0          # I 数量
            gm = _num(xs.cell(row, 14).value) or 0.0          # N 毛利
            cat = str(xs.cell(row, 4).value or "")            # D 商品分类
            scat = str(xs.cell(row, 5).value or "")           # E 商品sku分类
            sku = str(xs.cell(row, 6).value or "")            # F 商品SKU编码
            gname = str(xs.cell(row, 7).value or "")          # G 商品名称
            a = agg[who]
            a["maoli"] += gm
            if cat == "01手机":        a["phone"] += qty
            elif cat == "05电脑":      a["pc"] += qty
            elif cat == "06平板电脑":  a["pad"] += qty
            elif cat == "08穿戴":      a["wear"] += qty
            elif cat == "07音频":      a["audio"] += qty
            if sku.startswith("12"):                          a["hd"] += qty
            if scat == "合约入网":     a["hetong"] += qty
            if ("大师课" in gname) and gm > 0:                 a["kecheng"] += qty
            if ("增值" in cat) or ("运营商业" in cat):         a["zz"] += gm

    # ---------- 3. 太力回收增值 + 乐机收（U 列） ----------
    taili = {n: 0.0 for n in names}
    if "太力回收" in wb.sheetnames:
        tl = wb["太力回收"]
        for row in range(2, tl.max_row + 1):
            who = str(tl.cell(row, 22).value or "").strip()   # V 销售员
            if who in taili:
                taili[who] += _num(tl.cell(row, 29).value) or 0.0   # AC 回收价

    leji = {}
    if "李家村销售" in wb.sheetnames:
        ljs = wb["李家村销售"]
        for n, r in people:
            leji[n] = _num(ljs.cell(r + 10, 21).value) or 0.0      # U 列（乐机收金额）

    # ---------- 4. 逐人计分 ----------
    out = {}
    for n, r in people:
        a = agg[n]
        K = [a["maoli"], a["phone"],
             a["zz"] + taili[n] * 0.14 + leji[n],
             a["pc"] + a["pad"], a["wear"] + a["audio"],
             a["hd"], a["hetong"], a["kecheng"]]
        C = [task(r, "毛利"), task(r, "手机"), task(r, "增值"),
             (task(r, "智慧办公a") or 0) + (task(r, "智慧办公b") or 0),
             (task(r, "音频穿戴a") or 0) + (task(r, "音频穿戴b") or 0),
             task(r, "HD"), task(r, "合约"), task(r, "课程")]
        total = 0.0
        for i in range(8):
            c, m, k = C[i], W[i], K[i]
            if not c:                       # 任务为 0 / 空
                total += 5.0 if i >= 5 else 0.0   # r9~r11 公式带 IF(C=0,5,..)
            else:
                total += min(k / c * m, m)
        # 手工行 L12:L17（投诉/执行力/学习/晨读/全科生…）
        if n in wb.sheetnames:
            ws = wb[n]
            for rr in range(12, 18):
                v = _num(ws.cell(rr, 12).value)
                if v:
                    total += v
        out[n] = round(total, 6)

    # ---------- 5. 张博晨 → 店长表 J4:J22 ----------
    if MANAGER_SHEET in wb.sheetnames:
        zd = wb[MANAGER_SHEET]
        s = 0.0
        for rr in range(4, 23):
            s += _num(zd.cell(rr, 10).value) or 0.0
        out["张博晨"] = round(s, 6)

    return out


if __name__ == "__main__":
    import sys, json
    p = sys.argv[1] if len(sys.argv) > 1 else \
        "/Users/mac/Desktop/李家村销售/李家村9月任务进度.xlsx"
    res = compute_perf(p)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    vals = [v for v in res.values() if v is not None]
    print("门店均值:", round(sum(vals) / len(vals), 6) if vals else None)
