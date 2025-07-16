# app/routes/session.py

from flask import Blueprint, request, jsonify
from app.services import ai_service, database as db

session_bp = Blueprint('session_bp', __name__)

@session_bp.route("/start_session", methods=['GET'])
def start_session_endpoint():
    """
    開始一個新的學習回合，包含複習題與新題目。
    現在會接收前端指定的出題模型。
    """
    try:
        num_review = int(request.args.get('num_review', 2))
        num_new = int(request.args.get('num_new', 1))
        difficulty = int(request.args.get('difficulty', 3))
        length = request.args.get('length', 'medium')
        generation_model = request.args.get('generation_model', 'gemini-1.5-flash-latest')
        
        print(f"\n[Session] 收到新回合請求: {num_review} 複習, {num_new} 新題 (出題模型: {generation_model})")

        all_questions = []
        
        # 1. 獲取複習題
        if num_review > 0:
            due_points = db.get_due_knowledge_points(limit=num_review)
            if due_points:
                weak_points_str = "\n".join([f"- {p['correct_phrase']} (上次熟練度: {p['mastery_level']:.2f})" for p in due_points])
                review_questions_data = ai_service.generate_question_batch(weak_points_str, len(due_points), generation_model)
                
                if review_questions_data:
                    for i, q_data in enumerate(review_questions_data):
                        original_point = due_points[i]
                        q_data['type'] = 'review'
                        q_data['knowledge_point_id'] = original_point['id']
                        q_data['mastery_level'] = original_point['mastery_level']
                        q_data['original_mistake_id'] = original_point['id']
                    all_questions.extend(review_questions_data)

        # 2. 獲取新題目
        if num_new > 0:
            new_questions_data = ai_service.generate_new_question_batch(num_new, difficulty, length, generation_model)
            if new_questions_data:
                for q_data in new_questions_data:
                    q_data['type'] = 'new'
                all_questions.extend(new_questions_data)
        
        if not all_questions:
            # 即使沒題目，也回傳一個空的成功回應，避免前端出錯
            return jsonify({"questions": []})

        return jsonify({"questions": all_questions})
    except Exception as e:
        print(f"[/start_session] 發生嚴重錯誤: {e}")
        return jsonify({"error": "伺服器在準備題目時發生未知錯誤。"}), 500


@session_bp.route("/submit_answer", methods=['POST'])
def submit_answer_endpoint():
    """
    提交使用者答案，進行批改並更新資料庫。
    現在會接收前端指定的批改模型。
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "無效的請求，需要 JSON 資料。"}), 400

        question_data = data.get('question_data')
        user_answer = data.get('user_answer')
        
        # 【修正核心】獲取批改模型，並在呼叫時傳入
        grading_model = data.get('grading_model', 'gemini-1.5-pro-latest')
        
        print(f"\n[Session] 收到答案提交 (批改模型: {grading_model})")

        is_review = question_data.get('type') == 'review'
        review_context = question_data.get('hint_text') if is_review else None
        hint_text = question_data.get('hint_text')

        # 【修正核心】將 grading_model 作為第五個參數傳入
        feedback = ai_service.get_tutor_feedback(
            chinese_sentence=question_data.get('new_sentence'), 
            user_translation=user_answer, 
            review_context=review_context, 
            hint_text=hint_text, 
            model_name=grading_model
        )

        is_correct = feedback.get('is_generally_correct', False)
        
        if is_review:
            if feedback.get('did_master_review_concept', False):
                print(f"[Session] 複習題 ID {question_data.get('knowledge_point_id')} 核心概念答對，更新熟練度。")
                db.update_knowledge_point_mastery(question_data.get('knowledge_point_id'), question_data.get('mastery_level', 0))
                # 即使有其他小錯，只要核心概念答對，就視為答對
                is_correct = True
            else:
                print(f"[Session] 複習題 ID {question_data.get('knowledge_point_id')} 核心概念答錯。")
                is_correct = False
        
        # 只要答案不完全正確，且 AI 有分析出錯誤點，就記錄下來
        if not is_correct and feedback.get('error_analysis'):
            exclude_phrase = review_context if is_review else None
            print(f"[Session] 發現新錯誤，準備寫入資料庫 (排除: {exclude_phrase})。")
            db.add_mistake(question_data, user_answer, feedback, exclude_phrase)
        elif not is_correct:
            # 即使 AI 沒分析出錯誤，但判定為錯，還是要記錄學習事件
            print("[Session] 答案被判定為錯誤，但 AI 未提供具體錯誤分析，僅記錄事件。")
            db.add_mistake(question_data, user_answer, feedback)
            
        return jsonify(feedback)
    except Exception as e:
        print(f"[/submit_answer] 發生嚴重錯誤: {e}")
        return jsonify({"error": "伺服器在批改答案時發生未知錯誤。"}), 500