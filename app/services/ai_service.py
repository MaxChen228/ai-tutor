# app/services/ai_service.py

import os
import json
import random
import openai
import google.generativeai as genai
from app.assets import EXAMPLE_SENTENCE_BANK

MONITOR_MODE = True

# --- 環境變數與 API 初始化 ---

LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'OPENAI').upper()
print(f"[AI Service] 目前使用的 LLM 供應商: {LLM_PROVIDER}")

# OpenAI 初始化
try:
    openai_client = openai.OpenAI() if os.environ.get("OPENAI_API_KEY") else None
except openai.OpenAIError:
    openai_client = None
    if LLM_PROVIDER == 'OPENAI':
        print("警告: LLM_PROVIDER 設定為 OPENAI，但 OPENAI_API_KEY 未設定或無效。")

# Gemini 初始化
try:
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        genai.configure(api_key=gemini_api_key)
        gemini_model = genai.GenerativeModel(
            'gemini-1.5-flash',
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json"
            )
        )
    else:
        gemini_model = None
        if LLM_PROVIDER == 'GEMINI':
            print("警告: LLM_PROVIDER 設定為 GEMINI，但 GEMINI_API_KEY 未設定。")
except Exception as e:
    gemini_model = None
    print(f"初始化 Gemini 時發生錯誤: {e}")

# --- 文法書讀取 ---
try:
    with open("翻譯句型.md", "r", encoding="utf-8") as f:
        translation_patterns = f.read()
except FileNotFoundError:
    print("錯誤：找不到 `翻譯句型.md` 檔案。")
    translation_patterns = "（文法書讀取失敗）"

# --- 私有函式：各模型的具體實現 ---

def _call_openai_api(system_prompt, user_prompt):
    """通用的 OpenAI API 呼叫函式。"""
    if not openai_client:
        raise ValueError("OpenAI API 金鑰未設定或客戶端初始化失敗。")
    
    if MONITOR_MODE:
        print("\n" + "="*20 + " OpenAI API INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---\n" + system_prompt)
        print("\n--- USER PROMPT ---\n" + user_prompt)
        print("="*60 + "\n")

    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )
    return json.loads(response.choices[0].message.content)

def _call_gemini_api(system_prompt, user_prompt):
    """通用的 Gemini API 呼叫函式。"""
    if not gemini_model:
        raise ValueError("Gemini API 金鑰未設定或模型初始化失敗。")
    
    full_prompt = system_prompt + "\n\n" + user_prompt

    if MONITOR_MODE:
        print("\n" + "="*20 + " Gemini API INPUT " + "="*20)
        print(full_prompt)
        print("="*60 + "\n")
        
    response = gemini_model.generate_content(full_prompt)
    return json.loads(response.text)

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

# --- 公共函式：供外部呼叫的統一介面 (Dispatcher) ---

def generate_question_batch(weak_points_str, num_review):
    """根據弱點生成複習題 (Dispatcher)。"""
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
        if LLM_PROVIDER == 'GEMINI':
            response_data = _call_gemini_api(system_prompt, user_prompt)
        else:
            response_data = _call_openai_api(system_prompt, user_prompt)
        return _normalize_questions_output(response_data)
    except Exception as e:
        print(f"AI 備課時發生錯誤 (複習題) - Provider: {LLM_PROVIDER}, Error: {e}")
        return None

def generate_new_question_batch(num_new, difficulty, length):
    """生成全新挑戰題 (Dispatcher)。"""
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
        if LLM_PROVIDER == 'GEMINI':
            response_data = _call_gemini_api(system_prompt, user_prompt)
        else:
            response_data = _call_openai_api(system_prompt, user_prompt)
        return _normalize_questions_output(response_data)
    except Exception as e:
        print(f"AI 備課時發生錯誤 (新題) - Provider: {LLM_PROVIDER}, Error: {e}")
        return None

