# app/services/ai_service.py

import os
import json
import random
from app.assets import EXAMPLE_SENTENCE_BANK

# 條件式導入 AI 服務 - 避免部署時強制安裝
openai = None
genai = None

try:
    import openai
except ImportError:
    print("警告: openai 套件未安裝，OpenAI 功能將無法使用")

try:
    import google.generativeai as genai
except ImportError:
    print("警告: google-generativeai 套件未安裝，Gemini 功能將無法使用")

MONITOR_MODE = True

# --- 模型設定與 API 初始化 ---

AVAILABLE_MODELS = {
    "gpt-4o": "openai/gpt-4o",
    "gemini-2.5-pro": "gemini/gemini-2.5-pro",
    "gemini-2.5-flash": "gemini/gemini-2.5-flash",
}
DEFAULT_GENERATION_MODEL = "gemini-2.5-pro"
DEFAULT_GRADING_MODEL = "gemini-2.5-flash"

# OpenAI 初始化
openai_client = None
if openai and os.environ.get("OPENAI_API_KEY"):
    try:
        openai_client = openai.OpenAI()
    except Exception as e:
        print(f"初始化 OpenAI 時發生錯誤: {e}")
else:
    print("警告: OpenAI 未啟用（套件未安裝或 API KEY 未設定）")

# Gemini 初始化  
gemini_api_key = None
gemini_generation_config = None
if genai and os.environ.get("GEMINI_API_KEY"):
    try:
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        genai.configure(api_key=gemini_api_key)
        gemini_generation_config = genai.GenerationConfig(response_mime_type="application/json")
    except Exception as e:
        print(f"初始化 Gemini 時發生錯誤: {e}")
else:
    print("警告: Gemini 未啟用（套件未安裝或 API KEY 未設定）")

# --- 文法庫讀取 ---
try:
    with open("app/grammar_patterns.json", "r", encoding="utf-8") as f:
        grammar_patterns = json.load(f)
    print(f"成功載入 {len(grammar_patterns)} 筆文法句型。")
except FileNotFoundError:
    print("錯誤：找不到 `app/grammar_patterns.json` 檔案。新題生成功能將受限。")
    grammar_patterns = []
except json.JSONDecodeError:
    print("錯誤：`app/grammar_patterns.json` 格式錯誤，無法解析。")
    grammar_patterns = []


# --- 私有函式 ---

