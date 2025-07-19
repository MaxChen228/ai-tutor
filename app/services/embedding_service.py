# app/services/embedding_service.py

import os
import numpy as np
import psycopg2
from typing import List, Dict, Optional, Tuple
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from app.services.database import get_db_connection
import datetime
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全域變數儲存模型實例（延遲載入）
_embedding_model = None
_model_name = os.environ.get('EMBEDDING_MODEL', "paraphrase-multilingual-MiniLM-L12-v2")  # 384維，支援中英文混合
_vector_dimension = 384

# 生產環境最佳化設定
_device = 'cpu'  # Render 通常沒有 GPU，強制使用 CPU

def get_embedding_model():
    """獲取 Sentence-BERT 模型實例（單例模式）"""
    global _embedding_model
    if _embedding_model is None:
        logger.info(f"正在載入 Sentence-BERT 模型: {_model_name}")
        try:
            _embedding_model = SentenceTransformer(_model_name, device=_device)
            logger.info(f"✅ Sentence-BERT 模型載入成功 (設備: {_device})")
        except Exception as e:
            logger.error(f"❌ 模型載入失敗: {e}")
            raise
    return _embedding_model

def create_knowledge_text(knowledge_point: Dict) -> str:
    """
    將知識點資料組合成適合向量化的文本
    
    Args:
        knowledge_point: 知識點資料字典
        
    Returns:
        組合後的文本字串
    """
    components = []
    
    # 核心片語
    if knowledge_point.get('correct_phrase'):
        components.append(f"正確用法: {knowledge_point['correct_phrase']}")
    
    # 錯誤片語（如果有）
    if knowledge_point.get('incorrect_phrase_in_context'):
        components.append(f"錯誤用法: {knowledge_point['incorrect_phrase_in_context']}")
    
    # 核心觀念總結
    if knowledge_point.get('key_point_summary'):
        components.append(f"觀念: {knowledge_point['key_point_summary']}")
    
    # 詳細解釋
    if knowledge_point.get('explanation'):
        components.append(f"說明: {knowledge_point['explanation']}")
    
    # 分類資訊
    if knowledge_point.get('category'):
        components.append(f"分類: {knowledge_point['category']}")
    
    if knowledge_point.get('subcategory'):
        components.append(f"子分類: {knowledge_point['subcategory']}")
    
    # 語境句子
    if knowledge_point.get('user_context_sentence'):
        components.append(f"語境: {knowledge_point['user_context_sentence']}")
    
    return " | ".join(components)

def generate_embedding(text: str) -> np.ndarray:
    """
    生成單一文本的向量
    
    Args:
        text: 要向量化的文本
        
    Returns:
        384維的 numpy 向量
    """
    try:
        model = get_embedding_model()
        embedding = model.encode(text, convert_to_numpy=True)
        return embedding.astype(np.float32)
    except Exception as e:
        logger.error(f"生成向量時發生錯誤: {e}")
        raise

