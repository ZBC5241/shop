#!/usr/bin/env python3
"""
fetch_mgr_profit.py — 用经理账号按门店逐个拉取毛利明细数据

report/exec 接口 pageSize 硬编码 500 行，经理账号能看全部门店但被截断。
解决方案：利用报表的"门店"过滤参数，按门店逐个拉取，每次 500 行足够。

用法:
  python3 fetch_mgr_profit.py
输出:
  yonyou_mgr_profit.tsv — 全门店毛利明细 TSV
  yonyou_mgr_profit.json — 全门店毛利明细 JSON
"""
import json, os, sys, time, urllib.request, ssl, re

STATE_PATH = os.path.expanduser("~/.agent-browser/sessions/yonyou-mgr-default.json")
YY_BASE = "https://c3.yonyoucloud.com"
YY_REPORT_ID = "a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"

def clean(v):
    return re.sub(r"[^\x20-\x7e]", "", str(v))

def load_cookies(state_path):
    d = json.load(open(state_path))
    ck = {}
    for c in d.get("cookies", []):
        dom = c.get("domain", "")
        if ("yonyou" in dom or "yonbip" in dom) and c.get("name") and c.get("value") is not None:
            ck[c["name"]] = c["value"]
    return ck

def get_report(ck, store_filter=None):
    """拉取毛利明细报表。store_filter 可选，传入门店名称做过滤。"""
    cookie_hdr = "; ".join(f"{k}={clean(v)}" for k, v in ck.items())
    
    url = (f"{YY_BASE}/iuap-data-analytic/report/exec/{YY_REPORT_ID}"
           "?isAjax=1&hb=close&systenant=U8C3&havePublishPermission=true&browse=true"
           f"&newExec=true&sdkCode={YY_REPORT_ID}&locale=zh_CN&serviceCode={YY_REPORT_ID}")
    
    hdr = {
        "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": YY_BASE,
        "Referer": YY_BASE + "/",
        "Cookie": cookie_hdr,
        "XSRF-TOKEN": ck.get("XSRF-TOKEN", ""),
        "yht_access_token": clean(ck.get("yht_access_token", "")),
    }
    
    # 如果有门店过滤，用 POST 传参
    if store_filter:
        body = json.dumps({
            "conditions": {
                "门店": [store_filter]
            }
        }).encode("utf-8")
        hdr["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=hdr, method="POST")
    else:
        req = urllib.request.Request(url, headers=hdr, method="GET")
    
    with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as resp:
        return json.loads(resp.read())

def parse_tsv(j):
    """从 report/exec 响应解析 TSV 数据行。"""
    try:
        sh = j["data"]["analysisModel"]["sheets"][0]
        dd = sh["datas"][list(sh["datas"].keys())[0]]
        cells = dd["cells"]
        if not cells:
            return [], []
        
        hdr_row = [c[0] if c else "" for c in cells[0]]
        hdr_row = [h for h in hdr_row if h != ""]
        n = len(hdr_row)
        rows = []
        for r in cells[1:]:
            if not r or not r[0] or not r[0][0]:
                continue
            row = [str(c[0]) if (c and c[0] is not None) else "" for c in r[:n]]
            rows.append(row)
        return hdr_row, rows
    except Exception:
        return [], []

def main():
    ck = load_cookies(STATE_PATH)
    if "yht_access_token" not in ck:
        print("✗ 缺少 yht_access_token")
        return 1
    
    base = os.path.dirname(os.path.abspath(__file__))
    
    # 门店列表（从 sa_mgr_stores.json 加载）
    stores_path = os.path.join(base, "sa_mgr_stores.json")
    if os.path.exists(stores_path):
        store_list = json.load(open(stores_path))["stores"]
        store_names = [s.split("|", 1)[1] for s in store_list]
    else:
        # 先不过滤拉一次，看有哪些门店
        print("未找到门店列表，先拉全量...")
        store_names = [None]
    
    all_rows = []
    hdr = None
    t0 = time.time()
    
    if None in store_names:
        # 不分门店，一次拉全量
        j = get_report(ck)
        hdr, rows = parse_tsv(j)
        all_rows.extend(rows)
        dt = time.time() - t0
        print(f"全量拉取: {len(rows)} 行 ({dt:.1f}s)")
    else:
        # 按门店逐个拉取
        for i, store_name in enumerate(store_names):
            try:
                j = get_report(ck, store_filter=store_name)
                h, rows = parse_tsv(j)
                if hdr is None and h:
                    hdr = h
                all_rows.extend(rows)
                dt = time.time() - t0
                print(f"  [{i+1:2d}/{len(store_names)}] {store_name}: {len(rows)} 行 (累计 {len(all_rows)}, {dt:.0f}s)")
            except Exception as e:
                print(f"  [{i+1:2d}/{len(store_names)}] {store_name}: ✗ {e}")
                # 退回不过滤拉
                try:
                    j = get_report(ck)
                    h, rows = parse_tsv(j)
                    if hdr is None and h:
                        hdr = h
                    all_rows.extend(rows)
                    print(f"    退回全量: {len(rows)} 行")
                except Exception as e2:
                    print(f"    全量也失败: {e2}")
    
    dt = time.time() - t0
    print(f"\n✓ 拉取完成: {len(all_rows)} 行 ({dt:.0f}s)")
    
    if not all_rows or not hdr:
        print("✗ 无数据")
        return 1
    
    # 统计门店
    store_col = None
    for i, h in enumerate(hdr):
        if "门店" in h:
            store_col = i
            break
    
    if store_col is not None:
        stores = {}
        for r in all_rows:
            s = r[store_col] if store_col < len(r) else "N/A"
            stores[s] = stores.get(s, 0) + 1
        print(f"\n📊 门店分布 ({len(stores)} 个):")
        for k, v in sorted(stores.items(), key=lambda x: -x[1]):
            print(f"  {k}: {v} 行")
    
    # 保存 TSV
    tsv_path = os.path.join(base, "yonyou_mgr_profit.tsv")
    lines = ["\t".join(hdr)]
    for r in all_rows:
        lines.append("\t".join(r))
    with open(tsv_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"\n✓ TSV 已保存: {tsv_path}")
    
    # 保存 JSON
    json_path = os.path.join(base, "yonyou_mgr_profit.json")
    records = []
    for r in all_rows:
        records.append({hdr[i]: r[i] for i in range(min(len(hdr), len(r)))})
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"fetched_at": time.time(), "recordCount": len(records), "records": records}, f, ensure_ascii=False)
    print(f"✓ JSON 已保存: {json_path} ({len(records)} 行)")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
