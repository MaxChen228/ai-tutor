# 知識點自動關聯功能 - 安裝與使用指南

## 🎯 功能概述

本功能使用 **Sentence-BERT** 本地模型為知識點生成語義向量，並通過餘弦相似度自動發現知識點間的關聯性，幫助學習者理解相關概念之間的聯繫。

### 核心特色
- ✅ **完全免費** - 使用本地 Sentence-BERT 模型，無 API 費用
- ✅ **多語言支援** - 支援中英文混合文本處理
- ✅ **即時關聯** - 新增知識點時自動發現相關概念
- ✅ **高效搜尋** - 使用 pgvector 優化的向量搜尋
- ✅ **智能建議** - 基於語義相似度的學習路徑推薦

## 📋 系統需求

### 軟體需求
- Python 3.8+
- PostgreSQL 12+ 
- pgvector 擴展
- 至少 2GB RAM（用於模型載入）

### 硬體建議
- CPU: 4核心以上
- RAM: 4GB 以上
- 儲存: 至少 1GB 可用空間（模型檔案）

## 🚀 安裝步驟

### 步驟 1: 安裝 pgvector 擴展

#### 方法 A: 使用 apt (Ubuntu/Debian)
```bash
# 安裝開發工具
sudo apt-get update
sudo apt-get install -y postgresql-server-dev-all build-essential git

# 安裝 pgvector
git clone https://github.com/pgvector/pgvector.git
cd pgvector
make
sudo make install
```

#### 方法 B: 使用 Homebrew (macOS)
```bash
brew install pgvector
```

#### 方法 C: 使用 Docker
```yaml
# docker-compose.yml
version: '3.8'
services:
  postgres:
    image: pgvector/pgvector:pg15
    environment:
      POSTGRES_DB: ai_tutor
      POSTGRES_USER: your_user
      POSTGRES_PASSWORD: your_password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### 步驟 2: 安裝 Python 依賴

```bash
# 確保在 ai-tutor 專案目錄中
cd /path/to/ai-tutor

# 安裝新增的依賴
pip install sentence-transformers>=2.2.0 scikit-learn>=1.0.0 numpy>=1.21.0

# 或者重新安裝全部依賴
pip install -r requirements.txt
```

### 步驟 3: 執行資料庫遷移

```bash
# 連接到 PostgreSQL 資料庫
psql -U your_user -d ai_tutor

# 執行遷移腳本
\i database_migration_embedding.sql

# 檢查安裝
SELECT * FROM knowledge_linking_stats;
```

### 步驟 4: 測試安裝

```bash
# 設定環境變數
export DATABASE_URL="postgresql://user:password@localhost:5432/ai_tutor"

# 執行測試腳本
python test_embedding_functionality.py
```

## 🔧 配置說明

### 環境變數

```bash
# 必需的環境變數
export DATABASE_URL="postgresql://user:password@localhost:5432/ai_tutor"

# 可選的配置
export EMBEDDING_MODEL="paraphrase-multilingual-MiniLM-L12-v2"  # 預設模型
export SIMILARITY_THRESHOLD="0.8"  # 預設相似度閾值
export MAX_LINKS_PER_POINT="5"     # 每個知識點最大關聯數
```

### 模型選擇

| 模型名稱 | 維度 | 語言支援 | 檔案大小 | 推薦用途 |
|---------|------|----------|----------|----------|
| `paraphrase-multilingual-MiniLM-L12-v2` | 384 | 多語言 | ~120MB | **推薦** - 平衡效果與效能 |
| `paraphrase-MiniLM-L6-v2` | 384 | 英文 | ~90MB | 英文為主的內容 |
| `all-MiniLM-L6-v2` | 384 | 英文 | ~90MB | 通用型英文模型 |

## 📊 使用方法

### 1. 批次處理現有知識點

```bash
# 執行批次處理腳本
python batch_process_embeddings.py

# 選項說明：
# 1. 測試模型載入
# 2. 批次處理知識點向量  ← 首次安裝選這個
# 3. 重建所有關聯
# 4. 查看統計資訊
```

### 2. 自動關聯（整合模式）

新的知識點會在 `add_mistake()` 函數中自動生成向量並建立關聯：

```python
# 在現有代碼中，已自動啟用
db.add_mistake(
    question_data, 
    user_answer, 
    feedback_data, 
    user_id=user_id,
    enable_auto_linking=True  # 預設啟用
)
```

### 3. API 端點使用

#### 獲取統計資訊
```bash
curl http://localhost:5000/api/embedding/statistics
```

#### 尋找相似知識點
```bash
curl "http://localhost:5000/api/embedding/find_similar/123?threshold=0.8&max_results=5"
```

#### 文本搜尋知識點
```bash
curl -X POST http://localhost:5000/api/embedding/search_by_text \
  -H "Content-Type: application/json" \
  -d '{"text": "on the other hand 用法", "threshold": 0.7}'
