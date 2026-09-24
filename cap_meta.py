#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""捕获 报表打开时的过滤元数据响应，提取日期字段 itemName。"""
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
    meta_resp={}
    def on_res(r):
        u=r.url
        if 'getInitFilterInfo' in u or 'getSolutionList' in u or 'filterDesign' in u or 'getFilterInfo' in u:
            try: body=r.body()
            except Exception: body=b''
            meta_resp[u]=body.decode('utf-8','ignore')
    pg.on("response", on_res)
    if not do_login(pg): b.close(); raise SystemExit(1)
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception: ok=False
        if ok: break
        time.sleep(1)
    time.sleep(4)

    for u,body in meta_resp.items():
        print("\n##### URL:", u)
        print(body[:4000])
    b.close()
