# 醫療口碑與社區健康監測平台

這是一個以 Flask 建置的醫院評論分析系統，整合 Google Maps 評論爬蟲、中文情緒分析、Gemini AI 輔助摘要、科別推薦、醫院 PK 比較、症狀智能分流與後台健康警示管理。

## 系統功能

- 醫院查詢與 Google Maps 評論爬取
- 中文評論情緒分析與正負評統計
- 負評原因分類、關鍵字分析與改善建議
- 醫院詳細檔案、收藏、院方通知與 A4 報告
- 科別推薦與兩家醫院 PK 比較
- AI 症狀智能分流與症狀趨勢公告草稿
- 後台儀表板、會員權限、醫院帳號審核
- 批次爬蟲、排程爬蟲與爬蟲進度監控
- Gemini 多模型備援與本地統計備援

## 專案結構

```text
Hospital_Sentiment_Analysis/
├── app.py                         # Flask 主程式
├── requirements.txt               # Python 套件清單
├── .env.example                   # 環境變數範例
├── hospital_reviews.db            # SQLite 主要資料庫
├── data/
│   └── hospitals.xlsx             # 醫院清單 Excel
├── static/                        # CSS、上傳檔案與靜態資源
├── templates/                     # HTML 頁面模板
├── auto_import_awards.py          # 從圖片匯入獎項資料
├── lazy_import.py                 # 匯入預設獎項資料
├── debug.py                       # Excel 讀取診斷工具
└── test_ai.py                     # Gemini 模型可用性測試
```

## 需要準備的環境

- Python 3.9 以上
- pip
- Chrome 或 Chromium
- ChromeDriver，或允許 `webdriver-manager` 自動下載
- 可連外網路，若要使用 Gemini、Hugging Face 模型與 Google Maps 爬蟲

如果部署在 Linux 主機，建議確認是否可以使用 headless Chrome 跑 Selenium。

## 需要準備的檔案

正式執行時至少需要：

```text
app.py
requirements.txt
templates/
static/
data/hospitals.xlsx
hospital_reviews.db
.env
```

注意：`.env` 內含 API Key，不要放到公開 GitHub，也不要傳給不需要的人。

## 環境變數設定

先複製範例檔：

```bash
cp .env.example .env
```

再編輯 `.env`：

```env
GOOGLE_GEMINI_API_KEY=請填入自己的 Gemini API Key
GOOGLE_GEMINI_MODELS=gemini-3.5-flash,gemini-2.5-flash,gemini-2.5-pro,gemini-2.5-flash-lite
GOOGLE_GEMINI_DAILY_LIMIT=50
```

如果沒有 Gemini API Key，系統仍可使用本地統計備援，但 Gemini 摘要與 AI 文字生成效果會受限。

## 本機安裝與啟動

1. 進入專案資料夾：

```bash
cd Hospital_Sentiment_Analysis
```

2. 建立虛擬環境：

```bash
python3 -m venv venv
source venv/bin/activate
```

Windows 可改用：

```bash
venv\Scripts\activate
```

3. 安裝套件：

```bash
pip install -r requirements.txt
```

4. 啟動系統：

```bash
python3 app.py
```

5. 開啟瀏覽器：

```text
http://127.0.0.1:5007
```

同網路其他裝置可使用終端機顯示的區域網路網址，例如：

```text
http://主機IP:5007
```

## 使用 Docker 啟動

如果學校要求包成 Docker，請準備：

```text
Dockerfile
docker-compose.yml
.dockerignore
.env
hospital_reviews.db
data/hospitals.xlsx
```

1. 確認 `.env` 已設定：

```env
FLASK_SECRET_KEY=請改成一組隨機字串
GOOGLE_GEMINI_API_KEY=請填入自己的 Gemini API Key
GOOGLE_GEMINI_MODELS=gemini-3.5-flash,gemini-2.5-flash,gemini-2.5-pro,gemini-2.5-flash-lite
GOOGLE_GEMINI_DAILY_LIMIT=50
SELENIUM_HEADLESS=1
SELENIUM_HEADLESS_MODE=new
```

2. 建立並啟動容器：

```bash
docker compose up --build -d
```

如果主機是舊版 Docker，可能要用：

```bash
docker-compose up --build -d
```

3. 查看執行狀態：

```bash
docker compose ps
docker compose logs -f
```

4. 開啟網站：

```text
http://主機IP:5007
```

5. 停止系統：

```bash
docker compose down
```

Docker 版本已在容器內安裝 Chromium、ChromeDriver 與中文字型，並設定 `SELENIUM_HEADLESS=1`，比較適合沒有圖形介面的 Linux 主機。