```

#### 獲取知識點關聯
```bash
curl http://localhost:5000/api/embedding/knowledge_links/123
```

## 🎛️ 管理功能

### 批次處理選項

```bash
# 處理指定數量的知識點
python batch_process_embeddings.py
# 輸入限制數量，如：100

# 重建所有關聯
python batch_process_embeddings.py
# 選擇選項 3
```

### 手動關聯管理

```bash
# 建立手動關聯
curl -X POST http://localhost:5000/api/embedding/create_manual_link \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_point_id": 123, "target_point_id": 456}'

# 移除關聯
curl -X DELETE http://localhost:5000/api/embedding/remove_link \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"source_point_id": 123, "target_point_id": 456}'
```

## 📈 效能調優

### 資料庫最佳化

```sql
-- 建立額外索引（如果需要）
CREATE INDEX CONCURRENTLY idx_knowledge_points_user_embedding 
ON knowledge_points(user_id) WHERE embedding_vector IS NOT NULL;

-- 更新統計資訊
ANALYZE knowledge_points;
ANALYZE knowledge_links;
```

### 向量搜尋調優

在 `app/services/embedding_service.py` 中調整參數：

```python
# 相似度閾值調整
SIMILARITY_THRESHOLD = 0.8  # 提高 = 更嚴格，降低 = 更寬鬆

# 批次大小調整
BATCH_SIZE = 32  # 根據記憶體容量調整

# 最大關聯數調整
MAX_LINKS_PER_POINT = 5  # 避免過多關聯
```

## 🐛 常見問題

### Q1: 模型下載緩慢
**A:** 首次運行會下載約120MB的模型檔案，請耐心等待。模型會緩存在 `~/.cache/huggingface/`

### Q2: 記憶體不足
**A:** 
- 減少 `batch_size` 參數
- 或分批處理知識點：`python batch_process_embeddings.py` 並設定較小的處理數量

### Q3: pgvector 安裝失敗
**A:** 
- 確認 PostgreSQL 開發套件已安裝
- 使用 Docker 方案作為替代

### Q4: 相似度搜尋結果不準確
**A:** 
- 調整 `similarity_threshold` 參數
- 檢查知識點文本內容是否充足
- 考慮使用不同的 Sentence-BERT 模型

### Q5: API 端點無回應
**A:** 
- 確認 Flask 應用已啟動
- 檢查路由是否正確註冊
- 查看伺服器日誌

## 📝 日誌與除錯

### 啟用詳細日誌

```python
# 在 app/services/embedding_service.py 中
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 查看處理進度

```sql
-- 檢查向量生成進度
SELECT 
    COUNT(*) as total_points,
    COUNT(embedding_vector) as with_vectors,
    COUNT(embedding_vector) * 100.0 / COUNT(*) as percentage
FROM knowledge_points 
WHERE is_archived = FALSE;

-- 檢查關聯建立狀況
SELECT link_type, COUNT(*) 
FROM knowledge_links 
WHERE is_active = TRUE 
GROUP BY link_type;
```

## 🔄 升級與維護

### 定期維護任務

```bash
# 每週執行一次清理
curl -X POST http://localhost:5000/api/embedding/cleanup_links \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# 重新計算統計資訊
psql -c "ANALYZE knowledge_points; ANALYZE knowledge_links;"
```

### 模型更新

如需更換模型，修改 `app/services/embedding_service.py`:

```python
_model_name = "your-new-model-name"
_vector_dimension = new_dimension  # 例如：768
```

然後重新執行批次處理。

## 📞 技術支援

如遇到問題，請提供以下資訊：
1. 錯誤訊息完整內容
2. 系統環境（Python、PostgreSQL 版本）
3. 測試腳本的執行結果
4. 相關日誌檔案

---

## ✨ 功能擴展計劃

- 🔮 支援更多語言模型
- 📊 向量化品質評估工具  
- 🎯 個人化相似度學習
- 🔍 進階語義搜尋介面
- 📱 關聯視覺化儀表板