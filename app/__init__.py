from flask import Flask
from flask_jwt_extended import JWTManager
from .services import database
import os
from datetime import timedelta

def create_app():
    app = Flask(__name__)
    app.config['JSON_AS_ASCII'] = False
    
    # JWT 配置
    app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET_KEY', 'your-secret-key-change-in-production')
    app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
    app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
    app.config['JWT_ALGORITHM'] = 'HS256'
    
    # 初始化 JWT
    jwt = JWTManager(app)
    
    # JWT 錯誤處理
    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        return {"error": "令牌已過期"}, 401
    
    @jwt.invalid_token_loader
    def invalid_token_callback(error):
        return {"error": "無效的令牌"}, 401
    
    @jwt.unauthorized_loader
    def missing_token_callback(error):
        return {"error": "需要提供認證令牌"}, 401
    
    if database.DATABASE_URL:
        print("正在初始化資料庫...")
        database.enhanced_init_db()  # 使用增強版
        print("資料庫準備就緒。")
    else:
        print("錯誤：未設定 DATABASE_URL 環境變數，伺服器無法啟動。")

    # 引入並註冊路由藍圖
    from .routes.session import session_bp
    from .routes.data import data_bp
    from .routes.vocabulary import vocabulary_bp
    from .routes.auth import auth_bp  # 新增認證路由
    from .routes.embedding import embedding_bp  # 新增向量化路由
    from .routes.admin import admin_bp  # 新增管理界面路由
    
    app.register_blueprint(session_bp, url_prefix='/api')
    app.register_blueprint(data_bp, url_prefix='/api')
    app.register_blueprint(vocabulary_bp, url_prefix='/api/vocabulary')
    app.register_blueprint(auth_bp, url_prefix='/api/auth')  # 新增認證路由
    app.register_blueprint(embedding_bp, url_prefix='/api')  # 新增向量化路由
    app.register_blueprint(admin_bp)  # 新增管理界面路由
    
    return app