from flask import Flask
from .services import database

def create_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    
    # 應用程式啟動時，初始化資料庫
    if database.DATABASE_URL:
        print("正在初始化資料庫...")
        database.init_db()
        print("資料庫準備就緒。")
    else:
        print("錯誤：未設定 DATABASE_URL 環境變數，伺服器無法啟動。")

    # 引入並註冊路由藍圖
    from .routes.session import session_bp
    from .routes.data import data_bp
    
    # 【修改】為所有 API 路由加上 /api 前綴
    app.register_blueprint(session_bp, url_prefix='/api')
    app.register_blueprint(data_bp, url_prefix='/api')
    
    return app