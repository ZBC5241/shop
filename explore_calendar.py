#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""打开日清日结，点击日期 input 弹出日历，打印日历 DOM 结构以便精准选择 8-31。"""
import time, json
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

    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); }""")
    for _ in range(25):
        try:
            ok = pg.evaluate("document.body.innerText.includes('收款日期')")
        except Exception:
            ok = False
        if ok:
            break
        time.sleep(1)
    time.sleep(3)

    # 点击开始日期框
    start = pg.query_selector('input[placeholder="开始"]')
    if start:
        start.click()
        time.sleep(2)
        print("clicked 开始 input")
    else:
        print("开始 input not found")

    # 探测日历 DOM
    cal = pg.evaluate("""() => {
      const safe=(s)=> s? (''+s).replace(/\\n/g,' ').trim().slice(0,200) : '';
      const picks=[...document.querySelectorAll('[class*="picker"],[class*="calendar"],[class*="panel"],[class*="Panel"],[class*="dropdown"]')];
      const info=picks.slice(0,8).map(el=>({cls:el.className?el.className.toString().slice(0,60):'', text:safe(el.innerText)}));
      const btns=[...document.querySelectorAll('button')].map(x=>safe(x.innerText)).filter(Boolean).slice(0,40);
      const tds=[...document.querySelectorAll('td')].map(x=>safe(x.innerText)).filter(t=>/^\\d{1,2}$/.test(t)).slice(0,40);
      return {picks:info, btns, tds};
    }""")
    print("PICKERS:", json.dumps(cal["picks"], ensure_ascii=False))
    print("BUTTONS:", cal["btns"])
    print("DATE_TDS:", cal["tds"])
    b.close()
