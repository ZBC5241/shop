#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""枚举用友云工作台上的报表入口，定位「商品收款查询」报表 ID。"""
import time
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd(), "label": "store"}


def do_login(page):
    page.goto(YY_BASE, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    try:
        b = page.query_selector(".button_accept")
        if b:
            b.click()
            time.sleep(1)
    except Exception:
        pass
    lf = None
    for f in page.frames:
        if "euc.yonyoucloud.com" in (f.url or ""):
            lf = f
            break
    if not lf:
        time.sleep(5)
        for f in page.frames:
            if "euc.yonyoucloud.com" in (f.url or ""):
                lf = f
                break
    if not lf:
        print("NO_LOGIN_FRAME")
        return False
    lf.fill("#username", account["username"])
    time.sleep(0.3)
    lf.fill("#password", account["password"])
    time.sleep(0.3)
    lf.click("#submit_btn_login")
    for i in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower():
            break
    time.sleep(3)
    print("LOGGED_IN url=", page.url)
    return True


with sync_playwright() as p:
    b = p.chromium.launch(
        headless=True,
        executable_path=CHROME_PATH,
        args=["--disable-blink-features=AutomationControlled"],
    )
    ctx = b.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900},
        accept_downloads=True,
    )
    pg = ctx.new_page()
    if not do_login(pg):
        b.close()
        raise SystemExit(1)
    time.sleep(6)

    items = pg.evaluate(
        """() => {
        const res=[];
        document.querySelectorAll('[id]').forEach(el=>{
            const id=el.id||'';
            if(id.startsWith('recent-')||id.startsWith('favor-')||id.startsWith('report-')||id.startsWith('widget-')){
                const t=(el.innerText||'').trim().replace(/\\n/g,' ').slice(0,50);
                res.push(id+' || '+t);
            }
        });
        return res;
    }"""
    )
    print("=== RECENT/FAVOR/REPORT/WIDGET ELEMENTS (" + str(len(items)) + ") ===")
    for it in items:
        print(it)

    kws = pg.evaluate(
        """() => {
        const set=new Set();
        document.querySelectorAll('*').forEach(el=>{
            const t=(el.innerText||'').trim().replace(/\\s+/g,' ').slice(0,40);
            if(t && (t.includes('收款')||t.includes('商品收款')||t.includes('日清')||t.includes('日结')||t.includes('销售分析')||t.includes('毛利'))){
                set.add(t);
            }
        });
        return [...set].slice(0,80);
    }"""
    )
    print("=== 含关键词文本 (" + str(len(kws)) + ") ===")
    for k in kws:
        print(k)
    b.close()
