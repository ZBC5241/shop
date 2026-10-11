#!/bin/bash
# find_task_xlsx.sh — 李家村任务底表动态发现（shell 版，与 ljc_paths.py 同逻辑）
# 用法: XLSX="$("$SHOP_DIR/find_task_xlsx.sh")"
# 按修改时间取最新的 李家村*任务进度.xlsx，翻月后无需改脚本。
ls -t /Users/mac/Desktop/李家村销售/李家村*任务进度.xlsx 2>/dev/null | grep -v '~\$' | head -1
