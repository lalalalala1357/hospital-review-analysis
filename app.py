from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin
from flask_bcrypt import Bcrypt
import sqlite3
import os
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import time

from captcha.image import ImageCaptcha
import random
import string
import io

from snownlp import SnowNLP
import re
from webdriver_manager.chrome import ChromeDriverManager

import threading
scrape_lock = threading.Lock() # 建立一把鎖

# ✅ 統一路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HR_DB = os.path.join(BASE_DIR, "hospital_reviews.db")

# 工具函式：過濾 emoji
def remove_emojis(text):
    """移除文字中的 emoji / 特殊符號"""
    emoji_pattern = re.compile(
        "[" 
        "\U0001F600-\U0001F64F"  # 😀 表情
        "\U0001F300-\U0001F5FF"  # 🌸 符號
        "\U0001F680-\U0001F6FF"  # 🚀 交通
        "\U0001F1E0-\U0001F1FF"  # 國旗
        "\u2600-\u26FF"          # ☀️☔⚡ 各種雜項符號
        "\u2700-\u27BF"          # ✂️✈️⛔ 箭頭符號
        "\u2190-\u21FF"          # ←↑→↓ 普通箭頭
        "\u2B00-\u2BFF"          # ⬆⬇⬅➡ 補充箭頭
        "\u2000-\u206F"          # 常見標點 (‼️、⁉️ 等在這裡)
        "\U0001F900-\U0001F9FF"  # 🤮🤯🦄 等
        "\U0001FA70-\U0001FAFF"  # 🛼🪐🪳 等
        "\U0001F100-\U0001F1FF"  # 🅿️ 帶圈字母/數字
        "\U0001F200-\U0001F2FF"  # 🈶️ 帶框漢字
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

# --- 縣市 -> 區域 對照表 & 地址判斷 ---
COUNTY_TO_REGION = {
    "台北": "north", "臺北": "north", "台北": "north", "新北": "north", "基隆": "north", "桃園": "north", "新竹": "north", "宜蘭": "north",
    "台中": "central", "臺中": "central", "苗栗": "central", "彰化": "central", "南投": "central", "雲林": "central",
    "台南": "south", "臺南": "south", "高雄": "south", "嘉義": "south", "屏東": "south",
    "花蓮": "east", "台東": "east", "臺東": "east",
}

def infer_region_from_address(address: str) -> str:
    if not address:
        return ""
    for county, region in COUNTY_TO_REGION.items():
        if county in address:
            return region
    return ""

# --- 自動建表 ---
def ensure_schema():
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS hospitals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT,
            google_place_id TEXT UNIQUE,
            created_at TEXT
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS reviews(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hospital_id INTEGER NOT NULL,
            author TEXT,
            content TEXT,
            rating REAL,
            review_time TEXT,
            analyzed_sentiment TEXT,
            stored_at TEXT,
            FOREIGN KEY(hospital_id) REFERENCES hospitals(id)
        )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_hospitals_place ON hospitals(google_place_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_hospital ON reviews(hospital_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(analyzed_sentiment)")
        conn.commit()


print("資料庫位置：", os.path.abspath("hospital_reviews.db"))

app = Flask(__name__)
app.secret_key = "supersecretkey"

bcrypt = Bcrypt(app)

# Flask-Login 設定
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# 初始化 SQLite 資料庫
DB_PATH = "users.db"
os.makedirs('data', exist_ok=True)

class User(UserMixin):
    def __init__(self, id_, username, password):
        self.id = id_
        self.username = username
        self.password = password

# --- 功能入口頁 ---
@app.route('/newindex')
@login_required
def newindex():
    return render_template('newindex.html', username=session.get('username'))

# --- 驗證碼功能 ---
@app.route('/captcha')
def get_captcha():
    chars = string.ascii_uppercase + string.digits
    captcha_text = ''.join(random.choice(chars) for _ in range(4))
    session['captcha_code'] = captcha_text.upper()
    image = ImageCaptcha(width=160, height=50)
    data = image.generate(captcha_text)
    return send_file(data, mimetype='image/png')

# --- 地區分類頁 ---
@app.route('/search')
@login_required
def search_page():
    return render_template('search.html', username=session.get('username'))


# 修改前 (您的原始寫法)
# c.execute("SELECT id, name, address FROM hospitals ORDER BY name ASC")
# rows = c.fetchall()
# for hid, name, address in rows:
#     if infer_region_from_address(address or "") == selected_region:
#         ...

# 修改後 (建議寫法：用 SQL Like 篩選)
@app.route('/region', methods=['GET', 'POST'])
@login_required
def region():
    selected_region = None
    hospitals = []
    
    # 定義區域對應的關鍵字 (這樣就不用先把全部撈出來)
    region_keywords = {
        "north": ["台北", "臺北", "新北", "基隆", "桃園", "新竹", "宜蘭"],
        "central": ["台中", "臺中", "苗栗", "彰化", "南投", "雲林"],
        "south": ["台南", "臺南", "高雄", "嘉義", "屏東"],
        "east": ["花蓮", "台東", "臺東"]
    }

    if request.method == 'POST':
        selected_region = request.form.get('region')
        keywords = region_keywords.get(selected_region, [])
        
        if keywords:
            # 動態建立 SQL 查詢： WHERE address LIKE '%台北%' OR address LIKE '%新北%' ...
            query_conditions = " OR ".join([f"address LIKE '%{k}%'" for k in keywords])
            sql = f"SELECT id, name, address FROM hospitals WHERE {query_conditions} ORDER BY name ASC"
            
            with sqlite3.connect(HR_DB) as conn:
                c = conn.cursor()
                c.execute(sql)
                rows = c.fetchall() # 這裡 fetchall 只會抓出符合的幾筆，記憶體安全很多
                
                for hid, name, address in rows:
                    hospitals.append({"id": hid, "name": name, "address": address or ""})
                    
    return render_template('region.html', selected_region=selected_region, hospitals=hospitals)




@login_manager.user_loader
def load_user(user_id):
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
    if row:
        return User(id_=row[0], username=row[1], password=row[2])
    return None


def scrape_google_reviews(hospital_name, max_reviews=30):
    print(f"🚀 開始爬取：{hospital_name} (內存優化模式)")
    
    options = webdriver.ChromeOptions()
    
    # --- 1. 極限內存優化參數 ---
    options.add_argument("--headless=new") 
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage") # 核心：解決容器內存不足
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--blink-settings=imagesEnabled=false") # 禁用圖片：省下約 30% 內存
    options.add_argument("--incognito") 
    options.add_argument("--single-process") # 減少進程開銷
    options.add_argument("window-size=1200,800")
    
    # 雲端環境特定路徑設定
    if os.environ.get('RENDER'):
        options.binary_location = "/opt/render/project/.render/chrome/opt/google/chrome/chrome"

    # 使用 Context Manager 思維，確保 driver 一定會被關閉
    driver = None
    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 10) # 縮短等待時間，減少佔用

        # 2. 前往 Google Maps
        driver.get(f"https://www.google.com.tw/maps/search/{hospital_name}?hl=zh-TW")
        time.sleep(2)

        # 3. 嘗試進入評論區
        print("🔍 尋找評論入口...")
        try:
            # 直接嘗試點擊帶有「評論」文字的按鈕
            review_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, '評論')]")))
            review_btn.click()
            time.sleep(2)
        except Exception:
            print("⚠️ 找不到評論按鈕，嘗試備用策略...")

        # 4. 排序：最新
        try:
            sort_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, '排序')]")))
            sort_btn.click()
            time.sleep(1)
            newest_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='menuitem' and contains(., '最新')]")))
            newest_btn.click()
            time.sleep(2)
        except:
            pass

        # 5. 滾動與抓取 (優化滾動邏輯，減少 DOM 元素堆積)
        reviews_data = []
        unique_ids = set()
        
        for _ in range(15): # 限制最大滾動次數
            if len(reviews_data) >= max_reviews:
                break
                
            # 抓取當前頁面的評論塊
            containers = driver.find_elements(By.CSS_SELECTOR, 'div[data-review-id]')
            for r in containers:
                rid = r.get_attribute("data-review-id")
                if rid and rid not in unique_ids:
                    try:
                        # 僅抓取必要的文字
                        text_el = r.find_element(By.CSS_SELECTOR, ".wiI7pd")
                        text = remove_emojis(text_el.text.strip())
                        if text:
                            reviews_data.append({'text': text, 'time': '近期'})
                            unique_ids.add(rid)
                    except:
                        continue
                if len(reviews_data) >= max_reviews: break

            # 滾動
            try:
                feed = driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
                driver.execute_script("arguments[0].scrollTop += 800", feed)
                time.sleep(1)
            except:
                break

        print(f"✅ 成功抓取 {len(reviews_data)} 筆")
        return reviews_data

    except Exception as e:
        print(f"❌ 爬蟲發生錯誤: {str(e)[:100]}")
        return []
    finally:
        if driver:
            driver.quit() # ⚠️ 這是最重要的：強制關閉瀏覽器進程

