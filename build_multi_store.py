#!/usr/bin/env python3
"""
build_multi_store.py — 从销售分析数据生成多门店 data.json

输入: sa_mgr_month.json (全门店本月销售分析)
输出: data_multi.json — 多门店看板数据

结构:
{
  "meta": { "date", "stores": [...] },
  "current": "ALL|全部门店汇总",
  "stores": {
    "HW0001|华为智能生活馆·西安大唐不夜城": { meta, store, people, details, dayDetails, insights },
    "HW0006|华为李家村万达授权体验店": { ... },
    ...
    "ALL|全部门店汇总": { ... }
  }
}
"""
import json, os, sys, datetime, calendar
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
INPUT = os.path.join(BASE, "sa_mgr_month.json")
OUTPUT = os.path.join(BASE, "data_multi.json")

# 品类匹配规则（与 calc_data.py 的 DET_CATS 口径对齐）
# 销售分析的 productClass_name 对应明细的"商品分类"（D列）
# 销售分析的 product_cName 对应明细的"商品名称"（G列）
# 销售分析的 productsku_cCode / product_cCode 对应明细的"SKU编码"（F列）

# productClass_name 在销售分析中的常见值：
#   "01手机" "05电脑" "06平板电脑" "07音频" "08穿戴" "10运营商业务" "增值..." 等

def categorize_by_class(class_name):
    """按商品分类（productClass_name）归类，与 calc_data.py 的 DET_CATS 一致"""
    d = (class_name or "").strip()
    if d == "01手机":   return "手机"
    if d == "05电脑":   return "PC"
    if d == "06平板电脑": return "平板"
    if d == "08穿戴":   return "穿戴"
    if d == "07音频":   return "音频"
    if "增值" in d:     return "增值"
    if "运营商" in d:    return "增值"  # 运营商业务归入增值
    return None  # 未知分类，后面按名称再判断

def categorize_by_name(name):
    """按商品名称归类（兜底）"""
    s = (name or "")
    if any(k in s for k in ["WATCH", "手表", "手环", "Band"]):
        return "穿戴"
    if any(k in s for k in ["FreeBuds", "耳机", "Earbuds", "Sound", "音箱"]):
        return "音频"
    if any(k in s for k in ["MatePad", "Tab", "平板"]):
        return "平板"
    if any(k in s for k in ["MateBook", "笔记本", "PC", "电脑"]):
        return "PC"
    if any(k in s for k in ["Mate ", "手机", "Phone", "Nova", "畅享", "Pura", "MateXT"]):
        return "手机"
    if any(k in s for k in ["路由", "AX ", "网线", "Super ", "千兆", "智慧屏"]):
        return "HD"
    if any(k in s for k in ["贴膜", "Care", "保护壳", "保护膜", "充电", "数据线", "车充", "支架", "笔", "键盘", "鼠标", "包", "壳"]):
        return "增值"
    return "增值"  # 默认归增值

def get_cat(name, class_name, sku=""):
    """主归类函数：先按分类，再按名称"""
    cat = categorize_by_class(class_name)
    if cat:
        return cat
    # HD 按 SKU 前缀判断（与 calc_data.py 一致：F列 startswith("12")）
    if sku and str(sku).strip().startswith("12"):
        return "HD"
    return categorize_by_name(name)

def get_display_cat(name, class_name="", sku=""):
    """音频穿戴合并：音频+穿戴 → 音频穿戴"""
    cat = get_cat(name, class_name, sku)
    if cat in ("音频", "穿戴"):
        return "音频穿戴"
    return cat

def parse_num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").replace("%", "").strip()
    try:
        return float(s)
    except:
        return 0.0

