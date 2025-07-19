import os
import psycopg
from psycopg.rows import dict_row
import datetime
import json

# 全域資料庫連接池
db_pool = None

def init_app(app):
    """初始化資料庫連接池。"""
    global db_pool
    try:
        conn_info = os.getenv("DATABASE_URL")
        if not conn_info:
            raise ValueError("DATABASE_URL 環境變數未設定")
        
        # 根據 DATABASE_URL 建立連接池設定
        db_pool = psycopg.conninfo.conninfo_to_dict(conn_info)
        print("✅ 資料庫服務初始化成功 (使用 psycopg v3 連接池)。")

    except Exception as e:
        print(f"❌ 資料庫連接池初始化失敗: {e}")
        db_pool = None

def get_db_connection():
    """從連接池獲取一個新的資料庫連接。"""
    if not db_pool:
        raise ConnectionError("資料庫未初始化或初始化失敗。")
    # row_factory=dict_row 讓查詢結果以字典形式返回 (取代舊的 DictCursor)
    return psycopg.connect(**db_pool, row_factory=dict_row)

def execute_query(query, params=None, fetch=None):
    """
    執行 SQL 查詢的統一函式。
    :param query: SQL 查詢語句
    :param params: 查詢參數
    :param fetch: 'one' (獲取單筆), 'all' (獲取所有), None (執行不返回結果的命令)
    """
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            
            if fetch == 'one':
                result = cur.fetchone()
            elif fetch == 'all':
                result = cur.fetchall()
            else:
                conn.commit()
                result = cur.rowcount # 返回受影響的行數
            
            return result
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"❌ 資料庫查詢失敗: {e}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    """初始化 PostgreSQL 資料庫和表格。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        print("正在檢查並初始化 PostgreSQL 資料庫...")
        
        # 創建用戶表格
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            display_name VARCHAR(100),
            native_language VARCHAR(50) DEFAULT '中文',
            target_language VARCHAR(50) DEFAULT '英文',
            learning_level VARCHAR(50) DEFAULT '初級',
            total_learning_time INTEGER DEFAULT 0,
            knowledge_points_count INTEGER DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            last_login_at TIMESTAMPTZ,
            is_active BOOLEAN DEFAULT TRUE,
            email_verified BOOLEAN DEFAULT FALSE
        );
        """)
        
        # 創建刷新令牌表格
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            token_hash VARCHAR(255) NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            is_revoked BOOLEAN DEFAULT FALSE
        );
        """)
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS learning_events (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
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
            user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            subcategory TEXT NOT NULL,
            correct_phrase TEXT NOT NULL,
            explanation TEXT,
            user_context_sentence TEXT,
            incorrect_phrase_in_context TEXT,
            key_point_summary TEXT,
            mastery_level REAL DEFAULT 0.0,
            mistake_count INTEGER DEFAULT 0,
            correct_count INTEGER DEFAULT 0,
            last_reviewed_on TIMESTAMPTZ,
            next_review_date DATE,
            is_archived BOOLEAN DEFAULT FALSE,
            ai_review_notes TEXT,
            last_ai_review_date TIMESTAMPTZ,
            UNIQUE(user_id, correct_phrase)
        );
        """)
        
        # 檢查並添加新的AI審閱相關欄位
        cursor.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='knowledge_points' AND column_name='ai_review_notes'
            ) THEN
                ALTER TABLE knowledge_points ADD COLUMN ai_review_notes TEXT;
                RAISE NOTICE '欄位 ai_review_notes 已成功加入 knowledge_points 表格。';
            END IF;
            
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name='knowledge_points' AND column_name='last_ai_review_date'
            ) THEN
                ALTER TABLE knowledge_points ADD COLUMN last_ai_review_date TIMESTAMPTZ;
                RAISE NOTICE '欄位 last_ai_review_date 已成功加入 knowledge_points 表格。';
            END IF;
            
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

def add_mistake(question_data, user_answer, feedback_data, exclude_phrase=None, user_id=None, enable_auto_linking=True):
    """將學習事件和知識點弱點存入 PostgreSQL，並自動生成向量與關聯。"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        is_correct = feedback_data.get('is_generally_correct', False)
        feedback_json = json.dumps(feedback_data, ensure_ascii=False, indent=2)
        chinese = question_data.get('new_sentence', '（題目文字遺失）')
        q_type = question_data.get('type', 'new')
        source_id = question_data.get('original_mistake_id')
        
        # 建立一個從 code 到中文名稱的對照表
        ERROR_CODE_MAP = {
            "A": "詞彙與片語錯誤",
            "B": "語法結構錯誤",
            "C": "語意與語用錯誤",
            "D": "拼寫與格式錯誤",
            "E": "系統錯誤"
        }

        primary_error_category = "翻譯正確"
        primary_error_subcategory = "無"
        error_analysis = feedback_data.get('error_analysis', [])
        
        if error_analysis:
            major_errors = [e for e in error_analysis if e.get('severity') == 'major']
            first_error = major_errors[0] if major_errors else error_analysis[0]
            
            primary_error_code = first_error.get('error_type_code')
            primary_error_category = ERROR_CODE_MAP.get(primary_error_code, '分類錯誤')
            primary_error_subcategory = first_error.get('key_point_summary', '子分類錯誤')

        # 只有已認證用戶才記錄學習事件
        if user_id:
            cursor.execute(
                """
                INSERT INTO learning_events 
                (user_id, question_type, source_mistake_id, chinese_sentence, user_answer, is_correct, 
                error_category, error_subcategory, ai_feedback_json, timestamp) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (user_id, q_type, source_id, chinese, user_answer, is_correct, 
                primary_error_category, primary_error_subcategory, 
                feedback_json, datetime.datetime.now(datetime.timezone.utc))
            )
        
        # 收集新增或更新的知識點ID，用於後續向量處理
        processed_point_ids = []
        
        # 只有已認證用戶才處理知識點
        if not is_correct and error_analysis and user_id:
            print("\n正在更新您的具體知識點弱點分析...")
            for error in error_analysis:
                correct_phrase = error.get('correction')
                if exclude_phrase and correct_phrase == exclude_phrase:
                    print(f"  - (忽略已處理的複習點: {exclude_phrase})")
                    continue
                
                error_code = error.get('error_type_code')
                category = ERROR_CODE_MAP.get(error_code, '分類錯誤')
                subcategory = error.get('key_point_summary', '核心觀念')
                
                explanation = error.get('explanation')
                incorrect_phrase = error.get('original_phrase')
                summary = error.get('key_point_summary', '核心觀念')
                
                if not category or not subcategory or not correct_phrase:
                    continue

                cursor.execute("SELECT id, mastery_level FROM knowledge_points WHERE user_id = %s AND correct_phrase = %s", (user_id, correct_phrase))
                point = cursor.fetchone()
                severity_penalty = 0.5 if error.get('severity') == 'major' else 0.2

                if point:
                    new_mastery_level = max(0, point['mastery_level'] - severity_penalty)
                    cursor.execute(
                        """
                        UPDATE knowledge_points 
                        SET mistake_count = mistake_count + 1, mastery_level = %s, user_context_sentence = %s, incorrect_phrase_in_context = %s, key_point_summary = %s, last_reviewed_on = %s, next_review_date = %s,
                        category = %s, subcategory = %s
                        WHERE id = %s
                        """,
                        (new_mastery_level, user_answer, incorrect_phrase, summary, datetime.datetime.now(datetime.timezone.utc), datetime.date.today() + datetime.timedelta(days=1), category, subcategory, point['id'])
                    )
                    processed_point_ids.append(point['id'])
                    print(f"  - 已更新弱點：[{summary}]，熟練度下降。")
                else:
                    cursor.execute(
                        """
                        INSERT INTO knowledge_points (user_id, category, subcategory, correct_phrase, explanation, user_context_sentence, incorrect_phrase_in_context, key_point_summary, mistake_count, mastery_level, last_reviewed_on, next_review_date)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1, 0.0, %s, %s)
                        RETURNING id
                        """,
                        (user_id, category, subcategory, correct_phrase, explanation, user_answer, incorrect_phrase, summary, datetime.datetime.now(datetime.timezone.utc), datetime.date.today() + datetime.timedelta(days=1))
                    )
                    new_point_id = cursor.fetchone()['id']
                    processed_point_ids.append(new_point_id)
                    print(f"  - 已發現新弱點：[{summary}]，已加入複習計畫。")
    
    conn.commit()
    conn.close()
    
    # 處理向量生成與自動關聯（在資料庫事務外執行，避免阻塞）
    if enable_auto_linking and processed_point_ids:
        print("\n正在為知識點生成語義向量與建立關聯...")
        try:
            from app.services.embedding_service import generate_and_store_embedding_for_point, auto_link_knowledge_point
            
            for point_id in processed_point_ids:
                try:
                    # 獲取知識點完整資料
                    point_data = get_knowledge_point_by_id(point_id)
                    if point_data:
                        # 生成並儲存向量
                        if generate_and_store_embedding_for_point(point_data):
                            print(f"  - 已為知識點 {point_id} 生成語義向量")
                            
                            # 自動建立關聯
                            link_count = auto_link_knowledge_point(point_id)
                            if link_count > 0:
                                print(f"  - 已為知識點 {point_id} 建立 {link_count} 個語義關聯")
                        else:
                            print(f"  - 知識點 {point_id} 向量生成失敗，跳過關聯建立")
                except Exception as e:
                    print(f"  - 處理知識點 {point_id} 的向量與關聯時發生錯誤: {e}")
                    continue
        except ImportError:
            print("  - 向量服務未啟用，跳過語義關聯建立")
    
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
    
    updated_rows = execute_query(
        """
        UPDATE knowledge_points 
        SET mastery_level = %s, correct_count = correct_count + 1, next_review_date = %s 
        WHERE id = %s
        """,
        (new_mastery_level, next_review_date, int(point_id))
    )

    if updated_rows > 0:
        print(f"✅ 知識點 ID: {point_id} 已成功更新！影響行數: {updated_rows}。安排在 {interval_days} 天後複習。")
    else:
        print(f"⚠️ 警告：更新知識點 ID: {point_id} 時，資料庫中沒有找到對應的紀錄，更新失敗！影響行數: {updated_rows}。")

def get_due_knowledge_points(limit):
    """根據台灣時區 (UTC+8) 來獲取當天到期的知識點。(舊版本，保持向後兼容)"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    taipei_offset = datetime.timedelta(hours=8)
    taipei_now = utc_now + taipei_offset
    today_in_taipei = taipei_now.date()
    print(f"[API] 伺服器UTC日期: {utc_now.date()} | 校準後台北日期: {today_in_taipei}")
    
    return execute_query(
        """
        SELECT * FROM knowledge_points 
        WHERE next_review_date <= %s AND is_archived = FALSE
        ORDER BY mastery_level ASC, last_reviewed_on ASC
        LIMIT %s
        """,
        (today_in_taipei, limit),
        fetch='all'
    )

