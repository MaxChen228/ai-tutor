# app/services/ai_service.py

import os
import json
import random
import openai
import google.generativeai as genai
from app.assets import EXAMPLE_SENTENCE_BANK

MONITOR_MODE = True

# --- 模型設定與 API 初始化 ---

AVAILABLE_MODELS = {
    "gpt-4o": "openai/gpt-4o",
    "gemini-2.5-pro": "gemini/gemini-2.5-pro",
    "gemini-2.5-flash": "gemini/gemini-2.5-flash",
}
DEFAULT_GENERATION_MODEL = "gemini-2.5-pro"
DEFAULT_GRADING_MODEL = "gemini-2.5-flash"

try:
    openai_client = openai.OpenAI() if os.environ.get("OPENAI_API_KEY") else None
except openai.OpenAIError:
    openai_client = None
    print("警告: OPENAI_API_KEY 未設定或無效。")

try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        genai.configure(api_key=gemini_api_key)
        gemini_generation_config = genai.GenerationConfig(response_mime_type="application/json")
    else:
        gemini_api_key = None
        print("警告: GEMINI_API_KEY 未設定。")
except Exception as e:
    gemini_api_key = None
    print(f"初始化 Gemini 時發生錯誤: {e}")

# --- 文法庫讀取 ---
try:
    # 修正路徑以符合從 run.py 執行的相對位置
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
    # 此處省略 generate_new_question_batch 的程式碼，因計畫一未修改此函式
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


# --- 【計畫一修改】重寫批改回饋函式 ---
def get_tutor_feedback(chinese_sentence, user_translation, review_context=None, hint_text=None, model_name=None):
    """
    【vNext 標準化版】批改使用者答案並提供回饋。
    - 強制中文回饋
    - 使用錯誤代碼 error_type_code
    """
    
    # 這是兩個 prompt 都會用到的共用說明，也是本次修改的重點
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
    
    # 整體建議，也要求用繁體中文
    overall_suggestion_instruction = "3.  `overall_suggestion`: (string) 在綜合考量所有錯誤後，提供一個「整體最佳」的翻譯建議。這個建議「必須」是完整的句子，且「必須」使用**繁體中文**。"

    if review_context:
        # 這是複習題的「目標導向」prompt
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
        # 這是新題目的常規 prompt
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
        # 確保錯誤回傳的格式也符合前端預期
        return {
            "did_master_review_concept": False, 
            "is_generally_correct": False, 
            "overall_suggestion": f"AI 模型 ({model_name}) 暫時無法提供服務，請稍後再試。",
            "error_analysis": [{
                "error_type_code": "E", # 'E' for Error
                "key_point_summary": "系統錯誤",
                "original_phrase": "N/A",
                "correction": "N/A",
                "explanation": f"系統無法處理 AI 的回覆：{e}",
                "severity": "major"
            }]
        }