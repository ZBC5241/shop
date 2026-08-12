#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_sales_analysis_http.py —— 纯 HTTP 直连用友「销售分析」报表(yonbip-mkt-retailweb)，免浏览器。

用友「销售分析」不是 report/exec 引擎，而是零售报表引擎 yonbip-mkt-retailweb：
  POST https://c3.yonyoucloud.com/yonbip-mkt-retailweb/report/list
  body: {"billnum":"rm_saleanalysis","page":{"pageIndex":1,"pageSize":N},
         "queryParams":[{"name":"beginDate","value":"YYYY-MM-DD"},
                        {"name":"endDate","value":"YYYY-MM-DD"}]}
  => {"code":200,"data":{"pageIndex":1,"pageSize":N,"recordCount":K,"recordList":[...]}}

登录态来源：agent-browser 持久化 session 状态文件（yht_access_token / XSRF-TOKEN 等 cookie）。
翻页抓取全量 recordList，落盘 JSON + 扁平 TSV（便于人工核对 / 后续映射进 42 列模板）。

用法:
  python3 fetch_sales_analysis_http.py [输出JSON] [输出TSV]
退出码: 0 成功 / 1 失败(含401需重登录)
"""
import json, sys, time, os, datetime, urllib.request, urllib.error, ssl

YY_BASE = "https://c3.yonyoucloud.com"
SA_URL = YY_BASE + "/yonbip-mkt-retailweb/report/list"
BILLNUM = "rm_saleanalysis"
DEFAULT_STATE = os.path.expanduser("~/.agent-browser/sessions/yonyou-default.json")
OUT_JSON = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa_raw.json")
OUT_TSV = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa_raw.tsv")

MONTH_FIRST = datetime.date.today().replace(day=1)
TODAY = datetime.date.today()


def load_cookies(state_path):
    d = json.load(open(state_path))
    return {c["name"]: c["value"] for c in d.get("cookies", [])
            if "yonyoucloud" in c.get("domain", "") and c.get("name") and c.get("value") is not None}


def post_report_list(ck, begin, end, page_index, page_size):
    xsrf = ck.get("XSRF-TOKEN", "")
    yht = ck.get("yht_access_token", "")
    cookie_hdr = "; ".join("%s=%s" % (k, v) for k, v in ck.items())
    body = json.dumps({
        "billnum": BILLNUM,
        "page": {"pageIndex": page_index, "pageSize": page_size},
        "queryParams": [
            {"name": "beginDate", "value": begin},
            {"name": "endDate", "value": end},
        ],
    }).encode("utf-8")
    hdr = {
        "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": YY_BASE,
        "Referer": YY_BASE + "/",
        "Cookie": cookie_hdr,
        "XSRF-TOKEN": xsrf,
        "yht_access_token": yht,
    }
    req = urllib.request.Request(SA_URL, data=body, headers=hdr, method="POST")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
        return resp.status, json.loads(resp.read())


def flatten(rec):
    """把嵌套对象拍平成 点号路径 的扁平 dict（recordList 里有些字段是嵌套对象）。"""
    out = {}
    for k, v in rec.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                out["%s.%s" % (k, kk)] = vv
        else:
            out[k] = v
    return out


def main():
    state = os.environ.get("YONYOU_STATE", DEFAULT_STATE)
    if not os.path.exists(state):
        sys.stderr.write("✗ 找不到用友登录态文件: %s\n" % state)
        return 1
    ck = load_cookies(state)
    # 关键校验只依赖 yht_access_token；XSRF-TOKEN / yht_usertoken_diwork 有则附上（增强兼容性）
    if "yht_access_token" not in ck:
        sys.stderr.write("✗ 登录态缺少关键 cookie: yht_access_token\n")
        return 1
    if "XSRF-TOKEN" not in ck:
        print("  [提示] 状态文件无 XSRF-TOKEN，尝试不携带该头直连（多数 yonyou 零售接口仅校验 cookie）")

    begin = MONTH_FIRST.strftime("%Y-%m-%d")
    end = TODAY.strftime("%Y-%m-%d")
    page_size = 5000  # 服务端单次上限约 5000；全量约 2 页，~26s（远快于 200/页 的 39 页）
    all_rows = []
    total = None
    t0 = time.time()
    page = 1
    while True:
        try:
            st, j = post_report_list(ck, begin, end, page, page_size)
        except urllib.error.HTTPError as e:
            sys.stderr.write("✗ HTTP_%d（登录态失效，需重新登录用友）\n" % e.code)
            return 1
        except Exception as e:
            sys.stderr.write("✗ 请求异常: %s\n" % e)
            return 1
        if st != 200 or j.get("code") != 200:
            sys.stderr.write("✗ 接口异常: %s\n" % str(j.get("message"))[:200])
            return 1
        data = j["data"]
        if total is None:
            total = data.get("recordCount", 0)
        recs = data.get("recordList", [])
        all_rows.extend(recs)
        print("  [页 %d] 本页 %d 行，累计 %d / %s" % (page, len(recs), len(all_rows), total))
        if not recs or (total is not None and len(all_rows) >= total):
            break
        if len(recs) < page_size:
            break
        page += 1
        if page > 200:
            break

    dt = time.time() - t0
    # 落盘 JSON（全量原始）
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"begin": begin, "end": end, "recordCount": len(all_rows),
                   "records": all_rows}, f, ensure_ascii=False)
    # 落盘 TSV（扁平，便于核对）
    if all_rows:
        cols = []
        seen = set()
        for r in all_rows:
            for k in flatten(r):
                if k not in seen:
                    seen.add(k)
                    cols.append(k)
        lines = ["\t".join(cols)]
        for r in all_rows:
            fr = flatten(r)
            lines.append("\t".join(str(fr.get(c, "")) for c in cols))
        with open(OUT_TSV, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    print("✓ 销售分析(纯HTTP)已保存: %s" % OUT_JSON)
    print("  日期范围: %s ~ %s" % (begin, end))
    print("  明细行数: %d（接口 recordCount=%s）" % (len(all_rows), total))
    print("  [计时] 纯HTTP翻页耗时: %.3fs" % dt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
