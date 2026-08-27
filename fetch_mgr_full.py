#!/usr/bin/env python3
"""
fetch_mgr_full.py — 用经理账号全量拉取销售分析数据（所有门店）

策略：
  1. 用 report/list 接口分页拉取全量（~20万条）
  2. 只保留本月数据（按 dDate 过滤）
  3. 保存到 sa_mgr_month.json

用法:
  python3 fetch_mgr_full.py [--page-size N] [--output PATH]

输出:
  sa_mgr_month.json — 本月全门店销售分析数据
  sa_mgr_stores.json — 门店列表
"""
import json, os, sys, time, urllib.request, ssl, datetime, math

STATE_PATH = os.path.expanduser("~/.agent-browser/sessions/yonyou-mgr-token.json")
SA_URL = "https://c3.yonyoucloud.com/yonbip-mkt-retailweb/report/list"
BEGIN = datetime.date.today().replace(day=1).strftime("%Y-%m-%d")
END = datetime.date.today().strftime("%Y-%m-%d")
PAGE_SIZE = 20000
MAX_PAGES = 15

def load_cookies(state_path):
    d = json.load(open(state_path))
    return {c["name"]: c["value"] for c in d.get("cookies", [])
            if "yonyoucloud" in c.get("domain", "") and c.get("name") and c.get("value") is not None}

def post_page(ck, page_index, page_size=PAGE_SIZE, timeout=180):
    body = json.dumps({
        "billnum": "rm_saleanalysis",
        "page": {"pageIndex": page_index, "pageSize": page_size},
        "queryParams": [
            {"name": "beginDate", "value": BEGIN},
            {"name": "endDate", "value": END},
        ],
    }).encode("utf-8")
    hdr = {
        "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://c3.yonyoucloud.com",
        "Referer": "https://c3.yonyoucloud.com/",
        "Cookie": "; ".join(f"{k}={v}" for k, v in ck.items()),
        "XSRF-TOKEN": ck.get("XSRF-TOKEN", ""),
        "yht_access_token": ck.get("yht_access_token", ""),
    }
    req = urllib.request.Request(SA_URL, data=body, headers=hdr, method="POST")
    with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as resp:
        return resp.status, json.loads(resp.read())

def main():
    ck = load_cookies(STATE_PATH)
    if "yht_access_token" not in ck:
        print("✗ 缺少 yht_access_token")
        return 1
    print(f"日期范围: {BEGIN} ~ {END}")
    print(f"Cookie 数: {len(ck)}")

    all_month_recs = []
    total = None
    page = 1
    t0 = time.time()

    while page <= MAX_PAGES:
        for attempt in range(1, 4):
            try:
                st, j = post_page(ck, page)
                break
            except Exception as e:
                if attempt < 3:
                    print(f"  [重试 {attempt}/3] 页 {page}: {e}")
                    time.sleep(5 * attempt)
                else:
                    print(f"✗ 页 {page} 请求失败: {e}")
                    return 1

        if st != 200 or j.get("code") != 200:
            print(f"✗ 接口异常: HTTP {st}, code={j.get('code')}")
            return 1

        data = j["data"]
        if total is None:
            total = data.get("recordCount", 0)
            print(f"总记录数: {total} (约 {math.ceil(total / PAGE_SIZE)} 页)")

        recs = data.get("recordList", [])
        month = [r for r in recs if BEGIN <= (r.get("dDate") or "")[:10] <= END]
        all_month_recs.extend(month)

        dt = time.time() - t0
        print(f"  [页 {page:2d}] {len(recs)} 行 → 本月 {len(month)} 行 (累计 {len(all_month_recs)}, {dt:.0f}s)")

        if not recs or len(recs) < PAGE_SIZE:
            break
        page += 1

    dt = time.time() - t0
    print(f"\n✓ 全量拉取完成: {len(all_month_recs)} 行本月数据 ({dt:.0f}s)")

    # 门店分布
    stores = {}
    for r in all_month_recs:
        s = r.get("store_name", "N/A")
        sc = r.get("store_code", "N/A")
        key = f"{sc}|{s}"
        stores[key] = stores.get(key, 0) + 1

    print(f"\n📊 门店分布（{len(stores)} 个门店）:")
    for k, v in sorted(stores.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} 行")

    # 员工分布
    emps = {}
    for r in all_month_recs:
        e = r.get("iEmployeeid_name", "N/A")
        s = r.get("store_name", "N/A")
        key = f"{s}|{e}"
        emps[key] = emps.get(key, 0) + 1

    print(f"\n👤 员工分布（{len(emps)} 个员工-门店组合）:")
    for k, v in sorted(emps.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} 行")

    # 保存
    base = os.path.dirname(os.path.abspath(__file__))
    out_json = os.path.join(base, "sa_mgr_month.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "fetched_at": time.time(),
            "begin": BEGIN,
            "end": END,
            "recordCount": len(all_month_recs),
            "stores": list(stores.keys()),
            "records": all_month_recs,
        }, f, ensure_ascii=False)
    print(f"\n✓ 已保存: {out_json} ({len(all_month_recs)} 行)")

    store_list = sorted(stores.keys())
    out_stores = os.path.join(base, "sa_mgr_stores.json")
    with open(out_stores, "w", encoding="utf-8") as f:
        json.dump({"stores": store_list, "fetched_at": time.time()}, f, ensure_ascii=False, indent=2)
    print(f"✓ 门店列表: {out_stores} ({len(store_list)} 个)")

    return 0

if __name__ == "__main__":
    sys.exit(main())
