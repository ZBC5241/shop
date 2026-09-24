#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""调试日历：逐步打印面板月份 + 输入值，最终触发 report/list。"""
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

def panels_info(pg):
    return pg.evaluate("""() => {
        const panels=[...document.querySelectorAll('.wui-picker-date-panel')];
        return panels.map(p=>{
            const y=p.querySelector('.wui-picker-year-btn'); const m=p.querySelector('.wui-picker-month-btn');
            return {y:y?y.innerText.trim():'', m:m?m.innerText.trim():''};
        });
    }""")

with sync_playwright() as p:
    b=p.chromium.launch(headless=True, executable_path=CHROME_PATH,
                        args=["--disable-blink-features=AutomationControlled"])
    ctx=b.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                      viewport={"width":1400,"height":900}, accept_downloads=True)
    pg=ctx.new_page()
    reqs=[]
    pg.on("request", lambda r: (reqs.append((r.url,r.post_data)) if 'report/list' in r.url else None))
    if not do_login(pg): b.close(); raise SystemExit(1)
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception: ok=False
        if ok: break
        time.sleep(1)
    time.sleep(2)
    print("初始输入值:", pg.evaluate("""() => {const s=document.querySelector('input[placeholder=\"开始\"]');const e=document.querySelector('input[placeholder=\"结束\"]');return {start:s?s.value:'?',end:e?e.value:'?'}}"""))

    # 点开始输入
    pg.click('input[placeholder="开始"]'); time.sleep(1.5)
    print("点开始后 面板:", panels_info(pg))
    # 上一月
    prev=pg.query_selector('.wui-picker-header-prev-btn')
    if prev: prev.click(); time.sleep(1.2)
    print("点上一月后 面板:", panels_info(pg))
    # 在 8月 面板点 31
    r = pg.evaluate("""() => {
        const panels=[...document.querySelectorAll('.wui-picker-date-panel')];
        const p=panels.find(x=>{const m=x.querySelector('.wui-picker-month-btn');return m&&m.innerText.includes('8月');});
        if(!p) return 'no 8月 panel; panels='+JSON.stringify(panels.map(x=>x.querySelector('.wui-picker-month-btn')?.innerText));
        const c=[...p.querySelectorAll('.wui-picker-cell')].find(c=>c.innerText.trim()==='31'&&!c.className.includes('disabled'));
        if(c){c.click();return 'clicked 31 in 8月';}
        return 'no 31 cell';
    }""")
    print("点31结果:", r)
    time.sleep(0.8)
    print("点31后 开始输入值:", pg.evaluate("""() => {const s=document.querySelector('input[placeholder=\"开始\"]');return s?s.value:'?'}"""))
    print("点31后 面板(应仍在):", panels_info(pg))

    # 再点 31 (设结束)
    r2 = pg.evaluate("""() => {
        const panels=[...document.querySelectorAll('.wui-picker-date-panel')];
        const p=panels.find(x=>{const m=x.querySelector('.wui-picker-month-btn');return m&&m.innerText.includes('8月');});
        if(!p) return 'no 8月 panel after';
        const c=[...p.querySelectorAll('.wui-picker-cell')].find(c=>c.innerText.trim()==='31'&&!c.className.includes('disabled'));
        if(c){c.click();return 'clicked 31 end';}
        return 'no 31 cell end';
    }""")
    print("点31(结束)结果:", r2)
    time.sleep(1)
    print("最终输入值:", pg.evaluate("""() => {const s=document.querySelector('input[placeholder=\"开始\"]');const e=document.querySelector('input[placeholder=\"结束\"]');return {start:s?s.value:'?',end:e?e.value:'?'}}"""))

    # 等查询
    for _ in range(20):
        time.sleep(2)
        if reqs: break
    print("\n=== report/list 请求 ===")
    for u,d in reqs:
        print("URL:", u)
        print("BODY:", d)
    b.close()
