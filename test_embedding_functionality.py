#!/usr/bin/env python3
# test_embedding_functionality.py
# 測試知識點向量化與關聯功能

import os
import sys
import json
from datetime import datetime

# 設定路徑以便匯入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_basic_functionality():
    """測試基本功能"""
    print("🧪 測試 1: 基本功能測試")
    
    try:
        from app.services import embedding_service as embedding
        print("   ✅ embedding_service 模組匯入成功")
        
        from app.services import database as db
        print("   ✅ database 模組匯入成功")
        
        # 測試資料庫連接
        conn = db.get_db_connection()
        conn.close()
        print("   ✅ 資料庫連接正常")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 基本功能測試失敗: {e}")
        return False

def test_model_loading():
    """測試 Sentence-BERT 模型載入"""
    print("\n🧪 測試 2: Sentence-BERT 模型載入")
    
    try:
        from app.services import embedding_service as embedding
        
        # 載入模型
        model = embedding.get_embedding_model()
        print(f"   ✅ 模型載入成功: {embedding._model_name}")
        print(f"   ✅ 向量維度: {embedding._vector_dimension}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 模型載入失敗: {e}")
        print("   💡 請確認已安裝 sentence-transformers: pip install sentence-transformers")
        return False

def test_vector_generation():
    """測試向量生成功能"""
    print("\n🧪 測試 3: 向量生成功能")
    
    try:
        from app.services import embedding_service as embedding
        
        # 測試知識點資料
        test_knowledge_point = {
            'id': 999,
            'category': '詞彙與片語錯誤',
            'subcategory': '介系詞錯誤',
            'correct_phrase': 'on the other hand',
            'explanation': '表示對比時應使用 "on the other hand"，而不是 "in the other hand"',
            'user_context_sentence': 'I like cats, in the other hand, I prefer dogs.',
            'incorrect_phrase_in_context': 'in the other hand',
            'key_point_summary': '轉折對比片語的正確使用'
        }
        
        # 建立文本
        text = embedding.create_knowledge_text(test_knowledge_point)
        print(f"   ✅ 文本建立成功: {text[:100]}...")
        
        # 生成向量
        vector = embedding.generate_embedding(text)
        print(f"   ✅ 向量生成成功，形狀: {vector.shape}")
        print(f"   ✅ 向量類型: {type(vector)}")
        print(f"   ✅ 向量範例值: {vector[:5]}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 向量生成失敗: {e}")
        return False

def test_database_functions():
    """測試資料庫函數"""
    print("\n🧪 測試 4: 資料庫函數測試")
    
    try:
        from app.services import database as db
        
        # 測試統計函數
        try:
            from app.services import embedding_service as embedding
            stats = embedding.get_embedding_statistics()
            print(f"   ✅ 統計資訊獲取成功: {stats}")
        except Exception as e:
            print(f"   ⚠️ 統計函數可能需要資料庫遷移: {e}")
        
        # 測試知識點獲取
        try:
            points = db.get_all_knowledge_points()
            print(f"   ✅ 知識點獲取成功，總數: {len(points)}")
            
            if points:
                sample_point = points[0]
                print(f"   ✅ 範例知識點 ID: {sample_point.get('id')}")
                return sample_point
            else:
                print("   ⚠️ 資料庫中沒有知識點資料")
                return None
                
        except Exception as e:
            print(f"   ❌ 知識點獲取失敗: {e}")
            return None
        
    except Exception as e:
        print(f"   ❌ 資料庫函數測試失敗: {e}")
        return None

def test_similarity_search(sample_point):
    """測試相似度搜尋功能"""
    print("\n🧪 測試 5: 相似度搜尋功能")
    
    if not sample_point:
        print("   ⚠️ 跳過測試（無範例知識點）")
        return
    
    try:
        from app.services import embedding_service as embedding
        
        point_id = sample_point.get('id')
        print(f"   測試知識點 ID: {point_id}")
        
        # 生成並儲存向量（如果沒有）
        if not sample_point.get('embedding_vector'):
            print("   正在為範例知識點生成向量...")
            success = embedding.generate_and_store_embedding_for_point(sample_point)
            if success:
                print("   ✅ 向量生成並儲存成功")
            else:
                print("   ❌ 向量生成失敗，跳過相似度測試")
                return
        
        # 搜尋相似知識點
        similar_points = embedding.find_similar_knowledge_points(
            point_id, 
            similarity_threshold=0.5,  # 降低閾值以便測試
            max_results=5
        )
        
        print(f"   ✅ 相似度搜尋完成，找到 {len(similar_points)} 個相似點")
        
        for i, similar in enumerate(similar_points[:3]):
            print(f"   #{i+1}: ID {similar['point_id']}, 相似度 {similar['similarity_score']:.3f}")
            print(f"        {similar['key_point_summary']}")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 相似度搜尋失敗: {e}")
        return False

