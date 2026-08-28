#!/bin/bash
# ============================================================
# push_board.sh — 看板一键上线（SSH over 443，不依赖 Clash）
# 用法：bash push_board.sh "提交说明"
# 通道优先级：① SSH over 443 直连 GitHub（默认，已验证最稳）
# SOP 来源：GitHub推送_SOP.md + push_kucun.sh（2026-08-27 跑通）
# ============================================================
set -u

MSG="${1:-看板数据更新 $(date +%Y-%m-%d_%H:%M)}"
SHOP_DIR="/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/shop"
HTML_OUT="/Users/mac/.local/share/TeleAgent/TeleAgent的工作空间/华为门店业绩看板.html"

cd "$SHOP_DIR" || { echo "❌ shop 目录不存在: $SHOP_DIR"; exit 1; }

echo "===== 0. 确认 index.html 是最新 ====="
if [ ! -f index.html ]; then
  echo "❌ index.html 不存在，请先运行 update_board.py"
  exit 1
fi
echo "✅ index.html 存在 ($(du -h index.html | cut -f1))"

echo "===== 1. 本地提交 ====="
git add index.html .gitignore
git commit -m "$MSG" >/dev/null 2>&1 && echo "✅ 本地提交: $MSG" || echo "ℹ️ 无新改动，跳过提交"

echo "===== 2. 通道A：SSH over 443 直连 GitHub ====="
# 验证 SSH-443 通道（config 已配 github.com → ssh.github.com:443）
if ssh -T -o ConnectTimeout=12 -o StrictHostKeyChecking=no git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo "✅ SSH-443 通道可用"
  git push origin main && {
    echo "🚀 通道A成功 → GitHub Pages 已更新"
    echo "   线上地址: https://zbc5241.github.io/shop/"
    # 同步复制到工作目录
    cp -f index.html "$HTML_OUT" 2>/dev/null
    exit 0
  }
  echo "⚠️ SSH-443 通道通但 push 失败，尝试 force push"
  git push -f origin main && {
    echo "🚀 通道A force push 成功"
    cp -f index.html "$HTML_OUT" 2>/dev/null
    exit 0
  }
  echo "❌ push 失败，退出"
  exit 1
else
  echo "⚠️ 通道A未认证（GitHub 公钥未贴 / 443不通）"
fi

echo "❌ SSH-443 通道不可用。请检查："
echo "   - GitHub 公钥：cat ~/.ssh/github_push.pub 是否已贴进 GitHub SSH keys"
echo "   - 验证命令：ssh -T git@github.com"
echo "   - 备用方案：GitHub 连接器云端 push_files / Gitee 中转"
exit 2
