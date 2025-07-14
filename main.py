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

def init_db():
    """
    v5.0 版更新：初始化資料庫。
    - 建立 learning_events 表格，用於儲存所有原始學習紀錄。
    - 建立全新的 knowledge_points 表格，用於追蹤每個獨立知識點的掌握度。
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    print("正在檢查並初始化資料庫...")

    # 1. 學習事件日誌 (保留不變，作為原始紀錄)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS learning_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_type TEXT NOT NULL,
        source_mistake_id INTEGER,
        chinese_sentence TEXT NOT NULL,
        intended_pattern TEXT,
        user_answer TEXT,
        is_correct BOOLEAN NOT NULL,
        response_time REAL,
        self_assessment_score INTEGER,
        error_category TEXT,
        error_subcategory TEXT,
        ai_feedback_json TEXT,
        difficulty REAL,
        stability REAL,
        next_review_date DATE,
        timestamp DATETIME NOT NULL
    )
    """)
    
    # 2. 全新的「知識點」核心表格
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_points (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT NOT NULL,
        subcategory TEXT NOT NULL,
        mastery_level REAL DEFAULT 0.0,
        mistake_count INTEGER DEFAULT 0,
        correct_count INTEGER DEFAULT 0,
        last_reviewed_on DATETIME,
        next_review_date DATE,
        UNIQUE(category, subcategory)
    )
    """)

    conn.commit()
    conn.close()
    print("資料庫 learning_events 和 knowledge_points 表格已準備就緒。")

def add_mistake(question_data, user_answer, feedback_data):
    """
    v5.0 版更新：儲存學習事件，並根據 AI 的詳細錯誤分析，更新 knowledge_points 表格。
    """
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()

    # --- 1. 儲存原始學習事件到 learning_events (作為日誌) ---
    is_correct = feedback_data.get('is_generally_correct', False)
    feedback_json = json.dumps(feedback_data, ensure_ascii=False, indent=2)
    chinese = question_data.get('new_sentence', '（題目文字遺失）')
    q_type = question_data.get('type', 'new')
    source_id = question_data.get('original_mistake_id')
    
    # 決定代表性錯誤 (用於舊欄位，方便快速瀏覽)
    primary_error_category = "翻譯正確"
    primary_error_subcategory = "無"
    error_analysis = feedback_data.get('error_analysis', [])
    if error_analysis:
        major_errors = [e for e in error_analysis if e.get('severity') == 'major']
        if major_errors:
            primary_error_category = major_errors[0].get('error_type', '分類錯誤')
            primary_error_subcategory = major_errors[0].get('error_subtype', '子分類錯誤')
        else:
            primary_error_category = error_analysis[0].get('error_type', '分類錯誤')
            primary_error_subcategory = error_analysis[0].get('error_subtype', '子分類錯誤')

    cursor.execute(
        """
        INSERT INTO learning_events 
        (question_type, source_mistake_id, chinese_sentence, user_answer, is_correct, 
        error_category, error_subcategory, ai_feedback_json, timestamp) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (q_type, source_id, chinese, user_answer, is_correct, 
        primary_error_category, primary_error_subcategory, 
        feedback_json, datetime.datetime.now())
    )
    
    # --- 2. 更新 knowledge_points 核心表格 ---
    if not is_correct and error_analysis:
        print("\n正在更新您的知識點弱點分析...")
        for error in error_analysis:
            category = error.get('error_type')
            subcategory = error.get('error_subtype')
            
            if not category or not subcategory:
                continue

            # 檢查知識點是否存在
            cursor.execute("SELECT * FROM knowledge_points WHERE category = ? AND subcategory = ?", (category, subcategory))
            point = cursor.fetchone()
            
            # 計算熟練度懲罰 (主要錯誤懲罰更重)
            severity_penalty = 0.5 if error.get('severity') == 'major' else 0.2

            if point:
                # 更新現有知識點：增加錯誤次數，降低熟練度
                new_mastery_level = max(0, point[3] - severity_penalty) # mastery_level 在 point[3]
                cursor.execute(
                    """
                    UPDATE knowledge_points 
                    SET mistake_count = mistake_count + 1, mastery_level = ?, last_reviewed_on = ?, next_review_date = ?
                    WHERE id = ?
                    """,
                    (new_mastery_level, datetime.datetime.now(), datetime.date.today() + datetime.timedelta(days=1), point[0])
                )
                print(f"  - 已記錄弱點：[{category} - {subcategory}]，熟練度下降。")
            else:
                # 新增知識點紀錄
                cursor.execute(
                    """
                    INSERT INTO knowledge_points (category, subcategory, mistake_count, mastery_level, last_reviewed_on, next_review_date)
                    VALUES (?, ?, 1, 0.0, ?, ?)
                    """,
                    (category, subcategory, datetime.datetime.now(), datetime.date.today() + datetime.timedelta(days=1))
                )
                print(f"  - 已發現新弱點：[{category} - {subcategory}]，已加入複習計畫。")

    conn.commit()
    conn.close()

    if not is_correct:
        print(f"\n(本句主要錯誤已歸檔：{primary_error_category} - {primary_error_subcategory})")

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