# 销售分析中无毛利/成本/原价/折扣价，dayDetails 需占位
def build_store_data(recs, store_name, store_code, date_str, ref_date, time_progress, remain_days):
    """为单个门店（或全部）构建 data.json 兼容结构"""
    # 员工列表
    emp_set = set()
    for r in recs:
        emp = r.get("iEmployeeid_name", "")
        if emp:
            emp_set.add(emp)
    employees = sorted(emp_set)

    # 品类统计
    cat_amount = defaultdict(float)  # 金额（销额）
    cat_qty = defaultdict(float)     # 数量

    # 员工统计
    emp_amount = defaultdict(float)
    emp_qty = defaultdict(float)

    # 今日数据
    today_recs = [r for r in recs if (r.get("dDate", "")[:10] or "") == date_str]
    today_cat_qty = defaultdict(float)
    today_cat_amount = defaultdict(float)
    today_emp_amount = defaultdict(float)
    today_emp_qty = defaultdict(float)

    # 明细
    details = defaultdict(list)
    day_details = []

    for r in recs:
        name = r.get("product_cName", "") or ""
        class_name = r.get("productClass_name", "")
        qty = parse_num(r.get("fQuantity", 0))
        amount = parse_num(r.get("fMoney", 0))
        emp = r.get("iEmployeeid_name", "")
        dDate = (r.get("dDate", "") or "")[:10]
        sku = r.get("productsku_cCode", "") or r.get("product_cCode", "")
        code = r.get("code", "") or ""

        cat = get_display_cat(name, class_name, sku)
        cat_amount[cat] += amount
        cat_qty[cat] += abs(qty)

        if emp:
            emp_amount[emp] += amount
            emp_qty[emp] += abs(qty)

        # 今日数据
        if dDate == date_str:
            today_cat_qty[cat] += abs(qty)
            today_cat_amount[cat] += amount
            if emp:
                today_emp_amount[emp] += amount
                today_emp_qty[emp] += abs(qty)
            day_details.append({
                "code": code,
                "type": "",
                "emp": emp,
                "product": name,
                "sku": sku,
                "qty": qty,
                "origPrice": 0,
                "discPrice": 0,
                "amount": amount,
                "profit": 0,  # 销售分析无毛利
                "cost": 0,
                "gpr": None,
                "cat": cat,
            })

        # 按品类归入 details
        details[cat].append({
            "date": dDate,
            "name": name,
            "qty": qty,
            "origPrice": 0,
            "discPrice": 0,
            "amount": amount,
            "profit": 0,
            "gpr": None,
            "so": "",
            "cost": 0,
            "emp": emp,
            "sku": sku,
        })

    # 排序 details：按日期倒序
    for cat in details:
        details[cat].sort(key=lambda x: (x["date"] or ""), reverse=True)

    # 构建 store.performance
    # 销售分析的金额 = 销额，无毛利和任务量
    cats = ["手机", "PC", "平板", "穿戴", "音频", "HD", "智慧办公", "音频穿戴", "增值"]
    performance = {}
    for cat in cats:
        done = cat_amount.get(cat, 0)
        performance[cat] = {
            "task": 0,
            "done": round(done, 2),
            "gap": round(-done, 2),
            "rate": 0,
        }
    total_amount = sum(cat_amount.values())
    performance["毛利"] = {"task": 0, "done": 0, "gap": 0, "rate": 0}
    performance["销额"] = {"task": 0, "done": round(total_amount, 2), "gap": round(-total_amount, 2), "rate": 0}
    performance["绩效"] = None  # 无绩效数据

    # 品类台数
    cat_qty_out = {cat: int(cat_qty.get(cat, 0)) for cat in cats}

    # 员工数据
    people = {}
    for emp in employees:
        # 员工品类明细
        emp_perf = {
            "销额": {"task": 0, "done": round(emp_amount[emp], 2), "gap": 0, "rate": 0},
            "毛利": {"task": 0, "done": 0, "gap": 0, "rate": 0},
        }
        # 补充各品类
        for cat in cats:
            emp_perf[cat] = {"task": 0, "done": 0, "gap": 0, "rate": 0}
        emp_perf["智慧办公"] = {"task": 0, "done": 0, "gap": 0, "rate": 0}
        emp_perf["音频穿戴"] = {"task": 0, "done": 0, "gap": 0, "rate": 0}
        emp_perf["绩效"] = None

        people[emp] = {
            "performance": emp_perf,
            "qcs": {},  # 无全科生数据
            "dailyDone": {},
            "dailyGap": {},
        }

    # 为每个员工补充品类完成量（从明细统计）
    emp_cat_amount = defaultdict(lambda: defaultdict(float))
    emp_cat_qty = defaultdict(lambda: defaultdict(float))
    for r in recs:
        emp = r.get("iEmployeeid_name", "")
        if not emp:
            continue
        name = r.get("product_cName", "") or ""
        class_name = r.get("productClass_name", "")
        sku = r.get("productsku_cCode", "") or r.get("product_cCode", "")
        cat = get_display_cat(name, class_name, sku)
        emp_cat_amount[emp][cat] += parse_num(r.get("fMoney", 0))
        emp_cat_qty[emp][cat] += abs(parse_num(r.get("fQuantity", 0)))

    for emp in employees:
        for cat in cats:
            people[emp]["performance"][cat] = {
                "task": 0,
                "done": round(emp_cat_amount[emp].get(cat, 0), 2),
                "gap": 0,
                "rate": 0,
            }
        # 音频穿戴 = 音频 + 穿戴
        aw_amt = emp_cat_amount[emp].get("音频", 0) + emp_cat_amount[emp].get("穿戴", 0)
        people[emp]["performance"]["音频穿戴"] = {
            "task": 0, "done": round(aw_amt, 2), "gap": 0, "rate": 0,
        }
        # 智慧办公 = PC + 平板
        so_amt = emp_cat_amount[emp].get("PC", 0) + emp_cat_amount[emp].get("平板", 0)
        people[emp]["performance"]["智慧办公"] = {
            "task": 0, "done": round(so_amt, 2), "gap": 0, "rate": 0,
        }
        # 今日达成
        people[emp]["dailyDone"] = {
            "销额": round(today_emp_amount.get(emp, 0), 2),
        }

    # 今日数据
    today_total = sum(today_cat_amount.values())
    today_qty = sum(today_cat_qty.values())

    # dailyDone / dailyGap（门店级）
    daily_done = {}
    for cat in cats + ["销额", "毛利"]:
        if cat == "毛利":
            daily_done["毛利"] = 0
        elif cat == "销额":
            daily_done["销额"] = round(today_total, 2)
        elif cat == "音频穿戴":
            daily_done["音频穿戴"] = round(today_cat_amount.get("音频穿戴", 0), 2)
        elif cat == "智慧办公":
            daily_done["智慧办公"] = round(today_cat_amount.get("智慧办公", 0), 2)
        else:
            daily_done[cat] = round(today_cat_amount.get(cat, 0), 2)

    # insights
    today_sold = [
        {"name": emp, "orders": int(today_emp_qty.get(emp, 0)), "gross": 0}
        for emp in sorted(employees, key=lambda e: -today_emp_amount.get(e, 0))
        if today_emp_amount.get(emp, 0) > 0
    ]
    today_idle = [emp for emp in employees if today_emp_amount.get(emp, 0) <= 0]

    return {
        "meta": {
            "storeName": store_name,
            "storeCode": store_code,
            "date": date_str,
            "dayTitle": f"{ref_date.month:02d}-{ref_date.day:02d}达成",
            "timeProgress": time_progress,
            "remainDays": remain_days,
            "refDate": ref_date.isoformat(),
            "isToday": ref_date.isoformat() == date_str,
            "lagDays": (ref_date - datetime.date.fromisoformat(date_str)).days if date_str else 0,
            "todayLabel": f"{ref_date.month:02d}-{ref_date.day:02d}",
            "fetchTime": datetime.datetime.now().strftime("%H:%M"),
            "employees": employees,
            "sourceFile": f"销售分析({store_code})",
            "sourceRows": len(recs),
            "dayRows": len(today_recs),
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "recordCount": len(recs),
            "todayCount": len(today_recs),
            "totalAmount": round(total_amount, 2),
            "todayAmount": round(today_total, 2),
        },
        "store": {
            "performance": performance,
            "qcs": {},  # 无全科生数据
            "catQty": cat_qty_out,
            "totalAmount": round(total_amount, 2),
            "todayAmount": round(today_total, 2),
            "todayQty": int(today_qty),
            "todayCatQty": {k: int(v) for k, v in today_cat_qty.items()},
            "dailyDone": daily_done,
            "dailyGap": {},
        },
        "people": people,
        "details": dict(details),
        "dayDetails": day_details,
        "insights": {
            "categories": [
                {
                    "key": cat,
                    "name": cat,
                    "unit": "件",
                    "task": 0,
                    "done": round(cat_amount.get(cat, 0), 2),
                    "rate": 0,
                    "qty": int(cat_qty.get(cat, 0)),
                    "todayQty": int(today_cat_qty.get(cat, 0)),
                    "todayAmount": round(today_cat_amount.get(cat, 0), 2),
                    "level": "none",
                    "lastDate": "",
                    "coldDays": None,
                    "needPerDay": 0,
                    "zeroPeople": [],
                }
                for cat in cats
            ],
            "people": [
                {
                    "name": emp,
                    "score": 0,
                    "rank": i + 1,
                    "level": "none",
                    "毛利": {"done": 0, "task": 0, "rate": 0},
                    "手机": {"done": 0, "task": 0, "rate": 0},
                    "增值": {"done": 0, "task": 0, "rate": 0},
                    "毛利率": None,
                    "strong": [],
                    "weak": [],
                    "amount": round(emp_amount[emp], 2),
                    "qty": int(emp_qty[emp]),
                    "todayAmount": round(today_emp_amount.get(emp, 0), 2),
                    "todayGross": 0,
                    "todayPhone": 0,
                }
                for i, emp in enumerate(sorted(employees, key=lambda e: -emp_amount[e]))
            ],
            "today": {
                "sold": today_sold,
                "idle": today_idle,
                "totalOrders": len(today_recs),
                "totalGross": 0,
                "totalQty": int(today_qty),
                "totalAmount": round(today_total, 2),
            },
            "advices": [],
            "timeProgress": time_progress,
            "remainDays": remain_days,
        },
    }

