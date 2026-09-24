#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""捕获 商品收款查询 的查询按钮 + 真实 bill/list 请求与响应。"""
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
    reqs=[]; resps=[]
    def on_req(r):
        if 'rm_goodsgatherreport' in r.url and 'bill/list' in r.url:
            reqs.append((r.url, r.post_data))
    def on_res(r):
        if 'rm_goodsgatherreport' in r.url and 'bill/list' in r.url:
            try: body=r.body()
            except Exception: body=b''
            resps.append((r.status, body[:2000]))
    pg.on("request", on_req); pg.on("response", on_res)

    if not do_login(pg): b.close(); raise SystemExit(1)
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception: ok=False
        if ok: break
        time.sleep(1)
    time.sleep(2)

    # 列出报表区所有按钮
    btns = pg.evaluate("""() => {
        const all=[...document.querySelectorAll('button')];
        return all.map(x=>({t:(x.innerText||'').trim().slice(0,12), cls:(x.className||'').toString().slice(0,40), fid:x.getAttribute('fieldid')||''})).filter(x=>x.t);
    }""")
    print("=== 页面按钮(含零售单号相关区) ===")
    print(json.dumps(btns, ensure_ascii=False, indent=1))

    # 尝试点 查询/搜索 按钮
    clicked=None
    for cand in ['查询','搜索','刷新','检索']:
        for x in btns:
            if x['t']==cand:
                pg.evaluate(f"""() => {{ const bs=[...document.querySelectorAll('button')]; const t=bs.find(b=>(b.innerText||'').trim()==='{cand}'); if(t) t.click(); }}""")
                clicked=cand; break
        if clicked: break
    print("点击查询按钮:", clicked)
    time.sleep(5)

    print("\n=== 捕获到的 rm_goodsgatherreport bill/list 请求 ===")
    for u,d in reqs:
        print("URL:", u)
        print("BODY:", d)
    print("\n=== 响应(前2) ===")
    for st,body in resps[:2]:
        print("STATUS:", st)
        print("BODY[:2000]:", body.decode('utf-8','ignore'))

    with open("/Users/mac/WorkBuddy/2026-08-13-12-21-50/捕获_0831.txt","w") as f:
        f.write("REQS:\n")
        for u,d in reqs: f.write(u+"\n"+str(d)+"\n\n")
        f.write("RESPS:\n")
        for st,body in resps[:3]: f.write(f"status={st}\n"+body.decode('utf-8','ignore')+"\n\n")
    b.close()
