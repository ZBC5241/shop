#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""精细探测日清日结日历面板：找月份切换箭头 + 日期格子 class。"""
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

    pg.query_selector('input[placeholder="开始"]').click()
    time.sleep(2)

    info = pg.evaluate("""()=>{
      const cells=[...document.querySelectorAll('td')];
      if(!cells.length) return {err:'no td'};
      let root=cells[0].parentElement;
      while(root && !(root.innerText||'').includes('2026')) root=root.parentElement;
      if(!root) return {err:'no root with 2026'};
      const btns=[...root.querySelectorAll('button')].map(b=>({cls:b.className?b.className.toString().slice(0,50):'',t:(b.innerText||'').trim().slice(0,10),aria:b.getAttribute('aria-label')||''}));
      const arrows=[...root.querySelectorAll('[class*="prev"],[class*="next"],[class*="arrow"],[class*="left"],[class*="right"],[class*="super"],[class*="Year"],[class*="Month"]')].map(e=>({tag:e.tagName,cls:e.className?e.className.toString().slice(0,50):'',t:(e.innerText||'').trim().slice(0,10),aria:e.getAttribute('aria-label')||''}));
      const tdcls=[...new Set(cells.slice(0,4).map(c=>c.className?c.className.toString().slice(0,60):''))];
      return {rootCls:root.className?root.className.toString().slice(0,70):'', head:root.innerText.replace(/\\n/g,' ').slice(0,90), btns, arrows, tdcls};
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=2))

    # 尝试点第一个 prev-like 元素，看月份是否变化
    tried = pg.evaluate("""()=>{
      const cells=[...document.querySelectorAll('td')];
      let root=cells[0].parentElement;
      while(root && !(root.innerText||'').includes('2026')) root=root.parentElement;
      if(!root) return 'no root';
      const prev=root.querySelector('[class*="prev"],[class*="left"],[class*="arrow"]');
      if(prev){prev.click();return 'clicked '+prev.className;}
      return 'no prev element';
    }""")
    print("TRIED PREV:", tried)
    time.sleep(1)
    head2 = pg.evaluate("""()=>{const cells=[...document.querySelectorAll('td')];let root=cells[0].parentElement;while(root && !(root.innerText||'').includes('2026')) root=root.parentElement;return root?root.innerText.replace(/\\n/g,' ').slice(0,90):'none'}""")
    print("HEAD AFTER PREV:", head2)
    b.close()
