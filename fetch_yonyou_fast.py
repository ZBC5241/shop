#!/usr/bin/env python3
from yonyou_cred import get_yonyou_pwd
# -*- coding: utf-8 -*-
"""
fetch_yonyou_fast.py — 用友云双标签并行导出（Playwright原生脚本，零snapshot）

流程：登录 → 打开两个报表 → 毛利明细表导出 + 销售分析导出 → 等待下载完成
全程用CSS选择器直接操作，不走MCP snapshot，速度提升10倍+

关键技术点：
1. 登录在iframe（euc.yonyoucloud.com/cas/login）内，用 #username/#password/#submit_btn_login
2. 报表不通过URL直接导航（会404），需从工作台点击 recent-xxx 元素
3. 导出下拉菜单必须用Playwright原生click()（JS的click()打不开）
4. 下载文件必须用page.expect_download() + download.save_as()捕获
5. 销售分析需检查分组是否为"华为-门店"（默认"大疆-门店"需改）

用法：
  python3 fetch_yonyou_fast.py                          # 店长账号（李家村单店）
  python3 fetch_yonyou_fast.py --account manager        # 经理账号（全门店）
"""
import sys, os, time, argparse

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ─── 配置 ───
CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
YY_BASE = "https://c3.yonyoucloud.com"
DOWNLOAD_DIR = os.path.expanduser("~/.local/share/TeleAgent/playwright-mcp")

# 报表ID
PROFIT_REPORT_ID = "a76e21a0-fe9b-4366-9b8e-2c9327c15ab9"
SALES_REPORT_ID = "rm_saleanalysis"

ACCOUNTS = {
    "store": {
        "username": "18161914293",
        "password": get_yonyou_pwd(),
        "label": "李家村店长（张博晨）",
    },
    "manager": {
        "username": "18591910491",
        "password": get_yonyou_pwd("18591910491"),
        "label": "经理（杨晨晨）",
    },
}


def log(msg):
    t = time.strftime("%H:%M:%S")
    print(f"  [{t}] {msg}", flush=True)


def do_login(page, account):
    """在iframe中完成登录"""
    log(f"开始登录：{account['label']}")
    page.goto(YY_BASE, wait_until="domcontentloaded", timeout=30000)
    time.sleep(3)

    # 处理cookie弹窗
    try:
        accept_btn = page.query_selector(".button_accept")
        if accept_btn:
            accept_btn.click()
            time.sleep(1)
    except:
        pass

    # 找登录iframe
    login_frame = None
    for f in page.frames:
        if "euc.yonyoucloud.com" in (f.url or ""):
            login_frame = f
            break
    if not login_frame:
        time.sleep(5)
        for f in page.frames:
            if "euc.yonyoucloud.com" in (f.url or ""):
                login_frame = f
                break
    if not login_frame:
        log("❌ 未找到登录iframe")
        return False

    # 输入账号密码
    login_frame.fill("#username", account["username"])
    time.sleep(0.3)
    login_frame.fill("#password", account["password"])
    time.sleep(0.3)
    login_frame.click("#submit_btn_login")

    # 等待跳转
    for i in range(15):
        time.sleep(2)
        url = page.url
        if "login" not in url.lower() and "cas" not in url.lower():
            break
    time.sleep(3)
    log(f"✅ 登录成功：{account['label']}")
    return True


def open_report(page, report_id, report_name):
    """从工作台点击报表入口打开报表面板"""
    el_id = f"recent-{report_id}"
    # 等待报表入口出现（工作台可能渲染较慢），最多30秒
    entry_ready = False
    for i in range(15):
        found = page.evaluate(f"""() => !!document.getElementById('{el_id}') || !!document.getElementById('favor-{report_id}')""")
        if found:
            entry_ready = True
            break
        time.sleep(2)
    if not entry_ready:
        log(f"⚠️ {report_name}入口未出现（工作台渲染慢）")

    # 点击最近使用中的报表（重试3次）
    for attempt in range(3):
        page.evaluate(f"""() => {{
            const el = document.getElementById('{el_id}');
            if (el) el.click();
            else {{
                // 备用：收藏中的
                const el2 = document.getElementById('favor-{report_id}');
                if (el2) el2.click();
            }}
        }}""")

        # 等待报表面板加载（工具栏出现）
        for i in range(15):
            time.sleep(2)
            count = page.evaluate("() => document.querySelectorAll('button.wui-dropdown-trigger.ana-header-dropdown-list').length")
            if count >= 3:
                log(f"✅ {report_name}面板已加载")
                return True
        if attempt < 2:
            log(f"⚠️ {report_name}面板未加载（第{attempt+1}次），5秒后重试")
            time.sleep(5)
    log(f"⚠️ {report_name}面板未加载")
    return False


