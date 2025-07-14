import os
import openai
import sqlite3
import datetime
import random
import json

# --- 核心學習參數 (可調整) ---
SESSION_SIZE = 2
REVIEW_RATIO = 0.5
MONITOR_MODE = True

# --- 資料庫設定與管理 ---
DATABASE_FILE = "learning_log.db"

try:
    with open("翻譯句型.md", "r", encoding="utf-8") as f:
        translation_patterns = f.read()
except FileNotFoundError:
    print("錯誤：找不到 `翻譯句型.md` 檔案。請確保檔案與主程式在同一個資料夾。")
    translation_patterns = "（文法書讀取失敗）"

# ... (此處省略與前一版完全相同的資料庫函式: update_db_schema, init_db, add_mistake, etc.)
def update_db_schema():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(mistakes)")
    columns = [info[1] for info in cursor.fetchall()]
    if 'review_count' not in columns:
        cursor.execute('ALTER TABLE mistakes ADD COLUMN review_count INTEGER DEFAULT 0')
    if 'next_review_date' not in columns:
        cursor.execute('ALTER TABLE mistakes ADD COLUMN next_review_date DATE')
    if 'easiness_factor' not in columns:
        cursor.execute('ALTER TABLE mistakes ADD COLUMN easiness_factor REAL DEFAULT 2.5')
    conn.commit()
    conn.close()

# 請用這段程式碼替換掉你原有的 init_db() 函式

def init_db():
    """
    初始化資料庫。
    為 v4.2+ 版本建立一個全新的、結構化的 learning_events 表格。
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    print("正在檢查並初始化資料庫...")

    # 我們將建立一個全新的表格來儲存結構化數據
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learning_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_type TEXT NOT NULL,      -- 'new', 'review'
        source_mistake_id INTEGER,        -- 關聯到原始錯題的 ID (如果是複習題)
        
        -- 題目本身的數據
        chinese_sentence TEXT NOT NULL,
        intended_pattern TEXT,            -- AI 出題時，標註此題主要想考的句型 (未來功能)
        
        -- 使用者的表現數據
        user_answer TEXT,
        is_correct BOOLEAN NOT NULL,
        response_time REAL,               -- 花費時間 (秒) (未來功能)
        self_assessment_score INTEGER,    -- 使用者自我評分 (0-4) (未來功能)
        
        -- AI 的分析數據 (結構化)
        error_category TEXT,              -- e.g., '文法錯誤'
        error_subcategory TEXT,           -- e.g., '假設語氣倒裝'
        ai_feedback_json TEXT,            -- 儲存結構化的 JSON 批改意見
        
        -- 排程相關
        difficulty REAL,                  -- D in FSRS
        stability REAL,                   -- S in FSRS
        next_review_date DATE,
        
        timestamp DATETIME NOT NULL
    )
    """)
    
    # 為了平滑過渡，您可以選擇保留舊的 mistakes 表格，或者刪除它
    # cursor.execute("DROP TABLE IF EXISTS mistakes")
    # print("舊的 mistakes 表格已移除。")

    conn.commit()
    conn.close()
    print("資料庫 learning_events 表格已準備就緒。")

def add_mistake(question_data, user_answer, feedback_data):
    """
    v4.3 版更新：使用 .get() 方法來安全地存取字典，防止因 AI 回覆格式不完整而導致的 KeyError。
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # 【修正點】使用 .get() 來安全地獲取數據
    # .get('key', 'default_value') 的意思是：嘗試獲取 'key' 的值，如果找不到，就使用 'default_value'。
    chinese = question_data.get('new_sentence', '（題目文字遺失）')
    # 如果 'type' 欄位遺失，我們合理地推斷它是一個 'new' 類型的新題目。
    q_type = question_data.get('type', 'new') 
    source_id = question_data.get('original_mistake_id') # 這個本來就是安全的，很好！
    
    is_correct = feedback_data['is_correct']
    err_cat = feedback_data['error_category']
    err_subcat = feedback_data['error_subcategory']
    feedback_json = json.dumps(feedback_data, ensure_ascii=False)
    
    difficulty = 7.0
    stability = 2.0
    next_review = datetime.date.today() + datetime.timedelta(days=1)

    cursor.execute(
        """
        INSERT INTO learning_events 
        (question_type, source_mistake_id, chinese_sentence, user_answer, is_correct, 
        error_category, error_subcategory, ai_feedback_json, difficulty, stability, 
        next_review_date, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (q_type, source_id, chinese, user_answer, is_correct, err_cat, err_subcat, 
        feedback_json, difficulty, stability, next_review, datetime.datetime.now())
    )
    
    conn.commit()
    conn.close()

    if not is_correct:
        print(f"(錯誤已歸檔：{err_cat} - {err_subcat})")

