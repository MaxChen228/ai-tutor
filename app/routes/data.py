# app/routes/data.py

from flask import Blueprint, request, jsonify
from app.services import database as db
from app.services import ai_service as ai
import datetime
import json

data_bp = Blueprint('data_bp', __name__)

# --- v5.16 儀表板、閃卡、日曆相關路由 ---

@data_bp.route("/get_dashboard", methods=['GET'])
def get_dashboard_endpoint():
    """獲取知識點儀表板數據 (未封存的)。"""
    print("\n[API] 收到請求：獲取知識點儀表板數據...")
    try:
        points_dict = db.get_all_knowledge_points()
        return jsonify({"knowledge_points": points_dict})
    except Exception as e:
        print(f"[API] 獲取儀表板數據時發生嚴重錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/get_flashcards", methods=['GET'])
def get_flashcards_endpoint():
    """根據錯誤類型獲取單字卡數據。"""
    print("\n[API] 收到請求：獲取單字卡數據...")
    types_str = request.args.get('types', '')
    if not types_str:
        return jsonify({"error": "請提供要查詢的錯誤類型(types)。"}), 400
        
    types_to_fetch = types_str.split(',')
    print(f"[API] 準備查詢以下類型的單字卡: {types_to_fetch}")
    
    try:
        flashcards = db.get_flashcards_by_types(types_to_fetch)
        print(f"[API] 成功提取到 {len(flashcards)} 張不重複的單字卡。")
        return jsonify({"flashcards": flashcards})
    except Exception as e:
        print(f"[API] 獲取單字卡時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/get_calendar_heatmap", methods=['GET'])
def get_calendar_heatmap_endpoint():
    """提供特定月份的每日學習題數。"""
    print("\n[API] 收到請求：獲取學習日曆熱力圖數據...")
    try:
        current_time = datetime.datetime.now(datetime.timezone.utc)
        year = int(request.args.get('year', current_time.year))
        month = int(request.args.get('month', current_time.month))
    except ValueError:
        current_time = datetime.datetime.now(datetime.timezone.utc)
        year = current_time.year
        month = current_time.month
    
    print(f"[API] 正在查詢 {year} 年 {month} 月的數據...")
    
    try:
        heatmap_data = db.get_daily_activity(year, month)
        return jsonify({"heatmap_data": heatmap_data})
    except Exception as e:
        print(f"[API] 查詢熱力圖數據時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/get_daily_details", methods=['GET'])
