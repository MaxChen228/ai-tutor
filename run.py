# run.py
import os
from app import create_app

app = create_app()

if __name__ == '__main__':
    # 這部分主要用於本地端測試
    # 確保已設定環境變數
    if not os.getenv("OPENAI_API_KEY") or not os.getenv("DATABASE_URL"):
        print("錯誤：請先設定 OPENAI_API_KEY 和 DATABASE_URL 環境變數！")
    else:
        app.run(host='0.0.0.0', port=5000, debug=True)