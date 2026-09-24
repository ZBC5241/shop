#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""打开「商品收款查询」，点查询触发真实 report/list 请求，捕获正确参数后改日期重发。"""
import time, json
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd(), "label": "store"}
DATE = "2026-08-31"

REFETCH_JS = r'''async (args) => {
  try {
    const m=[...document.cookie.split(';')].map(c=>c.trim()).find(c=>c.startsWith('yht_access_token'));
    const token=m?decodeURIComponent(m.split('=').slice(1).join('=')):'';
    const r=await fetch(args.url,{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','yht_access_token':token,'X-Requested-With':'XMLHttpRequest'},body:args.body});
    const j=await r.json();
    const d=j.data||{};
    const rl=d.recordList||[];
    return {code:j.code, msg:j.message, recordCount:d.recordCount, rlLen:rl.length, fields:(rl[0]?Object.keys(rl[0]):[]), sample:rl.slice(0,3)};
  } catch(e){ return {ok:false, err:String(e)}; }
}'''


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
    captured = []

    def on_req(req):
        if req.method == "POST":
            try:
                captured.append((req.url, req.post_data))
            except Exception:
                pass

    pg.on("request", on_req)

    if not do_login(pg):
        b.close()
        raise SystemExit(1)

    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); }""")

    for _ in range(25):
        try:
            cnt = pg.evaluate("document.querySelectorAll('button.wui-dropdown-trigger.ana-header-dropdown-list').length")
        except Exception:
            cnt = 0
        if cnt >= 3:
            break
        time.sleep(1)
    time.sleep(3)

    # 枚举按钮，找查询
    btns = pg.evaluate("""()=>[...document.querySelectorAll('button')].map(x=>(x.innerText||'').trim().slice(0,20)).filter(Boolean)""")
    print("BUTTONS:", btns)

    clicked = pg.evaluate("""()=>{const bs=[...document.querySelectorAll('button')];const b=bs.find(x=>(x.innerText||'').includes('查询')||(x.innerText||'').includes('搜索'));if(b){b.click();return (b.innerText||'').trim();}return null}""")
    print("CLICKED QUERY:", clicked)

    # 轮询 report/list
    for _ in range(30):
        if any("report/list" in u for u, _ in captured):
            break
        time.sleep(1)

    hit = [(u, bd) for u, bd in captured if "report/list" in u]
    print("report/list captures:", len(hit))
    if hit:
        url, body = hit[-1]
        print("REPORT/LIST URL:", url)
        print("BODY:", (body or "")[:2500])
        try:
            bd = json.loads(body)
            for qp in bd.get("queryParams", []):
                nm = qp.get("name", "").lower()
                if "date" in nm or "日期" in nm or "time" in nm:
                    qp["value"] = DATE
            for k in ("beginDate", "endDate"):
                if k in bd:
                    bd[k] = DATE
            res = pg.evaluate(REFETCH_JS, {"url": url, "body": json.dumps(bd, ensure_ascii=False)})
            print("REFETCH RESULT:")
            print(json.dumps(res, ensure_ascii=False, indent=2)[:6000])
        except Exception as e:
            print("REFETCH ERR:", e)
    else:
        print("NO report/list. PAGE TEXT:", pg.evaluate("document.body.innerText.slice(0,500)"))
    b.close()
