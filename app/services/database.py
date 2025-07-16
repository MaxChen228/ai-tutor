# app/services/database.py

import os
import datetime
import json
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """建立並回傳一個新的 PostgreSQL 資料庫連線。"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except psycopg2.OperationalError as e:
        print(f"資料庫連接失敗: {e}")
        exit()

def init_db():
    """初始化 PostgreSQL 資料庫和表格。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        print("正在檢查並初始化 PostgreSQL 資料庫...")
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
            key_point_summary TEXT,
            mastery_level REAL DEFAULT 0.0,
            mistake_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            last_reviewed_on TIMESTAMPTZ,
            next_review_date DATE,
            is_archived BOOLEAN DEFAULT FALSE
        );
        """)
        
        # 【新增】檢查 is_archived 欄位是否存在，如果不存在就加上
        cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='knowledge_points' AND column_name='is_archived'
            ) THEN
                ALTER TABLE knowledge_points ADD COLUMN is_archived BOOLEAN DEFAULT FALSE;
                RAISE NOTICE '欄位 is_archived 已成功加入 knowledge_points 表格。';
            END IF;
        END $$;
        """)

    conn.commit()
    conn.close()
    print("資料庫表格已準備就緒。")

def add_mistake(question_data, user_answer, feedback_data, exclude_phrase=None):
    """將學習事件和知識點弱點存入 PostgreSQL。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        is_correct = feedback_data.get('is_generally_correct', False)
        feedback_json = json.dumps(feedback_data, ensure_ascii=False, indent=2)
        chinese = question_data.get('new_sentence', '（題目文字遺失）')
        q_type = question_data.get('type', 'new')
        source_id = question_data.get('original_mistake_id')
        
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
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (q_type, source_id, chinese, user_answer, is_correct, 
            primary_error_category, primary_error_subcategory, 
            feedback_json, datetime.datetime.now(datetime.timezone.utc))
        )
        
        if not is_correct and error_analysis:
            print("\n正在更新您的具體知識點弱點分析...")
            for error in error_analysis:
                correct_phrase = error.get('correction')
                if exclude_phrase and correct_phrase == exclude_phrase:
                    print(f"  - (忽略已處理的複習點: {exclude_phrase})")
                    continue
                
                category = error.get('error_type')
                subcategory = error.get('error_subtype')
                explanation = error.get('explanation')
                incorrect_phrase = error.get('original_phrase')
                summary = error.get('key_point_summary', '核心觀念')
                
                if not category or not subcategory or not correct_phrase:
                    continue

                cursor.execute("SELECT id, mastery_level FROM knowledge_points WHERE correct_phrase = %s", (correct_phrase,))
                point = cursor.fetchone()
                severity_penalty = 0.5 if error.get('severity') == 'major' else 0.2

                if point:
                    new_mastery_level = max(0, point[1] - severity_penalty)
                    cursor.execute(
                        """
                        UPDATE knowledge_points 
                        SET mistake_count = mistake_count + 1, mastery_level = %s, user_context_sentence = %s, incorrect_phrase_in_context = %s, key_point_summary = %s, last_reviewed_on = %s, next_review_date = %s
                        WHERE id = %s
                        """,
                        (new_mastery_level, user_answer, incorrect_phrase, summary, datetime.datetime.now(datetime.timezone.utc), datetime.date.today() + datetime.timedelta(days=1), point[0])
                    )
                    print(f"  - 已更新弱點：[{summary}]，熟練度下降。")
                else:
                    cursor.execute(
                        """
                        INSERT INTO knowledge_points (category, subcategory, correct_phrase, explanation, user_context_sentence, incorrect_phrase_in_context, key_point_summary, mistake_count, mastery_level, last_reviewed_on, next_review_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 0.0, %s, %s)
                        """,
                        (category, subcategory, correct_phrase, explanation, user_answer, incorrect_phrase, summary, datetime.datetime.now(datetime.timezone.utc), datetime.date.today() + datetime.timedelta(days=1))
                    )
                    print(f"  - 已發現新弱點：[{summary}]，已加入複習計畫。")
    conn.commit()
    conn.close()
    if not is_correct:
        print(f"\n(本句主要錯誤已歸檔：{primary_error_category} - {primary_error_subcategory})")

def update_knowledge_point_mastery(point_id, current_mastery):
    """更新答對的知識點熟練度。"""
    print(f"[DEBUG] update_knowledge_point_mastery 函式被呼叫。")
    print(f"[DEBUG] 準備更新知識點 ID: {point_id} (類型: {type(point_id)}), 目前熟練度: {current_mastery}")
    
    if point_id is None:
        print(f"⚠️ 嚴重警告：傳入的 point_id 為 None，無法執行更新。請檢查前端回傳的資料。")
        return

    new_mastery_level = min(5.0, current_mastery + 0.25)
    interval_days = max(1, round(2 ** new_mastery_level))
    next_review_date = datetime.date.today() + datetime.timedelta(days=interval_days)
    
    conn = get_db_connection()
    updated_rows = 0
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE knowledge_points 
                SET mastery_level = %s, correct_count = correct_count + 1, next_review_date = %s 
                WHERE id = %s
                """,
                (new_mastery_level, next_review_date, int(point_id))
            )
            updated_rows = cursor.rowcount
            conn.commit()
    except Exception as e:
        print(f"[ERROR] 更新 knowledge_point 時發生資料庫錯誤: {e}")
        conn.rollback()
    finally:
        conn.close()

    if updated_rows > 0:
        print(f"✅ 知識點 ID: {point_id} 已成功更新！影響行數: {updated_rows}。安排在 {interval_days} 天後複習。")
    else:
        print(f"⚠️ 警告：更新知識點 ID: {point_id} 時，資料庫中沒有找到對應的紀錄，更新失敗！影響行數: {updated_rows}。")

