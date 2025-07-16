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

    # 【v6.0 指南強化版】: 注入了清晰定義和豐富範例的全新 Prompt 核心
    error_analysis_instructions = """
    **PART 1: 全新四層級錯誤分類法**
    你是一位英文教育的裁判，必須嚴格遵守以下分類定義，絕不混淆。

    ---
    **層級 1: `拼字與格律層級 (Orthography & Form)`**
    * **定義**: 最表層的機械性錯誤，關乎「拼寫」或「書寫形式」。
    * **範疇**: 單字拼錯、大小寫錯誤、名詞單複數形式錯誤 (例如 `game` vs `games`)。
    * **範例**: "I have two **cat**." -> `error_type`: "拼字與格律層級", `error_subtype`: "名詞單複數"。

    ---
    **層級 2: `詞彙與片語層級 (Lexical & Phrasal)`**
    * **定義**: 「選詞」或「固定搭配」的錯誤。單字拼寫正確，但用錯了地方。
    * **範疇**: 近義詞混淆 (`affect` vs `effect`)、動詞/介系詞固定搭配 (`interested in`)。
    * **範例**: "He **said** me a story." -> `error_type`: "詞彙與片語層級", `error_subtype`: "動詞選擇錯誤", `correction`: "told"。

    ---
    **層級 3: `語法結構層級 (Grammatical & Structural)`**
    * **定義**: 「句子組合規則」的錯誤，即傳統文法錯誤。
    * **範疇**: 時態、主謂一致、冠詞、動詞型態 (Gerunds/Infinitives)、句子結構。
    * **【特別指令】**: `stop to play` vs `stop playing` 這類動詞型態錯誤，**必須**歸於此類。
    * **範例**: "He **stop to play** computer games." -> `error_type`: "語法結構層級", `error_subtype`: "動詞型態錯誤", `correction`: "stopped playing"。

    ---
    **層級 4: `語意與語用層級 (Semantic & Pragmatic)`**
    * **定義**: 句子文法可能正確，但在「意義」或「情境」上不自然、不禮貌或冗餘。
    * **範疇**: 語氣正式度、語意冗餘、中式英文。
    * **範例**: "The reason is **because**..." -> `error_type`: "語意與語用層級", `error_subtype`: "語意冗餘"。

    **PART 2: JSON 欄位結構**
    `error_analysis` 陣列中的每個物件，必須包含: `key_point_summary`, `error_type`, `error_subtype`, `original_phrase`, `correction`, `explanation`, `severity`。
    """
    
    if review_context:
        system_prompt = f"""
        你是一位嚴格的英文教學評審，正在驗收學生對核心觀念的掌握。
        **首要任務**: 判斷學生作答是否掌握了「核心複習觀念: {review_context}」，並設定 `did_master_review_concept` (boolean) 的值。
        **次要任務**: 根據下方【PART 1】的四層級分類法，精準分析其他新錯誤。
        **排他性原則**: `error_analysis` 列表不得包含與核心複習觀念相關的分析。
        **輸出格式**: JSON 必須包含 `did_master_review_concept`(boolean), `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。
        **【重要】`overall_suggestion` 格式**: 你的回覆必須包含 `[AI建議完整翻譯]` 和 `[核心中文點評]` 這兩個標籤，並用繁體中文撰寫點評。
        ---
        {error_analysis_instructions}
        ---
        **原始中文句子是**: "{chinese_sentence}"
        """
    else:
        system_prompt = f"""
        你是一位極其細心且嚴格的英文家教，請根據下方【PART 1】的四層級分類法，精準分析學生的翻譯答案。
        **核心考點提示**: 「{hint_text if hint_text else '無特定提示'}」。請特別留意此點的掌握情況。
        **輸出格式**: JSON 必須包含 `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。
        **【重要】`overall_suggestion` 格式**: 你的回覆必須包含 `[AI建議完整翻譯]` 和 `[核心中文點評]` 這兩個標籤，並用繁體中文撰寫點評。
        ---
        {error_analysis_instructions}
        ---
        **原始中文句子是**: "{chinese_sentence}"
        """
        
    user_prompt = f"這是我的翻譯：「{user_translation}」。請嚴格根據你被賦予的【四層級定義與規範】，為我生成一份鉅細靡遺的 JSON 分析報告。"

    try:
        if LLM_PROVIDER == 'GEMINI':
            return _call_gemini_api(system_prompt, user_prompt)
        else: # 預設使用 OpenAI
            return _call_openai_api(system_prompt, user_prompt)
    except Exception as e:
        print(f"AI 批改時發生錯誤 - Provider: {LLM_PROVIDER}, Error: {e}")
        return {
            "did_master_review_concept": False, "is_generally_correct": False, "overall_suggestion": f"[核心中文點評]AI 模型 ({LLM_PROVIDER}) 暫時無法提供服務，請稍後再試。",
            "error_analysis": [{"error_type": "系統錯誤", "explanation": f"系統無法處理 AI 的回覆：{e}"}]
        }