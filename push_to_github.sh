#!/bin/bash

echo "🚀 推送知識點自動關聯功能到 GitHub"
echo "================================================"

# 檢查是否有未提交的變更
if [ -n "$(git status --porcelain)" ]; then
    echo "❌ 發現未提交的變更，請先提交"
    git status
    exit 1
fi

# 檢查提交歷史
echo "📋 最近的提交："
git log --oneline -3

echo ""
echo "🔄 準備推送到 GitHub..."
echo "如果遇到認證問題，請："
echo "1. 確認已登入 GitHub"
echo "2. 或手動執行: git push origin new"

# 嘗試推送
git push origin new

if [ $? -eq 0 ]; then
    echo "✅ 推送成功！"
    echo ""
    echo "🎯 下一步："
    echo "1. 前往 Render Dashboard"
    echo "2. 建立新的 Web Service"
    echo "3. 連接到 GitHub 倉庫: MaxChen228/ai-tutor"
    echo "4. 選擇 'new' 分支"
    echo "5. 設定環境變數："
    echo "   - DATABASE_URL=你的PostgreSQL連接字串"
    echo "   - JWT_SECRET_KEY=你的JWT密鑰"
    echo ""
    echo "📖 詳細部署指南請參考: RENDER_DEPLOY.md"
else
    echo "❌ 推送失敗"
    echo ""
    echo "💡 手動推送方法："
    echo "1. 開啟終端機"
    echo "2. cd /Users/chenliangyu/my_project/ai-tutor"
    echo "3. git push origin new"
    echo "4. 輸入 GitHub 用戶名和密碼/token"
fi