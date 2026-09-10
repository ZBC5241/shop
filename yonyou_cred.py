# -*- coding: utf-8 -*-
"""用友云登录密码统一从 macOS 钥匙串读取, 杜绝脚本内硬编码明文。
条目: service=yonyou, account=18161914293
其他脚本: from yonyou_cred import get_yonyou_pwd
"""
import subprocess

def get_yonyou_pwd(account="18161914293"):
    """从 macOS 钥匙串读取用友密码。绝不硬编码明文。account 为用友账号。"""
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-w"],
            capture_output=True, text=True, timeout=15)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception as e:
        print("KEYCHAIN_ERR", e)
    raise SystemExit("ERR: 钥匙串未找到 yonyou 密码, 请先存: security add-generic-password -s yonyou -a 18161914293 -w '<密码>'")