def _call_llm_api(system_prompt, user_prompt, model_name, default_model):
    model_name = model_name or default_model
    full_model_id = AVAILABLE_MODELS.get(model_name)
    if not full_model_id:
        print(f"警告：找不到名為 '{model_name}' 的模型，將使用預設模型 '{default_model}'。")
        full_model_id = AVAILABLE_MODELS[default_model]
    
    provider, model_id = full_model_id.split('/', 1)
    print(f"[AI Service] 正在使用模型: Provider={provider}, Model ID={model_id}")

    if provider == 'gemini':
        gemini_model = genai.GenerativeModel(model_id, generation_config=gemini_generation_config)
        full_prompt = system_prompt + "\n\n" + user_prompt
        if MONITOR_MODE:
            print("\n" + "="*20 + f" Gemini API INPUT (Model: {model_id}) " + "="*20)
            print(full_prompt)
            print("="*60 + "\n")
        response = gemini_model.generate_content(full_prompt)
        return json.loads(response.text)
    elif provider == 'openai':
        if MONITOR_MODE:
            print("\n" + "="*20 + f" OpenAI API INPUT (Model: {model_id}) " + "="*20)
            print("--- SYSTEM PROMPT ---\n" + system_prompt)
            print("\n--- USER PROMPT ---\n" + user_prompt)
            print("="*60 + "\n")
        response = openai_client.chat.completions.create(
            model=model_id,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    else:
        raise ValueError(f"不支援的 LLM 供應商: {provider}")

def _normalize_questions_output(response_data):
    if isinstance(response_data, dict) and "questions" in response_data and isinstance(response_data["questions"], list):
        return response_data["questions"]
    elif isinstance(response_data, list):
         return response_data
    elif isinstance(response_data, dict):
        for value in response_data.values():
            if isinstance(value, list):
                return value
    return []

# --- 公共函式 ---

def generate_new_question_batch(num_new, difficulty, length, model_name=None):
    if not grammar_patterns:
        print("錯誤：文法庫為空或載入失敗，無法生成新題目。")
        return []
    try:
        selected_patterns = random.sample(grammar_patterns, k=min(num_new, len(grammar_patterns)))
    except ValueError:
        return []
    generated_questions = []
    for i, pattern_data in enumerate(selected_patterns):
        print(f"\n[AI Service] 正在為第 {i+1}/{len(selected_patterns)} 個新句型出題...")
        print(f"  - 目標句型: {pattern_data.get('pattern', 'N/A')}")
        example_sentences = EXAMPLE_SENTENCE_BANK.get(length, {}).get(str(difficulty), [])
        example_sentences_str = "\n".join([f"- {s}" for s in example_sentences]) if example_sentences else "無風格參考範例"
        system_prompt = f"""
        你是一位英文命題專家，你的唯一任務是根據我提供的一個「核心句型」，設計一題高品質的中文翻譯題。
        **指令一：強制使用核心句型**
        你「必須」圍繞以下這個句型來出題。題目的答案必須用到這個句型。
        ---
        【核心句型資料】
        - 句型: `{pattern_data.get('pattern', '無')}`
        - 說明: `{pattern_data.get('explanation', '無')}`
        - 範例: `{pattern_data.get('example_zh', '無')} -> {pattern_data.get('example_en', '無')}`
        ---
        **指令二：模仿風格**
        題目的難度、長度和語氣，請盡量模仿下方的「風格參考範例」。
        ---
        【風格參考範例】
        {example_sentences_str}
        ---
        **指令三：嚴格輸出格式**
        你的回覆「必須」是一個 JSON 物件，且「只能」包含這兩個 key：
        1. `new_sentence`: (string) 你設計的中文翻譯題目。
        2. `hint_text`: (string) 提示文字，內容必須是核心句型的「句型」本身，例如 `S + V + as...as...`。
        """
        user_prompt = "請嚴格遵照你的三項核心指令，為我生成一題考題的 JSON 物件。"
        try:
            response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
            if isinstance(response_data, dict) and 'new_sentence' in response_data and 'hint_text' in response_data:
                response_data['hint_text'] = pattern_data.get('pattern', response_data['hint_text'])
                generated_questions.append(response_data)
                print(f"  - 成功生成題目: \"{response_data['new_sentence']}\"")
            else:
                print(f"  - 警告：AI 回傳格式不符，已跳過此題。收到的資料: {response_data}")
        except Exception as e:
            print(f"為句型 '{pattern_data.get('pattern')}' 生成題目時發生錯誤: {e}")
            continue
    return generated_questions

def generate_question_batch(weak_points_str, num_questions, model_name=None):
    """為複習題生成問題"""
    system_prompt = f"""
    你是一位專業的英文教學 AI，專門為學生的弱點設計「複習題」。
    
    以下是學生需要複習的弱點知識：
    {weak_points_str}
    
    請為每個弱點設計一個中文翻譯題目，用來測試學生是否已掌握該知識點。
    
    輸出格式要求：
    回傳一個 JSON 陣列，每個元素包含：
    - new_sentence: 中文翻譯題目
    - hint_text: 考點提示（簡潔描述該知識點）
    
    請確保題目設計合理，能有效檢驗學生對該知識點的掌握程度。
    """
    
    user_prompt = f"請為這 {num_questions} 個弱點知識設計對應的複習題目。"
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        return _normalize_questions_output(response_data)
    except Exception as e:
        print(f"生成複習題時發生錯誤: {e}")
        return []

def get_tutor_feedback(chinese_sentence, user_translation, review_context=None, hint_text=None, model_name=None):
    """批改使用者答案並提供回饋。"""
    
    error_analysis_instructions = """
    4.  `error_analysis`: (array of objects) 錯誤分析清單。如果沒有任何錯誤，請回傳一個空清單 `[]`。
        清單中的每一個物件都「必須」包含以下「所有」欄位：
        * `error_type_code`: (string) 【極重要】你「必須」從以下四個代碼中，選擇「一個」最貼切的分類：
            - `A`: 詞彙與片語錯誤 (用字不當、搭配詞錯誤、介係詞錯誤等)
            - `B`: 語法結構錯誤 (時態、主被動、詞性、句子結構錯誤等)
            - `C`: 語意與語用錯誤 (語意不通、邏輯矛盾、中式英文、語氣不當等)
            - `D`: 拼寫與格式錯誤 (拼字、大小寫、標點符號等基本錯誤)
        * `key_point_summary`: (string) 【最重要的欄位】為這個錯誤點提煉一個「錯誤焦點」，例如「'in the other hand' 應為 'on the other hand'」。此欄位「必須」使用**繁體中文**。
        * `original_phrase`: (string) 從學生答案中，精確地提取出「錯誤」的那個單字或片語。
        * `correction`: (string) 針對該錯誤片語，提供「正確」的寫法。
        * `explanation`: (string) 「必須」使用**繁體中文**，簡潔地解釋為什麼這是錯的，以及應該如何修正。
        * `severity`: (string) 錯誤嚴重程度，`major` 或 `minor`。
    """
    
    overall_suggestion_instruction = "3.  `overall_suggestion`: (string) 在綜合考量所有錯誤後，提供一個「整體最佳」的翻譯建議。這個建議「必須」是完整的句子，且「必須」使用**繁體中文**。"

    if review_context:
        system_prompt = f"""
        你是一位嚴謹的英文教學評分 AI。
        **首要任務**: 判斷學生作答是否掌握了「核心複習觀念: {review_context}」，並在回傳的 JSON 中設定 `did_master_review_concept` (boolean) 的值。
        **次要任務**: 分析其他與核心觀念無關的錯誤。
        **排他性原則**: `error_analysis` 列表絕對不應包含與核心複習觀念相關的分析。
        **輸出格式**: 你的 JSON 回覆必須包含以下所有欄位：
        1.  `did_master_review_concept`: (boolean)
        2.  `is_generally_correct`: (boolean)
        {overall_suggestion_instruction}
        {error_analysis_instructions}
        
        **原始中文句子是**: "{chinese_sentence}"
        """
    else:
        system_prompt = f"""
        你是一位細心且嚴謹的英文家教 AI。
        **核心考點提示**: 「{hint_text if hint_text else '無特定提示'}」。請特別留意此點的掌握情況。
        **輸出格式**: 你的 JSON 回覆必須包含以下所有欄位：
        1.  `is_generally_correct`: (boolean)
        2.  `overall_suggestion`: (string) 在綜合考量所有錯誤後，提供一個「整體最佳」的翻譯建議。這個建議「必須」是完整的句子，且「必須」使用**繁體中文**。
        {error_analysis_instructions}

        **原始中文句子是**: "{chinese_sentence}"
        """
        
    user_prompt = f"這是學生的翻譯：「{user_translation}」。請根據你的專業知識和上述嚴格指令，為我生成一份鉅細靡遺、完全符合格式的 JSON 分析報告。"

    try:
        return _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GRADING_MODEL)
    except Exception as e:
        print(f"AI 批改時發生錯誤 - Model: {model_name}, Error: {e}")
        return {
            "did_master_review_concept": False, 
            "is_generally_correct": False, 
            "overall_suggestion": f"AI 模型 ({model_name}) 暫時無法提供服務，請稍後再試。",
            "error_analysis": [{
                "error_type_code": "E",
                "key_point_summary": "系統錯誤",
                "original_phrase": "N/A",
                "correction": "N/A",
                "explanation": f"系統無法處理 AI 的回覆：{e}",
                "severity": "major"
            }]
        }

