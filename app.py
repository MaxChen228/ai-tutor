# app.py - 您的 AI 家教後端 API 伺服器
import os
from flask import Flask, request, jsonify
import main as tutor  # 我們將 main.py 引用並取名為 tutor，方便呼叫

# --- 初始化 Flask 應用 ---
app = Flask(__name__)
app.config['JSON_AS_ASCII'] = False # 讓回傳的 JSON 可以正確顯示中文

# --- 應用程式啟動時，初始化資料庫 ---
# 確保資料庫表格都已經建立
print("正在初始化資料庫...")
tutor.init_db()
print("資料庫準備就緒。")


# --- API 端點 1: 開始一輪新的學習 ---
@app.route("/start_session", methods=['GET'])
def start_session_endpoint():
    """
    iOS App 從這裡獲取新一輪的題目。
    可以直接用 GET 請求，也可以設計成 POST 來接收參數，例如 SESSION_SIZE。
    """
    print("\n[API] 收到請求：開始新的一輪學習...")
    
    # 這裡我們先用 main.py 裡寫死的 SESSION_SIZE，未來可以從 request 裡讀取
    session_size = tutor.SESSION_SIZE

    # --- 這段邏輯完全來自您的 start_dynamic_session 函式 ---
    num_review_questions = int(session_size * tutor.REVIEW_RATIO)
    due_knowledge_points = tutor.get_due_knowledge_points(num_review_questions)
    actual_num_review = len(due_knowledge_points)
    num_new_questions = session_size - actual_num_review
    
    questions_to_ask = []
    print(f"[API] 準備生成 {actual_num_review} 題複習題和 {num_new_questions} 題新題目。")

    if actual_num_review > 0:
        weak_points_for_prompt = [f"- {p['category']}: {p['subcategory']}" for p in due_knowledge_points]
        weak_points_str = "\n".join(weak_points_for_prompt)
        review_questions = tutor.generate_question_batch(weak_points_str, actual_num_review)
        if review_questions:
            for q, point in zip(review_questions, due_knowledge_points):
                q['type'] = 'review'
                q['knowledge_point_id'] = point['id']
                q['mastery_level'] = point['mastery_level']
            questions_to_ask.extend(review_questions)

    if num_new_questions > 0:
        new_questions = tutor.generate_new_question_batch(num_new_questions)
        if new_questions:
            for q in new_questions:
                q['type'] = 'new'
            questions_to_ask.extend(new_questions)
    
    if not questions_to_ask:
        print("[API] AI 備課失敗或無題目可學。")
        return jsonify({"error": "AI備課失敗，無法生成題目。"}), 500
        
    tutor.random.shuffle(questions_to_ask)
    print(f"[API] 已成功生成 {len(questions_to_ask)} 題，準備回傳給 App。")
    # --- 邏輯結束 ---

    # 將題目列表以 JSON 格式回傳給 App
    return jsonify({"questions": questions_to_ask})


# --- API 端點 2: 提交答案並獲取批改回饋 ---
@app.route("/submit_answer", methods=['POST'])
def submit_answer_endpoint():
    """
    iOS App 將使用者作答的內容傳到這裡來批改。
    """
    print("\n[API] 收到請求：批改使用者答案...")
    
    # 從 App 傳來的 JSON 資料中獲取內容
    data = request.get_json()
    if not data:
        return jsonify({"error": "請求格式錯誤，需要 JSON 資料。"}), 400

    question_data = data.get('question_data')
    user_answer = data.get('user_answer')

    if not question_data or user_answer is None:
        return jsonify({"error": "請求資料不完整，需要 'question_data' 和 'user_answer'。"}), 400

    sentence = question_data.get('new_sentence', '（題目獲取失敗）')

    # 1. 獲取 AI 批改回饋
    feedback_data = tutor.get_tutor_feedback(sentence, user_answer)
    print(f"[API] 已獲取 AI 對 '{user_answer}' 的批改。")

    # 2. 儲存學習紀錄並更新知識點 (此函式會處理答錯的情況)
    tutor.add_mistake(question_data, user_answer, feedback_data)
    print(f"[API] 已儲存學習事件。")

    # 3. 如果是「複習題」且「答對了」，更新知識點掌握度
    if question_data.get('type') == 'review' and feedback_data.get('is_generally_correct'):
        point_id = question_data.get('knowledge_point_id')
        mastery = question_data.get('mastery_level')
        if point_id is not None and mastery is not None:
            tutor.update_knowledge_point_mastery(point_id, mastery)
            print(f"[API] 複習題答對，已更新知識點熟練度 (ID: {point_id})。")

    # 4. 將完整的批改回饋回傳給 App
    return jsonify(feedback_data)


# --- 運行伺服器 ---
if __name__ == '__main__':
    # 確保您已經設定了 OPENAI_API_KEY 環境變數
    if not os.getenv("OPENAI_API_KEY"):
        print("錯誤：請先設定 OPENAI_API_KEY 環境變數！")
    else:
        # debug=True 讓您修改程式碼後伺服器會自動重啟，方便開發
        app.run(debug=True, port=5000)