def get_due_knowledge_points_for_user(user_id, limit):
    """根據用戶ID和台灣時區 (UTC+8) 來獲取當天到期的知識點。"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    taipei_offset = datetime.timedelta(hours=8)
    taipei_now = utc_now + taipei_offset
    today_in_taipei = taipei_now.date()
    print(f"[API] 用戶 {user_id} 伺服器UTC日期: {utc_now.date()} | 校準後台北日期: {today_in_taipei}")
    
    return execute_query(
        """
        SELECT * FROM knowledge_points 
        WHERE user_id = %s AND next_review_date <= %s AND is_archived = FALSE
        ORDER BY mastery_level ASC, last_reviewed_on ASC
        LIMIT %s
        """,
        (user_id, today_in_taipei, limit),
        fetch='all'
    )

def get_daily_activity(year, month):
    """查詢特定月份的每日學習活動數量。"""
    activities = execute_query(
        """
        SELECT DATE_TRUNC('day', timestamp AT TIME ZONE 'UTC')::date AS activity_date, COUNT(id) AS activity_count
        FROM learning_events
        WHERE EXTRACT(YEAR FROM timestamp AT TIME ZONE 'UTC') = %s AND EXTRACT(MONTH FROM timestamp AT TIME ZONE 'UTC') = %s
        GROUP BY activity_date ORDER BY activity_date;
        """,
        (year, month),
        fetch='all'
    )
    
    heatmap_data = {activity['activity_date'].isoformat(): activity['activity_count'] for activity in activities}
    return heatmap_data

def get_daily_details(activity_date):
    """查詢特定日期的學習詳情，並區分為「已複習」和「新學習」。"""
    events = execute_query(
        """
        SELECT question_type, ai_feedback_json, response_time
        FROM learning_events
        WHERE DATE(timestamp AT TIME ZONE 'UTC' + INTERVAL '8 hours') = %s;
        """,
        (activity_date,),
        fetch='all'
    )
    
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

# --- 知識點管理專用的函式 ---

def update_knowledge_point_details(point_id, details):
    """更新單一知識點的詳細資訊。"""
    allowed_fields = [
        'correct_phrase', 'explanation', 'key_point_summary', 
        'category', 'subcategory', 'user_context_sentence', 
        'incorrect_phrase_in_context', 'ai_review_notes'
    ]
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
    
    updated_rows = execute_query(query, tuple(update_values))
    return updated_rows > 0, f"成功更新 {updated_rows} 個知識點。"

def update_knowledge_point_ai_review(point_id, ai_review_notes):
    """更新知識點的AI審閱結果。"""
    updated_rows = execute_query(
        """
        UPDATE knowledge_points 
        SET ai_review_notes = %s, last_ai_review_date = %s
        WHERE id = %s
        """,
        (ai_review_notes, datetime.datetime.now(datetime.timezone.utc), point_id)
    )
    return updated_rows > 0

def set_knowledge_point_archived_status(point_id, is_archived):
    """設定知識點的封存狀態。"""
    updated_rows = execute_query(
        "UPDATE knowledge_points SET is_archived = %s WHERE id = %s", 
        (is_archived, point_id)
    )
    return updated_rows > 0

def delete_knowledge_point(point_id):
    """根據 ID 刪除一個知識點。"""
    deleted_rows = execute_query(
        "DELETE FROM knowledge_points WHERE id = %s", 
        (point_id,)
    )
    return deleted_rows > 0

def batch_update_knowledge_points_archived_status(point_ids, is_archived):
    """批次更新知識點的封存狀態。"""
    updated_rows = execute_query(
        "UPDATE knowledge_points SET is_archived = %s WHERE id = ANY(%s)",
        (is_archived, point_ids)
    )
    return updated_rows

def get_knowledge_point_phrase(point_id):
    """根據 ID 獲取單一知識點的 correct_phrase。"""
    result = execute_query(
        "SELECT correct_phrase FROM knowledge_points WHERE id = %s", 
        (point_id,), 
        fetch='one'
    )
    return result['correct_phrase'] if result else None

def get_knowledge_point_by_id(point_id):
    """根據 ID 獲取完整的知識點資料。"""
    point = execute_query(
        """
        SELECT id, category, subcategory, correct_phrase, explanation, 
               user_context_sentence, incorrect_phrase_in_context, 
               key_point_summary, mastery_level, mistake_count, 
               correct_count, next_review_date, ai_review_notes, 
               last_ai_review_date, is_archived
        FROM knowledge_points 
        WHERE id = %s
        """,
        (point_id,),
        fetch='one'
    )
    
    if point:
        if point.get('next_review_date'):
            point['next_review_date'] = point['next_review_date'].isoformat()
        if point.get('last_ai_review_date'):
            point['last_ai_review_date'] = point['last_ai_review_date'].isoformat()
        return point
    return None

def get_all_knowledge_points():
    """獲取所有未封存的知識點，用於儀表板。"""
    points_raw = execute_query(
        """
        SELECT id, category, subcategory, correct_phrase, explanation, 
               user_context_sentence, incorrect_phrase_in_context, 
               key_point_summary, mastery_level, mistake_count, 
               correct_count, next_review_date, ai_review_notes, 
               last_ai_review_date
        FROM knowledge_points 
        WHERE is_archived = FALSE
        ORDER BY mastery_level ASC, mistake_count DESC
        """,
        fetch='all'
    )
    
    points_dict = []
    for row in points_raw:
        if row.get('next_review_date'):
            row['next_review_date'] = row['next_review_date'].isoformat()
        if row.get('last_ai_review_date'):
            row['last_ai_review_date'] = row['last_ai_review_date'].isoformat()
        points_dict.append(row)
    return points_dict

def get_archived_knowledge_points():
    """獲取所有已封存的知識點。"""
    points_raw = execute_query(
        """
        SELECT id, category, subcategory, correct_phrase, explanation, 
               user_context_sentence, incorrect_phrase_in_context, 
               key_point_summary, mastery_level, mistake_count, 
               correct_count, next_review_date, ai_review_notes, 
               last_ai_review_date
        FROM knowledge_points 
        WHERE is_archived = TRUE
        ORDER BY last_reviewed_on DESC
        """,
        fetch='all'
    )
    
    points_dict = []
    for row in points_raw:
        if row.get('next_review_date'):
            row['next_review_date'] = row['next_review_date'].isoformat()
        if row.get('last_ai_review_date'):
            row['last_ai_review_date'] = row['last_ai_review_date'].isoformat()
        points_dict.append(row)
    return points_dict

def get_flashcards_by_types(types_to_fetch):
    """根據錯誤類型獲取單字卡。"""
    flashcards, unique_checker = [], set()
    all_events = execute_query(
        "SELECT ai_feedback_json FROM learning_events WHERE is_correct = false",
        fetch='all'
    )
    
    for event in all_events:
        if not event['ai_feedback_json']: 
            continue
        feedback_data = json.loads(event['ai_feedback_json'])
        for error in feedback_data.get('error_analysis', []):
            error_type = error.get('error_type')
            if error_type and error_type in types_to_fetch:
                card_front = error.get('original_phrase', 'N/A')
                card_back_correction = error.get('correction', 'N/A')
                card_identifier = (card_front, card_back_correction)
                if card_identifier in unique_checker: 
                    continue
                unique_checker.add(card_identifier)
                flashcards.append({
                    "front": card_front,
                    "back_correction": card_back_correction,
                    "back_explanation": error.get('explanation', 'N/A'),
                    "category": error_type
                })
    return flashcards

def get_daily_learning_events(activity_date):
    """查詢特定日期的完整學習事件數據，用於AI總結分析。"""
    events = execute_query(
        """
        SELECT id, question_type, chinese_sentence, user_answer, is_correct,
               response_time, error_category, error_subcategory, ai_feedback_json,
               difficulty, timestamp
        FROM learning_events
        WHERE DATE(timestamp AT TIME ZONE 'UTC' + INTERVAL '8 hours') = %s
        ORDER BY timestamp ASC;
        """,
        (activity_date,),
        fetch='all'
    )
    
    # 轉換為字典格式，方便AI處理
    events_list = []
    for event in events:
        # 解析AI反饋JSON
        if event['ai_feedback_json']:
            try:
                event['ai_feedback'] = json.loads(event['ai_feedback_json'])
            except json.JSONDecodeError:
                event['ai_feedback'] = None
        else:
            event['ai_feedback'] = None
        
        # 格式化時間戳
        if event['timestamp']:
            event['timestamp'] = event['timestamp'].isoformat()
            
        events_list.append(event)
    
    return events_list

def init_vocabulary_tables():
    """初始化單字相關的 PostgreSQL 表格"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        print("正在初始化單字資料庫表格...")
        
        # 1. 核心單字表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary_words (
            id SERIAL PRIMARY KEY,
            word TEXT NOT NULL UNIQUE,
            
            -- 字典資訊
            pronunciation_ipa TEXT,
            pronunciation_audio_url TEXT,
            part_of_speech TEXT,
            definition_zh TEXT NOT NULL,
            definition_en TEXT,
            difficulty_level INTEGER DEFAULT 1 CHECK (difficulty_level BETWEEN 1 AND 5),
            word_frequency_rank INTEGER,
            
            -- 學習數據
            mastery_level REAL DEFAULT 0.0 CHECK (mastery_level BETWEEN 0.0 AND 5.0),
            total_reviews INTEGER DEFAULT 0,
            correct_reviews INTEGER DEFAULT 0,
            consecutive_correct INTEGER DEFAULT 0,
            last_reviewed_at TIMESTAMPTZ,
            next_review_at TIMESTAMPTZ,
            
            -- 來源追蹤
            source_type TEXT DEFAULT 'manual' CHECK (source_type IN ('manual', 'translation_error', 'ai_recommend')),
            source_reference_id INTEGER,
            added_context TEXT,
            
            -- 元數據
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            is_archived BOOLEAN DEFAULT FALSE
        );
        """)
        
        # 2. 例句表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary_examples (
            id SERIAL PRIMARY KEY,
            word_id INTEGER REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            sentence_en TEXT NOT NULL,
            sentence_zh TEXT,
            source TEXT DEFAULT 'manual' CHECK (source IN ('cambridge', 'llm', 'user_context', 'manual')),
            difficulty_level INTEGER DEFAULT 1 CHECK (difficulty_level BETWEEN 1 AND 5),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """)
        
        # 3. 單字關係表（同義詞、反義詞等）
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary_relations (
            id SERIAL PRIMARY KEY,
            word_id INTEGER REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            related_word_id INTEGER REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            relation_type TEXT NOT NULL CHECK (relation_type IN ('synonym', 'antonym', 'word_family', 'collocation')),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(word_id, related_word_id, relation_type)
        );
        """)
        
        # 4. 單字複習記錄表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary_review_logs (
            id SERIAL PRIMARY KEY,
            word_id INTEGER REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            review_type TEXT NOT NULL CHECK (review_type IN ('flashcard', 'multiple_choice', 'context_fill', 'audio_quiz')),
            user_response TEXT,
            correct_answer TEXT,
            is_correct BOOLEAN NOT NULL,
            response_time REAL,
            difficulty_at_time INTEGER,
            mastery_before REAL,
            mastery_after REAL,
            timestamp TIMESTAMPTZ DEFAULT NOW()
        );
        """)
        
        # 5. 單字測驗題庫表
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS vocabulary_quiz_questions (
            id SERIAL PRIMARY KEY,
            word_id INTEGER REFERENCES vocabulary_words(id) ON DELETE CASCADE,
            question_type TEXT NOT NULL CHECK (question_type IN ('multiple_choice', 'context_fill')),
            question_text TEXT NOT NULL,
            correct_answer TEXT NOT NULL,
            wrong_options TEXT[], -- PostgreSQL 陣列型態，儲存錯誤選項
            context_sentence TEXT,
            difficulty_level INTEGER DEFAULT 1,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """)
        
        # 建立索引以提升查詢效能
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabulary_words_next_review ON vocabulary_words(next_review_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabulary_words_mastery ON vocabulary_words(mastery_level);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabulary_words_source ON vocabulary_words(source_type, source_reference_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vocabulary_review_logs_word_timestamp ON vocabulary_review_logs(word_id, timestamp);")
        
    conn.commit()
    conn.close()
    print("單字資料庫表格已準備就緒。")

# 單字CRUD操作函式

def add_vocabulary_word(word_data):
    """新增單字到資料庫"""
    conn = get_db_connection()
    with conn.cursor() as cursor:
        cursor.execute("""
            INSERT INTO vocabulary_words 
            (word, pronunciation_ipa, part_of_speech, definition_zh, definition_en, 
             difficulty_level, source_type, source_reference_id, added_context)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            word_data['word'],
            word_data.get('pronunciation_ipa'),
            word_data.get('part_of_speech'),
            word_data['definition_zh'],
            word_data.get('definition_en'),
            word_data.get('difficulty_level', 1),
            word_data.get('source_type', 'manual'),
            word_data.get('source_reference_id'),
            word_data.get('added_context')
        ))
        word_id = cursor.fetchone()['id']
        
        # 如果有例句，一併新增
        if 'examples' in word_data:
            for example in word_data['examples']:
                cursor.execute("""
                    INSERT INTO vocabulary_examples (word_id, sentence_en, sentence_zh, source)
                    VALUES (%s, %s, %s, %s)
                """, (word_id, example['sentence_en'], example.get('sentence_zh'), example.get('source', 'manual')))
        
    conn.commit()
    conn.close()
    return word_id