def batch_generate_embeddings(texts: List[str], batch_size: int = 32) -> List[np.ndarray]:
    """
    批次生成多個文本的向量
    
    Args:
        texts: 文本列表
        batch_size: 批次大小
        
    Returns:
        向量列表
    """
    if not texts:
        return []
    
    try:
        model = get_embedding_model()
        logger.info(f"開始批次生成 {len(texts)} 個向量，批次大小: {batch_size}")
        
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            logger.info(f"處理批次 {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
            
            batch_embeddings = model.encode(batch, convert_to_numpy=True, show_progress_bar=True)
            all_embeddings.extend([emb.astype(np.float32) for emb in batch_embeddings])
        
        logger.info("✅ 批次向量生成完成")
        return all_embeddings
        
    except Exception as e:
        logger.error(f"批次生成向量時發生錯誤: {e}")
        raise

def update_knowledge_point_embedding(point_id: int, embedding_vector: np.ndarray) -> bool:
    """
    更新知識點的向量到資料庫
    
    Args:
        point_id: 知識點ID
        embedding_vector: 384維向量
        
    Returns:
        更新是否成功
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 將 numpy 陣列轉換為 PostgreSQL vector 格式
            vector_str = '[' + ','.join(map(str, embedding_vector.tolist())) + ']'
            
            cursor.execute(
                """
                UPDATE knowledge_points 
                SET embedding_vector = %s::vector, embedding_updated_at = %s
                WHERE id = %s
                """,
                (vector_str, datetime.datetime.now(datetime.timezone.utc), point_id)
            )
            
            updated_rows = cursor.rowcount
            conn.commit()
        
        conn.close()
        return updated_rows > 0
        
    except Exception as e:
        logger.error(f"更新知識點 {point_id} 向量時發生錯誤: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

def generate_and_store_embedding_for_point(knowledge_point: Dict) -> bool:
    """
    為單一知識點生成並儲存向量
    
    Args:
        knowledge_point: 包含完整知識點資料的字典
        
    Returns:
        操作是否成功
    """
    try:
        # 建立文本
        text = create_knowledge_text(knowledge_point)
        logger.info(f"生成向量文本: {text[:100]}...")
        
        # 生成向量
        embedding = generate_embedding(text)
        
        # 儲存到資料庫
        point_id = knowledge_point.get('id')
        if point_id:
            success = update_knowledge_point_embedding(point_id, embedding)
            if success:
                logger.info(f"✅ 知識點 {point_id} 向量生成並儲存成功")
            return success
        else:
            logger.error("知識點缺少 ID，無法儲存向量")
            return False
            
    except Exception as e:
        logger.error(f"為知識點生成向量時發生錯誤: {e}")
        return False

def batch_process_knowledge_points(limit: Optional[int] = None) -> Dict[str, int]:
    """
    批次處理資料庫中沒有向量的知識點
    
    Args:
        limit: 處理數量限制（None = 全部處理）
        
    Returns:
        處理結果統計
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 查詢沒有向量的知識點
            query = """
                SELECT id, category, subcategory, correct_phrase, explanation,
                       user_context_sentence, incorrect_phrase_in_context, key_point_summary
                FROM knowledge_points 
                WHERE embedding_vector IS NULL AND is_archived = FALSE
                ORDER BY id
            """
            
            if limit:
                query += f" LIMIT {limit}"
            
            cursor.execute(query)
            knowledge_points = cursor.fetchall()
        
        conn.close()
        
        if not knowledge_points:
            logger.info("所有知識點都已有向量")
            return {"processed": 0, "success": 0, "failed": 0}
        
        logger.info(f"找到 {len(knowledge_points)} 個需要生成向量的知識點")
        
        # 準備批次處理
        texts = []
        point_data = []
        
        for point in knowledge_points:
            point_dict = {
                'id': point[0],
                'category': point[1],
                'subcategory': point[2],
                'correct_phrase': point[3],
                'explanation': point[4],
                'user_context_sentence': point[5],
                'incorrect_phrase_in_context': point[6],
                'key_point_summary': point[7]
            }
            
            text = create_knowledge_text(point_dict)
            texts.append(text)
            point_data.append(point_dict)
        
        # 批次生成向量
        embeddings = batch_generate_embeddings(texts)
        
        # 逐一儲存到資料庫
        success_count = 0
        failed_count = 0
        
        for i, (point, embedding) in enumerate(zip(point_data, embeddings)):
            try:
                if update_knowledge_point_embedding(point['id'], embedding):
                    success_count += 1
                else:
                    failed_count += 1
                    
                # 每處理100個顯示進度
                if (i + 1) % 100 == 0:
                    logger.info(f"已處理 {i + 1}/{len(point_data)} 個知識點")
                    
            except Exception as e:
                logger.error(f"儲存知識點 {point['id']} 向量失敗: {e}")
                failed_count += 1
        
        result = {
            "processed": len(knowledge_points),
            "success": success_count,
            "failed": failed_count
        }
        
        logger.info(f"✅ 批次處理完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"批次處理知識點時發生錯誤: {e}")
        return {"processed": 0, "success": 0, "failed": 0}

def find_similar_knowledge_points(
    target_point_id: int,
    similarity_threshold: float = 0.75,
    max_results: int = 10
) -> List[Dict]:
    """
    尋找與目標知識點相似的其他知識點
    
    Args:
        target_point_id: 目標知識點ID
        similarity_threshold: 相似度閾值（0-1）
        max_results: 最大結果數量
        
    Returns:
        相似知識點列表，包含相似度分數
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 獲取目標知識點的向量
            cursor.execute(
                "SELECT embedding_vector FROM knowledge_points WHERE id = %s AND embedding_vector IS NOT NULL",
                (target_point_id,)
            )
            target_result = cursor.fetchone()
            
            if not target_result:
                logger.warning(f"知識點 {target_point_id} 沒有向量或不存在")
                return []
            
            target_vector = target_result[0]
            
            # 使用資料庫函數查詢相似知識點
            cursor.execute(
                """
                SELECT * FROM find_similar_knowledge_points(%s::vector, %s, %s, %s)
                """,
                (str(target_vector), similarity_threshold, max_results, target_point_id)
            )
            
            similar_points = cursor.fetchall()
        
        conn.close()
        
        # 格式化結果
        results = []
        for point in similar_points:
            results.append({
                'point_id': point[0],
                'similarity_score': float(point[1]),
                'correct_phrase': point[2],
                'key_point_summary': point[3]
            })
        
        logger.info(f"找到 {len(results)} 個相似知識點（閾值: {similarity_threshold}）")
        return results
        
    except Exception as e:
        logger.error(f"搜尋相似知識點時發生錯誤: {e}")
        return []

def create_knowledge_link(
    source_point_id: int,
    target_point_id: int,
    similarity_score: float,
    link_type: str = 'semantic_similarity'
) -> bool:
    """
    建立知識點間的關聯
    
    Args:
        source_point_id: 來源知識點ID
        target_point_id: 目標知識點ID
        similarity_score: 相似度分數
        link_type: 關聯類型
        
    Returns:
        建立是否成功
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 檢查關聯是否已存在
            cursor.execute(
                "SELECT id FROM knowledge_links WHERE source_point_id = %s AND target_point_id = %s",
                (source_point_id, target_point_id)
            )
            
            if cursor.fetchone():
                logger.info(f"關聯已存在: {source_point_id} -> {target_point_id}")
                conn.close()
                return True
            
            # 建立新關聯
            cursor.execute(
                """
                INSERT INTO knowledge_links (source_point_id, target_point_id, similarity_score, link_type)
                VALUES (%s, %s, %s, %s)
                """,
                (source_point_id, target_point_id, similarity_score, link_type)
            )
            
            conn.commit()
        
        conn.close()
        logger.info(f"✅ 建立關聯: {source_point_id} -> {target_point_id} (相似度: {similarity_score:.3f})")
        return True
        
    except Exception as e:
        logger.error(f"建立知識點關聯時發生錯誤: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()
        return False

def auto_link_knowledge_point(point_id: int, similarity_threshold: float = 0.8) -> int:
    """
    自動為知識點建立關聯
    
    Args:
        point_id: 知識點ID
        similarity_threshold: 相似度閾值
        
    Returns:
        建立的關聯數量
    """
    try:
        # 尋找相似知識點
        similar_points = find_similar_knowledge_points(
            point_id, 
            similarity_threshold=similarity_threshold,
            max_results=5  # 限制關聯數量避免過多連結
        )
        
        created_links = 0
        
        for similar_point in similar_points:
            # 建立雙向關聯
            if create_knowledge_link(
                point_id, 
                similar_point['point_id'], 
                similar_point['similarity_score']
            ):
                created_links += 1
            
            if create_knowledge_link(
                similar_point['point_id'], 
                point_id, 
                similar_point['similarity_score']
            ):
                created_links += 1
        
        logger.info(f"為知識點 {point_id} 建立了 {created_links} 個關聯")
        return created_links
        
    except Exception as e:
        logger.error(f"自動建立知識點關聯時發生錯誤: {e}")
        return 0

def get_embedding_statistics() -> Dict:
    """
    獲取向量化功能的統計資訊
    
    Returns:
        統計資訊字典
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT * FROM knowledge_linking_stats")
            stats = cursor.fetchone()
        
        conn.close()
        
        if stats:
            return {
                'points_with_vectors': stats[0],
                'points_without_vectors': stats[1],
                'active_links': stats[2],
                'avg_similarity_score': float(stats[3]) if stats[3] else 0.0,
                'last_embedding_update': stats[4].isoformat() if stats[4] else None
            }
        else:
            return {}
            
    except Exception as e:
        logger.error(f"獲取統計資訊時發生錯誤: {e}")
        return {}

def cleanup_knowledge_links() -> int:
    """
    清理無效的知識點關聯
    
    Returns:
        清理的關聯數量
    """
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT cleanup_invalid_links()")
            deleted_count = cursor.fetchone()[0]
            conn.commit()
        
        conn.close()
        logger.info(f"清理了 {deleted_count} 個無效關聯")
        return deleted_count
        
    except Exception as e:
        logger.error(f"清理知識點關聯時發生錯誤: {e}")
        return 0