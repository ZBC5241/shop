#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""设好 8-31 后，列出全部按钮，点击 查询/搜索/刷新，捕获 report/list。"""
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
    pick(pg, "开始"); pick(pg, "结束")
    print("日期:", pg.evaluate("""() => {const s=document.querySelector('input[placeholder=\"开始\"]');const e=document.querySelector('input[placeholder=\"结束\"]');return s.value+'~'+e.value}"""))

    # 列出全部含 查询/搜索/刷新 的按钮
    btns = pg.evaluate("""() => {
        return [...document.querySelectorAll('button')].map(x=>({t:(x.innerText||'').trim(), fid:x.getAttribute('fieldid')||'', cls:(x.className||'').toString().slice(0,50)})).filter(x=>x.t);
    }""")
    print("全部按钮:", json.dumps(btns, ensure_ascii=False, indent=1))

    # 点击任何 查询/搜索/刷新
    for cand in ['查询','搜索','刷新','检索','确定']:
        hit = pg.evaluate(f"""() => {{ const bs=[...document.querySelectorAll('button')]; const t=bs.find(b=>(b.innerText||'').trim()==='{cand}'); if(t){{t.click();return true;}} return false; }}""")
        if hit:
            print("已点击:", cand); break
    time.sleep(6)
    print("\n=== report/list 请求 ===")
    for u,d in reqs:
        print("URL:", u); print("BODY:", d)
    b.close()
