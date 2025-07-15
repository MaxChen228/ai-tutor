import os
import openai
import datetime
import random
import json
import psycopg2 # 引入 PostgreSQL 驅動
import psycopg2.extras # 引入用於字典 cursor 的額外功能

# --- 核心學習參數 (可調整) ---
SESSION_SIZE = 2
REVIEW_RATIO = 0.5
MONITOR_MODE = True

# --- 資料庫設定與管理 ---
# 從環境變數讀取 Render 提供的資料庫連接 URL
DATABASE_URL = os.environ.get('DATABASE_URL')

try:
    with open("翻譯句型.md", "r", encoding="utf-8") as f:
        translation_patterns = f.read()
except FileNotFoundError:
    print("錯誤：找不到 `翻譯句型.md` 檔案。請確保檔案與主程式在同一個資料夾。")
    translation_patterns = "（文法書讀取失敗）"

def get_db_connection():
    """建立並回傳一個新的 PostgreSQL 資料庫連線。"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        print(f"資料庫連接失敗: {e}")
        print("請確保您已在 Render 環境變數中正確設定了 'DATABASE_URL'。")
        exit()

def init_db():
    """
    【v5.4 PostgreSQL 版】: 初始化 PostgreSQL 資料庫和表格。
    """
    conn = get_db_connection()
    # 使用 with 陳述式可以確保 cursor 和連線在使用後自動關閉
    with conn.cursor() as cursor:
        print("正在檢查並初始化 PostgreSQL 資料庫...")

        # SERIAL PRIMARY KEY 是 PostgreSQL 的自增主鍵
        # TIMESTAMPTZ 是帶有時區的標準時間戳格式
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_events (
            id SERIAL PRIMARY KEY,
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
            timestamp TIMESTAMPTZ NOT NULL
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_points (
            id SERIAL PRIMARY KEY,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            correct_phrase TEXT NOT NULL UNIQUE,
            explanation TEXT,
            user_context_sentence TEXT,
            incorrect_phrase_in_context TEXT,
            mastery_level REAL DEFAULT 0.0,
            mistake_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            last_reviewed_on TIMESTAMPTZ,
            next_review_date DATE
        );
        """)
    conn.commit()
    conn.close()
    print("資料庫表格已準備就緒。")