# 位於 main.py

def generate_question_batch(weak_points_str, num_review):
    """
    v5.0 版更新：(有複習題時使用) 根據學生的「知識點弱點報告」來生成一整輪的題目。
    """
    system_prompt = f"""
    你是一位為台灣大學入學考試（學測）設計英文翻譯題的資深命題委員。你的核心任務是根據一份指定的「句型文法書」以及一份關於學生的「個人知識點弱點分析報告」，為他量身打造 {num_review} 題複習考題。

    **你的核心工作原則：**
    1.  **深度分析弱點**：你必須仔細分析下方報告中列出的學生弱點。你的每一道題都必須精準地針對報告中的一個或多個知識點進行測驗。
    2.  **概念重生，而非重複**：絕對不要出重複的句子。你的任務是「換句話說」，用全新的情境和單字來考驗同一個核心觀念。
    3.  **權威教材**：「句型文法書」是你唯一的出題依據，你必須從中尋找靈感來結合學生的弱點。
    4.  **【重要指令】輸出格式**：你必須嚴格按照指定的 JSON 格式輸出。在 JSON 的 `new_sentence` 欄位中，**必須、且只能填入你設計的【中文】考題句子**。

    ---
    **【句型文法書 (你的出題武器庫)】**
    {translation_patterns}
    ---
    **【學生個人知識點弱點分析報告】**
    {weak_points_str}
    """
    user_prompt = f"請根據以上資料，為我生成 {num_review} 題針對上述弱點的複習題。請務必記得，在輸出的 JSON 中，`new_sentence` 欄位的值必須是中文句子。"

    if MONITOR_MODE:
        print("\n" + "="*20 + " AI 備課 (弱點) INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*60 + "\n")

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
            print("\n" + "*"*20 + " AI 備課 (弱點) OUTPUT " + "*"*20)
            print(response_content)
            print("*"*62 + "\n")
        
        response_data = json.loads(response_content)
        if isinstance(response_data, dict):
            for value in response_data.values():
                if isinstance(value, list):
                    return value
            return list(response_data.values())
        elif isinstance(response_data, list):
            return response_data
            
        print("警告：AI 回傳的備課資料格式非預期的字典或清單。")
        return None

    except Exception as e:
        print(f"AI 備課時發生錯誤 (有複習題): {e}")
        return None

def generate_new_question_batch(num_new):
    """
    (僅用於無複習題時) AI 生成指定數量的新題目。
    (此函式在 v5.0 中 prompt 維持不變，因為它沒有弱點報告可參考)
    """
    system_prompt = f"""
    你是一位為台灣大學入學考試（學測）設計英文翻譯題的資深命題委員。你的任務是根據一份指定的「句型文法書」與「頂尖命題範例分析」，設計出 {num_new} 題全新的、具有挑戰性的翻譯考題。

    **你的核心工作原則：**
    1.  **深度學習範例**：你必須深度學習下方的「頂尖命題範例分析」，你的出題風格、難度與巧思都應向這些範例看齊。
    2.  **絕對權威的教材**：「句型文法書」是你唯一的出題依據。
    3.  **【重要指令】輸出格式**：你必須嚴格按照指定的 JSON 格式輸出。在 JSON 的 `new_sentence` 欄位中，**必須、且只能填入你設計的【中文】考題句子**。

    ---
    **【頂尖命題範例分析 (你必須模仿的思維模式)】**
    * **範例一**: 「直到深夜，這位科學家才意識到，正是這個看似微不足道的實驗誤差，為他的突破性研究提供了關鍵線索。」(結合倒裝與分裂句)
    * **範例二**: 「現代社會中，我們再怎麼強調培養批判性思考能力的重要性也不為過，以免在資訊爆炸的時代迷失方向。」(結合 'cannot over-V' 與 'lest')

    ---
    **【句型文法書 (你的出題武器庫)】**
    {translation_patterns}
    """
    user_prompt = f"請給我 {num_new} 題全新的題目。請務必記得，在輸出的 JSON 中，`new_sentence` 欄位的值必須是中文句子。"

    if MONITOR_MODE:
        print("\n" + "="*20 + " AI 備課 (新) INPUT " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*59 + "\n")
        
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
            print("\n" + "*"*20 + " AI 備課 (新) OUTPUT " + "*"*20)
            print(response_content)
            print("*"*60 + "\n")
        
        response_data = json.loads(response_content)
        if isinstance(response_data, dict):
            for value in response_data.values():
                if isinstance(value, list):
                    return value
            return list(response_data.values())
        elif isinstance(response_data, list):
            return response_data
            
        print("警告：AI 回傳的備課資料格式非預期的字典或清單。")
        return None

    except Exception as e:
        print(f"AI 備課時發生錯誤 (無複習題): {e}")
        return None

def get_tutor_feedback(chinese_sentence, user_translation):
    """
    獲取家教批改的回饋。
    v4.5 版更新：命令 AI 回傳包含「錯誤分析清單」的、更精細的結構化 JSON 物件。
    """
    system_prompt = f"""
    你是一位極其細心、專業且有耐心的英文家教。你的任務是像批改作業一樣，逐字逐句分析學生從中文翻譯到英文的答案，並回傳一份結構化的 JSON 分析報告。

    **【重要指令】輸出格式**
    你必須嚴格回傳一個 JSON 物件，絕對不能包含 JSON 格式以外的任何文字。此 JSON 物件必須包含以下欄位：

    1.  `is_generally_correct`: (boolean) 綜合判斷，儘管有錯誤，學生的翻譯是否在整體語意上大致正確。
    2.  `overall_suggestion`: (string) 提供一個或多個整體最流暢、最道地的英文翻譯建議。
    3.  `error_analysis`: (array of objects) 一個清單，其中包含你找出的【所有】錯誤。如果沒有任何錯誤，請回傳一個空清單 `[]`。
        清單中的每一個物件都必須包含以下欄位：
        * `error_type`: (string) 從以下列表中選擇：`文法錯誤`, `單字選擇`, `慣用語不熟`, `語氣不當`, `句構問題`, `拼寫錯誤`, `贅字或漏字`。
        * `error_subtype`: (string) 請用 2-5 個字的專業術語，精準描述錯誤的核心觀念 (例如：「動詞時態」、「介系詞搭配」、「主詞動詞一致」)。
        * `original_phrase`: (string) 從學生答案中，精確地提取出錯誤的那個單字或片語。
        * `correction`: (string) 針對該錯誤片語，提供正確的寫法。
        * `explanation`: (string) 簡潔地解釋為什麼這是錯的，以及為什麼修正後是正確的。
        * `severity`: (string) 判斷此錯誤的嚴重性，分為 `major` (影響理解的結構性或語意錯誤) 或 `minor` (不影響理解的拼寫、單複數等小錯誤)。

    **原始中文句子是**："{chinese_sentence}"
    """
    user_prompt = f"這是我的翻譯：「{user_translation}」。請根據你的專業知識和上述指令，為我生成一份鉅細靡遺的 JSON 分析報告。"

    if MONITOR_MODE:
        print("\n" + "="*20 + " AI 批改 INPUT (v4.5) " + "="*20)
        print("--- SYSTEM PROMPT ---")
        print(system_prompt)
        print("\n--- USER PROMPT ---")
        print(user_prompt)
        print("="*64 + "\n")

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            response_format={"type": "json_object"}
        )
        response_content = response.choices[0].message.content

        if MONITOR_MODE:
            print("\n" + "*"*20 + " AI 批改 OUTPUT (v4.5) " + "*"*20)
            print(response_content)
            print("*"*62 + "\n")

        feedback_data = json.loads(response_content)
        return feedback_data

    except (json.JSONDecodeError, openai.APIError) as e:
        print(f"AI 批改或解析 JSON 時發生錯誤: {e}")
        return {
            "is_generally_correct": False,
            "overall_suggestion": "N/A",
            "error_analysis": [{
                "error_type": "系統錯誤",
                "error_subtype": "AI回覆格式錯誤",
                "original_phrase": "N/A",
                "correction": "N/A",
                "explanation": f"系統無法處理 AI 的回覆：{e}",
                "severity": "major"
            }]
        }
    except Exception as e:
         return {
            "is_generally_correct": False,
            "overall_suggestion": "N/A",
            "error_analysis": [{
                "error_type": "系統錯誤",
                "error_subtype": "未知錯誤",
                "original_phrase": "N/A",
                "correction": "N/A",
                "explanation": f"發生未知錯誤：{e}",
                "severity": "major"
            }]
        }

