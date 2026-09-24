#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""用正确 body（condition.commonVOs + 业务日期）直接查 report/list 8-31。"""
import time, json
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd()}

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
    if not lf: print("NO_LOGIN_FRAME"); return False
    lf.fill("#username", account["username"]); time.sleep(0.3)
    lf.fill("#password", account["password"]); time.sleep(0.3)
    lf.click("#submit_btn_login")
    for _ in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower(): break
    time.sleep(3)
    print("LOGGED_IN"); return True

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

    cands = [
        {"billnum":"rm_goodsgatherreport","condition":{"commonVOs":[{"itemName":"业务日期","value1":"2026-08-31 00:00:00","value2":"2026-08-31 23:59:59"}]},"page":{"pageSize":1000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"},
        {"billnum":"rm_goodsgatherreport","condition":{"commonVOs":[{"itemName":"业务日期","value1":"2026-08-31","value2":"2026-08-31"}]},"page":{"pageSize":1000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"},
    ]
    for i,cand in enumerate(cands):
        res = pg.evaluate("""async (body) => {
            try {
                const r=await fetch('/yonbip-mkt-retailweb/report/list?terminalType=1&serviceCode=rm_goodsgatherreport&locale=zh_CN',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                const t=await r.text();
                return {status:r.status, text:t};
            } catch(e){ return {err:String(e)}; }
        }""", cand)
        print(f"\n=== candidate {i} ===")
        print("status:", res.get("status"), "err:", res.get("err"))
        txt = res.get("text","")
        try:
            j = json.loads(txt)
            print("code:", j.get("code"), "message:", j.get("message"))
            # 打印结构
            if j.get("code")==200:
                print("top keys:", list(j.keys()))
                data = j.get("data")
                if isinstance(data, dict):
                    print("data keys:", list(data.keys()))
                    rows = data.get("rows") or data.get("list") or data.get("data")
                    if rows is not None:
                        print("rows count:", len(rows))
                        if rows: print("first row keys:", list(rows[0].keys()) if isinstance(rows[0],dict) else type(rows[0]))
                else:
                    print("data type:", type(data))
            else:
                print("full:", txt[:800])
        except Exception as e:
            print("parse err:", e, "raw:", txt[:800])
        if res.get("status")==200 and '"code":200' in txt:
            with open("/Users/mac/WorkBuddy/2026-08-13-12-21-50/日清日结_0831_api.json","w") as f:
                f.write(txt)
            print(">>> 已保存完整响应到 日清日结_0831_api.json")
            break
    b.close()
