# app.py - 您的 AI 家教後端 API 伺服器
import os
import json
from flask import Flask, request, jsonify
import datetime
import main as tutor  # 我們將 main.py 引用並取名為 tutor，方便呼叫
import psycopg2 # 引入 PostgreSQL 驅動
import psycopg2.extras # 引入用於字典 cursor 的額外功能

# --- 初始化 Flask 應用 ---
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False # 讓回傳的 JSON 可以正確顯示中文

# --- 應用程式啟動時，初始化資料庫 ---
# 確保 DATABASE_URL 已設定，否則 init_db() 會中斷程式
if tutor.DATABASE_URL:
    print("正在初始化資料庫...")
    tutor.init_db()
    print("資料庫準備就緒。")
else:
    print("錯誤：未設定 DATABASE_URL 環境變數，伺服器無法啟動。")
    # 在實際部署中，如果沒有資料庫URL，伺服器應該無法啟動
    # 這裡只印出錯誤，但 gunicorn 可能仍會嘗試運行
    # 最好的做法是在 Render 的啟動命令中檢查環境變數

# --- API 端點 0: 根目錄歡迎頁面 (可選) ---
@app.route("/", methods=['GET'])
def index():
    """
    提供一個簡單的歡迎訊息，避免直接訪問根目錄時出現 404 錯誤。
    """
    return "<h1>AI Tutor API (v5.4 PostgreSQL) is running!</h1><p>請使用 /start_session, /submit_answer, /get_dashboard, /get_flashcards 端點。</p>"

# 位於 app.py

# --- API 端點 1: 開始一輪新的學習 ---
@app.route("/start_session", methods=['GET'])
def start_session_endpoint():
    """
    【v5.9 Token 優化版】: 接收難度與長度參數，並傳遞給新的生成函式。
    """
    print("\n[API] 收到請求：開始新的一輪學習...")
    
    try:
        # 從 App 請求中獲取所有參數
        desired_review_count = int(request.args.get('num_review', '3'))
        desired_new_count = int(request.args.get('num_new', '2'))
        difficulty = int(request.args.get('difficulty', '3'))
        length = request.args.get('length', 'medium')
    except ValueError:
        # 如果參數格式錯誤，使用安全的預設值
        desired_review_count, desired_new_count, difficulty, length = 3, 2, 3, 'medium'

    print(f"[API] App 請求參數: 複習={desired_review_count}, 全新={desired_new_count}, 難度={difficulty}, 長度={length}")
    
    questions_to_ask = []

    # 1. 產生複習題 (邏輯維持不變)
    if desired_review_count > 0:
        due_knowledge_points = tutor.get_due_knowledge_points(desired_review_count)
        actual_num_review = len(due_knowledge_points)
        print(f"[API] 從資料庫中找到 {actual_num_review} 題到期的複習題。")
        
        if actual_num_review > 0:
            weak_points_for_prompt = [
                f"- 錯誤分類: {p['category']} -> {p['subcategory']}\n  正確用法: \"{p['correct_phrase']}\"\n  核心觀念: {p['explanation']}"
                for p in due_knowledge_points
            ]
            weak_points_str = "\n\n".join(weak_points_for_prompt)
            review_questions = tutor.generate_question_batch(weak_points_str, actual_num_review)
            if review_questions:
                for q, point in zip(review_questions, due_knowledge_points):
                    if isinstance(q, dict):
                        q['type'] = 'review'
                        q['knowledge_point_id'] = point['id']
                        q['mastery_level'] = point['mastery_level']
                questions_to_ask.extend(review_questions)

    # 2. 產生新題目
    if desired_new_count > 0:
        print(f"[API] 準備生成 {desired_new_count} 個全新挑戰...")
        # 【核心修改】: 呼叫新版函式，並傳入新的參數
        new_questions = tutor.generate_new_question_batch(desired_new_count, difficulty, length)
        if new_questions:
            for q in new_questions:
                 if isinstance(q, dict):
                    q['type'] = 'new'
            questions_to_ask.extend(new_questions)
    
    # 處理無題目可學的狀況
    if not questions_to_ask:
        print("[API] 本次請求無題目生成。")
        return jsonify({"questions": []})
        
    tutor.random.shuffle(questions_to_ask)
    print(f"[API] 已成功生成 {len(questions_to_ask)} 題，準備回傳給 App。")
    return jsonify({"questions": questions_to_ask})

