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

重要事实（已实测）：
  - 该接口对 rm_saleanalysis 的日期筛选在服务端无效（beginDate/endDate/vouchdate/condition 等
    25+ 种参数组合实测：要么忽略返回全量 7811 行，要么 999 报错）。日期筛选是 用友前端 SPA 私有结构。
  - 所以每次联网必拉回「李家村全量历史」7811 行（~90s），本地按单据日期过滤为本月。
  - 为把「更新看板」做到毫秒级：增加本地数据仓 sa_warehouse.json 缓存全量；--use-cache 直接读仓跳过联网。

用法:
  python3 fetch_sales_analysis_http.py [输出JSON] [输出TSV] [--use-cache]
退出码: 0 成功 / 1 失败(含401需重登录)
"""
import json, sys, time, os, datetime, urllib.request, urllib.error, ssl

YY_BASE = "https://c3.yonyoucloud.com"
SA_URL = YY_BASE + "/yonbip-mkt-retailweb/report/list"
BILLNUM = "rm_saleanalysis"
DEFAULT_STATE = os.path.expanduser("~/.agent-browser/sessions/yonyou-default.json")
# 参数：位置参数 [输出JSON] [输出TSV]，可选 --use-cache（放在任意位置）
_ARGS = [a for a in sys.argv[1:] if a != "--use-cache"]
OUT_JSON = _ARGS[0] if len(_ARGS) > 0 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa_raw.json")
OUT_TSV = _ARGS[1] if len(_ARGS) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa_raw.tsv")
WAREHOUSE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa_warehouse.json")
AUG_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sa_aug_cache.json")  # 预存「8月李家村」切片，读仓时直接读它→真毫秒
CACHE_MAX_AGE = 6 * 3600  # 仓有效期 6h

MONTH_FIRST = datetime.date.today().replace(day=1)
TODAY = datetime.date.today()
USE_CACHE = "--use-cache" in sys.argv


def load_cookies(state_path):
    d = json.load(open(state_path))
    return {c["name"]: c["value"] for c in d.get("cookies", [])
            if "yonyoucloud" in c.get("domain", "") and c.get("name") and c.get("value") is not None}


def post_report_list(ck, begin, end, page_index, page_size, timeout=180):
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
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.status, json.loads(resp.read())


def flatten(rec):
    out = {}
    for k, v in rec.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                out["%s.%s" % (k, kk)] = vv
        else:
            out[k] = v
    return out


def atomic_write_json(path, obj):
    """先写临时文件再原子改名，避免并发读取读到半截/空文件。"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def atomic_write_text(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


# 用友 report/list 对 rm_saleanalysis 返回的行存在两类冗余（2026-08-19 实测，与
# 晨哥手机手工导出的《销售分析_0819.xlsx》417 行逐项核对）：
#   1) 同一单号下部分商品行被重复返回（如 18 行变 36 行，内容全同）；
#   2) 预订单以「单号_YD」额外返回一份（与主单同金额，属订金，不应重复计入）。
# 去重规则 = 剔除 _YD 单号 + 按 (单号, SKU编码, 序列号) 去重。
# 验证：去重后 8008→约对应晨哥文件 417 行；六渠道净额 83753 完全一致。
SN_FIELD = "oid_userDefine_2419863036093267976"  # 序列号（SN）


def dedup_records(records):
    seen = set()
    out = []
    for r in records:
        code = str(r.get("code") or "")
        if code.endswith("_YD"):          # 订金/预订单变体，剔除
            continue
        k = (code,
             str(r.get("productsku_cCode") or ""),
             str(r.get(SN_FIELD) or ""))
        if k in seen:
            continue
        seen.add(k)
        out.append(r)
    return out