def add_mistake(question_data, user_answer, feedback_data):
    """
    【v5.4 PostgreSQL 版】: 將學習事件和知識點弱點存入 PostgreSQL。
    參數風格從 '?' 改為 '%s'。
    """
    conn = get_db_connection()
    with conn.cursor() as cursor:
        is_correct = feedback_data.get('is_generally_correct', False)
        feedback_json = json.dumps(feedback_data, ensure_ascii=False, indent=2)
        chinese = question_data.get('new_sentence', '（題目文字遺失）')
        q_type = question_data.get('type', 'new')
        source_id = question_data.get('original_mistake_id')
        
        # ... (決定 primary_error_category 的邏輯不變) ...
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

        # 使用 %s 作為參數佔位符
        cursor.execute(
            """
            INSERT INTO learning_events 
            (question_type, source_mistake_id, chinese_sentence, user_answer, is_correct, 
            error_category, error_subcategory, ai_feedback_json, timestamp) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (q_type, source_id, chinese, user_answer, is_correct, 
            primary_error_category, primary_error_subcategory, 
            feedback_json, datetime.datetime.now(datetime.timezone.utc))
        )
        
        if not is_correct and error_analysis:
            print("\n正在更新您的具體知識點弱點分析...")
            for error in error_analysis:
                category = error.get('error_type')
                subcategory = error.get('error_subtype')
                correct_phrase = error.get('correction')
                explanation = error.get('explanation')
                incorrect_phrase = error.get('original_phrase')
                
                if not category or not subcategory or not correct_phrase:
                    continue

                # 使用 %s 作為參數佔位符
                cursor.execute("SELECT id, mastery_level FROM knowledge_points WHERE correct_phrase = %s", (correct_phrase,))
                point = cursor.fetchone()
                severity_penalty = 0.5 if error.get('severity') == 'major' else 0.2

                if point:
                    new_mastery_level = max(0, point[1] - severity_penalty)
                    cursor.execute(
                        """
                        UPDATE knowledge_points 
                        SET mistake_count = mistake_count + 1, mastery_level = %s, user_context_sentence = %s, incorrect_phrase_in_context = %s, last_reviewed_on = %s, next_review_date = %s
                        WHERE id = %s
                        """,
                        (new_mastery_level, user_answer, incorrect_phrase, datetime.datetime.now(datetime.timezone.utc), datetime.date.today() + datetime.timedelta(days=1), point[0])
                    )
                    print(f"  - 已更新弱點：[{correct_phrase}]，熟練度下降。")
                else:
                    cursor.execute(
                        """
                        INSERT INTO knowledge_points (category, subcategory, correct_phrase, explanation, user_context_sentence, incorrect_phrase_in_context, mistake_count, mastery_level, last_reviewed_on, next_review_date)
                        VALUES (%s, %s, %s, %s, %s, %s, 1, 0.0, %s, %s)
                        """,
                        (category, subcategory, correct_phrase, explanation, user_answer, incorrect_phrase, datetime.datetime.now(datetime.timezone.utc), datetime.date.today() + datetime.timedelta(days=1))
                    )
                    print(f"  - 已發現新弱點：[{correct_phrase}]，已加入複習計畫。")

    conn.commit()
    conn.close()

    if not is_correct:
        print(f"\n(本句主要錯誤已歸檔：{primary_error_category} - {primary_error_subcategory})")

# --- AI 功能函式 (這部分完全不需要修改，因為它們不直接操作資料庫) ---
try:
    client = openai.OpenAI()
except openai.OpenAIError:
    print("錯誤：OPENAI_API_KEY 環境變數未設定或無效。")
    exit()

def generate_question_batch(weak_points_str, num_review):
    # ... (此函式內容維持原樣)
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
    # ... (後續的 try/except 邏輯維持原樣) ...
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
        response_data = json.loads(response_content)
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

def generate_new_question_batch(num_new):
    # ... (此函式內容維持原樣)
    system_prompt = f"""
    你是一位為台灣大學入學考試（學測）設計英文翻譯題的資深命題委員。你的任務是根據一份「句型文法書」，設計出 {num_new} 題全新的、具有挑戰性的翻譯考題。

    **你的核心工作原則：**
    1.  **權威教材**：「句型文法書」是你唯一的出題依據。
    2.  **【重要指令】輸出格式**：你必須嚴格回傳一個 JSON 物件，其根部必須有一個名為 "questions" 的 key，其 value 是一個包含 {num_new} 個問題物件的列表。每個問題物件都必須有一個 `new_sentence` 的 key，其 value 是你設計的【中文】考題。
    
    範例格式:
    {{
        "questions": [
            {{ "new_sentence": "直到深夜，這位科學家才意識到那個看似微不足道的實驗誤差，為他提供了關鍵線索。" }},
            {{ "new_sentence": "現代社會中，我們再怎麼強調培養批判性思考能力的重要性也不為過。" }}
        ]
    }}
    ---
    **【句型文法書 (你的出題武器庫)】**
    {translation_patterns}
    """
    user_prompt = f"請給我 {num_new} 題全新的題目。請務必記得，在輸出的 JSON 中，`new_sentence` 欄位的值必須是中文句子。"
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
        response_data = json.loads(response_content)
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
        print(f"AI 備課時發生錯誤 (無複習題): {e}")
        return None

def get_tutor_feedback(chinese_sentence, user_translation):
    # ... (此函式內容維持原樣)
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
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
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
        return {}


def update_knowledge_point_mastery(point_id, current_mastery):
    """
    【v5.4 PostgreSQL 版】: 更新答對的知識點熟練度。
    """
    new_mastery_level = min(5.0, current_mastery + 0.25)
    interval_days = max(1, round(2 ** new_mastery_level))
    next_review_date = datetime.date.today() + datetime.timedelta(days=interval_days)
    
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute(
            """
            UPDATE knowledge_points 
            SET mastery_level = %s, correct_count = correct_count + 1, next_review_date = %s 
            WHERE id = %s
            """,
            (new_mastery_level, next_review_date, point_id)
        )
    conn.commit()
    conn.close()
    print(f"(太棒了！這個觀念我們安排在 {interval_days} 天後複習。)")

def get_due_knowledge_points(limit):
    """
    【v5.4 PostgreSQL 版】: 獲取到期且掌握度最低的「知識點」。
    """
    conn = get_db_connection()
    # 使用 DictCursor 讓回傳的結果可以用欄位名稱存取
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        today = datetime.date.today()
        cursor.execute(
            """
            SELECT * FROM knowledge_points 
            WHERE next_review_date <= %s 
            ORDER BY mastery_level ASC, last_reviewed_on ASC
            LIMIT %s
            """,
            (today, limit)
        )
        points = cursor.fetchall()
    conn.close()
    return points

def start_dynamic_session():
    """
    v5.0 版更新：圍繞「知識點」來建構整個學習流程。
    【v5.4 PostgreSQL 版】: 資料庫操作已全面更新。
    """
    print(f"\n--- 🚀 準備開始新的一輪學習 (共 {SESSION_SIZE} 題) ---")

    num_review_questions = int(SESSION_SIZE * REVIEW_RATIO)
    due_knowledge_points = get_due_knowledge_points(num_review_questions)
    actual_num_review = len(due_knowledge_points)
    num_new_questions = SESSION_SIZE - actual_num_review
    
    questions_to_ask = []
    print("AI 老師正在為您備課，請稍候...")

    if actual_num_review > 0:
        weak_points_for_prompt = [
            f"- 錯誤分類: {p['category']} -> {p['subcategory']}\n  正確用法: \"{p['correct_phrase']}\"\n  核心觀念: {p['explanation']}"
            for p in due_knowledge_points
        ]
        weak_points_str = "\n\n".join(weak_points_for_prompt)
        print(f"正在針對您以下的 {actual_num_review} 個具體弱點設計考題：\n{weak_points_str}")
        
        review_questions = generate_question_batch(weak_points_str, actual_num_review)
        if review_questions:
            for q, point in zip(review_questions, due_knowledge_points):
                if isinstance(q, dict):
                    q['type'] = 'review'
                    q['knowledge_point_id'] = point['id']
                    q['mastery_level'] = point['mastery_level']
            questions_to_ask.extend(review_questions)

    if num_new_questions > 0:
        print(f"正在為您準備 {num_new_questions} 個全新挑戰...")
        new_questions = generate_new_question_batch(num_new_questions)
        if new_questions:
            for q in new_questions:
                if isinstance(q, dict):
                    q['type'] = 'new'
            questions_to_ask.extend(new_questions)
    
    if not questions_to_ask:
        print("AI 備課失敗或無題目可學，無法開始本輪練習。")
        return
        
    random.shuffle(questions_to_ask)
    print("\nAI 老師已備課完成！準備好了嗎？")
    input("按 Enter 鍵開始上課...")

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

        add_mistake(question_data, user_answer, feedback_data)
        
        if question_data.get('type') == 'review' and feedback_data.get('is_generally_correct'):
            point_id = question_data.get('knowledge_point_id')
            mastery = question_data.get('mastery_level')
            if point_id is not None and mastery is not None:
                update_knowledge_point_mastery(point_id, mastery)

        if i < len(questions_to_ask):
            input("\n按 Enter 鍵繼續下一題...")

    print("\n--- 🎉 恭喜！完成了本輪所有練習！ ---")

def main():
    """
    主執行函式，用於本地端測試。
    """
    # 首次執行時初始化資料庫
    if DATABASE_URL:
        init_db()
    else:
        print("錯誤：未設定 DATABASE_URL 環境變數，無法啟動。")
        return

    while True:
        print("\n--- 🌟 動態 AI 英文家教 (v5.4) 🌟 ---")
        print("1. 開始一輪智慧學習")
        print("2. （功能待開發：查看儀表板）")
        print("3. 結束程式")
        choice = input("請輸入你的選擇 (1/3): ")

        if choice == '1':
            start_dynamic_session()
        elif choice == '3':
            print("\n掰掰，下次見！👋")
            break
        else:
            print("\n無效的輸入，請重新輸入。")

if __name__ == '__main__':
    # 這部分主要用於本地端測試，Render 部署時不會執行
    main()