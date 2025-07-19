# app/routes/embedding.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, jwt_required
from app.services import embedding_service as embedding
from app.services import database as db
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_current_user_id():
    """獲取當前用戶ID，支持訪客模式"""
    try:
        verify_jwt_in_request(optional=True)
        return get_jwt_identity()
    except:
        return None

embedding_bp = Blueprint('embedding_bp', __name__)

@embedding_bp.route("/embedding/statistics", methods=['GET'])
def get_embedding_statistics_endpoint():
    """獲取向量化功能的統計資訊"""
    try:
        stats = embedding.get_embedding_statistics()
        return jsonify({
            "status": "success",
            "statistics": stats
        })
    except Exception as e:
        logger.error(f"獲取向量統計資訊時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/batch_process", methods=['POST'])
@jwt_required()
def batch_process_embeddings_endpoint():
    """批次處理知識點向量生成（需要認證）"""
    try:
        request_data = request.get_json() or {}
        limit = request_data.get('limit', 100)  # 預設處理100個
        
        logger.info(f"開始批次處理向量，限制: {limit}")
        
        result = embedding.batch_process_knowledge_points(limit=limit)
        
        return jsonify({
            "status": "success",
            "message": f"批次處理完成",
            "result": result
        })
        
    except Exception as e:
        logger.error(f"批次處理向量時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/regenerate_point/<int:point_id>", methods=['POST'])
@jwt_required()
def regenerate_point_embedding_endpoint(point_id):
    """重新生成單一知識點的向量"""
    try:
        # 獲取知識點資料
        point_data = db.get_knowledge_point_by_id(point_id)
        if not point_data:
            return jsonify({"error": f"找不到知識點 {point_id}"}), 404
        
        # 生成並儲存向量
        success = embedding.generate_and_store_embedding_for_point(point_data)
        
        if success:
            # 重新建立關聯
            link_count = embedding.auto_link_knowledge_point(point_id)
            
            return jsonify({
                "status": "success",
                "message": f"知識點 {point_id} 向量重新生成成功",
                "links_created": link_count
            })
        else:
            return jsonify({"error": "向量生成失敗"}), 500
            
    except Exception as e:
        logger.error(f"重新生成知識點 {point_id} 向量時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/find_similar/<int:point_id>", methods=['GET'])
def find_similar_points_endpoint(point_id):
    """尋找與指定知識點相似的其他知識點"""
    try:
        threshold = float(request.args.get('threshold', 0.75))
        max_results = int(request.args.get('max_results', 10))
        
        similar_points = embedding.find_similar_knowledge_points(
            point_id, 
            similarity_threshold=threshold,
            max_results=max_results
        )
        
        return jsonify({
            "status": "success",
            "target_point_id": point_id,
            "similarity_threshold": threshold,
            "similar_points": similar_points
        })
        
    except Exception as e:
        logger.error(f"尋找相似知識點時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/knowledge_links/<int:point_id>", methods=['GET'])
def get_knowledge_links_endpoint(point_id):
    """獲取知識點的所有關聯"""
    try:
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            # 獲取出站關聯
            cursor.execute("""
                SELECT kl.target_point_id, kl.similarity_score, kl.link_type, kl.created_at,
                       kp.correct_phrase, kp.key_point_summary
                FROM knowledge_links kl
                JOIN knowledge_points kp ON kl.target_point_id = kp.id
                WHERE kl.source_point_id = %s AND kl.is_active = TRUE
                ORDER BY kl.similarity_score DESC
            """, (point_id,))
            outbound_links = cursor.fetchall()
            
            # 獲取入站關聯
            cursor.execute("""
                SELECT kl.source_point_id, kl.similarity_score, kl.link_type, kl.created_at,
                       kp.correct_phrase, kp.key_point_summary
                FROM knowledge_links kl
                JOIN knowledge_points kp ON kl.source_point_id = kp.id
                WHERE kl.target_point_id = %s AND kl.is_active = TRUE
                ORDER BY kl.similarity_score DESC
            """, (point_id,))
            inbound_links = cursor.fetchall()
        
        conn.close()
        
        # 格式化結果
        outbound_formatted = []
        for link in outbound_links:
            outbound_formatted.append({
                'linked_point_id': link[0],
                'similarity_score': float(link[1]),
                'link_type': link[2],
                'created_at': link[3].isoformat() if link[3] else None,
                'correct_phrase': link[4],
                'key_point_summary': link[5]
            })
        
        inbound_formatted = []
        for link in inbound_links:
            inbound_formatted.append({
                'linked_point_id': link[0],
                'similarity_score': float(link[1]),
                'link_type': link[2],
                'created_at': link[3].isoformat() if link[3] else None,
                'correct_phrase': link[4],
                'key_point_summary': link[5]
            })
        
        return jsonify({
            "status": "success",
            "point_id": point_id,
            "outbound_links": outbound_formatted,
            "inbound_links": inbound_formatted,
            "total_links": len(outbound_formatted) + len(inbound_formatted)
        })
        
    except Exception as e:
        logger.error(f"獲取知識點關聯時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/create_manual_link", methods=['POST'])
