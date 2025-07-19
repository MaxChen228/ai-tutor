# app/services/psycopg_adapter.py
"""
psycopg2 到 psycopg3 的相容性適配器
提供向後相容的 API，讓現有 psycopg2 代碼能與 psycopg3 一起工作
"""

import os
import sys

# 嘗試導入可用的 PostgreSQL 驅動
PSYCOPG_VERSION = None
psycopg_module = None

try:
    # 首先嘗試 psycopg2
    import psycopg2
    import psycopg2.extras
    import psycopg2.extensions
    PSYCOPG_VERSION = 2
    psycopg_module = psycopg2
    print("✅ 使用 psycopg2")
    
except ImportError:
    try:
        # 如果 psycopg2 不可用，嘗試 psycopg3
        import psycopg
        from psycopg import sql
        from psycopg.rows import dict_row
        PSYCOPG_VERSION = 3
        psycopg_module = psycopg
        print("✅ 使用 psycopg3 (通過適配器)")
        
    except ImportError:
        raise ImportError("無法導入 psycopg2 或 psycopg3。請安裝其中一個 PostgreSQL 驅動。")

class DatabaseAdapter:
    """資料庫適配器類，提供統一的 API"""
    
    def __init__(self):
        self.version = PSYCOPG_VERSION
        self.module = psycopg_module
    
    def connect(self, dsn):
        """建立資料庫連接"""
        if self.version == 2:
            return psycopg2.connect(dsn)
        else:
            return psycopg.connect(dsn)
    
    def get_dict_cursor_factory(self):
        """獲取字典游標工廠"""
        if self.version == 2:
            return psycopg2.extras.RealDictCursor
        else:
            return dict_row
    
    def get_exceptions(self):
        """獲取異常類"""
        if self.version == 2:
            return {
                'OperationalError': psycopg2.OperationalError,
                'DatabaseError': psycopg2.DatabaseError,
                'Error': psycopg2.Error
            }
        else:
            return {
                'OperationalError': psycopg.OperationalError,
                'DatabaseError': psycopg.DatabaseError,
                'Error': psycopg.Error
            }

# 創建全域適配器實例
adapter = DatabaseAdapter()

# 為了向後相容，模擬 psycopg2 的 API
class MockPsycopg2Module:
    """模擬 psycopg2 模組的類"""
    
    def __init__(self, adapter_instance):
        self.adapter = adapter_instance
        self.extras = self._create_extras_mock()
        
        # 導出異常
        exceptions = self.adapter.get_exceptions()
        self.OperationalError = exceptions['OperationalError']
        self.DatabaseError = exceptions['DatabaseError']
        self.Error = exceptions['Error']
    
    def connect(self, dsn):
        """連接資料庫"""
        return self.adapter.connect(dsn)
    
    def _create_extras_mock(self):
        """創建 extras 模組的模擬"""
        class ExtrasMock:
            def __init__(self, adapter_instance):
                self.adapter = adapter_instance
                
                if adapter_instance.version == 2:
                    self.RealDictCursor = psycopg2.extras.RealDictCursor
                else:
                    # 為 psycopg3 創建相容的游標類
                    self.RealDictCursor = self._create_dict_cursor_wrapper()
            
            def _create_dict_cursor_wrapper(self):
                """為 psycopg3 創建字典游標包裝器"""
                def dict_cursor_wrapper(connection):
                    return connection.cursor(row_factory=dict_row)
                return dict_cursor_wrapper
        
        return ExtrasMock(self.adapter)

# 根據可用的驅動導出適當的模組
if PSYCOPG_VERSION == 2:
    # 如果使用 psycopg2，直接導出
    psycopg2_compat = psycopg2
else:
    # 如果使用 psycopg3，導出相容性包裝
    psycopg2_compat = MockPsycopg2Module(adapter)

# 便利函數
def get_db_connection_with_adapter():
    """使用適配器獲取資料庫連接"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL 環境變數未設定")
    
    try:
        return adapter.connect(database_url)
    except Exception as e:
        print(f"資料庫連接失敗: {e}")
        raise

def get_psycopg_info():
    """獲取當前使用的 psycopg 版本資訊"""
    return {
        'version': PSYCOPG_VERSION,
        'module': psycopg_module.__name__,
        'file': psycopg_module.__file__,
        'package_version': getattr(psycopg_module, '__version__', 'Unknown')
    }

# 測試函數
def test_adapter():
    """測試適配器功能"""
    print("🧪 測試 psycopg 適配器...")
    
    info = get_psycopg_info()
    print(f"使用版本: psycopg{info['version']}")
    print(f"模組: {info['module']}")
    print(f"版本號: {info['package_version']}")
    
    try:
        conn = get_db_connection_with_adapter()
        print("✅ 資料庫連接成功")
        
        with conn.cursor() as cursor:
            cursor.execute("SELECT version();")
            version = cursor.fetchone()[0]
            print(f"✅ PostgreSQL 版本: {version}")
        
        conn.close()
        print("✅ 適配器測試通過")
        return True
        
    except Exception as e:
        print(f"❌ 適配器測試失敗: {e}")
        return False

if __name__ == "__main__":
    test_adapter()