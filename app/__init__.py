from flask import Flask
from .services import database

def create_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    
    if database.DATABASE_URL:
        print("正在初始化資料庫...")
        database.enhanced_init_db()  # 使用增強版
        print("資料庫準備就緒。")
    else:
        print("錯誤：未設定 DATABASE_URL 環境變數，伺服器無法啟動。")

    # 引入並註冊路由藍圖
    from .routes.session import session_bp
    from .routes.data import data_bp
    from .routes.vocabulary import vocabulary_bp  # 新增
    
    app.register_blueprint(session_bp, url_prefix='/api')
    app.register_blueprint(data_bp, url_prefix='/api')
    app.register_blueprint(vocabulary_bp, url_prefix='/api/vocabulary')  # 新增
    
    return app