def query_data(page, report_name):
    """点击查询按钮，等待数据加载（毛利明细表专用）"""
    # 点击查询
    page.evaluate("""() => {
        const btn = document.querySelector('button[fieldid="filter_panel_handle_search_btn"]');
        if (btn) btn.click();
    }""")

    # 等待"共N条"出现
    for i in range(30):
        time.sleep(2)
        total = page.evaluate(r"""() => {
            const m = document.body.innerText.match(/共\s*(\d+)\s*条/);
            return m ? m[0] : '';
        }""")
        if total:
            log(f"  {report_name}数据: {total}")
            return total
    log(f"  ⚠️ {report_name}未检测到数据条数")
    return ""


def export_profit_detail(page, context):
    """导出毛利明细表（在当前页面操作，不需要新标签）"""
    log("═══ 导出毛利明细表 ═══")

    # 打开报表
    if not open_report(page, PROFIT_REPORT_ID, "毛利明细表"):
        return None

    # 查询
    query_data(page, "毛利明细表")

    # 记录下载前的文件
    old_files = set(os.listdir(DOWNLOAD_DIR))

    # 用Playwright原生click点击导出trigger（第3个）
    log("点击导出按钮...")
    triggers = page.query_selector_all('button.wui-dropdown-trigger.ana-header-dropdown-list')
    triggers[2].click()
    time.sleep(1)

    # 点击"导出Excel"
    log("选择导出Excel...")
    page.click('li[fieldid="analysis|toolbar|export|export_excel"]')
    time.sleep(2)

    # 选择"原始数据导出"
    log("选择原始数据导出...")
    radios = page.query_selector_all('input[type="radio"]')
    for r in radios:
        label = r.evaluate("el => el.parentElement ? el.parentElement.textContent.trim() : ''")
        if '原始数据' in label:
            r.click()
            log(f"  ✅ 已选择: {label}")
            break
    time.sleep(0.5)

    # 用expect_download捕获下载
    log("点击确定，等待文件下载...")
    try:
        with page.expect_download(timeout=300000) as download_info:
            # 点击确定
            btns = page.query_selector_all('button, input[type="button"]')
            for b in btns:
                text = b.text_content().strip()
                if text == '确定' and b.is_visible():
                    b.click()
                    log("  ✅ 点击了确定")
                    break

        download = download_info.value
        # 保存到目标目录
        filename = download.suggested_filename or "门店毛利明细表-华为终端.xlsx"
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        download.save_as(filepath)
        size = os.path.getsize(filepath)
        log(f"  ✅ 毛利明细表下载完成: {filename} ({size//1024}KB)")
        return filepath
    except PWTimeout:
        log("  ⚠️ expect_download超时，检查文件...")
        # 备用：检查是否有新文件
        current = set(os.listdir(DOWNLOAD_DIR))
        new_files = current - old_files
        new_xlsx = [f for f in new_files if f.endswith('.xlsx') and not f.startswith('~')]
        if new_xlsx:
            filepath = os.path.join(DOWNLOAD_DIR, new_xlsx[0])
            log(f"  ✅ 找到新文件: {new_xlsx[0]}")
            return filepath
        log("  ❌ 未找到下载文件")
        return None
    except Exception as e:
        log(f"  ❌ 下载失败: {e}")
        return None


