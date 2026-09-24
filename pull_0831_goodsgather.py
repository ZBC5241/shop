#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""
pull_0831_goodsgather.py — 拉取 2026-08-31 日清日结（商品收款查询 / rm_goodsgatherreport）
返回 3 个指标：
  1. 零售单数（唯一零售单号计数）
  2. 金额（金额列合计 / 报表页脚合计）
  3. 国补POS挂账单数（收款方式含"国补"的唯一零售单号计数）

做法：登录 → 打开报表 → 日历切到 8月31日 → 等自动重查 → 读数据表
同时捕获底层 report/list 请求作兜底。
"""
import time, json, sys
from playwright.sync_api import sync_playwright

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
account = {"username": "18161914293", "password": get_yonyou_pwd(), "label": "store"}
TARGET = "2026-08-31"

def do_login(page):
    page.goto(YY_BASE, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)
    try:
        b = page.query_selector(".button_accept")
        if b:
            b.click(); time.sleep(1)
    except Exception:
        pass
    lf = None
    for f in page.frames:
        if "euc.yonyoucloud.com" in (f.url or ""):
            lf = f; break
    if not lf:
        time.sleep(5)
        for f in page.frames:
            if "euc.yonyoucloud.com" in (f.url or ""):
                lf = f; break
    if not lf:
        print("NO_LOGIN_FRAME"); return False
    lf.fill("#username", account["username"]); time.sleep(0.3)
    lf.fill("#password", account["password"]); time.sleep(0.3)
    lf.click("#submit_btn_login")
    for _ in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower():
            break
    time.sleep(3)
    print("LOGGED_IN url=", page.url)
    return True

def set_calendar_to(pg, ym_str):
    """把范围选择器左面板切到目标月份（ym_str 形如 '2026年8月' 的 '8月' 片段）。"""
    # 点击开始输入，打开日历
    pg.click('input[placeholder="开始"]')
    time.sleep(1.5)
    # 循环点"上一月"直到某个面板显示 8月
    for _ in range(4):
        found = pg.evaluate("""() => {
            const panels=[...document.querySelectorAll('.wui-picker-date-panel')];
            const p=panels.find(x=>{const m=x.querySelector('.wui-picker-month-btn');return m&&m.innerText.includes('8月');});
            return p? p.querySelector('.wui-picker-month-btn').innerText : '';
        }""")
        if found:
            print("  日历已定位到:", found); break
        prev = pg.query_selector('.wui-picker-header-prev-btn')
        if prev:
            prev.click(); time.sleep(1.2)
        else:
            print("  ⚠️ 未找到 month-prev 按钮"); break
    # 点击左面板(8月)里的 31
    for attempt in range(2):  # 第一次设开始，第二次设结束
        clicked = pg.evaluate("""() => {
            const panels=[...document.querySelectorAll('.wui-picker-date-panel')];
            const p=panels.find(x=>{const m=x.querySelector('.wui-picker-month-btn');return m&&m.innerText.includes('8月');});
            if(!p) return 'no-panel';
            const cell=[...p.querySelectorAll('.wui-picker-cell')].find(c=>c.innerText.trim()==='31' && !c.className.includes('disabled'));
            if(cell){cell.click();return 'clicked';}
            return 'no-cell';
        }""")
        print(f"  点 31 尝试{attempt+1}: {clicked}")
        time.sleep(0.8)
    time.sleep(0.5)
    pg.keyboard.press("Escape")
    time.sleep(0.5)

with sync_playwright() as p:
    b = p.chromium.launch(headless=True, executable_path=CHROME_PATH,
                          args=["--disable-blink-features=AutomationControlled"])
    ctx = b.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
        viewport={"width": 1400, "height": 900}, accept_downloads=True)
    pg = ctx.new_page()

    # 捕获底层请求作兜底
    reqs = []
    pg.on("request", lambda r: reqs.append((r.url, r.method, r.post_data)))

    if not do_login(pg):
        b.close(); raise SystemExit(1)

    # 打开报表
    pg.evaluate("""() => { const el=document.getElementById('recent-rm_goodsgatherreport'); if(el) el.click(); else { const f=document.getElementById('favor-rm_goodsgatherreport'); if(f) f.click(); } }""")
    for _ in range(25):
        try:
            ok = pg.evaluate("document.body.innerText.includes('零售单号')")
        except Exception:
            ok = False
        if ok:
            break
        time.sleep(1)
    time.sleep(2)
    print("报表已打开")

    # 设置日期到 8-31
    set_calendar_to(pg, "8月")

    # 等自动重查出数据
    for _ in range(40):
        time.sleep(2)
        info = pg.evaluate("""() => {
            const tables=[...document.querySelectorAll('table')];
            let t=null;
            for(const x of tables){ if((x.innerText||'').includes('零售单号')){t=x;break;} }
            if(!t) return {rows:0};
            return {rows: t.querySelectorAll('tbody tr').length};
        }""")
        if info.get("rows",0) > 0:
            print("  数据行:", info["rows"]); break
    time.sleep(1)

    # 读指标
    result = pg.evaluate("""() => {
        const tables=[...document.querySelectorAll('table')];
        let t=null;
        for(const x of tables){ if((x.innerText||'').includes('零售单号')){t=x;break;} }
        if(!t) return {err:'NO_TABLE'};
        const headerCells=[...t.querySelectorAll('thead th, thead td')].map(th=>th.innerText.trim());
        const idxNo=headerCells.findIndex(h=>h.includes('零售单号'));
        const idxAmt=headerCells.findIndex(h=>h==='金额'||h.includes('金额'));
        const idxRetailAmt=headerCells.findIndex(h=>h.includes('零售金额'));
        const idxPay=headerCells.findIndex(h=>h.includes('收款方式')||h.includes('收款')||h.includes('结算')||h.includes('支付')||h.includes('币')||h.includes('方式'));
        const rows=[...t.querySelectorAll('tbody tr')];
        const orderSet=new Set();
        const guobuOrders=new Set();
        let amtSum=0, retailAmtSum=0;
        for(const r of rows){
            const cells=[...r.querySelectorAll('td')].map(c=>c.innerText.trim());
            const no = idxNo>=0?cells[idxNo]:'';
            if(no) orderSet.add(no);
            if(idxAmt>=0){ const v=parseFloat((cells[idxAmt]||'').replace(/[,¥\\s]/g,'')); if(!isNaN(v)) amtSum+=v; }
            if(idxRetailAmt>=0){ const v=parseFloat((cells[idxRetailAmt]||'').replace(/[,¥\\s]/g,'')); if(!isNaN(v)) retailAmtSum+=v; }
            if(idxPay>=0 && (cells[idxPay]||'').includes('国补') && no) guobuOrders.add(no);
        }
        // 页脚合计
        let footer='';
        const frow=t.querySelector('tfoot tr');
        if(frow) footer=frow.innerText.replace(/\\n/g,' ').trim();
        return {headerCells, idxNo, idxAmt, idxRetailAmt, idxPay,
                rowCount:rows.length, orderCount:orderSet.size,
                amtSum:Math.round(amtSum*100)/100, retailAmtSum:Math.round(retailAmtSum*100)/100,
                guobuOrderCount:guobuOrders.size, footer, payColFound: idxPay>=0};
    }""")

    print("\n===== 8-31 日清日结 指标 =====")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 兜底：打印捕获到的 report/list 请求
    print("\n===== 捕获到的相关请求(前5) =====")
    rel = [r for r in reqs if 'report' in r[0] or 'list' in r[0]]
    for u,m,d in rel[:5]:
        print(f"[{m}] {u}")
        if d: print("   body:", d[:400])

    # 落盘
    with open("/Users/mac/WorkBuddy/2026-08-13-12-21-50/日清日结_0831_raw.json","w") as f:
        rel5 = [ (u, m, (d or '')[:500]) for (u, m, d) in rel ][:5]
        json.dump({"result":result,"reqs":rel5}, f, ensure_ascii=False, indent=2)

    b.close()