# --- API 端點 2: 提交答案並獲取批改回饋 ---
@app.route("/submit_answer", methods=['POST'])
def submit_answer_endpoint():
    """
    【v5.10 改造】: 實現「目標導向」的複習與錯誤記錄流程。
    """
    print("\n[API] 收到請求：批改使用者答案...")
    data = request.get_json()
    if not data:
        return jsonify({"error": "請求格式錯誤，需要 JSON 資料。"}), 400

    question_data = data.get('question_data')
    user_answer = data.get('user_answer')

    if not question_data or user_answer is None:
        return jsonify({"error": "請求資料不完整，需要 'question_data' 和 'user_answer'。"}), 400

    sentence = question_data.get('new_sentence', '（題目獲取失敗）')

    feedback_data = {}
    review_concept_to_check = None

    # 判斷是否為複習題，並預先從資料庫取出要檢查的核心觀念
    if question_data.get('type') == 'review':
        conn = tutor.get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # 確保傳入的 ID 是整數
            try:
                point_id_to_check = int(question_data.get('knowledge_point_id'))
                cursor.execute("SELECT correct_phrase FROM knowledge_points WHERE id = %s", (point_id_to_check,))
                result = cursor.fetchone()
                if result:
                    review_concept_to_check = result['correct_phrase']
            except (TypeError, ValueError):
                print(f"[API] 警告：收到的 knowledge_point_id 無效。")
                pass # 如果 ID 無效，則當作新題目處理
        conn.close()

    # 呼叫改造後的批改函式，如果 review_concept_to_check 有值，就會啟用「目標導向批改」
    feedback_data = tutor.get_tutor_feedback(sentence, user_answer, review_context=review_concept_to_check)

    # 全新的「雙重檢查」判斷流程
    # 1. 首先，專門處理「核心複習觀念」是否掌握
    if review_concept_to_check and feedback_data.get('did_master_review_concept'):
        print(f"[API] 核心觀念 '{review_concept_to_check}' 複習成功！")
        point_id = question_data.get('knowledge_point_id')
        mastery = question_data.get('mastery_level')
        if point_id is not None and mastery is not None:
            # 即使句子有其他錯誤，只要核心觀念對了，就給予獎勵
            tutor.update_knowledge_point_mastery(point_id, mastery)
    
    # 2. 然後，獨立地處理句子中「其他」的錯誤
    # 我們將已處理過的複習觀念傳入，避免重複懲罰
    tutor.add_mistake(question_data, user_answer, feedback_data, exclude_phrase=review_concept_to_check)
    
    return jsonify(feedback_data)


