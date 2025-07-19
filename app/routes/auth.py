# app/routes/auth.py

from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import JWTManager, create_access_token, create_refresh_token, jwt_required, get_jwt_identity, get_jwt
from werkzeug.security import generate_password_hash, check_password_hash
from app.services import database as db
import datetime
import hashlib
import secrets

auth_bp = Blueprint('auth_bp', __name__)

@auth_bp.route("/register", methods=['POST'])
def register():
    """用戶註冊"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "請求格式錯誤，需要 JSON 資料"}), 400

        # 驗證必要欄位
        required_fields = ['username', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"缺少必要欄位: {field}"}), 400

        username = data['username'].strip()
        email = data['email'].strip().lower()
        password = data['password']

        # 基本驗證
        if len(username) < 3:
            return jsonify({"error": "用戶名至少需要3個字符"}), 400
        
        if len(password) < 6:
            return jsonify({"error": "密碼至少需要6個字符"}), 400
        
        if '@' not in email:
            return jsonify({"error": "請輸入有效的電子郵件地址"}), 400

        # 檢查用戶是否已存在
        existing_user = db.get_user_by_email(email)
        if existing_user:
            return jsonify({"error": "該電子郵件已被註冊"}), 409

        # 創建密碼雜湊
        password_hash = generate_password_hash(password)

        # 獲取可選欄位
        display_name = data.get('display_name', username)
        native_language = data.get('native_language', '中文')
        target_language = data.get('target_language', '英文')
        learning_level = data.get('learning_level', '初級')

        # 創建新用戶
        user_data = db.create_user(
            username=username,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            native_language=native_language,
            target_language=target_language,
            learning_level=learning_level
        )

        if not user_data:
            return jsonify({"error": "創建用戶失敗"}), 500

        # 生成 JWT tokens
        access_token = create_access_token(identity=user_data['id'])
        refresh_token_str = create_refresh_token(identity=user_data['id'])

        # 儲存刷新令牌到資料庫
        refresh_token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        db.store_refresh_token(user_data['id'], refresh_token_hash, expires_at)

        # 更新最後登入時間
        db.update_user_last_login(user_data['id'])

        # 返回認證回應
        return jsonify({
            "user": user_data,
            "access_token": access_token,
            "refresh_token": refresh_token_str,
            "expires_in": 3600  # 1小時
        }), 201

    except Exception as e:
        print(f"註冊錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤"}), 500

@auth_bp.route("/login", methods=['POST'])
def login():
    """用戶登入"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "請求格式錯誤，需要 JSON 資料"}), 400

        email = data.get('email', '').strip().lower()
        password = data.get('password', '')

        if not email or not password:
            return jsonify({"error": "請輸入電子郵件和密碼"}), 400

        # 查找用戶
        user_data = db.get_user_by_email(email)
        if not user_data:
            return jsonify({"error": "電子郵件或密碼錯誤"}), 401

        # 驗證密碼
        if not check_password_hash(user_data['password_hash'], password):
            return jsonify({"error": "電子郵件或密碼錯誤"}), 401

        # 移除密碼雜湊從回應中
        user_response = {k: v for k, v in user_data.items() if k != 'password_hash'}

        # 生成 JWT tokens
        access_token = create_access_token(identity=user_data['id'])
        refresh_token_str = create_refresh_token(identity=user_data['id'])

        # 儲存刷新令牌到資料庫
        refresh_token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        db.store_refresh_token(user_data['id'], refresh_token_hash, expires_at)

        # 更新最後登入時間
        db.update_user_last_login(user_data['id'])

        # 返回認證回應
        return jsonify({
            "user": user_response,
            "access_token": access_token,
            "refresh_token": refresh_token_str,
            "expires_in": 3600  # 1小時
        }), 200

    except Exception as e:
        print(f"登入錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤"}), 500

@auth_bp.route("/refresh", methods=['POST'])
def refresh():
    """刷新訪問令牌"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "請求格式錯誤，需要 JSON 資料"}), 400

        refresh_token_str = data.get('refresh_token')
        if not refresh_token_str:
            return jsonify({"error": "缺少刷新令牌"}), 400

        # 驗證刷新令牌
        refresh_token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
        token_data = db.get_refresh_token(refresh_token_hash)

        if not token_data:
            return jsonify({"error": "無效的刷新令牌"}), 401

        if token_data['is_revoked']:
            return jsonify({"error": "刷新令牌已被撤銷"}), 401

        if token_data['expires_at'] < datetime.datetime.utcnow():
            return jsonify({"error": "刷新令牌已過期"}), 401

        if not token_data['user_is_active']:
            return jsonify({"error": "用戶帳戶已被停用"}), 401

        # 獲取用戶資料
        user_data = db.get_user_by_id(token_data['user_id'])
        if not user_data:
            return jsonify({"error": "用戶不存在"}), 401

        # 生成新的 tokens
        access_token = create_access_token(identity=user_data['id'])
        new_refresh_token_str = create_refresh_token(identity=user_data['id'])

        # 撤銷舊的刷新令牌
        db.revoke_refresh_token(refresh_token_hash)

        # 儲存新的刷新令牌
        new_refresh_token_hash = hashlib.sha256(new_refresh_token_str.encode()).hexdigest()
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=30)
        db.store_refresh_token(user_data['id'], new_refresh_token_hash, expires_at)

        # 返回新的令牌
        return jsonify({
            "user": user_data,
            "access_token": access_token,
            "refresh_token": new_refresh_token_str,
            "expires_in": 3600  # 1小時
        }), 200

    except Exception as e:
        print(f"刷新令牌錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤"}), 500

@auth_bp.route("/logout", methods=['POST'])
@jwt_required()
def logout():
    """用戶登出"""
    try:
        user_id = get_jwt_identity()
        
        # 從請求中獲取刷新令牌（可選）
        data = request.get_json() or {}
        refresh_token_str = data.get('refresh_token')
        
        if refresh_token_str:
            # 撤銷特定的刷新令牌
            refresh_token_hash = hashlib.sha256(refresh_token_str.encode()).hexdigest()
            db.revoke_refresh_token(refresh_token_hash)
        
        # 清理過期的令牌
        db.cleanup_expired_tokens()

        return jsonify({"message": "登出成功"}), 200

    except Exception as e:
        print(f"登出錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤"}), 500

@auth_bp.route("/me", methods=['GET'])
@jwt_required()
def get_current_user():
    """獲取當前用戶資訊"""
    try:
        user_id = get_jwt_identity()
        user_data = db.get_user_by_id(user_id)
        
        if not user_data:
            return jsonify({"error": "用戶不存在"}), 404

        return jsonify(user_data), 200

    except Exception as e:
        print(f"獲取用戶資訊錯誤: {e}")
        return jsonify({"error": "伺服器內部錯誤"}), 500

@auth_bp.route("/validate", methods=['POST'])
@jwt_required()
def validate_token():
    """驗證訪問令牌"""
    try:
        user_id = get_jwt_identity()
        user_data = db.get_user_by_id(user_id)
        
        if not user_data:
            return jsonify({"valid": False, "error": "用戶不存在"}), 401

        return jsonify({
            "valid": True,
            "user": user_data
        }), 200

    except Exception as e:
        print(f"驗證令牌錯誤: {e}")
        return jsonify({"valid": False, "error": "伺服器內部錯誤"}), 500

# JWT 錯誤處理
@auth_bp.errorhandler(422)
def handle_unprocessable_entity(e):
    return jsonify({"error": "無效的令牌格式"}), 422

@auth_bp.errorhandler(401)
def handle_unauthorized(e):
    return jsonify({"error": "未授權訪問"}), 401