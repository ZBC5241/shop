#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""拉 9-01 和 8-28「国补专项」明细（财务-华为 + 国补POS挂账/补贴），看金额是否对得上图片 ¥7,786 / ¥13,215。"""
import time, json
from collections import defaultdict
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd()}
DATES = ["2026-09-01", "2026-08-28"]
OUT_DIR = "/Users/mac/WorkBuddy/2026-08-13-12-21-50"

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
    if not lf: return False
    lf.fill("#username", account["username"]); time.sleep(0.3)
    lf.fill("#password", account["password"]); time.sleep(0.3)
    lf.click("#submit_btn_login")
    for _ in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower(): break
    time.sleep(3)
    return True

with sync_playwright() as p:
    b=p.chromium.launch(headless=True, executable_path=CHROME_PATH,
                        args=["--disable-blink-features=AutomationControlled"])
    ctx=b.new_context(user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
                      viewport={"width":1400,"height":900}, accept_downloads=True)
    pg=ctx.new_page()
    if not do_login(pg): b.close(); raise SystemExit(1)
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try: ok=pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception: ok=False
        if ok: break
        time.sleep(1)
    time.sleep(2)

    # 尝试带分组条件：itemName=iGroupByGroup 或 groupCondition 之类 + 收款方式限定
    # 同时尝试不带分组的全量，对照图片金额
    cands = {}
    for d in DATES:
        cands[d] = [
            # 全量
            {"label":"all", "body": {"billnum":"rm_goodsgatherreport",
                "condition":{"commonVOs":[{"itemName":"gathervouchdate","value1":f"{d} 00:00:00","value2":f"{d} 23:59:59"}]},
                "page":{"pageSize":2000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"}},
            # 全量 + 收款方式=国补POS挂账
            {"label":"gb_pos", "body": {"billnum":"rm_goodsgatherreport",
                "condition":{"commonVOs":[
                    {"itemName":"gathervouchdate","value1":f"{d} 00:00:00","value2":f"{d} 23:59:59"},
                    {"itemName":"iPaymentid_name","value1":"国补POS挂账","value2":""},
                ]},
                "page":{"pageSize":2000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"}},
            # 全量 + 收款方式=国补补贴
            {"label":"gb_sub", "body": {"billnum":"rm_goodsgatherreport",
                "condition":{"commonVOs":[
                    {"itemName":"gathervouchdate","value1":f"{d} 00:00:00","value2":f"{d} 23:59:59"},
                    {"itemName":"iPaymentid_name","value1":"国补补贴","value2":""},
                ]},
                "page":{"pageSize":2000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"}},
            # 全量 + 财务-华为 (猜测 itemName=groupCondition)
            {"label":"fin_huawei", "body": {"billnum":"rm_goodsgatherreport",
                "condition":{"commonVOs":[
                    {"itemName":"gathervouchdate","value1":f"{d} 00:00:00","value2":f"{d} 23:59:59"},
                    {"itemName":"groupCondition","value1":"财务-华为","value2":""},
                ]},
                "page":{"pageSize":2000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"}},
            # 财务-华为 + 收款方式双选（猜测 value1=value2）
            {"label":"fin_huawei_gb", "body": {"billnum":"rm_goodsgatherreport",
                "condition":{"commonVOs":[
                    {"itemName":"gathervouchdate","value1":f"{d} 00:00:00","value2":f"{d} 23:59:59"},
                    {"itemName":"groupCondition","value1":"财务-华为","value2":""},
                    {"itemName":"iPaymentid_name","value1":"国补POS挂账,国补补贴","value2":""},
                ]},
                "page":{"pageSize":2000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"}},
        ]

    summary = {}
    for d in DATES:
        summary[d] = {}
        for cand in cands[d]:
            res = pg.evaluate("""async (body) => {
                try {
                    const r=await fetch('/yonbip-mkt-retailweb/report/list?terminalType=1&serviceCode=rm_goodsgatherreport&locale=zh_CN',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
                    const t=await r.text();
                    return {status:r.status, text:t};
                } catch(e){ return {err:String(e)}; }
            }""", cand["body"])
            txt=res.get("text","")
            try:
                j=json.loads(txt)
            except Exception:
                summary[d][cand["label"]] = {"err":"parse", "raw":txt[:300]}
                continue
            if j.get("code")!=200:
                summary[d][cand["label"]] = {"err":j.get("code"), "msg":j.get("message")}
                continue
            data=j["data"]
            rows=data.get("recordList") or []
            footer=(data.get("sumRecordList") or [{}])[0]
            codes=set(r["code"] for r in rows if r.get("code"))
            gb_pos=set(r["code"] for r in rows if r.get("iPaymentid_name")=="国补POS挂账")
            gb_sub=set(r["code"] for r in rows if r.get("iPaymentid_name")=="国补补贴")
            gb_total_money = sum(float(r.get("fMoney") or 0) for r in rows if r.get("iPaymentid_name") in ("国补POS挂账","国补补贴"))
            gb_total_qty = sum(float(r.get("fQuantity") or 0) for r in rows if r.get("iPaymentid_name") in ("国补POS挂账","国补补贴"))
            summary[d][cand["label"]] = {
                "rows":len(rows),
                "uniq_codes":len(codes),
                "footer_money":footer.get("fMoney"),
                "footer_quote":footer.get("fQuoteMoney"),
                "footer_discount":footer.get("fDiscount"),
                "gb_pos_codes":len(gb_pos),
                "gb_sub_codes":len(gb_sub),
                "gb_total_money":round(gb_total_money,2),
                "gb_total_qty":round(gb_total_qty,2),
                "pc_dist":{k:len(v) for k,v in defaultdict(set,( (r.get('productClass_name','?'), r.get('code')) for r in rows )).items()},
            }
    b.close()

print(json.dumps(summary, ensure_ascii=False, indent=2))
with open(f"{OUT_DIR}/国补口径试探.json","w") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)