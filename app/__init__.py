import os
from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from .services import database
from .routes.session import session_bp
from .routes.chat import chat_bp
from .routes.auth import auth_bp
from .routes.feedback import feedback_bp
from .routes.history import history_bp
from .routes.admin import admin_bp

def create_app(test_config=None):
    """
    建立並設定 Flask 應用程式。
    這是一個應用程式工廠函式 (Application Factory)。
    """
    # --- 1. 應用程式實例化與基本設定 ---
    app = Flask(__name__, instance_relative_config=True)

    # 從 config.py 或環境變數載入設定
    # 優先使用環境變數，若無則使用預設值
    app.config.from_mapping(
        SECRET_KEY=os.getenv('SECRET_KEY', 'dev'),
        JWT_SECRET_KEY=os.getenv('JWT_SECRET_KEY', 'super-secret'),
        # 其他您可能需要的設定
    )

    if test_config is None:
        # 當不是在測試模式時，載入實例設定
        app.config.from_pyfile('config.py', silent=True)
    else:
        # 載入測試設定
        app.config.from_mapping(test_config)

    # --- 2. 初始化擴充套件 ---
    # 設定 CORS，允許來自所有來源的請求
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    # 設定 JWT 管理器
    jwt = JWTManager(app)

    # --- 3. 資料庫初始化 (已修正) ---
    print("正在初始化資料庫服務...")
    try:
        # 這會讀取 DATABASE_URL 環境變數並設定連線池
        database.init_app(app)
        
        print("正在檢查並初始化資料庫表格...")
        # 這會使用已設定好的連線池來建立表格
        database.enhanced_init_db()
        print("資料庫準備就緒。")
    except Exception as e:
        print(f"資料庫初始化失敗: {e}")
        # 在生產環境中，您可能會希望在此處停止應用程式或採取其他措施

    # --- 4. 註冊路由藍圖 (Blueprints) ---
    # 將所有 API 路由都放在 /api/ 字首下
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(session_bp, url_prefix='/api/session')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    app.register_blueprint(feedback_bp, url_prefix='/api/feedback')
    app.register_blueprint(history_bp, url_prefix='/api/history')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')

    # --- 5. 定義根路由與健康檢查端點 ---
    @app.route('/')
    def index():
        return "AI Tutor API is running!"

    @app.route('/health')
    def health_check():
        return jsonify(status="ok"), 200

    return app
