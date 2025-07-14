import os
import openai
import sqlite3
import datetime
import random
import json

# --- 核心學習參數 (可調整) ---
SESSION_SIZE = 5
REVIEW_RATIO = 0.7
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

def init_db():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mistakes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chinese_sentence TEXT NOT NULL,
        user_translation TEXT NOT NULL,
        tutor_notes TEXT NOT NULL,
        error_category TEXT,
        timestamp DATETIME NOT NULL,
        review_count INTEGER DEFAULT 0,
        next_review_date DATE,
        easiness_factor REAL DEFAULT 2.5
    )
    """)
    conn.commit()
    conn.close()
    update_db_schema()

def add_mistake(chinese, user_trans, notes, category, original_mistake_id=None):
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    if original_mistake_id:
        cursor.execute(
            "UPDATE mistakes SET review_count = 0, easiness_factor = max(1.3, easiness_factor - 0.2), next_review_date = ? WHERE id = ?",
            (tomorrow, original_mistake_id)
        )
        print(f"(唉呀，這個舊觀念還不熟，我們明天再來一次！)")
    else:
        cursor.execute(
            "INSERT INTO mistakes (chinese_sentence, user_translation, tutor_notes, error_category, timestamp, next_review_date) VALUES (?, ?, ?, ?, ?, ?)",
            (chinese, user_trans, notes, category, datetime.datetime.now(), tomorrow)
        )
    conn.commit()
    conn.close()

def update_review_schedule(record_id, old_review_count, old_ef):
    new_ef = max(1.3, old_ef + 0.1)
    if old_review_count == 0:
        interval_days = 1
    elif old_review_count == 1:
        interval_days = 6
    else:
        interval_days = round(old_review_count * new_ef)
    next_review_date = datetime.date.today() + datetime.timedelta(days=interval_days)
    review_count = old_review_count + 1
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE mistakes SET review_count = ?, easiness_factor = ?, next_review_date = ? WHERE id = ?",
        (review_count, new_ef, next_review_date, record_id)
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
        response_data = json.loads(response_content)
        if isinstance(response_data, dict):
            for key in response_data:
                if isinstance(response_data[key], list):
                    return response_data[key]
        return response_data
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
        response_data = json.loads(response_content)
        if isinstance(response_data, dict):
            for key in response_data:
                if isinstance(response_data[key], list):
                    return response_data[key]
        return response_data
    except Exception as e:
        print(f"AI 備課時發生錯誤 (無複習題): {e}")
        return None

# ... (get_tutor_feedback, start_dynamic_session, main 等函式與前版完全相同，此處省略以節省篇幅)
def get_tutor_feedback(chinese_sentence, user_translation):
    # (此函式與前版相同，直接沿用)
    system_prompt = f"""
    你是一位專業且有耐心的英文家教。你的任務是分析學生從中文翻譯到英文的答案。
    你的回覆必須遵循以下格式：
    1.  第一行必須是錯誤分類，格式為 `[分類]: <類型>`。
    2.  從第二行開始，才是你給學生的完整教學回饋。
    原始中文句子是："{chinese_sentence}"
    """
    user_prompt = f"這是我的翻譯：「{user_translation}」。請幫我看看，謝謝！"

    # 【監控點 5】
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
            temperature=0.3, max_tokens=600
        )
        response_content = response.choices[0].message.content.strip()

        # 【監控點 6】
        if MONITOR_MODE:
            print("\n" + "*"*20 + " AI 批改 OUTPUT " + "*"*20)
            print(response_content)
            print("*"*56 + "\n")

        lines = response_content.split('\n')
        category = "未分類"
        if lines and lines[0].startswith("[分類]:"):
            category = lines[0].replace("[分類]:", "").strip()
            notes = "\n".join(lines[1:]).strip()
        else:
            notes = response_content
        return category, notes
    except Exception as e:
        return "錯誤", f"批改時出錯：{e}"


def start_dynamic_session():
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
        sentence = question_data['new_sentence']
        print(f"請翻譯：{sentence}")
        
        user_translation = input("你的翻譯: ")
        if user_translation.strip().lower() == 'exit':
            print("\n已提前結束本輪練習。")
            return
            
        category, feedback = get_tutor_feedback(sentence, user_translation)
        
        print("\n--- 🎓 家教點評 ---")
        print(feedback)
        
        original_mistake_id = question_data.get('original_mistake_id')
        if category == '翻譯正確':
            if question_data['type'] == 'review' and original_mistake_id:
                original_record = next((r for r in due_reviews if r[0] == original_mistake_id), None)
                if original_record:
                    review_count, ef = original_record[5], original_record[6]
                    update_review_schedule(original_mistake_id, review_count, ef)
        else:
            add_mistake(sentence, user_translation, feedback, category, original_mistake_id=original_mistake_id)
            
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