def get_vocabulary_word_by_id(word_id):
    """根據ID獲取單字完整資訊"""
    # 獲取基本單字資訊
    word = execute_query(
        "SELECT * FROM vocabulary_words WHERE id = %s", 
        (word_id,), 
        fetch='one'
    )
    
    if not word:
        return None
        
    # 獲取例句
    examples = execute_query(
        """
        SELECT sentence_en, sentence_zh, source 
        FROM vocabulary_examples 
        WHERE word_id = %s 
        ORDER BY created_at
        """, 
        (word_id,),
        fetch='all'
    )
    word['examples'] = examples
    
    return word

def get_due_vocabulary_words(limit=20):
    """獲取今日需要複習的單字"""
    # 使用台灣時區
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    taipei_offset = datetime.timedelta(hours=8)
    taipei_now = utc_now + taipei_offset
    today_in_taipei = taipei_now.date()
    
    words = execute_query(
        """
        SELECT * FROM vocabulary_words 
        WHERE (next_review_at IS NULL OR DATE(next_review_at AT TIME ZONE 'UTC' + INTERVAL '8 hours') <= %s)
        AND is_archived = FALSE
        ORDER BY mastery_level ASC, last_reviewed_at ASC NULLS FIRST
        LIMIT %s
        """, 
        (today_in_taipei, limit),
        fetch='all'
    )
    
    return words