def main():
    state = os.environ.get("YONYOU_STATE", DEFAULT_STATE)
    if not os.path.exists(state):
        sys.stderr.write("✗ 找不到用友登录态文件: %s\n" % state)
        return 1
    ck = load_cookies(state)
    if "yht_access_token" not in ck:
        sys.stderr.write("✗ 登录态缺少关键 cookie: yht_access_token\n")
        return 1
    if "XSRF-TOKEN" not in ck:
        print("  [提示] 状态文件无 XSRF-TOKEN，尝试不携带该头直连（多数 yonyou 零售接口仅校验 cookie）")

    begin = MONTH_FIRST.strftime("%Y-%m-%d")
    end = TODAY.strftime("%Y-%m-%d")
    page_size = 5000
    all_rows = []
    total = None
    t0 = time.time()

    # ---- 仓模式：直接读「8月切片」缓存（真毫秒级），否则读全量仓，否则联网 ----
    if USE_CACHE and os.path.exists(AUG_CACHE):
        try:
            ac = json.load(open(AUG_CACHE))
            age = time.time() - ac.get("filtered_at", 0)
            if age < CACHE_MAX_AGE:
                all_rows = ac["records"]
                total = ac.get("raw_total", len(all_rows))
                print("  [仓] 直接读8月切片缓存（%.0f 分钟前，跳过联网）行数=%d" % (age / 60, len(all_rows)))
            else:
                print("  [仓] 8月切片已过期(%.1f小时)，转读全量仓/联网" % (age / 3600))
        except Exception as e:
            print("  [仓] 8月切片读取失败，转全量仓: %s" % e)
    if USE_CACHE and not all_rows and os.path.exists(WAREHOUSE):
        try:
            wh = json.load(open(WAREHOUSE))
            age = time.time() - wh.get("fetched_at", 0)
            if age < CACHE_MAX_AGE:
                all_rows = wh["records"]
                total = len(all_rows)
                print("  [仓] 直接读本地仓（%.0f 分钟前抓取，跳过联网）行数=%d" % (age / 60, total))
            else:
                print("  [仓] 已过期(%.1f小时)，转联网重抓" % (age / 3600))
        except Exception as e:
            print("  [仓] 读取失败，转联网: %s" % e)

    # ---- 联网拉全量（仅仓缺失/过期时）----
    if not all_rows:
        page = 1
        while True:
            st, j = None, None
            for attempt in range(1, 4):
                try:
                    st, j = post_report_list(ck, begin, end, page, page_size)
                    break
                except urllib.error.HTTPError as e:
                    sys.stderr.write("✗ HTTP_%d（登录态失效，需重新登录用友）\n" % e.code)
                    return 1
                except Exception as e:
                    if attempt < 3:
                        print("  [重试 %d/3] 页 %d 请求异常: %s" % (attempt, page, e))
                        time.sleep(3 * attempt)
                    else:
                        sys.stderr.write("✗ 请求异常(重试耗尽): %s\n" % e)
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
        # 去重（剔除 _YD 预订单 + 按 单号/SKU/序列号 去重）→ 与晨哥手工导出口径一致
        all_rows = dedup_records(all_rows)
        print("  [去重] 剔除 _YD 预订单 + (单号,SKU,序列号) 去重后 %d 行" % len(all_rows))
        # 写仓（全量，已去重）—— 供 --use-cache 毫秒级复用
        try:
            atomic_write_json(WAREHOUSE, {"fetched_at": time.time(), "records": all_rows})
            print("  [仓] 已写入仓库（%d 行）" % len(all_rows))
        except Exception as e:
            print("  [仓] 写仓失败(不影响本次): %s" % e)

    # 仅保留查询日期范围内的单据（按 dDate 单据日期，与毛利明细口径一致）
    # 用友 report/list 对 rm_saleanalysis 不识别日期参数，会返回该门店全部历史，故本地过滤。
    before = len(all_rows)
    all_rows = [r for r in all_rows if begin <= (r.get("dDate") or "")[:10] <= end]
    print("  [筛选] 按单据日期 %s~%s 保留 %d / %d 行" % (begin, end, len(all_rows), before))
    # 预存「8月李家村」切片，供 --use-cache 真毫秒级复用
    try:
        atomic_write_json(AUG_CACHE, {"filtered_at": time.time(), "begin": begin, "end": end,
                                      "raw_total": before, "records": all_rows})
        print("  [仓] 已写入8月切片缓存（%d 行）" % len(all_rows))
    except Exception as e:
        print("  [仓] 写8月切片失败(不影响本次): %s" % e)

    dt = time.time() - t0
    atomic_write_json(OUT_JSON, {"begin": begin, "end": end, "recordCount": len(all_rows),
                                 "records": all_rows})
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
        atomic_write_text(OUT_TSV, "\n".join(lines))

    print("✓ 销售分析(纯HTTP)已保存: %s" % OUT_JSON)
    print("  日期范围: %s ~ %s" % (begin, end))
    print("  明细行数: %d（本月，接口原始返回 %s）" % (len(all_rows), total))
    print("  [计时] 耗时: %.3fs" % dt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
