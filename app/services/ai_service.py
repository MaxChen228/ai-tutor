# app/services/ai_service.py

import os
import openai
import random
import json
from app.assets import EXAMPLE_SENTENCE_BANK # 注意 import 路徑的變化
MONITOR_MODE = True
# --- AI 客戶端初始化 ---
try:
    client = openai.OpenAI()
except openai.OpenAIError:
    print("錯誤：OPENAI_API_KEY 環境變數未設定或無效。")
    exit()

# --- 文法書讀取 ---
try:
    with open("翻譯句型.md", "r", encoding="utf-8") as f:
        translation_patterns = f.read()
except FileNotFoundError:
    print("錯誤：找不到 `翻譯句型.md` 檔案。")
    translation_patterns = "（文法書讀取失敗）"

# --- AI 功能函式 ---
def generate_question_batch(weak_points_str, num_review):
    """
    (複習題) 此函式邏輯維持不變。
    """
    system_prompt = f"""
            你是一位頂尖的英文教學專家與命題者，專門設計「精準打擊」的複習題。你的核心任務是根據下方一份關於學生的「具體知識點弱點報告」，為他量身打造 {num_review} 題翻譯考題。

            **你的核心工作原則：**
            1.  **精準打擊**：你必須仔細分析報告中列出的每一個「正確用法」。你的每一道題都必須圍繞這個「正確用法」來設計，確保學生能在一个全新的句子中正確地使用它。
            2.  **情境創造**：不要只滿足於替換單字。你要創造一個全新的、自然的、合乎邏輯的中文情境，使得「正確用法」是這個情境下最貼切的翻譯。
            3.  **絕對保密**：在你的題目中，絕對不能出現「正確用法」的任何英文字眼。你的任務是提供中文情境，讓學生自己把正確的英文翻譯出來。
            4.  **【重要指令】輸出格式**：你必須嚴格按照指定的 JSON 格式輸出。在 JSON 的 `new_sentence` 欄位中，**必須、且只能填入你設計的【中文】考題句子**。

            範例格式:
            {{
                "questions": [
                    {{ "new_sentence": "這份工作薪水很高，但另一方面，它需要經常加班。" }}
                ]
            }}
            """
    user_prompt = f"""
        **【學生具體知識點弱點報告】**
        {weak_points_str}
        ---
        請根據以上報告，為我生成 {num_review} 題能測驗出學生是否已經掌握這些「正確用法」的翻譯題。
        請務必記得，在輸出的 JSON 中，`new_sentence` 欄位的值必須是中文句子。
        """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        response_data = json.loads(response.choices[0].message.content)
        questions_list = []
        if isinstance(response_data, dict):
            for value in response_data.values():
                if isinstance(value, list):
                    questions_list = value
                    break
        elif isinstance(response_data, list):
            questions_list = response_data
        return questions_list
    except Exception as e:
        print(f"AI 備課時發生錯誤 (有複習題): {e}")
        return None

# 位於 main.py

