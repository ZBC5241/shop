#!/usr/bin/env python3
# fetch_yonyou_http.py —— 纯 HTTP 携带用友登录态直连 report/exec，免浏览器
# 登录态来源：agent-browser 持久化的 session 状态文件（含 yht_access_token / XSRF-TOKEN 等 cookie）
# 用法: python3 fetch_yonyou_http.py [输出TSV路径]
# 退出码: 0 成功 / 1 失败(含401需重登录)
import json, sys, time, os, urllib.request, urllib.error, ssl

YY_BASE = "https://c3.yonyoucloud.com"
YY_REPORT_ID = "a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"
DEFAULT_STATE = os.path.expanduser("~/.agent-browser/sessions/yonyou-default.json")
TSV = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "yonyou_raw.tsv")

def load_cookies(state_path):
    d = json.load(open(state_path))
    out = {}
    for c in d.get("cookies", []):
        if "yonyoucloud" in c.get("domain", "") and c.get("name") and c.get("value") is not None:
            out[c["name"]] = c["value"]
    return out

def parse_tsv(j):
    sh = j["data"]["analysisModel"]["sheets"][0]
    dd = sh["datas"][list(sh["datas"].keys())[0]]
    cells = dd["cells"]
    if not cells:
        return ""
    hdr = [c[0] if c else "" for c in cells[0]]
    hdr = [h for h in hdr if h != ""]
    n = len(hdr)
    rows = []
    for r in cells[1:]:
        if not r or not r[0] or not r[0][0]:
            continue
        row = [str(c[0]) if (c and c[0] is not None) else "" for c in r[:n]]
        rows.append(row)
    lines = ["\t".join(hdr)] + ["\t".join(r) for r in rows]
    return "\n".join(lines)

def main():
    state = os.environ.get("YONYOU_STATE", DEFAULT_STATE)
    if not os.path.exists(state):
        sys.stderr.write("✗ 找不到用友登录态文件: %s\n" % state)
        sys.stderr.write("  请先用 agent-browser 登录一次用友（fetch_all.sh 会处理），生成该状态文件。\n")
        return 1
    ck = load_cookies(state)
    need = ("yht_access_token", "yht_usertoken_diwork", "XSRF-TOKEN")
    missing = [k for k in need if k not in ck]
    if missing:
        sys.stderr.write("✗ 登录态缺少关键 cookie: %s\n" % ",".join(missing))
        return 1
    xsrf = ck.get("XSRF-TOKEN", "")
    yht = ck.get("yht_access_token", "")
    cookie_hdr = "; ".join("%s=%s" % (k, v) for k, v in ck.items())
    url = ("%s/iuap-data-analytic/report/exec/%s"
           "?isAjax=1&hb=close&systenant=U8C3&havePublishPermission=true&browse=true"
           "&newExec=true&sdkCode=%s&locale=zh_CN&serviceCode=%s") % (YY_BASE, YY_REPORT_ID, YY_REPORT_ID, YY_REPORT_ID)
    hdr = {
        "User-Agent": "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": YY_BASE,
        "Referer": YY_BASE + "/",
        "Cookie": cookie_hdr,
        "XSRF-TOKEN": xsrf,
        "yht_access_token": yht,
    }
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers=hdr, method="GET")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=40, context=ctx) as resp:
            body = resp.read()
            st = resp.status
    except urllib.error.HTTPError as e:
        sys.stderr.write("✗ HTTP_%d（登录态失效，需重新登录用友）\n" % e.code)
        return 1
    except Exception as e:
        sys.stderr.write("✗ 请求异常: %s\n" % e)
        return 1
    dt = time.time() - t0
    if st != 200:
        sys.stderr.write("✗ HTTP_%d\n" % st)
        return 1
    j = json.loads(body)
    if j.get("status") != 1:
        sys.stderr.write("✗ 接口返回异常: %s\n" % str(j.get("message"))[:200])
        return 1
    tsv = parse_tsv(j)
    with open(TSV, "w", encoding="utf-8") as f:
        f.write(tsv)
    lines = tsv.split("\n")
    dates = sorted({l.split("\t")[2] for l in lines[1:] if len(l.split("\t")) > 2 and l.split("\t")[2]})
    print("✓ 纯HTTP已保存: %s" % TSV)
    print("  明细行数: %d" % (len(lines) - 1))
    print("  日期范围: %s ~ %s" % (dates[0] if dates else "-", dates[-1] if dates else "-"))
    print("  [计时] 接口耗时: %.3fs" % dt)
    return 0

if __name__ == "__main__":
    sys.exit(main())
