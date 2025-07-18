# app/routes/vocabulary.py - 新建檔案

from flask import Blueprint, request, jsonify
import app.services.database as db
import app.services.ai_service as ai
import random
from datetime import datetime

vocabulary_bp = Blueprint('vocabulary', __name__)

# === 單字管理 API ===

@vocabulary_bp.route("/words", methods=['GET'])
def get_vocabulary_words():
    """獲取單字列表（支援搜尋、分頁、篩選）"""
    print("\n[API] 收到請求：獲取單字列表")
    
    # 獲取查詢參數
    search_query = request.args.get('search', '').strip()
    page = int(request.args.get('page', 1))
    limit = int(request.args.get('limit', 20))
    mastery_filter = request.args.get('mastery')  # 'new', 'learning', 'mastered'
    due_only = request.args.get('due_only', 'false').lower() == 'true'
    
    try:
        if due_only:
            # 獲取今日需要複習的單字
            words = db.get_due_vocabulary_words(limit)
            total_count = len(words)
        elif search_query:
            # 搜尋單字
            words = db.search_vocabulary_words(search_query, limit)
            total_count = len(words)
        else:
            # 一般列表（未來實作分頁）
            words = db.get_due_vocabulary_words(limit * page)  # 簡化的分頁
            total_count = len(words)
        
        print(f"[API] 回傳 {len(words)} 個單字")
        
        return jsonify({
            "words": words,
            "total_count": total_count,
            "page": page,
            "limit": limit
        })
        
    except Exception as e:
        print(f"[API] 獲取單字列表時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@vocabulary_bp.route("/words/<int:word_id>", methods=['GET'])
def get_vocabulary_word_detail(word_id):
    """獲取單字詳細資訊"""
    print(f"\n[API] 收到請求：獲取單字詳情 ID={word_id}")
    
    try:
        word = db.get_vocabulary_word_by_id(word_id)
        if not word:
            return jsonify({"error": "找不到指定的單字"}), 404
        
        return jsonify(word)
        
    except Exception as e:
        print(f"[API] 獲取單字詳情時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@vocabulary_bp.route("/words", methods=['POST'])
def add_vocabulary_word():
    """新增單字"""
    print("\n[API] 收到請求：新增單字")
    
    data = request.get_json()
    if not data or 'word' not in data:
        return jsonify({"error": "請提供單字資料"}), 400
    
    word = data['word'].strip().lower()
    if not word:
        return jsonify({"error": "單字不能為空"}), 400
    
    try:
        # 檢查單字是否已存在
        existing_word = db.get_vocabulary_word_by_word(word)  # 需要實作按單字查詢
        if existing_word:
            return jsonify({"error": "單字已存在"}), 409
        
        # 使用智慧新增功能
        word_data = ai.smart_add_vocabulary_word(
            word=word,
            context=data.get('context'),
            source_type=data.get('source_type', 'manual'),
            source_reference_id=data.get('source_reference_id')
        )
        
        # 儲存到資料庫
        word_id = db.add_vocabulary_word(word_data)
        
        print(f"[API] 成功新增單字: {word} (ID: {word_id})")
        
        return jsonify({
            "message": "單字新增成功",
            "word_id": word_id,
            "word_data": word_data
        }), 201
        
    except Exception as e:
        print(f"[API] 新增單字時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@vocabulary_bp.route("/words/<int:word_id>", methods=['PUT'])
def update_vocabulary_word(word_id):
    """更新單字資訊"""
    print(f"\n[API] 收到請求：更新單字 ID={word_id}")
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "請提供更新資料"}), 400
    
    try:
        # 更新單字（需要實作 update_vocabulary_word 函式）
        success = db.update_vocabulary_word(word_id, data)
        
        if success:
            return jsonify({"message": "單字更新成功"})
        else:
            return jsonify({"error": "更新失敗"}), 400
            
    except Exception as e:
        print(f"[API] 更新單字時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@vocabulary_bp.route("/words/<int:word_id>", methods=['DELETE'])
def delete_vocabulary_word(word_id):
    """刪除單字"""
    print(f"\n[API] 收到請求：刪除單字 ID={word_id}")
    
    try:
        # 實際上是歸檔，不是真刪除
        success = db.archive_vocabulary_word(word_id)
        
        if success:
            return jsonify({"message": "單字已歸檔"})
        else:
            return jsonify({"error": "歸檔失敗"}), 400
            
    except Exception as e:
        print(f"[API] 歸檔單字時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

# === 學習和複習 API ===

@vocabulary_bp.route("/review/daily", methods=['GET'])
def get_daily_review_words():
    """獲取今日複習單字"""
    print("\n[API] 收到請求：獲取今日複習單字")
    
    limit = int(request.args.get('limit', 20))
    
    try:
        words = db.get_due_vocabulary_words(limit)
        
        print(f"[API] 今日需複習 {len(words)} 個單字")
        
        return jsonify({
            "review_words": words,
            "total_due": len(words)
        })
        
    except Exception as e:
        print(f"[API] 獲取今日複習單字時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@vocabulary_bp.route("/review/submit", methods=['POST'])
def submit_vocabulary_review():
    """提交單字複習結果"""
    print("\n[API] 收到請求：提交單字複習結果")
    
    data = request.get_json()
    required_fields = ['word_id', 'is_correct', 'review_type']
    
    if not data or not all(field in data for field in required_fields):
        return jsonify({"error": "請提供完整的複習資料"}), 400
    
    try:
        word_id = data['word_id']
        is_correct = data['is_correct']
        review_type = data['review_type']
        response_time = data.get('response_time')
        
        # 更新掌握度和複習排程
        success = db.update_vocabulary_mastery(
            word_id=word_id,
            is_correct=is_correct,
            response_time=response_time,
            review_type=review_type
        )
        
        if success:
            # 獲取更新後的單字資訊
            updated_word = db.get_vocabulary_word_by_id(word_id)
            
            print(f"[API] 單字複習結果已記錄: ID={word_id}, 正確={is_correct}")
            
            return jsonify({
                "message": "複習結果已記錄",
                "updated_word": updated_word
            })
        else:
            return jsonify({"error": "記錄複習結果失敗"}), 400
            
    except Exception as e:
        print(f"[API] 記錄複習結果時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

# === 測驗相關 API ===

@vocabulary_bp.route("/quiz/generate", methods=['POST'])
def generate_vocabulary_quiz():
    """生成單字測驗"""
    print("\n[API] 收到請求：生成單字測驗")
    
    data = request.get_json()
    quiz_type = data.get('quiz_type', 'multiple_choice')  # flashcard, multiple_choice, context_fill
    word_count = data.get('word_count', 10)
    difficulty_level = data.get('difficulty_level')  # 可選的難度篩選
    
    try:
        # 獲取適合的單字
        candidate_words = db.get_due_vocabulary_words(word_count * 2)  # 多取一些備選
        
        if len(candidate_words) < word_count:
            # 如果今日複習單字不夠，補充一些其他單字
            additional_words = db.search_vocabulary_words("", word_count)
            candidate_words.extend(additional_words)
        
        # 隨機選擇指定數量的單字
        selected_words = random.sample(candidate_words, min(word_count, len(candidate_words)))
        
        quiz_questions = []
        
        for word in selected_words:
            if quiz_type == 'multiple_choice':
                # 生成選擇題
                quiz_data = ai.generate_vocabulary_quiz_options(
                    target_word=word['word'],
                    correct_definition=word['definition_zh']
                )
                
                # 組合選項並隨機排列
                all_options = [quiz_data['correct_answer']] + quiz_data['wrong_options']
                random.shuffle(all_options)
                correct_index = all_options.index(quiz_data['correct_answer'])
                
                quiz_questions.append({
                    'word_id': word['id'],
                    'word': word['word'],
                    'pronunciation': word.get('pronunciation_ipa'),
                    'question_type': 'multiple_choice',
                    'question_text': quiz_data['question_text'],
                    'options': all_options,
                    'correct_index': correct_index,
                    'explanation': quiz_data.get('explanation')
                })
                
            elif quiz_type == 'context_fill':
                # 生成語境填空題
                context_data = ai.generate_context_fill_question(
                    word=word['word'],
                    difficulty_level=word.get('difficulty_level', 3)
                )
                
                quiz_questions.append({
                    'word_id': word['id'],
                    'word': word['word'],
                    'question_type': 'context_fill',
                    'question_sentence': context_data['question_sentence'],
                    'complete_sentence': context_data['complete_sentence'],
                    'target_word': word['word'],
                    'hints': context_data.get('context_hints', [])
                })
                
            else:  # flashcard
                quiz_questions.append({
                    'word_id': word['id'],
                    'word': word['word'],
                    'pronunciation': word.get('pronunciation_ipa'),
                    'part_of_speech': word.get('part_of_speech'),
                    'definition_zh': word['definition_zh'],
                    'definition_en': word.get('definition_en'),
                    'examples': word.get('examples', []),
                    'question_type': 'flashcard'
                })
        
        print(f"[API] 生成了 {len(quiz_questions)} 道 {quiz_type} 測驗題")
        
        return jsonify({
            "quiz_type": quiz_type,
            "questions": quiz_questions,
            "total_questions": len(quiz_questions)
        })
        
    except Exception as e:
        print(f"[API] 生成單字測驗時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

# === 統計和進度 API ===

@vocabulary_bp.route("/statistics", methods=['GET'])
def get_vocabulary_statistics():
    """獲取單字庫統計資訊"""
    print("\n[API] 收到請求：獲取單字統計")
    
    try:
        stats = db.get_vocabulary_statistics()
        
        return jsonify({
            "total_words": stats['total_words'],
            "mastered_words": stats['mastered_words'],
            "learning_words": stats['learning_words'],
            "new_words": stats['new_words'],
            "due_today": stats['due_today'],
            "mastery_percentage": round((stats['mastered_words'] / max(stats['total_words'], 1)) * 100, 1)
        })
        
    except Exception as e:
        print(f"[API] 獲取統計資訊時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

# === AI輔助功能 API ===

@vocabulary_bp.route("/ai/define", methods=['POST'])
def ai_define_word():
    """使用AI為單字生成定義"""
    print("\n[API] 收到請求：AI生成單字定義")
    
    data = request.get_json()
    if not data or 'word' not in data:
        return jsonify({"error": "請提供要定義的單字"}), 400
    
    word = data['word'].strip()
    context = data.get('context')
    model_name = data.get('model_name')
    
    try:
        definition_data = ai.generate_vocabulary_definition(word, context, model_name)
        
        return jsonify({
            "word": word,
            "definition_data": definition_data
        })
        
    except Exception as e:
        print(f"[API] AI生成定義時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500

@vocabulary_bp.route("/ai/extract-from-translation", methods=['POST'])
def extract_vocabulary_from_translation():
    """從翻譯錯誤中提取單字"""
    print("\n[API] 收到請求：從翻譯錯誤提取單字")
    
    data = request.get_json()
    if not data or 'knowledge_point_id' not in data:
        return jsonify({"error": "請提供知識點ID"}), 400
    
    try:
        # 獲取知識點資料
        knowledge_point = db.get_knowledge_point_by_id(data['knowledge_point_id'])
        if not knowledge_point:
            return jsonify({"error": "找不到指定的知識點"}), 404
        
        # 提取單字
        extraction_result = ai.extract_vocabulary_from_translation_error(knowledge_point)
        
        # 可選：自動將高優先級的單字加入單字庫
        auto_add = data.get('auto_add', False)
        added_words = []
        
        if auto_add:
            for word_info in extraction_result['extracted_words']:
                if word_info['priority'] == 'high':
                    word_data = ai.smart_add_vocabulary_word(
                        word=word_info['word'],
                        context=knowledge_point.get('user_context_sentence'),
                        source_type='translation_error',
                        source_reference_id=data['knowledge_point_id']
                    )
                    word_id = db.add_vocabulary_word(word_data)
                    added_words.append({'word': word_info['word'], 'word_id': word_id})
        
        return jsonify({
            "extraction_result": extraction_result,
            "auto_added_words": added_words
        })
        
    except Exception as e:
        print(f"[API] 提取單字時發生錯誤: {e}")
        return jsonify({"error": str(e)}), 500