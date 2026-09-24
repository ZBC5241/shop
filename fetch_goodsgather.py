#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""拉取「商品收款查询」(rm_goodsgatherreport) 指定日期数据，探查字段结构。"""
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
    time.sleep(3)

    js = r'''async () => {
      try {
        const url='https://c3.yonyoucloud.com/yonbip-mkt-retailweb/report/list';
        const m=[...document.cookie.split(';')].map(c=>c.trim()).find(c=>c.startsWith('yht_access_token'));
        const token=m?decodeURIComponent(m.split('=').slice(1).join('=')):'';
        const body={billnum:'rm_goodsgatherreport', page:{pageIndex:1,pageSize:5000}, queryParams:[{name:'beginDate',value:'DATE'},{name:'endDate',value:'DATE'}]};
        const r=await fetch(url,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','yht_access_token':token,'X-Requested-With':'XMLHttpRequest'},body:JSON.stringify(body)});
        const j=await r.json();
        const d=j.data||{};
        const rl=d.recordList||[];
        const topKeys=Object.keys(d);
        let fields=[];
        if(rl.length) fields=Object.keys(rl[0]);
        return {ok:true, code:j.code, msg:j.message, topKeys:topKeys, recordCount:d.recordCount, rlLen:rl.length, fields:fields, sample:rl.slice(0,3)};
      } catch(e){ return {ok:false, err:String(e)}; }
    }'''
    js = js.replace("DATE", DATE)
    j = pg.evaluate(js)
    print(json.dumps(j, ensure_ascii=False, indent=2)[:6000])
    b.close()