def get_daily_details_endpoint():
    """提供特定日期的學習詳情。"""
    print("\n[API] 收到請求：獲取單日學習詳情...")
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "請提供日期參數 (date=YYYY-MM-DD)。"}), 400
    
    print(f"[API] 正在查詢日期 {date_str} 的詳情...")
    
    try:
        daily_details = db.get_daily_details(date_str)
        return jsonify(daily_details)
    except Exception as e:
        print(f"[API] 查詢單日詳情時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

# --- 管理知識點的 API ---

@data_bp.route("/knowledge_point/<int:point_id>", methods=['GET'])
def get_knowledge_point_endpoint(point_id):
    """獲取單一知識點的詳細資訊。"""
    print(f"[API] 收到請求：獲取知識點 ID {point_id} 的詳細資訊")
    
    try:
        point_data = db.get_knowledge_point_by_id(point_id)
        if point_data:
            return jsonify(point_data)
        else:
            return jsonify({"error": f"找不到知識點 ID {point_id}"}), 404
    except Exception as e:
        print(f"[API] 獲取知識點詳情時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/knowledge_point/<int:point_id>", methods=['PUT'])
def update_knowledge_point_endpoint(point_id):
    """更新一個知識點的詳細資訊。"""
    data = request.get_json()
    if not data:
        return jsonify({"error": "請求中需要包含 JSON 格式的更新資料。"}), 400
    
    print(f"[API] 收到請求：更新知識點 ID {point_id}，資料: {data}")
    success, message = db.update_knowledge_point_details(point_id, data)
    
    if success:
        return jsonify({"message": message})
    else:
        return jsonify({"error": message}), 400

@data_bp.route("/knowledge_point/<int:point_id>/ai_review", methods=['POST'])
def ai_review_knowledge_point_endpoint(point_id):
    """
    使用 AI 重新審閱知識點並提供改進建議。
    """
    print(f"[API] 收到請求：AI 重新審閱知識點 ID {point_id}")
    
    try:
        # 先獲取知識點資料
        point_data = db.get_knowledge_point_by_id(point_id)
        if not point_data:
            return jsonify({"error": f"找不到知識點 ID {point_id}"}), 404
        
        # 從請求中獲取使用的模型（可選）
        request_data = request.get_json() or {}
        model_name = request_data.get('model_name')
        
        # 呼叫 AI 服務進行審閱
        review_result = ai.ai_review_knowledge_point(point_data, model_name)
        
        # 將審閱結果格式化為字串並儲存到資料庫
        review_notes = json.dumps(review_result, ensure_ascii=False, indent=2)
        success = db.update_knowledge_point_ai_review(point_id, review_notes)
        
        if success:
            return jsonify({
                "message": "AI 審閱完成並已儲存",
                "review_result": review_result
            })
        else:
            return jsonify({"error": "審閱結果儲存失敗"}), 500
            
    except Exception as e:
        print(f"[API] AI 審閱知識點時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/knowledge_point/<int:point_id>/archive", methods=['POST'])
def archive_knowledge_point_endpoint(point_id):
    """封存一個知識點。"""
    print(f"[API] 收到請求：封存知識點 ID {point_id}")
    success = db.set_knowledge_point_archived_status(point_id, True)
    if success:
        return jsonify({"message": f"知識點 {point_id} 已成功封存。"})
    else:
        return jsonify({"error": f"找不到或無法封存知識點 {point_id}。"}), 404

@data_bp.route("/knowledge_point/<int:point_id>/unarchive", methods=['POST'])
def unarchive_knowledge_point_endpoint(point_id):
    """取消封存一個知識點。"""
    print(f"[API] 收到請求：取消封存知識點 ID {point_id}")
    success = db.set_knowledge_point_archived_status(point_id, False)
    if success:
        return jsonify({"message": f"知識點 {point_id} 已成功取消封存。"})
    else:
        return jsonify({"error": f"找不到或無法取消封存知識點 {point_id}。"}), 404

@data_bp.route("/knowledge_point/<int:point_id>", methods=['DELETE'])
def delete_knowledge_point_endpoint(point_id):
    """刪除一個知識點。"""
    print(f"[API] 收到請求：刪除知識點 ID {point_id}")
    success = db.delete_knowledge_point(point_id)
    if success:
        return jsonify({"message": f"知識點 {point_id} 已被永久刪除。"})
    else:
        return jsonify({"error": f"找不到或無法刪除知識點 {point_id}。"}), 404

@data_bp.route("/archived_knowledge_points", methods=['GET'])
def get_archived_knowledge_points_endpoint():
    """獲取所有已封存的知識點列表。"""
    print(f"[API] 收到請求：獲取已封存的知識點列表。")
    try:
        archived_points = db.get_archived_knowledge_points()
        return jsonify({"knowledge_points": archived_points})
    except Exception as e:
        print(f"[API] 獲取已封存知識點時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/knowledge_points/batch_action", methods=['POST'])
def batch_action_knowledge_points_endpoint():
    """批次處理多個知識點。"""
    data = request.get_json()
    if not data or "action" not in data or "ids" not in data:
        return jsonify({"error": "請求格式錯誤，需要 'action' 和 'ids' 欄位。"}), 400

    action = data["action"]
    point_ids = data["ids"]

    if not isinstance(point_ids, list) or not point_ids:
        return jsonify({"error": "'ids' 必須是一個非空的 ID 列表。"}), 400

    print(f"[API] 收到批次請求: 動作='{action}', IDs={point_ids}")

    updated_count = 0
    if action == "archive":
        updated_count = db.batch_update_knowledge_points_archived_status(point_ids, True)
    elif action == "unarchive":
        updated_count = db.batch_update_knowledge_points_archived_status(point_ids, False)
    else:
        return jsonify({"error": f"不支援的動作: {action}"}), 400

    return jsonify({
        "message": f"動作 '{action}' 執行完畢。",
        "updated_count": updated_count
    })

# --- 合併錯誤的 API 端點 ---
@data_bp.route("/merge_errors", methods=['POST'])
def merge_errors_endpoint():
    """使用 AI 將兩個錯誤分析合併成一個。"""
    data = request.get_json()
    if not data or "error1" not in data or "error2" not in data:
        return jsonify({"error": "請求格式錯誤，需要 'error1' 和 'error2' 欄位。"}), 400
    
    error1 = data["error1"]
    error2 = data["error2"]
    
    print(f"[API] 收到請求：合併兩個錯誤分析")
    print(f"  - 錯誤1: {error1.get('key_point_summary', 'N/A')}")
    print(f"  - 錯誤2: {error2.get('key_point_summary', 'N/A')}")
    
    try:
        merged_error = ai.merge_error_analyses(error1, error2)
        return jsonify({"merged_error": merged_error})
    except Exception as e:
        print(f"[API] 合併錯誤時發生問題: {e}")
        return jsonify({"error": str(e)}), 500

# --- 儲存最終知識點的 API 端點 ---
@data_bp.route("/knowledge_points/finalize", methods=['POST'])
def finalize_knowledge_points_endpoint():
    """接收前端整理好的錯誤分析陣列，並將它們作為正式的知識點存入資料庫。"""
    data = request.get_json()
    
    if not isinstance(data, dict):
        return jsonify({"error": "無效的資料格式。"}), 400
    
    final_errors = data.get('errors', [])
    question_data = data.get('question_data', {})
    user_answer = data.get('user_answer', '')
    
    if not isinstance(final_errors, list):
        return jsonify({"error": "錯誤列表格式不正確。"}), 400

    try:
        print(f"[API] 收到請求：儲存 {len(final_errors)} 個最終確認的知識點")
        
        for error_data in final_errors:
            mock_feedback_data = {
                "is_generally_correct": False,
                "error_analysis": [error_data]
            }
            
            db.add_mistake(question_data, user_answer, mock_feedback_data)
            print(f"  - 已儲存知識點: {error_data.get('key_point_summary', 'N/A')}")
        
        return jsonify({
            "status": "success",
            "message": f"已成功儲存 {len(final_errors)} 個知識點。"
        }), 201

    except Exception as e:
        print(f"Error in finalize_knowledge_points_endpoint: {e}")
        return jsonify({"error": "儲存知識點時發生內部錯誤。"}), 500