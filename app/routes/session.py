# app/routes/session.py

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, verify_jwt_in_request
from app.services import database as db
from app.services import ai_service as ai
import random

session_bp = Blueprint('session_bp', __name__)

def get_current_user_id():
    """獲取當前用戶ID，支持訪客模式"""
    try:
        verify_jwt_in_request(optional=True)
        return get_jwt_identity()
    except:
        return None

@session_bp.route("/start_session", methods=['GET'])
def start_session_endpoint():
    """
    【vNext 版】: 接收 generation_model 參數。
    """
    print("\n[API] 收到請求：開始新的一輪學習...")
    
    # 獲取當前用戶ID（可能為None表示訪客模式）
    user_id = get_current_user_id()
    print(f"[API] 用戶ID: {user_id if user_id else '訪客模式'}")
    
    try:
        desired_review_count = int(request.args.get('num_review', '3'))
        desired_new_count = int(request.args.get('num_new', '2'))
        difficulty = int(request.args.get('difficulty', '3'))
        length = request.args.get('length', 'medium')
        # 【新增】接收出題模型參數
        generation_model = request.args.get('generation_model') 
    except ValueError:
        desired_review_count, desired_new_count, difficulty, length = 3, 2, 3, 'medium'
        generation_model = None

    print(f"[API] App 請求參數: 複習={desired_review_count}, 全新={desired_new_count}, 難度={difficulty}, 長度={length}, 出題模型={generation_model}")
    
    questions_to_ask = []

    if desired_review_count > 0 and user_id:  # 只有已認證用戶才有複習題
        due_knowledge_points = db.get_due_knowledge_points_for_user(user_id, desired_review_count)
        actual_num_review = len(due_knowledge_points)
        print(f"[API] 從資料庫中找到 {actual_num_review} 題到期的複習題。")
        
        if actual_num_review > 0:
            weak_points_for_prompt = [
                f"- 錯誤分類: {p['category']} -> {p['subcategory']}\n  正確用法: \"{p['correct_phrase']}\"\n  核心觀念: {p['explanation']}"
                for p in due_knowledge_points
            ]
            weak_points_str = "\n\n".join(weak_points_for_prompt)
            # 【修改】傳入模型名稱
            review_questions = ai.generate_question_batch(weak_points_str, actual_num_review, model_name=generation_model)
            if review_questions:
                for q, point in zip(review_questions, due_knowledge_points):
                    if isinstance(q, dict):
                        q['type'] = 'review'
                        q['knowledge_point_id'] = point['id']
                        q['mastery_level'] = point['mastery_level']
                questions_to_ask.extend(review_questions)

    if desired_new_count > 0:
        print(f"[API] 準備生成 {desired_new_count} 個全新挑戰...")
        # 【修改】傳入模型名稱
        new_questions = ai.generate_new_question_batch(desired_new_count, difficulty, length, model_name=generation_model)
        if new_questions:
            for q in new_questions:
                 if isinstance(q, dict):
                    q['type'] = 'new'
            questions_to_ask.extend(new_questions)
    
    if not questions_to_ask:
        print("[API] 本次請求無題目生成。")
        return jsonify({"questions": []})
        
    random.shuffle(questions_to_ask)
    print(f"[API] 已成功生成 {len(questions_to_ask)} 題，準備回傳給 App。")
    return jsonify({"questions": questions_to_ask})

@session_bp.route("/submit_answer", methods=['POST'])
def submit_answer_endpoint():
    """
    【vNext 版 / 互動式修改】: 接收 grading_model 參數，且不再自動儲存錯誤。
    """
    print("\n[API] 收到請求：批改使用者答案...")
    
    # 獲取當前用戶ID（可能為None表示訪客模式）
    user_id = get_current_user_id()
    print(f"[API] 批改用戶ID: {user_id if user_id else '訪客模式'}")
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "請求格式錯誤，需要 JSON 資料。"}), 400

    question_data = data.get('question_data')
    user_answer = data.get('user_answer')
    # 【新增】從 JSON body 中接收批改模型參數
    grading_model = data.get('grading_model')

    if not question_data or user_answer is None:
        return jsonify({"error": "請求資料不完整，需要 'question_data' 和 'user_answer'。"}), 400

    sentence = question_data.get('new_sentence', '（題目獲取失敗）')
    hint_text = question_data.get('hint_text') 

    review_concept_to_check = None
    if question_data.get('type') == 'review':
        try:
            point_id_to_check = int(question_data.get('knowledge_point_id'))
            review_concept_to_check = db.get_knowledge_point_phrase(point_id_to_check)
        except (TypeError, ValueError):
            print(f"[API] 警告：收到的 knowledge_point_id 無效。")
            pass

    # 將 hint_text 和模型名稱傳遞給批改函式
    feedback_data = ai.get_tutor_feedback(sentence, user_answer, review_context=review_concept_to_check, hint_text=hint_text, model_name=grading_model)

    # 對於複習題，如果答對了核心觀念，我們仍然立即更新其熟練度。
    # 這與「是否要將新錯誤加入知識庫」是兩件獨立的事。
    if review_concept_to_check and feedback_data.get('did_master_review_concept'):
        print(f"[API] 核心觀念 '{review_concept_to_check}' 複習成功！")
        point_id = question_data.get('knowledge_point_id')
        mastery = question_data.get('mastery_level')
        if point_id is not None and mastery is not None:
            db.update_knowledge_point_mastery(point_id, mastery)
    
    # 【核心修改】：移除 db.add_mistake(...) 這一行，不再自動儲存錯誤。
    # 完整的 feedback_data 將直接回傳給前端，由使用者決定如何處理。
    
    return jsonify(feedback_data)

@session_bp.route("/get_smart_hint", methods=['POST'])
def get_smart_hint_endpoint():
    """
    【新功能】AI智慧提示 - 根據使用者當前翻譯和題目內容提供引導性提示
    """
    print("\n[API] 收到請求：生成AI智慧提示...")
    data = request.get_json()
    if not data:
        return jsonify({"error": "請求格式錯誤，需要 JSON 資料。"}), 400

    chinese_sentence = data.get('chinese_sentence')
    user_current_input = data.get('user_current_input', '')
    original_hint = data.get('original_hint', '')
    model_name = data.get('model_name')

    if not chinese_sentence:
        return jsonify({"error": "請求資料不完整，需要 'chinese_sentence'。"}), 400

    print(f"[API] 正在為句子「{chinese_sentence}」生成智慧提示...")
    print(f"[API] 使用者當前輸入：「{user_current_input}」")
    
    try:
        smart_hint_response = ai.generate_smart_hint(
            chinese_sentence=chinese_sentence,
            user_current_input=user_current_input,
            original_hint=original_hint,
            model_name=model_name
        )
        
        return jsonify(smart_hint_response)
    
    except Exception as e:
        print(f"[API] 生成智慧提示時發生錯誤: {e}")
        return jsonify({
            "error": f"AI 智慧提示服務暫時無法使用：{str(e)}",
            "smart_hint": "抱歉，智慧提示功能暫時無法使用。請參考基本提示或稍後再試。"
        }), 500