#!/usr/bin/env python3
# switch_psycopg_version.py - 快速切換 psycopg 版本的工具

import os
import shutil
import sys

def backup_current_requirements():
    """備份當前的 requirements.txt"""
    if os.path.exists('requirements.txt'):
        shutil.copy('requirements.txt', 'requirements_current_backup.txt')
        print("✅ 已備份當前 requirements.txt")

def switch_to_psycopg2_old():
    """切換到舊版 psycopg2 (Python 3.11)"""
    print("🔄 切換到 psycopg2 2.9.5 + Python 3.11.10...")
    
    # 更新 requirements.txt
    with open('requirements.txt', 'w') as f:
        f.write("""# === 向量化功能專用版本（穩定版 psycopg2）===

# === 核心 Web 框架與部署 ===
flask==2.3.3
gunicorn==21.2.0

# === 資料庫連接（穩定版）===
psycopg2-binary==2.9.5

# === 用戶認證與安全 ===
flask-jwt-extended==4.5.3
bcrypt==4.0.1

# === 環境變數管理 ===
python-dotenv==1.0.0

# === 知識點向量化功能（核心功能）===
numpy==2.0.2
sentence-transformers==2.2.2
scikit-learn==1.5.2
""")
    
    # 更新 runtime.txt
    with open('runtime.txt', 'w') as f:
        f.write('python-3.11.10')
    
    print("✅ 已切換到 psycopg2 2.9.5 + Python 3.11.10")

def switch_to_psycopg3():
    """切換到 psycopg3 (Python 3.13 相容)"""
    print("🔄 切換到 psycopg3 + Python 3.12.8...")
    
    # 更新 requirements.txt
    with open('requirements.txt', 'w') as f:
        f.write("""# === 向量化功能專用版本（psycopg3）===

# === 核心 Web 框架與部署 ===
flask==2.3.3
gunicorn==21.2.0

# === 資料庫連接（psycopg3）===
psycopg[binary]==3.1.18

# === 用戶認證與安全 ===
flask-jwt-extended==4.5.3
bcrypt==4.0.1

# === 環境變數管理 ===
python-dotenv==1.0.0

# === 知識點向量化功能（核心功能）===
numpy==2.0.2
sentence-transformers==2.2.2
scikit-learn==1.5.2
""")
    
    # 更新 runtime.txt
    with open('runtime.txt', 'w') as f:
        f.write('python-3.12.8')
    
    print("✅ 已切換到 psycopg3 + Python 3.12.8")

def switch_to_psycopg2_source():
    """切換到從源碼編譯的 psycopg2"""
    print("🔄 切換到從源碼編譯的 psycopg2...")
    
    # 更新 requirements.txt
    with open('requirements.txt', 'w') as f:
        f.write("""# === 向量化功能專用版本（從源碼編譯）===

# === 核心 Web 框架與部署 ===
flask==2.3.3
gunicorn==21.2.0

# === 資料庫連接（從源碼編譯）===
psycopg2==2.9.9

# === 用戶認證與安全 ===
flask-jwt-extended==4.5.3
bcrypt==4.0.1

# === 環境變數管理 ===
python-dotenv==1.0.0

# === 知識點向量化功能（核心功能）===
numpy==2.0.2
sentence-transformers==2.2.2
scikit-learn==1.5.2
""")
    
    # 更新 runtime.txt
    with open('runtime.txt', 'w') as f:
        f.write('python-3.12.8')
    
    print("✅ 已切換到從源碼編譯的 psycopg2")

def show_current_config():
    """顯示當前配置"""
    print("\n📋 當前配置:")
    
    # 讀取 runtime.txt
    try:
        with open('runtime.txt', 'r') as f:
            python_version = f.read().strip()
        print(f"🐍 Python 版本: {python_version}")
    except FileNotFoundError:
        print("⚠️ runtime.txt 不存在")
    
    # 讀取 requirements.txt 中的 psycopg 版本
    try:
        with open('requirements.txt', 'r') as f:
            content = f.read()
            
        for line in content.split('\n'):
            if 'psycopg' in line and not line.strip().startswith('#'):
                print(f"🗄️ PostgreSQL 驅動: {line.strip()}")
                break
        else:
            print("⚠️ 未找到 psycopg 配置")
            
    except FileNotFoundError:
        print("⚠️ requirements.txt 不存在")

def main():
    print("🔧 psycopg 版本切換工具")
    print("=" * 40)
    
    show_current_config()
    
    print("\n選擇要切換的配置:")
    print("1. psycopg2 2.9.5 + Python 3.11.10 (最穩定)")
    print("2. psycopg3 + Python 3.12.8 (支援 Python 3.13)")
    print("3. psycopg2 從源碼編譯 + Python 3.12.8")
    print("4. 顯示當前配置")
    print("5. 退出")
    
    while True:
        choice = input("\n請選擇 (1-5): ").strip()
        
        if choice == '1':
            backup_current_requirements()
            switch_to_psycopg2_old()
            break
        elif choice == '2':
            backup_current_requirements()
            switch_to_psycopg3()
            break
        elif choice == '3':
            backup_current_requirements()
            switch_to_psycopg2_source()
            break
        elif choice == '4':
            show_current_config()
        elif choice == '5':
            print("👋 再見！")
            sys.exit(0)
        else:
            print("❌ 無效選擇，請輸入 1-5")
    
    print("\n📝 後續步驟:")
    print("1. git add requirements.txt runtime.txt")
    print("2. git commit -m 'fix: 切換 psycopg 版本解決相容性問題'")
    print("3. git push")
    print("4. 等待 Render 重新部署")

if __name__ == "__main__":
    main()