def merge_error_analyses(error1, error2):
    """使用 AI 將兩個錯誤分析智慧地合併成一個。"""
    
    system_prompt = """
    你是一位專業的英文教學 AI 助理。
    你的任務是將兩個相關的英文錯誤分析「智慧地合併」成一個更精煉、更有教學價值的知識點。
    
    合併原則：
    1. 找出兩個錯誤的共同核心觀念
    2. 整合它們的解釋，去除重複部分
    3. 保留最具代表性的錯誤片語作為範例
    4. 生成一個涵蓋兩者的新標題（key_point_summary）
    
    輸出格式（JSON）：
    {
        "error_type_code": "A/B/C/D",
        "key_point_summary": "合併後的核心觀念標題（繁體中文）",
        "original_phrase": "代表性的錯誤片語",
        "correction": "正確的片語",
        "explanation": "整合後的解釋（繁體中文）",
        "severity": "major/minor"
    }
    """
    
    user_prompt = f"""
    請將以下兩個英文錯誤分析合併成一個：
    
    錯誤分析 1：
    - 分類：{error1.get('error_type_code', 'N/A')}
    - 標題：{error1.get('key_point_summary', 'N/A')}
    - 錯誤片語："{error1.get('original_phrase', 'N/A')}"
    - 正確片語："{error1.get('correction', 'N/A')}"
    - 解釋：{error1.get('explanation', 'N/A')}
    - 嚴重程度：{error1.get('severity', 'N/A')}
    
    錯誤分析 2：
    - 分類：{error2.get('error_type_code', 'N/A')}
    - 標題：{error2.get('key_point_summary', 'N/A')}
    - 錯誤片語："{error2.get('original_phrase', 'N/A')}"
    - 正確片語："{error2.get('correction', 'N/A')}"
    - 解釋：{error2.get('explanation', 'N/A')}
    - 嚴重程度：{error2.get('severity', 'N/A')}
    
    請分析這兩個錯誤的關聯性，並智慧地合併成一個更有價值的知識點。
    """
    
    try:
        merged_data = _call_llm_api(system_prompt, user_prompt, None, DEFAULT_GENERATION_MODEL)
        
        if MONITOR_MODE:
            print("\n" + "="*20 + " AI 合併結果 " + "="*20)
            print(json.dumps(merged_data, ensure_ascii=False, indent=2))
            print("="*50 + "\n")
        
        return merged_data
        
    except Exception as e:
        print(f"AI 合併錯誤分析時發生錯誤: {e}")
        return {
            "error_type_code": error1.get('error_type_code', 'A'),
            "key_point_summary": f"{error1.get('key_point_summary', '')} / {error2.get('key_point_summary', '')}",
            "original_phrase": error1.get('original_phrase', ''),
            "correction": error1.get('correction', ''),
            "explanation": f"{error1.get('explanation', '')} 另外，{error2.get('explanation', '')}",
            "severity": "major" if error1.get('severity') == 'major' or error2.get('severity') == 'major' else "minor"
        }

def ai_review_knowledge_point(knowledge_point_data, model_name=None):
    """
    AI 重新審閱知識點，提供改進建議。
    
    Args:
        knowledge_point_data (dict): 知識點的完整資料
        model_name (str): 使用的模型名稱
    
    Returns:
        dict: AI 審閱結果
    """
    
    system_prompt = """
    你是一位專業的英語教學專家和知識管理顧問。
    你的任務是仔細審閱一個英文學習知識點，並提供建設性的改進建議。
    
    審閱重點：
    1. 知識點的準確性和完整性
    2. 解釋的清晰度和教學效果
    3. 錯誤分類是否合適
    4. 是否有遺漏的重要資訊
    5. 學習者可能的困惑點
    
    請提供具體、實用的改進建議，並評估這個知識點的整體品質。
    
    輸出格式（JSON）：
    {
        "overall_assessment": "整體評估（繁體中文）",
        "accuracy_score": 1-10,
        "clarity_score": 1-10,
        "teaching_effectiveness": 1-10,
        "improvement_suggestions": [
            "建議1（繁體中文）",
            "建議2（繁體中文）"
        ],
        "potential_confusions": [
            "可能的困惑點1（繁體中文）",
            "可能的困惑點2（繁體中文）"
        ],
        "recommended_category": "建議的錯誤分類（如果需要更改）",
        "additional_examples": [
            "額外的例句1",
            "額外的例句2"
        ]
    }
    """
    
    user_prompt = f"""
    請審閱以下英文學習知識點：
    
    【知識點資料】
    - 分類：{knowledge_point_data.get('category', 'N/A')}
    - 子分類：{knowledge_point_data.get('subcategory', 'N/A')}
    - 核心觀念：{knowledge_point_data.get('key_point_summary', 'N/A')}
    - 正確用法：{knowledge_point_data.get('correct_phrase', 'N/A')}
    - 錯誤用法：{knowledge_point_data.get('incorrect_phrase_in_context', 'N/A')}
    - 解釋：{knowledge_point_data.get('explanation', 'N/A')}
    - 學習者原句：{knowledge_point_data.get('user_context_sentence', 'N/A')}
    - 熟練度：{knowledge_point_data.get('mastery_level', 0)}/5.0
    - 錯誤次數：{knowledge_point_data.get('mistake_count', 0)}
    - 答對次數：{knowledge_point_data.get('correct_count', 0)}
    
    請提供詳細的審閱報告和改進建議。
    """
    
    try:
        review_result = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        if MONITOR_MODE:
            print("\n" + "="*20 + " AI 審閱結果 " + "="*20)
            print(json.dumps(review_result, ensure_ascii=False, indent=2))
            print("="*50 + "\n")
        
        return review_result
        
    except Exception as e:
        print(f"AI 審閱知識點時發生錯誤: {e}")
        return {
            "overall_assessment": f"AI 審閱過程中發生錯誤：{str(e)}",
            "accuracy_score": 5,
            "clarity_score": 5,
            "teaching_effectiveness": 5,
            "improvement_suggestions": ["請稍後再試或聯絡系統管理員"],
            "potential_confusions": ["系統暫時無法提供分析"],
            "recommended_category": knowledge_point_data.get('category', 'N/A'),
            "additional_examples": []
        }
    

