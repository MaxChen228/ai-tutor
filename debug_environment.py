#!/usr/bin/env python3
# debug_environment.py - 診斷 Render 環境和 psycopg2 問題

import sys
import os
import platform
import importlib
import subprocess

def check_python_version():
    """檢查 Python 版本"""
    print("=" * 50)
    print("🐍 Python 環境檢查")
    print("=" * 50)
    print(f"Python 版本: {sys.version}")
    print(f"Python 可執行檔: {sys.executable}")
    print(f"平台: {platform.platform()}")
    print(f"架構: {platform.architecture()}")
    print(f"處理器: {platform.processor()}")

def check_environment_variables():
    """檢查環境變數"""
    print("\n" + "=" * 50)
    print("🔧 環境變數檢查")
    print("=" * 50)
    
    important_vars = [
        'DATABASE_URL',
        'PORT',
        'PYTHON_VERSION',
        'PYTHONPATH',
        'PATH'
    ]
    
    for var in important_vars:
        value = os.environ.get(var, 'Not Set')
        if var == 'DATABASE_URL' and value != 'Not Set':
            # 隱藏敏感資訊
            value = value[:20] + "***" + value[-10:]
        print(f"{var}: {value}")

def check_psycopg2_availability():
    """檢查 psycopg2 可用性"""
    print("\n" + "=" * 50)
    print("🗄️ PostgreSQL 驅動檢查")
    print("=" * 50)
    
    # 檢查 psycopg2
    try:
        import psycopg2
        print(f"✅ psycopg2 版本: {psycopg2.__version__}")
        print(f"✅ psycopg2 位置: {psycopg2.__file__}")
        
        # 檢查擴展
        try:
            from psycopg2._psycopg import version
            print(f"✅ psycopg2 C 擴展版本: {version}")
        except ImportError as e:
            print(f"❌ psycopg2 C 擴展載入失敗: {e}")
            
    except ImportError as e:
        print(f"❌ psycopg2 導入失敗: {e}")
        
        # 嘗試 psycopg3
        try:
            import psycopg
            print(f"✅ psycopg3 版本: {psycopg.__version__}")
            print(f"✅ psycopg3 位置: {psycopg.__file__}")
        except ImportError:
            print("❌ psycopg3 也不可用")

def check_database_connection():
    """檢查資料庫連接"""
    print("\n" + "=" * 50)
    print("🔗 資料庫連接檢查")
    print("=" * 50)
    
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("❌ DATABASE_URL 未設定")
        return
        
    try:
        # 嘗試 psycopg2
        import psycopg2
        conn = psycopg2.connect(database_url)
        with conn.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            print(f"✅ 使用 psycopg2 連接成功")
            print(f"✅ PostgreSQL 版本: {version}")
        conn.close()
        
    except Exception as e:
        print(f"❌ psycopg2 連接失敗: {e}")
        
        try:
            # 嘗試 psycopg3
            import psycopg
            with psycopg.connect(database_url) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT version();")
                    version = cursor.fetchone()[0]
                    print(f"✅ 使用 psycopg3 連接成功")
                    print(f"✅ PostgreSQL 版本: {version}")
                    
        except Exception as e2:
            print(f"❌ psycopg3 連接也失敗: {e2}")

def check_installed_packages():
    """檢查已安裝的相關套件"""
    print("\n" + "=" * 50)
    print("📦 相關套件檢查")
    print("=" * 50)
    
    packages_to_check = [
        'flask',
        'gunicorn',
        'psycopg2',
        'psycopg2-binary',
        'psycopg',
        'numpy',
        'scikit-learn',
        'sentence-transformers'
    ]
    
    for package in packages_to_check:
        try:
            module = importlib.import_module(package.replace('-', '_'))
            version = getattr(module, '__version__', 'Unknown')
            print(f"✅ {package}: {version}")
        except ImportError:
            print(f"❌ {package}: 未安裝")

def check_render_specific():
    """檢查 Render 特定設定"""
    print("\n" + "=" * 50)
    print("🌐 Render 平台檢查")
    print("=" * 50)
    
    # 檢查是否在 Render 環境中
    render_indicators = [
        ('RENDER', 'Render 環境標識'),
        ('RENDER_EXTERNAL_URL', 'Render 外部 URL'),
        ('RENDER_INTERNAL_HOSTNAME', 'Render 內部主機名'),
        ('PORT', 'Render 分配的端口')
    ]
    
    is_render = False
    for var, description in render_indicators:
        value = os.environ.get(var)
        if value:
            is_render = True
            print(f"✅ {description}: {value}")
        else:
            print(f"❌ {description}: 未設定")
    
    if is_render:
        print("✅ 確認運行在 Render 環境中")
    else:
        print("⚠️ 可能不在 Render 環境中")

def generate_fix_suggestions():
    """生成修復建議"""
    print("\n" + "=" * 50)
    print("💡 修復建議")
    print("=" * 50)
    
    python_version = sys.version_info
    
    print("建議的修復方案：")
    print()
    
    if python_version >= (3, 13):
        print("🔧 方案1: 降級 Python 版本")
        print("   - 在 runtime.txt 中設定: python-3.11.10")
        print("   - 刪除並重新部署以清除緩存")
        print()
        
    print("🔧 方案2: 使用 psycopg3")
    print("   - requirements.txt 中改為: psycopg[binary]==3.1.18")
    print("   - 修改 import 語句")
    print()
    
    print("🔧 方案3: 從源碼編譯 psycopg2")
    print("   - requirements.txt 中改為: psycopg2==2.9.9")
    print("   - 注意：編譯時間較長")
    print()
    
    print("🔧 方案4: 強制清除 Render 緩存")
    print("   - 添加 .buildpacks 文件")
    print("   - 在 Render 控制台手動清除緩存")

def main():
    """主診斷函數"""
    print("🩺 AI家教後端環境診斷工具")
    print("=" * 50)
    
    try:
        check_python_version()
        check_environment_variables()
        check_installed_packages()
        check_psycopg2_availability()
        check_database_connection()
        check_render_specific()
        generate_fix_suggestions()
        
        print("\n" + "=" * 50)
        print("✅ 診斷完成！請查看上述結果分析問題。")
        print("=" * 50)
        
    except Exception as e:
        print(f"\n❌ 診斷過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()