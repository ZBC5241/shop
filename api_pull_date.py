# -*- coding: utf-8 -*-
"""按晨哥 8 点规格拉 今天(2026-09-01) 国补业务日清日结：
   商品收款查询(rm_goodsgatherreport) / 日清日结视图 / 收款日期=今天 /
   分组 财务-华为(本账号=全部华为业务) / 收款方式=国补POS挂账+国补补贴。
   输出：零售数量 / 金额 / 总单数(国补POS挂账唯一零售单号)。
"""
import time, json, subprocess
from datetime import datetime
from playwright.sync_api import sync_playwright

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY = "https://c3.yonyoucloud.com"
ACCT = "18161914293"
REPORT_ID = "rm_goodsgatherreport"

def get_yonyou_pwd():
    """从 macOS 钥匙串读取用友密码(条目 service=yonyou, account=18161914293)。绝不硬编码明文。"""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", "yonyou", "-a", "18161914293", "-w"],
            capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception as e:
        print("KEYCHAIN_ERR", e)
    raise SystemExit("ERR: 钥匙串未找到 yonyou 密码, 请先存: security add-generic-password -s yonyou -a 18161914293 -w '<密码>'")

TODAY = "2026-09-01"   # 收款日期=今天

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
    lf.fill("#password", get_yonyou_pwd()); time.sleep(0.3)
    lf.click("#submit_btn_login")
    for _ in range(15):
        time.sleep(2)
        if "login" not in page.url.lower() and "cas" not in page.url.lower(): break
    time.sleep(3)
    print("LOGGED_IN"); return True

def main():
    out = {}
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True, executable_path=CHROME,
                            args=["--no-sandbox","--disable-dev-shm-usage","--disable-blink-features=AutomationControlled"])
        pg=b.new_page()
        if not do_login(pg): b.close(); return
        time.sleep(2)

        start = f"{TODAY} 00:00:00"
        end   = f"{TODAY} 23:59:59"
        # 服务端尝试加 收款方式 过滤（iPaymentid，国补POS挂账=1005, 国补补贴=1042）
        body = {
            "billnum": REPORT_ID,
            "condition": {"commonVOs": [
                {"itemName":"gathervouchdate","value1":start,"value2":end},
            ]},
            "page":{"pageSize":1000,"pageIndex":1},
            "serviceCode": REPORT_ID,
            "terminalType":"1",
        }
        req_js = json.dumps(body, ensure_ascii=False)
        resp_text = pg.evaluate("""(args) => {
            const body = JSON.parse(args.body);
            return fetch('/yonbip-mkt-retailweb/report/list?terminalType=1&serviceCode=rm_goodsgatherreport&locale=zh_CN', {
                method:'POST',
                credentials:'include',
                headers:{'Content-Type':'application/json'},
                body: JSON.stringify(body)
            }).then(r=>r.text()).catch(e=>'FETCH_ERR:'+e.message);
        }""", {"body": req_js})
        print("RESP_LEN", len(resp_text))
        try:
            j = json.loads(resp_text)
        except Exception as e:
            print("JSON_PARSE_ERR", e); print(resp_text[:500]); b.close(); return
        print("code", j.get("code"), "msg", j.get("msg"))
        data = j.get("data", {})
        rows = data.get("recordList", [])
        print("rows returned:", len(rows), " recordCount:", data.get("recordCount"))

        # 客户端兜底校验：只看 国补POS挂账 / 国补补贴
        GUOBU = ("国补POS挂账","国补补贴")
        gb = [r for r in rows if r.get("iPaymentid_name") in GUOBU]
        # 检查服务端过滤是否生效（非国补行占比）
        non_gb = [r for r in rows if r.get("iPaymentid_name") not in GUOBU]
        print(f"服务端过滤后: 国补行={len(gb)} 非国补行={len(non_gb)} -> {'已生效' if len(non_gb)==0 else '未生效,客户端兜底'}")

        # 计算指标（基于国补行，补贴行 fMoney/fQty=0 不影响求和）
        codes = sorted(set(r["code"] for r in gb if r.get("code")))
        amount = round(sum(float(r.get("fMoney") or 0) for r in gb), 2)
        qty    = round(sum(float(r.get("fQuantity") or 0) for r in gb), 2)
        pos_codes = sorted(set(r["code"] for r in gb if r.get("iPaymentid_name")=="国补POS挂账"))
        # 每单明细（取国补POS挂账行作为代表）
        detail = []
        for c in pos_codes:
            sub=[r for r in gb if r["code"]==c and r.get("iPaymentid_name")=="国补POS挂账"]
            r0=sub[0]
            detail.append({
                "code": c,
                "productClass": r0.get("productClass_name"),
                "product": r0.get("product_name"),
                "amount": round(float(r0.get("fMoney") or 0),2),
                "qty": round(float(r0.get("fQuantity") or 0),2),
                "employee": r0.get("iEmployeeid_name"),
            })
        # 页脚
        footer = data.get("sumRecordList",[{}])[0] if data.get("sumRecordList") else {}
        out = {
            "date": TODAY,
            "metrics": {
                "零售数量": qty,
                "金额": amount,
                "总单数": len(pos_codes),
            },
            "detail": detail,
            "footer": {k:footer.get(k) for k in ["fMoney","fQuoteMoney","fDiscount","fQuantity"]},
            "serverFilterApplied": len(non_gb)==0,
            "rawRowCount": len(rows),
            "guobuRowCount": len(gb),
        }
        # 保存原始
        with open("/Users/mac/WorkBuddy/2026-08-13-12-21-50/日清日结_0901_api.json","w") as f:
            json.dump(j, f, ensure_ascii=False, indent=2)
        print("\n=== 9-01 国补业务日清日结 ===")
        print("零售数量:", qty)
        print("金额:", amount)
        print("总单数(国补POS挂账唯一单号):", len(pos_codes))
        print("--- 明细 ---")
        for d in detail:
            print(f"  {d['code']} | {d['productClass']} | {d['product']} | ¥{d['amount']:,.2f} | {d['qty']:.0f}件 | {d['employee']}")
        with open("/Users/mac/WorkBuddy/2026-08-13-12-21-50/日清日结_0901_result.json","w") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        b.close()

main()
