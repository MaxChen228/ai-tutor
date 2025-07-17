# app/routes/data.py

from flask import Blueprint, request, jsonify
from app.services import database as db
import datetime
import json

data_bp = Blueprint('data_bp', __name__)

# --- v5.16 儀表板、閃卡、日曆相關路由 ---

@data_bp.route("/get_dashboard", methods=['GET'])
def get_dashboard_endpoint():
    """
    獲取知識點儀表板數據 (未封存的)。
    """
    print("\n[API] 收到請求：獲取知識點儀表板數據...")
    try:
        points_dict = db.get_all_knowledge_points()
        return jsonify({"knowledge_points": points_dict})
    except Exception as e:
        print(f"[API] 獲取儀表板數據時發生嚴重錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/get_flashcards", methods=['GET'])
def get_flashcards_endpoint():
    """
    根據錯誤類型獲取單字卡數據。
    """
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
    """
    提供特定月份的每日學習題數。
    """
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
    """
    提供特定日期的學習詳情。
    """
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

# --- 【v5.17 新增】管理知識點的 API ---

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
    """
    批次處理多個知識點。
    預期請求 Body: { "action": "archive" | "unarchive", "ids": [1, 2, 3] }
    """
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


# --- 新增的 API 端點 ---
@data_bp.route("/knowledge_points/finalize", methods=['POST'])
def finalize_knowledge_points_endpoint():
    """
    接收前端整理好（排序、刪除、合併後）的錯誤分析陣列，
    並將它們作為正式的知識點存入資料庫。
    """
    # 這裡的 user_id 應該從您的認證機制中獲取，例如 g.user_id
    # 為了範例的完整性，我們暫時 hardcode
    # user_id = g.user_id 
    
    final_errors = request.get_json()

    if not isinstance(final_errors, list):
        return jsonify({"error": "無效的資料格式，應為一個錯誤列表。"}), 400

    try:
        question_data = final_errors[0].get('question_context', {}) # 假設前端會把原始問題上下文一起傳來
        user_answer = final_errors[0].get('user_answer_context', '')
        
        # 遍歷前端傳來的列表
        for error_data in final_errors:
            # 為了復用 db.add_mistake，我們需要構造一個類似原始 feedback 的結構
            # 這裡的實作取決於您 db.add_mistake 的具體參數
            # 假設它需要一個完整的 feedback dict
            mock_feedback_data = {
                "is_generally_correct": False,
                "error_analysis": [error_data] # 將單個錯誤放入分析列表
            }
            # 呼叫資料庫服務，將每個錯誤（現在是確認過的知識點）加入資料庫
            db.add_mistake(question_data, user_answer, mock_feedback_data)
        
        return jsonify({
            "status": "success",
            "message": f"已成功儲存 {len(final_errors)} 個知識點。"
        }), 201 # 201 Created

    except Exception as e:
        print(f"Error in finalize_knowledge_points_endpoint: {e}")
        return jsonify({"error": "儲存知識點時發生內部錯誤。"}), 500