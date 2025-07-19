# Render 部署指南 - AI Tutor 知識點自動關聯功能

## 🚀 部署步驟

### 1. 前置需求檢查

在 Render 部署前，確認以下項目已完成：

- ✅ PostgreSQL 資料庫已設定（推薦使用 Render PostgreSQL 或 Supabase）
- ✅ `DATABASE_URL` 環境變數已準備
- ✅ pgvector 擴展已安裝在資料庫中

### 2. Render 服務設定

#### Web Service 設定
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `gunicorn --workers 4 --bind 0.0.0.0:$PORT 'app:create_app()'`
- **Environment**: `Python 3.9+`

#### 環境變數設定
```
DATABASE_URL=postgresql://user:password@host:port/database
JWT_SECRET_KEY=your-strong-jwt-secret-key
GEMINI_API_KEY=your-gemini-api-key (可選)
OPENAI_API_KEY=your-openai-api-key (可選)
```

### 3. 資料庫遷移

部署後需要執行以下步驟：

#### 步驟 A: 安裝 pgvector 擴展
```sql
-- 連接到你的 PostgreSQL 資料庫
CREATE EXTENSION IF NOT EXISTS vector;
```

#### 步驟 B: 執行向量功能遷移
將 `database_migration_embedding.sql` 的內容在資料庫中執行。

**Render PostgreSQL 用戶**：
1. 在 Render Dashboard 中打開 PostgreSQL 服務
2. 點擊 "Connect" → "External Connection"
3. 使用 psql 連接：
   ```bash
   psql postgresql://user:password@host:port/database
   ```
4. 執行遷移腳本：
   ```sql
   \i database_migration_embedding.sql
   ```

**Supabase 用戶**：
1. 前往 Supabase Dashboard → SQL Editor
2. 貼上 `database_migration_embedding.sql` 內容並執行

### 4. 部署後設定

#### 驗證部署
訪問以下端點確認服務正常：
- `https://your-app.onrender.com/api/embedding/statistics`

#### 初始化向量功能
部署成功後，執行批次處理生成現有知識點的向量：

```bash
# 方法 1: 通過 API 端點（需要認證）
curl -X POST https://your-app.onrender.com/api/embedding/batch_process \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"limit": 100}'

# 方法 2: 通過 Render Shell（如果啟用）
# 在 Render Dashboard 中開啟 Shell 並執行：
python batch_process_embeddings.py
```

## 📊 效能建議

### Render 方案建議
- **Starter Plan**: 適合測試和小規模使用
- **Professional Plan**: 生產環境推薦（更多 RAM 用於模型載入）

### 記憶體最佳化
```python
# 在 app/services/embedding_service.py 中調整
_model_name = "paraphrase-MiniLM-L6-v2"  # 較小的模型（英文）
# 或保持 "paraphrase-multilingual-MiniLM-L12-v2"（多語言）
```

### 批次處理策略
- 初次部署時分批處理知識點（每次50-100個）
- 設定較低的相似度閾值（0.75）避免過多關聯

## 🔧 故障排除

### 常見部署問題

#### 1. 記憶體不足
**症狀**: Sentence-BERT 模型載入失敗
**解決**: 
- 升級到 Professional Plan
- 或使用更小的模型

#### 2. pgvector 擴展未安裝
**症狀**: `CREATE EXTENSION vector` 失敗
**解決**: 
- Render PostgreSQL: 聯絡支援啟用 pgvector
- 改用 Supabase（內建支援 pgvector）

#### 3. 模型下載慢
**症狀**: 首次啟動很慢
**解決**: 
- 這是正常現象，模型會緩存
- 後續啟動會變快

### 監控建議

```bash
# 檢查向量化狀態
curl https://your-app.onrender.com/api/embedding/statistics

# 檢查系統健康
curl https://your-app.onrender.com/api/data/get_dashboard
```

## 🎯 部署檢查清單

- [ ] Render Web Service 已建立
- [ ] 環境變數已設定
- [ ] PostgreSQL 資料庫已連接
- [ ] pgvector 擴展已安裝
- [ ] 遷移腳本已執行
- [ ] API 端點回應正常
- [ ] 批次處理已完成
- [ ] 向量關聯功能正常運作

## 🔄 更新流程

當需要更新代碼時：
1. 推送到 GitHub
2. Render 會自動重新部署
3. 檢查 `/api/embedding/statistics` 確認功能正常

---

## 📞 支援聯絡

如遇到部署問題：
1. 檢查 Render 部署日誌
2. 查看 `EMBEDDING_SETUP.md` 詳細文檔
3. 驗證資料庫連接和擴展安裝