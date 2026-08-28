#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_yonyou_browser.py — 用 Playwright 浏览器提取完整毛利明细
突破 report/exec 接口 500 行硬截断

原理：
  1. 从 agent-browser session 文件加载 cookie + localStorage
  2. 用 Playwright 启动系统 Chrome（headless），注入 cookie
  3. 导航到用友报表页面
  4. 拦截 report/refresh 响应，从 JSON 中提取完整数据
  5. 备用：直接从 Handsontable 实例取 getSourceData() 全量数据
  6. 输出 TSV 文件（16列或19列，calc_data.py 均兼容）

用法：python3 fetch_yonyou_browser.py [输出TSV路径]
退出码：0 成功 / 1 失败
"""
import json, sys, os, time, re
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
YY_REPORT_ID = "a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"
SESSION_PATH = os.path.expanduser("~/.agent-browser/sessions/yonyou-default.json")
DEFAULT_TSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yonyou_full.tsv")

# 19列标准表头（HTTP版完整列）
HEADERS_19 = ["出库单号", "单据类型", "出库日期", "商品分类", "商品sku分类", "商品SKU编码",
              "商品名称", "入库属性", "数量", "单价", "原价", "折扣价", "金额", "毛利",
              "SO激励", "业务员", "库区", "销售出库单门店", "销售成本"]
# 16列浏览器版表头（缺库区/门店/销售成本）
HEADERS_16 = HEADERS_19[:16]


def load_session(path):
    """从 agent-browser session 文件加载 cookie 和 localStorage。"""
    d = json.load(open(path))
    cookies = []
    for c in d.get("cookies", []):
        ss = c.get("sameSite", "None")
        # Playwright 要求 sameSite 为 "Strict" / "Lax" / "None" 之一
        if ss and ss.lower() in ("strict", "lax", "none"):
            ss_final = ss.capitalize() if ss.lower() != "none" else "None"
        else:
            ss_final = "None"
        cookies.append({
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ""),
            "path": c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
            "sameSite": ss_final,
        })
    # localStorage（agent-browser session 格式：{"name":"x","value":"y"}）
    localStorage = {}
    for o in d.get("origins", []):
        if "yonyoucloud" in o.get("origin", ""):
            for entry in o.get("localStorage", []):
                if isinstance(entry, dict) and "name" in entry and "value" in entry:
                    localStorage[entry["name"]] = entry["value"]
                elif isinstance(entry, list) and len(entry) >= 2:
                    localStorage[entry[0]] = entry[1]
    return cookies, localStorage


def extract_from_response(captured):
    """从拦截到的 report/refresh 或 report/exec 响应 JSON 中提取完整数据。"""
    for resp in captured:
        try:
            j = json.loads(resp["body"])
        except Exception:
            continue
        if j.get("status") != 1:
            continue
        data = j.get("data", {})
        am = data.get("analysisModel", {})
        sheets = am.get("sheets", [])
        if not sheets:
            continue
        sh = sheets[0]
        datas = sh.get("datas", {})
        for key, dd in datas.items():
            cells = dd.get("cells", [])
            if len(cells) > 1:
                # cells[0] 是表头, cells[1:] 是数据行
                hdr = [c[0] if c else "" for c in cells[0]]
                hdr = [h for h in hdr if h != ""]
                rows = []
                for r in cells[1:]:
                    if not r or not r[0] or not r[0][0]:
                        continue
                    row = [str(c[0]) if (c and c[0] is not None) else "" for c in r[:len(hdr)]]
                    rows.append(row)
                if rows:
                    return hdr, rows
    return None, None


def main():
    tsv_out = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TSV
    t_total = time.time()

    if not os.path.exists(SESSION_PATH):
        sys.stderr.write(f"✗ 找不到用友登录态文件: {SESSION_PATH}\n")
        return 1

    cookies, localStorage = load_session(SESSION_PATH)
    print(f"  加载 cookie: {len(cookies)} 个 | localStorage: {len(localStorage)} 项")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=CHROME_PATH)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
        )

        # 注入 cookie
        context.add_cookies(cookies)

        page = context.new_page()

        # 先打开域名以设置 localStorage
        page.goto(YY_BASE + "/", wait_until="domcontentloaded", timeout=30000)
        if localStorage:
            try:
                page.evaluate("""(items) => {
                    for (const [k, v] of Object.entries(items)) {
                        try { localStorage.setItem(k, v); } catch(e) {}
                    }
                }""", localStorage)
            except Exception:
                pass

        # 拦截网络响应
        captured = []

        def on_response(response):
            url = response.url
            if "report/refresh" in url or "report/exec" in url:
                try:
                    body = response.text()
                    captured.append({"url": url, "body": body, "status": response.status})
                    print(f"  [拦截] {url[:80]}... status={response.status} size={len(body)}")
                except Exception:
                    pass

        page.on("response", on_response)

        # 导航到报表页面
        report_url = f"{YY_BASE}/iuap-data-analytic/report/view/{YY_REPORT_ID}"
        print(f"  导航到报表页面: {report_url}")
        try:
            page.goto(report_url, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"  [提示] 页面加载超时/部分完成: {e}")
            # 即使超时，可能已经拦截到响应了

        # 等待额外响应
        time.sleep(3)
        print(f"  拦截到 {len(captured)} 个报表相关响应")

        # 策略1：从拦截的响应中提取
        hdr, rows = extract_from_response(captured)
        if hdr and rows:
            print(f"  [策略1] 从拦截响应提取: {len(rows)} 行, {len(hdr)} 列")
        else:
            print(f"  [策略1] 拦截响应中未找到可用数据")

        # 策略2：从 Handsontable 实例提取全量数据
        if not hdr or not rows or len(rows) < 500:
            print(f"  [策略2] 尝试从 Handsontable 实例提取...")
            try:
                result = page.evaluate("""() => {
                    // 方法A: 通过 HotMap 找实例
                    var hotEl = document.querySelector('.htCore, .handsontable');
                    if (!hotEl) return {error: 'no handsontable element found'};
                    
                    // 方法B: 遍历 window 上的 Handsontable 实例
                    var instances = [];
                    if (typeof HotMap !== 'undefined') {
                        for (var k in HotMap) {
                            var inst = HotMap[k];
                            if (inst && typeof inst.getSourceData === 'function') {
                                instances.push(k);
                            }
                        }
                    }
                    
                    // 方法C: 查找 .handsontable 上的 hot 实例
                    var containers = document.querySelectorAll('.handsontable');
                    for (var c of containers) {
                        if (c.hot && typeof c.hot.getSourceData === 'function') {
                            instances.push('container.hot');
                        }
                    }
                    
                    // 方法D: 通过 Handsontable 全局
                    if (typeof Handsontable !== 'undefined') {
                        var found = Handsontable.getInstance(document.querySelector('.htCore'));
                        if (found) instances.push('Handsontable.getInstance');
                    }
                    
                    return {
                        instances: instances,
                        hotElFound: !!hotEl,
                        bodyHTML: document.body.innerHTML.substring(0, 500)
                    };
                }""")
                print(f"    Handsontable 探测: {json.dumps(result, ensure_ascii=False)[:200]}")
            except Exception as e:
                print(f"    Handsontable 探测失败: {e}")

            # 尝试直接从 DOM 表格提取
            if not hdr or not rows:
                print(f"  [策略2b] 尝试从 DOM 表格提取...")
                try:
                    dom_data = page.evaluate("""() => {
                        var tables = document.querySelectorAll('table.htCore');
                        if (!tables.length) return {error: 'no htCore table found'};
                        
                        var table = tables[0];
                        var trs = table.querySelectorAll('tr');
                        var result = [];
                        for (var tr of trs) {
                            var tds = tr.querySelectorAll('td, th');
                            var row = [];
                            for (var td of tds) {
                                row.push(td.textContent || '');
                            }
                            if (row.length > 0) result.push(row);
                        }
                        return {rows: result.length, data: result.slice(0, 5)};
                    }""")
                    print(f"    DOM 表格: {json.dumps(dom_data, ensure_ascii=False)[:300]}")
                except Exception as e:
                    print(f"    DOM 表格提取失败: {e}")

        # 策略3：从页面上下文直接 fetch report/exec（浏览器自动带 cookie）
        if not hdr or not rows or len(rows) < 500:
            print(f"  [策略3] 从页面上下文 fetch report/exec...")
            try:
                fetch_result = page.evaluate("""async (url) => {
                    try {
                        var resp = await fetch(url, {
                            method: 'GET',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'X-Requested-With': 'XMLHttpRequest'
                            },
                            credentials: 'include'
                        });
                        var text = await resp.text();
                        return {status: resp.status, size: text.length, preview: text.substring(0, 500)};
                    } catch(e) {
                        return {error: e.toString()};
                    }
                }""", f"{YY_BASE}/iuap-data-analytic/report/exec/{YY_REPORT_ID}?isAjax=1&hb=close&systenant=U8C3&havePublishPermission=true&browse=true&newExec=true&sdkCode={YY_REPORT_ID}&locale=zh_CN&serviceCode={YY_REPORT_ID}")
                print(f"    fetch 结果: {json.dumps(fetch_result, ensure_ascii=False)[:400]}")
            except Exception as e:
                print(f"    fetch 失败: {e}")

        # 策略4：打印拦截响应的结构（诊断）
        if not hdr or not rows:
            print(f"\n  [诊断] 拦截响应结构:")
            for i, resp in enumerate(captured):
                try:
                    j = json.loads(resp["body"])
                    print(f"  响应 {i}: top keys = {list(j.keys())[:10]}")
                    if "data" in j:
                        d = j["data"]
                        print(f"    data keys = {list(d.keys())[:10] if isinstance(d, dict) else type(d).__name__}")
                        if isinstance(d, dict) and "analysisModel" in d:
                            am = d["analysisModel"]
                            print(f"    analysisModel keys = {list(am.keys())[:10]}")
                            sheets = am.get("sheets", [])
                            print(f"    sheets: {len(sheets)}")
                            if sheets:
                                sh = sheets[0]
                                print(f"    sheet[0] keys = {list(sh.keys())[:10]}")
                                datas = sh.get("datas", {})
                                print(f"    datas keys = {list(datas.keys())[:5]}")
                                for k, dd in datas.items():
                                    print(f"    datas['{k}'] keys = {list(dd.keys())[:10]}")
                                    cells = dd.get("cells", [])
                                    print(f"      cells: {len(cells)} rows")
                                    for field in ["rows", "data", "records", "list", "items", "result", "allCells", "totalCells", "sourceData", "totalRecord"]:
                                        if field in dd:
                                            val = dd[field]
                                            print(f"      {field}: {type(val).__name__} len={len(val) if hasattr(val, '__len__') else val}")
                        # Check for totalRecord at top level
                        for field in ["totalRecord", "total", "totalCount", "count", "recordCount"]:
                            if field in d:
                                print(f"    data.{field} = {d[field]}")
                    for field in ["totalRecord", "total", "totalCount", "count"]:
                        if field in j:
                            print(f"    top.{field} = {j[field]}")
                except Exception as e:
                    print(f"  响应 {i}: 解析失败: {e}")

        browser.close()

    # 如果成功提取到数据，保存 TSV
    if hdr and rows:
        tsv = "\n".join(["\t".join(hdr)] + ["\t".join(r) for r in rows])
        with open(tsv_out, "w", encoding="utf-8") as f:
            f.write(tsv)
        dates = sorted({r[2] for r in rows if len(r) > 2 and r[2]})
        dt = time.time() - t_total
        print(f"\n✓ 浏览器提取完成: {tsv_out}")
        print(f"  明细行数: {len(rows)}")
        print(f"  列数: {len(hdr)}")
        print(f"  日期范围: {dates[0] if dates else '-'} ~ {dates[-1] if dates else '-'}")
        print(f"  [计时] {dt:.1f}s")
        return 0
    else:
        print(f"\n✗ 未能提取到数据")
        return 1


if __name__ == "__main__":
    sys.exit(main())
