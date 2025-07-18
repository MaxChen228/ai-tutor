#!/bin/bash

# 設定你的 Render URL
BASE_URL="https://ai-tutor-ikjn.onrender.com"

echo "🧪 測試 API 端點..."

echo "1. 測試單字庫統計："
curl -s "$BASE_URL/api/vocabulary/statistics" | python -m json.tool

echo -e "\n2. 測試獲取單字列表："
curl -s "$BASE_URL/api/vocabulary/words?limit=3" | python -m json.tool

echo -e "\n3. 測試AI生成定義："
curl -s -X POST "$BASE_URL/api/vocabulary/ai/define" \
  -H "Content-Type: application/json" \
  -d '{"word": "test", "context": "testing the API"}' | python -m json.tool

echo -e "\n✅ 測試完成！"
