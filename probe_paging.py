#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""拉 8-28 全量明细，分页 + 不同口径试一遍，验证 ¥13,215.05。"""
import time, json
from collections import defaultdict
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd()}
OUT_DIR = "/Users/mac/WorkBuddy/2026-08-13-12-21-50"
DATE = "2026-08-28"

def do_login(page):
    page.goto(YY_BASE, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    try:
        b = page.query_selector(".button_accept")
        if b: b.click(); time.sleep(1)
    except Exception: pass
    lf=None
    for f in page.frames:
        if "euc.yonyoucloud.com" in (f.url or ""): lf=f; break
    if not lf:
        time.sleep(5)
        for f in page.frames:
            if "euc.yonyoucloud.com" in (f.url or ""): lf=f; break
    if not lf: return False
    lf.fill("#username", account["username"]); time.sleep(0.3)
    lf.fill("#password", account["password"]); time.sleep(0.3)
    lf.click("#submit_btn_login")
    for _ in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower(): break
    time.sleep(3)
    return True

with sync_playwright() as p:
    b=p.chromium.launch(headless=True, executable_path=CHROME_PATH,
                        args=["--disable-blink-features=AutomationControlled"])
    ctx=b.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                      viewport={"width":1400,"height":900}, accept_downloads=True)
    pg=ctx.new_page()
    if not do_login(pg): b.close(); raise SystemExit(1)
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception: ok=False
        if ok: break
        time.sleep(1)
    time.sleep(2)

    # 尝试分页查询: pageSize=10, pageIndex=1,2 看 recordCount 和 recordList
    results = {}
    for page_size in [10, 20, 50, 100, 2000]:
        body = {"billnum":"rm_goodsgatherreport",
                "condition":{"commonVOs":[{"itemName":"gathervouchdate","value1":f"{DATE} 00:00:00","value2":f"{DATE} 23:59:59"}]},
                "page":{"pageSize":page_size,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"}
        res = pg.evaluate("""async (body) => {
            try {
                const r=await fetch('/yonbip-mkt-retailweb/report/list?terminalType=1&serviceCode=rm_goodsgatherreport&locale=zh_CN',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                return {status:r.status, text:await r.text()};
            } catch(e){ return {err:String(e)}; }
        }""", body)
        j=json.loads(res["text"])
        d=j["data"]
        results[page_size]={"recordCount":d.get("recordCount"),"pageCount":d.get("pageCount"),"pageIndex":d.get("pageIndex"),"pageSize":d.get("pageSize"),"rows":len(d.get("recordList") or [])}
    b.close()
print(json.dumps(results, ensure_ascii=False, indent=2))