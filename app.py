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

@app.route('/region', methods=['GET', 'POST'])
@login_required
def region():
    selected_region = None
    hospitals = []
    if request.method == 'POST':
        selected_region = request.form.get('region')
        with sqlite3.connect(HR_DB) as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, address FROM hospitals ORDER BY name ASC")
            rows = c.fetchall()
        for hid, name, address in rows:
            if infer_region_from_address(address or "") == selected_region:
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
    print(f"🚀 開始爬取：{hospital_name}")
    
    # -------------------------------------------
    # 1. 設定 Chrome 選項
    # -------------------------------------------
    options = webdriver.ChromeOptions()
    
    # 判斷是否在 Render 雲端環境 (Render 會自動提供這個環境變數)
    if os.environ.get('RENDER'):
        print("☁️ 偵測到雲端環境，啟動 Headless 模式...")
        options.binary_location = "/opt/render/project/.render/chrome/opt/google/chrome/chrome"
        options.add_argument("--headless=new") # 無頭模式 (無螢幕)
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
    else:
        print("💻 偵測到本機環境，啟動一般模式...")
        # 在本機測試時，保持原本的設定，不用 headless
        options.add_argument("--start-maximized")
    
    
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=zh-TW") # 強制繁體中文
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--start-maximized")
    options.add_argument("--incognito") 

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 15)

    try:
        # 2. 前往 Google Maps
        driver.get("https://www.google.com.tw/maps?hl=zh-TW")
        
        # 3. 搜尋地點
        search_box = wait.until(EC.presence_of_element_located((By.ID, "searchboxinput")))
        search_box.clear()
        search_box.send_keys(hospital_name)
        search_box.send_keys(Keys.RETURN)
        print("✅ 已輸入並搜尋")

        # ---------------------------------------------------------
        # 4. 進入評論區 (多重策略)
        # ---------------------------------------------------------
        print("🔍 嘗試進入評論列表...")
        time.sleep(3) 

        entered_reviews = False

        # 策略 A: 點擊「總評論數」或「星級」
        if not entered_reviews:
            try:
                review_count_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@aria-label, '評論') and contains(@jsaction, 'pane.rating')]")
                ))
                review_count_btn.click()
                entered_reviews = True
                print("✅ 成功點擊評分按鈕進入列表")
            except:
                pass

        # 策略 B: 找 Tab
        if not entered_reviews:
            try:
                review_tab = driver.find_element(By.XPATH, "//button[contains(@aria-label, '評論') and @role='tab']")
                review_tab.click()
                entered_reviews = True
                print("✅ 成功點擊評論分頁")
            except:
                pass

        # 策略 C: 點擊第一個搜尋結果
        if not entered_reviews:
            try:
                print("⚠️ 找不到入口，嘗試點擊搜尋結果第一項...")
                first_result = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href*='/maps/place']")))
                first_result.click()
                time.sleep(3)
                review_count_btn = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(@aria-label, '評論') and contains(@jsaction, 'pane.rating')]")
                ))
                review_count_btn.click()
                entered_reviews = True
                print("✅ 進入詳細頁後成功開啟評論")
            except Exception as e:
                print("❌ 無法進入評論區")
                driver.quit()
                return []
        
        time.sleep(3)

        # 5. 排序：切換為「最新」
        try:
            sort_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(@aria-label, '排序') or contains(@data-value, 'Sort')]")
            ))
            sort_btn.click()
            time.sleep(1)
            newest_btn = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//div[contains(@aria-label, '最新') or contains(text(), '最新')]")
            ))
            newest_btn.click()
            print("✅ 已切換為最新排序")
            time.sleep(3)
        except:
            print("⚠️ 無法排序 (可能已是最新)，繼續抓取")

        # ---------------------------------------------------------
        # 6. 【修正版】定位捲動容器 (改用 role='feed')
        # ---------------------------------------------------------
        print("🔍 定位捲動區域...")
        scrollable_div = None
        try:
            # 最新版 Google Maps 的評論列表都有 role="feed" 屬性
            scrollable_div = driver.find_element(By.CSS_SELECTOR, "div[role='feed']")
            print("✅ 成功鎖定捲動容器 (div[role='feed'])")
        except:
            print("⚠️ 找不到 role='feed'，嘗試使用舊版 class 定位...")
            try:
                scrollable_div = driver.find_element(By.CSS_SELECTOR, "div.m6QErb.DxyBCb.kA9KIf.dS8AEf")
            except:
                print("⚠️ 找不到特定捲動容器，將嘗試捲動整個頁面。")

        # ---------------------------------------------------------
        # 7. 【修正版】強力捲動抓取
        # ---------------------------------------------------------
        reviews_data = []
        unique_ids = set()
        scroll_attempts = 0
        last_height = 0
        
        if scrollable_div:
            last_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_div)

        while len(reviews_data) < max_reviews and scroll_attempts < 50:
            # 動作 A: 使用 JS 捲動容器
            if scrollable_div:
                driver.execute_script('arguments[0].scrollTop = arguments[0].scrollHeight', scrollable_div)
            else:
                # 動作 B: 捲動整個 Body (備用方案)
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.END)

            time.sleep(2) # 等待載入

            # 抓取目前所有看得到的評論區塊
            all_reviews = driver.find_elements(By.CSS_SELECTOR, 'div[data-review-id]')
            
            for r in all_reviews:
                try:
                    rid = r.get_attribute("data-review-id")
                    if rid in unique_ids: continue
                    
                    # 展開全文
                    try:
                        btn = r.find_element(By.TAG_NAME, "button")
                        if "全文" in btn.text or "更多" in btn.get_attribute("aria-label"):
                            driver.execute_script("arguments[0].click();", btn)
                    except: pass

                    # 抓文字
                    text = ""
                    try:
                        text = r.find_element(By.CSS_SELECTOR, ".wiI7pd").text.strip()
                    except:
                        try:
                            # 備用: 抓 span
                            spans = r.find_elements(By.TAG_NAME, "span")
                            for s in spans:
                                if len(s.text) > 5 and s.text != "翻譯":
                                    text = s.text
                                    break
                        except: pass
                    
                    # 抓時間
                    r_time = "Unknown"
                    try:
                        time_els = r.find_elements(By.XPATH, ".//span[contains(text(), '前') or contains(text(), 'ago')]")
                        for t in time_els:
                            if len(t.text) < 15:
                                r_time = t.text
                                break
                    except: pass

                    if text:
                        clean_text = remove_emojis(text)
                        if clean_text:
                            reviews_data.append({'text': clean_text, 'time': r_time})
                            unique_ids.add(rid)
                            print(f"  -> ({len(reviews_data)}/{max_reviews}) 抓取: {clean_text[:10]}...")

                    if len(reviews_data) >= max_reviews: break

                except: continue
                
            if len(reviews_data) >= max_reviews: 
                print(f"✅ 已達到目標數量 ({len(reviews_data)} 筆)")
                break

            # 檢查是否滑不動了
            if scrollable_div:
                new_height = driver.execute_script("return arguments[0].scrollHeight", scrollable_div)
                if new_height == last_height and scroll_attempts > 5:
                    # 如果高度沒變，且嘗試超過5次，可能真的到底了
                    pass
                last_height = new_height
            
            scroll_attempts += 1

        print(f"✅ 最終抓取 {len(reviews_data)} 筆")
        driver.quit()
        return reviews_data

    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        driver.quit()
        return []

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