@jwt_required()
def create_manual_link_endpoint():
    """手動建立知識點關聯"""
    try:
        data = request.get_json()
        if not data or 'source_point_id' not in data or 'target_point_id' not in data:
            return jsonify({"error": "需要提供 source_point_id 和 target_point_id"}), 400
        
        source_id = data['source_point_id']
        target_id = data['target_point_id']
        similarity_score = data.get('similarity_score', 1.0)  # 手動關聯預設為1.0
        
        # 建立雙向關聯
        success1 = embedding.create_knowledge_link(
            source_id, target_id, similarity_score, 'manual_link'
        )
        success2 = embedding.create_knowledge_link(
            target_id, source_id, similarity_score, 'manual_link'
        )
        
        if success1 or success2:
            return jsonify({
                "status": "success",
                "message": f"手動關聯建立成功: {source_id} <-> {target_id}"
            })
        else:
            return jsonify({"error": "關聯建立失敗"}), 500
            
    except Exception as e:
        logger.error(f"建立手動關聯時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/remove_link", methods=['DELETE'])
@jwt_required()
def remove_knowledge_link_endpoint():
    """移除知識點關聯"""
    try:
        data = request.get_json()
        if not data or 'source_point_id' not in data or 'target_point_id' not in data:
            return jsonify({"error": "需要提供 source_point_id 和 target_point_id"}), 400
        
        source_id = data['source_point_id']
        target_id = data['target_point_id']
        
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            # 移除指定關聯
            cursor.execute("""
                UPDATE knowledge_links 
                SET is_active = FALSE 
                WHERE source_point_id = %s AND target_point_id = %s
            """, (source_id, target_id))
            
            # 也移除反向關聯
            cursor.execute("""
                UPDATE knowledge_links 
                SET is_active = FALSE 
                WHERE source_point_id = %s AND target_point_id = %s
            """, (target_id, source_id))
            
            conn.commit()
        
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": f"關聯已移除: {source_id} <-> {target_id}"
        })
        
    except Exception as e:
        logger.error(f"移除關聯時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/cleanup_links", methods=['POST'])
@jwt_required()
def cleanup_links_endpoint():
    """清理無效的知識點關聯"""
    try:
        deleted_count = embedding.cleanup_knowledge_links()
        
        return jsonify({
            "status": "success",
            "message": f"清理完成，移除了 {deleted_count} 個無效關聯"
        })
        
    except Exception as e:
        logger.error(f"清理關聯時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@embedding_bp.route("/embedding/search_by_text", methods=['POST'])
def search_knowledge_by_text_endpoint():
    """使用文本搜尋相似的知識點"""
    try:
        data = request.get_json()
        if not data or 'text' not in data:
            return jsonify({"error": "需要提供 text 參數"}), 400
        
        search_text = data['text']
        threshold = data.get('threshold', 0.7)
        max_results = data.get('max_results', 10)
        
        # 生成搜尋文本的向量
        search_embedding = embedding.generate_embedding(search_text)
        
        # 在資料庫中搜尋相似向量
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            search_vector_str = '[' + ','.join(map(str, search_embedding.tolist())) + ']'
            
            cursor.execute("""
                SELECT id, correct_phrase, key_point_summary, 
                       1 - (embedding_vector <=> %s::vector) AS similarity
                FROM knowledge_points 
                WHERE embedding_vector IS NOT NULL 
                  AND is_archived = FALSE
                  AND (1 - (embedding_vector <=> %s::vector)) >= %s
                ORDER BY embedding_vector <=> %s::vector
                LIMIT %s
            """, (search_vector_str, search_vector_str, threshold, search_vector_str, max_results))
            
            results = cursor.fetchall()
        
        conn.close()
        
        # 格式化結果
        formatted_results = []
        for result in results:
            formatted_results.append({
                'point_id': result[0],
                'correct_phrase': result[1],
                'key_point_summary': result[2],
                'similarity_score': float(result[3])
            })
        
        return jsonify({
            "status": "success",
            "search_text": search_text,
            "threshold": threshold,
            "results": formatted_results
        })
        
    except Exception as e:
        logger.error(f"文本搜尋時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500