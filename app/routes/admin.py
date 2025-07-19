# app/routes/admin.py

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.services import embedding_service as embedding
from app.services import database as db
import logging

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/admin')
@jwt_required()
def admin_dashboard():
    """管理員主儀表板"""
    try:
        # 獲取統計資訊
        stats = embedding.get_embedding_statistics()
        
        return render_template('admin/dashboard.html', 
                             stats=stats,
                             page_title="知識點網絡管理")
    except Exception as e:
        logger.error(f"載入管理儀表板時發生錯誤: {e}")
        return render_template('admin/error.html', error=str(e)), 500

@admin_bp.route('/admin/knowledge-points')
@jwt_required()
def knowledge_points_list():
    """知識點列表管理"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        has_vector = request.args.get('has_vector', 'all')
        
        # 構建查詢條件
        where_clause = "WHERE is_archived = FALSE"
        if has_vector == 'yes':
            where_clause += " AND embedding_vector IS NOT NULL"
        elif has_vector == 'no':
            where_clause += " AND embedding_vector IS NULL"
        
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            # 獲取總數
            cursor.execute(f"SELECT COUNT(*) FROM knowledge_points {where_clause}")
            total = cursor.fetchone()[0]
            
            # 獲取分頁資料
            offset = (page - 1) * per_page
            cursor.execute(f"""
                SELECT id, correct_phrase, key_point_summary, category, subcategory,
                       embedding_vector IS NOT NULL as has_vector,
                       embedding_updated_at, created_at
                FROM knowledge_points {where_clause}
                ORDER BY id DESC
                LIMIT %s OFFSET %s
            """, (per_page, offset))
            
            knowledge_points = cursor.fetchall()
        
        conn.close()
        
        # 格式化資料
        formatted_points = []
        for point in knowledge_points:
            formatted_points.append({
                'id': point[0],
                'correct_phrase': point[1],
                'key_point_summary': point[2],
                'category': point[3],
                'subcategory': point[4],
                'has_vector': point[5],
                'embedding_updated_at': point[6].isoformat() if point[6] else None,
                'created_at': point[7].isoformat() if point[7] else None
            })
        
        # 計算分頁資訊
        total_pages = (total + per_page - 1) // per_page
        
        return render_template('admin/knowledge_points.html',
                             knowledge_points=formatted_points,
                             page=page,
                             per_page=per_page,
                             total=total,
                             total_pages=total_pages,
                             has_vector=has_vector,
                             page_title="知識點管理")
                             
    except Exception as e:
        logger.error(f"載入知識點列表時發生錯誤: {e}")
        return render_template('admin/error.html', error=str(e)), 500

@admin_bp.route('/admin/batch-processing')
@jwt_required() 
def batch_processing():
    """批次處理管理界面"""
    try:
        # 獲取待處理的知識點數量
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT COUNT(*) FROM knowledge_points 
                WHERE embedding_vector IS NULL AND is_archived = FALSE
            """)
            pending_count = cursor.fetchone()[0]
        
        conn.close()
        
        return render_template('admin/batch_processing.html',
                             pending_count=pending_count,
                             page_title="批次處理")
                             
    except Exception as e:
        logger.error(f"載入批次處理頁面時發生錯誤: {e}")
        return render_template('admin/error.html', error=str(e)), 500

@admin_bp.route('/admin/network-visualization')
@jwt_required()
def network_visualization():
    """網絡視覺化界面"""
    try:
        # 獲取基本統計
        stats = embedding.get_embedding_statistics()
        
        return render_template('admin/network_visualization.html',
                             stats=stats,
                             page_title="知識點網絡視覺化")
                             
    except Exception as e:
        logger.error(f"載入網絡視覺化頁面時發生錯誤: {e}")
        return render_template('admin/error.html', error=str(e)), 500

@admin_bp.route('/admin/api/batch-process', methods=['POST'])
@jwt_required()
def api_batch_process():
    """啟動批次處理API"""
    try:
        data = request.get_json() or {}
        limit = data.get('limit', 100)
        
        result = embedding.batch_process_knowledge_points(limit=limit)
        
        return jsonify({
            "status": "success",
            "result": result
        })
        
    except Exception as e:
        logger.error(f"批次處理API錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@admin_bp.route('/admin/api/regenerate-point/<int:point_id>', methods=['POST'])
@jwt_required()
def api_regenerate_point(point_id):
    """重新生成單一知識點向量API"""
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

@admin_bp.route('/admin/api/network-data')
@jwt_required()
def api_network_data():
    """獲取網絡視覺化資料API"""
    try:
        limit = request.args.get('limit', 50, type=int)
        min_similarity = request.args.get('min_similarity', 0.8, type=float)
        
        conn = db.get_db_connection()
        with conn.cursor() as cursor:
            # 獲取節點資料
            cursor.execute("""
                SELECT id, correct_phrase, key_point_summary, category, subcategory
                FROM knowledge_points 
                WHERE embedding_vector IS NOT NULL AND is_archived = FALSE
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))
            
            nodes_data = cursor.fetchall()
            
            # 獲取關聯資料
            if nodes_data:
                node_ids = [str(node[0]) for node in nodes_data]
                placeholders = ','.join(['%s'] * len(node_ids))
                
                cursor.execute(f"""
                    SELECT kl.source_point_id, kl.target_point_id, kl.similarity_score
                    FROM knowledge_links kl
                    WHERE kl.source_point_id IN ({placeholders})
                        AND kl.target_point_id IN ({placeholders})
                        AND kl.similarity_score >= %s
                        AND kl.is_active = TRUE
                    ORDER BY kl.similarity_score DESC
                """, node_ids + node_ids + [min_similarity])
                
                links_data = cursor.fetchall()
            else:
                links_data = []
        
        conn.close()
        
        # 格式化節點資料
        nodes = []
        for node in nodes_data:
            nodes.append({
                'id': node[0],
                'label': node[1] or f"Point {node[0]}",
                'title': node[2] or "無摘要",
                'group': node[3] or "未分類",
                'subcategory': node[4] or "未分類"
            })
        
        # 格式化連結資料
        links = []
        for link in links_data:
            links.append({
                'source': link[0],
                'target': link[1],
                'weight': float(link[2])
            })
        
        return jsonify({
            "nodes": nodes,
            "links": links,
            "stats": {
                "node_count": len(nodes),
                "link_count": len(links),
                "min_similarity": min_similarity
            }
        })
        
    except Exception as e:
        logger.error(f"獲取網絡資料時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500