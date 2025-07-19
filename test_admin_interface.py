#!/usr/bin/env python3
# test_admin_interface.py - 測試管理界面功能

import requests
import json
import sys
import os
from urllib.parse import urljoin

class AdminInterfaceTester:
    def __init__(self, base_url="http://localhost:5000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.jwt_token = None
        
    def test_server_status(self):
        """測試服務器是否運行"""
        print("🔍 測試服務器狀態...")
        try:
            response = self.session.get(f"{self.base_url}/api/embedding/statistics")
            if response.status_code == 200:
                print("✅ 服務器運行正常")
                return True
            else:
                print(f"⚠️ 服務器回應狀態碼: {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ 無法連接到服務器，請確認服務已啟動")
            return False
        except Exception as e:
            print(f"❌ 測試服務器狀態時發生錯誤: {e}")
            return False

    def test_admin_routes(self):
        """測試管理界面路由"""
        print("\n🔍 測試管理界面路由...")
        
        routes_to_test = [
            ("/admin", "管理儀表板"),
            ("/admin/knowledge-points", "知識點列表"),
            ("/admin/batch-processing", "批次處理"),
            ("/admin/network-visualization", "網絡視覺化")
        ]
        
        success_count = 0
        
        for route, description in routes_to_test:
            try:
                url = f"{self.base_url}{route}"
                response = self.session.get(url, allow_redirects=False)
                
                if response.status_code == 200:
                    print(f"✅ {description} ({route}) - 頁面載入成功")
                    success_count += 1
                elif response.status_code == 401:
                    print(f"🔒 {description} ({route}) - 需要認證 (正常)")
                    success_count += 1
                elif response.status_code == 302:
                    print(f"🔄 {description} ({route}) - 重導向 (可能需要認證)")
                    success_count += 1
                else:
                    print(f"⚠️ {description} ({route}) - 狀態碼: {response.status_code}")
                    
            except Exception as e:
                print(f"❌ 測試 {description} 時發生錯誤: {e}")
        
        print(f"\n📊 路由測試結果: {success_count}/{len(routes_to_test)} 通過")
        return success_count == len(routes_to_test)

    def test_api_endpoints(self):
        """測試API端點"""
        print("\n🔍 測試API端點...")
        
        api_tests = [
            ("/api/embedding/statistics", "GET", "向量統計"),
            ("/admin/api/network-data", "GET", "網絡資料"),
        ]
        
        success_count = 0
        
        for endpoint, method, description in api_tests:
            try:
                url = f"{self.base_url}{endpoint}"
                
                if method == "GET":
                    response = self.session.get(url)
                else:
                    response = self.session.post(url, json={})
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        print(f"✅ {description} ({endpoint}) - API 正常回應")
                        if 'status' in data and data['status'] == 'success':
                            print(f"   ↳ 資料格式正確")
                        success_count += 1
                    except json.JSONDecodeError:
                        print(f"⚠️ {description} ({endpoint}) - 回應不是有效的JSON")
                elif response.status_code == 401:
                    print(f"🔒 {description} ({endpoint}) - 需要認證")
                    success_count += 1
                else:
                    print(f"⚠️ {description} ({endpoint}) - 狀態碼: {response.status_code}")
                    
            except Exception as e:
                print(f"❌ 測試 {description} API 時發生錯誤: {e}")
        
        print(f"\n📊 API測試結果: {success_count}/{len(api_tests)} 通過")
        return success_count > 0

    def test_static_files(self):
        """測試靜態文件"""
        print("\n🔍 測試靜態文件...")
        
        static_files = [
            ("/static/css/admin.css", "管理界面CSS"),
            ("/static/js/network-visualization.js", "網絡視覺化JS")
        ]
        
        success_count = 0
        
        for file_path, description in static_files:
            try:
                url = f"{self.base_url}{file_path}"
                response = self.session.get(url)
                
                if response.status_code == 200:
                    print(f"✅ {description} - 檔案載入成功")
                    success_count += 1
                else:
                    print(f"⚠️ {description} - 狀態碼: {response.status_code}")
                    
            except Exception as e:
                print(f"❌ 測試 {description} 時發生錯誤: {e}")
        
        print(f"\n📊 靜態文件測試結果: {success_count}/{len(static_files)} 通過")
        return success_count == len(static_files)

    def test_database_connection(self):
        """測試資料庫連接"""
        print("\n🔍 測試資料庫連接...")
        
        try:
            # 測試統計API
            response = self.session.get(f"{self.base_url}/api/embedding/statistics")
            
            if response.status_code == 200:
                data = response.json()
                if 'statistics' in data:
                    stats = data['statistics']
                    print("✅ 資料庫連接正常")
                    print(f"   ↳ 已向量化知識點: {stats.get('points_with_vectors', 0)}")
                    print(f"   ↳ 待處理知識點: {stats.get('points_without_vectors', 0)}")
                    print(f"   ↳ 活躍關聯: {stats.get('active_links', 0)}")
                    return True
                else:
                    print("⚠️ 資料庫回應格式異常")
                    return False
            else:
                print(f"⚠️ 資料庫測試失敗，狀態碼: {response.status_code}")
                return False
                
        except Exception as e:
            print(f"❌ 測試資料庫連接時發生錯誤: {e}")
            return False

    def run_all_tests(self):
        """執行所有測試"""
        print("🚀 開始測試管理界面功能...")
        print("=" * 50)
        
        test_results = []
        
        # 測試服務器狀態
        test_results.append(("服務器狀態", self.test_server_status()))
        
        # 如果服務器正常，繼續其他測試
        if test_results[0][1]:
            test_results.append(("管理界面路由", self.test_admin_routes()))
            test_results.append(("API端點", self.test_api_endpoints()))
            test_results.append(("靜態文件", self.test_static_files()))
            test_results.append(("資料庫連接", self.test_database_connection()))
        
        # 總結測試結果
        print("\n" + "=" * 50)
        print("📋 測試結果總結:")
        
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ 通過" if result else "❌ 失敗"
            print(f"   {test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\n🎯 總體結果: {passed}/{total} 項測試通過")
        
        if passed == total:
            print("🎉 所有測試都通過！管理界面功能正常")
            self.print_usage_instructions()
        else:
            print("⚠️ 部分測試失敗，請檢查服務器配置")
            self.print_troubleshooting_tips()
        
        return passed == total

    def print_usage_instructions(self):
        """打印使用說明"""
        print("\n📖 使用說明:")
        print(f"1. 訪問管理儀表板: {self.base_url}/admin")
        print(f"2. 查看知識點列表: {self.base_url}/admin/knowledge-points")
        print(f"3. 批次處理界面: {self.base_url}/admin/batch-processing")
        print(f"4. 網絡視覺化: {self.base_url}/admin/network-visualization")
        print("\n⚠️ 注意: 部分功能可能需要JWT認證")

    def print_troubleshooting_tips(self):
        """打印故障排除建議"""
        print("\n🔧 故障排除建議:")
        print("1. 確認Flask應用已啟動: python run.py")
        print("2. 檢查環境變數是否設定: DATABASE_URL")
        print("3. 確認資料庫連接正常")
        print("4. 檢查是否已執行資料庫遷移: database_migration_embedding.sql")
        print("5. 確認靜態文件路徑正確")

def main():
    """主函數"""
    print("🧪 AI家教管理界面測試工具")
    print("=" * 50)
    
    # 檢查參數
    base_url = "http://localhost:5000"
    if len(sys.argv) > 1:
        base_url = sys.argv[1]
    
    print(f"🌐 測試目標: {base_url}")
    
    # 創建測試器並執行測試
    tester = AdminInterfaceTester(base_url)
    success = tester.run_all_tests()
    
    # 返回適當的退出碼
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()