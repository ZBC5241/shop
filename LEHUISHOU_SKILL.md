# 李家村销售看板 · 乐回收更新 skill

> **凡用户给出"乐回收"数据（截图 / 表格 / 口述） → 落表 → 跑看板 → 发回最新表**
> 这一整套动作可由本 skill 完整闭环。

---

## 1. 位置

| 角色 | 文件 |
|---|---|
| 写入工具 | `update_lehuishou.py` |
| 基准表 | `/workspace/李家村8月任务进度.xlsx`（**固定不变**） |
| 看板产物 | `/workspace/李家村看板_最新.html` |
| 备份目录 | `/workspace/_备份/`（每次写入前自动备份一次） |

`update_lehuishou.py` 自带 docstring，本文档是"何时用 / 怎么用 / 出错怎么办"的人读指引。

---

## 2. 写入单元格铁律（**不可改**）

《李家村销售》sheet 已经有"乐回收"区块的固定结构：

```
        T12 = "乐回收"
        T13 = "单量"  |  U13 = "增值"
        T14 = 邵乐乐  |  U14 = 邵乐乐   ← 行14
        T15 = 杨丽华  |  U15 = 杨丽华   ← 行15
        T16 = 李泽    |  U16 = 李泽      ← 行16
        T17 = 陈超磊  |  U17 = 陈超磊    ← 行17
        T18 = 张博晨  |  U18 = 张博晨    ← 行18
        T19 = =SUM(T14:T18)             ← 公式，**不碰**
        U19 = =SUM(U14:U18)             ← 公式，**不碰**
```

- T 列 = 成交量（总单量）
- U 列 = 公司净利（总增值）
- 行号 ↔ 姓名映射是 **铁律**，写在 `update_lehuishou.py` 的 `LEHUI_ROWS` 常量里。
- T12/T13/U13 是表头，**不碰**。
- T19/U19 是 SUM 公式，**不碰**（工具 verify 时会校验它们没被改坏）。

---

## 3. 触发条件

用户给出以下任一信号即可触发：

- "乐回收：邵乐乐 8 单 138 元，李泽 7 单 451 元……"
- 一张"店员/成交量/净利"的截图
- 上传一个含"店员/单量/增值"列的 CSV/xlsx
- 一句"更新乐回收"

---

## 4. 标准流程（按顺序，不可跳步）

```
[1] 解析用户输入 → {姓名: [单量, 增值]}
    |__ 例: {"邵乐乐":[8,138], "李泽":[7,451], "陈超磊":[6,1197], "杨丽华":[5,1067]}

[2] 备份当前表（先备份再改）：
    cp '/workspace/李家村8月任务进度.xlsx' '/workspace/_备份/李家村8月任务进度_备份YYYYMMDD_HHMMSS.xlsx'

[3] 写入固定单元格：
    python3 update_lehuishou.py --xlsx '/workspace/李家村8月任务进度.xlsx' \
        --data '{"邵乐乐":[8,138],"李泽":[7,451],"陈超磊":[6,1197],"杨丽华":[5,1067]}'
    -- 没出现在 data 里的姓名（如张博晨）保留原值，不去清零（持久化靠 xlsx）
    -- 工具会校验 T19/U19 的 SUM 公式没被破坏

[4] 复算 data.json（按用户**整体**标准更新流程的铁律：先拉用友最新两张表 → calc_data）：
    cd /root/.codebuddy/artifact/shop
    python3 fetch_yonyou_http.py         # 拉门店毛利明细
    python3 fetch_sales_analysis_http.py # 拉销售分析
    python3 calc_data.py yonyou_raw.tsv --xlsx '/workspace/李家村8月任务进度.xlsx'
    python3 merge_qudao.py data.json '/workspace/李家村8月任务进度.xlsx'
    python3 build.py

[5] 把最新看板复制到 /workspace 方便用户直接打开：
    cp /root/.codebuddy/artifact/shop/index.html /workspace/李家村看板_最新.html

[6] 发回用户：
    - 表：/workspace/李家村8月任务进度.xlsx
    - 看板：/workspace/李家村看板_最新.html
```

---

## 5. 关键不变项（任何修改不能让它们失效）

| 项 | 位置 |
|---|---|
| 行号↔姓名映射 | `LEHUI_ROWS = {邵乐乐:14, 杨丽华:15, 李泽:16, 陈超磊:17, 张博晨:18}` |
| 列号 | T=20, U=21 |
| 表头 | T12="乐回收", T13="单量", U13="增值" |
| 公式行 | T19=SUM(T14:T18), U19=SUM(U14:U18) |
| 持久化介质 | 唯一：`xlsx` 文件（不另起 JSON / 数据库） |

---

## 6. 看板展示约定（已固化）

- 看板从 `data.json → store.qcs.乐回收` 和 `people[n].qcs.乐回收` 读，不再有独立"乐回收（手动录入）"板块
- 卡片标签："乐回收（公司净利）"，与"太力回收（自动）"并列
- 无"手动录入"标记、无"沿用上次"徽标（持久化由表本身承载，不需要展示状态）

---

## 7. 出错检查清单

| 现象 | 检查项 |
|---|---|
| 写入失败 "找不到表" | 确认 xlsx 路径，且文件存在 |
| 写入失败 "没有 [李家村销售] sheet" | 表被改名，恢复 |
| 写入失败 "公式被改坏了" | T19/U19 被人手工改动，从备份恢复后重写 |
| 看板看不到乐回收 | data.json 的 store.qcs.乐回收 应有 orders/amount/增值 三字段 |
| 数据没生效 | 检查 xlsx 里 T14:T18 单元格实际值 |
| 复算后数值对不上 | calc_data.py 读的是 data_only=True 的缓存，需要 WPS/Excel 打开一次刷新，或用 LibreOffice headless 计算 |
