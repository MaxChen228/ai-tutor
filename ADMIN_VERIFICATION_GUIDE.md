# 管理界面功能驗證指南

## 🚀 快速驗證步驟

### 1. 啟動應用
```bash
# 確保在 ai-tutor 目錄中
cd /path/to/ai-tutor

# 設定環境變數 (如果尚未設定)
export DATABASE_URL="your_database_url"

# 啟動應用
python run.py
```

### 2. 運行自動測試
```bash
# 執行自動測試腳本
python test_admin_interface.py
```

### 3. 手動驗證步驟

#### A. 檢查基本路由
在瀏覽器中訪問以下地址：

1. **管理儀表板**
   ```
   http://localhost:5000/admin
   ```
   ✅ 應顯示: 統計卡片、進度條、快速操作按鈕

2. **知識點列表**
   ```
   http://localhost:5000/admin/knowledge-points
   ```
   ✅ 應顯示: 知識點表格、篩選選項、分頁控制

3. **批次處理界面**
   ```
   http://localhost:5000/admin/batch-processing
   ```
   ✅ 應顯示: 處理設定、進度監控、日誌顯示

4. **網絡視覺化**
   ```
   http://localhost:5000/admin/network-visualization
   ```
   ✅ 應顯示: D3.js 圖表、控制面板、統計資訊

#### B. 測試API端點
使用 curl 或 Postman 測試：

1. **統計資訊API**
   ```bash
   curl http://localhost:5000/api/embedding/statistics
   ```
   ✅ 期望回應: JSON格式的統計資料

2. **網絡資料API**
   ```bash
   curl http://localhost:5000/admin/api/network-data?limit=10
   ```
   ✅ 期望回應: 包含nodes和links的JSON資料

#### C. 驗證靜態文件
檢查以下文件是否可正常載入：

1. **CSS樣式**
   ```
   http://localhost:5000/static/css/admin.css
   ```

2. **JavaScript腳本**
   ```
   http://localhost:5000/static/js/network-visualization.js
   ```

## 🔍 功能測試清單

### 管理儀表板功能
- [ ] 統計卡片顯示正確數據
- [ ] 進度條反映真實進度
- [ ] 快速操作按鈕可點擊
- [ ] 重新整理功能正常

### 知識點列表功能
- [ ] 表格正確顯示知識點資料
- [ ] 篩選功能正常工作
- [ ] 分頁導航正確
- [ ] 詳情模態框可開啟
- [ ] 重新生成向量功能正常

### 批次處理功能
- [ ] 設定面板可調整參數
- [ ] 開始處理按鈕正常
- [ ] 進度條實時更新
- [ ] 日誌正確顯示
- [ ] 暫停/清除功能正常

### 網絡視覺化功能
- [ ] D3.js 圖表正常載入
- [ ] 節點和連結正確顯示
- [ ] 縮放和拖拽功能正常
- [ ] 搜尋功能可用
- [ ] 節點詳情面板正常
- [ ] 布局切換功能正常

## ⚠️ 常見問題排除

### 1. 頁面顯示 404 錯誤
**原因**: 管理路由未正確註冊
**解決**: 檢查 `app/__init__.py` 是否包含:
```python
from .routes.admin import admin_bp
app.register_blueprint(admin_bp)
```

### 2. 靜態文件載入失敗
**原因**: 靜態文件路徑不正確
**解決**: 確認以下目錄結構存在:
```
app/
├── static/
│   ├── css/admin.css
│   └── js/network-visualization.js
└── templates/admin/
```

### 3. API 回應 500 錯誤
**原因**: 資料庫連接或環境變數問題
**解決**: 
- 檢查 `DATABASE_URL` 環境變數
- 確認資料庫遷移已執行
- 查看服務器日誌

### 4. 網絡圖不顯示
**原因**: D3.js 載入失敗或資料問題
**解決**:
- 檢查瀏覽器控制台錯誤
- 確認 D3.js CDN 可訪問
- 驗證API資料格式正確

### 5. 認證問題
**原因**: JWT令牌缺失或過期
**解決**:
- 某些功能需要有效的JWT令牌
- 可暫時移除 `@jwt_required()` 裝飾器進行測試

## 📊 驗證成功標準

✅ **基本功能**: 所有頁面可正常載入
✅ **API響應**: 主要API端點回應正確
✅ **視覺化**: D3.js圖表正常顯示
✅ **互動性**: 按鈕和表單正常工作
✅ **資料連接**: 能從資料庫獲取真實資料

## 🎯 下一步驗證

1. **資料完整性**: 使用批次處理生成測試向量
2. **效能測試**: 測試大量節點的視覺化效能
3. **使用者體驗**: 測試完整的工作流程
4. **瀏覽器相容性**: 在不同瀏覽器中測試
5. **響應式設計**: 在不同螢幕尺寸下測試

---

💡 **提示**: 首次使用建議先執行 `python test_admin_interface.py` 進行自動驗證，然後再進行手動測試。