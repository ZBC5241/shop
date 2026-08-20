#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich_day_members.py —— 给 data.json 增加 dayMembers 字段。

来源：用友云「销售分析」接口全量记录（vouchdate + iMemberid_name + iMemberid_cphone + iEmployeeid_name + product_cName）。
用途：用户点日期时展示"单号 + 会员姓名 + 电话"（codeInfoHTML 的回退数据源）。

注意：用友云"销售分析"接口 vouchdate 滞后约 12 天（如本次 08-20 时仅到 08-08），
      8-09 之后的日期暂无会员数据。脚本会优雅处理空数据。
"""
import json, sys, os
from collections import defaultdict
from datetime import datetime

WH_PATH = 'sa_warehouse.json'
DATA_PATH = 'data.json'

def main():
    # 1. 读销售分析数据仓
    if not os.path.exists(WH_PATH):
        print(f'❌ 未找到 {WH_PATH}，跳过'); return
    wh = json.load(open(WH_PATH, encoding='utf-8'))
    recs = wh.get('records', []) if isinstance(wh, dict) else wh
    print(f'  销售分析数据仓: {len(recs)} 条')

    # 2. 按 vouchdate 聚合
    by_date = defaultdict(list)
    for r in recs:
        vd = r.get('vouchdate') or ''
        ds = str(vd)[:10] if vd else ''
        if not ds.startswith('2026-08'): continue
        code = r.get('id') or r.get('retailVouchHeaderDefineCharacter__id') or r.get('单据编号') or ''
        if not code: continue
        emp = r.get('iEmployeeid_name') or ''
        member = r.get('iMemberid_name') or ''
        phone = r.get('iMemberid_cphone') or ''
        product = r.get('product_cName') or r.get('oid_userDefine_2394043221715451912') or ''
        # 只保留有会员的（手机/姓名同时有）
        if not (member and phone): continue
        by_date[ds].append({
            'code': str(code),
            'emp': emp,
            'member': member,
            'phone': str(phone),
            'product': str(product)[:40]
        })
    print(f'  覆盖日期: {len(by_date)} 天')
    if by_date:
        max_d = max(by_date.keys())
        print(f'  最新日期: {max_d} ({len(by_date[max_d])} 单)')

    # 3. 写入 data.json
    d = json.load(open(DATA_PATH, encoding='utf-8'))
    d['dayMembers'] = dict(by_date)
    json.dump(d, open(DATA_PATH, 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'✅ dayMembers 已写入 {DATA_PATH}')

    # 4. 简表
    print('\n--- 各日会员单数 ---')
    for ds in sorted(by_date.keys(), reverse=True)[:10]:
        print(f'  {ds}: {len(by_date[ds])} 单')

if __name__ == '__main__':
    main()
