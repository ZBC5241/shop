#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""拉 2026-09-02 商品收款查询(日清日结) rm_goodsgatherreport，解析三指标并生成 HTML。"""
import time, json, html
from collections import defaultdict
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd()}
DATE = "2026-09-02"
OUT_DIR = "/Users/mac/WorkBuddy/2026-08-13-12-21-50"
JSON_PATH = f"{OUT_DIR}/日清日结_0902_api.json"

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
    if not lf: print("NO_LOGIN_FRAME"); return False
    lf.fill("#username", account["username"]); time.sleep(0.3)
    lf.fill("#password", account["password"]); time.sleep(0.3)
    lf.click("#submit_btn_login")
    for _ in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower(): break
    time.sleep(3)
    print("LOGGED_IN"); return True

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

    cand = {"billnum":"rm_goodsgatherreport",
            "condition":{"commonVOs":[{"itemName":"gathervouchdate","value1":f"{DATE} 00:00:00","value2":f"{DATE} 23:59:59"}]},
            "page":{"pageSize":2000,"pageIndex":1},
            "serviceCode":"rm_goodsgatherreport","terminalType":"1"}
    res = pg.evaluate("""async (body) => {
        try {
            const r=await fetch('/yonbip-mkt-retailweb/report/list?terminalType=1&serviceCode=rm_goodsgatherreport&locale=zh_CN',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
            const t=await r.text();
            return {status:r.status, text:t};
        } catch(e){ return {err:String(e)}; }
    }""", cand)
    b.close()
    txt=res.get("text","")
    try:
        j=json.loads(txt)
    except Exception as e:
        print("JSON parse err:", e); print(txt[:800]); raise SystemExit(1)
    if j.get("code")!=200:
        print("API 返回非200:", j.get("code"), j.get("message")); print(txt[:800]); raise SystemExit(1)
    with open(JSON_PATH,"w") as f: f.write(txt)
    print(">>> 已保存", JSON_PATH)

# ---- 解析三指标 ----
d=j["data"]
rows=d.get("recordList") or []
footer=(d.get("sumRecordList") or [{}])[0]
codes=set(r["code"] for r in rows if r.get("code"))
retail_cnt=len(codes)
amount=footer.get("fMoney")
quote=footer.get("fQuoteMoney")
discount=footer.get("fDiscount")
# 国补POS挂账 单据
guobu=set(r["code"] for r in rows if r.get("iPaymentid_name")=="国补POS挂账")
# 收款方式分布
pay=defaultdict(set)
for r in rows:
    nm=r.get("iPaymentid_name")
    if nm: pay[nm].add(r.get("code"))
neg=set(r["code"] for r in rows if float(r.get("fMoney") or 0)<0)
print("零售单数:",retail_cnt,"| 金额:",amount,"| 国补POS挂账:",len(guobu))
print("页脚:",json.dumps(footer,ensure_ascii=False)[:400])
print("收款方式分布:",{k:len(v) for k,v in pay.items()})
print("退货单:",len(neg))

# ---- 生成 HTML ----
pay_sorted=sorted(pay.items(), key=lambda x:-len(x[1]))
pay_rows="".join(f"<tr><td>{html.escape(k)}</td><td>{len(v)}</td></tr>" for k,v in pay_sorted)
html_doc=f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>李家村万达店 日清日结 {DATE}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6fa;color:#222;padding:20px}}
.wrap{{max-width:780px;margin:0 auto;background:#fff;border-radius:14px;box-shadow:0 4px 20px rgba(0,0,0,.08);overflow:hidden}}
.head{{background:linear-gradient(135deg,#6a5acd,#8a7ff0);color:#fff;padding:22px 26px}}
.head h1{{font-size:22px;font-weight:700}}
.head .sub{{opacity:.9;margin-top:4px;font-size:13px}}
.cards{{display:flex;gap:14px;padding:22px 26px}}
.card{{flex:1;background:#fafbff;border:1px solid #eceefb;border-radius:12px;padding:18px;text-align:center}}
.card .lab{{font-size:13px;color:#888;margin-bottom:8px}}
.card .num{{font-size:30px;font-weight:800;color:#5b4bd6}}
.card .unit{{font-size:13px;color:#aaa;margin-top:4px}}
.note{{padding:0 26px 8px;font-size:12.5px;color:#777;line-height:1.7}}
.note b{{color:#444}}
.tbl{{padding:10px 26px 26px}}
.tbl h3{{font-size:15px;margin:14px 0 8px;color:#444}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #f0f0f5}}
th{{background:#fafbff;color:#888;font-weight:600}}
tr:hover td{{background:#fafbff}}
.foot{{padding:14px 26px 22px;font-size:11.5px;color:#aaa;border-top:1px solid #f0f0f5}}
.tag{{display:inline-block;background:#fdeaea;color:#d33;border-radius:6px;padding:2px 8px;font-size:12px;margin-left:6px}}
</style></head>
<body><div class="wrap">
<div class="head"><h1>📊 李家村万达店 · 日清日结</h1><div class="sub">日期：{DATE} ｜ 数据源：用友云「商品收款查询」(rm_goodsgatherreport) 实时接口</div></div>
<div class="cards">
<div class="card"><div class="lab">零售单数</div><div class="num">{retail_cnt}</div><div class="unit">单</div></div>
<div class="card"><div class="lab">金额（净额）</div><div class="num">¥{amount:,.2f}</div><div class="unit">零售 {quote:,.2f} − 折扣 {discount:,.2f}</div></div>
<div class="card"><div class="lab">国补POS挂账</div><div class="num">{len(guobu)}</div><div class="unit">单</div></div>
</div>
<div class="note">
⚠️ <b>口径说明</b>（均为系统原始返回，未做复算）：<br>
· <b>零售单数 {retail_cnt}</b> = 当日唯一零售单号数，含退货单 <b>{len(neg)}</b> 单（已并计）。<br>
· <b>金额 ¥{amount:,.2f}</b> = 页脚「金额」列净额 = 零售金额 ¥{quote:,.2f} − 折扣额 ¥{discount:,.2f}。<br>
· <b>国补POS挂账 {len(guobu)} 单</b> = 收款方式精确等于「国补POS挂账」的单数。
</div>
<div class="tbl">
<h3>💳 收款方式分布（按涉及单据数）</h3>
<table><thead><tr><th>收款方式</th><th>单据数</th></tr></thead><tbody>{pay_rows}</tbody></table>
</div>
<div class="foot">数据来源：用友云 YonSuite 报表接口 report/list（billnum=rm_goodsgatherreport，条件 gathervouchdate={DATE}）。本页为本地离线文件，双击即看，无需联网。</div>
</div></body></html>"""
html_path=f"{OUT_DIR}/李家村_{DATE.replace('-','')}_日清日结.html"
with open(html_path,"w",encoding="utf-8") as f: f.write(html_doc)
print(">>> 已生成", html_path)
