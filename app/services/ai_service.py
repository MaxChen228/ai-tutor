# app/services/ai_service.py

import os
import json
import random
import openai
import google.generativeai as genai
from app.assets import EXAMPLE_SENTENCE_BANK

MONITOR_MODE = True

# --- 模型設定與 API 初始化 ---

# 【vNext 新增】模型註冊表
# 我們把所有支援的模型統一定義在這裡
# Key 是給前端顯示和選擇的，Value 是對應的 API model ID
AVAILABLE_MODELS = {
    # OpenAI Models
    "gpt-4o": "openai/gpt-4o",
    "gpt-4-turbo": "openai/gpt-4-turbo",
    # Gemini Models
    "gemini-2.5-pro": "gemini/gemini-1.5-pro-latest", # Gemini 在 API 中通常用 1.5
    "gemini-2.5-flash": "gemini/gemini-1.5-flash-latest",
}
DEFAULT_GENERATION_MODEL = "gemini-2.5-pro"
DEFAULT_GRADING_MODEL = "gemini-2.5-flash"


# OpenAI 初始化
try:
    openai_client = openai.OpenAI() if os.environ.get("OPENAI_API_KEY") else None
except openai.OpenAIError:
    openai_client = None
    print("警告: OPENAI_API_KEY 未設定或無效。")

# Gemini 初始化
try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        genai.configure(api_key=gemini_api_key)
        # 移除固定的 model name，讓呼叫時動態決定
        # 設定 generation_config 以確保回傳的是 JSON
        gemini_generation_config = genai.GenerationConfig(response_mime_type="application/json")
    else:
        gemini_api_key = None
        print("警告: GEMINI_API_KEY 未設定。")
except Exception as e:
    gemini_api_key = None
    print(f"初始化 Gemini 時發生錯誤: {e}")

# --- 文法書讀取 ---
try:
    with open("翻譯句型.md", "r", encoding="utf-8") as f:
        translation_patterns = f.read()
except FileNotFoundError:
    print("錯誤：找不到 `翻譯句型.md` 檔案。")
    translation_patterns = "（文法書讀取失敗）"

# --- 私有函式：各模型的具體實現 ---