def update_knowledge_point_mastery(point_id, current_mastery):
    """
    v5.0 新函式：當複習題答對時，提升對應知識點的熟練度。
    這是一個簡化的熟練度增長模型。
    """
    # 簡單的增長公式：每次答對，熟練度提升 0.25 (最高為 5.0)
    new_mastery_level = min(5.0, current_mastery + 0.25)
    
    # 下次複習的間隔約等於 (熟練度 * 2) 的指數增長
    interval_days = max(1, round(2 ** new_mastery_level))
    next_review_date = datetime.date.today() + datetime.timedelta(days=interval_days)
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE knowledge_points 
        SET mastery_level = ?, correct_count = correct_count + 1, next_review_date = ? 
        WHERE id = ?
        """,
        (new_mastery_level, next_review_date, point_id)
    )
    conn.commit()
    conn.close()
    print(f"(太棒了！這個觀念我們安排在 {interval_days} 天後複習。)")

def get_due_knowledge_points(limit):
    """
    v5.0 新函式：不再獲取舊句子，而是獲取到期且掌握度最低的「知識點」。
    """
    conn = sqlite3.connect(DATABASE_FILE)
    # 讓回傳結果可以用欄位名稱存取
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    today = datetime.date.today()
    
    cursor.execute(
        """
        SELECT * FROM knowledge_points 
        WHERE next_review_date <= ? 
        ORDER BY mastery_level ASC, last_reviewed_on ASC
        LIMIT ?
        """,
        (today, limit)
    )
    points = cursor.fetchall()
    conn.close()
    return points

def start_dynamic_session():
    """
    v5.0 版更新：圍繞「知識點」來建構整個學習流程。
    """
    print(f"\n--- 🚀 準備開始新的一輪學習 (共 {SESSION_SIZE} 題) ---")

    # 1. 獲取最需要複習的「知識點」
    num_review_questions = int(SESSION_SIZE * REVIEW_RATIO)
    due_knowledge_points = get_due_knowledge_points(num_review_questions)
    actual_num_review = len(due_knowledge_points)
    num_new_questions = SESSION_SIZE - actual_num_review
    
    questions_to_ask = []
    print("AI 老師正在為您備課，請稍候...")

    # 2. 根據有無到期弱點，選擇不同的備課方式
    if actual_num_review > 0:
        # 將知識點格式化，傳給 AI
        weak_points_for_prompt = [f"- {p['category']}: {p['subcategory']}" for p in due_knowledge_points]
        weak_points_str = "\n".join(weak_points_for_prompt)
        print(f"正在針對您以下的 {actual_num_review} 個弱點設計考題：\n{weak_points_str}")
        
        # 讓 AI 生成複習題 (針對知識點)
        review_questions = generate_question_batch(weak_points_str, actual_num_review)
        if review_questions:
            # 為複習題打上標記，方便後續處理
            for q, point in zip(review_questions, due_knowledge_points):
                q['type'] = 'review'
                q['knowledge_point_id'] = point['id']
                q['mastery_level'] = point['mastery_level']
            questions_to_ask.extend(review_questions)

    if num_new_questions > 0:
        print(f"正在為您準備 {num_new_questions} 個全新挑戰...")
        new_questions = generate_new_question_batch(num_new_questions)
        if new_questions:
            # 為新題目打上標記
            for q in new_questions:
                q['type'] = 'new'
            questions_to_ask.extend(new_questions)
    
    if not questions_to_ask:
        print("AI 備課失敗或無題目可學，無法開始本輪練習。")
        return
        
    random.shuffle(questions_to_ask)
    print("\nAI 老師已備課完成！準備好了嗎？")
    input("按 Enter 鍵開始上課...")

    # 3. 【逐題上課】
    for i, question_data in enumerate(questions_to_ask, 1):
        print(f"\n--- 第 {i}/{len(questions_to_ask)} 題 ({question_data.get('type', '未知')}類型) ---")
        sentence = question_data.get('new_sentence', '（題目獲取失敗）')
        print(f"請翻譯：{sentence}")
        
        user_answer = input("你的翻譯: ")
        if user_answer.strip().lower() == 'exit':
            print("\n已提前結束本輪練習。")
            return
            
        feedback_data = get_tutor_feedback(sentence, user_answer)
        print("\n--- 🎓 家教點評 ---")
        print(f"整體建議翻譯：{feedback_data.get('overall_suggestion', '無法獲取建議翻譯。')}")

        # 無論對錯，都先儲存這筆學習紀錄，並更新犯錯的知識點
        add_mistake(question_data, user_answer, feedback_data)
        
        # 【核心複習邏輯】如果這是一道「複習題」且「答對了」
        if question_data.get('type') == 'review' and feedback_data.get('is_generally_correct'):
            point_id = question_data.get('knowledge_point_id')
            mastery = question_data.get('mastery_level')
            if point_id is not None and mastery is not None:
                update_knowledge_point_mastery(point_id, mastery)

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