---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'a96c3d4c-eee0-49f6-b9bb-383e867443d1'
  PropagateID: 'a96c3d4c-eee0-49f6-b9bb-383e867443d1'
  ReservedCode1: '7c6b65f4-7b5d-44d8-8502-279174e0a72b'
  ReservedCode2: '7c6b65f4-7b5d-44d8-8502-279174e0a72b'
---

# 李家村销售看板 · 乐机收更新 skill

> **凡用户给出"乐机收"数据（截图 / 表格 / 口述） → 落表 → 跑看板 → 发回最新表**
> 这一整套动作可由本 skill 完整闭环。
>
> ⚠️ 命名沿革：底表 2026-09 已把「乐回收」改名「**乐机收**」（T12 标题），数据链路 key 已全链路同步改名。旧名仅存在于历史记录，代码中不再出现。

---

## 1. 位置

| 角色 | 文件 |
|---|---|
| 写入工具 | `update_lehuishou.py` |
| 基准表 | `/Users/mac/Desktop/李家村销售/李家村月度任务进度.xlsx`（**唯一数据源**） |
| 看板产物 | `shop/index.html`（线上 https://zbc5241.github.io/shop/） |
| 备份 | 写入前确认 xlsx 有备份（iCloud/Time Machine），工具本身不另建备份目录 |

`update_lehuishou.py` 自带 docstring，本文档是"何时用 / 怎么用 / 出错怎么办"的人读指引。

---

## 2. 写入单元格规则（行号动态，人员变动只改底表）

《李家村销售》sheet 的"乐机收"区块结构：

```
        T12 = "乐机收"          ← 标题由底表承载，本脚本**不写**标题
        T13 = "单量"  |  U13 = "增值"
        T14~T17 = 现役员工       ← 行号 = 月任务行号 + 10（动态）
        T18 = 张博晨             ← 固定 18（店长不背任务，但保留汇总行）
        T19 = =SUM(T14:T18)     ← 公式，**不碰**
        U19 = =SUM(U14:U18)     ← 公式，**不碰**
```

- T 列 = 成交量（总单量）
- U 列 = 公司净利（总增值）
- **行号↔姓名映射已动态化**（2026-09-05）：`update_lehuishou.py` 的 `load_rows(xlsx)` 从底表「月任务」sheet B4:B7 读取现役人员（空名跳过），行号 = 月任务行号 + 10，张博晨固定 18。**人员变动只改底表，不改代码。**
- T12/T13/U13 是表头，**不碰**；T19/U19 是 SUM 公式，**不碰**（工具 verify 会校验）。

---

## 3. 触发条件

用户给出以下任一信号即可触发：

- "乐机收：邵乐乐 8 单 138 元，李泽 7 单 451 元……"
- 一张"店员/成交量/净利"的截图
- 上传一个含"店员/单量/增值"列的 CSV/xlsx
- 一句"更新乐机收"（或口头说"乐回收"，按同一业务处理）

---

## 4. 标准流程（按顺序，不可跳步）

```
[1] 解析用户输入 → {姓名: [单量, 增值]}
    |__ 例: {"邵乐乐":[8,138], "李泽":[7,451], "杨丽华":[5,1067]}

[2] 写入单元格（行号自动从底表解析）：
    python3 update_lehuishou.py \
        --xlsx '/Users/mac/Desktop/李家村销售/李家村月度任务进度.xlsx' \
        --data '{"邵乐乐":[8,138],"李泽":[7,451],"杨丽华":[5,1067]}'
    -- 没出现在 data 里的姓名（如张博晨）保留原值，不去清零（持久化靠 xlsx）
    -- 工具会校验 T19/U19 的 SUM 公式没被破坏

[3] 复算 data.json（按整体标准更新流程：拉用友最新两张表 → 全链路复算）：
    cd shop目录
    ./daily_push.sh push          # 一键：登录拉表 → calc → merge → build → 上线
    # 或手动：
    python3 calc_data.py <毛利明细.xlsx> --xlsx '<底表.xlsx>' -o data.json
    python3 merge_qudao.py data.json '<底表.xlsx>'
    python3 build.py

[4] 推送上线：
    git add -A && git commit -m "乐机收更新：<单量/金额简述>" && git push origin main
    # 线上 https://zbc5241.github.io/shop/ 1–3 分钟自动刷新

[5] 发回用户：底表 + 看板链接
```

---

## 5. 关键不变项（任何修改不能让它们失效）

| 项 | 位置 |
|---|---|
| 行号↔姓名映射 | **动态**：`load_rows(xlsx)` 读「月任务」B4:B7，行号+10；张博晨固定 18 |
| 列号 | T=20, U=21 |
| 表头 | T12="乐机收"（底表承载，脚本不写）, T13="单量", U13="增值" |
| 公式行 | T19=SUM(T14:T18), U19=SUM(U14:U18) |
| 持久化介质 | 唯一：`xlsx` 文件（不另起 JSON / 数据库） |
| data.json key | `qcs.乐机收`（orders/amount/增值），与底表 T12 同名 |

---

## 6. 看板展示约定（已固化）

**单一「回收业务」卡片**（`class="q wide"`），标题「回收业务」，内部两行紧凑文字（`.rec-list`）：

```
回收业务
  乐机收 27 单 · 公司净利 2,853
  太力回收 2 单 · 983 · 增值 138
```

- 乐机收从 `《李家村销售》` T14:U18 直读（xlsx 即持久化），与太力回收**合并在同一张卡**；
- **不再有独立「乐机收（公司净利）」5 人明细板块**，无「手动录入」标记；
- 乐机收「增值」=0 时不显示该列（太力回收增值≠0 时显示「· 增值 N」）；
- 渲染代码：`parts/03_js_core.js`「回收业务」块；样式：`parts/01_head.html` `.rec-list`。

---

## 7. 推送上线

SSH over 443 推 GitHub（`ssh -p 443`，`~/.ssh/config` 已配置 `github.com` 别名）→ `git push` 免密。

```
cd shop目录
git add -A && git commit -m "乐机收更新：<简述>" && git push origin main
```

- 仓库：`ZBC5241/shop`（main 分支），唯一正本；Claw 只做归档
- ⚠️ Gitee 中转通道已废除（2026-09-05 晨哥拍板），不要再走 ghproxy/Gitee

---

## 8. 出错检查清单

| 现象 | 检查项 |
|---|---|
| 写入失败 "找不到表" | 确认 xlsx 路径，且文件存在 |
| 写入失败 "没有 [李家村销售] sheet" | 表被改名，恢复 |
| 写入失败 "公式被改坏了" | T19/U19 被人手工改动，从备份恢复后重写 |
| 行号错乱 / 写错人 | 检查底表「月任务」B4:B7 是否与《李家村销售》T14+ 行对齐（人员变动需两处同步） |
| 看板看不到乐机收 | data.json 的 store.qcs.乐机收 应有 orders/amount/增值 三字段 |
| 数据没生效 | 检查 xlsx 里 T14:T18 单元格实际值 |
| 复算后数值对不上 | calc_data.py 读的是 data_only=True 的缓存，需要 WPS/Excel 打开一次刷新 |
| push 认证失败 | `~/.ssh/config` 的 github.com（ssh over 443）配置被清，按 GitHub推送_SOP.md 恢复 |
| 线上 404 | 仓库 `Settings → Pages` 发布源需设为 **main 分支 / (root)** |

> 历史版本说明：本 skill 前身基于 CloudStudio 环境（/workspace 路径、ghproxy 中转、陈超磊行号 17），2026-09-05 已全面迁移到本机路径 + 动态行号 + 乐机收命名。