def generate_daily_learning_summary(date_str, daily_details, learning_events, model_name=None):
    """
    使用AI生成指定日期的個人化學習總結。
    
    Args:
        date_str (str): 日期字符串 (YYYY-MM-DD)
        daily_details (dict): 當日學習統計數據
        learning_events (list): 當日詳細學習事件列表
        model_name (str): 使用的AI模型名稱
    
    Returns:
        dict: 包含AI總結的完整數據
    """
    
    if not learning_events:
        return {
            "summary": "今天沒有學習紀錄。明天是新的開始，一起加油吧！",
            "key_achievements": [],
            "improvement_suggestions": ["開始您的第一道翻譯練習"],
            "motivational_message": "每一次學習都是進步的開始。"
        }
    
    # 準備學習數據摘要
    total_questions = len(learning_events)
    correct_questions = len([e for e in learning_events if e.get('is_correct')])
    accuracy_rate = (correct_questions / total_questions * 100) if total_questions > 0 else 0
    
    # 分析錯誤模式
    error_patterns = {}
    common_mistakes = []
    
    for event in learning_events:
        if event.get('ai_feedback') and event['ai_feedback'].get('error_analysis'):
            for error in event['ai_feedback']['error_analysis']:
                error_type = error.get('error_type_code', 'Unknown')
                if error_type not in error_patterns:
                    error_patterns[error_type] = []
                error_patterns[error_type].append(error.get('key_point_summary', ''))
                
                if error.get('severity') == 'major':
                    common_mistakes.append(error.get('key_point_summary', ''))
    
    # 準備給AI的提示
    system_prompt = """
    你是一位專業的英語學習顧問和教學專家。
    你的任務是為學習者生成一份個人化、溫暖且具有建設性的每日學習總結。
    
    總結要求：
    1. 語氣溫暖鼓勵，就像一位關心學生的老師
    2. 重點關注進步和亮點，即使成績不理想也要找到正面的地方
    3. 提供具體、實用的改進建議
    4. 使用繁體中文
    5. 保持專業性的同時要有人文關懷
    
    輸出格式（JSON）：
    {
        "summary": "整體學習情況的溫暖總結（150-200字）",
        "key_achievements": ["今日亮點1", "今日亮點2", "今日亮點3"],
        "improvement_suggestions": ["具體建議1", "具體建議2", "具體建議3"],
        "motivational_message": "溫暖的激勵話語（50字內）"
    }
    """
    
    user_prompt = f"""
    請為以下學習數據生成一份溫暖的每日總結：
    
    【基本數據】
    日期：{date_str}
    練習題數：{total_questions} 題
    答對題數：{correct_questions} 題
    正確率：{accuracy_rate:.1f}%
    學習時長：{daily_details.get('total_learning_time_seconds', 0)} 秒
    
    【知識點掌握情況】
    複習知識點：{len(daily_details.get('reviewed_knowledge_points', []))} 個
    新學知識點：{len(daily_details.get('new_knowledge_points', []))} 個
    
    【錯誤分析】
    主要錯誤類型分布：{dict([(k, len(v)) for k, v in error_patterns.items()])}
    常見錯誤知識點：{common_mistakes[:5]}  # 只顯示前5個
    
    【學習事件概要】
    總共有 {len([e for e in learning_events if e.get('question_type') == 'review'])} 道複習題
    總共有 {len([e for e in learning_events if e.get('question_type') == 'new'])} 道新題目
    
    請基於以上數據，生成一份既專業又溫暖的學習總結，重點關注學習者的進步和成長。
    """
    
    try:
        summary_result = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        if MONITOR_MODE:
            print("\n" + "="*20 + " AI 每日總結生成結果 " + "="*20)
            print(json.dumps(summary_result, ensure_ascii=False, indent=2))
            print("="*60 + "\n")
        
        # 確保返回的數據結構正確
        if not isinstance(summary_result, dict):
            raise ValueError("AI返回的數據格式不正確")
        
        required_fields = ['summary', 'key_achievements', 'improvement_suggestions', 'motivational_message']
        for field in required_fields:
            if field not in summary_result:
                summary_result[field] = f"AI未能生成{field}內容"
        
        return summary_result
        
    except Exception as e:
        print(f"AI生成每日總結時發生錯誤: {e}")
        # 返回備用總結
        return {
            "summary": f"今天您完成了 {total_questions} 道練習，正確率為 {accuracy_rate:.1f}%。每一次的練習都是進步的積累，繼續保持這樣的學習節奏！",
            "key_achievements": [
                f"完成了 {total_questions} 道翻譯練習" if total_questions > 0 else "開始了新的學習嘗試",
                f"正確率達到 {accuracy_rate:.1f}%" if accuracy_rate > 0 else "勇於嘗試新挑戰",
                "持續投入英語學習"
            ],
            "improvement_suggestions": [
                "建議定期複習錯誤的知識點",
                "可以嘗試增加練習的多樣性",
                "保持每日學習的好習慣"
            ],
            "motivational_message": "學習是一個持續的過程，每一步都很重要。繼續加油！"
        }
    