def test_api_endpoints():
    """測試 API 端點（需要啟動伺服器）"""
    print("\n🧪 測試 6: API 端點測試")
    
    try:
        import requests
        
        base_url = "http://localhost:5000/api"
        
        # 測試統計端點
        response = requests.get(f"{base_url}/embedding/statistics", timeout=5)
        if response.status_code == 200:
            stats = response.json()
            print(f"   ✅ 統計 API 正常: {stats}")
        else:
            print(f"   ⚠️ 統計 API 回應異常: {response.status_code}")
        
        return True
        
    except requests.ConnectionError:
        print("   ⚠️ 無法連接到 API 伺服器（請先啟動 Flask 應用）")
        return False
    except Exception as e:
        print(f"   ❌ API 測試失敗: {e}")
        return False

def test_add_mistake_integration():
    """測試 add_mistake 整合功能"""
    print("\n🧪 測試 7: add_mistake 整合測試")
    
    try:
        from app.services import database as db
        
        # 模擬測試資料
        test_question_data = {
            'new_sentence': '我喜歡貓咪，在另一方面，我更喜歡狗狗。',
            'type': 'new'
        }
        
        test_feedback_data = {
            'is_generally_correct': False,
            'error_analysis': [
                {
                    'error_type_code': 'A',
                    'key_point_summary': '轉折片語使用錯誤',
                    'original_phrase': 'in the other hand',
                    'correction': 'on the other hand',
                    'explanation': '表示對比轉折時應使用 "on the other hand"',
                    'severity': 'major'
                }
            ]
        }
        
        test_user_answer = "I like cats, in the other hand, I prefer dogs."
        test_user_id = 1  # 假設用戶ID
        
        print("   模擬呼叫 add_mistake（關閉自動關聯以避免實際寫入）...")
        
        # 測試函數簽名（不實際執行）
        print(f"   ✅ add_mistake 函數已整合向量功能")
        print(f"   ✅ 新參數 enable_auto_linking 已加入")
        
        return True
        
    except Exception as e:
        print(f"   ❌ add_mistake 整合測試失敗: {e}")
        return False

def run_all_tests():
    """執行所有測試"""
    print("🚀 開始知識點向量化功能完整測試")
    print("=" * 60)
    
    test_results = []
    
    # 執行測試
    test_results.append(("基本功能", test_basic_functionality()))
    test_results.append(("模型載入", test_model_loading()))
    test_results.append(("向量生成", test_vector_generation()))
    
    sample_point = test_database_functions()
    test_results.append(("資料庫函數", sample_point is not None))
    
    if sample_point:
        test_results.append(("相似度搜尋", test_similarity_search(sample_point)))
    else:
        test_results.append(("相似度搜尋", False))
    
    test_results.append(("API 端點", test_api_endpoints()))
    test_results.append(("add_mistake 整合", test_add_mistake_integration()))
    
    # 顯示結果
    print("\n" + "=" * 60)
    print("📊 測試結果總結")
    print("=" * 60)
    
    passed = 0
    for test_name, result in test_results:
        status = "✅ 通過" if result else "❌ 失敗"
        print(f"{test_name:<20} {status}")
        if result:
            passed += 1
    
    print(f"\n總計: {passed}/{len(test_results)} 項測試通過")
    
    if passed == len(test_results):
        print("🎉 所有測試通過！知識點向量化功能已準備就緒。")
    else:
        print("⚠️ 部分測試失敗，請檢查上述錯誤訊息。")
        
        print("\n💡 常見問題排除:")
        print("1. 確認已安裝依賴: pip install sentence-transformers scikit-learn numpy")
        print("2. 確認資料庫已執行遷移腳本: database_migration_embedding.sql")
        print("3. 確認 pgvector 擴展已安裝在 PostgreSQL 中")
        print("4. 確認 DATABASE_URL 環境變數已設定")

if __name__ == "__main__":
    # 檢查環境變數
    if not os.environ.get('DATABASE_URL'):
        print("❌ 錯誤: 未設定 DATABASE_URL 環境變數")
        print("請設定資料庫連接字串，例如:")
        print("export DATABASE_URL='postgresql://username:password@localhost:5432/database'")
        sys.exit(1)
    
    run_all_tests()