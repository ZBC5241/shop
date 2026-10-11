#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ljc_paths.py — 李家村任务底表动态发现（2026-10-11 根治翻月硬编码）

背景：底表文件名含月份（如 李家村10月任务进度.xlsx），每月翻月后文件名
变化。此前 15+ 脚本硬编码「9月」路径，10-01 翻月后全管线找不到文件挂掉，
dailypush 定时任务被停。本模块按修改时间动态发现最新底表，翻月后无需
改任何脚本。

用法：
    from ljc_paths import find_task_xlsx
    DEFAULT_XLSX = find_task_xlsx() or "/Users/mac/Desktop/李家村销售/李家村10月任务进度.xlsx"
"""
import glob
import os

_LJC_DIR = "/Users/mac/Desktop/李家村销售"
_PATTERN = os.path.join(_LJC_DIR, "李家村*任务进度.xlsx")


def find_task_xlsx():
    """返回最新修改的李家村任务底表路径；找不到返回 None。"""
    cands = [p for p in glob.glob(_PATTERN)
             if not os.path.basename(p).startswith("~$")]
    if not cands:
        return None
    return max(cands, key=os.path.getmtime)


if __name__ == "__main__":
    p = find_task_xlsx()
    print(p if p else "NOT_FOUND")