def generate_smart_hint(chinese_sentence, user_current_input="", original_hint="", model_name=None):
    """
    生成AI智慧提示 - 根據使用者當前翻譯和題目內容提供引導性提示
    
    Args:
        chinese_sentence (str): 原始中文題目
        user_current_input (str): 使用者當前的翻譯輸入
        original_hint (str): 原始的基本提示
        model_name (str): 使用的AI模型名稱
    
    Returns:
        dict: 包含智慧提示的回應
    """
    
    system_prompt = """
    你是一位溫暖而有耐心的英語家教老師。你的專長是「引導式教學」，絕對不會直接給出答案，而是透過巧妙的提問和提示，啟發學生自己思考出正確的翻譯。

    **核心教學原則：**
    1. 🚫 絕對不能直接給出完整的英文翻譯
    2. 🚫 不能直接說出關鍵單字或片語的正確答案
    3. ✅ 要引導學生思考句子結構和語法重點
    4. ✅ 要針對學生當前的翻譯內容給出有針對性的建議
    5. ✅ 要用溫暖鼓勵的語氣，讓學生有信心繼續嘗試

    **引導技巧：**
    - 用問句引導思考：「你覺得這個句子的主詞是什麼？」
    - 提示句型結構：「這個句子可能需要用到...的句型」
    - 分段引導：「我們先處理前半句，再處理後半句」
    - 給出思考方向：「注意這裡的時態」、「考慮一下語氣」
    - 提供對比：「中文說法和英文表達習慣有什麼不同？」

    **回應格式（JSON）：**
    {
        "smart_hint": "你的智慧引導提示（繁體中文，150字內）",
        "thinking_questions": [
            "思考問題1",
            "思考問題2",
            "思考問題3"
        ],
        "encouragement": "鼓勵話語（50字內）"
    }
    """
    
    # 構建使用者情況分析
    current_input_analysis = ""
    if user_current_input.strip():
        current_input_analysis = f"""
        **學生目前的翻譯嘗試：**
        "{user_current_input}"
        
        請根據學生目前的翻譯內容，分析他們可能遇到的困難點，並針對性地提供引導。
        """
    else:
        current_input_analysis = """
        **學生狀況：**
        學生目前還沒有開始翻譯，或者翻譯欄位是空的。請提供入門級的引導，幫助他們開始思考。
        """
    
    # 基本提示分析
    original_hint_analysis = ""
    if original_hint.strip():
        original_hint_analysis = f"""
        **基本考點提示：**
        "{original_hint}"
        
        這是這道題的核心文法考點，請在不直接透露答案的前提下，引導學生理解和應用這個考點。
        """
    
    user_prompt = f"""
    請為以下翻譯練習提供智慧引導：

    **題目（中文）：**
    "{chinese_sentence}"

    {current_input_analysis}

    {original_hint_analysis}

    **你的任務：**
    作為一位專業的英語家教，請提供溫暖而有效的引導提示，幫助學生自己思考出正確的翻譯方向。記住，絕對不要直接給出答案，而是要啟發學生的思考過程。

    請特別注意：
    - 如果學生已有翻譯內容，要針對他們的嘗試給出具體的改進方向
    - 如果學生還沒開始，要提供入門的思考框架
    - 語氣要溫暖鼓勵，讓學生感受到老師的耐心和關懷
    """
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        if MONITOR_MODE:
            print("\n" + "="*20 + " AI 智慧提示生成結果 " + "="*20)
            print(json.dumps(response_data, ensure_ascii=False, indent=2))
            print("="*60 + "\n")
        
        # 確保回應格式正確
        if not isinstance(response_data, dict):
            raise ValueError("AI返回的格式不正確")
        
        required_fields = ['smart_hint', 'thinking_questions', 'encouragement']
        for field in required_fields:
            if field not in response_data:
                response_data[field] = "AI生成內容不完整"
        
        # 確保 thinking_questions 是列表
        if not isinstance(response_data['thinking_questions'], list):
            response_data['thinking_questions'] = ["請嘗試分析句子結構", "考慮一下時態和語態", "注意中英文表達的差異"]
        
        return response_data
        
    except Exception as e:
        print(f"AI生成智慧提示時發生錯誤: {e}")
        # 回傳備用提示
        return {
            "smart_hint": "讓我們一步步來分析這個句子吧！首先，你能找出這個句子的主詞和動詞嗎？然後思考一下這個句子的時態和語氣。",
            "thinking_questions": [
                "這個句子的主詞是什麼？",
                "動詞用什麼時態比較合適？",
                "有沒有需要注意的特殊句型？"
            ],
            "encouragement": "慢慢來，每一次思考都是進步！"
        }
    
