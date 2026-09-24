#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""打开日清日结，用日历选 2026-08-31（开始+结束），触发查询并读取表格。"""
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


def month_text(pg):
    return pg.evaluate("""()=>{const r=document.querySelector('.yxy_rangepicker_design');return r?r.innerText.replace(/\\n/g,' '):''}""")


def click_prev(pg):
    return pg.evaluate("""()=>{
      const root=document.querySelector('.yxy_rangepicker_design');if(!root)return false;
      const cands=[...root.querySelectorAll('button,[class*="prev"],[class*="last"],[class*="arrow"],[class*="left"]')];
      const arr=cands.filter(el=>{const t=(el.innerText||'').trim();return t===''||t.length<=2;});
      if(arr[0]){arr[0].click();return true;}
      return false;
    }""")


def click_31(pg):
    return pg.evaluate("""()=>{
      const root=document.querySelector('.yxy_rangepicker_design');if(!root)return false;
      const cells=[...root.querySelectorAll('td,[class*="cell"]')];
      const t31=cells.filter(c=>(c.innerText||'').trim()==='31');
      if(t31[0]){t31[0].click();return true;}
      return false;
    }""")


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

    # 点开始 input 弹出日历
    start = pg.query_selector('input[placeholder="开始"]')
    start.click()
    time.sleep(2)

    # 切到 8 月
    for _ in range(3):
        mt = month_text(pg)
        if "8月" in mt and "9月" in mt:
            break
        click_prev(pg)
        time.sleep(1)
    print("MONTH AFTER PREV:", month_text(pg)[:80])

    # 选开始 31
    print("click 31 (start):", click_31(pg))
    time.sleep(1)
    # 选结束 31（日历仍在，处于选结束态，应仍在 8 月）
    mt2 = month_text(pg)
    print("MONTH before end-select:", mt2[:80])
    if "8月" not in mt2:
        for _ in range(3):
            if "8月" in mt2 and "9月" in mt2:
                break
            click_prev(pg)
            time.sleep(1)
            mt2 = month_text(pg)
    print("click 31 (end):", click_31(pg))
    time.sleep(1)
    pg.keyboard.press("Escape")
    time.sleep(1)

    rng = pg.evaluate("""()=>{const i=[...document.querySelectorAll('input')];const s=i.find(e=>e.placeholder==='开始');const e=i.find(e=>e.placeholder==='结束');return (s?s.value:'?')+' ~ '+(e?e.value:'?')}""")
    print("DATE RANGE:", rng)

    time.sleep(8)
    txt = pg.evaluate("document.body.innerText")
    print("=== PAGE TEXT ===")
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
