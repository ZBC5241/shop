#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""设 8-31，关闭日历，捕获所有 POST 请求，找真实数据端点。"""
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

def pick(pg, placeholder):
    pg.click(f'input[placeholder="{placeholder}"]')
    time.sleep(1.2)
    for _ in range(4):
        has = pg.evaluate("""()=>!!([...document.querySelectorAll('.wui-picker-date-panel')].find(p=>{const m=p.querySelector('.wui-picker-month-btn');return m&&m.innerText.includes('8月');}))""")
        if has: break
        prev=pg.query_selector('.wui-picker-header-prev-btn')
        if prev: prev.click(); time.sleep(1.0)
        else: break
    pg.evaluate("""() => {
        const panels=[...document.querySelectorAll('.wui-picker-date-panel')];
        const p=panels.find(x=>{const m=x.querySelector('.wui-picker-month-btn');return m&&m.innerText.includes('8月');});
        if(!p)return;
        const c=[...p.querySelectorAll('.wui-picker-cell')].find(c=>c.innerText.trim()==='31' && c.className.includes('wui-picker-cell-in-view'));
        if(c)c.click();
    }""")
    time.sleep(0.6); pg.keyboard.press('Escape'); time.sleep(0.6)

with sync_playwright() as p:
    b=p.chromium.launch(headless=True, executable_path=CHROME_PATH,
                        args=["--disable-blink-features=AutomationControlled"])
    ctx=b.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                      viewport={"width":1400,"height":900}, accept_downloads=True)
    pg=ctx.new_page()
    allreqs=[]
    pg.on("request", lambda r: allreqs.append((r.method, r.url, r.post_data)))
    if not do_login(pg): b.close(); raise SystemExit(1)
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception: ok=False
        if ok: break
        time.sleep(1)
    time.sleep(2)
    pick(pg, "开始"); pick(pg, "结束")
    print("日期:", pg.evaluate("""() => {const s=document.querySelector('input[placeholder=\"开始\"]');const e=document.querySelector('input[placeholder=\"结束\"]');return s.value+'~'+e.value}"""))
    # 强制关闭日历：点页面空白处
    pg.mouse.click(700, 500); time.sleep(0.5)
    pg.keyboard.press('Escape'); time.sleep(0.5)
    # 等查询
    for _ in range(25):
        time.sleep(2)
        # 看是否有表格
        try:
            n = pg.evaluate("() => {const ts=[...document.querySelectorAll('table')];let c=0;for(const t of ts){if((t.innerText||'').includes('零售单号'))c+=t.querySelectorAll('tbody tr').length;}return c;}")
        except Exception:
            n=0
        if n>0:
            print("表格行数:", n); break
    time.sleep(1)
    print("\n=== 全部 POST 请求(日期变更后) ===")
    posts=[(m,u,d) for m,u,d in allreqs if m=='POST']
    for m,u,d in posts:
        print(f"[{m}] {u}")
        if d: print("   body:", d[:500])
    b.close()
