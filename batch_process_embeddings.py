#!/usr/bin/env python3
# batch_process_embeddings.py
# 批次處理現有知識點，生成向量並建立關聯

import os
import sys
import logging
from datetime import datetime

# 設定路徑以便匯入模組
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services import embedding_service as embedding
from app.services import database as db

# 設定日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """主要執行函數"""
    print("=" * 60)
    print("🚀 知識點向量化與關聯建立批次處理工具")
    print("=" * 60)
    
    # 檢查資料庫連接
    try:
        conn = db.get_db_connection()
        conn.close()
        print("✅ 資料庫連接正常")
    except Exception as e:
        print(f"❌ 資料庫連接失敗: {e}")
        return
    
    # 獲取統計資訊
    try:
        stats = embedding.get_embedding_statistics()
        print(f"\n📊 當前狀態:")
        print(f"   - 已有向量的知識點: {stats.get('points_with_vectors', 0)}")
        print(f"   - 待處理的知識點: {stats.get('points_without_vectors', 0)}")
        print(f"   - 現有關聯數: {stats.get('active_links', 0)}")
        print(f"   - 平均相似度: {stats.get('avg_similarity_score', 0):.3f}")
        
        if stats.get('points_without_vectors', 0) == 0:
            print("\n🎉 所有知識點都已生成向量！")
            
            # 詢問是否要重建關聯
            response = input("\n是否要重建所有知識點的關聯？(y/N): ").strip().lower()
            if response == 'y':
                rebuild_all_links()
            return
            
    except Exception as e:
        print(f"⚠️ 獲取統計資訊失敗: {e}")
    
    # 詢問用戶確認
    response = input(f"\n是否開始批次處理？(y/N): ").strip().lower()
    if response != 'y':
        print("取消處理。")
        return
    
    # 詢問處理數量限制
    try:
        limit_input = input("請輸入處理數量限制（直接按 Enter 處理全部）: ").strip()
        limit = int(limit_input) if limit_input else None
    except ValueError:
        limit = None
    
    # 開始批次處理
    print(f"\n🔄 開始批次處理（限制: {limit or '無限制'}）...")
    start_time = datetime.now()
    
    try:
        # 步驟1: 生成向量
        print("\n步驟 1/3: 生成知識點向量")
        result = embedding.batch_process_knowledge_points(limit=limit)
        
        print(f"   ✅ 處理完成:")
        print(f"      - 總處理數: {result['processed']}")
        print(f"      - 成功: {result['success']}")
        print(f"      - 失敗: {result['failed']}")
        
        if result['failed'] > 0:
            print(f"   ⚠️ 有 {result['failed']} 個知識點處理失敗，請檢查日誌")
        
        # 步驟2: 建立關聯
        if result['success'] > 0:
            print(f"\n步驟 2/3: 建立語義關聯")
            create_links_for_recent_points(limit=result['success'])
        
        # 步驟3: 清理無效關聯
        print(f"\n步驟 3/3: 清理無效關聯")
        deleted_count = embedding.cleanup_knowledge_links()
        print(f"   ✅ 清理了 {deleted_count} 個無效關聯")
        
    except Exception as e:
        print(f"❌ 批次處理過程中發生錯誤: {e}")
        logger.exception("批次處理失敗")
        return
    
    # 顯示最終統計
    end_time = datetime.now()
    duration = end_time - start_time
    
    print(f"\n🎉 批次處理完成！")
    print(f"   總耗時: {duration.total_seconds():.1f} 秒")
    
    try:
        final_stats = embedding.get_embedding_statistics()
        print(f"\n📊 最終狀態:")
        print(f"   - 已有向量的知識點: {final_stats.get('points_with_vectors', 0)}")
        print(f"   - 待處理的知識點: {final_stats.get('points_without_vectors', 0)}")
        print(f"   - 總關聯數: {final_stats.get('active_links', 0)}")
        print(f"   - 平均相似度: {final_stats.get('avg_similarity_score', 0):.3f}")
        
    except Exception as e:
        print(f"⚠️ 獲取最終統計失敗: {e}")