def generate_vocabulary_definition(word, context=None, model_name=None):
    """使用LLM為單字生成完整的學習資訊"""
    
    system_prompt = f"""
    你是專業的英語詞典編輯和語言學習專家，請為單字 "{word}" 提供準確且適合台灣學習者的完整學習資訊。

    回傳格式要求：
    你的回覆「必須」是一個 JSON 物件，包含以下欄位：
    
    {{
        "word": "{word}",
        "pronunciation_ipa": "國際音標（IPA格式）",
        "part_of_speech": "詞性（名詞/動詞/形容詞等）",
        "definition_zh": "清晰的繁體中文定義，適合台灣學習者理解",
        "definition_en": "簡潔的英文定義",
        "difficulty_level": 1-5的整數（1=國中程度，5=高階學術），
        "word_frequency_rank": 估計的詞頻排名（1-10000），
        "example_sentences": [
            {{"en": "實用的英文例句", "zh": "對應的中文翻譯"}},
            {{"en": "另一個例句", "zh": "中文翻譯"}}
        ],
        "word_family": ["相關的詞彙變化"],
        "common_collocations": ["常用的搭配詞組"],
        "synonyms": ["同義詞"],
        "antonyms": ["反義詞"]
    }}
    
    注意事項：
    1. 音標使用標準IPA格式
    2. 中文定義要準確且容易理解
    3. 例句要實用且不要太複雜
    4. 難度評估要考慮台灣學習者的程度
    """
    
    user_prompt = f"請為單字 '{word}' 生成完整的學習資料。"
    if context:
        user_prompt += f"\n\n語境參考：{context}\n請特別考慮這個語境中的用法。"
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        if MONITOR_MODE:
            print("\n" + "="*20 + " 單字定義生成結果 " + "="*20)
            print(json.dumps(response_data, ensure_ascii=False, indent=2))
            print("="*60 + "\n")
        
        # 驗證必要欄位
        required_fields = ['word', 'definition_zh', 'part_of_speech']
        for field in required_fields:
            if field not in response_data:
                raise ValueError(f"AI回應缺少必要欄位：{field}")
        
        # 設定預設值
        response_data.setdefault('difficulty_level', 3)
        response_data.setdefault('word_frequency_rank', 5000)
        response_data.setdefault('example_sentences', [])
        response_data.setdefault('word_family', [])
        response_data.setdefault('common_collocations', [])
        response_data.setdefault('synonyms', [])
        response_data.setdefault('antonyms', [])
        
        return response_data
        
    except Exception as e:
        print(f"AI生成單字定義時發生錯誤: {e}")
        # 回傳基本的備用資料
        return {
            "word": word,
            "pronunciation_ipa": "/wɜːrd/",
            "part_of_speech": "unknown",
            "definition_zh": f"單字 '{word}' 的定義（AI生成失敗）",
            "definition_en": f"Definition of '{word}' (AI generation failed)",
            "difficulty_level": 3,
            "word_frequency_rank": 5000,
            "example_sentences": [],
            "word_family": [],
            "common_collocations": [],
            "synonyms": [],
            "antonyms": []
        }

def generate_vocabulary_quiz_options(target_word, correct_definition, question_type="multiple_choice", model_name=None):
    """為單字測驗生成選擇題選項"""
    
    system_prompt = f"""
    你是專業的英語測驗題目設計師，需要為單字 "{target_word}" 的測驗生成高品質的干擾選項。
    
    設計原則：
    1. 干擾選項要有一定的迷惑性，但不能完全不合理
    2. 選項應該是相似程度的詞彙或概念
    3. 避免過於明顯的錯誤答案
    4. 考慮台灣學習者容易混淆的地方
    
    回傳格式：
    {{
        "question_text": "請選擇 '{target_word}' 的正確中文意思",
        "correct_answer": "{correct_definition}",
        "wrong_options": [
            "干擾選項1",
            "干擾選項2", 
            "干擾選項3"
        ],
        "explanation": "為什麼正確答案是對的，以及干擾選項為什麼錯誤的簡短說明"
    }}
    """
    
    user_prompt = f"""
    目標單字：{target_word}
    正確定義：{correct_definition}
    題目類型：{question_type}
    
    請生成3個合適的干擾選項，讓這道題目有適當的鑑別度。
    """
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        if MONITOR_MODE:
            print("\n" + "="*20 + " 單字測驗選項生成結果 " + "="*20)
            print(json.dumps(response_data, ensure_ascii=False, indent=2))
            print("="*60 + "\n")
        
        # 驗證格式
        if not isinstance(response_data.get('wrong_options'), list) or len(response_data['wrong_options']) != 3:
            raise ValueError("干擾選項格式不正確")
        
        return response_data
        
    except Exception as e:
        print(f"AI生成測驗選項時發生錯誤: {e}")
        # 回傳基本的備用選項
        return {
            "question_text": f"請選擇 '{target_word}' 的正確中文意思",
            "correct_answer": correct_definition,
            "wrong_options": [
                "選項A（AI生成失敗）",
                "選項B（AI生成失敗）", 
                "選項C（AI生成失敗）"
            ],
            "explanation": "測驗選項生成失敗，請手動檢查。"
        }