# --- API 端點 3: 獲取知識點儀表板數據 ---
@app.route("/get_dashboard", methods=['GET'])
def get_dashboard_endpoint():
    """
    【v5.14 改造】: 在回傳給 App 的資料中，加入 next_review_date。
    """
    print("\n[API] 收到請求：獲取知識點儀表板數據...")
    conn = None
    try:
        conn = tutor.get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            # 【核心修改處】: 在 SELECT 語句中加入 next_review_date
            cursor.execute("""
                SELECT 
                    category, 
                    subcategory, 
                    correct_phrase, 
                    explanation, 
                    user_context_sentence, 
                    incorrect_phrase_in_context, 
                    key_point_summary,
                    mastery_level, 
                    mistake_count, 
                    correct_count,
                    next_review_date 
                FROM knowledge_points 
                ORDER BY mastery_level ASC, mistake_count DESC
            """)
            points_raw = cursor.fetchall()
        
        # psycopg2 會自動處理 Date 物件，但為了確保 JSON 相容性，我們手動轉為字串
        points_dict = []
        for row in points_raw:
            row_dict = dict(row)
            if row_dict.get('next_review_date'):
                row_dict['next_review_date'] = row_dict['next_review_date'].isoformat()
            points_dict.append(row_dict)
            
        return jsonify({"knowledge_points": points_dict})
    except Exception as e:
        print(f"[API] 獲取儀表板數據時發生嚴重錯誤: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()


# --- API 端點 4: 根據錯誤類型獲取單字卡數據 ---
@app.route("/get_flashcards", methods=['GET'])
def get_flashcards_endpoint():
    """
    【v5.4 PostgreSQL 版】: 使用新的連線函式。
    """
    print("\n[API] 收到請求：獲取單字卡數據...")
    types_str = request.args.get('types', '')
    if not types_str:
        return jsonify({"error": "請提供要查詢的錯誤類型(types)。"}), 400
        
    types_to_fetch = types_str.split(',')
    print(f"[API] 準備查詢以下類型的單字卡: {types_to_fetch}")
    
    flashcards = []
    unique_checker = set()
    conn = None
    try:
        conn = tutor.get_db_connection()
        with conn.cursor() as cursor:
            # 查詢 is_correct=false 的事件
            cursor.execute("SELECT ai_feedback_json FROM learning_events WHERE is_correct = false")
            all_events = cursor.fetchall()
        
        for event in all_events:
            if not event[0]: continue
            
            feedback_data = json.loads(event[0])
            error_analysis = feedback_data.get('error_analysis', [])
            
            for error in error_analysis:
                error_type = error.get('error_type')
                if error_type and error_type in types_to_fetch:
                    card_front = error.get('original_phrase', 'N/A')
                    card_back_correction = error.get('correction', 'N/A')
                    
                    card_identifier = (card_front, card_back_correction)
                    if card_identifier in unique_checker:
                        continue
                    
                    unique_checker.add(card_identifier)

                    card = {
                        "front": card_front,
                        "back_correction": card_back_correction,
                        "back_explanation": error.get('explanation', 'N/A'),
                        "category": error_type
                    }
                    flashcards.append(card)

        print(f"[API] 成功提取到 {len(flashcards)} 張不重複的單字卡。")
        return jsonify({"flashcards": flashcards})

    except Exception as e:
        print(f"[API] 獲取單字卡時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

# --- API 端點 5: 獲取學習日曆熱力圖數據 (新功能) ---
@app.route("/get_calendar_heatmap", methods=['GET'])
def get_calendar_heatmap_endpoint():
    """
    【v5.11 新增】: 提供特定月份的每日學習題數，用於繪製熱力圖。
    範例請求: /get_calendar_heatmap?year=2025&month=7
    """
    print("\n[API] 收到請求：獲取學習日曆熱力圖數據...")
    try:
        # 從 App 請求中獲取年份和月份，若無則使用當前伺服器時間
        current_time = datetime.datetime.now(datetime.timezone.utc)
        year = int(request.args.get('year', current_time.year))
        month = int(request.args.get('month', current_time.month))
    except ValueError:
        # 如果傳入無效參數，使用安全的預設值
        current_time = datetime.datetime.now(datetime.timezone.utc)
        year = current_time.year
        month = current_time.month
    
    print(f"[API] 正在查詢 {year} 年 {month} 月的數據...")
    
    try:
        heatmap_data = tutor.get_daily_activity(year, month)
        return jsonify({"heatmap_data": heatmap_data})
    except Exception as e:
        print(f"[API] 查詢熱力圖數據時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/get_daily_details", methods=['GET'])
def get_daily_details_endpoint():
    """
    【v5.15 新增】: 提供特定日期的學習詳情。
    範例請求: /get_daily_details?date=2025-07-16
    """
    print("\n[API] 收到請求：獲取單日學習詳情...")
    # 從請求中獲取日期字串
    date_str = request.args.get('date')
    if not date_str:
        return jsonify({"error": "請提供日期參數 (date=YYYY-MM-DD)。"}), 400
    
    print(f"[API] 正在查詢日期 {date_str} 的詳情...")
    
    try:
        # 呼叫 main.py 中的新函式來獲取數據
        daily_details = tutor.get_daily_details(date_str)
        return jsonify(daily_details)
    except Exception as e:
        print(f"[API] 查詢單日詳情時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

# --- 運行伺服器 ---
if __name__ == '__main__':
    # 確保您已經設定了 OPENAI_API_KEY 環境變數
    if not os.getenv("OPENAI_API_KEY"):
        print("錯誤：請先設定 OPENAI_API_KEY 環境變數！")
    # 確保資料庫 URL 已設定
    if not os.getenv("DATABASE_URL"):
        print("錯誤：請先設定 DATABASE_URL 環境變數！")
    else:
        # debug=True 讓您修改程式碼後伺服器會自動重啟，方便開發
        # 當部署到 Render 時，它會使用 gunicorn，這個設定會被忽略
        app.run(host='0.0.0.0', port=5000, debug=True)