def create_links_for_recent_points(limit=100):
    """為最近生成向量的知識點建立關聯"""
    try:
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id FROM knowledge_points 
                WHERE embedding_vector IS NOT NULL 
                  AND is_archived = FALSE
                ORDER BY embedding_updated_at DESC NULLS LAST
                LIMIT %s
            """, (limit,))
            
            point_ids = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        print(f"   為 {len(point_ids)} 個知識點建立關聯...")
        
        total_links = 0
        for i, point_id in enumerate(point_ids):
            try:
                link_count = embedding.auto_link_knowledge_point(point_id, similarity_threshold=0.8)
                total_links += link_count
                
                if (i + 1) % 20 == 0:
                    print(f"      已處理 {i + 1}/{len(point_ids)} 個知識點")
                    
            except Exception as e:
                logger.error(f"為知識點 {point_id} 建立關聯失敗: {e}")
                continue
        
        print(f"   ✅ 總共建立了 {total_links} 個關聯")
        
    except Exception as e:
        print(f"   ❌ 建立關聯失敗: {e}")

def rebuild_all_links():
    """重建所有知識點的關聯"""
    print("\n🔄 重建所有知識點關聯...")
    
    try:
        # 先清除現有關聯
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM knowledge_links")
            deleted_count = cursor.rowcount
            conn.commit()
        conn.close()
        
        print(f"   清除了 {deleted_count} 個現有關聯")
        
        # 獲取所有有向量的知識點
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id FROM knowledge_points 
                WHERE embedding_vector IS NOT NULL 
                  AND is_archived = FALSE
                ORDER BY id
            """)
            point_ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        print(f"   為 {len(point_ids)} 個知識點重建關聯...")
        
        total_links = 0
        for i, point_id in enumerate(point_ids):
            try:
                link_count = embedding.auto_link_knowledge_point(point_id, similarity_threshold=0.8)
                total_links += link_count
                
                if (i + 1) % 50 == 0:
                    print(f"      已處理 {i + 1}/{len(point_ids)} 個知識點")
                    
            except Exception as e:
                logger.error(f"為知識點 {point_id} 重建關聯失敗: {e}")
                continue
        
        print(f"   ✅ 重建完成，總共建立了 {total_links} 個關聯")
        
    except Exception as e:
        print(f"   ❌ 重建關聯失敗: {e}")

def test_model_loading():
    """測試模型載入"""
    print("\n🧪 測試 Sentence-BERT 模型載入...")
    
    try:
        model = embedding.get_embedding_model()
        print(f"   ✅ 模型載入成功: {embedding._model_name}")
        
        # 測試生成向量
        test_text = "測試文本: correct phrase test"
        test_embedding = embedding.generate_embedding(test_text)
        print(f"   ✅ 向量生成成功，維度: {test_embedding.shape}")
        
    except Exception as e:
        print(f"   ❌ 模型測試失敗: {e}")
        logger.exception("模型測試失敗")

if __name__ == "__main__":
    # 檢查環境變數
    if not os.environ.get('DATABASE_URL'):
        print("❌ 錯誤: 未設定 DATABASE_URL 環境變數")
        print("請設定資料庫連接字串，例如:")
        print("export DATABASE_URL='postgresql://username:password@localhost:5432/database'")
        sys.exit(1)
    
    # 選單
    print("請選擇操作:")
    print("1. 測試模型載入")
    print("2. 批次處理知識點向量")
    print("3. 重建所有關聯")
    print("4. 查看統計資訊")
    
    choice = input("\n請輸入選項 (1-4): ").strip()
    
    if choice == "1":
        test_model_loading()
    elif choice == "2":
        main()
    elif choice == "3":
        rebuild_all_links()
    elif choice == "4":
        try:
            stats = embedding.get_embedding_statistics()
            print(f"\n📊 統計資訊:")
            for key, value in stats.items():
                print(f"   {key}: {value}")
        except Exception as e:
            print(f"❌ 獲取統計失敗: {e}")
    else:
        print("無效選項")