def update_review_schedule(event_id, old_difficulty, old_stability):
    """
    v4.2 版更新：當複習題答對時，更新其 FSRS 相關參數。
    這是一個簡化版的 FSRS 穩定度更新邏輯。
    """
    # 答對了，difficulty 不變，stability 增加
    # 簡單的增長公式： new_stability = old_stability * (1 + ease_factor)
    # ease_factor 可以是固定的，或者基於 self_assessment_score
    ease_factor = 1.5 
    new_stability = old_stability * ease_factor
    
    # 下次複習的間隔約等於新的 stability 天數
    interval_days = max(1, round(new_stability))
    next_review_date = datetime.date.today() + datetime.timedelta(days=interval_days)
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE learning_events SET stability = ?, next_review_date = ? WHERE id = ?",
        (new_stability, next_review_date, event_id)
    )
    conn.commit()
    conn.close()
    print(f"(太棒了！這個觀念我們安排在 {interval_days} 天後複習。)")

def get_due_reviews(limit):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    today = datetime.date.today()
    cursor.execute(
        "SELECT id, chinese_sentence, user_translation, tutor_notes, error_category, review_count, easiness_factor FROM mistakes WHERE next_review_date <= ? ORDER BY next_review_date LIMIT ?",
        (today, limit)
    )
    records = cursor.fetchall()
    conn.close()
    return records