def analyze_word_difficulty(word, user_level="intermediate", model_name=None):
    """AI分析單字難度等級"""
    
    system_prompt = f"""
    你是英語教學專家，請根據以下標準為英文單字評估難度等級（1-5）：
    
    難度分級標準：
    1級：國中基礎詞彙 (cat, run, happy, book)
    2級：高中常用詞彙 (environment, successful, describe)  
    3級：大學入學詞彙 (sophisticated, analyze, comprehensive)
    4級：高階學術詞彙 (methodology, paradigm, correlation)
    5級：專業/罕見詞彙 (ubiquitous, ephemeral, serendipity)
    
    評估考量因素：
    - 詞彙在日常生活中的使用頻率
    - 音節複雜度和拼寫難度
    - 詞根詞綴的複雜程度
    - 語義的抽象程度
    - 在台灣英語教育中的出現時機
    
    使用者程度參考：{user_level}
    
    回傳格式：
    {{
        "difficulty_level": 1-5的整數,
        "frequency_estimate": 1-10000的詞頻估計排名,
        "reasoning": "難度評估的理由說明",
        "learning_tips": "學習這個單字的建議方法"
    }}
    """
    
    user_prompt = f"請評估單字 '{word}' 的難度等級和學習建議。"
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        # 確保難度等級在有效範圍內
        difficulty = response_data.get('difficulty_level', 3)
        if not isinstance(difficulty, int) or difficulty < 1 or difficulty > 5:
            difficulty = 3
        
        frequency = response_data.get('frequency_estimate', 5000)
        if not isinstance(frequency, int) or frequency < 1:
            frequency = 5000
        
        return {
            'difficulty_level': difficulty,
            'frequency_estimate': frequency,
            'reasoning': response_data.get('reasoning', '難度分析處理中'),
            'learning_tips': response_data.get('learning_tips', '建議多練習使用')
        }
        
    except Exception as e:
        print(f"AI分析單字難度時發生錯誤: {e}")
        return {
            'difficulty_level': 3,
            'frequency_estimate': 5000,
            'reasoning': 'AI分析失敗，使用預設值',
            'learning_tips': '建議查閱字典並多加練習'
        }

def extract_vocabulary_from_translation_error(knowledge_point_data, model_name=None):
    """從翻譯錯誤中智慧提取應該學習的單字"""
    
    system_prompt = """
    你是英語學習分析專家，需要從學生的翻譯錯誤中提取出「真正值得學習的核心單字」。
    
    分析原則：
    1. 專注於「詞彙類錯誤」，忽略純語法錯誤
    2. 提取學生不熟悉或用錯的「關鍵單字」
    3. 優先考慮實用性高的詞彙
    4. 避免過於基礎或過於冷僻的單字
    
    回傳格式：
    {{
        "extracted_words": [
            {{
                "word": "目標單字",
                "reason": "為什麼這個單字值得學習",
                "difficulty_estimate": 1-5,
                "priority": "high/medium/low"
            }}
        ],
        "analysis_summary": "整體分析說明"
    }}
    
    如果沒有找到合適的單字，回傳空陣列。
    """
    
    user_prompt = f"""
    請分析以下翻譯錯誤，提取值得學習的單字：
    
    錯誤分類：{knowledge_point_data.get('category', '未知')}
    錯誤子分類：{knowledge_point_data.get('subcategory', '未知')}
    正確表達：{knowledge_point_data.get('correct_phrase', '未知')}
    學生原句：{knowledge_point_data.get('user_context_sentence', '未知')}
    錯誤片段：{knowledge_point_data.get('incorrect_phrase_in_context', '未知')}
    
    請從中提取應該加入單字庫的詞彙。
    """
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        if MONITOR_MODE:
            print("\n" + "="*20 + " 翻譯錯誤單字提取結果 " + "="*20)
            print(json.dumps(response_data, ensure_ascii=False, indent=2))
            print("="*60 + "\n")
        
        extracted_words = response_data.get('extracted_words', [])
        
        # 過濾和驗證提取的單字
        valid_words = []
        for word_info in extracted_words:
            if isinstance(word_info, dict) and 'word' in word_info:
                # 基本的單字驗證（只包含字母）
                word = word_info['word'].strip().lower()
                if word.isalpha() and len(word) > 1:
                    valid_words.append({
                        'word': word,
                        'reason': word_info.get('reason', '翻譯錯誤中發現'),
                        'difficulty_estimate': word_info.get('difficulty_estimate', 3),
                        'priority': word_info.get('priority', 'medium')
                    })
        
        return {
            'extracted_words': valid_words,
            'analysis_summary': response_data.get('analysis_summary', '分析完成')
        }
        
    except Exception as e:
        print(f"AI提取翻譯錯誤單字時發生錯誤: {e}")
        return {
            'extracted_words': [],
            'analysis_summary': '提取失敗，請手動檢查'
        }

def generate_context_fill_question(word, difficulty_level=3, model_name=None):
    """為指定單字生成語境填空題"""
    
    system_prompt = f"""
    你是英語測驗設計專家，需要為單字 "{word}" 設計一道語境填空題。
    
    設計要求：
    1. 創造一個自然的英文句子，其中包含目標單字
    2. 句子要有足夠的語境線索，但不能過於明顯
    3. 難度等級：{difficulty_level}/5
    4. 句子長度適中，適合台灣學習者
    
    回傳格式：
    {{
        "question_sentence": "包含空格_____的句子",
        "complete_sentence": "完整的句子",
        "target_word": "{word}",
        "context_hints": ["語境提示1", "語境提示2"],
        "difficulty_level": {difficulty_level}
    }}
    """
    
    user_prompt = f"請為單字 '{word}' 設計一道語境填空題，難度等級為 {difficulty_level}。"
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        
        # 驗證必要欄位
        if 'question_sentence' not in response_data or 'complete_sentence' not in response_data:
            raise ValueError("語境填空題格式不完整")
        
        return response_data
        
    except Exception as e:
        print(f"AI生成語境填空題時發生錯誤: {e}")
        return {
            "question_sentence": f"The _____ was very important in this situation.",
            "complete_sentence": f"The {word} was very important in this situation.",
            "target_word": word,
            "context_hints": ["根據語境判斷"],
            "difficulty_level": difficulty_level
        }

