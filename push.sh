#!/usr/bin/env bash
# ============================================================
# 李家村看板 · 推送上线脚本（三镜像自动切换）
# ------------------------------------------------------------
# 用法:  TOKEN="gho_xxx" bash push.sh "提交说明"
# 功能:
#   1. 自动提交当前全部改动
#   2. 按 ghproxy.net → gh-proxy.com → ghfast.top 顺序探测可用镜像
#   3. 经可用镜像推送 main（临时注入令牌，推完立即还原，token 不落盘）
#   4. 推送前检查远端是否有并行推送，有则 rebase 叠加，不覆盖
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

TOKEN="${TOKEN:-}"
MSG="${1:-看板更新}"
REPO_PATH="https://github.com/ZBC5241/shop.git"
ORIG_URL="https://ghproxy.net/${REPO_PATH}"
MIRRORS=("ghproxy.net" "gh-proxy.com" "ghfast.top")

# 提交（无新改动但存在未推送提交时，也继续走推送）
echo "→ 检查待提交改动..."
git status --short
git add -A
if git diff --cached --quiet; then
  if [ "$(git rev-parse main 2>/dev/null)" = "$(git rev-parse origin/main 2>/dev/null)" ]; then
    echo "⚠️  没有改动可提交，且本地与远端一致，无需推送"
    exit 0
  else
    echo "⚠️  没有新改动，但存在未推送提交，继续推送..."
  fi
else
  git commit -m "$MSG" || true
fi

# 无令牌则退出（不污染 remote）
if [ -z "$TOKEN" ]; then
  echo "❌ 缺少令牌：TOKEN=gho_xxx bash push.sh"
  exit 1
fi

push_ok=0
for m in "${MIRRORS[@]}"; do
  echo "── 尝试镜像: ${m} ──"
  # 镜像可用性探测（8 秒超时）
  if ! curl -s -o /dev/null --max-time 8 "https://${m}/${REPO_PATH%/*}/raw/main/index.html" 2>/dev/null; then
    echo "  镜像 ${m} 探测不通，跳过"
    continue
  fi
  echo "  镜像 ${m} 可用，注入令牌并推送..."
  git remote set-url origin "https://x-access-token:${TOKEN}@${m}/${REPO_PATH}"
  # 拉取远端，检查并行推送
  if git fetch origin main --quiet 2>/dev/null; then
    LB=$(git rev-parse main)
    RB=$(git rev-parse origin/main 2>/dev/null || echo "$LB")
    MB=$(git merge-base main origin/main 2>/dev/null || echo "$LB")
    if [ "$LB" != "$RB" ] && [ "$MB" != "$RB" ]; then
      echo "  远端有并行更新，rebase 叠加（不覆盖）..."
      git rebase origin/main || {
        echo "  ⚠️  rebase 冲突，请手动处理"; git remote set-url origin "$ORIG_URL"; exit 1
      }
    fi
  fi
  if git push origin main 2>&1 | tail -3; then
    push_ok=1
  fi
  git remote set-url origin "$ORIG_URL"   # 立即还原，清除令牌
  [ "$push_ok" = "1" ] && break
  echo "  镜像 ${m} 推送失败，换下一个..."
done

if [ "$push_ok" = "1" ]; then
  echo "✅ 推送成功，remote 已还原（token 即用即清）"
else
  echo "❌ 三个镜像全部失败，请检查网络或令牌"
  exit 1
fi
