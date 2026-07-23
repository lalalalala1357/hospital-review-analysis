import os
import pandas as pd

# ==========================================
# 🧪 Excel 醫院名單診斷：確認檔案存在、欄位正確且可讀取
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
excel_path = os.path.join(BASE_DIR, 'data', 'hospitals.xlsx')

print("="*40)
print("🔍 開始診斷 Excel 檔案...")
print(f"📂 預期檔案路徑: {excel_path}")

# ==========================================
# 📂 檢查 Excel 檔案是否存在
# ==========================================
if os.path.exists(excel_path):
    print("✅ 檔案存在！")
else:
    print("❌ 錯誤：找不到檔案！")
    print("請確認資料夾內是否有 'data' 資料夾，且裡面有 'hospitals.xlsx'")
    exit()

# ==========================================
# 📖 讀取 Excel 並檢查必要欄位
# ==========================================
print("📖 正在嘗試讀取 Excel 內容...")
try:
    df = pd.read_excel(excel_path, engine='openpyxl')
    print("✅ 讀取成功！")
    
    # 4. 檢查欄位名稱
    print(f"📊 你的 Excel 欄位名稱有: {list(df.columns)}")
    
    df.columns = df.columns.str.strip() # 去除空白
    
    required_cols = ['醫事機構名稱', '機構地址']
    missing = [col for col in required_cols if col not in df.columns]
    
    if missing:
        print(f"❌ 嚴重錯誤：缺少關鍵欄位 {missing}")
        print("請打開 Excel，確認第一行的標題完全正確（不要有錯字或多餘空格）")
    else:
        print("🎉 格式完全正確！app.py 應該要能讀到才對。")
        print("前 3 筆資料預覽：")
        print(df[['醫事機構名稱', '機構地址']].head(3))

except Exception as e:
    print(f"❌ 讀取發生錯誤: {e}")
    print("可能是檔案損毀，或是 openpyxl 套件沒裝好。")

print("="*40)