def generate_new_question_batch(num_new, difficulty, length):
    """
    【v5.9.1 修正版】: 在 Prompt 中加入對 question 物件內部結構的嚴格規定。
    """
    # ... (文法書取樣、例句選取的邏輯維持不變) ...
    try:
        patterns_list = [p.strip() for p in translation_patterns.split('* ') if p.strip()]
        num_to_sample = min(len(patterns_list), 15)
        sampled_patterns = random.sample(patterns_list, num_to_sample)
        sampled_patterns_str = "* " + "\n* ".join(sampled_patterns)
    except Exception as e:
        print(f"文法書取樣失敗: {e}")
        sampled_patterns_str = "（文法書取樣失敗）"

    example_sentences = EXAMPLE_SENTENCE_BANK.get(length, EXAMPLE_SENTENCE_BANK['medium']) \
                                             .get(str(difficulty), EXAMPLE_SENTENCE_BANK['medium']['3'])
    example_sentences_str = "\n".join([f"- {s}" for s in example_sentences])

    # 【核心修改處】: 改造指令三，加入詳細的物件結構說明和範例
    system_prompt = f"""
    你是一位超級高效的英文命題 AI。你的任務是嚴格遵循以下三項指令，為我生成 {num_new} 題翻譯考題。

    **指令一：模仿風格**
    你必須深度學習下方的「風格參考範例」，你的出題用字、句式複雜度和主題，都必須與這些範例的風格完全一致。
    ---
    【風格參考範例 (來自難度 {difficulty} / 長度 {length})】
    {example_sentences_str}
    ---

    **指令二：運用句型**
    在出題時，你必須從下方的「指定句型庫」中，選擇合適的句型融入到你的題目裡。
    ---
    【指定句型庫 (本次隨機抽取)】
    {sampled_patterns_str}
    ---

    **指令三：嚴格輸出**
    你必須嚴格回傳一個 JSON 物件。此物件的根部必須有一個名為 "questions" 的 key，其 value 是一個包含 {num_new} 個問題物件的列表。
    **每一個問題物件都必須、且只能包含一個 key，名為 "new_sentence"**，其 value 為你設計的中文考題。

    範例格式：
    {{
        "questions": [
            {{ "new_sentence": "中文考題一..." }},
            {{ "new_sentence": "中文考題二..." }}
        ]
    }}
    """
    user_prompt = f"請嚴格遵照你的三項核心指令，為我生成 {num_new} 題考題。"

    # ... (後續的 MONITOR_MODE 和 try/except 邏輯維持不變) ...
    if MONITOR_MODE:
        print("\n" + "="*20 + " AI 備課 (Token 優化版 v2) INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*75 + "\n")
        
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        response_data = json.loads(response.choices[0].message.content)
        questions_list = []
        if isinstance(response_data, dict):
            for value in response_data.values():
                if isinstance(value, list):
                    questions_list = value
                    break
        elif isinstance(response_data, list):
            questions_list = response_data
        
        return questions_list
    except Exception as e:
        print(f"AI 備課時發生錯誤 (Token 優化版): {e}")
        return None
    
def get_tutor_feedback(chinese_sentence, user_translation, review_context=None):
    """
    【v5.15.3 最終改造】: 在 Prompt 中加入排他性指令，防止 AI 在 error_analysis 中回報已掌握的複習觀念。
    """
    
    # 共同的指令部分，定義了 error_analysis 的結構和 key_point_summary 的生成規則
    error_analysis_instructions = """
    4.  `error_analysis`: (array of objects) 一個清單，如果沒有任何錯誤，請回傳一個空清單 `[]`。
        清單中的每一個物件都必須包含以下所有欄位：
        * `key_point_summary`: (string) 【最重要的欄位】請為這個錯誤點提煉一個「錯誤焦點」。這不是一個普通的標題，而是一個能讓學生立刻回憶起錯誤的、精簡的提示。請嚴格模仿下方的範例格式：
            - 如果是介系詞錯誤，範例：`"on" the other hand`
            - 如果是動詞時態/形式錯誤，範例：`strive "to V"` 或 `be used "to V-ing"`
            - 如果是特定文法結構，範例：`強調句構 (It is... that...)`
            - 如果是單字拼寫錯誤，範例：`"tomorrow" (拼寫)`
        * `error_type`: (string) `文法錯誤`, `單字選擇`, `慣用語不熟`, `語氣不當`, `句構問題`, `拼寫錯誤`, `贅字或漏字`。
        * `error_subtype`: (string) 2-5 個字的專業術語。
        * `original_phrase`: (string) 從學生答案中，精確地提取出錯誤的那個單字或片語。
        * `correction`: (string) 針對該錯誤片語，提供正確的寫法。
        * `explanation`: (string) 簡潔地解釋為什麼這是錯的。
        * `severity`: (string) `major` 或 `minor`。
    """

    if review_context:
        # 這是複習題的「目標導向」prompt
        system_prompt = f"""
        你是一位頂尖的英文教學專家，正在為一名學生進行「核心觀念」的複習驗收。

        **你的首要任務：**
        學生的本次作答，是為了測驗他是否已經掌握了以下這個核心觀念：
        - **核心複習觀念: "{review_context}"**

        請在你的 JSON 回覆中，務必包含一個名為 `did_master_review_concept` 的布林值欄位，用來明確回答「學生的翻譯是否正確地應用了上述的核心複習觀念？」。

        **你的次要任務：**
        在完成首要任務後，請對學生的整個句子進行常規的錯誤分析，並將結果填入 `error_analysis` 列表中。

        **【極重要的新增指令：排他性原則】**
        在你的次要任務中，`error_analysis` 列表應該**只包含與「核心複習觀念」無關的其他新錯誤**。如果某個文法點或用法，其本質就是正在複習的這個核心觀念，**請絕對不要**將它再次放入 `error_analysis` 列表中。
        例如，如果核心複習觀念是 "strives"，而學生寫對了 "strives to improve"，那麼 `error_analysis` 列表中，絕對不應該再出現任何關於 "strive to V" 的分析，即使是正面的教學說明也不行。

        **【輸出格式指令】**
        你的 JSON 回覆必須包含以下所有欄位：
        1.  `did_master_review_concept`: (boolean)
        2.  `is_generally_correct`: (boolean)
        3.  `overall_suggestion`: (string)
        {error_analysis_instructions}

        **原始中文句子是**："{chinese_sentence}"
        """
    else:
        # 這是新題目的常規 prompt
        system_prompt = f"""
        你是一位極其細心、專業且有耐心的英文家教。你的任務是像批改作業一樣，逐字逐句分析學生從中文翻譯到英文的答案，並回傳一份結構化的 JSON 分析報告。

        **【重要指令】輸出格式**
        你必須嚴格回傳一個 JSON 物件，絕對不能包含 JSON 格式以外的任何文字。此 JSON 物件必須包含以下欄位：
        1.  `is_generally_correct`: (boolean)
        2.  `overall_suggestion`: (string)
        {error_analysis_instructions}

        **原始中文句子是**："{chinese_sentence}"
        """

    user_prompt = f"這是我的翻譯：「{user_translation}」。請根據你的專業知識和上述指令，為我生成一份鉅細靡遺的 JSON 分析報告。"

    if MONITOR_MODE:
        print("\n" + "="*20 + " AI 批改 (v5.15.3) INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*65 + "\n")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        feedback_data = json.loads(response.choices[0].message.content)
        return feedback_data
    except Exception as e:
        print(f"AI 批改時發生錯誤: {e}")
        return {
            "did_master_review_concept": False, "is_generally_correct": False, "overall_suggestion": "N/A",
            "error_analysis": [{"error_type": "系統錯誤", "explanation": f"系統無法處理 AI 的回覆：{e}"}]
        }
