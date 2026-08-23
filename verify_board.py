#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_board.py —— 看板推送前强制校验（铁律：不通过不许 push）

为什么需要它：
  历史教训——多次漏跑 merge_qudao.py 导致运营看板(渠道)数据为空就直接推送上线，
  用户每次打开看到的是错的。本脚本在 build 之后、git push 之前自动跑，
  任何一项不达标直接非零退出，CI/人工都不能放行推送。

校验项：
  1) data.json 存在且可解析
  2) meta.date == 今天（或显式 --day 指定日），确保不是旧缓存数据
  3) meta.remainDays 为 1~31 的整数（剩余天数口径有效）
  4) store.qcs.增值 存在且 done>0（增值柱有数）
  5) qudao 字段存在且 done>0（运营看板渠道数据，漏跑 merge_qudao 会被抓出）
  6) people 含全部 5 名业务员且每人 qcs/performance 非空
  7) 销售核心指标：门店毛利 done>0、销额>0

用法：
  python verify_board.py [data.json] [--day YYYY-MM-DD]
退出码：0 通过 / 1 不通过（并打印失败项）
"""
import sys, os, json, datetime, argparse

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data.json")

# 应有业务员（与 calc_data 固定名单一致）
EXPECT_PEOPLE = ["邵乐乐", "杨丽华", "李泽", "陈超磊", "张博晨"]


def fail(msg):
    print("✗ 校验失败：" + msg)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default=DATA)
    ap.add_argument("--day", default=datetime.date.today().strftime("%Y-%m-%d"))
    a = ap.parse_args()

    if not os.path.exists(a.path):
        fail("找不到 data.json: %s" % a.path)

    try:
        d = json.load(open(a.path, encoding="utf-8"))
    except Exception as e:
        fail("data.json 解析错误: %s" % e)

    print("→ 校验 data.json (期望日期 %s)" % a.day)

    # 1) meta 存在
    meta = d.get("meta") or {}
    if not meta:
        fail("meta 字段缺失")

    # 3) remainDays 有效（先取，供第 2 步自洽校验用）
    rd = meta.get("remainDays")
    if not (isinstance(rd, int) and 1 <= rd <= 31):
        fail("remainDays 无效: %r（应为 1~31 整数）" % rd)

    # 2) 日期必须是近期（防止拿几天前的旧缓存推送）
    #    看板数据日期 = 抓取的最后一个营业日，常比系统"今天"早（夜间/凌晨跑）。
    #    所以不强制等于今天，而是要求落在最近 3 天内，且 remainDays 与日期自洽。
    mdate = meta.get("date")
    try:
        md = datetime.datetime.strptime(mdate, "%Y-%m-%d").date()
    except Exception:
        fail("meta.date 格式异常: %r" % mdate)
    today = datetime.date.today()
    age = (today - md).days
    if age < 0:
        fail("meta.date %s 是未来日期（系统时钟或数据异常）" % mdate)
    if age > 3:
        fail("数据日期 %s 距今天 %d 天（疑似旧缓存，先重跑抓取+calc+merge）" % (mdate, age))
    # remainDays 自洽：calc_data 用 ref=系统today（同月且today>=数据最新日时）算剩余天数
    #   即 remainDays = 本月天数 - 今天（不含今天，晨哥拍板口径）
    #   校验须基于"今天"，不是 meta.date（数据日期常比今天早，是夜间/凌晨抓取的正常现象）
    import calendar
    if (today.year, today.month) != (md.year, md.month):
        # 跨月：今天已不在数据所在月，ref 会回退到 base0，remainDays 按数据月末算
        last = calendar.monthrange(md.year, md.month)[1]
        exp_rd = max(1, last - md.day)
        if rd != exp_rd:
            fail("跨月：remainDays %d 与数据月末 %s 不符（期望 %d）" % (rd, mdate, exp_rd))
    else:
        last = calendar.monthrange(today.year, today.month)[1]
        exp_rd = max(1, last - today.day)
        if rd != exp_rd:
            fail("remainDays %d 与今天 %s 自洽不符（期望 %d，自然月口径=本月天数-今天）" % (rd, today.isoformat(), exp_rd))

    store = d.get("store") or {}
    qcs = store.get("qcs") or {}
    # 4) 增值柱
    zengzhi = qcs.get("增值") or {}
    if not (isinstance(zengzhi.get("done"), (int, float)) and zengzhi.get("done") > 0):
        fail("store.qcs.增值 无有效数据（增值柱会空白）")

    # 5) 运营看板 qudao（漏跑 merge_qudao 必被抓）
    #    完成额实际在 qudao.total.done（与前端 parts/03_js_core.js:702 一致）
    qudao = d.get("qudao")
    if not qudao:
        fail("qudao 字段缺失（运营看板渠道数据为空！漏跑 merge_qudao.py）")
    qd = (qudao.get("total") or {}).get("done") if isinstance(qudao, dict) else None
    if not (isinstance(qd, (int, float)) and qd > 0):
        fail("qudao.total.done 无有效数据（运营看板渠道为空，重跑 merge_qudao.py）")

    # 6) 业务员齐全
    people = d.get("people") or {}
    missing = [p for p in EXPECT_PEOPLE if p not in people]
    if missing:
        fail("业务员缺失: %s" % ",".join(missing))
    for p in EXPECT_PEOPLE:
        pp = people[p] or {}
        if not (pp.get("qcs") or pp.get("performance")):
            fail("业务员 %s 数据为空" % p)

    # 7) 销售核心（毛利在 store.performance.毛利）
    perf = store.get("performance") or {}
    maoli_done = (perf.get("毛利") or {}).get("done") if isinstance(perf.get("毛利"), dict) else None
    if not (isinstance(maoli_done, (int, float)) and maoli_done > 0):
        fail("毛利 done 无效（销售核心数据为0）")

    # 全部通过
    print("✓ 校验通过：")
    print("    日期 %s / 剩余 %d 天" % (mdate, rd))
    print("    增值完成 %.0f / 渠道完成 %.0f(达成%.1f%%)" % (
        zengzhi.get("done", 0), qd, ((qudao.get("total") or {}).get("rate") or 0) * 100))
    print("    业务员 %d 人齐全 / 门店毛利 %.0f" % (len(EXPECT_PEOPLE), maoli_done or 0))
    print("    → 可安全推送")
    sys.exit(0)


if __name__ == "__main__":
    main()