def get_due_knowledge_points(limit):
    """根據台灣時區 (UTC+8) 來獲取當天到期的知識點。"""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        utc_now = datetime.datetime.now(datetime.timezone.utc)
        taipei_offset = datetime.timedelta(hours=8)
        taipei_now = utc_now + taipei_offset
        today_in_taipei = taipei_now.date()
        print(f"[API] 伺服器UTC日期: {utc_now.date()} | 校準後台北日期: {today_in_taipei}")
        cursor.execute(
            """
            SELECT * FROM knowledge_points 
            WHERE next_review_date <= %s AND is_archived = FALSE
            ORDER BY mastery_level ASC, last_reviewed_on ASC
            LIMIT %s
            """,
            (today_in_taipei, limit)
        )
        points = cursor.fetchall()
    conn.close()
    return points

def get_daily_activity(year, month):
    """查詢特定月份的每日學習活動數量。"""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        query = """
        SELECT DATE_TRUNC('day', timestamp AT TIME ZONE 'UTC')::date AS activity_date, COUNT(id) AS activity_count
        FROM learning_events
        WHERE EXTRACT(YEAR FROM timestamp AT TIME ZONE 'UTC') = %s AND EXTRACT(MONTH FROM timestamp AT TIME ZONE 'UTC') = %s
        GROUP BY activity_date ORDER BY activity_date;
        """
        cursor.execute(query, (year, month))
        activities = cursor.fetchall()
    conn.close()
    heatmap_data = {activity['activity_date'].isoformat(): activity['activity_count'] for activity in activities}
    return heatmap_data

def get_daily_details(activity_date):
    """查詢特定日期的學習詳情，並區分為「已複習」和「新學習」。"""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        query = """
        SELECT question_type, ai_feedback_json, response_time
        FROM learning_events
        WHERE DATE(timestamp AT TIME ZONE 'UTC' + INTERVAL '8 hours') = %s;
        """
        cursor.execute(query, (activity_date,))
        events = cursor.fetchall()
    conn.close()
    total_seconds, reviewed_points, new_points = 0, {}, {}
    for event in events:
        if event['response_time']:
            try:
                total_seconds += float(event['response_time'])
            except (ValueError, TypeError): pass
        if event['ai_feedback_json']:
            try:
                feedback = json.loads(event['ai_feedback_json'])
                if not feedback.get('is_generally_correct') and feedback.get('error_analysis'):
                    for error in feedback['error_analysis']:
                        summary = error.get('key_point_summary')
                        if summary:
                            if event['question_type'] == 'review':
                                reviewed_points[summary] = reviewed_points.get(summary, 0) + 1
                            else:
                                new_points[summary] = new_points.get(summary, 0) + 1
            except json.JSONDecodeError: continue
    formatted_reviewed = [{"summary": s, "count": c} for s, c in reviewed_points.items()]
    formatted_new = [{"summary": s, "count": c} for s, c in new_points.items()]
    return {"total_learning_time_seconds": int(total_seconds), "reviewed_knowledge_points": formatted_reviewed, "new_knowledge_points": formatted_new}

# --- 【v5.17 新增】管理知識點專用的函式 ---