def _call_openai_api(system_prompt, user_prompt, model_id):
    """通用的 OpenAI API 呼叫函式。"""
    if not openai_client:
        raise ValueError("OpenAI API 金鑰未設定或客戶端初始化失敗。")
    
    if MONITOR_MODE:
        print("\n" + "="*20 + f" OpenAI API INPUT (Model: {model_id}) " + "="*20)
        print("--- SYSTEM PROMPT ---\n" + system_prompt)
        print("\n--- USER PROMPT ---\n" + user_prompt)
        print("="*60 + "\n")

    response = openai_client.chat.completions.create(
        model=model_id, # 使用傳入的 model_id
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def _call_gemini_api(system_prompt, user_prompt, model_id):
    """通用的 Gemini API 呼叫函式。"""
    if not gemini_api_key:
        raise ValueError("Gemini API 金鑰未設定或模型初始化失敗。")
    
    # 根據 model_id 動態建立模型實例
    gemini_model = genai.GenerativeModel(
        model_id,
        generation_config=gemini_generation_config
    )
    
    full_prompt = system_prompt + "\n\n" + user_prompt

    if MONITOR_MODE:
        print("\n" + "="*20 + f" Gemini API INPUT (Model: {model_id}) " + "="*20)
        print(full_prompt)
        print("="*60 + "\n")
        
    response = gemini_model.generate_content(full_prompt)
    return json.loads(response.text)

def _call_llm_api(system_prompt, user_prompt, model_name, default_model):
    """【vNext 新增】統一的 LLM 呼叫函式 (Dispatcher)。"""
    
    # 如果沒有提供 model_name，就使用預設值
    model_name = model_name or default_model
    
    # 從註冊表中找到對應的 provider 和 model_id
    full_model_id = AVAILABLE_MODELS.get(model_name)
    
    if not full_model_id:
        print(f"警告：找不到名為 '{model_name}' 的模型，將使用預設模型 '{default_model}'。")
        full_model_id = AVAILABLE_MODELS[default_model]
        
    provider, model_id = full_model_id.split('/', 1)
    
    print(f"[AI Service] 正在使用模型: Provider={provider}, Model ID={model_id}")

    if provider == 'gemini':
        return _call_gemini_api(system_prompt, user_prompt, model_id)
    elif provider == 'openai':
        return _call_openai_api(system_prompt, user_prompt, model_id)
    else:
        raise ValueError(f"不支援的 LLM 供應商: {provider}")


def _normalize_questions_output(response_data):
    """將不同模型的輸出格式統一為問題列表。"""
    if isinstance(response_data, dict) and "questions" in response_data and isinstance(response_data["questions"], list):
        return response_data["questions"]
    elif isinstance(response_data, list):
         return response_data
    elif isinstance(response_data, dict):
        for value in response_data.values():
            if isinstance(value, list):
                return value
    return []

# --- 公共函式：供外部呼叫的統一介面 ---

def generate_question_batch(weak_points_str, num_review, model_name=None):
    """根據弱點生成複習題。"""
    system_prompt = f"""
        你是一位頂尖的英文教學專家與命題者，專門設計「精準打擊」的複習題。你的核心任務是根據下方一份關於學生的「具體知識點弱點報告」，為他量身打造 {num_review} 題翻譯考題。
        **核心原則**: 1. 精準打擊 2. 情境創造 3. 絕對保密
        **輸出格式**: 你必須嚴格回傳一個 JSON 物件。根部有一個 "questions" key，其 value 是一個包含 {num_review} 個問題物件的列表。
        每個問題物件必須包含 "new_sentence" (string) 和 "hint_text" (string)。
        範例: {{"questions": [{{"new_sentence": "這份工作薪水很高，但另一方面...", "hint_text": "on the other hand"}}]}}
        """
    user_prompt = f"""
        **【學生具體知識點弱點報告】**
        {weak_points_str}
        ---
        請根據以上報告，為我生成 {num_review} 題翻譯題。請務必記得，你的輸出必須是包含 "questions" key 的 JSON 格式。
        """
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        return _normalize_questions_output(response_data)
    except Exception as e:
        print(f"AI 備課時發生錯誤 (複習題) - Model: {model_name}, Error: {e}")
        return None

def generate_new_question_batch(num_new, difficulty, length, model_name=None):
    """生成全新挑戰題。"""
    patterns_list = [p.strip() for p in translation_patterns.split('* ') if p.strip()]
    sampled_patterns_str = "* " + "\n* ".join(random.sample(patterns_list, min(len(patterns_list), 15))) if patterns_list else "無"
    
    example_sentences = EXAMPLE_SENTENCE_BANK.get(length, {}).get(str(difficulty), [])
    example_sentences_str = "\n".join([f"- {s}" for s in example_sentences]) if example_sentences else "無範例"

    system_prompt = f"""
    你是一位超級高效的英文命題 AI，任務是為我生成 {num_new} 題翻譯考題。
    **指令一：模仿風格**
    你必須深度學習下方的「風格參考範例 (來自難度 {difficulty} / 長度 {length})」，你的出題風格必須與其一致。
    ---
    【風格參考範例】
    {example_sentences_str}
    ---
    **指令二：運用句型**
    你必須從下方的「指定句型庫」中，選擇合適的句型融入題目。
    ---
    【指定句型庫】
    {sampled_patterns_str}
    ---
    **指令三：嚴格輸出**
    你必須嚴格回傳一個 JSON 物件。根部有一個 "questions" key，其 value 是一個包含 {num_new} 個問題物件的列表。
    每個問題物件必須包含 "new_sentence" (string) 和 "hint_text" (string)。
    範例: {{"questions": [{{"new_sentence": "再怎麼強調...也不為過。", "hint_text": "再...也不為過: cannot + V + too much / adv."}}]}}
    """
    user_prompt = f"請嚴格遵照你的三項核心指令，為我生成 {num_new} 題考題。"
    
    try:
        response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
        return _normalize_questions_output(response_data)
    except Exception as e:
        print(f"AI 備課時發生錯誤 (新題) - Model: {model_name}, Error: {e}")
        return None

def get_tutor_feedback(chinese_sentence, user_translation, review_context=None, hint_text=None, model_name=None):
    """批改使用者答案並提供回饋。"""
    # ... (prompt 內容不變，此處省略) ...
    error_analysis_instructions = """
    4.  `error_analysis`: (array of objects) 一個清單，如果沒有任何錯誤，請回傳一個空清單 `[]`。
        清單中的每一個物件都必須包含以下所有欄位：
        * `key_point_summary`: (string) 【最重要的欄位】請為這個錯誤點提煉一個「錯誤焦點」。
        * `error_type`: (string) 【極重要】你「必須」從以下三個層級中選擇一個最貼切的分類：`詞彙與片語層級 (Lexical & Phrasal)`、`語法結構層級 (Grammatical & Structural)`、`語意與語用層級 (Semantic & Pragmatic)`。
        * `error_subtype`: (string) 2-5 個字的具體錯誤類型，例如：`介係詞搭配`, `時態錯誤`。
        * `original_phrase`: (string) 從學生答案中，精確地提取出錯誤的那個單字或片語。
        * `correction`: (string) 針對該錯誤片語，提供正確的寫法。
        * `explanation`: (string) 簡潔地解釋為什麼這是錯的。
        * `severity`: (string) `major` 或 `minor`。
    """
    
    if review_context:
        # 這是複習題的「目標導向」prompt
        system_prompt = f"""
        你是一位英文教學專家，正在驗收學生對核心觀念的掌握。
        **首要任務**: 判斷學生作答是否掌握了「核心複習觀念: {review_context}」，並在回傳的 JSON 中設定 `did_master_review_concept` (boolean) 的值。
        **次要任務**: 分析其他與核心觀念無關的錯誤。
        **排他性原則**: `error_analysis` 列表絕對不應包含與核心複習觀念相關的分析。
        **輸出格式**: 你的 JSON 回覆必須包含 `did_master_review_concept`(boolean), `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。
        {error_analysis_instructions}
        **原始中文句子是**: "{chinese_sentence}"
        """
    else:
        # 這是新題目的常規 prompt
        system_prompt = f"""
        你是一位細心的英文家教，請分析學生的翻譯答案。
        **核心考點提示**: 「{hint_text if hint_text else '無特定提示'}」。請特別留意此點的掌握情況。
        **輸出格式**: 你的 JSON 回覆必須包含 `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。
        {error_analysis_instructions}
        **原始中文句子是**: "{chinese_sentence}"
        """
        
    user_prompt = f"這是我的翻譯：「{user_translation}」。請根據你的專業知識和上述指令，為我生成一份鉅細靡遺的 JSON 分析報告。"

    try:
        return _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GRADING_MODEL)
    except Exception as e:
        print(f"AI 批改時發生錯誤 - Model: {model_name}, Error: {e}")
        return {
            "did_master_review_concept": False, "is_generally_correct": False, "overall_suggestion": f"AI 模型 ({model_name}) 暫時無法提供服務。",
            "error_analysis": [{"error_type": "系統錯誤", "explanation": f"系統無法處理 AI 的回覆：{e}"}]
        }