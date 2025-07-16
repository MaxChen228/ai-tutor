# app/services/ai_service.py

import os
import json
import random
import openai
import google.generativeai as genai
from app.assets import EXAMPLE_SENTENCE_BANK

MONITOR_MODE = True

# --- API 客戶端一次性初始化 ---
openai_client = openai.OpenAI() if os.environ.get("OPENAI_API_KEY") else None
if os.environ.get("GEMINI_API_KEY"):
    genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

# --- 文法書讀取 ---
try:
    with open("翻譯句型.md", "r", encoding="utf-8") as f:
        translation_patterns = f.read()
except FileNotFoundError:
    translation_patterns = "（文法書讀取失敗）"

# --- 【v6.1 記憶體優化】將龐大的靜態 Prompt 定義為全域常數 ---
ERROR_ANALYSIS_INSTRUCTIONS_V6 = """
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

# --- 私有函式：各模型的具體實現 ---

def _call_openai_api(system_prompt, user_prompt, model_name):
    if not openai_client: raise ValueError("OpenAI API 金鑰未設定。")
    if MONITOR_MODE: print(f"\n{'='*20} OpenAI API INPUT ({model_name}) {'='*20}\n--- SYSTEM PROMPT ---\n{system_prompt}\n\n--- USER PROMPT ---\n{user_prompt}\n{'='*60}\n")
    response = openai_client.chat.completions.create(model=model_name, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}], response_format={"type": "json_object"})
    return json.loads(response.choices[0].message.content)

def _call_gemini_api(system_prompt, user_prompt, model_name):
    if not os.environ.get("GEMINI_API_KEY"): raise ValueError("Gemini API 金鑰未設定。")
    gemini_model = genai.GenerativeModel(model_name, generation_config=genai.GenerationConfig(response_mime_type="application/json"))
    full_prompt = system_prompt + "\n\n" + user_prompt
    if MONITOR_MODE: print(f"\n{'='*20} Gemini API INPUT ({model_name}) {'='*20}\n{full_prompt}\n{'='*60}\n")
    response = gemini_model.generate_content(full_prompt)
    return json.loads(response.text)

def _normalize_questions_output(response_data):
    if isinstance(response_data, dict) and "questions" in response_data and isinstance(response_data["questions"], list): return response_data["questions"]
    if isinstance(response_data, list): return response_data
    if isinstance(response_data, dict):
        for value in response_data.values():
            if isinstance(value, list): return value
    return []

def _get_provider_and_call(model_name, system_prompt, user_prompt):
    if 'gemini' in model_name:
        print(f"[AI Service] Routing to Gemini model: {model_name}")
        return _call_gemini_api(system_prompt, user_prompt, model_name)
    elif 'gpt' in model_name:
        print(f"[AI Service] Routing to OpenAI model: {model_name}")
        return _call_openai_api(system_prompt, user_prompt, model_name)
    else:
        raise ValueError(f"無法識別的模型名稱: {model_name}。")

# --- 公共函式：供外部呼叫的統一介面 (Dispatcher) ---

def generate_question_batch(weak_points_str, num_review, model_name):
    system_prompt = f"""你是一位頂尖的英文教學專家與命題者，專門設計「精準打擊」的複習題。你的核心任務是根據下方一份關於學生的「具體知識點弱點報告」，為他量身打造 {num_review} 題翻譯考題。**核心原則**: 1. 精準打擊 2. 情境創造 3. 絕對保密。**輸出格式**: JSON 物件，根部有 "questions" key，其 value 是列表。每個問題物件必須包含 "new_sentence" (string) 和 "hint_text" (string)。"""
    user_prompt = f"**【學生具體知識點弱點報告】**\n{weak_points_str}\n---\n請根據以上報告，為我生成 {num_review} 題翻譯題。請務必記得，你的輸出必須是包含 \"questions\" key 的 JSON 格式。"
    try:
        response_data = _get_provider_and_call(model_name, system_prompt, user_prompt)
        return _normalize_questions_output(response_data)
    except Exception as e:
        print(f"AI 備課時發生錯誤 (複習題) - Model: {model_name}, Error: {e}")
        return None

def generate_new_question_batch(num_new, difficulty, length, model_name):
    patterns_list = [p.strip() for p in translation_patterns.split('* ') if p.strip()]
    sampled_patterns_str = "* " + "\n* ".join(random.sample(patterns_list, min(len(patterns_list), 15))) if patterns_list else "無"
    example_sentences = EXAMPLE_SENTENCE_BANK.get(length, {}).get(str(difficulty), [])
    example_sentences_str = "\n".join([f"- {s}" for s in example_sentences]) if example_sentences else "無範例"
    system_prompt = f"你是一位超級高效的英文命題 AI，任務是為我生成 {num_new} 題翻譯考題。\n**指令一：模仿風格**\n你必須深度學習下方的「風格參考範例 (來自難度 {difficulty} / 長度 {length})」，你的出題風格必須與其一致。\n---\n【風格參考範例】\n{example_sentences_str}\n---\n**指令二：運用句型**\n你必須從下方的「指定句型庫」中，選擇合適的句型融入題目。\n---\n【指定句型庫】\n{sampled_patterns_str}\n---\n**指令三：嚴格輸出**\n你必須嚴格回傳一個 JSON 物件。根部有一個 \"questions\" key，其 value 是一個包含 {num_new} 個問題物件的列表。每個問題物件必須包含 \"new_sentence\" (string) 和 \"hint_text\" (string)。"
    user_prompt = f"請嚴格遵照你的三項核心指令，為我生成 {num_new} 題考題。"
    try:
        response_data = _get_provider_and_call(model_name, system_prompt, user_prompt)
        return _normalize_questions_output(response_data)
    except Exception as e:
        print(f"AI 備課時發生錯誤 (新題) - Model: {model_name}, Error: {e}")
        return None

def get_tutor_feedback(chinese_sentence, user_translation, review_context, hint_text, model_name):
    if review_context:
        system_prompt = (
            f"你是一位嚴格的英文教學評審，正在驗收學生對核心觀念的掌握。\n"
            f"**首要任務**: 判斷學生作答是否掌握了「核心複習觀念: {review_context}」，並設定 `did_master_review_concept` (boolean) 的值。\n"
            f"**次要任務**: 根據下方【PART 1】的四層級分類法，精準分析其他與核心觀念無關的新錯誤。\n"
            f"**排他性原則**: `error_analysis` 列表不得包含與核心複習觀念相關的分析。\n"
            f"**輸出格式**: JSON 必須包含 `did_master_review_concept`(boolean), `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。\n"
            f"**【重要】`overall_suggestion` 格式**: 你的回覆必須包含 `[AI建議完整翻譯]` 和 `[核心中文點評]` 這兩個標籤，並用繁體中文撰寫點評。\n"
            f"---\n{ERROR_ANALYSIS_INSTRUCTIONS_V6}\n---\n" # 【記憶體優化】使用 + 號拼接
            f"**原始中文句子是**: \"{chinese_sentence}\""
        )
    else:
        system_prompt = (
            f"你是一位極其細心且嚴格的英文家教，請根據下方提供的【三層級定義與規範】，精準分析學生的翻譯答案。\n"
            f"**核心考點提示**: 「{hint_text if hint_text else '無特定提示'}」。請特別留意此點的掌握情況。\n"
            f"**輸出格式**: JSON 必須包含 `is_generally_correct`(boolean), `overall_suggestion`(string), 和 `error_analysis`(array)。\n"
            f"**【重要】`overall_suggestion` 格式**: 你的回覆必須包含 `[AI建議完整翻譯]` 和 `[核心中文點評]` 這兩個標籤，並用繁體中文撰寫點評。\n"
            f"---\n{ERROR_ANALYSIS_INSTRUCTIONS_V6}\n---\n" # 【記憶體優化】使用 + 號拼接
            f"**原始中文句子是**: \"{chinese_sentence}\""
        )
    user_prompt = f"這是我的翻譯：「{user_translation}」。請嚴格根據你被賦予的【四層級定義與規範】，為我生成一份鉅細靡遺的 JSON 分析報告。"
    try:
        return _get_provider_and_call(model_name, system_prompt, user_prompt)
    except Exception as e:
        print(f"AI 批改時發生錯誤 - Model: {model_name}, Error: {e}")
        return {
            "did_master_review_concept": False, "is_generally_correct": False, "overall_suggestion": f"[核心中文點評]AI 模型 ({model_name}) 暫時無法提供服務。",
            "error_analysis": [{"error_type": "系統錯誤", "explanation": f"系統無法處理 AI 的回覆：{e}"}]
        }