def main():
    print("加载销售分析数据...")
    d = json.load(open(INPUT))
    recs = d["records"]

    # 确定日期：用明细中最大日期作为"今天"
    dates = sorted(set((r.get("dDate", "") or "")[:10] for r in recs if r.get("dDate")))
    if not dates:
        date_str = datetime.date.today().strftime("%Y-%m-%d")
    else:
        date_str = dates[-1]  # 最大日期

    # 用今天作为参考日（timeProgress 基于"今天"）
    today = datetime.date.today()
    base = datetime.date.fromisoformat(date_str)
    # 如果数据日期和今天在同月，用今天算时间进度；否则用数据日期
    if (today.year, today.month) == (base.year, base.month) and today >= base:
        ref_date = today
    else:
        ref_date = base

    last_day = calendar.monthrange(ref_date.year, ref_date.month)[1]
    time_progress = ref_date.day / last_day
    remain_days = max(1, last_day - ref_date.day)

    print(f"  总行数: {len(recs)}, 数据日期: {date_str}, 参考日: {ref_date}, 时间进度: {time_progress:.1%}")

    # 按门店分组
    store_recs = defaultdict(list)
    for r in recs:
        sname = r.get("store_name", "")
        scode = r.get("store_code", "")
        key = f"{scode}|{sname}"
        store_recs[key].append(r)

    # 构建各门店数据
    stores = {}
    store_list = []
    for key in sorted(store_recs.keys()):
        scode, sname = key.split("|", 1)
        s_recs = store_recs[key]
        stores[key] = build_store_data(s_recs, sname, scode, date_str, ref_date, time_progress, remain_days)
        store_list.append({"code": scode, "name": sname, "count": len(s_recs)})
        print(f"  {key}: {len(s_recs)} 行")

    # 全部门店汇总
    all_data = build_store_data(recs, "全部门店汇总", "ALL", date_str, ref_date, time_progress, remain_days)
    stores["ALL|全部门店汇总"] = all_data

    output = {
        "meta": {
            "date": date_str,
            "stores": store_list,
            "storeCount": len(store_list),
            "totalRecords": len(recs),
            "generatedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "timeProgress": time_progress,
            "remainDays": remain_days,
        },
        "current": "ALL|全部门店汇总",
        "stores": stores,
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False)
    print(f"\n✓ 已保存: {OUTPUT}")
    print(f"  门店数: {len(store_list)} + 汇总 = {len(stores)}")
    print(f"  文件大小: {os.path.getsize(OUTPUT) / 1024 / 1024:.1f} MB")

if __name__ == "__main__":
    main()
