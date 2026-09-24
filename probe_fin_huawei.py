#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""拉 8-28 全量明细，尝试多个'财务-华为'口径，看哪个对得上 ¥13,215.05。"""
import time, json
from collections import defaultdict
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd()}
OUT_DIR = "/Users/mac/WorkBuddy/2026-08-13-12-21-50"
DATE = "2026-08-28"

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

    body = {"billnum":"rm_goodsgatherreport",
            "condition":{"commonVOs":[{"itemName":"gathervouchdate","value1":f"{DATE} 00:00:00","value2":f"{DATE} 23:59:59"}]},
            "page":{"pageSize":3000,"pageIndex":1},"serviceCode":"rm_goodsgatherreport","terminalType":"1"}
    res = pg.evaluate("""async (body) => {
        try {
            const r=await fetch('/yonbip-mkt-retailweb/report/list?terminalType=1&serviceCode=rm_goodsgatherreport&locale=zh_CN',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
            return {status:r.status, text:await r.text()};
        } catch(e){ return {err:String(e)}; }
    }""", body)
    b.close()
    txt=res.get("text","")
    j=json.loads(txt)
    if j.get("code")!=200:
        print("ERR:",j); raise SystemExit(1)
    with open(f"{OUT_DIR}/日清日结_0828_api.json","w") as f: f.write(txt)
    rows=j["data"]["recordList"]
    print("8-28 全量行数:", len(rows), "唯一单号:", len(set(r['code'] for r in rows if r.get('code'))))

# 尝试 4 种'财务-华为'口径
gb_pay = {"国补POS挂账","国补补贴"}
def sum_money(rs):
    s=sum(float(r.get('fMoney') or 0) for r in rs)
    q=sum(float(r.get('fQuantity') or 0) for r in rs)
    c=set(r['code'] for r in rs if r.get('code'))
    return round(s,2), round(q,2), len(c)

# 候选1: productClass_name 含品牌关键词
brands=['Mate','Pura','nova','畅享','FreeBuds','FreeClip','Watch','MateBook','MatePad','WATCH']
# 候选2: 排除非华为（垫付/三方/定金/碎屏/贴膜/服务/其他/华为-重复?）
exclude=['垫付','定金','三方','碎屏','贴膜','服务','其他类','权益系列']
# 候选3: productClass_code 前缀匹配
# 候选4: 全量

trials={}
# 候选A: 含品牌关键词
rows_a=[r for r in rows if any(r.get('productClass_name','').startswith(b) or r.get('productClass_name','')==b for b in brands)]
trials['A_brands']=sum_money([r for r in rows_a if r.get('iPaymentid_name') in gb_pay])
# 候选B: 排除非华为
rows_b=[r for r in rows if not any(x in r.get('productClass_name','') for x in exclude)]
trials['B_exclude']=sum_money([r for r in rows_b if r.get('iPaymentid_name') in gb_pay])
# 候选C: 全量
trials['C_all']=sum_money([r for r in rows if r.get('iPaymentid_name') in gb_pay])
# 候选D: 仅国补POS挂账(不算补贴)
rows_d=[r for r in rows if r.get('iPaymentid_name')=='国补POS挂账']
trials['D_pos_only']=sum_money(rows_d)
# 候选E: 国补POS挂账+国补补贴 但加 + 排除服务/垫付
rows_e=[r for r in rows if r.get('iPaymentid_name') in gb_pay and not any(x in r.get('productClass_name','') for x in ['垫付','定金','三方','碎屏','贴膜','服务','其他类'])]
trials['E_exc_gb']=sum_money(rows_e)

# 各候选涉及的零售单号
for k in trials:
    print(f"{k}: 金额={trials[k][0]} 数量={trials[k][1]} 单号={trials[k][2]}")

# 看 9-01 全量验证（已知 = 图片 7,786.00）
print()
print("=== 9-01 验证（应是全量=财务-华为）===")
d=json.load(open(f"{OUT_DIR}/日清日结_0902_api.json"))  # 9-02 当参考
# 重新拉 9-01
# 已经有 pull_guobu.py 输出的 9-01 全量 = ¥7,786
# 看 9-01 的 productClass
print("9-01 全量 = 财务-华为组（因为仅 3 类产品：权益系列、MateBook D16、Watch GT7）")