如果 Google Maps 在 headless 模式爬不到，可以先把 `.env` 或 `docker-compose.yml` 的模式改成：

```env
SELENIUM_HEADLESS_MODE=old
```

再重建或重啟容器：

```bash
docker compose up --build -d
```

爬蟲失敗時，系統會在以下資料夾留下截圖與 HTML，方便判斷 Google Maps 畫面是否被驗證、擋住或版面不同：

```text
debug/crawler/
```

注意：`docker-compose.yml` 會把以下資料掛到容器內，讓資料不會因為重建容器而消失：

```text
hospital_reviews.db
data/
static/uploads/
Chrome_Spider_Profile/
Hugging Face 模型快取
```

## AI 情緒分析模型

系統使用 Hugging Face 模型：

```text
uer/roberta-base-finetuned-dianping-chinese
```

第一次執行情緒分析時會自動下載模型，可能需要數百 MB。若要先下載，可執行：

```bash
python3 -c "from transformers import pipeline; pipeline('sentiment-analysis', model='uer/roberta-base-finetuned-dianping-chinese'); print('model ok')"
```

如果主機不能連外網，需要先在可連網電腦下載模型快取，再搬到主機。

## Google Maps 爬蟲注意事項

本系統使用 Selenium 控制 Chrome / Chromium 爬取 Google Maps 評論。若部署到學校主機，請確認：

- 主機可以安裝 Chrome 或 Chromium
- 主機可以使用 ChromeDriver
- 主機可以連到 Google Maps
- Linux 無圖形介面時可以使用 headless Chrome
- 專案資料夾可寫入 `Chrome_Spider_Profile/`

如果主機不能跑 Selenium，仍可使用已存在的 `hospital_reviews.db` 展示資料庫快取、評論分析、後台統計與 PK 結果。

## 資料庫與資料檔

主要資料庫：

```text
hospital_reviews.db
```

醫院名單：

```text
data/hospitals.xlsx
```

上傳檔案預設位置：

```text
static/uploads/proofs/
```

請確認部署主機對這些位置有讀寫權限。

## Gemini 模型測試

設定好 `.env` 後，可測試 Gemini API Key 與可用模型：

```bash
python3 test_ai.py
```

## 匯入獎項資料

匯入內建獎項資料：

```bash
python3 lazy_import.py
```

從圖片辨識並匯入獎項資料：

```bash
python3 auto_import_awards.py
```

圖片預設路徑為：

```text
awards.jpg
```

## 部署到學校主機時要確認

請先向主機管理者確認：

- 是否提供 SSH 帳號與密碼或金鑰
- 主機是否為 Linux / Ubuntu
- 是否支援 Python 3.9 以上
- 是否可以建立 venv 並安裝 `requirements.txt`
- 是否可以安裝 Chrome / Chromium 和 ChromeDriver
- 是否可以連外網、Google Maps、Gemini API、Hugging Face
- 是否可以開放 `5007` port
- 若不能開 port，是否可設定 Nginx / Apache 反向代理
- 是否允許使用 SQLite 檔案
- 是否允許 `.env` 存放 Gemini API Key
- 專案資料夾是否有寫入權限

## 正式部署建議

展示或正式部署時，不建議只靠 SSH 視窗執行 `python3 app.py`。可以考慮：

```text
Gunicorn + systemd
Gunicorn + Nginx
學校提供的 Python App 部署面板
```

簡單測試可先使用：

```bash
python3 app.py
```

正式常駐則建議由主機管理者協助設定。

## 壓縮交付建議

若要壓縮給老師或同學，建議包含：

```text
app.py
requirements.txt
README.md
.env.example
templates/
static/
data/hospitals.xlsx
hospital_reviews.db
auto_import_awards.py
lazy_import.py
debug.py
test_ai.py
```

不要直接附上真正的 `.env`，除非對方就是負責部署且需要 API Key。

## 常見問題

### 找不到醫院清單

確認檔案存在：

```text
data/hospitals.xlsx
```

可執行：

```bash
python3 debug.py
```

### Gemini 無法回應

確認 `.env` 裡有：

```env
GOOGLE_GEMINI_API_KEY=你的 Key
```

也可以執行：

```bash
python3 test_ai.py
```

### 第一次情緒分析很慢

第一次會下載 Hugging Face 模型，下載完成後會快很多。

### 主機不能爬 Google Maps

可以先使用本機已爬好的 `hospital_reviews.db` 展示系統功能，或請主機管理者協助安裝 headless Chrome / Chromium。
