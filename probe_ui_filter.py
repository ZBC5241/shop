#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""直接打开商品收款查询 UI，设筛选条件 + 看页面渲染后的数据（按浏览器实际口径）。"""
import time, json
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd()}
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
    b=p.chromium.launch(headless=False, executable_path=CHROME_PATH,
                        args=["--disable-blink-features=AutomationControlled","--start-maxless=new_page"])
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
    # 设置日期 8-28
    pg.evaluate("""() => {
        const inputs=document.querySelectorAll('input[placeholder="开始"]');
        const setVal=(el,v)=>{const desc=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value');desc.set.call(el,v);el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));};
        setVal(inputs[0],'2026-08-28'); setVal(inputs[1],'2026-08-28');
    }""")
    time.sleep(3)
    # 截图保存
    pg.screenshot(path="/Users/mac/WorkBuddy/2026-08-13-12-21-50/0828_ui_filter.png", full_page=True)
    # 取页面顶部数据卡内容
    body_text = pg.evaluate("document.body.innerText")[:2000]
    print("--- 页面顶部文本 ---")
    print(body_text)
    b.close()