# ==========================================
# 爬蟲函式結束，以下原功能不變
# ==========================================

# ✅ 情感分析 (輕量化 SnowNLP 版)
def analyze_reviews(reviews):
    sentiments = []
    pos_count = 0
    neg_count = 0

    for review in reviews:
        text = review['text']
        r_time = review.get('time', 'Unknown') 

        # 使用 SnowNLP 進行分析
        try:
            s = SnowNLP(text)
            prob = s.sentiments # 範圍 0~1，越接近 1 越正向
        except:
            prob = 0.5 # 如果分析失敗給中立分

        score = round(prob * 100, 2)

        # 定義：大於 0.6 算正面，其他算負面 (SnowNLP 比較嚴格，門檻可自己調)
        if prob > 0.6:
            sentiment = "POSITIVE"
            pos_count += 1
        else:
            sentiment = "NEGATIVE"
            neg_count += 1

        emotion = sentiment 

        sentiments.append({
            'text': text,
            'time': r_time,
            'label': sentiment,
            'emotion': emotion,
            'score': score
        })

    return sentiments, pos_count, neg_count

@app.route('/google')
@login_required
def google_page():
    return render_template('google.html')

@app.route('/dashboard')
@login_required
def dashboard_page():
    return render_template('dashboard.html')


@app.route('/analyze', methods=['POST'])
@login_required
def analyze():
    # 嘗試取得鎖，如果有人正在用，就直接拒絕，保護記憶體
    if scrape_lock.locked():
        flash("系統忙碌中，請稍後再試（目前有人正在使用分析功能）", "analyze_error")
        return redirect(url_for('google_page'))

    with scrape_lock: # 這區塊內的程式碼，同一時間只能有一個人執行
        hospital_name = request.form.get('hospital')
        if not hospital_name:
            flash("請輸入醫院名稱")
            return redirect(url_for('google_page'))




    # 呼叫新的爬蟲函式
    reviews = scrape_google_reviews(hospital_name)
    
    if not reviews:
        flash("❌ 無法取得評論資料，請確認名稱正確或 Google 格式變動","analyze_error")
        return redirect(url_for('google_page'))

    sentiments, pos_count, neg_count = analyze_reviews(reviews)

    pd.DataFrame(sentiments).to_csv('data/google_reviews.csv', index=False, encoding='utf-8-sig')

    conn = sqlite3.connect(HR_DB)
    cursor = conn.cursor()

    place_id = hospital_name.lower().strip().replace(" ", "_")
    address = f"{hospital_name}（地址未知）"

    cursor.execute("SELECT id FROM hospitals WHERE google_place_id = ?", (place_id,))
    existing = cursor.fetchone()

    if existing:
        hospital_id = existing[0]
        print(f"⚠️ 醫院已存在：{hospital_name}，使用既有 ID: {hospital_id}")
    else:
        cursor.execute('''
            INSERT INTO hospitals (name, address, google_place_id, created_at)
            VALUES (?, ?, ?, ?)
        ''', (hospital_name, address, place_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        hospital_id = cursor.lastrowid
        print(f"✅ 已加入新醫院：{hospital_name}，編號為 {hospital_id}")

    for s in sentiments:
        cursor.execute('''
            INSERT OR IGNORE INTO reviews (
                hospital_id, author, content, rating, review_time, analyzed_sentiment, stored_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            hospital_id,
            'Unknown',  
            s['text'],
            None,       
            s['time'],
            s['label'],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

    conn.commit()
    conn.close()
    print("✅ 完成醫院與評論資料庫寫入！")
    
    return render_template('google.html', hospital=hospital_name, sentiments=sentiments, pos=pos_count, neg=neg_count)

@app.route('/')
@login_required
def index():
    return render_template('index.html', username=session.get('username'))

@login_required
def dashboard_data():
    try:
        with sqlite3.connect(HR_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE analyzed_sentiment = 'POSITIVE'")
            pos_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE analyzed_sentiment = 'NEGATIVE'")
            neg_count = cursor.fetchone()[0]
            conn.close()
            return jsonify({'positive': pos_count, 'negative': neg_count})
    except Exception as e:
        return jsonify({'error': f'資料讀取錯誤：{e}'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_captcha = request.form.get('captcha', '').upper()
        
        real_captcha = session.pop('captcha_code', None) 
        
        if not real_captcha or user_captcha != real_captcha:
            flash('驗證碼錯誤，請點擊圖片換一張重試', 'login_error')
            return redirect(url_for('login'))
        
        with sqlite3.connect(HR_DB) as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=?", (username,))
            row = c.fetchone()
            
        if row and bcrypt.check_password_hash(row[2], password):
            user = User(id_=row[0], username=row[1], password=row[2])
            login_user(user)
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('帳號或密碼錯誤','login_error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        try:
            with sqlite3.connect(HR_DB) as conn:
                c = conn.cursor()
                c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_pw))
                conn.commit()
            flash('註冊成功，請登入','register_success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('帳號已存在','register_error')
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

def init_admin_user(bcrypt):
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", ('admin',))
        if not c.fetchone():
            hashed_pw = bcrypt.generate_password_hash('123456').decode('utf-8')
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('admin', hashed_pw))
            print("✅ 已建立預設管理員 (帳號: admin / 密碼: 123456)")

ensure_schema()
init_admin_user(bcrypt)

if __name__ == '__main__':
    app.run(host='0.0.0.0',debug=True,port=5003)
    # 這是為了觸發 Git 更新的註解