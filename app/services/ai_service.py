# ai-tutor/app/services/ai_service.py

import os
import json
import random
import openai
import google.generativeai as genai
from app.assets import EXAMPLE_SENTENCE_BANK

MONITOR_MODE = True

# --- 模型設定與 API 初始化 (此部分不變) ---

AVAILABLE_MODELS = {
    "gpt-4o": "openai/gpt-4o",
    "gpt-4-turbo": "openai/gpt-4-turbo",
    "gemini-2.5-pro": "gemini/gemini-1.5-pro-latest",
    "gemini-2.5-flash": "gemini/gemini-1.5-flash-latest",
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

# --- 【計畫二修改】讀取新的 JSON 文法庫 ---
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


# --- 私有函式 (此部分不變) ---

def _call_openai_api(system_prompt, user_prompt, model_id):
    if not openai_client:
        raise ValueError("OpenAI API 金鑰未設定或客戶端初始化失敗。")
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

def _call_gemini_api(system_prompt, user_prompt, model_id):
    if not gemini_api_key:
        raise ValueError("Gemini API 金鑰未設定或模型初始化失敗。")
    gemini_model = genai.GenerativeModel(model_id, generation_config=gemini_generation_config)
    full_prompt = system_prompt + "\n\n" + user_prompt
    if MONITOR_MODE:
        print("\n" + "="*20 + f" Gemini API INPUT (Model: {model_id}) " + "="*20)
        print(full_prompt)
        print("="*60 + "\n")
    response = gemini_model.generate_content(full_prompt)
    return json.loads(response.text)

def _call_llm_api(system_prompt, user_prompt, model_name, default_model):
    model_name = model_name or default_model
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
    """根據弱點生成複習題 (此函式不變)。"""
    system_prompt = f"""
        你是一位頂尖的英文教學專家與命題者，專門設計「精準打擊」的複習題。你的核心任務是根據下方一份關於學生的「具體知識點弱點報告」，為他量身打造 {num_review} 題翻譯考題。
        **核心原則**: 1. 精準打擊 2. 情境創造 3. 絕對保密
        **輸出格式**: 你必須嚴格回傳一個 JSON 物件。根部有一個 "questions" key，其 value 是一個包含 {num_review} 個問題物件的列表。
        每個問題物件必須包含 "new_sentence" (string) 和 "hint_text" (string)。
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

# --- 【計畫二修改】重寫生成新題的函式 ---
def generate_new_question_batch(num_new, difficulty, length, model_name=None):
    """
    【vNext 版】根據結構化的文法庫，為每個句型精準生成一個新題目。
    """
    if not grammar_patterns:
        print("錯誤：文法庫為空或載入失敗，無法生成新題目。")
        return []

    # 1. 從文法庫中隨機選取 num_new 個不重複的句型
    try:
        selected_patterns = random.sample(grammar_patterns, k=min(num_new, len(grammar_patterns)))
    except ValueError:
        return [] # 如果請求的數量大於庫中的數量，返回空

    generated_questions = []

    # 2. 針對每一個選中的句型，單獨呼叫 AI 生成一題
    for i, pattern_data in enumerate(selected_patterns):
        print(f"\n[AI Service] 正在為第 {i+1}/{len(selected_patterns)} 個新句型出題...")
        print(f"  - 目標句型: {pattern_data.get('pattern', 'N/A')}")

        # 準備範例句子，增加 AI 模仿的精準度
        example_sentences = EXAMPLE_SENTENCE_BANK.get(length, {}).get(str(difficulty), [])
        example_sentences_str = "\n".join([f"- {s}" for s in example_sentences]) if example_sentences else "無風格參考範例"

        # 3. 建立一個高度聚焦的 Prompt
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

        範例輸出:
        {{
            "new_sentence": "如果我有足夠的錢，我就會買下那棟房子。",
            "hint_text": "If + S + had + ..., S + would + V..."
        }}
        """
        user_prompt = "請嚴格遵照你的三項核心指令，為我生成一題考題的 JSON 物件。"

        # 4. 呼叫 LLM API
        try:
            # 注意：這裡的 API 呼叫回傳的是單一物件，而不是列表
            response_data = _call_llm_api(system_prompt, user_prompt, model_name, DEFAULT_GENERATION_MODEL)
            
            # 驗證回傳的資料是否符合預期
            if isinstance(response_data, dict) and 'new_sentence' in response_data and 'hint_text' in response_data:
                # 確保 hint_text 是我們指定的句型
                response_data['hint_text'] = pattern_data.get('pattern', response_data['hint_text'])
                generated_questions.append(response_data)
                print(f"  - 成功生成題目: \"{response_data['new_sentence']}\"")
            else:
                print(f"  - 警告：AI 回傳格式不符，已跳過此題。收到的資料: {response_data}")

        except Exception as e:
            print(f"為句型 '{pattern_data.get('pattern')}' 生成題目時發生錯誤: {e}")
            # 單一題目生成失敗，不影響其他題目，繼續循環
            continue

    return generated_questions


def get_tutor_feedback(chinese_sentence, user_translation, review_context=None, hint_text=None, model_name=None):
    """批改使用者答案並提供回饋 (此函式不變)。"""
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