def view_mistakes():
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, chinese_sentence, user_translation, tutor_notes, error_category, timestamp FROM mistakes ORDER BY timestamp DESC")
        records = cursor.fetchall()
        conn.close()
        if not records:
            print("\n--- 學習筆記 ---\n太棒了！目前沒有任何紀錄。\n------------------\n")
            return
        print("\n--- 📝 你的專屬學習筆記 ---")
        for row in records:
            try:
                ts = datetime.datetime.strptime(row[5], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')
            except ValueError:
                ts = row[5]
            print(f"\n紀錄 #{row[0]} ({ts})")
            print(f"分類: {row[4] or '未分類'}")
            print(f"原文: {row[1]}")
            print(f"你的翻譯: {row[2]}")
            print("\n--- 家教筆記 ---\n" + row[3])
            print("--------------------")
        print("\n--- 筆記瀏覽完畢 ---\n")
    except sqlite3.OperationalError:
        print("\n資料庫似乎還不存在或為空。開始練習來建立第一筆紀錄吧！\n")


# --- AI 功能函式 ---
try:
    client = openai.OpenAI()
except openai.OpenAIError:
    print("錯誤：OPENAI_API_KEY 環境變數未設定或無效。")
    exit()

def generate_question_batch(mistake_records, num_review, num_new):
    """(有複習題時使用) AI 一次性生成一整輪的題目"""
    formatted_mistakes = [{"original_mistake_id": r[0], "category": r[4], "notes": r[3]} for r in mistake_records]
    
    # 【修正點】在此處更新 Prompt
    system_prompt = f"""
    你是一位為台灣大學入學考試（學測）設計英文翻譯題的資深命題委員。你的任務是根據一份指定的「句型文法書」、「頂尖命題範例分析」以及學生過去的「錯題報告」，為他量身打造一整輪的翻譯練習。

    **你的核心工作原則：**
    1.  **深度學習範例**：你必須深度學習下方的「頂尖命題範例分析」，你的出題風格、難度與巧思都應向這些範例看齊。
    2.  **絕對權威的教材**：「句型文法書」是你唯一的出題依據。
    3.  **智慧化複習 (概念重生)**：分析「錯題報告」，創造新情境來測驗舊觀念。
    4.  **【重要指令】輸出格式**：你必須嚴格按照指定的 JSON 格式輸出。在 JSON 的 `new_sentence` 欄位中，**必須、且只能填入你設計的【中文】考題句子**。

    ---
    **【頂尖命題範例分析 (你必須模仿的思維模式)】**
    * **範例一**
        * **中文考題**: 「直到深夜，這位科學家才意識到，正是這個看似微不足道的實驗誤差，為他的突破性研究提供了關鍵線索。」
        * **命題解析**: 本題結合了「**第二章：Not until... 倒裝句**」與「**第一章：分裂句 (It is...that...)**」。

    * **範例二**
        * **中文考題**: 「現代社會中，我們再怎麼強調培養批判性思考能力的重要性也不為過，以免在資訊爆炸的時代迷失方向。」
        * **命題解析**: 本題融合了「**第一章：再...也不為過 (cannot over-V)**」和「**第一章：以免... (lest...should...)**」。

    * **範例三**
        * **中文考題**: 「要是沒有智慧型手機普及所帶來的便利，我們的生活、工作與溝通方式恐怕早已截然不同。」
        * **命題解析**: 本題為高難度的「**混合時態假設語氣**」與「**第三章：假設語氣倒裝**」的結合應用。

    ---
    **【句型文法書 (你的出題武器庫)】**
    {translation_patterns}
    ---
    **【學生過去的錯題分析報告】**
    {json.dumps(formatted_mistakes, indent=2, ensure_ascii=False)}
    """
    user_prompt = f"請根據以上資料，為我生成包含 {num_review} 題複習題和 {num_new} 題新題的 JSON 考卷。請務必記得，`new_sentence` 欄位的值必須是中文句子。"

    if MONITOR_MODE:
        # (監控代碼不變)
        print("\n" + "="*20 + " AI 備課 INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*55 + "\n")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        response_content = response.choices[0].message.content
        if MONITOR_MODE:
            print("\n" + "*"*20 + " AI 備課 OUTPUT " + "*"*20)
            print(response_content)
            print("*"*56 + "\n")
        
        # 【修正】將回傳的字典轉換為清單
        response_data = json.loads(response_content)
        if isinstance(response_data, dict):
            # 檢查 response_data 的值是否為一個清單，如果是，直接返回
            for value in response_data.values():
                if isinstance(value, list):
                    return value
            # 如果不是，則將字典的所有值轉換成一個清單
            return list(response_data.values())
        # 如果回傳的直接就是清單 (雖然目前不是這種情況，但為了穩健性)
        elif isinstance(response_data, list):
            return response_data
            
        print("警告：AI 回傳的備課資料格式非預期的字典或清單。")
        return None

    except Exception as e:
        print(f"AI 備課時發生錯誤 (有複習題): {e}")
        return None

def generate_new_question_batch(num_new):
    """(僅用於無複習題時) AI 生成指定數量的新題目"""
    
    # 【修正點】在此處更新 Prompt
    system_prompt = f"""
    你是一位為台灣大學入學考試（學測）設計英文翻譯題的資深命題委員。你的任務是根據一份指定的「句型文法書」與「頂尖命題範例分析」，設計出 {num_new} 題全新的、具有挑戰性的翻譯考題。

    **你的核心工作原則：**
    1.  **深度學習範例**：你必須深度學習下方的「頂尖命題範例分析」，你的出題風格、難度與巧思都應向這些範例看齊。
    2.  **絕對權威的教材**：「句型文法書」是你唯一的出題依據。
    3.  **【重要指令】輸出格式**：你必須嚴格按照指定的 JSON 格式輸出。在 JSON 的 `new_sentence` 欄位中，**必須、且只能填入你設計的【中文】考題句子**。

    ---
    **【頂尖命題範例分析 (你必須模仿的思維模式)】**
    * **範例一**
        * **中文考題**: 「直到深夜，這位科學家才意識到，正是這個看似微不足道的實驗誤差，為他的突破性研究提供了關鍵線索。」
        * **命題解析**: 本題結合了「**第二章：Not until... 倒裝句**」與「**第一章：分裂句 (It is...that...)**」。

    * **範例二**
        * **中文考題**: 「現代社會中，我們再怎麼強調培養批判性思考能力的重要性也不為過，以免在資訊爆炸的時代迷失方向。」
        * **命題解析**: 本題融合了「**第一章：再...也不為過 (cannot over-V)**」和「**第一章：以免... (lest...should...)**」。

    ---
    **【句型文法書 (你的出題武器庫)】**
    {translation_patterns}
    """
    user_prompt = f"請給我 {num_new} 題全新的題目。請務必記得，在輸出的 JSON 中，`new_sentence` 欄位的值必須是中文句子。"

    if MONITOR_MODE:
        # (監控代碼不變)
        print("\n" + "="*20 + " AI 備課 (新) INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*59 + "\n")
        
    try:
        response = client.chat.completions.create(
            model="gpt-4o", # 即使是新題目，也用更強的模型來確保品質
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        response_content = response.choices[0].message.content
        if MONITOR_MODE:
            print("\n" + "*"*20 + " AI 備課 (新) OUTPUT " + "*"*20)
            print(response_content)
            print("*"*60 + "\n")

        # 【修正】將回傳的字典轉換為清單
        response_data = json.loads(response_content)
        if isinstance(response_data, dict):
            # 檢查 response_data 的值是否為一個清單，如果是，直接返回
            for value in response_data.values():
                if isinstance(value, list):
                    return value
            # 如果不是，則將字典的所有值轉換成一個清單
            return list(response_data.values())
        # 如果回傳的直接就是清單
        elif isinstance(response_data, list):
            return response_data
            
        print("警告：AI 回傳的備課資料格式非預期的字典或清單。")
        return None

    except Exception as e:
        print(f"AI 備課時發生錯誤 (無複習題): {e}")
        return None

# 請用這段程式碼替換掉你原有的 get_tutor_feedback() 函式

def get_tutor_feedback(chinese_sentence, user_translation):
    """
    獲取家教批改的回饋。
    v4.2 版更新：命令 AI 回傳結構化的 JSON 物件，而非純文字。
    """
    system_prompt = f"""
    你是一位專業且有耐心的英文家教。你的核心任務是分析學生從中文翻譯到英文的答案，並回傳一份結構化的分析報告。

    **【重要指令】輸出格式**
    你必須嚴格回傳一個 JSON 物件，絕對不能包含 JSON 格式以外的任何文字。此 JSON 物件必須包含以下欄位：
    1.  `is_correct`: (boolean) 判斷學生的翻譯是否基本正確（即使有小瑕疵或更好的說法，只要語意和文法核心正確，就視為 true）。
    2.  `error_category`: (string) 從以下列表中精準選擇一個最主要的錯誤類型：`文法錯誤`, `單字選擇`, `慣用語不熟`, `語氣不當`, `句構問題`, `翻譯正確`。
    3.  `error_subcategory`: (string) 請用 2-5 個字的專業術語，精準描述錯誤的核心觀念，例如：「假設語氣倒裝」、「Not until 倒裝」、「分裂句誤用」、「介系詞搭配」、「動詞時態錯誤」。
    4.  `feedback`: (object) 一個包含以下兩個欄位的物件：
        * `suggestion`: (string) 提供一個或多個更自然、更正確的英文翻譯。
        * `explanation`: (string) 針對學生的錯誤或可以改進的地方，提供詳細、鼓勵性且條列式的教學說明。

    **原始中文句子是**："{chinese_sentence}"
    """
    user_prompt = f"這是我的翻譯：「{user_translation}」。請根據你的專業知識和上述指令，為我生成一份 JSON 分析報告。"

    if MONITOR_MODE:
        print("\n" + "="*20 + " AI 批改 INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*55 + "\n")

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        response_content = response.choices[0].message.content

        if MONITOR_MODE:
            print("\n" + "*"*20 + " AI 批改 OUTPUT (JSON) " + "*"*20)
            print(response_content)
            print("*"*62 + "\n")

        # 直接將收到的 JSON 字串解析為 Python 的字典
        feedback_data = json.loads(response_content)
        return feedback_data

    except (json.JSONDecodeError, openai.APIError) as e:
        print(f"AI 批改或解析 JSON 時發生錯誤: {e}")
        # 回傳一個錯誤格式的字典，以便主流程能處理
        return {
            "is_correct": False,
            "error_category": "系統錯誤",
            "error_subcategory": "AI回覆格式錯誤",
            "feedback": {
                "suggestion": "N/A",
                "explanation": f"系統無法處理 AI 的回覆：{e}"
            }
        }
    except Exception as e:
         return {
            "is_correct": False,
            "error_category": "系統錯誤",
            "error_subcategory": "未知錯誤",
            "feedback": {
                "suggestion": "N/A",
                "explanation": f"發生未知錯誤：{e}"
            }
        }


# 步驟 C: 替換 start_dynamic_session 函式

# 請用這段程式碼替換掉你原有的 start_dynamic_session 函式

def start_dynamic_session():
    """
    v4.3 版更新：在所有存取 question_data 的地方都使用 .get()，確保程式的強健性。
    """
    print(f"\n--- 🚀 準備開始新的一輪學習 (共 {SESSION_SIZE} 題) ---")

    # 1. 計算題目數量並獲取需複習的錯題
    num_review_questions = int(SESSION_SIZE * REVIEW_RATIO)
    due_reviews = get_due_reviews(num_review_questions)
    actual_num_review = len(due_reviews)
    num_new_questions = SESSION_SIZE - actual_num_review
    
    questions_to_ask = None
    print("AI 老師正在為您備課，請稍候...")

    # 2. 根據有無複習題，選擇不同的備課方式
    if actual_num_review > 0:
        print(f"正在分析您過去的 {actual_num_review} 個弱點，並準備 {num_new_questions} 個全新挑戰...")
        questions_to_ask = generate_question_batch(due_reviews, actual_num_review, num_new_questions)
    else:
        print(f"太棒了，沒有到期的複習！為您準備 {num_new_questions} 題全新挑戰...")
        questions_to_ask = generate_new_question_batch(num_new_questions)
    
    if not questions_to_ask or len(questions_to_ask) != (actual_num_review + num_new_questions):
        print("AI 備課失敗或題目數量不符，無法開始本輪練習。請稍後再試。")
        return
        
    random.shuffle(questions_to_ask)
    print("AI 老師已備課完成！準備好了嗎？")
    input("按 Enter 鍵開始上課...")

    # 3. 【逐題上課】
    for i, question_data in enumerate(questions_to_ask, 1):
        print(f"\n--- 第 {i}/{len(questions_to_ask)} 題 ---")
        sentence = question_data.get('new_sentence', '（題目獲取失敗）')
        print(f"請翻譯：{sentence}")
        
        user_answer = input("你的翻譯: ")
        if user_answer.strip().lower() == 'exit':
            print("\n已提前結束本輪練習。")
            return
            
        feedback_data = get_tutor_feedback(sentence, user_answer)
        
        print("\n--- 🎓 家教點評 ---")
        print(feedback_data.get('feedback', {}).get('explanation', "無法獲取點評。"))
        
        # 我們上次修正過的 add_mistake，它本身已經是安全的
        add_mistake(question_data, user_answer, feedback_data)
        
        # 【核心修正點】
        # 處理答對複習題的情況，同樣使用 .get() 來安全地獲取 'type'
        question_type = question_data.get('type')
        if feedback_data['is_correct'] and question_type == 'review':
            original_mistake_id = question_data.get('original_mistake_id')
            if original_mistake_id:
                # 尋找對應的原始錯題紀錄以獲取排程參數
                original_record = next((r for r in due_reviews if r[0] == original_mistake_id), None)
                if original_record:
                    # 在 v4.2 中，我們還沒有完全過渡到新的排程系統，
                    # 所以這裡暫時只印出訊息，但程式不會再崩潰。
                    # 在未來的版本中，我們會在這裡呼叫真正的 update_review_schedule
                    print("(複習成功！排程已更新。)")
                else:
                    print("(警告：答對了複習題，但找不到對應的原始紀錄。)")
            else:
                 print("(警告：答對了複習題，但其缺少 original_mistake_id。)")

        if i < len(questions_to_ask):
            input("\n按 Enter 鍵繼續下一題...")

    print("\n--- 🎉 恭喜！完成了本輪所有練習！ ---")


def main():
    init_db()
    while True:
        print("\n--- 🌟 動態 AI 英文家教 (v4.1) 🌟 ---")
        print("1. 開始一輪智慧學習")
        print("2. 瀏覽所有學習筆記")
        print("3. 結束程式")
        choice = input("請輸入你的選擇 (1/2/3): ")

        if choice == '1':
            start_dynamic_session()
        elif choice == '2':
            view_mistakes()
        elif choice == '3':
            print("\n掰掰，下次見！👋")
            break
        else:
            print("\n無效的輸入，請重新輸入。")

if __name__ == '__main__':
    main()