def update_vocabulary_mastery(word_id, is_correct, response_time=None, review_type='flashcard'):
    """更新單字掌握度和複習排程"""
    # 獲取當前狀態
    result = execute_query(
        """
        SELECT mastery_level, consecutive_correct, total_reviews, correct_reviews
        FROM vocabulary_words WHERE id = %s
        """, 
        (word_id,),
        fetch='one'
    )
    
    if not result:
        return False
        
    current_mastery, consecutive_correct, total_reviews, correct_reviews = (
        result['mastery_level'], result['consecutive_correct'], 
        result['total_reviews'], result['correct_reviews']
    )
    mastery_before = current_mastery
    
    # 計算新的掌握度和間隔
    if is_correct:
        new_mastery = min(5.0, current_mastery + 0.3)
        new_consecutive = consecutive_correct + 1
        new_correct_reviews = correct_reviews + 1
        
        # 計算下次複習間隔（天數）
        interval_days = max(1, round(2 ** new_mastery))
    else:
        new_mastery = max(0.0, current_mastery - 0.4)
        new_consecutive = 0
        new_correct_reviews = correct_reviews
        interval_days = 1  # 明天再複習
    
    next_review_date = datetime.date.today() + datetime.timedelta(days=interval_days)
    
    conn = get_db_connection()
    with conn.cursor() as cursor:
        # 更新單字狀態
        cursor.execute("""
            UPDATE vocabulary_words 
            SET mastery_level = %s, 
                consecutive_correct = %s,
                total_reviews = %s,
                correct_reviews = %s,
                last_reviewed_at = %s,
                next_review_at = %s,
                updated_at = %s
            WHERE id = %s
        """, (
            new_mastery, new_consecutive, total_reviews + 1, new_correct_reviews,
            datetime.datetime.now(datetime.timezone.utc), next_review_date,
            datetime.datetime.now(datetime.timezone.utc), word_id
        ))
        
        # 記錄複習歷史
        cursor.execute("""
            INSERT INTO vocabulary_review_logs 
            (word_id, review_type, is_correct, response_time, mastery_before, mastery_after)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (word_id, review_type, is_correct, response_time, mastery_before, new_mastery))
        
    conn.commit()
    conn.close()
    return True

def get_vocabulary_statistics():
    """獲取單字庫統計資訊"""
    # 總單字數
    total_words = execute_query(
        "SELECT COUNT(*) as count FROM vocabulary_words WHERE is_archived = FALSE",
        fetch='one'
    )['count']
    
    # 已掌握單字（掌握度 >= 4.0）
    mastered_words = execute_query(
        "SELECT COUNT(*) as count FROM vocabulary_words WHERE mastery_level >= 4.0 AND is_archived = FALSE",
        fetch='one'
    )['count']
    
    # 學習中單字（0 < 掌握度 < 4.0）
    learning_words = execute_query(
        "SELECT COUNT(*) as count FROM vocabulary_words WHERE mastery_level > 0 AND mastery_level < 4.0 AND is_archived = FALSE",
        fetch='one'
    )['count']
    
    # 新單字（掌握度 = 0）
    new_words = execute_query(
        "SELECT COUNT(*) as count FROM vocabulary_words WHERE mastery_level = 0 AND is_archived = FALSE",
        fetch='one'
    )['count']
    
    # 今日複習數
    today = datetime.date.today()
    due_today = execute_query(
        """
        SELECT COUNT(*) as count FROM vocabulary_words 
        WHERE DATE(next_review_at AT TIME ZONE 'UTC' + INTERVAL '8 hours') <= %s 
        AND is_archived = FALSE
        """, 
        (today,),
        fetch='one'
    )['count']
    
    return {
        'total_words': total_words,
        'mastered_words': mastered_words,
        'learning_words': learning_words,
        'new_words': new_words,
        'due_today': due_today
    }

def search_vocabulary_words(query, limit=50):
    """搜尋單字"""
    words = execute_query(
        """
        SELECT * FROM vocabulary_words 
        WHERE (word ILIKE %s OR definition_zh ILIKE %s) 
        AND is_archived = FALSE
        ORDER BY 
            CASE WHEN word ILIKE %s THEN 1 ELSE 2 END,
            mastery_level ASC
        LIMIT %s
        """, 
        (f'%{query}%', f'%{query}%', f'{query}%', limit),
        fetch='all'
    )
    
    return words

# 在原有的 init_db() 函式末尾加入
def enhanced_init_db():
    """增強版的資料庫初始化，包含單字表格"""
    # 先執行原有的初始化
    init_db()
    # 再執行單字表格初始化
    init_vocabulary_tables()

# MARK: - 用戶認證相關函式

def create_user(username, email, password_hash, display_name=None, native_language='中文', target_language='英文', learning_level='初級'):
    """創建新用戶"""
    user_data = execute_query(
        """
        INSERT INTO users (username, email, password_hash, display_name, native_language, target_language, learning_level)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING id, username, email, display_name, native_language, target_language, learning_level, 
                 total_learning_time, knowledge_points_count, created_at, last_login_at
        """, 
        (username, email, password_hash, display_name, native_language, target_language, learning_level),
        fetch='one'
    )
    
    if user_data:
        return {
            'id': user_data['id'],
            'username': user_data['username'],
            'email': user_data['email'],
            'display_name': user_data['display_name'],
            'native_language': user_data['native_language'],
            'target_language': user_data['target_language'],
            'learning_level': user_data['learning_level'],
            'total_learning_time': user_data['total_learning_time'],
            'knowledge_points_count': user_data['knowledge_points_count'],
            'created_at': user_data['created_at'].isoformat() if user_data['created_at'] else None,
            'last_login_at': user_data['last_login_at'].isoformat() if user_data['last_login_at'] else None
        }
    return None

def get_user_by_email(email):
    """根據email獲取用戶"""
    user_data = execute_query(
        """
        SELECT id, username, email, password_hash, display_name, native_language, target_language, 
               learning_level, total_learning_time, knowledge_points_count, created_at, last_login_at, is_active
        FROM users WHERE email = %s AND is_active = TRUE
        """, 
        (email,),
        fetch='one'
    )
    
    if user_data:
        return {
            'id': user_data['id'],
            'username': user_data['username'],
            'email': user_data['email'],
            'password_hash': user_data['password_hash'],
            'display_name': user_data['display_name'],
            'native_language': user_data['native_language'],
            'target_language': user_data['target_language'],
            'learning_level': user_data['learning_level'],
            'total_learning_time': user_data['total_learning_time'],
            'knowledge_points_count': user_data['knowledge_points_count'],
            'created_at': user_data['created_at'].isoformat() if user_data['created_at'] else None,
            'last_login_at': user_data['last_login_at'].isoformat() if user_data['last_login_at'] else None,
            'is_active': user_data['is_active']
        }
    return None

def get_user_by_id(user_id):
    """根據ID獲取用戶"""
    user_data = execute_query(
        """
        SELECT id, username, email, display_name, native_language, target_language, 
               learning_level, total_learning_time, knowledge_points_count, created_at, last_login_at
        FROM users WHERE id = %s AND is_active = TRUE
        """, 
        (user_id,),
        fetch='one'
    )
    
    if user_data:
        return {
            'id': user_data['id'],
            'username': user_data['username'],
            'email': user_data['email'],
            'display_name': user_data['display_name'],
            'native_language': user_data['native_language'],
            'target_language': user_data['target_language'],
            'learning_level': user_data['learning_level'],
            'total_learning_time': user_data['total_learning_time'],
            'knowledge_points_count': user_data['knowledge_points_count'],
            'created_at': user_data['created_at'].isoformat() if user_data['created_at'] else None,
            'last_login_at': user_data['last_login_at'].isoformat() if user_data['last_login_at'] else None
        }
    return None

def update_user_last_login(user_id):
    """更新用戶最後登入時間"""
    execute_query(
        "UPDATE users SET last_login_at = NOW() WHERE id = %s",
        (user_id,)
    )

def store_refresh_token(user_id, token_hash, expires_at):
    """儲存刷新令牌"""
    token_id = execute_query(
        """
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
        RETURNING id
        """,
        (user_id, token_hash, expires_at),
        fetch='one'
    )['id']
    
    return token_id

def get_refresh_token(token_hash):
    """獲取刷新令牌"""
    token_data = execute_query(
        """
        SELECT rt.id, rt.user_id, rt.expires_at, rt.is_revoked, u.is_active
        FROM refresh_tokens rt
        JOIN users u ON rt.user_id = u.id
        WHERE rt.token_hash = %s
        """,
        (token_hash,),
        fetch='one'
    )
    
    if token_data:
        return {
            'id': token_data['id'],
            'user_id': token_data['user_id'],
            'expires_at': token_data['expires_at'],
            'is_revoked': token_data['is_revoked'],
            'user_is_active': token_data['is_active']
        }
    return None

def revoke_refresh_token(token_hash):
    """撤銷刷新令牌"""
    updated_rows = execute_query(
        "UPDATE refresh_tokens SET is_revoked = TRUE WHERE token_hash = %s",
        (token_hash,)
    )
    return updated_rows > 0

def cleanup_expired_tokens():
    """清理過期的刷新令牌"""
    deleted_rows = execute_query(
        "DELETE FROM refresh_tokens WHERE expires_at < NOW() OR is_revoked = TRUE"
    )
    return deleted_rows

# 在 app/services/database.py 中新增以下缺少的函式

def get_vocabulary_word_by_word(word):
    """根據單字文本獲取單字資訊（用於檢查重複）"""
    word_data = execute_query(
        "SELECT * FROM vocabulary_words WHERE word = %s", 
        (word.lower(),),
        fetch='one'
    )
    return word_data

def update_vocabulary_word(word_id, update_data):
    """更新單字資訊"""
    allowed_fields = [
        'pronunciation_ipa', 'part_of_speech', 'definition_zh', 'definition_en',
        'difficulty_level', 'word_frequency_rank', 'added_context'
    ]
    
    update_fields = []
    update_values = []
    
    for key, value in update_data.items():
        if key in allowed_fields:
            update_fields.append(f"{key} = %s")
            update_values.append(value)
    
    if not update_fields:
        return False
    
    update_fields.append("updated_at = %s")
    update_values.append(datetime.datetime.now(datetime.timezone.utc))
    update_values.append(word_id)
    
    query = f"UPDATE vocabulary_words SET {', '.join(update_fields)} WHERE id = %s"
    updated_rows = execute_query(query, tuple(update_values))
    
    return updated_rows > 0

def archive_vocabulary_word(word_id):
    """歸檔單字"""
    updated_rows = execute_query(
        "UPDATE vocabulary_words SET is_archived = TRUE, updated_at = %s WHERE id = %s",
        (datetime.datetime.now(datetime.timezone.utc), word_id)
    )
    return updated_rows > 0