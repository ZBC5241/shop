#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""诊断：8-31 商品收款查询 实际渲染结构与数据端点。"""
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
    print("=== 报表打开(默认日期) ===")

    # 默认日期下先诊断结构 + 抓端点
    diag = pg.evaluate("""() => {
        const tables=[...document.querySelectorAll('table')];
        const tblInfo=tables.map(t=>({rows:t.querySelectorAll('tbody tr').length, head:(t.innerText||'').slice(0,120).replace(/\\n/g,' ')}));
        // 找含 零售单号 的容器
        let host=null;
        const all=[...document.querySelectorAll('*')];
        for(const e of all){ if((e.innerText||'').includes('零售单号') && e.children.length<30){ host=e; break; } }
        return {tableCount:tables.length, tblInfo,
                bodyPreview: document.body.innerText.replace(/\\n/g,' ').slice(0,300),
                totalMatch: (document.body.innerText.match(/共\\s*\\d+\\s*条/)||[''])[0]};
    }""")
    print(json.dumps(diag, ensure_ascii=False, indent=2))

    print("\n=== 默认日期已捕获请求(数据相关) ===")
    for m,u,d in allreqs:
        if any(k in u for k in ['bill','report','list','query','gather','analysis']):
            print(f"[{m}] {u}")
            if d: print("   body:", d[:300])

    b.close()
