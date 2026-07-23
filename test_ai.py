import google.generativeai as genai
import os
from dotenv import load_dotenv

# ==========================================
# 🤖 Gemini 模型可用性測試：讀取 .env 金鑰並列出可呼叫模型
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

YOUR_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
if not YOUR_API_KEY:
    raise RuntimeError("找不到 GOOGLE_GEMINI_API_KEY，請先在 .env 設定。")

genai.configure(api_key=YOUR_API_KEY)

print(f"🔑 使用 Key: {YOUR_API_KEY[:10]}... 進行測試")

try:
    print("📋 正在查詢您的帳號可用模型...")
    count = 0
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"   ✅ 發現模型: {m.name}")
            count += 1
    
    if count == 0:
        print("❌ 您的 Key 雖然有效，但沒有權限存取任何模型 (請確認是否在 AI Studio 申請)")
    else:
        print(f"🎉 測試成功！共發現 {count} 個可用模型。")
        
except Exception as e:
    print(f"❌ 連線失敗: {e}")
