import os
import json
import sqlite3
import google.generativeai as genai
from dotenv import load_dotenv

# ==========================================
# 🏆 圖片辨識匯入獎項資料：用 Gemini 讀取圖片並寫入 SQLite
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

# 設定你的 Gemini API Key
genai.configure(api_key=os.getenv("GOOGLE_GEMINI_API_KEY"))

# 指定你的資料庫路徑 (確保跟 app.py 用的是同一個)
HR_DB = os.path.join(BASE_DIR, "hospital_reviews.db")

def analyze_image_and_insert(image_path):
    # ==========================================
    # 🖼️ 圖片上傳與 AI 辨識
    # ==========================================
    if not os.path.exists(image_path):
        print(f"❌ 找不到圖片檔案：{image_path}")
        return

    print(f"📤 正在將圖片上傳至 AI 視覺引擎: {image_path}...")
    
    try:
        # 上傳圖片給 Gemini
        sample_file = genai.upload_file(path=image_path)
        
        # 💡 建議這裡使用 gemini-1.5-pro (它對於密集的文字辨識與 100% 準確率比 flash 更強)
        # 如果你的 API 權限只有 flash，也可以改成 'gemini-1.5-flash'
        model = genai.GenerativeModel('gemini-flash-latest')
        
        # ==========================================
        # 🧠 終極防漏 Prompt (嚴格要求 100% 輸出)
        # ==========================================
        prompt = """
        這是一張包含醫院得獎或權威認證紀錄的圖片（可能是名單或表格）。
        你的任務是「極度精準、完整」地萃取出裡面的每一筆資料。
        
        ⚠️【絕對禁止事項】：
        1. 絕對不能遺漏任何一筆！圖片裡有 50 行，你就要輸出 50 筆。
        2. 絕對不能自己總結或概括，必須逐字對應圖片上的資訊。
        
        請將結果轉換為純 JSON 陣列格式輸出（不要加上 ```json 標記，不要開場白，只要純粹的陣列）：
        [
            {
                "hospital_name": "醫院名稱 (例如: 臺大醫院)",
                "department": "科別 (例如: 骨科。若圖片上沒寫科別，請填 '綜合/未提及')",
                "award_name": "得獎或認證項目名稱 (例如: 2023 SNQ 國家品質標章)"
            }
        ]
        """
        
        print("🤖 AI 正在發功，啟動逐行像素掃描與資料轉換中，請稍候...")
        response = model.generate_content([sample_file, prompt])
        
        # ==========================================
        # 💾 解析 JSON 並寫入 SQLite
        # ==========================================
        # 清除 AI 可能雞婆加上去的 Markdown 標籤
        clean_text = response.text.replace("```json", "").replace("```", "").strip()
        
        try:
            awards_list = json.loads(clean_text)
            print(f"✅ AI 成功辨識出 {len(awards_list)} 筆資料！準備存入資料庫...")
        except json.JSONDecodeError:
            print("❌ AI 輸出的格式不是正確的 JSON，請檢查原始回傳內容：")
            print(response.text)
            return

        with sqlite3.connect(HR_DB) as conn:
            # ==========================================
            # 💾 寫入得獎/認證資料並略過重複紀錄
            # ==========================================
            cursor = conn.cursor()
            success_count = 0
            duplicate_count = 0
            
            for award in awards_list:
                # 統一防呆：把臺轉成台，並去掉前後多餘空白
                h_name = award.get('hospital_name', '').replace("臺", "台").strip()
                dept = award.get('department', '綜合/未提及').strip()
                a_name = award.get('award_name', '').strip()
                
                # 防呆：確保不是空資料
                if not h_name or not a_name:
                    continue
                
                try:
                    cursor.execute('''
                        INSERT INTO hospital_awards (hospital_name, department, award_name) 
                        VALUES (?, ?, ?)
                    ''', (h_name, dept, a_name))
                    success_count += 1
                except sqlite3.IntegrityError:
                    # 因為你在 app.py 有設定 UNIQUE，所以重複的資料會自動走到這裡被忽略
                    duplicate_count += 1
            
            conn.commit()
            print("==========================================")
            print(f"🎉 匯入完成！")
            print(f"➕ 成功新增: {success_count} 筆")
            print(f"⏭️ 略過重複: {duplicate_count} 筆")
            print("==========================================")

    except Exception as e:
        print(f"❌ 執行過程中發生錯誤: {e}")

# ==========================================
# 🚀 執行區塊
# ==========================================
if __name__ == "__main__":
    # 這裡填入你要辨識的圖片路徑 (放在專案目錄下的圖片)
    # 例如：你有一個截圖叫做 "awards.jpg"
    target_image = os.path.join(BASE_DIR, "awards.jpg")
    
    analyze_image_and_insert(target_image)