def update_knowledge_point_details(point_id, details):
    """更新單一知識點的詳細資訊。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        # 這裡可以根據前端傳來的 `details` dictionary 動態建立 UPDATE 語句
        # 為了安全起見，我們先只允許更新特定欄位
        allowed_fields = ['correct_phrase', 'explanation', 'key_point_summary', 'category', 'subcategory']
        update_fields = []
        update_values = []
        
        for key, value in details.items():
            if key in allowed_fields:
                update_fields.append(f"{key} = %s")
                update_values.append(value)
        
        if not update_fields:
            return False, "沒有任何允許更新的欄位。"

        update_values.append(point_id)
        query = f"UPDATE knowledge_points SET {', '.join(update_fields)} WHERE id = %s"
        
        cursor.execute(query, tuple(update_values))
        updated_rows = cursor.rowcount
        conn.commit()
    conn.close()
    return updated_rows > 0, f"成功更新 {updated_rows} 個知識點。"

def set_knowledge_point_archived_status(point_id, is_archived):
    """設定知識點的封存狀態。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("UPDATE knowledge_points SET is_archived = %s WHERE id = %s", (is_archived, point_id))
        updated_rows = cursor.rowcount
        conn.commit()
    conn.close()
    return updated_rows > 0

def delete_knowledge_point(point_id):
    """根據 ID 刪除一個知識點。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM knowledge_points WHERE id = %s", (point_id,))
        deleted_rows = cursor.rowcount
        conn.commit()
    conn.close()
    return deleted_rows > 0


# --- 【v5.17 修改】路由檔案需要用到的輔助查詢函式 ---

def get_knowledge_point_phrase(point_id):
    """根據 ID 獲取單一知識點的 correct_phrase。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT correct_phrase FROM knowledge_points WHERE id = %s", (point_id,))
        result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def get_all_knowledge_points():
    """獲取所有未封存的知識點，用於儀表板。"""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("""
            SELECT id, category, subcategory, correct_phrase, explanation, 
                   user_context_sentence, incorrect_phrase_in_context, 
                   key_point_summary, mastery_level, mistake_count, 
                   correct_count, next_review_date 
            FROM knowledge_points 
            WHERE is_archived = FALSE
            ORDER BY mastery_level ASC, mistake_count DESC
        """)
        points_raw = cursor.fetchall()
    conn.close()
    points_dict = []
    for row in points_raw:
        row_dict = dict(row)
        if row_dict.get('next_review_date'):
            row_dict['next_review_date'] = row_dict['next_review_date'].isoformat()
        points_dict.append(row_dict)
    return points_dict

def get_archived_knowledge_points():
    """獲取所有已封存的知識點。"""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cursor:
        cursor.execute("""
            SELECT id, category, subcategory, correct_phrase, explanation, 
                   user_context_sentence, incorrect_phrase_in_context, 
                   key_point_summary, mastery_level, mistake_count, 
                   correct_count, next_review_date 
            FROM knowledge_points 
            WHERE is_archived = TRUE
            ORDER BY last_reviewed_on DESC
        """)
        points_raw = cursor.fetchall()
    conn.close()
    points_dict = []
    for row in points_raw:
        row_dict = dict(row)
        if row_dict.get('next_review_date'):
            row_dict['next_review_date'] = row_dict['next_review_date'].isoformat()
        points_dict.append(row_dict)
    return points_dict

def get_flashcards_by_types(types_to_fetch):
    """根據錯誤類型獲取單字卡。"""
    flashcards, unique_checker = [], set()
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT ai_feedback_json FROM learning_events WHERE is_correct = false")
        all_events = cursor.fetchall()
    conn.close()
    for event in all_events:
        if not event[0]: continue
        feedback_data = json.loads(event[0])
        for error in feedback_data.get('error_analysis', []):
            error_type = error.get('error_type')
            if error_type and error_type in types_to_fetch:
                card_front = error.get('original_phrase', 'N/A')
                card_back_correction = error.get('correction', 'N/A')
                card_identifier = (card_front, card_back_correction)
                if card_identifier in unique_checker: continue
                unique_checker.add(card_identifier)
                flashcards.append({
                    "front": card_front,
                    "back_correction": card_back_correction,
                    "back_explanation": error.get('explanation', 'N/A'),
                    "category": error_type
                })
    return flashcards


def batch_update_knowledge_points_archived_status(point_ids, is_archived):
    """
    根據 ID 列表，批次更新多個知識點的封存狀態。
    """
    if not point_ids:
        return 0  # 如果傳入空的 ID 列表，直接返回

    conn = get_db_connection()
    with conn.cursor() as cursor:
        # 使用 ANY(%s) 語法可以高效地處理 ID 列表
        query = "UPDATE knowledge_points SET is_archived = %s WHERE id = ANY(%s)"
        cursor.execute(query, (is_archived, point_ids))
        updated_rows = cursor.rowcount
        conn.commit()
    conn.close()
    return updated_rows