def batch_enhance_vocabulary_definitions(word_list, model_name=None):
    """批次增強單字定義（用於改善現有單字庫）"""
    
    system_prompt = """
    你是專業的詞典編輯，需要批次處理多個英文單字，為每個單字提供增強的學習資訊。
    
    對於每個單字，請提供：
    1. 更準確的中文定義
    2. 實用的例句
    3. 常用搭配
    
    回傳格式：
    {{
        "enhanced_definitions": [
            {{
                "word": "單字",
                "improved_definition_zh": "改善的中文定義",
                "example_sentences": [
                    {{"en": "英文例句", "zh": "中文翻譯"}}
                ],
                "collocations": ["常用搭配"]
            }}
        ]
    }}
    """
    
    word_list_str = ", ".join(word_list)
    user_prompt = f"請為以下單字提供增強的定義和學習資訊：{word_list_str}"
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        return response_data.get('enhanced_definitions', [])
        
    except Exception as e:
        print(f"AI批次增強單字定義時發生錯誤: {e}")
        return []

# 字典API整合功能

def fetch_cambridge_definition(word):
    """調用劍橋字典API（或備用免費API）"""
    try:
        import requests
    except ImportError:
        print("警告: requests 套件未安裝，字典API功能將無法使用")
        return None
    
    # 首先嘗試免費的字典API（因為劍橋字典API需要付費）
    try:
        free_api_url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(free_api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                entry = data[0]
                
                # 提取資訊
                pronunciation = ""
                if 'phonetics' in entry:
                    for phonetic in entry['phonetics']:
                        if 'text' in phonetic:
                            pronunciation = phonetic['text']
                            break
                
                definitions = []
                examples = []
                part_of_speech = ""
                
                if 'meanings' in entry:
                    for meaning in entry['meanings']:
                        if not part_of_speech:
                            part_of_speech = meaning.get('partOfSpeech', '')
                        
                        for definition in meaning.get('definitions', []):
                            definitions.append(definition.get('definition', ''))
                            if 'example' in definition:
                                examples.append(definition['example'])
                
                return {
                    'word': word,
                    'pronunciation_ipa': pronunciation,
                    'part_of_speech': part_of_speech,
                    'definition_en': '; '.join(definitions[:2]),  # 取前兩個定義
                    'examples': examples[:2],  # 取前兩個例句
                    'source': 'free_dictionary_api'
                }
    
    except Exception as e:
        print(f"字典API查詢失敗: {e}")
    
    # 如果API失敗，回傳None，讓系統使用LLM生成
    return None

def smart_add_vocabulary_word(word, context=None, source_type='manual', source_reference_id=None):
    """智慧新增單字：結合字典API和LLM"""
    
    print(f"正在智慧分析單字: {word}")
    
    # 1. 首先嘗試字典API
    dict_data = fetch_cambridge_definition(word)
    
    # 2. 使用LLM生成完整定義（包含中文）
    llm_data = generate_vocabulary_definition(word, context)
    
    # 3. 合併最佳資訊
    final_data = {
        'word': word.lower().strip(),
        'source_type': source_type,
        'source_reference_id': source_reference_id,
        'added_context': context
    }
    
    if dict_data:
        # 優先使用字典API的音標和英文定義
        final_data.update({
            'pronunciation_ipa': dict_data.get('pronunciation_ipa') or llm_data.get('pronunciation_ipa'),
            'part_of_speech': dict_data.get('part_of_speech') or llm_data.get('part_of_speech'),
            'definition_en': dict_data.get('definition_en') or llm_data.get('definition_en'),
            'definition_zh': llm_data.get('definition_zh'),  # LLM的中文定義
            'difficulty_level': llm_data.get('difficulty_level', 3),
            'word_frequency_rank': llm_data.get('word_frequency_rank', 5000)
        })
        
        # 合併例句
        dict_examples = [{'sentence_en': ex, 'source': 'dictionary'} for ex in dict_data.get('examples', [])]
        llm_examples = [{'sentence_en': ex['en'], 'sentence_zh': ex.get('zh'), 'source': 'llm'} 
                       for ex in llm_data.get('example_sentences', [])]
        final_data['examples'] = dict_examples + llm_examples
        
    else:
        # 完全使用LLM資料
        final_data.update({
            'pronunciation_ipa': llm_data.get('pronunciation_ipa'),
            'part_of_speech': llm_data.get('part_of_speech'),
            'definition_en': llm_data.get('definition_en'),
            'definition_zh': llm_data.get('definition_zh'),
            'difficulty_level': llm_data.get('difficulty_level', 3),
            'word_frequency_rank': llm_data.get('word_frequency_rank', 5000),
            'examples': [{'sentence_en': ex['en'], 'sentence_zh': ex.get('zh'), 'source': 'llm'} 
                        for ex in llm_data.get('example_sentences', [])]
        })
    
    return final_data