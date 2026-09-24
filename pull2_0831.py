#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""拉 8-31 日清日结：显式设置 开始/结束 两输入框，捕获 report/list 响应。"""
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
    pg.evaluate("""()=>{const p=[...document.querySelectorAll('.wui-picker-date-panel')].find(x=>{const m=x.querySelector('.wui-picker-month-btn');return m&&m.innerText.includes('8月');});if(!p)return;const c=[...p.querySelectorAll('.wui-picker-cell')].find(c=>c.innerText.trim()==='31'&&!c.className.includes('disabled'));if(c)c.click();}""")
    time.sleep(0.5)
    pg.keyboard.press('Escape')
    time.sleep(0.6)

with sync_playwright() as p:
    b=p.chromium.launch(headless=True, executable_path=CHROME_PATH,
                        args=["--disable-blink-features=AutomationControlled"])
    ctx=b.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                      viewport={"width":1400,"height":900}, accept_downloads=True)
    pg=ctx.new_page()
    reqs=[]; resps=[]
    pg.on("request", lambda r: (reqs.append((r.url,r.post_data)) if ('report/list' in r.url or ('retailweb' in r.url and 'report' in r.url)) else None))
    pg.on("response", lambda r: (resps.append((r.url, r.status, r.body() if r.body() else b'')) if ('report/list' in r.url or ('retailweb' in r.url and 'report' in r.url)) else None))

    if not do_login(pg): b.close(); raise SystemExit(1)
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception: ok=False
        if ok: break
        time.sleep(1)
    time.sleep(2)

    pick(pg, "开始")
    pick(pg, "结束")
    # 读日期输入框值
    vals = pg.evaluate("""() => {
        const s=document.querySelector('input[placeholder=\"开始\"]'); const e=document.querySelector('input[placeholder=\"结束\"]');
        return {start:s?s.value:'?', end:e?e.value:'?'};
    }""")
    print("日期输入值:", vals)

    # 等自动重查
    for _ in range(30):
        time.sleep(2)
        if reqs: break
    time.sleep(2)

    print("\n=== report/list 请求 ===")
    for u,d in reqs:
        print("URL:", u)
        print("BODY:", d)

    print("\n=== report/list 响应(前2) ===")
    for u,st,body in resps[:2]:
        print("URL:", u, "STATUS:", st)
        txt=body.decode('utf-8','ignore')
        print("BODY[:3000]:", txt[:3000])

    # 也读渲染表
    grid = pg.evaluate("""() => {
        const tables=[...document.querySelectorAll('table')];
        let t=null;
        for(const x of tables){ if((x.innerText||'').includes('零售单号')){t=x;break;} }
        if(!t) return {err:'NO_TABLE', tableCount:tables.length};
        const headerCells=[...t.querySelectorAll('thead th, thead td')].map(th=>th.innerText.trim());
        const rows=[...t.querySelectorAll('tbody tr')];
        const idxNo=headerCells.findIndex(h=>h.includes('零售单号'));
        const idxAmt=headerCells.findIndex(h=>h==='金额'||h.includes('金额'));
        const idxRetailAmt=headerCells.findIndex(h=>h.includes('零售金额'));
        const idxPay=headerCells.findIndex(h=>h.includes('收款方式')||h.includes('收款')||h.includes('结算')||h.includes('支付')||h.includes('币')||h.includes('方式'));
        const orderSet=new Set(); const guobuOrders=new Set();
        let amtSum=0, retailAmtSum=0;
        for(const r of rows){
            const cells=[...r.querySelectorAll('td')].map(c=>c.innerText.trim());
            const no=idxNo>=0?cells[idxNo]:'';
            if(no) orderSet.add(no);
            if(idxAmt>=0){const v=parseFloat((cells[idxAmt]||'').replace(/[,¥\\s]/g,''));if(!isNaN(v))amtSum+=v;}
            if(idxRetailAmt>=0){const v=parseFloat((cells[idxRetailAmt]||'').replace(/[,¥\\s]/g,''));if(!isNaN(v))retailAmtSum+=v;}
            if(idxPay>=0&&(cells[idxPay]||'').includes('国补')&&no) guobuOrders.add(no);
        }
        let footer=''; const frow=t.querySelector('tfoot tr'); if(frow) footer=frow.innerText.replace(/\\n/g,' ').trim();
        return {headerCells, rowCount:rows.length, orderCount:orderSet.size,
                amtSum:Math.round(amtSum*100)/100, retailAmtSum:Math.round(retailAmtSum*100)/100,
                guobuOrderCount:guobuOrders.size, footer, payColFound:idxPay>=0};
    }""")
    print("\n=== 渲染表指标 ===")
    print(json.dumps(grid, ensure_ascii=False, indent=2))

    with open("/Users/mac/WorkBuddy/2026-08-13-12-21-50/日清日结_0831_raw.json","w") as f:
        reqs_out = [ (u, (d or '')[:600]) for (u, d) in reqs ]
        resps_out = [ (u, st, body.decode('utf-8','ignore')[:3000]) for (u, st, body) in resps ][:2]
        json.dump({"dateVals":vals,"reqs":reqs_out, "resps":resps_out, "grid":grid}, f, ensure_ascii=False, indent=2)
    b.close()
