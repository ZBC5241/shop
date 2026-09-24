#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""打开日清日结，用 playwright 原生 fill 精准设收款日期为 2026-08-31，拉表格。"""
import time, json
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd(), "label": "store"}
DATE = "2026-08-31"


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

    start = pg.query_selector('input[placeholder="开始"]')
    end = pg.query_selector('input[placeholder="结束"]')
    if start and end:
        start.fill(DATE)
        time.sleep(0.5)
        end.fill(DATE)
        time.sleep(0.5)
        print("filled start/end =", pg.evaluate("()=>{const i=[...document.querySelectorAll('input')];const s=i.find(e=>e.placeholder==='开始');const e=i.find(e=>e.placeholder==='结束');return (s?s.value:'?')+' ~ '+(e?e.value:'?')}"))
    else:
        print("DATE INPUTS NOT FOUND, start=", bool(start), "end=", bool(end))

    time.sleep(8)

    txt = pg.evaluate("document.body.innerText")
    print("=== PAGE TEXT (head) ===")
    print(txt[:1800])

    table = pg.evaluate("""()=>{
      const t=document.querySelector('table');
      if(!t) return {err:'NO TABLE'};
      const th=[...t.querySelectorAll('thead th, thead td')].map(x=>x.innerText.trim().replace(/\\n/g,' '));
      const trs=[...t.querySelectorAll('tbody tr')];
      const rows=trs.map(r=>[...r.querySelectorAll('td')].map(c=>c.innerText.trim().replace(/\\n/g,' ')));
      return {th, rowCount:rows.length, rows:rows.slice(0,40)};
    }""")
    print("=== TABLE ===")
    print(json.dumps(table, ensure_ascii=False, indent=2)[:12000])
    b.close()
