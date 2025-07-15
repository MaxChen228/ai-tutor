import sqlite3
import json
import os
from datetime import datetime

# --- 設定 ---
DATABASE_FILE = "learning_log.db"

def display_formatted_event(record):
    """
    v5.0 版更新：以美觀的卡片格式，顯示單筆「學習事件」的完整紀錄。
    能夠完美解析並逐條展示 `error_analysis` 清單中的所有錯誤。
    """
    record_dict = dict(record)
    is_correct_str = "✅ 大致正確" if record_dict.get('is_correct') else "⚠️ 存在主要錯誤"
    timestamp_str = datetime.strptime(record_dict['timestamp'], '%Y-%m-%d %H:%M:%S.%f').strftime('%Y-%m-%d %H:%M')

    print("\n" + "="*70)
    print(f"學習事件 ID: {record_dict['id']} | 時間: {timestamp_str}")
    print(f"狀態: {is_correct_str} | 類型: {record_dict.get('question_type', 'N/A').capitalize()}")
    print("="*70)

    print("\n【原始題目】")
    print(f"  {record_dict.get('chinese_sentence')}")

    print("\n【你的作答】")
    print(f"  {record_dict.get('user_answer')}")

    print("\n--- 🎓 AI 家教點評 ---")

    try:
        feedback = json.loads(record_dict['ai_feedback_json'])
        suggestion = feedback.get('overall_suggestion', 'N/A')
        print("\n  [整體建議翻譯]")
        print(f"    {suggestion}")

        error_analysis = feedback.get('error_analysis', [])
        if not error_analysis:
            print("\n  [詳細錯誤分析]")
            print("    🎉 恭喜！AI沒有發現任何錯誤。")
        else:
            print("\n  [詳細錯誤分析]")
            for i, error in enumerate(error_analysis, 1):
                severity_str = "主要" if error.get('severity') == 'major' else "次要"
                print(f"\n    {i}. ({severity_str}錯誤) {error.get('error_type', '')} - {error.get('error_subtype', '')}")
                print(f"       - 原文片段: \"{error.get('original_phrase', 'N/A')}\"")
                print(f"       - 建議修正: \"{error.get('correction', 'N/A')}\"")
                print(f"       - 教學說明: {error.get('explanation', 'N/A')}")

    except (json.JSONDecodeError, AttributeError, TypeError) as e:
        print(f"\n  [錯誤分析] (無法解析，顯示原始資料)")
        print(record_dict['ai_feedback_json'])

    print("="*70 + "\n")


def view_learning_events(cursor):
    """
    提供選單，讓使用者查看「學習事件」的日誌。
    """
    while True:
        print("\n--- 📖 學習事件日誌檢視 ---")
        print("1. 查看最新的 5 筆紀錄")
        print("2. 查看所有「存在主要錯誤」的紀錄")
        print("3. 返回主選單")
        choice = input("請選擇 (1-3): ")

        query = ""
        if choice == '1':
            query = "SELECT * FROM learning_events ORDER BY timestamp DESC LIMIT 5"
        elif choice == '2':
            query = "SELECT * FROM learning_events WHERE is_correct = 0 ORDER BY timestamp DESC"
        elif choice == '3':
            break
        else:
            print("無效的輸入。")
            continue

        cursor.execute(query)
        records = cursor.fetchall()
        if not records:
            print("\n沒有找到符合條件的紀錄。")
            continue
        
        # 逆序顯示，讓最新的在最下面，方便閱讀
        for record in reversed(records):
            display_formatted_event(record)
        
        print(f"--- 已顯示 {len(records)} 筆紀錄 ---")
        input("\n按 Enter 鍵繼續...")


def view_knowledge_points(cursor):
    """
    【v5.2 改造】顯示「具體知識點儀表板」。
    """
    print("\n" + "#"*15 + " 🧠 個人化知識點儀表板 " + "#"*15)
    print("這裡會列出您所有犯過的「具體」錯誤，並根據您目前的熟練度排序。")
    print("熟練度越低，代表您越需要加強該觀念！")
    print("-" * 80)

    # 【修改】從資料庫讀取包含新欄位的資料
    cursor.execute("SELECT category, subcategory, correct_phrase, explanation, mastery_level, mistake_count, correct_count FROM knowledge_points ORDER BY mastery_level ASC, mistake_count DESC")
    points = cursor.fetchall()

    if not points:
        print("\n太棒了！目前沒有任何弱點知識點紀錄。")
        print("開始練習，系統就會自動為您建立分析報告。")
        return

    # 【修改】重新設計表頭以容納更多資訊
    print(f"{'熟練度':<12} | {'錯誤':<4} | {'答對':<4} | {'具體知識點 (正確用法)'}")
    print("-" * 80)

    for point in points:
        # 熟練度進度條 (不變)
        mastery_bar = '█' * int(point['mastery_level'] * 2)
        mastery_bar = mastery_bar.ljust(10)
        mastery_str = f"[{mastery_bar}]"
        
        mistakes = str(point['mistake_count']).center(4)
        corrects = str(point['correct_count']).center(4)
        
        # 【修改】主要顯示內容變更為 correct_phrase
        phrase = point['correct_phrase']
        
        # 為了排版，如果片語太長，就截斷顯示
        if len(phrase) > 45:
            phrase = phrase[:42] + "..."

        print(f"{mastery_str:<12} | {mistakes} | {corrects} | \"{phrase}\"")
        # 【新增】在下一行用縮排顯示分類和核心觀念，更清晰
        print(f"{'':<26}└ 分類: {point['category']} -> {point['subcategory']}")

    print("-" * 80)


def main():
    if not os.path.exists(DATABASE_FILE):
        print(f"錯誤：找不到資料庫檔案 '{DATABASE_FILE}'。")
        print("請先執行 main.py 並完成至少一輪學習，以生成資料庫。")
        return

    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    while True:
        print("\n" + "="*20 + " 📊 AI 學習儀表板 (v5.0) " + "="*20)
        print("1. 🧠 查看個人知識點儀表板 (建議！)")
        print("2. 📖 查看詳細學習事件日誌")
        print("3. 👋 退出程式")
        choice = input("請輸入你的選擇 (1-3): ")

        if choice == '1':
            view_knowledge_points(cursor)
            input("\n按 Enter 鍵返回主選單...")
        elif choice == '2':
            view_learning_events(cursor)
        elif choice == '3':
            break
        else:
            print("\n無效的輸入，請重新輸入。")

    conn.close()
    print("\n感謝使用，下次見！")

if __name__ == '__main__':
    main()