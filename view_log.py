import sqlite3
import json
import os
from datetime import datetime

# --- 設定 ---
DATABASE_FILE = "learning_log.db"

def display_formatted_event(record):
    """
    以一個美觀、易讀的卡片格式來顯示單筆學習事件。(原有的功能)
    """
    record_dict = dict(record)
    is_correct_str = "✅ 正確" if record_dict.get('is_correct') else "⚠️ 錯誤"
    timestamp_str = datetime.strptime(record_dict['timestamp'], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')

    print("\n" + "="*60)
    print(f"學習紀錄 ID: {record_dict['id']} | 時間: {timestamp_str}")
    print(f"狀態: {is_correct_str} | 類型: {record_dict.get('question_type', 'N/A').capitalize()}")
    if record_dict.get('question_type') == 'review':
        print(f"來源錯題 ID: {record_dict.get('source_mistake_id')}")
    print("="*60)
    
    print("\n【原始題目】")
    print(f"  {record_dict.get('chinese_sentence')}")
    
    print("\n【你的作答】")
    print(f"  {record_dict.get('user_answer')}")
    
    try:
        feedback = json.loads(record_dict['ai_feedback_json'])
        feedback_details = feedback.get('feedback', {})
        suggestion = feedback_details.get('suggestion', 'N/A')
        explanation = feedback_details.get('explanation', 'N/A')
        
        print("\n--- 🎓 AI 家教點評 ---")
        print(f"  錯誤分類: {feedback.get('error_category', 'N/A')} -> {feedback.get('error_subcategory', 'N/A')}")
        print("\n  [建議翻譯]")
        print(f"    {suggestion}")
        print("\n  [教學說明]")
        for line in explanation.split('\n'):
            print(f"    {line}")
    except (json.JSONDecodeError, AttributeError, TypeError):
        print("\n--- 🎓 AI 家教點評 (原始JSON) ---")
        print(record_dict['ai_feedback_json'])

    print("="*60 + "\n")

def display_raw_event(record):
    """
    【新功能】以欄位:值的形式，顯示最原始的數據。
    """
    # 將資料庫的 row 物件轉換為字典
    record_dict = dict(record)
    
    print("\n" + "-"*25 + f" 原始數據 (ID: {record_dict['id']}) " + "-"*25)
    # 遍歷字典中的每一個項目 (欄位名稱, 值)
    for key, value in record_dict.items():
        # 為了對齊，我們計算欄位名稱的長度
        # str(key).ljust(20) 的意思是，讓 key 這個字串靠左對齊，總長度補滿到 20 個字元
        print(f"{str(key).ljust(22)}: {value}")
    print("-" * 75)


def main():
    """
    主程式，提供選單讓使用者選擇如何查看紀錄。
    """
    if not os.path.exists(DATABASE_FILE):
        print(f"錯誤：找不到資料庫檔案 '{DATABASE_FILE}'。")
        print("請先執行 main.py 並完成至少一輪學習，以生成資料庫。")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    while True:
        print("\n--- 📊 學習日報檢視器 ---")
        print("【一般模式】")
        print("  1. 查看最新的 5 筆學習紀錄 (美化格式)")
        print("  2. 查看所有「錯誤」的學習紀錄 (美化格式)")
        print("\n【開發者模式】")
        print("  3. 查看最新的 5 筆學習紀錄 (完全原始數據)")
        print("  4. 查看所有「錯誤」的學習紀錄 (完全原始數據)")
        print("\n  5. 退出")
        choice = input("請選擇你要執行的操作 (1-5): ")

        query = ""
        is_raw_mode = False
        
        if choice == '1':
            query = "SELECT * FROM learning_events ORDER BY timestamp DESC LIMIT 5"
        elif choice == '2':
            query = "SELECT * FROM learning_events WHERE is_correct = 0 ORDER BY timestamp DESC"
        elif choice == '3':
            query = "SELECT * FROM learning_events ORDER BY timestamp DESC LIMIT 5"
            is_raw_mode = True # 開啟原始數據模式
        elif choice == '4':
            query = "SELECT * FROM learning_events WHERE is_correct = 0 ORDER BY timestamp DESC"
            is_raw_mode = True # 開啟原始數據模式
        elif choice == '5':
            break
        else:
            print("無效的輸入，請重新選擇。")
            continue

        try:
            cursor.execute(query)
            records = cursor.fetchall()

            if not records:
                print("\n沒有找到符合條件的紀錄。")
                continue

            # 如果不是原始模式，就逆序顯示，讓舊的先出來
            display_records = records if is_raw_mode else reversed(records)
            
            for record in display_records:
                if is_raw_mode:
                    display_raw_event(record)
                else:
                    display_formatted_event(record)
            
            input("\n按 Enter 鍵返回主選單...")

        except sqlite3.OperationalError as e:
            print(f"\n查詢資料庫時發生錯誤: {e}")
            print("表格 'learning_events' 可能不存在。請確認您已使用最新版的 main.py 跑過學習流程。")

    conn.close()
    print("感謝使用，下次見！")

if __name__ == '__main__':
    main()