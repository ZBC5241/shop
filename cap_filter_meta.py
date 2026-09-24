# -*- coding: utf-8 -*-
from yonyou_cred import get_yonyou_pwd
"""复刻 cap_meta.py 成功路径：登录 → 点击 recent-报表 → 等'零售单号'出现 → 捕获 getInitFilterInfo 响应 → 解析全部筛选字段。"""
import time, json, re
from playwright.sync_api import sync_playwright

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY = "https://c3.yonyoucloud.com"
ACCT = "18161914293"
PWD = get_yonyou_pwd()
REPORT_ID = "rm_goodsgatherreport"

def do_login(page):
    page.goto(YY, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    try:
        b = page.query_selector(".button_accept")
        if b: b.click(); time.sleep(1)
    except: pass
    lf=None
    for f in page.frames:
        if "euc.yonyoucloud.com" in (f.url or ""): lf=f; break
    if not lf:
        time.sleep(5)
        for f in page.frames:
            if "euc.yonyoucloud.com" in (f.url or ""): lf=f; break
    if not lf: print("NO_LOGIN_FRAME"); return False
    lf.fill("#username", ACCT); time.sleep(0.3)
    lf.fill("#password", PWD); time.sleep(0.3)
    lf.click("#submit_btn_login")
    for _ in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower(): break
    time.sleep(3)
    print("LOGGED_IN"); return True

def main():
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True, executable_path=CHROME,
                            args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        pg=b.new_page()
        meta_resp={}
        captured_urls=[]
        def on_res(r):
            u=r.url
            if 'Filter' in u or 'filter' in u:
                captured_urls.append(u)
                if 'getInitFilterInfo' in u and REPORT_ID in u:
                    try: meta_resp[u]=r.text()
                    except Exception: pass
        pg.on("response", on_res)
        if not do_login(pg): b.close(); return

        pg.evaluate(f"""() => {{ const el=document.getElementById('recent-{REPORT_ID}'); if(el) el.click(); else {{ const f=document.getElementById('favor-{REPORT_ID}'); if(f) f.click(); }} }}""")
        opened=False
        for _ in range(25):
            try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
            except Exception: ok=False
            if ok: opened=True; break
            time.sleep(1)
        print("REPORT_OPENED" if opened else "REPORT_NOT_OPENED")
        time.sleep(4)
        # 兜底：若没抓到元数据，reload 强制重发
        if not meta_resp:
            print("RELOAD to force refetch...")
            pg.reload(wait_until="domcontentloaded")
            time.sleep(8)
            for _ in range(15):
                try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
                except Exception: ok=False
                if ok: break
                time.sleep(1)

        print("CAPTURED_URLS:")
        for u in captured_urls: print("  ", u)

        for u,body in meta_resp.items():
            with open("/Users/mac/WorkBuddy/2026-08-13-12-21-50/filter_meta_raw.json","w") as f:
                f.write(body)
            print("\n##### captured URL:", u)
            try:
                j=json.loads(body)
                def deep(o):
                    if isinstance(o,dict):
                        for k,v in o.items():
                            if k=="CommonModel": return v
                            r=deep(v)
                            if r: return r
                    elif isinstance(o,list):
                        for it in o:
                            r=deep(it)
                            if r: return r
                    return None
                cm=deep(j)
                items=cm if isinstance(cm,list) else []
                print(f"=== CommonModel 共 {len(items)} 项 ===")
                for it in items:
                    nm=it.get("itemName"); cap=it.get("itemTitle")
                    ctrl=it.get("ctrlType"); cmp=it.get("compareLogic"); rt=it.get("cRefType","")
                    print(f"  itemName={nm:<30} caption={cap:<16} ctrl={ctrl:<14} cmp={cmp} ref={rt}")
            except Exception as e:
                print("PARSE_ERR", e)
                names=re.findall(r'"itemName":"([^"]+)"', body)
                caps=re.findall(r'"itemTitle":"([^"]+)"', body)
                for n,c in zip(names,caps): print("  ",n,"=",c)
        b.close()

main()
