# app.py - 您的 AI 家教後端 API 伺服器
import os
import json
from flask import Flask, request, jsonify
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
    【v5.5 客製化修改】: 不再使用後端寫死的設定，而是從 App 的請求參數中動態獲取題目數量。
    範例請求: /start_session?num_review=3&num_new=2
    """
    print("\n[API] 收到請求：開始新的一輪學習...")
    
    # 從請求的 URL 查詢參數中獲取數值，如果 App 未提供，則使用預設值
    try:
        num_review_questions = int(request.args.get('num_review', '3'))
        num_new_questions = int(request.args.get('num_new', '2'))
    except ValueError:
        # 如果傳入的不是數字，則使用安全的預設值
        num_review_questions = 3
        num_new_questions = 2

    print(f"[API] App 要求生成 {num_review_questions} 題複習題和 {num_new_questions} 題新題目。")

    # 原本的邏輯幾乎可以完全重用，只是變數來源不同
    due_knowledge_points = tutor.get_due_knowledge_points(num_review_questions)
    actual_num_review = len(due_knowledge_points)
    
    questions_to_ask = []

    if actual_num_review > 0:
        weak_points_for_prompt = [
            f"- 錯誤分類: {p['category']} -> {p['subcategory']}\n  正確用法: \"{p['correct_phrase']}\"\n  核心觀念: {p['explanation']}"
            for p in due_knowledge_points
        ]
        weak_points_str = "\n\n".join(weak_points_for_prompt)
        print(f"正在針對您以下的 {actual_num_review} 個具體弱點設計考題：\n{weak_points_str}")
        
        review_questions = tutor.generate_question_batch(weak_points_str, actual_num_review)
        if review_questions:
            for q, point in zip(review_questions, due_knowledge_points):
                if isinstance(q, dict):
                    q['type'] = 'review'
                    q['knowledge_point_id'] = point['id']
                    q['mastery_level'] = point['mastery_level']
            questions_to_ask.extend(review_questions)

    if num_new_questions > 0:
        print(f"正在為您準備 {num_new_questions} 個全新挑戰...")
        new_questions = tutor.generate_new_question_batch(num_new_questions)
        if new_questions:
            for q in new_questions:
                 if isinstance(q, dict):
                    q['type'] = 'new'
            questions_to_ask.extend(new_questions)
    
    if not questions_to_ask:
        print("[API] AI 備課失敗或無題目可學。")
        return jsonify({"error": "AI備課失敗，無法生成題目。"}), 500
        
    tutor.random.shuffle(questions_to_ask)
    print(f"[API] 已成功生成 {len(questions_to_ask)} 題，準備回傳給 App。")
    return jsonify({"questions": questions_to_ask})

# --- API 端點 2: 提交答案並獲取批改回饋 ---
@app.route("/submit_answer", methods=['POST'])
def submit_answer_endpoint():
    """
    iOS App 將使用者作答的內容傳到這裡來批改。
    【v5.4 PostgreSQL 版】: 此函式邏輯不變，因為它不直接操作資料庫。
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
    feedback_data = tutor.get_tutor_feedback(sentence, user_answer)
    tutor.add_mistake(question_data, user_answer, feedback_data)

    if question_data.get('type') == 'review' and feedback_data.get('is_generally_correct'):
        point_id = question_data.get('knowledge_point_id')
        mastery = question_data.get('mastery_level')
        if point_id is not None and mastery is not None:
            tutor.update_knowledge_point_mastery(point_id, mastery)
    
    return jsonify(feedback_data)


# --- API 端點 3: 獲取知識點儀表板數據 ---
@app.route("/get_dashboard", methods=['GET'])
def get_dashboard_endpoint():
    """
    【v5.4 PostgreSQL 版】: 使用新的連線函式和字典 cursor。
    """
    print("\n[API] 收到請求：獲取知識點儀表板數據...")
    conn = None
    try:
        conn = tutor.get_db_connection()
        # 使用 DictCursor 讓回傳的結果可以用欄位名稱存取
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
            cursor.execute("""
                SELECT 
                    category, subcategory, correct_phrase, explanation, 
                    user_context_sentence, incorrect_phrase_in_context, 
                    mastery_level, mistake_count, correct_count 
                FROM knowledge_points 
                ORDER BY mastery_level ASC, mistake_count DESC
            """)
            points_raw = cursor.fetchall()
        # DictCursor 回傳的結果可以直接轉換為字典列表
        points_dict = [dict(row) for row in points_raw]
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