# app/routes/data.py

from flask import Blueprint, request, jsonify
from app.services import database as db
import datetime
import json

data_bp = Blueprint('data_bp', __name__)

@data_bp.route("/get_dashboard", methods=['GET'])
def get_dashboard_endpoint():
    """
    【v5.16 重構版】: 獲取知識點儀表板數據。
    """
    print("\n[API] 收到請求：獲取知識點儀表板數據...")
    try:
        points_dict = db.get_all_knowledge_points() # 假設 db 有一個新函式
        return jsonify({"knowledge_points": points_dict})
    except Exception as e:
        print(f"[API] 獲取儀表板數據時發生嚴重錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/get_flashcards", methods=['GET'])
def get_flashcards_endpoint():
    """
    【v5.16 重構版】: 根據錯誤類型獲取單字卡數據。
    """
    print("\n[API] 收到請求：獲取單字卡數據...")
    types_str = request.args.get('types', '')
    if not types_str:
        return jsonify({"error": "請提供要查詢的錯誤類型(types)。"}), 400
        
    types_to_fetch = types_str.split(',')
    print(f"[API] 準備查詢以下類型的單字卡: {types_to_fetch}")
    
    try:
        flashcards = db.get_flashcards_by_types(types_to_fetch) # 假設 db 有一個新函式
        print(f"[API] 成功提取到 {len(flashcards)} 張不重複的單字卡。")
        return jsonify({"flashcards": flashcards})
    except Exception as e:
        print(f"[API] 獲取單字卡時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@data_bp.route("/get_calendar_heatmap", methods=['GET'])
def get_calendar_heatmap_endpoint():
    """
    【v5.16 重構版】: 提供特定月份的每日學習題數。
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
    【v5.16 重構版】: 提供特定日期的學習詳情。
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