def export_sales_analysis(page, context):
    """导出销售分析（需要关闭毛利报表，打开销售分析）"""
    log("═══ 导出销售分析 ═══")

    # 关闭当前报表tab（毛利明细表）
    page.evaluate("""() => {
        const closeBtn = document.querySelector('.navLi--LkQEZ.active .close-btn, li[class*="active"] .close-btn');
        if (closeBtn) closeBtn.click();
    }""")
    time.sleep(2)

    # 打开销售分析
    if not open_report(page, SALES_REPORT_ID, "销售分析"):
        return None

    # 确保分组为"华为-门店"（带重试，避免偶发切分组失败导致下游缺列）
    log("确保分组为'华为-门店'...")
    for attempt in range(4):
        group_text = page.evaluate("""() => {
            const el = document.querySelector('.groupCondition .Grouping-condition-span');
            return el ? el.textContent.trim() : '';
        }""")
        if '华为' in group_text:
            log(f"  当前分组已是华为-门店 ({group_text})")
            break
        log(f"  ⚠️ 当前分组'{group_text or '未检测'}'，尝试切换({attempt+1}/4)...")
        try:
            page.click('.groupCondition .Grouping-condition-input', timeout=5000)
        except PWTimeout:
            log("  ⚠️ 分组输入框未找到，重试")
        time.sleep(1.5)
        page.evaluate("""() => {
            const spans = document.querySelectorAll('.wui-popover-inner-content span[title]');
            for (const s of spans) {
                if (s.getAttribute('title') === '华为-门店') { s.click(); return; }
            }
            const all = document.querySelectorAll('.wui-popover-inner-content span');
            for (const s of all) {
                if (s.textContent.trim() === '华为-门店') { s.click(); return; }
            }
        }""")
        time.sleep(2)
    # 最终验证：必须切到华为-门店，否则后续列缺失直接失败（不让错文件流到下游）
    final_group = page.evaluate("""() => {
        const el = document.querySelector('.groupCondition .Grouping-condition-span');
        return el ? el.textContent.trim() : '';
    }""")
    if '华为' not in final_group:
        log(f"  ❌ 切换华为-门店失败，当前分组: {final_group or '未检测'}")
        return None
    log(f"  ✅ 分组确认: {final_group}")

    # 点击查询按钮
    log("点击查询...")
    page.click('button[fieldid="rm_saleanalysis|search"]')

    # 等待数据加载（"共N条"出现）
    for i in range(30):
        time.sleep(2)
        total = page.evaluate(r"""() => {
            const m = document.body.innerText.match(/共\s*(\d+)\s*条/);
            return m ? m[0] : '';
        }""")
        if total:
            log(f"  销售分析数据: {total}")
            break
    else:
        log("  ⚠️ 销售分析未检测到数据条数")

    old_files = set(os.listdir(DOWNLOAD_DIR))

    # 点击工具栏"导出"按钮，打开导出工作台对话框
    log("点击导出按钮...")
    page.click('button[fieldid="rm_saleanalysis|btnTempexport"]')
    time.sleep(2)

    # 确保"带查询条件导出"关闭（表头位置固定，无需动态查找）
    log("确保带查询条件导出已关闭...")
    page.evaluate("""() => {
        const sw = document.querySelector('.wui-switch.wui-switch-lg.wui-switch-span');
        if (sw && sw.offsetParent !== null) {
            if (sw.classList.contains('wui-switch-checked')) {
                sw.click();
                return 'turned off';
            }
            return 'already off';
        }
        return 'not found';
    }""")
    time.sleep(0.5)

    # 点击对话框中的"导出"按钮
    log("点击对话框导出...")
    page.click('button[fieldid="rm_saleanalysis|export"]')
    time.sleep(2)

    # 确认导出全部数据 — 点击确认框中的"确定"
    log("确认导出全部数据，等待下载...")
    try:
        with page.expect_download(timeout=300000) as download_info:
            page.click('button[fieldid="rm_saleanalysis|conform_modal_footer_ok"]')

        download = download_info.value
        filename = download.suggested_filename or "销售分析.xlsx"
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        download.save_as(filepath)
        size = os.path.getsize(filepath)
        log(f"  ✅ 销售分析下载完成: {filename} ({size//1024}KB)")
        return filepath
    except PWTimeout:
        log("  ⚠️ expect_download超时，检查文件...")
        current = set(os.listdir(DOWNLOAD_DIR))
        new_files = current - old_files
        new_xlsx = [f for f in new_files if f.endswith('.xlsx') and not f.startswith('~') and '销售' in f]
        if new_xlsx:
            filepath = os.path.join(DOWNLOAD_DIR, new_xlsx[0])
            log(f"  ✅ 找到新文件: {new_xlsx[0]}")
            return filepath
        log("  ❌ 未找到下载文件")
        return None
    except Exception as e:
        log(f"  ❌ 下载失败: {e}")
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", default="store", choices=["store", "manager"])
    args = parser.parse_args()

    account = ACCOUNTS[args.account]
    t_total = time.time()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    log(f"🚀 用友云双报表导出（{account['label']}）")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            executable_path=CHROME_PATH,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36",
            viewport={"width": 1400, "height": 900},
            accept_downloads=True,
        )

        page = context.new_page()

        # ═══ 第1步：登录 ═══
        t1 = time.time()
        if not do_login(page, account):
            browser.close()
            return 1
        log(f"登录耗时: {time.time()-t1:.1f}s")

        # ═══ 第2步：导出毛利明细表 ═══
        t2 = time.time()
        profit_file = export_profit_detail(page, context)
        log(f"毛利明细表导出耗时: {time.time()-t2:.1f}s")

        # ═══ 第3步：导出销售分析 ═══
        t3 = time.time()
        sales_file = export_sales_analysis(page, context)
        log(f"销售分析导出耗时: {time.time()-t3:.1f}s")

        browser.close()

        total_time = time.time() - t_total
        log(f"\n{'='*60}")
        log(f"🏁 全流程完成！总耗时 {total_time:.1f}s ({total_time/60:.1f}min)")
        log(f"  毛利明细表: {profit_file or '❌'}")
        log(f"  销售分析: {sales_file or '❌'}")

        print(f"\nPROFIT_FILE={profit_file or ''}")
        print(f"SALES_FILE={sales_file or ''}")

        if profit_file and sales_file:
            return 0
        else:
            return 1


if __name__ == "__main__":
    sys.exit(main())