def get_tutor_feedback(chinese_sentence, user_translation, review_context=None, hint_text=None):
    """批改使用者答案並提供回饋 (Dispatcher)。"""

    # 【v5.19 規則強化版】: 注入了清晰定義和豐富範例的全新 Prompt 核心
    error_analysis_instructions = """
    `error_analysis` (array of objects):
    
    **【極重要】錯誤分類的三層級定義與規範：**
    你必須嚴格遵守以下分類定義，絕不混淆。
    
    ---
    **1. `詞彙與片語層級 (Lexical & Phrasal)`**
    * **定義**: 關乎「單一詞彙」或「固定片語搭配」的錯誤。這是最小的錯誤單位。
    * **範疇**: 介係詞 (`in`, `on`, `at`), 固定搭配 (Collocations), 近義詞混淆, 拼寫錯誤。
    * **分類範例**:
        * 錯誤: "I am interested `on` it." -> 正確分類: `詞彙與片語層級` (因為 `interested in` 是固定搭配)
        * 錯誤: "He made a `speech`." (情境應為 'gave a speech') -> 正確分類: `詞彙與片語層級` (動詞搭配錯誤)
        * 錯誤: "I `recommand` this book." -> 正確分類: `詞彙與片語層級` (拼寫錯誤)

    ---
    **2. `語法結構層級 (Grammatical & Structural)`**
    * **定義**: 關乎「句子組合規則」的錯誤，即文法錯誤。錯誤單位是詞與詞之間的關係或句子結構。
    * **範疇**: 時態 (Tenses), 主謂一致 (S-V Agreement), 冠詞 (`a`, `an`, `the`), 名詞單複數, 句子結構（如倒裝、假設語氣）, 詞性誤用（如用形容詞修飾動詞）。
    * **分類範例**:
        * 錯誤: "He `go` to school." -> 正確分類: `語法結構層級` (主謂不一致)
        * 錯誤: "I `have went` there." -> 正確分類: `語法結構層級` (時態錯誤，現在完成式結構錯誤)
        * 錯誤: "This is `apple`." -> 正確分類: `語法結構層級` (冠詞缺失)
        * **【特別指令】**: 所有關於「時態」、「假設語氣」、「倒裝句」等句子級別的結構性問題，**必須**被歸類於此。

    ---
    **3. `語意與語用層級 (Semantic & Pragmatic)`**
    * **定義**: 關乎「意義表達」與「使用情境」的錯誤。句子本身文法可能正確，但在特定情境下顯得不自然、不禮貌、有歧義或冗餘。
    * **範疇**: 語氣與正式度 (Tone & Formality), 冗餘/贅字 (Redundancy), 文化慣用法, 中式英文 (Chinglish)。
    * **分類範例**:
        * 錯誤: (在商業郵件中) "Give me the report." -> 正確分類: `語意與語用層級` (語氣過於直接，不夠正式)
        * 錯誤: "The reason is `because`..." -> 正確分類: `語意與語用層級` (語意冗餘)
        * 錯誤: "You and me should go." -> 正確分類: `語意與語用層級` (語用習慣上會說 'You and I')
    ---
    
    **每個錯誤物件的欄位結構:**
    * `key_point_summary`: (string) 錯誤焦點的簡潔提示。
    * `error_type`: (string) 【必須】從上述三層級中精準選擇一個。
    * `error_subtype`: (string) 2-5 個字的具體錯誤類型，例如：`介係詞搭配`, `時態錯誤`。
    * `original_phrase`: (string) 從學生答案中提取的錯誤片段。
    * `correction`: (string) 正確的寫法。
    * `explanation`: (string) 簡潔的解釋。
    * `severity`: (string) `major` 或 `minor`。
    """
    
    if review_context:
        system_prompt = f"""
        你是一位嚴格的英文教學評審，正在驗收學生對核心觀念的掌握。
        **首要任務**: 判斷學生作答是否掌握了「核心複習觀念: {review_context}」，並在回傳的 JSON 中設定 `did_master_review_concept` (boolean) 的值。
        **次要任務**: 根據下方提供的【三層級定義與規範】，精準分析其他與核心觀念無關的新錯誤。
        **排他性原則**: `error_analysis` 列表絕對不應包含與核心複習觀念相關的分析。
        **輸出格式**: JSON 必須包含 `did_master_review_concept`(boolean), `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。
        ---
        {error_analysis_instructions}
        ---
        **原始中文句子是**: "{chinese_sentence}"
        """
    else:
        system_prompt = f"""
        你是一位極其細心且嚴格的英文家教，請根據下方提供的【三層級定義與規範】，精準分析學生的翻譯答案。
        **核心考點提示**: 「{hint_text if hint_text else '無特定提示'}」。請特別留意此點的掌握情況。
        **輸出格式**: JSON 必須包含 `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。
        ---
        {error_analysis_instructions}
        ---
        **原始中文句子是**: "{chinese_sentence}"
        """
        
    user_prompt = f"這是我的翻譯：「{user_translation}」。請嚴格根據你被賦予的【三層級定義與規範】，為我生成一份鉅細靡遺的 JSON 分析報告。"

    try:
        if LLM_PROVIDER == 'GEMINI':
            return _call_gemini_api(system_prompt, user_prompt)
        else: # 預設使用 OpenAI
            return _call_openai_api(system_prompt, user_prompt)
    except Exception as e:
        print(f"AI 批改時發生錯誤 - Provider: {LLM_PROVIDER}, Error: {e}")
        return {
            "did_master_review_concept": False, "is_generally_correct": False, "overall_suggestion": f"AI 模型 ({LLM_PROVIDER}) 暫時無法提供服務。",
            "error_analysis": [{"error_type": "系統錯誤", "explanation": f"系統無法處理 AI 的回覆：{e}"}]
        }