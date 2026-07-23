# ==========================================
# 🤫 隱藏煩人的系統警告
# ==========================================
import warnings
warnings.filterwarnings("ignore")
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
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
from datetime import datetime, timedelta
import time
from captcha.image import ImageCaptcha
import random
import string
import io
import re
import html
import json
import logging
import socket
import math
from difflib import SequenceMatcher
from transformers import pipeline
import threading
scrape_lock = threading.Lock() 
batch_crawl_status_lock = threading.Lock()
batch_crawl_stop_event = threading.Event()
batch_crawl_pause_event = threading.Event()
batch_scheduler_started = False
batch_crawl_status = {
    'running': False,
    'status': 'idle',
    'message': '尚未啟動批次爬蟲',
    'stop_requested': False,
    'pause_requested': False,
    'started_at': None,
    'finished_at': None,
    'total': 0,
    'current_index': 0,
    'current_hospital': '',
    'processed': 0,
    'success': 0,
    'failed': 0,
    'skipped': 0,
    'new_reviews': 0,
    'refreshed_reviews': 0,
    'current_review_count': 0,
    'target_review_count': 0,
    'scroll_round': 0,
    'phase': '',
    'elapsed_seconds': 0,
    'estimated_remaining_seconds': None,
    'last_error': '',
    'current_job_id': None,
    'last_updated': None,
    'recent_logs': []
}
import google.generativeai as genai
import jieba
from collections import Counter
import jieba.posseg as pseg
from selenium.webdriver.common.action_chains import ActionChains

from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from dotenv import load_dotenv

import uuid
from werkzeug.utils import secure_filename

# ==========================================
# ⚙️ 系統路徑與環境變數設定
# ==========================================
# ✅ 1. 先定義 BASE_DIR (取得目前 app.py 所在的資料夾路徑)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ✅ 2. 明確組合出 .env 檔案的絕對路徑
env_path = os.path.join(BASE_DIR, '.env')

# ✅ 3. 強制載入該路徑的設定檔
load_dotenv(env_path, override=True)

CHINESE_NUMERAL_MAP = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "俩": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "半": 0.5
}

# ==========================================
# 🕒 Google 評論時間格式標準化
# ==========================================
def parse_chinese_number(value):
    """支援 Google 評論常見的中文數字，例如：一、兩、十、十一、二十。"""
    value = str(value or "").strip()
    if not value:
        return 1

    try:
        return float(value)
    except ValueError:
        pass

    if value in CHINESE_NUMERAL_MAP:
        return CHINESE_NUMERAL_MAP[value]

    if "十" in value:
        left, _, right = value.partition("十")
        tens = CHINESE_NUMERAL_MAP.get(left, 1) if left else 1
        ones = CHINESE_NUMERAL_MAP.get(right, 0) if right else 0
        return tens * 10 + ones

    total = 0
    for char in value:
        total = total * 10 + CHINESE_NUMERAL_MAP.get(char, 0)
    return total or 1

def subtract_months(base_date, months):
    month_index = base_date.month - 1 - months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    days_in_month = [
        31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31
    ]
    day = min(base_date.day, days_in_month[month - 1])
    return base_date.replace(year=year, month=month, day=day)

def normalize_google_review_time(raw_time, now=None):
    """
    將 Google Maps 的相對評論時間轉成日期字串。
    注意：「幾個月前 / 幾年前」在 Google 端本來就是模糊值，因此這裡是估算日期。
    """
    text = str(raw_time or "").replace("上次編輯：", "").replace("上次編輯:", "").strip()
    if not text or text in ["未知時間", "Unknown"]:
        return text or "未知時間"

    now = now or datetime.now()
    clean_text = re.sub(r"\s+", "", text)

    if clean_text in ["剛剛", "剛才"]:
        return now.strftime("%Y/%m/%d")
    if clean_text == "昨天":
        return (now - timedelta(days=1)).strftime("%Y/%m/%d")
    if clean_text == "前天":
        return (now - timedelta(days=2)).strftime("%Y/%m/%d")

    match = re.search(r"([0-9]+(?:\.[0-9]+)?|[零〇一二兩俩三四五六七八九十半]+)(?:個)?(分鐘|分|小時|時|天|日|週|周|星期|禮拜|月|年)前", clean_text)
    if not match:
        return text

    amount = parse_chinese_number(match.group(1))
    unit = match.group(2)

    if unit in ["分鐘", "分"]:
        target = now - timedelta(minutes=amount)
    elif unit in ["小時", "時"]:
        target = now - timedelta(hours=amount)
    elif unit in ["天", "日"]:
        target = now - timedelta(days=amount)
    elif unit in ["週", "周", "星期", "禮拜"]:
        target = now - timedelta(days=amount * 7)
    elif unit == "月":
        target = subtract_months(now, int(amount))
    elif unit == "年":
        target = subtract_months(now, int(amount) * 12)
    else:
        return text

    return target.strftime("%Y/%m/%d")

def normalize_stored_review_time(raw_time, stored_at=None):
    if not raw_time:
        return "未知時間"

    text = str(raw_time).strip()
    date_match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if date_match:
        year, month, day = date_match.groups()
        return f"{int(year):04d}/{int(month):02d}/{int(day):02d}"

    base_time = None
    if stored_at:
        for date_format in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                base_time = datetime.strptime(str(stored_at), date_format)
                break
            except ValueError:
                continue

    return normalize_google_review_time(text, base_time or datetime.now())

# ✅ 統一路徑設定
HR_DB = os.path.join(BASE_DIR, "hospital_reviews.db")
HOSPITAL_EXCEL_PATH = os.path.join(BASE_DIR, "data", "hospitals.xlsx")

AWARD_DEPARTMENTS = [
    "骨科", "心臟科", "婦產科", "小兒科", "腸胃科", "急診", "皮膚科", "眼科",
    "牙科", "耳鼻喉科", "復健科", "家庭醫學科", "神經外科", "泌尿科", "胸腔內科",
    "一般外科", "身心科", "中醫科", "其他"
]

# ==========================================
# 🧠 AI 情感分析模型：延遲載入
# ==========================================
SENTIMENT_MODEL_NAME = "uer/roberta-base-finetuned-dianping-chinese"
sentiment_pipeline = None
sentiment_model_error = None
sentiment_model_lock = threading.Lock()

def get_sentiment_pipeline():
    """第一次需要情感分析時才載入模型，避免 Flask 啟動被 400MB 模型卡住。"""
    global sentiment_pipeline, sentiment_model_error

    if sentiment_pipeline is not None:
        return sentiment_pipeline
    if sentiment_model_error is not None:
        return None

    with sentiment_model_lock:
        if sentiment_pipeline is not None:
            return sentiment_pipeline
        if sentiment_model_error is not None:
            return None

        print("⏳ 正在載入 AI 情感分析模型 (第一次執行會下載約 400MB，請稍候)...")
        try:
            sentiment_pipeline = pipeline(
                "sentiment-analysis",
                model=SENTIMENT_MODEL_NAME
            )
            print("✅ AI 模型載入完成！")
        except Exception as e:
            sentiment_model_error = str(e)
            print(f"❌ 模型載入失敗，請確認已執行 'pip install transformers torch'。錯誤: {e}")
            sentiment_pipeline = None

    return sentiment_pipeline

def remove_emojis(text):
    emoji_pattern = re.compile(
        "[" 
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\u2600-\u26FF"
        "\u2700-\u27BF"
        "\u2190-\u21FF"
        "\u2B00-\u2BFF"
        "\u2000-\u206F"
        "\U0001F900-\U0001F9FF"
        "\U0001FA70-\U0001FAFF"
        "\U0001F100-\U0001F1FF"
        "\U0001F200-\U0001F2FF"
        "]+", flags=re.UNICODE
    )
    return emoji_pattern.sub(r'', text)

# ==========================================
# 🏥 國軍臺中總醫院 官方症狀分流指南 (來自官網)
# ==========================================
OFFICIAL_SYMPTOM_GUIDE = {
    "血液腫瘤科": "貧血、紫斑、異常出血、紅白血球及血小板過多或過低、各種血液及各種腫瘤疾病",
    "胸腔內科": "感冒、呼吸困難、咳嗽、咳血、肺結核、肺腫瘤、肺炎、支氣管炎、支氣管擴張、氣喘、胸悶及各種胸部疾病",
    "腸胃內科": "食道、胃、腸、肝、膽、胰、膽管疾病和胃道逆流、消化不良、便秘、各種消化道疾病、功能性胃腸蠕動障礙",
    "心臟內科": "心悸、胸悶、運動後胸痛、心絞痛、高血壓、血管疾病及各種心臟疾病、呼吸困難",
    "腎臟內科": "頻尿、小便灼熱、血尿、腰部酸痛、水腫、腎結石及各種腎臟疾病、腎性高血壓、糖尿病腎病變、蛋白尿",
    "一般外科": "一般外傷、燙灼傷、靜脈曲張、乳房有硬塊、甲狀腺腫大、表皮組織腫瘤、疝氣",
    "神經外科": "頭部多傷、脊椎外傷、腦瘤、脊髓腫瘤、高血壓腦出血、腦動脈破裂、腦動靜脈畸型、手汗症、三叉神經痛、坐骨神經痛、半邊顏面痙、頸椎骨次症、下背痛、水腦症、腕道症候群、臂神經叢病變",
    "泌尿外科": "濃尿、乳糜尿、遲疑尿、血尿、頻尿、小便無力、夜尿、尿失禁、龜頭包皮炎急性或慢性腎孟炎、慢性前列腺炎、膀胱尿道發炎、泌尿道腫瘤、前列腺肥大、膀胱輸尿管結石、腎結石、尿道結石、不穩定、膀胱、膀胱機能異常、隱睪症、男性不孕、陰囊水腫、陰囊腫瘤、睪丸炎、神經性膀胱病變、性功能異常、精索靜脈曲張、疝氣、先天性泌尿道異常、阻塞性腎病變、尿道下裂、泌尿系統炎症、泌尿系統結石、泌尿系統腫瘤先天性畸型",
    "整型外科": "兔唇、上顎裂、小耳症、先天性手畸型、顏臉腫瘤、外傷及骨折、燙傷、化學灼傷、皮膚腫瘤及癌症口腔腫瘤及癌症、斷指及斷肢外科",
    "胸腔外科": "胸部外傷、血、氣胸、肋膜積水、積膿、肺膿瘍、肺腫瘤、氣管、支氣管、腫瘤食道腫瘤、縱隔腔腫瘤、氣管、支氣管、及食道外傷性疾病、手汗症",
    "心臟血管外科": "間歇性跛行、下肢冰麻疼痛、下肢潰瘍癒合不良、下肢腫漲不消、四肢末稍壞死、各類血管疾病、腹部脈動性腫瘤、急性胸悶胸痛、嚴重冠狀動脈疾病、重度瓣膜性心臟病、心臟手術後追縱",
    "一般牙科": "牙疼、牙齦出血、口臭、口腔檢查、拔牙補牙、顳顎關節障礙、口腔腫瘤及口腔內不適者、牙周炎根尖炎、齒列矯正、下顎骨折、蜂窩組織炎、蛀牙、變色牙齒漂白術、口內潰瘍",
    "口腔外科": "口腔潰瘍、口腔腫瘤、咬合不正、顎骨骨折、顳顎關節障礙、張口困難",
    "骨科": "運動傷害、脊椎損傷及變型、坐骨神經痛、軟組織腫瘤、痛風、骨骼肌肉神經病變、骨質疏鬆症頸椎骨刺症、小兒骨骼病變、手外科、關節退化、關節炎、腰酸背痛、骨畸型、骨腫瘤、脊椎病變肌肉肌腱扭傷、拉傷、骨折、脫臼、骨骼疼痛、骨髓炎",
    "家庭醫學科": "一般內科、兒科疾病、各種慢性病追蹤治療、健康檢查、家庭醫療諮詢婚前健康檢查、殘障鍵定職業病特別門診、更年期特別門診、感冒、腸胃疾病、各種慢性疾病（高血壓、糖尿病、高血脂症、痛風關節酸痛肝炎防治等）居家護理、保健諮詢",
    "小兒科": "凡十五歲以下、身體不適者、皆可看診",
    "婦產科": "例行婦科檢查、子宮抹片檢查、不規則陰道出血、白帶或不正常分泌物、月經失調、不孕症、下腹部疼痛、子宮、卵巢、輸卵管腫瘤、家庭計劃推展及優生保健之檢查與治療依健保局規並辦理",
    "急診醫學科": "內、外、骨、小兒、牙、身心科急症處理、家暴或性侵驗傷",
    "耳鼻喉科": "中耳炎、耳鳴、暈眩、聽力障礙、外耳炎、鼻塞、鼻炎、過敏性鼻炎、鼻竇炎、鼻肉長瘤、流鼻血、喉痛吞嚥困難、聲音沙啞、語言障礙、扁桃腺炎、頭頸部腫瘤、舌及口腔咽喉疾病、上呼吸道感染、打鼾、顏面神經麻痺",
    "眼科": "結膜炎、角膜炎、角膜退化症、角膜潰瘍、乾眼症、角膜移植、葡萄膜炎、鞏膜炎、青光眼、白內障、斜弱視、屈光不正（近視、遠視、散光）、老年性黃斑部病變、糖尿病視網膜病變、視網膜剝離、玻璃體出血、眼瞼下垂、眼皮鬆弛、眼窩腫瘤、麥粒腫、霧粒腫、鼻淚管阻塞、視神經病變",
    "復健科": "關節炎、腰酸背痛、運動傷害、中風、骨骼肌肉神經病變、脊椎損傷、腦性麻痺、語言治療、灼傷及外傷所致功能或活動障礙之肢體復健、截肢後之復健訓練、整脊治療、呼吸治療",
    "麻醉科": "頸肩酸痛、下背痛、關節疼痛、急慢性肌肉扭傷、癌症疼痛、頭痛、不明原因之身體各部位慢性疼痛分娩疼痛諮詢",
    "放射腫瘤科": "異常出血分泌物排泄物經久不癒之損傷、不明原因之體重減輕、吞嚥困難、消化不良、便血、疣或痣的變化、聲嘶或慢性咳嗽、頭頸部腫瘤（鼻咽癌、鼻竇癌、舌癌、喉癌、扁桃癌、口頰癌、牙齦癌）、婦科腫瘤（子宮頸癌、子宮內膜癌、卵巢癌、輸卵管癌）、腦瘤、泌尿道腫瘤、陰囊腫瘤、攝護腺癌、精原細胞瘤、皮膚癌、眼窩腫瘤、腦下垂體瘤、肺腫瘤、縱隔腔腫瘤、腦腺瘤、乳房癌、表皮組織腫瘤、肛門腫瘤、直腸癌、骨腫瘤及移轉性癌、各種癌症篩檢",
    "檢驗科": "生化檢驗、血液檢驗、驗尿、驗屎"
}

# ==========================================
# 🏥 醫療科別關鍵字字典與辨識邏輯
# ==========================================
DEPARTMENT_KEYWORDS = {
    "婦產科": ["婦產科", "產檢", "接生", "月子", "婦科", "產房", "羊膜穿刺"],
    "小兒科": ["小兒科", "兒科", "小孩", "寶寶", "嬰兒", "打疫苗"],
    "骨科": ["骨科", "骨折", "開刀", "復健", "關節", "脊椎", "石膏"],
    "急診": ["急診", "急救", "救護車", "掛急診"],
    "牙科": ["牙科", "牙醫", "拔牙", "根管", "洗牙", "植牙", "蛀牙"],
    "眼科": ["眼科", "視力", "白內障", "雷射", "結膜炎"],
    "心臟科": ["心臟科", "心臟內科", "心血管", "心肌梗塞", "心律不整"],
    "皮膚科": ["皮膚科", "雷射", "醫美", "痘痘", "過敏", "濕疹"],
    "腸胃科": ["腸胃科", "胃鏡", "大腸鏡", "腸胃炎", "消化"],
    "耳鼻喉科": ["耳鼻喉科", "感冒", "喉嚨痛", "鼻塞", "中耳炎"]
}

def detect_department(text):
    """從評論內文中偵測提到的科別"""
    for dept, keywords in DEPARTMENT_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return dept
    return "綜合/未提及"

# ==========================================
# 🧩 負評原因分類：把「負面」拆成可行動的問題類型
# ==========================================
NEGATIVE_ISSUE_CATEGORIES = {
    "等候時間": ["等很久", "等太久", "久等", "等待", "排隊", "等候", "拖很久", "很慢", "太慢", "慢到", "耗時"],
    "醫護態度": ["態度", "口氣", "不耐煩", "兇", "冷漠", "沒禮貌", "敷衍", "不友善", "很差", "惡劣"],
    "掛號流程": ["掛號", "報到", "櫃台", "流程", "動線", "系統", "預約", "叫號", "插隊"],
    "停車交通": ["停車", "車位", "停車場", "交通", "接駁", "路線", "不好停"],
    "收費問題": ["收費", "費用", "價格", "很貴", "太貴", "自費", "帳單", "付款", "健保"],
    "環境設備": ["環境", "設備", "廁所", "髒", "吵", "空間", "座位", "病房", "老舊", "冷氣"],
    "醫療溝通": ["說明", "解釋", "溝通", "診斷", "問診", "沒講", "不清楚", "檢查", "用藥"],
}

def classify_negative_issue(text, sentiment):
    """依關鍵字把負評歸類，正評不分類。"""
    if sentiment != "NEGATIVE":
        return "無"

    clean_text = text or ""
    for category, keywords in NEGATIVE_ISSUE_CATEGORIES.items():
        if any(keyword in clean_text for keyword in keywords):
            return category
    return "其他問題"

def summarize_negative_issues(sentiments):
    issue_counter = Counter()
    for item in sentiments:
        if item.get('label') == 'NEGATIVE':
            issue = item.get('issue_category') or classify_negative_issue(item.get('text', ''), item.get('label'))
            issue_counter[issue] += 1

    ordered_items = sorted(issue_counter.items(), key=lambda x: x[1], reverse=True)
    return {
        'labels': [item[0] for item in ordered_items],
        'data': [item[1] for item in ordered_items]
    }

def get_negative_issue_rows(reviews, limit=None):
    issue_counter = Counter()
    for review in reviews:
        if review.get('label') == 'NEGATIVE':
            issue_counter[classify_negative_issue(review.get('text', ''), review.get('label'))] += 1

    ordered_items = sorted(issue_counter.items(), key=lambda x: x[1], reverse=True)
    if limit:
        ordered_items = ordered_items[:limit]
    return [{'issue_category': item[0], 'count': item[1]} for item in ordered_items]

IMPROVEMENT_SUGGESTIONS = {
    "等候時間": "建議檢視尖峰時段掛號、報到、叫號與看診節奏，並評估是否需要增加即時等候資訊或分流人力。",
    "醫護態度": "建議加強第一線溝通訓練與情緒壓力支持，並針對高頻抱怨單位追蹤服務回饋。",
    "掛號流程": "建議檢查線上預約、現場報到、櫃台指引與叫號流程，減少民眾在流程中反覆詢問或等待。",
    "停車交通": "建議補強停車資訊揭露、尖峰時段動線指引與接駁說明，降低就醫前後的交通壓力。",
    "收費問題": "建議在檢查、治療或自費項目前加強費用說明，讓病患清楚知道收費原因與可選方案。",
    "環境設備": "建議優先盤點候診區、廁所、病房與公共空間的清潔、噪音、座位及設備狀況。",
    "醫療溝通": "建議強化問診後的診斷、用藥、檢查目的與後續追蹤說明，降低病患不確定感。",
    "其他問題": "建議抽樣閱讀此分類評論，補充更精準的分類關鍵字，或找出尚未被歸納的新問題類型。"
}

def generate_improvement_suggestions(issue_rows, neg_count, total_count):
    if not issue_rows or neg_count == 0:
        return [{
            'title': '維持服務品質',
            'description': '目前沒有明顯集中的負評原因，可持續追蹤最新評論並維持現有服務品質。',
            'priority': '觀察'
        }]

    suggestions = []
    for index, issue in enumerate(issue_rows[:3]):
        category = issue['issue_category']
        count = issue['count']
        percent = round(count / neg_count * 100) if neg_count else 0
        priority = '高' if index == 0 and percent >= 40 else ('中' if percent >= 20 else '觀察')
        suggestions.append({
            'title': f"優先改善：{category}",
            'description': IMPROVEMENT_SUGGESTIONS.get(category, IMPROVEMENT_SUGGESTIONS["其他問題"]),
            'count': count,
            'percent': percent,
            'priority': priority
        })

    if total_count and neg_count / total_count >= 0.5:
        suggestions.insert(0, {
            'title': '整體負評比例偏高',
            'description': '此醫院負評占比偏高，建議先從最大宗負評原因切入，並定期追蹤改善前後的評論變化。',
            'count': neg_count,
            'percent': round(neg_count / total_count * 100),
            'priority': '高'
        })

    return suggestions

def count_keyword_hits(reviews, keywords, sentiment=None):
    count = 0
    for review in reviews:
        review_sentiment = review.get('sentiment') or review.get('label')
        if sentiment and review_sentiment != sentiment:
            continue
        text = review.get('content') or review.get('text') or ''
        if any(keyword in text for keyword in keywords):
            count += 1
    return count

def generate_hospital_feature_tags(reviews, issue_rows, awards, stats):
    tags = []
    total = stats.get('total', 0)
    positive_rate = stats.get('positive_rate', 0)
    negative_rate = stats.get('negative_rate', 0)

    def add_tag(label, tone, reason, icon):
        if any(item['label'] == label for item in tags):
            return
        tags.append({
            'label': label,
            'tone': tone,
            'reason': reason,
            'icon': icon
        })

    if total == 0:
        add_tag('資料待累積', 'neutral', '目前尚無評論資料，建議先執行分析。', 'fa-database')
        return tags

    if positive_rate >= 80:
        add_tag('整體評價佳', 'positive', f'正評比例達 {positive_rate}%。', 'fa-thumbs-up')
    elif positive_rate >= 60:
        add_tag('評價相對穩定', 'positive', f'正評比例為 {positive_rate}%。', 'fa-chart-line')

    if negative_rate >= 45:
        add_tag('負評風險偏高', 'danger', f'負評比例為 {negative_rate}%，建議閱讀細部原因。', 'fa-triangle-exclamation')
    elif negative_rate <= 20 and total >= 5:
        add_tag('負評比例較低', 'positive', f'負評比例僅 {negative_rate}%。', 'fa-shield-heart')

    positive_themes = [
        ('醫師說明清楚', ['說明', '解釋', '清楚', '仔細', '細心', '專業'], 'fa-user-doctor'),
        ('護理照護友善', ['護理', '護士', '護理師', '親切', '溫柔', '耐心'], 'fa-hand-holding-heart'),
        ('看診效率佳', ['快速', '很快', '迅速', '效率', '不用等'], 'fa-stopwatch'),
        ('環境整潔舒適', ['乾淨', '整潔', '舒適', '環境好', '設備'], 'fa-house-medical-circle-check')
    ]
    threshold = 2 if total >= 10 else 1
    for label, keywords, icon in positive_themes:
        hits = count_keyword_hits(reviews, keywords, sentiment='POSITIVE')
        if hits >= threshold:
            add_tag(label, 'positive', f'{hits} 則正評提到相關體驗。', icon)

    if awards:
        departments = sorted({award.get('department') for award in awards if award.get('department')})
        dept_text = '、'.join(departments[:2])
        add_tag('具認證紀錄', 'positive', f'已收錄 {len(awards)} 筆得獎或認證{("，包含 " + dept_text) if dept_text else ""}。', 'fa-medal')

    caution_labels = {
        '等候時間': ('等候時間需留意', 'fa-clock'),
        '醫護態度': ('服務態度爭議', 'fa-face-frown'),
        '掛號流程': ('掛號流程需確認', 'fa-clipboard-list'),
        '停車交通': ('停車交通需規劃', 'fa-square-parking'),
        '收費問題': ('收費說明需留意', 'fa-file-invoice-dollar'),
        '環境設備': ('環境設備有反映', 'fa-hospital'),
        '醫療溝通': ('醫療溝通需多確認', 'fa-comments')
    }
    for issue in issue_rows[:3]:
        category = issue.get('issue_category')
        if category in caution_labels and issue.get('count', 0) > 0:
            label, icon = caution_labels[category]
            add_tag(label, 'warning', f'{issue["count"]} 則負評集中在「{category}」。', icon)

    if len(tags) < 3:
        top_department = Counter(item.get('department') for item in reviews if item.get('department')).most_common(1)
        if top_department:
            add_tag(f'{top_department[0][0]}討論較多', 'neutral', f'{top_department[0][1]} 則評論提到此科別。', 'fa-stethoscope')

    return tags[:8]

def get_representative_reviews(reviews, issue_rows, per_issue=3, max_issues=3):
    target_issues = [issue['issue_category'] for issue in issue_rows[:max_issues]]
    representatives = {issue: [] for issue in target_issues}

    negative_reviews = [
        review for review in reviews
        if review.get('sentiment') == 'NEGATIVE' and review.get('issue_category') in representatives
    ]
    negative_reviews.sort(key=lambda item: len(item.get('content') or ''), reverse=True)

    for review in negative_reviews:
        issue = review.get('issue_category')
        if len(representatives[issue]) >= per_issue:
            continue

        content = (review.get('content') or '').strip()
        if len(content) < 12:
            continue

        representatives[issue].append({
            'content': content[:180] + ('...' if len(content) > 180 else ''),
            'time': review.get('time') or 'Unknown'
        })

    return [
        {
            'issue_category': issue,
            'reviews': items
        }
        for issue, items in representatives.items()
        if items
    ]

# ==========================================
# 🔥 關鍵字分析設定 (動態資料庫版)
# ==========================================
def extract_keywords(reviews_list, top_n=10):
    dynamic_stop_words = set()
    try:
        with sqlite3.connect(HR_DB) as conn:
            c = conn.cursor()
            c.execute("CREATE TABLE IF NOT EXISTS stop_words(id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT UNIQUE NOT NULL)")
            c.execute("SELECT word FROM stop_words")
            # 💡 終極防呆 1：把資料庫撈出來的詞，強制去除前後空白
            dynamic_stop_words = set([str(row[0]).strip() for row in c.fetchall()])
    except Exception as e:
        print(f"⚠️ 讀取停用詞失敗，將使用空名單。錯誤: {e}")

    all_text = "".join([r['text'] for r in reviews_list])
    words = pseg.cut(all_text)
    candidate_set = set()
    
    for word, flag in words:
        # 💡 終極防呆 2：把文章切出來的詞，也強制去除前後空白，確保精準比對
        clean_word = word.strip()
        
        # 核心過濾邏輯
        if clean_word in dynamic_stop_words:
            continue
            
        if len(clean_word) < 2 and clean_word not in ["兇", "差", "爛", "慢", "久", "貴"]:
            continue
            
        if (flag.startswith('a') or 
            clean_word in ["等待", "排隊", "掛號", "停車", "動線", "態度", "效率", "櫃台", "護理師", "醫生", "醫師", "時間", "流程"]):
            candidate_set.add(clean_word)

    all_stats = []
    for kw in candidate_set:
        count = sum(1 for r in reviews_list if kw in r['text'])
        if count > 0:
            all_stats.append((kw, count))
    
    all_stats.sort(key=lambda x: x[1], reverse=True)
    top_results = all_stats[:top_n]
    
    return {
        'labels': [x[0] for x in top_results],
        'data': [x[1] for x in top_results]
    }

# ==========================================
# 🗺️ 縣市 -> 區域 對照表
# ==========================================
CITY_MAPPING = {
    "台北市": "north", "臺北市": "north", "新北市": "north", "基隆市": "north",
    "桃園市": "north", "新竹市": "north", "新竹縣": "north", "宜蘭縣": "north",
    "苗栗縣": "central", "台中市": "central", "臺中市": "central",
    "彰化縣": "central", "南投縣": "central", "雲林縣": "central",
    "嘉義市": "south", "嘉義縣": "south", "台南市": "south", "臺南市": "south",
    "高雄市": "south", "屏東縣": "south", "澎湖縣": "south",
    "花蓮縣": "east", "台東縣": "east", "臺東縣": "east",
    "金門縣": "other", "連江縣": "other"
}

# ==========================================
# 📂 讀取 Excel 醫院名單函式
# ==========================================
def load_hospitals_from_excel():
    excel_path = os.path.join(BASE_DIR, 'data', 'hospitals.xlsx')
    hospital_data = {"north": {}, "central": {}, "south": {}, "east": {}}

    if not os.path.exists(excel_path):
        print(f"⚠️ 找不到檔案：{excel_path}")
        return hospital_data

    try:
        print("📂 正在讀取醫院 Excel 資料...")
        df = pd.read_excel(excel_path, engine='openpyxl')
        df.columns = df.columns.str.strip()

        if '醫事機構名稱' not in df.columns or '機構地址' not in df.columns:
            print("❌ Excel 欄位名稱錯誤！請確認有「醫事機構名稱」和「機構地址」。")
            return hospital_data

        for _, row in df.iterrows():
            name = str(row['醫事機構名稱']).strip()
            address = str(row['機構地址']).strip()
            city = address[:3]
            
            region = CITY_MAPPING.get(city)
            if not region or region == 'other': continue

            if city not in hospital_data[region]:
                hospital_data[region][city] = []
            
            if name not in hospital_data[region][city]:
                hospital_data[region][city].append(name)
        
        print(f"✅ Excel 讀取完成！共載入 {len(df)} 筆醫院資料。")    
        return hospital_data
    except Exception as e:
        print(f"❌ 讀取 Excel 失敗: {e}")
        return hospital_data

GLOBAL_HOSPITALS_DATA = load_hospitals_from_excel()

# ==========================================
# 💡 新增：將所有醫院名稱攤平成一個單純的清單，給前端搜尋框使用
# ==========================================
FLAT_HOSPITAL_LIST = []
for region, cities in GLOBAL_HOSPITALS_DATA.items():
    for city, hospitals in cities.items():
        FLAT_HOSPITAL_LIST.extend(hospitals)

# 移除可能重複的項目，並排序一下
FLAT_HOSPITAL_LIST = sorted(list(set(FLAT_HOSPITAL_LIST)))

# ==========================================
# 🔧 資料庫結構檢查
# ==========================================
def ensure_schema():
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)")
        c.execute("CREATE TABLE IF NOT EXISTS hospitals(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, address TEXT, google_place_id TEXT UNIQUE, created_at TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, hospital_id INTEGER NOT NULL, author TEXT, content TEXT, rating REAL, review_time TEXT, analyzed_sentiment TEXT, stored_at TEXT, FOREIGN KEY(hospital_id) REFERENCES hospitals(id))")
        c.execute("CREATE TABLE IF NOT EXISTS stop_words(id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT UNIQUE NOT NULL)")
        c.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_audit_batches(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_name TEXT,
                sample_size INTEGER DEFAULT 30,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                completed_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sentiment_audit_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                batch_id INTEGER NOT NULL,
                review_id INTEGER NOT NULL,
                manual_sentiment TEXT,
                model_sentiment TEXT,
                is_correct INTEGER,
                created_at TEXT,
                FOREIGN KEY(batch_id) REFERENCES sentiment_audit_batches(id),
                FOREIGN KEY(review_id) REFERENCES reviews(id)
            )
        """)

        c.execute("PRAGMA table_info(hospitals)")
        hospital_columns = [column[1] for column in c.fetchall()]
        if 'latitude' not in hospital_columns:
            c.execute("ALTER TABLE hospitals ADD COLUMN latitude REAL")
        if 'longitude' not in hospital_columns:
            c.execute("ALTER TABLE hospitals ADD COLUMN longitude REAL")
        
        c.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in c.fetchall()]
        if 'reset_token' not in columns: c.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
        if 'is_admin' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
            c.execute("UPDATE users SET is_admin = 1 WHERE username = 'admin'")
        if 'role' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
            c.execute("UPDATE users SET role = CASE WHEN is_admin = 1 THEN 'admin' ELSE 'user' END")
        if 'hospital_id' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN hospital_id INTEGER")
        if 'approval_status' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN approval_status TEXT DEFAULT 'approved'")
        if 'official_email' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN official_email TEXT")
        if 'contact_name' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN contact_name TEXT")
        if 'contact_phone' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN contact_phone TEXT")
        if 'institution_code' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN institution_code TEXT")
        if 'requested_hospital_name' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN requested_hospital_name TEXT")
        if 'rejection_reason' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN rejection_reason TEXT")
        c.execute("UPDATE users SET role = 'admin', approval_status = 'approved' WHERE is_admin = 1")

        c.execute("""
            CREATE TABLE IF NOT EXISTS hospital_user_review_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                hospital_id INTEGER,
                note TEXT,
                actor_id INTEGER,
                created_at TEXT
            )
        """)
            
        # 👇 這是我們這次新增的：檢查並加入 department 欄位
        c.execute("PRAGMA table_info(reviews)")
        review_columns = [column[1] for column in c.fetchall()]
        if 'department' not in review_columns:
            print("🔧 資料庫升級：正在新增科別 (department) 欄位...")
            c.execute("ALTER TABLE reviews ADD COLUMN department TEXT DEFAULT '綜合/未提及'")

        c.execute("""
            CREATE TABLE IF NOT EXISTS batch_crawl_jobs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'queued',
                start_index INTEGER DEFAULT 0,
                hospital_count INTEGER DEFAULT 0,
                max_reviews INTEGER DEFAULT 30,
                rest_every INTEGER DEFAULT 5,
                rest_seconds INTEGER DEFAULT 20,
                total INTEGER DEFAULT 0,
                processed INTEGER DEFAULT 0,
                success INTEGER DEFAULT 0,
                skipped INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                new_reviews INTEGER DEFAULT 0,
                refreshed_reviews INTEGER DEFAULT 0,
                risk_count INTEGER DEFAULT 0,
                top_issue TEXT,
                retry_of_job_id INTEGER,
                requested_hospitals TEXT,
                message TEXT,
                created_at TEXT,
                started_at TEXT,
                finished_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS batch_crawl_job_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                hospital_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                new_reviews INTEGER DEFAULT 0,
                refreshed_reviews INTEGER DEFAULT 0,
                positive_reviews INTEGER DEFAULT 0,
                negative_reviews INTEGER DEFAULT 0,
                total_reviews INTEGER DEFAULT 0,
                top_issue TEXT,
                failure_category TEXT,
                error_message TEXT,
                review_samples TEXT,
                started_at TEXT,
                finished_at TEXT,
                FOREIGN KEY(job_id) REFERENCES batch_crawl_jobs(id)
            )
        """)
        c.execute("PRAGMA table_info(batch_crawl_job_items)")
        batch_item_columns = [column[1] for column in c.fetchall()]
        if 'failure_category' not in batch_item_columns:
            c.execute("ALTER TABLE batch_crawl_job_items ADD COLUMN failure_category TEXT")

        c.execute("""
            CREATE TABLE IF NOT EXISTS batch_crawl_schedules(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                frequency TEXT DEFAULT 'daily',
                run_time TEXT DEFAULT '02:00',
                hospital_count INTEGER DEFAULT 10,
                max_reviews INTEGER DEFAULT 30,
                rest_every INTEGER DEFAULT 5,
                rest_seconds INTEGER DEFAULT 20,
                next_start_index INTEGER DEFAULT 0,
                last_run_at TEXT,
                next_run_at TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)

        c.execute("SELECT COUNT(*) FROM stop_words")
        if c.fetchone()[0] == 0:
            default_words = [
                "可以", "沒有", "有些", "比較", "真的", "非常", "以為", "其實", 
                "結果", "這樣", "只是", "還是", "一點", "一下", "一樣", "一般", 
                "稍微", "感覺", "覺得", "主要", "重要", "普通", "正常", "好",
                "可能", "部分", "雖然", "但是", "不過", "甚至", "已經", "醫生",
                "醫師", "護理師", "護士"
            ]
            c.executemany("INSERT INTO stop_words (word) VALUES (?)", [(w,) for w in default_words])

            # 👇 新增這行：建立得獎紀錄表格
        c.execute("""
            CREATE TABLE IF NOT EXISTS hospital_awards(
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                hospital_name TEXT NOT NULL, 
                department TEXT NOT NULL, 
                award_name TEXT NOT NULL,
                UNIQUE(hospital_name, department, award_name) -- 避免重複匯入相同獎項
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS hospital_award_applications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_id INTEGER,
                hospital_name TEXT NOT NULL,
                user_id INTEGER,
                department TEXT NOT NULL,
                award_name TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                admin_note TEXT,
                proof_document TEXT,
                created_at TEXT NOT NULL,
                reviewed_at TEXT,
                reviewed_by INTEGER,
                FOREIGN KEY(hospital_id) REFERENCES hospitals(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        c.execute("PRAGMA table_info(hospital_award_applications)")
        award_app_columns = [column[1] for column in c.fetchall()]
        if 'proof_document' not in award_app_columns:
            c.execute("ALTER TABLE hospital_award_applications ADD COLUMN proof_document TEXT")

        c.execute("""
            CREATE TABLE IF NOT EXISTS hospital_award_application_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                application_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                note TEXT,
                proof_document TEXT,
                actor_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(application_id) REFERENCES hospital_award_applications(id),
                FOREIGN KEY(actor_id) REFERENCES users(id)
            )
        """)

        c.execute("CREATE TABLE IF NOT EXISTS symptom_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, symptom_text TEXT NOT NULL, created_at TEXT)")

        # 新增：建立系統公告表格
        c.execute("""
            CREATE TABLE IF NOT EXISTS announcements(
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                content TEXT NOT NULL, 
                is_active INTEGER DEFAULT 0, -- 0 為關閉，1 為顯示
                created_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage_logs(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                feature TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS app_settings(
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS backup_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_name TEXT NOT NULL,
                file_size_mb REAL NOT NULL,
                file_size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                created_by INTEGER,
                actor_username TEXT,
                FOREIGN KEY(created_by) REFERENCES users(id)
            )
        """)
        c.execute("""
            INSERT OR IGNORE INTO app_settings(key, value, updated_at)
            VALUES ('ai_summary_mode', 'auto', ?)
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))

        c.execute("""
            CREATE TABLE IF NOT EXISTS hospital_notifications(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital_id INTEGER,
                user_id INTEGER,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                status TEXT DEFAULT 'unread',
                category TEXT DEFAULT 'general',
                link_url TEXT,
                created_at TEXT NOT NULL,
                created_by INTEGER,
                FOREIGN KEY(hospital_id) REFERENCES hospitals(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)

        c.execute("PRAGMA table_info(hospital_notifications)")
        notification_columns = c.fetchall()
        hospital_id_column = next((column for column in notification_columns if column[1] == 'hospital_id'), None)
        if hospital_id_column and hospital_id_column[3] == 1:
            print("🔧 資料庫升級：正在允許院方通知不綁定醫院...")
            c.execute("ALTER TABLE hospital_notifications RENAME TO hospital_notifications_old")
            c.execute("""
                CREATE TABLE hospital_notifications(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hospital_id INTEGER,
                    user_id INTEGER,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    status TEXT DEFAULT 'unread',
                    category TEXT DEFAULT 'general',
                    link_url TEXT,
                    created_at TEXT NOT NULL,
                    created_by INTEGER,
                    FOREIGN KEY(hospital_id) REFERENCES hospitals(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            c.execute("""
                INSERT INTO hospital_notifications
                    (id, hospital_id, user_id, title, content, status, created_at, created_by)
                SELECT id, hospital_id, user_id, title, content, status, created_at, created_by
                FROM hospital_notifications_old
            """)
            c.execute("DROP TABLE hospital_notifications_old")

        c.execute("PRAGMA table_info(hospital_notifications)")
        notification_column_names = [column[1] for column in c.fetchall()]
        if 'category' not in notification_column_names:
            c.execute("ALTER TABLE hospital_notifications ADD COLUMN category TEXT DEFAULT 'general'")
        if 'link_url' not in notification_column_names:
            c.execute("ALTER TABLE hospital_notifications ADD COLUMN link_url TEXT")

        c.execute("""
            CREATE TABLE IF NOT EXISTS user_hospital_favorites(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                hospital_id INTEGER NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, hospital_id),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(hospital_id) REFERENCES hospitals(id)
            )
        """)

        conn.commit()

ensure_schema()
print("🌟 真正的資料庫位置：", HR_DB)

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or "dev-only-change-this-secret-key"
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, default_limits=["200 per day", "50 per hour"])
logging.getLogger('werkzeug').setLevel(logging.ERROR)

@app.after_request
def log_page_request(response):
    content_type = response.headers.get('Content-Type', '')
    if request.method == 'GET' and content_type.startswith('text/html') and request.endpoint != 'static':
        print(f"📍 開啟頁面：{request.path} ({request.endpoint or 'unknown'}) - {response.status_code}", flush=True)
    return response

def normalize_binary_sentiment(value):
    text = str(value or "").strip().upper()
    if text in ("POSITIVE", "NEGATIVE"):
        return text
    if text in ("正面", "正向", "好評", "正評", "POS", "1"):
        return "POSITIVE"
    if text in ("負面", "負向", "差評", "負評", "NEG", "0", "-1"):
        return "NEGATIVE"
    return None

def calculate_sentiment_audit_metrics(items):
    total = len(items)
    tp = fn = fp = tn = 0
    manual_positive = manual_negative = model_positive = model_negative = correct = 0

    for item in items:
        manual = normalize_binary_sentiment(item.get('manual_sentiment'))
        model = normalize_binary_sentiment(item.get('model_sentiment'))
        if manual == "POSITIVE":
            manual_positive += 1
        elif manual == "NEGATIVE":
            manual_negative += 1

        if model == "POSITIVE":
            model_positive += 1
        elif model == "NEGATIVE":
            model_negative += 1

        if manual == model:
            correct += 1
        if manual == "POSITIVE" and model == "POSITIVE":
            tp += 1
        elif manual == "POSITIVE" and model == "NEGATIVE":
            fn += 1
        elif manual == "NEGATIVE" and model == "POSITIVE":
            fp += 1
        elif manual == "NEGATIVE" and model == "NEGATIVE":
            tn += 1

    def safe_div(numerator, denominator):
        return numerator / denominator if denominator else 0

    positive_precision = safe_div(tp, tp + fp)
    positive_recall = safe_div(tp, tp + fn)
    negative_precision = safe_div(tn, tn + fn)
    negative_recall = safe_div(tn, tn + fp)

    def f1(precision, recall):
        return safe_div(2 * precision * recall, precision + recall)

    return {
        'total': total,
        'manual_positive': manual_positive,
        'manual_negative': manual_negative,
        'model_positive': model_positive,
        'model_negative': model_negative,
        'correct': correct,
        'incorrect': total - correct,
        'accuracy': safe_div(correct, total),
        'positive_precision': positive_precision,
        'positive_recall': positive_recall,
        'positive_f1': f1(positive_precision, positive_recall),
        'negative_precision': negative_precision,
        'negative_recall': negative_recall,
        'negative_f1': f1(negative_precision, negative_recall),
        'tp': tp,
        'fn': fn,
        'fp': fp,
        'tn': tn
    }

def fetch_sentiment_audit_items(cursor, batch_id):
    cursor.execute("""
        SELECT sai.id, sai.batch_id, sai.review_id, sai.manual_sentiment, sai.model_sentiment,
               sai.is_correct, r.content, r.rating, h.name AS hospital_name
        FROM sentiment_audit_items sai
        JOIN reviews r ON r.id = sai.review_id
        JOIN hospitals h ON h.id = r.hospital_id
        WHERE sai.batch_id = ?
        ORDER BY sai.id
    """, (batch_id,))
    return [dict(row) for row in cursor.fetchall()]

# 👇 新增：證明文件上傳資料夾設定
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads', 'proofs')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024
ALLOWED_PROOF_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}

def save_proof_document(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None

    original_filename = secure_filename(file_storage.filename)
    if "." not in original_filename:
        return None, "請上傳 PDF、PNG、JPG 或 JPEG 格式的證明文件。"

    ext = original_filename.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_PROOF_EXTENSIONS:
        return None, "證明文件格式不支援，請上傳 PDF、PNG、JPG 或 JPEG。"

    filename = f"{uuid.uuid4().hex}.{ext}"
    file_storage.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return filename, None

def log_award_application_history(cursor, application_id, action, note=None, proof_document=None, actor_id=None):
    cursor.execute("""
        INSERT INTO hospital_award_application_history
            (application_id, action, note, proof_document, actor_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        application_id,
        action,
        note,
        proof_document,
        actor_id,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

@app.errorhandler(413)
def file_too_large(error):
    flash('上傳檔案太大，請選擇 8MB 以下的證明文件。', 'analyze_error')
    return redirect(request.referrer or url_for('register'))

bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

os.makedirs('data', exist_ok=True)

# ==========================================
# 👤 使用者類別與載入
# ==========================================
class User(UserMixin):
    def __init__(self, id_, username, password, is_admin=0, role='user', hospital_id=None, approval_status='approved', rejection_reason=None):
        self.id = id_
        self.username = username
        self.password = password
        self.is_admin = is_admin
        self.role = role or ('admin' if is_admin else 'user')
        self.hospital_id = hospital_id
        self.approval_status = approval_status or 'approved'
        self.rejection_reason = rejection_reason

    @property
    def is_hospital_user(self):
        return self.role == 'hospital' and self.approval_status == 'approved' and self.hospital_id is not None

@login_manager.user_loader
def load_user(user_id):
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row  
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
    if row:
        return User(
            id_=row['id'],
            username=row['username'],
            password=row['password'],
            is_admin=row['is_admin'],
            role=row['role'] if 'role' in row.keys() else ('admin' if row['is_admin'] else 'user'),
            hospital_id=row['hospital_id'] if 'hospital_id' in row.keys() else None,
            approval_status=row['approval_status'] if 'approval_status' in row.keys() else 'approved',
            rejection_reason=row['rejection_reason'] if 'rejection_reason' in row.keys() else None
        )
    return None

def init_admin_user(bcrypt):
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", ('admin',))
        if not c.fetchone():
            hashed_pw = bcrypt.generate_password_hash('123456').decode('utf-8')
            c.execute(
                "INSERT INTO users (username, password, is_admin, role, approval_status) VALUES (?, ?, 1, 'admin', 'approved')",
                ('admin', hashed_pw)
            )
            print("✅ 已建立預設管理員 (帳號: admin / 密碼: 123456)")

init_admin_user(bcrypt)

def can_view_hospital_profile(hospital_id):
    if current_user.is_admin:
        return True
    return (
        getattr(current_user, 'role', None) == 'hospital'
        and current_user.approval_status == 'approved'
        and current_user.hospital_id == hospital_id
    )

def get_favorite_info(user_id, hospital_id):
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT note, created_at, updated_at
            FROM user_hospital_favorites
            WHERE user_id = ? AND hospital_id = ?
        """, (user_id, hospital_id))
        row = cursor.fetchone()
    return dict(row) if row else None

def get_user_favorites(user_id):
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                f.hospital_id,
                f.note,
                f.created_at,
                f.updated_at,
                h.name,
                h.address,
                COALESCE(MAX(r.stored_at), h.created_at) AS latest_update,
                COUNT(r.id) AS review_count,
                SUM(CASE WHEN r.analyzed_sentiment = 'POSITIVE' THEN 1 ELSE 0 END) AS positive_count,
                SUM(CASE WHEN r.analyzed_sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count
            FROM user_hospital_favorites f
            JOIN hospitals h ON f.hospital_id = h.id
            LEFT JOIN reviews r ON h.id = r.hospital_id
            WHERE f.user_id = ?
            GROUP BY f.id
            ORDER BY f.updated_at DESC, f.id DESC
        """, (user_id,))
        rows = cursor.fetchall()

    favorites = []
    for row in rows:
        review_count = row['review_count'] or 0
        positive_count = row['positive_count'] or 0
        negative_count = row['negative_count'] or 0
        display_address, _ = resolve_hospital_address(row['name'], row['address'])
        favorites.append({
            'hospital_id': row['hospital_id'],
            'name': row['name'],
            'address': display_address,
            'note': row['note'] or '',
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'latest_update': row['latest_update'] or '--',
            'review_count': review_count,
            'positive_count': positive_count,
            'negative_count': negative_count,
            'positive_rate': round(positive_count / review_count * 100) if review_count else 0,
            'negative_rate': round(negative_count / review_count * 100) if review_count else 0
        })
    return favorites

def is_hospital_favorite(user_id, hospital_id):
    return get_favorite_info(user_id, hospital_id) is not None

def normalize_hospital_name(name):
    return str(name or "").replace("臺", "台").strip()

def is_unknown_address(address):
    text = str(address or "").strip()
    return not text or "地址未知" in text or text.lower() in ["nan", "none", "null"]

_hospital_address_cache = None
_hospital_location_cache = None

def get_hospital_address_from_excel(hospital_name):
    global _hospital_address_cache
    if _hospital_address_cache is None:
        _hospital_address_cache = {}
        if os.path.exists(HOSPITAL_EXCEL_PATH):
            try:
                df = pd.read_excel(HOSPITAL_EXCEL_PATH)
                if '醫事機構名稱' in df.columns and '機構地址' in df.columns:
                    for _, row in df.iterrows():
                        name = normalize_hospital_name(row.get('醫事機構名稱'))
                        address = str(row.get('機構地址') or '').strip()
                        if name and address and address.lower() != 'nan':
                            _hospital_address_cache[name] = address
            except Exception as e:
                print(f"⚠️ 讀取醫院地址 Excel 失敗: {e}")

    normalized_name = normalize_hospital_name(hospital_name)
    if normalized_name in _hospital_address_cache:
        return _hospital_address_cache[normalized_name]

    for known_name, address in _hospital_address_cache.items():
        if normalized_name and (normalized_name in known_name or known_name in normalized_name):
            return address
    return None

def get_hospital_location_from_excel(hospital_name):
    global _hospital_location_cache
    if _hospital_location_cache is None:
        _hospital_location_cache = {}
        if os.path.exists(HOSPITAL_EXCEL_PATH):
            try:
                df = pd.read_excel(HOSPITAL_EXCEL_PATH)
                df.columns = df.columns.str.strip()
                required_columns = {'醫事機構名稱', 'latitude', 'longitude'}
                if required_columns.issubset(set(df.columns)):
                    for _, row in df.iterrows():
                        name = normalize_hospital_name(row.get('醫事機構名稱'))
                        latitude = pd.to_numeric(row.get('latitude'), errors='coerce')
                        longitude = pd.to_numeric(row.get('longitude'), errors='coerce')
                        if name and pd.notna(latitude) and pd.notna(longitude):
                            _hospital_location_cache[name] = {
                                'latitude': float(latitude),
                                'longitude': float(longitude)
                            }
                else:
                    print("⚠️ 醫院定位 Excel 欄位不足，請確認有「醫事機構名稱」、「latitude」、「longitude」。")
            except Exception as e:
                print(f"⚠️ 讀取醫院定位 Excel 失敗: {e}")

    normalized_name = normalize_hospital_name(hospital_name)
    if normalized_name in _hospital_location_cache:
        return _hospital_location_cache[normalized_name]
    return None

def sync_hospital_locations_from_excel():
    updated_count = 0
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, latitude, longitude
            FROM hospitals
        """)
        hospitals = cursor.fetchall()

        for hospital in hospitals:
            location = get_hospital_location_from_excel(hospital['name'])
            if not location:
                continue
            needs_update = hospital['latitude'] in (None, '') or hospital['longitude'] in (None, '')
            if not needs_update:
                try:
                    needs_update = (
                        abs(float(hospital['latitude']) - location['latitude']) > 0.000001
                        or abs(float(hospital['longitude']) - location['longitude']) > 0.000001
                    )
                except (TypeError, ValueError):
                    needs_update = True
            if not needs_update:
                continue
            cursor.execute("""
                UPDATE hospitals
                SET latitude = ?, longitude = ?
                WHERE id = ?
            """, (location['latitude'], location['longitude'], hospital['id']))
            updated_count += 1

        conn.commit()
    return updated_count

def calculate_distance_km(lat1, lng1, lat2, lng2):
    radius_km = 6371.0
    lat1_rad = math.radians(float(lat1))
    lng1_rad = math.radians(float(lng1))
    lat2_rad = math.radians(float(lat2))
    lng2_rad = math.radians(float(lng2))

    delta_lat = lat2_rad - lat1_rad
    delta_lng = lng2_rad - lng1_rad
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lng / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))

def resolve_hospital_address(hospital_name, db_address):
    # 1. 取得原始地址，並清除以前存入的不必要後綴文字
    addr = str(db_address or "").strip()
    addr = addr.replace("（批次自動匯入）", "").replace("(批次自動匯入)", "")
    addr = addr.replace("（地址未知）", "").replace("(地址未知)", "")
    addr = addr.strip() # 再次去除前後空白
    
    # 2. 💡 關鍵修正：如果清完變成空的、無效值，或是「剛好只剩下醫院名稱」，就去 Excel 抓真實地址！
    if not addr or addr.lower() in ["nan", "none", "null", "地址待補", "未知"] or addr == hospital_name:
        excel_address = get_hospital_address_from_excel(hospital_name)
        if excel_address:
            addr = str(excel_address).strip()
            
    # 3. 如果 Excel 真的也沒有，才顯示醫院名稱
    if not addr or addr.lower() in ["nan", "none", "null", "地址待補", "未知"]:
        addr = hospital_name
        
    return addr, "db" 

# 假設你的資料庫變數名稱叫做 HR_DB (請根據你 app.py 裡的設定確認一下)
def upgrade_db():
    try:
        with sqlite3.connect(HR_DB) as conn:
            cursor = conn.cursor()
            # 嘗試新增 proof_document 欄位
            cursor.execute("ALTER TABLE users ADD COLUMN proof_document TEXT;")
            conn.commit()
            print("✅ 資料庫更新成功：已新增 proof_document 欄位！")
    except sqlite3.OperationalError as e:
        # 如果欄位已經存在，SQLite 會報錯 "duplicate column name"，我們把它攔截下來略過就好
        if "duplicate column name" in str(e).lower():
            print("ℹ️ proof_document 欄位已經存在，無需新增。")
        else:
            print(f"⚠️ 資料庫更新發生其他錯誤：{e}")

# 讓程式每次啟動時，都先默默檢查並執行一次
upgrade_db()

# ==========================================
# 🌐 路由設定
# ==========================================

@app.route('/')
@app.route('/index') 
@login_required
def index():
    return render_template('index.html', username=session.get('username'))

@app.route('/captcha')
def get_captcha():
    chars = string.ascii_uppercase + string.digits
    captcha_text = ''.join(random.choice(chars) for _ in range(4))
    session['captcha_code'] = captcha_text.upper()
    image = ImageCaptcha(width=160, height=50)
    data = image.generate(captcha_text)
    return send_file(data, mimetype='image/png')

@app.route('/search')
@login_required
def search_page():
    return redirect(url_for('google_page'))

@app.route('/region', methods=['GET', 'POST'])
@login_required
def region():
    selected_region = request.args.get('region') or request.form.get('region')
    city_hospitals = {}
    hospital_times = {} # 🌟 新增：用來存放醫院對應的時間

    if selected_region and selected_region in GLOBAL_HOSPITALS_DATA:
        city_hospitals = GLOBAL_HOSPITALS_DATA[selected_region]
        
        # 🌟 核心邏輯：去資料庫抓取所有醫院的最後更新時間
        try:
            with sqlite3.connect(HR_DB) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # 撈取醫院名稱與對應的最晚評論存入時間
                cursor.execute("""
                    SELECT h.name, MAX(r.stored_at) as last_time 
                    FROM hospitals h
                    JOIN reviews r ON h.id = r.hospital_id
                    GROUP BY h.name
                """)
                for row in cursor.fetchall():
                    hospital_times[row['name']] = row['last_time']
        except Exception as e:
            print(f"⚠️ 地區頁面讀取時間失敗: {e}")

    # 🛑 關鍵：確保你是回傳 render_template 而不是 jsonify
    return render_template('region.html', 
                           selected_region=selected_region, 
                           city_hospitals=city_hospitals,
                           hospital_times=hospital_times, # 🌟 傳給前端
                           username=session.get('username'))

@app.route('/sentiment_audit')
@login_required
def sentiment_audit_list():
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.id, b.batch_name, b.sample_size, b.status, b.created_at, b.completed_at,
                   COUNT(i.id) AS actual_sample_size
            FROM sentiment_audit_batches b
            LEFT JOIN sentiment_audit_items i ON i.batch_id = b.id
            GROUP BY b.id
            ORDER BY b.id DESC
        """)
        batches = [dict(row) for row in cursor.fetchall()]
    return render_template('sentiment_audit_list.html', batches=batches)

@app.route('/api/sentiment_audit/create', methods=['POST'])
@login_required
def create_sentiment_audit_batch():
    sample_size = 30
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO sentiment_audit_batches (batch_name, sample_size, status, created_at)
            VALUES (?, ?, 'pending', ?)
        """, ("情緒分析人工抽驗", sample_size, created_at))
        batch_id = cursor.lastrowid
        cursor.execute(
            "UPDATE sentiment_audit_batches SET batch_name = ? WHERE id = ?",
            (f"情緒分析人工抽驗 #{batch_id}", batch_id)
        )

        selected = []
        selected_ids = set()
        for exclude_audited in (True, False):
            if len(selected) >= sample_size:
                break
            remaining = sample_size - len(selected)
            params = []
            conditions = [
                "r.content IS NOT NULL",
                "TRIM(r.content) != ''",
                """(
                    UPPER(TRIM(r.analyzed_sentiment)) IN ('POSITIVE', 'NEGATIVE')
                    OR TRIM(r.analyzed_sentiment) IN ('正面', '正向', '好評', '正評', '負面', '負向', '差評', '負評')
                )"""
            ]
            if exclude_audited:
                conditions.append("""
                    NOT EXISTS (
                        SELECT 1 FROM sentiment_audit_items old_item
                        WHERE old_item.review_id = r.id
                    )
                """)
            if selected_ids:
                placeholders = ",".join(["?"] * len(selected_ids))
                conditions.append(f"r.id NOT IN ({placeholders})")
                params.extend(selected_ids)
            params.append(remaining)
            cursor.execute(f"""
                SELECT r.id, r.analyzed_sentiment
                FROM reviews r
                WHERE {' AND '.join(conditions)}
                ORDER BY RANDOM()
                LIMIT ?
            """, params)
            for row in cursor.fetchall():
                model_sentiment = normalize_binary_sentiment(row['analyzed_sentiment'])
                if model_sentiment:
                    selected.append({'id': row['id'], 'model_sentiment': model_sentiment})
                    selected_ids.add(row['id'])

        cursor.executemany("""
            INSERT INTO sentiment_audit_items (batch_id, review_id, model_sentiment, created_at)
            VALUES (?, ?, ?, ?)
        """, [(batch_id, item['id'], item['model_sentiment'], created_at) for item in selected])
        cursor.execute(
            "UPDATE sentiment_audit_batches SET sample_size = ? WHERE id = ?",
            (len(selected), batch_id)
        )
        conn.commit()

    return jsonify({
        'success': True,
        'batch_id': batch_id,
        'sample_size': len(selected),
        'redirect_url': url_for('sentiment_audit_detail', batch_id=batch_id)
    })

@app.route('/sentiment_audit/<int:batch_id>')
@login_required
def sentiment_audit_detail(batch_id):
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sentiment_audit_batches WHERE id = ?", (batch_id,))
        batch = cursor.fetchone()
        if not batch:
            flash('找不到指定的情緒分析人工抽驗批次。', 'analyze_error')
            return redirect(url_for('sentiment_audit_list'))

        items = fetch_sentiment_audit_items(cursor, batch_id)
        metrics = calculate_sentiment_audit_metrics(items) if batch['status'] == 'completed' else None

    return render_template(
        'sentiment_audit_detail.html',
        batch=dict(batch),
        items=items,
        metrics=metrics
    )

@app.route('/api/sentiment_audit/<int:batch_id>/submit', methods=['POST'])
@login_required
def submit_sentiment_audit_batch(batch_id):
    payload = request.get_json(silent=True) or request.form
    raw_items = payload.get('items') if isinstance(payload, dict) else None
    if raw_items is None:
        raw_items = []
        for key, value in request.form.items():
            if key.startswith('manual_sentiment_'):
                raw_items.append({'item_id': key.replace('manual_sentiment_', '', 1), 'manual_sentiment': value})

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sentiment_audit_batches WHERE id = ?", (batch_id,))
        batch = cursor.fetchone()
        if not batch:
            return jsonify({'success': False, 'message': '找不到指定批次。'}), 404
        if batch['status'] == 'completed':
            return jsonify({'success': False, 'message': '此批次已完成，不能重複送出。'}), 400

        items = fetch_sentiment_audit_items(cursor, batch_id)
        item_ids = {item['id'] for item in items}
        manual_by_id = {}
        for item in raw_items:
            try:
                item_id = int(item.get('item_id'))
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': '送出的項目格式不正確。'}), 400
            manual_sentiment = normalize_binary_sentiment(item.get('manual_sentiment'))
            if item_id not in item_ids or manual_sentiment not in ('POSITIVE', 'NEGATIVE'):
                return jsonify({'success': False, 'message': '人工標記只能是 POSITIVE 或 NEGATIVE。'}), 400
            manual_by_id[item_id] = manual_sentiment

        if len(manual_by_id) != len(items):
            return jsonify({'success': False, 'message': '請完成所有評論的人工標記後再送出。'}), 400

        for item in items:
            manual_sentiment = manual_by_id[item['id']]
            is_correct = 1 if manual_sentiment == normalize_binary_sentiment(item['model_sentiment']) else 0
            cursor.execute("""
                UPDATE sentiment_audit_items
                SET manual_sentiment = ?, is_correct = ?
                WHERE id = ? AND batch_id = ?
            """, (manual_sentiment, is_correct, item['id'], batch_id))

        cursor.execute("""
            UPDATE sentiment_audit_batches
            SET status = 'completed', completed_at = ?
            WHERE id = ?
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), batch_id))
        conn.commit()

    return jsonify({
        'success': True,
        'message': '情緒分析人工抽驗已完成並計算結果。',
        'redirect_url': url_for('sentiment_audit_detail', batch_id=batch_id)
    })

# ==========================================
# 🚀 爬蟲與分析邏輯
# ==========================================

def emit_crawl_progress(progress_callback=None, **kwargs):
    if not progress_callback:
        return
    try:
        progress_callback(**kwargs)
    except Exception as progress_error:
        print(f"⚠️ 更新爬蟲進度失敗: {progress_error}")

class BatchCrawlStopped(Exception):
    pass

def raise_if_stop_requested(stop_event=None):
    if stop_event and stop_event.is_set():
        raise BatchCrawlStopped("批次爬蟲已被手動停止")

def wait_if_pause_requested(pause_event=None, stop_event=None, progress_callback=None):
    if not pause_event or not pause_event.is_set():
        return

    emit_crawl_progress(
        progress_callback,
        status='paused',
        phase='paused',
        pause_requested=True,
        message='批次爬蟲已暫停，等待繼續...'
    )
    while pause_event.is_set():
        raise_if_stop_requested(stop_event)
        time.sleep(0.5)

    emit_crawl_progress(
        progress_callback,
        status='running',
        phase='running',
        pause_requested=False,
        message='批次爬蟲已繼續'
    )

def interruptible_sleep(seconds, stop_event=None, pause_event=None, progress_callback=None, interval=0.25):
    end_time = time.time() + seconds
    while time.time() < end_time:
        raise_if_stop_requested(stop_event)
        wait_if_pause_requested(pause_event, stop_event, progress_callback)
        time.sleep(min(interval, max(end_time - time.time(), 0)))
    raise_if_stop_requested(stop_event)
    wait_if_pause_requested(pause_event, stop_event, progress_callback)

def find_reviews_scroll_container(driver):
    selectors = [
        "div[role='feed']",
        "div.m6QErb.DxyBCb.kA9KIf.dS8AEf",
        "div.m6QErb[tabindex='-1']"
    ]
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                if element.is_displayed():
                    return element
        except Exception:
            continue

    try:
        return driver.execute_script("""
            const reviews = Array.from(document.querySelectorAll('.jftiEf'));
            if (!reviews.length) return null;
            let node = reviews[0].parentElement;
            while (node && node !== document.body) {
                const style = getComputedStyle(node);
                if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && node.scrollHeight > node.clientHeight + 50) {
                    return node;
                }
                node = node.parentElement;
            }
            return null;
        """)
    except Exception:
        return None

def scroll_reviews_feed(driver, scrollable_div, containers):
    if scrollable_div:
        moved = driver.execute_script("""
            const el = arguments[0];
            const before = el.scrollTop;
            const step = Math.max(1400, el.clientHeight * 1.8);
            el.scrollBy({ top: step, left: 0, behavior: 'auto' });
            el.dispatchEvent(new WheelEvent('wheel', { deltaY: step, bubbles: true, cancelable: true }));
            return el.scrollTop !== before;
        """, scrollable_div)
        if moved:
            return True

    if containers:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'end', inline: 'nearest'});", containers[-1])
            return True
        except Exception:
            pass

    try:
        driver.execute_script("window.scrollBy(0, 1600);")
        return True
    except Exception:
        return False

def click_google_maps_element(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({ block: 'center', inline: 'center' });", element)
        ActionChains(driver).move_to_element(element).pause(0.15).click().perform()
    except Exception:
        driver.execute_script("""
            const el = arguments[0];
            el.scrollIntoView({ block: 'center', inline: 'center' });
            el.click();
        """, element)

def find_visible_google_maps_element_by_text(driver, selectors, keywords):
    return driver.execute_script("""
        const selectors = arguments[0];
        const keywords = arguments[1];
        const nodes = Array.from(document.querySelectorAll(selectors));
        const isVisible = el => {
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
        };
        return nodes.find(el => {
            if (!isVisible(el)) return false;
            const text = `${el.textContent || ''} ${el.getAttribute('aria-label') || ''}`.trim();
            return keywords.some(keyword => text.includes(keyword));
        }) || null;
    """, selectors, keywords)

def find_google_maps_menu_item_by_text(driver, keywords):
    return driver.execute_script("""
        const keywords = arguments[0];
        const isVisible = el => {
            const rect = el.getBoundingClientRect();
            const style = getComputedStyle(el);
            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
        };
        const menus = Array.from(document.querySelectorAll("[role='menu'], [role='listbox'], [role='dialog']"))
            .filter(isVisible);
        const scopes = menus.length ? menus : [document.body];
        const selectors = [
            "[role='menuitemradio']",
            "[role='menuitem']",
            "[role='radio']",
            "[role='option']",
            "button",
            "div[aria-label]"
        ];
        for (const scope of scopes) {
            for (const selector of selectors) {
                const nodes = Array.from(scope.querySelectorAll(selector));
                for (const el of nodes) {
                    if (!isVisible(el)) continue;
                    const text = `${el.textContent || ''} ${el.getAttribute('aria-label') || ''}`.trim();
                    if (!keywords.some(keyword => text.includes(keyword))) continue;
                    return el.closest("[role='menuitemradio'], [role='menuitem'], [role='radio'], [role='option'], button") || el;
                }
            }
        }
        return null;
    """, keywords)

def get_first_review_signature(driver):
    try:
        return driver.execute_script("""
            const first = document.querySelector('.jftiEf');
            return first ? (first.innerText || '').trim().slice(0, 500) : '';
        """)
    except Exception:
        return ''

def reset_reviews_scroll_to_top(driver):
    try:
        driver.execute_script("""
            const feed = document.querySelector("div[role='feed']");
            const scrollable = feed || (() => {
                const reviews = Array.from(document.querySelectorAll('.jftiEf'));
                if (!reviews.length) return null;
                let node = reviews[0].parentElement;
                while (node && node !== document.body) {
                    const style = getComputedStyle(node);
                    if ((style.overflowY === 'auto' || style.overflowY === 'scroll') && node.scrollHeight > node.clientHeight + 50) {
                        return node;
                    }
                    node = node.parentElement;
                }
                return null;
            })();
            if (scrollable) scrollable.scrollTo({ top: 0, left: 0, behavior: 'auto' });
        """)
    except Exception:
        pass

def clear_google_maps_review_search(driver, expected_keyword=None):
    """清掉 Google Maps 評論頁內的關鍵字搜尋，回到一般評論列表。"""
    try:
        clicked = driver.execute_script("""
            const expected = String(arguments[0] || '').trim();
            const visible = el => {
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            let inputs = Array.from(document.querySelectorAll('input'))
                .filter(input => visible(input) && input.value && input.value.trim().length > 0)
                .map(input => ({ input, value: input.value.trim() }));

            if (expected) {
                inputs = inputs.filter(item =>
                    item.value === expected
                    || item.value.includes(expected)
                    || expected.includes(item.value)
                );
            } else {
                inputs = inputs.filter(item => item.value.length <= 8);
            }

            inputs.sort((a, b) => a.value.length - b.value.length);

            for (const item of inputs) {
                const input = item.input;
                const inputRect = input.getBoundingClientRect();
                let root = input.parentElement;
                for (let depth = 0; root && depth < 6; depth += 1, root = root.parentElement) {
                    const buttons = Array.from(root.querySelectorAll('button')).filter(visible);
                    const clearButton = buttons.find(button => {
                        const label = [
                            button.getAttribute('aria-label') || '',
                            button.getAttribute('title') || '',
                            button.textContent || ''
                        ].join(' ');
                        const rect = button.getBoundingClientRect();
                        const nearInput = Math.abs((rect.top + rect.bottom) / 2 - (inputRect.top + inputRect.bottom) / 2) < 70;
                        const rightSide = rect.left > inputRect.left;
                        const looksLikeClear = /清除|關閉|關掉|Close|Clear|取消|移除/i.test(label)
                            || button.querySelector('svg, i')
                            || Math.abs(rect.width - rect.height) < 18;
                        return nearInput && rightSide && looksLikeClear;
                    });
                    if (clearButton) {
                        clearButton.click();
                        return true;
                    }
                }
                input.focus();
                input.value = '';
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Escape', code: 'Escape', keyCode: 27 }));
                return true;
            }
            return false;
        """, expected_keyword or "")
        if clicked:
            print("🧹 已按叉叉清除評論搜尋條件。")
            return True
    except Exception as e:
        print(f"⚠️ 清除評論搜尋條件失敗: {e}")
    return False

def is_visible_newest_sort_checked(driver):
    try:
        return driver.execute_script("""
            const keywords = ['最新', 'Newest'];
            const isVisible = el => {
                const rect = el.getBoundingClientRect();
                const style = getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
            };
            const menus = Array.from(document.querySelectorAll("[role='menu'], [role='listbox'], [role='dialog']"))
                .filter(isVisible);
            const scopes = menus.length ? menus : [document.body];
            for (const scope of scopes) {
                const nodes = Array.from(scope.querySelectorAll("[role='menuitemradio'], [role='menuitem'], [role='radio'], [role='option'], button"));
                for (const el of nodes) {
                    if (!isVisible(el)) continue;
                    const text = `${el.textContent || ''} ${el.getAttribute('aria-label') || ''}`.trim();
                    if (!keywords.some(keyword => text.includes(keyword))) continue;
                    const checked = el.getAttribute('aria-checked') || el.getAttribute('aria-selected') || el.getAttribute('aria-pressed');
                    if (checked === 'true') return true;
                    if (checked === 'false') return false;
                    return null;
                }
            }
            return false;
        """)
    except Exception:
        return None

def switch_reviews_to_newest(driver, wait, stop_event=None, pause_event=None, progress_callback=None):
    def find_sort_button():
        sort_xpaths = [
            "//button[contains(@aria-label, '排序')]",
            "//button[contains(@aria-label, '排序依據')]",
            "//button[contains(@aria-label, 'Sort')]",
            "//button[contains(., '排序')]",
        ]
        for xpath in sort_xpaths:
            try:
                return wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
            except Exception:
                continue

        return find_visible_google_maps_element_by_text(
            driver,
            "button, [role='button']",
            ["排序", "排序依據", "Sort"]
        )

    for attempt in range(3):
        raise_if_stop_requested(stop_event)
        wait_if_pause_requested(pause_event, stop_event, progress_callback)

        sort_button = find_sort_button()
        if not sort_button:
            raise RuntimeError("找不到評論排序按鈕")

        click_google_maps_element(driver, sort_button)
        interruptible_sleep(0.8, stop_event, pause_event, progress_callback)

        newest_item = find_google_maps_menu_item_by_text(driver, ["最新", "Newest"])
        if not newest_item:
            print(f"⚠️ 第 {attempt + 1} 次找不到排序選單裡的「最新」，準備重試。")
            try:
                ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
            interruptible_sleep(0.4, stop_event, pause_event, progress_callback)
            continue

        print(f"🕒 第 {attempt + 1} 次嘗試點擊 Google Maps 評論排序：最新")
        click_google_maps_element(driver, newest_item)
        interruptible_sleep(1.8, stop_event, pause_event, progress_callback)

        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jftiEf")))
        except Exception:
            pass

        reset_reviews_scroll_to_top(driver)
        interruptible_sleep(1.0, stop_event, pause_event, progress_callback)
        try:
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        except Exception:
            pass
        print("✅ 已點擊 Google Maps 評論排序：最新，開始抓取評論。")
        return True

    raise RuntimeError("排序選單中找不到可確認的「最新」選項")

def parse_google_review_card(driver, review_element):
    try:
        text_el = review_element.find_element(By.CSS_SELECTOR, ".wiI7pd, .MyEned, span[lang]")
        text = remove_emojis(text_el.text.strip())
        try:
            more = review_element.find_element(By.CSS_SELECTOR, "button[aria-label*='全文'], button.w8nwRe")
            driver.execute_script("arguments[0].click();", more)
            text_el = review_element.find_element(By.CSS_SELECTOR, ".wiI7pd, .MyEned, span[lang]")
            text = remove_emojis(text_el.text.strip())
        except Exception:
            pass

        raw_time = "未知時間"
        try:
            date_el = review_element.find_element(By.XPATH, ".//span[contains(text(), '前') or contains(text(), '昨天')]")
            raw_time = date_el.text.replace("上次編輯：", "").replace("上次編輯:", "").strip()
        except Exception:
            pass

        if len(text) <= 1:
            return None

        return {
            'text': text,
            'time': normalize_google_review_time(raw_time),
            'relative_time': raw_time
        }
    except Exception:
        return None

def save_crawl_debug_snapshot(driver, hospital_name, reason):
    try:
        debug_dir = os.path.join(BASE_DIR, "debug", "crawler")
        os.makedirs(debug_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", hospital_name or "hospital")[:40]
        base_path = os.path.join(debug_dir, f"{timestamp}_{safe_name}_{reason}")
        driver.save_screenshot(base_path + ".png")
        with open(base_path + ".html", "w", encoding="utf-8") as debug_file:
            debug_file.write(driver.page_source or "")
        print(f"🧪 已儲存爬蟲除錯畫面：{base_path}.png / .html")
    except Exception as debug_error:
        print(f"⚠️ 儲存爬蟲除錯畫面失敗: {debug_error}")

def scrape_google_reviews(hospital_name, max_reviews=30, target_dept=None, progress_callback=None, stop_event=None, pause_event=None):
    """
    爬取 Google 評論，支援指定科別過濾。
    :param target_dept: 想要搜尋的特定科系關鍵字 (例如: '牙科')
    """
    print(f"🚀 啟動【接管模式】：{hospital_name} " + (f"過濾科別：{target_dept}" if target_dept else ""))
    emit_crawl_progress(
        progress_callback,
        phase='opening',
        current_review_count=0,
        target_review_count=max_reviews,
        scroll_round=0,
        message=f"正在開啟 Google Maps：{hospital_name}"
    )
    raise_if_stop_requested(stop_event)
    wait_if_pause_requested(pause_event, stop_event, progress_callback)
    options = webdriver.ChromeOptions()
    # options.add_experimental_option("debuggerAddress", "127.0.0.1:9222")

    chrome_bin = os.getenv("CHROME_BIN")
    if chrome_bin:
        options.binary_location = chrome_bin

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--lang=zh-TW")
    options.add_argument("--accept-lang=zh-TW,zh;q=0.9,en;q=0.8")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Docker / Linux 主機通常沒有桌面環境，使用環境變數控制是否啟用 headless。
    if os.getenv("SELENIUM_HEADLESS", "1") == "1":
        headless_mode = os.getenv("SELENIUM_HEADLESS_MODE", "new")
        options.add_argument("--headless" if headless_mode == "old" else "--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--remote-debugging-port=9222")
    options.add_argument("--window-size=1440,1200")

    # 2. 🌟 新增這兩行：給爬蟲一個專屬的記憶資料夾 (存放在你的 Mac 使用者目錄下)
    profile_path = os.path.join(BASE_DIR, 'Chrome_Spider_Profile')
    options.add_argument(f"--user-data-dir={profile_path}")

    driver = None
    try:
        chromedriver_path = os.getenv("CHROMEDRIVER_PATH")
        service = Service(chromedriver_path) if chromedriver_path else Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
        wait = WebDriverWait(driver, 10)
        
        driver.get(f"https://www.google.com.tw/maps/search/{hospital_name}?hl=zh-TW")
        interruptible_sleep(3, stop_event, pause_event, progress_callback)
        emit_crawl_progress(progress_callback, phase='locating', message=f"正在定位醫院頁面：{hospital_name}")
        raise_if_stop_requested(stop_event)
        wait_if_pause_requested(pause_event, stop_event, progress_callback)

        # --- 進入評論頁面邏輯 ---
        already_on_detail = False
        if len(driver.find_elements(By.CSS_SELECTOR, "button[role='tab']")) > 0: 
            already_on_detail = True
        elif len(driver.find_elements(By.XPATH, "//button[contains(@aria-label, '則評論')]")) > 0: 
            already_on_detail = True

        if not already_on_detail:
            try:
                search_results = driver.find_elements(By.CLASS_NAME, "hfpxzc")
                if search_results:
                    driver.execute_script("arguments[0].click();", search_results[0])
                    interruptible_sleep(3, stop_event, pause_event, progress_callback)
            except BatchCrawlStopped:
                raise
            except: pass

        raise_if_stop_requested(stop_event)
        wait_if_pause_requested(pause_event, stop_event, progress_callback)
        in_reviews_tab = False
        try:
            tabs = driver.find_elements(By.CSS_SELECTOR, "button[role='tab']")
            for tab in tabs:
                if "評論" in tab.text or "評論" in tab.get_attribute("aria-label"):
                    driver.execute_script("arguments[0].click();", tab)
                    in_reviews_tab = True
                    break
        except: pass

        if not in_reviews_tab:
            try:
                star_btns = driver.find_elements(By.XPATH, "//button[contains(@aria-label, '則評論')]")
                if star_btns:
                    driver.execute_script("arguments[0].click();", star_btns[0])
            except: pass

        try:
            wait.until(EC.presence_of_element_located((By.CLASS_NAME, "jftiEf")))
            interruptible_sleep(1, stop_event, pause_event, progress_callback)
        except BatchCrawlStopped:
            raise
        except: pass
        emit_crawl_progress(progress_callback, phase='sorting', message=f"正在切換最新評論排序：{hospital_name}")
        raise_if_stop_requested(stop_event)
        wait_if_pause_requested(pause_event, stop_event, progress_callback)

        # --- ⚡ 嘗試切換為最新排序 ---
        try:
            switch_reviews_to_newest(driver, wait, stop_event, pause_event, progress_callback)
            emit_crawl_progress(progress_callback, phase='sorting', message=f"已切換為最新評論排序：{hospital_name}")
        except BatchCrawlStopped:
            raise
        except Exception as e:
            print(f"⚠️ 排序切換失敗: {e}")
            emit_crawl_progress(progress_callback, phase='error', message=f"評論排序切換失敗，已列入失敗重爬：{hospital_name}")
            save_crawl_debug_snapshot(driver, hospital_name, "sort_failed")
            try: ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            except: pass
            raise RuntimeError("評論排序無法切換到最新")

        # ==========================================
        # 🔍 新增：自動點擊放大鏡並搜尋科別 (核彈級底層 JS 送出版)
        # ==========================================
        review_search_keyword = None
        if target_dept:
            try:
                raise_if_stop_requested(stop_event)
                wait_if_pause_requested(pause_event, stop_event, progress_callback)
                # 💡 關鍵修改：自動把「科」字去掉，擴大搜尋命中率！
                # 例如：「牙科」->「牙」，「眼科」->「眼」，「小兒科」->「小兒」
                search_keyword = target_dept.replace("科", "")
                review_search_keyword = search_keyword
                
                print(f"🔎 嘗試過濾科別評論：原本選【{target_dept}】，實際輸入【{search_keyword}】")
                
                # 1. 點擊放大鏡按鈕展開輸入框
                search_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "button[aria-label='搜尋評論']")))
                driver.execute_script("arguments[0].click();", search_btn)
                interruptible_sleep(1.5, stop_event, pause_event, progress_callback)

                # 獲取當前閃爍游標的輸入框
                active_input = driver.switch_to.active_element
                
                if active_input.tag_name == "input":
                    print("🎯 游標已對焦，開始輸入文字...")
                    active_input.clear()
                    interruptible_sleep(0.5, stop_event, pause_event, progress_callback)
                    
                    # 💡 這裡改成打 search_keyword
                    for char in search_keyword:
                        raise_if_stop_requested(stop_event)
                        wait_if_pause_requested(pause_event, stop_event, progress_callback)
                        active_input.send_keys(char)
                        interruptible_sleep(0.2, stop_event, pause_event, progress_callback)
                    
                    interruptible_sleep(1.0, stop_event, pause_event, progress_callback) # 等待字完全進去，讓 React 狀態更新
                    
                    # 核彈級解法：用純 JS 模擬最完整的 Enter 鍵盤生命週期
                    print("⚡ 啟動 JS 底層 Enter 觸發器...")
                    js_enter = """
                    var input = arguments[0];
                    input.dispatchEvent(new KeyboardEvent('keydown', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13}));
                    input.dispatchEvent(new KeyboardEvent('keypress', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13}));
                    input.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true, cancelable: true, key: 'Enter', code: 'Enter', keyCode: 13}));
                    """
                    driver.execute_script(js_enter, active_input)
                    print(f"✅ 已強制送出「{search_keyword}」搜尋指令！")
                
                else:
                    print("⚠️ 找不到對焦的輸入框，請確認視窗狀態。")
                
                print("⏳ 等待過濾結果載入...")
                interruptible_sleep(4.0, stop_event, pause_event, progress_callback) # 等待 Google 畫面重整
                
                # 重新定位滾動視窗
                scrollable_div = find_reviews_scroll_container(driver)

            except BatchCrawlStopped:
                raise
            except Exception as e:
                print(f"⚠️ 搜尋科別過濾失敗: {e}")

        # --- 抓取評論邏輯 ---
        reviews_data = []
        unique_ids = set()
        scrollable_div = find_reviews_scroll_container(driver)

        no_new_data_count = 0
        stuck_scroll_count = 0
        for i in range(50):
            raise_if_stop_requested(stop_event)
            wait_if_pause_requested(pause_event, stop_event, progress_callback)
            if len(reviews_data) >= max_reviews: break
            prev_len = len(reviews_data)
            emit_crawl_progress(
                progress_callback,
                phase='collecting',
                current_review_count=len(reviews_data),
                target_review_count=max_reviews,
                scroll_round=i + 1,
                message=f"正在抓取 {hospital_name} 評論：{len(reviews_data)}/{max_reviews} 則"
            )
            containers = driver.find_elements(By.CLASS_NAME, "jftiEf")
            
            for r in containers:
                parsed_review = parse_google_review_card(driver, r)
                if not parsed_review:
                    continue
                rid = hash(parsed_review['text'])
                if rid not in unique_ids:
                    reviews_data.append(parsed_review)
                    unique_ids.add(rid)
                if len(reviews_data) >= max_reviews: break
            
            if len(reviews_data) == prev_len:
                no_new_data_count += 1
                if no_new_data_count >= 6: break
            else: no_new_data_count = 0
            
            print(f"📥 捲動第 {i+1} 次，目前 {len(reviews_data)} 筆")
            try:
                before_scroll = None
                if scrollable_div:
                    before_scroll = driver.execute_script("return arguments[0].scrollTop", scrollable_div)

                moved = scroll_reviews_feed(driver, scrollable_div, containers)
                interruptible_sleep(0.9, stop_event, pause_event, progress_callback)

                after_scroll = None
                if scrollable_div:
                    try:
                        after_scroll = driver.execute_script("return arguments[0].scrollTop", scrollable_div)
                    except Exception:
                        after_scroll = None

                if scrollable_div and before_scroll == after_scroll and not moved:
                    stuck_scroll_count += 1
                else:
                    stuck_scroll_count = 0

                if stuck_scroll_count >= 2:
                    print("🔁 評論容器疑似卡住，重新定位滾動區塊。")
                    scrollable_div = find_reviews_scroll_container(driver)
                    stuck_scroll_count = 0
            except BatchCrawlStopped:
                raise
            except Exception as scroll_error:
                print(f"⚠️ 捲動失敗，重新定位評論容器：{scroll_error}")
                scrollable_div = find_reviews_scroll_container(driver)

        if target_dept and len(reviews_data) < max_reviews:
            print(f"🔁 科別篩選只抓到 {len(reviews_data)} 則，按叉叉清除搜尋後改抓一般評論。")
            if clear_google_maps_review_search(driver, review_search_keyword):
                interruptible_sleep(2.0, stop_event, pause_event, progress_callback)
                reset_reviews_scroll_to_top(driver)
                scrollable_div = find_reviews_scroll_container(driver)
                no_new_data_count = 0
                stuck_scroll_count = 0
                for i in range(50):
                    raise_if_stop_requested(stop_event)
                    wait_if_pause_requested(pause_event, stop_event, progress_callback)
                    if len(reviews_data) >= max_reviews:
                        break
                    prev_len = len(reviews_data)
                    emit_crawl_progress(
                        progress_callback,
                        phase='collecting',
                        current_review_count=len(reviews_data),
                        target_review_count=max_reviews,
                        scroll_round=i + 1,
                        message=f"正在抓取 {hospital_name} 一般評論：{len(reviews_data)}/{max_reviews} 則"
                    )
                    containers = driver.find_elements(By.CLASS_NAME, "jftiEf")
                    for r in containers:
                        parsed_review = parse_google_review_card(driver, r)
                        if not parsed_review:
                            continue
                        rid = hash(parsed_review['text'])
                        if rid not in unique_ids:
                            reviews_data.append(parsed_review)
                            unique_ids.add(rid)
                        if len(reviews_data) >= max_reviews:
                            break

                    if len(reviews_data) == prev_len:
                        no_new_data_count += 1
                        if no_new_data_count >= 6:
                            break
                    else:
                        no_new_data_count = 0

                    print(f"📥 一般評論捲動第 {i+1} 次，目前 {len(reviews_data)} 筆")
                    try:
                        before_scroll = None
                        if scrollable_div:
                            before_scroll = driver.execute_script("return arguments[0].scrollTop", scrollable_div)
                        moved = scroll_reviews_feed(driver, scrollable_div, containers)
                        interruptible_sleep(0.9, stop_event, pause_event, progress_callback)
                        after_scroll = None
                        if scrollable_div:
                            try:
                                after_scroll = driver.execute_script("return arguments[0].scrollTop", scrollable_div)
                            except Exception:
                                after_scroll = None
                        if scrollable_div and before_scroll == after_scroll and not moved:
                            stuck_scroll_count += 1
                        else:
                            stuck_scroll_count = 0
                        if stuck_scroll_count >= 2:
                            print("🔁 一般評論容器疑似卡住，重新定位滾動區塊。")
                            scrollable_div = find_reviews_scroll_container(driver)
                            stuck_scroll_count = 0
                    except BatchCrawlStopped:
                        raise
                    except Exception as scroll_error:
                        print(f"⚠️ 一般評論捲動失敗，重新定位評論容器：{scroll_error}")
                        scrollable_div = find_reviews_scroll_container(driver)

        emit_crawl_progress(
            progress_callback,
            phase='crawl_done',
            current_review_count=len(reviews_data),
            target_review_count=max_reviews,
            message=f"{hospital_name} 評論抓取完成：{len(reviews_data)} 則"
        )
        if not reviews_data:
            save_crawl_debug_snapshot(driver, hospital_name, "no_reviews")
        reviews_data.sort(key=lambda item: item.get('time') or '', reverse=True)
        return reviews_data
    except BatchCrawlStopped:
        print(f"🛑 已停止爬蟲: {hospital_name}")
        emit_crawl_progress(
            progress_callback,
            phase='stopping',
            message=f"正在停止批次爬蟲：{hospital_name}"
        )
        raise
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        if driver is not None:
            save_crawl_debug_snapshot(driver, hospital_name, "exception")
        return []
    
    finally:
        # 👇 新增這三行：不管爬蟲成功還是失敗，最後一定強制關閉視窗、釋放記憶體！
        if driver is not None:
            driver.quit()

def analyze_reviews(reviews):
    sentiments = []
    pos_count = 0
    neg_count = 0
    analyzer = get_sentiment_pipeline()

    for review in reviews:
        text = review['text']
        r_time = review.get('time', 'Unknown') 
        truncated_text = text[:500]
        
        # 👇 新增這行：偵測科別
        dept = detect_department(text)

        try:
            if analyzer:
                result = analyzer(truncated_text)[0]
                label = result['label']
                confidence = result['score'] * 100
                
                if 'positive' in label.lower():  
                    sentiment = "POSITIVE"
                    score = confidence           
                    pos_count += 1
                else:
                    sentiment = "NEGATIVE"
                    score = confidence     
                    neg_count += 1
            else:
                sentiment = "NEUTRAL"
                score = 50.0
        except Exception as e:
            print(f"Error analyzing review: {e}")
            sentiment = "NEUTRAL"
            score = 50.0

        issue_category = classify_negative_issue(text, sentiment)

        sentiments.append({
            'text': text, 
            'time': r_time, 
            'label': sentiment,
            'emotion': sentiment, 
            'score': round(score, 2),
            'department': dept,  # 👇 新增這行：把科別存進字典裡
            'issue_category': issue_category
        })

    return sentiments, pos_count, neg_count

# ==========================================
# 🤖 Gemini / 本地 AI 設定與備援機制
# ==========================================
GOOGLE_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY")
genai.configure(api_key=GOOGLE_API_KEY)
GEMINI_MODELS = [
    model.strip()
    for model in os.getenv("GOOGLE_GEMINI_MODELS", "gemini-flash-latest").split(",")
    if model.strip()
]
GEMINI_DAILY_LIMIT = os.getenv("GOOGLE_GEMINI_DAILY_LIMIT")

def get_app_setting(key, default=None):
    try:
        with sqlite3.connect(HR_DB) as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
            row = c.fetchone()
            return row[0] if row else default
    except Exception as e:
        print(f"⚠️ 讀取系統設定失敗 ({key}): {e}")
        return default

def set_app_setting(key, value):
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO app_settings(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (key, value, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()

def get_ai_summary_mode():
    mode = get_app_setting('ai_summary_mode', 'auto')
    return mode if mode in ['auto', 'gemini', 'local'] else 'auto'

def get_gemini_daily_limit():
    try:
        return int(GEMINI_DAILY_LIMIT) if GEMINI_DAILY_LIMIT else None
    except ValueError:
        return None

def log_ai_usage(provider, model, feature, status, error_message=None):
    try:
        with sqlite3.connect(HR_DB) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO ai_usage_logs(provider, model, feature, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                provider,
                model,
                feature,
                status,
                str(error_message)[:500] if error_message else None,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
    except Exception as e:
        print(f"⚠️ AI 使用紀錄寫入失敗: {e}")

def notify_admin_ai_quota(feature, error_message=None):
    return

def is_quota_error(error):
    message = str(error).lower()
    return any(keyword in message for keyword in ["429", "quota", "rate limit", "resource exhausted", "exhausted"])

def should_try_next_gemini_model(error):
    message = str(error).lower()
    retry_keywords = [
        "429", "quota", "rate limit", "resource exhausted", "exhausted",
        "503", "500", "unavailable", "internal", "deadline", "timeout", "timed out",
        "not found", "not supported", "permission denied", "model"
    ]
    return any(keyword in message for keyword in retry_keywords)

class GeminiQuotaExceeded(RuntimeError):
    pass

def get_gemini_quota_blocks():
    raw_value = get_app_setting('gemini_quota_blocks', '{}')
    try:
        blocks = json.loads(raw_value or '{}')
    except json.JSONDecodeError:
        blocks = {}

    now = datetime.now()
    active_blocks = {}
    changed = False
    for model_name, block_info in blocks.items():
        if isinstance(block_info, str):
            blocked_until = block_info
        else:
            blocked_until = (block_info or {}).get('blocked_until')

        try:
            blocked_time = datetime.strptime(blocked_until, "%Y-%m-%d %H:%M:%S")
        except (TypeError, ValueError):
            changed = True
            continue

        if blocked_time > now:
            active_blocks[model_name] = {
                'blocked_until': blocked_until,
                'reason': (block_info or {}).get('reason') if isinstance(block_info, dict) else 'quota'
            }
        else:
            changed = True

    if changed:
        set_app_setting('gemini_quota_blocks', json.dumps(active_blocks, ensure_ascii=False))
    return active_blocks

def block_gemini_model_for_quota(model_name, error):
    blocked_until = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    blocks = get_gemini_quota_blocks()
    blocks[model_name] = {
        'blocked_until': blocked_until,
        'reason': str(error)[:240]
    }
    set_app_setting('gemini_quota_blocks', json.dumps(blocks, ensure_ascii=False))
    print(f"⏭️ Gemini 模型 {model_name} 已標記額度滿，{blocked_until} 前會直接跳過。")

def get_available_gemini_models():
    blocks = get_gemini_quota_blocks()
    available_models = [model_name for model_name in GEMINI_MODELS if model_name not in blocks]
    if not available_models and blocks:
        print("⚠️ Gemini 所有模型今天都被標記滿額，改用原清單最後嘗試一次。")
        return GEMINI_MODELS
    if blocks:
        skipped = ', '.join(blocks.keys())
        print(f"⏭️ 已跳過今日滿額 Gemini 模型：{skipped}")
    return available_models

def clean_ai_html_output(text):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:html)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()

def generate_gemini_content(prompt, feature="general", timeout_seconds=None):
    if not GOOGLE_API_KEY:
        raise RuntimeError("Gemini API Key 未設定")

    last_error = None
    attempted_models = []
    for model_name in get_available_gemini_models():
        attempted_models.append(model_name)
        try:
            model = genai.GenerativeModel(model_name)
            request_options = {"timeout": timeout_seconds} if timeout_seconds else None
            response = model.generate_content(prompt, request_options=request_options)
            log_ai_usage("gemini", model_name, feature, "success")
            return response
        except Exception as e:
            last_error = e
            log_ai_usage("gemini", model_name, feature, "failed", e)
            print(f"❌ Gemini 模型 {model_name} 呼叫失敗: {e}")
            if is_quota_error(e):
                block_gemini_model_for_quota(model_name, e)
            if not should_try_next_gemini_model(e):
                break

    if last_error and is_quota_error(last_error):
        raise GeminiQuotaExceeded(str(last_error))

    if not attempted_models:
        raise GeminiQuotaExceeded("今日 Gemini 模型皆已標記滿額")

    raise last_error or RuntimeError("Gemini 暫時無法回應")

def generate_local_review_summary(hospital_name, review_rows):
    # 本地端懶人包功能：不呼叫 Gemini，依評論情緒統計與負評分類產生就醫者摘要。
    total = len(review_rows)
    positive_reviews = [row for row in review_rows if row.get('sentiment') == 'POSITIVE']
    negative_reviews = [row for row in review_rows if row.get('sentiment') == 'NEGATIVE']
    neutral_reviews = total - len(positive_reviews) - len(negative_reviews)
    negative_issue_rows = get_negative_issue_rows([
        {'text': row.get('content', ''), 'label': row.get('sentiment', 'NEUTRAL')}
        for row in negative_reviews
    ], limit=3)

    positive_rate = round(len(positive_reviews) / total * 100) if total else 0
    negative_rate = round(len(negative_reviews) / total * 100) if total else 0

    if negative_issue_rows:
        issue_html = ''.join(
            f"<li><strong>{html.escape(item['issue_category'])}</strong>：{item['count']} 則</li>"
            for item in negative_issue_rows
        )
        top_issue = negative_issue_rows[0]['issue_category']
    else:
        issue_html = "<li>目前沒有明顯集中的負評原因。</li>"
        top_issue = None

    examples = negative_reviews[:2]
    example_html = ''.join(
        f"<div class='border-start border-3 border-danger ps-3 mb-2 small text-muted'>{html.escape(row.get('content', '')[:120])}</div>"
        for row in examples
    ) or "<div class='small text-muted'>目前沒有可列出的負評範例。</div>"

    if total < 5:
        patient_advice = "目前評論數較少，建議把這份懶人包當作初步參考，實際就醫仍可搭配交通距離、科別需求與親友經驗一起判斷。"
    elif positive_rate >= 70 and negative_rate <= 20:
        patient_advice = "整體評價偏正向，可作為優先考慮名單之一；就醫前仍建議確認門診時間、醫師專長與掛號方式。"
    elif negative_rate >= 40:
        patient_advice = "負評比例偏高，建議就醫前多看幾則近期評論，特別留意是否與你的需求相關；若是急症或特殊病況，仍應以醫療需求和專業判斷為優先。"
    elif top_issue:
        patient_advice = f"整體評價有正有負，就醫前可特別留意「{top_issue}」相關評論，判斷這些問題是否會影響你的就診體驗。"
    else:
        patient_advice = "整體評論沒有明顯集中問題，建議依科別需求、交通便利性、門診時間與個人病況綜合選擇。"

    return f"""
    <h5 class="text-success fw-bold"><i class="fas fa-thumbs-up me-2"></i>值得讚賞</h5>
    <p>{html.escape(hospital_name)} 目前收錄 {total} 則評論，正面評論 {len(positive_reviews)} 則，正評比例約 {positive_rate}%。</p>
    <h5 class="text-danger fw-bold"><i class="fas fa-circle-info me-2"></i>就醫前可留意</h5>
    <p>負面評論 {len(negative_reviews)} 則，負評比例約 {negative_rate}%；中性或未分類評論 {neutral_reviews} 則。若以下原因與你的就醫需求相關，建議多看近期評論再決定。</p>
    <ul>{issue_html}</ul>
    <h6 class="fw-bold mt-3">可參考的負評內容</h6>
    {example_html}
    <hr>
    <div class="alert alert-info border-0">
        <strong>💡 總結建議：</strong>{html.escape(patient_advice)}
    </div>
    """

def generate_local_pk_summary(h1_name, h2_name, stats1, stats2, target_dept=None):
    # 本地端 PK 比較功能：不呼叫 Gemini，依兩家醫院分數與正負評數套用比較模板。
    h1_score = float(stats1.get('avg_score') or 0)
    h2_score = float(stats2.get('avg_score') or 0)
    score_gap = round(abs(h1_score - h2_score), 1)
    dept_text = target_dept or '綜合門診'

    if score_gap < 0.5:
        comparison = "兩家醫療機構的整體滿意度接近，建議再比較交通距離、門診時間、醫師專長與實際病況需求。"
        recommendation = "若不是急症，可優先選擇交通較方便、掛號時間較合適，或較符合指定科別需求的醫院。"
    elif h1_score > h2_score:
        comparison = f"{html.escape(h1_name)} 的整體滿意度目前略高於 {html.escape(h2_name)}，可作為優先參考。"
        recommendation = f"若你重視評論滿意度，可先考慮 {html.escape(h1_name)}；若病況急迫，仍應以就近就醫與科別可近性為優先。"
    else:
        comparison = f"{html.escape(h2_name)} 的整體滿意度目前略高於 {html.escape(h1_name)}，可作為優先參考。"
        recommendation = f"若你重視評論滿意度，可先考慮 {html.escape(h2_name)}；若病況急迫，仍應以就近就醫與科別可近性為優先。"

    return f"""
    <div class="card border-0 shadow-sm mb-4" style="border-left: 5px solid #6c757d; border-radius: 12px; background: white;">
        <div class="card-body p-4">
            <h5 class="fw-bold text-info mb-3"><i class="fas fa-chart-line me-2"></i>醫療機構比較分析</h5>
            <p class="fs-6 text-dark mb-3" style="line-height: 1.8;">
                查詢科別為「{html.escape(dept_text)}」。{html.escape(h1_name)} 滿意度 {h1_score} 分，正面 {stats1.get('pos', 0)} 則、負面 {stats1.get('neg', 0)} 則；
                {html.escape(h2_name)} 滿意度 {h2_score} 分，正面 {stats2.get('pos', 0)} 則、負面 {stats2.get('neg', 0)} 則。
                {comparison}
            </p>
            <div class="p-3 rounded-3" style="background-color: #f8f9fa; border: 1px solid #e9ecef;">
                <strong class="text-secondary"><i class="fas fa-user-md me-2"></i>綜合評估建議：</strong>
                <span class="text-dark fw-bold">{recommendation}</span>
            </div>
        </div>
    </div>
    """

def generate_pk_ai_summary(h1_name, h2_name, stats1, stats2, target_dept=None):
    if get_ai_summary_mode() == 'local':
        summary = generate_local_pk_summary(h1_name, h2_name, stats1, stats2, target_dept)
        log_ai_usage("local", "local_statistics", "pk_analysis", "success")
        return summary

    try:
        print(f"🤖 正在同步生成 {h1_name} vs {h2_name} 的專業分析報告...")
        h1_score = stats1['avg_score']
        h2_score = stats2['avg_score']

        prompt = f"""
        你現在是一位專業、客觀且具備同理心的「醫療數據分析顧問」。
        有民眾正在猶豫要選擇哪家醫療機構就診，請根據以下真實的滿意度數據，提供一段約 100~150 字的專業分析與就醫建議。

        【機構 A】{h1_name}：綜合滿意度 {h1_score} 分 (滿分10分)，正面 {stats1['pos']} 則，負面 {stats1['neg']} 則。
        【機構 B】{h2_name}：綜合滿意度 {h2_score} 分 (滿分10分)，正面 {stats2['pos']} 則，負面 {stats2['neg']} 則。
        查詢科別：{target_dept if target_dept else '綜合門診'}

        寫作要求：
        1. 語氣必須嚴謹、專業，但確保一般大眾能輕鬆讀懂。
        2. 絕對不可使用「完勝」、「鄉民」、「賽評」等過於輕浮的網路用語。
        3. 請基於數據客觀陳述兩者的滿意度差異，並給出中肯的評估建議。

        請直接輸出 HTML 格式（絕對不要使用 ```html 這種 Markdown 語法標記，也不要有開場白）。
        排版規格如下：
        <div class="card border-0 shadow-sm mb-4" style="border-left: 5px solid #17a2b8; border-radius: 12px; background: white;">
            <div class="card-body p-4">
                <h5 class="fw-bold text-info mb-3"><i class="fas fa-chart-line me-2"></i>AI 醫療決策輔助分析</h5>
                <p class="fs-6 text-dark mb-3" style="line-height: 1.8;">
                    [請在此填寫客觀的綜合分析。例如：根據近期的滿意度數據顯示，這兩家醫療機構在整體評價上呈現...]
                </p>
                <div class="p-3 rounded-3" style="background-color: #f8f9fa; border: 1px solid #e9ecef;">
                    <strong class="text-secondary"><i class="fas fa-user-md me-2"></i>綜合評估建議：</strong>
                    <span class="text-dark fw-bold">[給出具體且專業的就醫建議。例如：若您考量整體的就診體驗，建議可優先考慮 A 醫院；若重視特定醫療資源，B 醫院亦是可靠的選擇。]</span>
                </div>
            </div>
        </div>
        """

        response = generate_gemini_content(prompt, feature='pk_analysis')
        print("✅ AI 專業分析生成成功！")
        return response.text.strip()
    except GeminiQuotaExceeded as e:
        print(f"⚠️ PK 分析 Gemini 額度已滿，改用本地端: {e}")
        notify_admin_ai_quota('pk_analysis', e)
        summary = generate_local_pk_summary(h1_name, h2_name, stats1, stats2, target_dept)
        log_ai_usage("local", "local_statistics", "pk_analysis", "success", "Gemini quota exceeded")
        return summary
    except Exception as e:
        print(f"❌ AI 分析生成失敗: {e}")
        summary = generate_local_pk_summary(h1_name, h2_name, stats1, stats2, target_dept)
        log_ai_usage("local", "local_statistics", "pk_analysis", "success", e)
        return summary

def extract_local_symptoms(user_input):
    # 本地端症狀萃取功能：不呼叫 Gemini，將常見口語症狀轉成 803 指南可比對的標準詞。
    text = str(user_input or '').strip()
    normalized = re.sub(r"\s+", "", text)
    alias_map = {
        '腹瀉': '腹瀉',
        '肚子痛': '腹痛',
        '肚子疼': '腹痛',
        '腹痛': '腹痛',
        '胃痛': '胃痛',
        '拉肚子': '腹瀉',
        '喘': '呼吸困難',
        '呼吸困難': '呼吸困難',
        '胸口痛': '胸痛',
        '心口痛': '胸痛',
        '頭很痛': '頭痛',
        '頭有點痛': '頭痛',
        '頭痛': '頭痛',
        '偏頭痛': '頭痛',
        '頭暈': '頭暈',
        '發燒': '發燒',
        '喉嚨痛': '喉嚨痛',
        '喉嚨疼': '喉嚨痛',
        '胸痛': '胸痛',
        '想吐': '噁心',
        '噁心': '噁心',
        '嘔吐': '嘔吐',
        '吐': '嘔吐',
        '咳嗽': '咳嗽',
        '手痛': '手痛',
        '腳痛': '腳痛'
    }

    found = []
    for raw, standard in alias_map.items():
        if raw in normalized and standard not in found:
            found.append(standard)

    for symptoms in OFFICIAL_SYMPTOM_GUIDE.values():
        for token in re.split(r"[、，,及和與/／\s]+", symptoms):
            token = token.strip()
            if len(token) >= 2 and token in normalized and token not in found:
                found.append(token)

    if not found and normalized:
        found.append(normalized[:12])
    return found[:8]

def clean_symptom_text(symptom):
    text = re.sub(r"[，,。.!！?？；;：:\s]+", "", str(symptom or ""))
    return text[:20]

def save_symptom_logs(symptom_list, source_label="症狀"):
    cleaned_symptoms = []
    for symptom in symptom_list or []:
        cleaned = clean_symptom_text(symptom)
        if cleaned and cleaned not in cleaned_symptoms:
            cleaned_symptoms.append(cleaned)

    if not cleaned_symptoms:
        return []

    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        now_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for symptom in cleaned_symptoms:
            cursor.execute("""
                INSERT INTO symptom_logs (symptom_text, created_at)
                VALUES (?, ?)
            """, (symptom, now_time))
        conn.commit()

    print(f"📥 {source_label}紀錄已寫入：{cleaned_symptoms}")
    return cleaned_symptoms

def infer_common_symptom_departments(user_input, symptom_list):
    # 本地端常見症狀輔助規則：補足 803 指南未明確列出的常見口語症狀，並在結果中標示為輔助規則推估。
    text = str(user_input or '')
    joined_symptoms = "、".join(symptom_list)
    combined = f"{text} {joined_symptoms}"
    inferred = {}

    def add(department, score, reason):
        item = inferred.setdefault(department, {'score': 0, 'matched': []})
        item['score'] += score
        if reason and reason not in item['matched']:
            item['matched'].append(reason)

    if any(word in combined for word in ['慢性疼痛', '長期疼痛', '癌症疼痛', '疼痛控制', '疼痛門診', '不明原因疼痛']):
        add('麻醉科', 8, '慢性或長期疼痛')

    if any(word in combined for word in ['頭痛', '偏頭痛']):
        if any(word in combined for word in ['突然', '劇烈', '頭部外傷', '撞到頭', '半身無力', '意識不清', '抽搐', '嘔吐']):
            add('神經外科', 8, '劇烈頭痛或伴隨神經警訊')
        elif any(word in combined for word in ['發燒', '咳嗽', '喉嚨痛', '流鼻水', '鼻塞', '感冒']):
            add('家庭醫學科', 6, '頭痛合併感冒或發燒症狀')
            add('耳鼻喉科', 4, '上呼吸道症狀')
        else:
            add('家庭醫學科', 5, '一般頭痛初步評估')

    if any(word in combined for word in ['喉嚨痛', '喉痛', '鼻塞', '流鼻水', '耳鳴', '耳朵痛', '聲音沙啞']):
        add('耳鼻喉科', 6, '耳鼻喉或上呼吸道症狀')
    if any(word in combined for word in ['發燒', '感冒', '全身痠痛']):
        add('家庭醫學科', 5, '一般內科或感冒症狀')
    if any(word in combined for word in ['咳嗽', '咳血', '呼吸困難', '喘', '氣喘']):
        add('胸腔內科', 7, '呼吸道或胸腔症狀')
    if any(word in combined for word in ['胸痛', '胸悶', '心悸', '心絞痛', '冒冷汗']):
        add('心臟內科', 8, '胸痛胸悶或心臟相關症狀')

    if any(word in combined for word in ['腹痛', '肚子痛', '胃痛', '腹瀉', '拉肚子', '嘔吐', '噁心', '消化不良']):
        add('腸胃內科', 7, '腸胃不適症狀')
    if any(word in combined for word in ['頻尿', '血尿', '尿痛', '小便灼熱', '腰痛', '腰部酸痛', '水腫']):
        add('腎臟內科', 5, '泌尿或腎臟相關症狀')
        add('泌尿外科', 5, '泌尿道症狀')
    if any(word in combined for word in ['牙痛', '牙疼', '牙齦出血', '蛀牙', '口臭']):
        add('一般牙科', 7, '牙齒或牙齦症狀')
    if any(word in combined for word in ['眼睛痛', '眼紅', '視力模糊', '乾眼', '眼皮腫', '白內障']):
        add('眼科', 7, '眼部症狀')
    if any(word in combined for word in ['皮膚癢', '皮膚癢癢', '紅疹', '濕疹', '蕁麻疹', '過敏', '痘痘', '皮膚痛']):
        add('皮膚科', 7, '皮膚或過敏症狀')
    if any(word in combined for word in ['骨折', '扭傷', '拉傷', '關節痛', '腰酸背痛', '膝蓋痛', '肩膀痛']):
        add('骨科', 7, '骨骼關節或肌肉傷害')
    if any(word in combined for word in ['中風', '復健', '語言治療', '活動障礙']):
        add('復健科', 6, '復健需求')
    if any(word in combined for word in ['懷孕', '月經', '陰道出血', '白帶', '下腹痛', '產檢']):
        add('婦產科', 7, '婦產科相關症狀')
    if any(word in combined for word in ['小孩', '兒童', '寶寶', '嬰兒']) or re.search(r"\d+\s*歲", combined):
        add('小兒科', 5, '兒童身體不適')
    if any(word in combined for word in ['貧血', '紫斑', '異常出血', '血小板']):
        add('血液腫瘤科', 6, '血液相關症狀')

    return inferred

def rank_local_departments(user_input):
    # 本地端症狀科別推薦功能：交叉比對 803 官方指南與常見症狀推測，並保留結果來源。
    text = str(user_input or '')
    symptom_list = extract_local_symptoms(text)
    guide_scores = {}
    for dept, guide in OFFICIAL_SYMPTOM_GUIDE.items():
        score = 0
        matched = []
        for symptom in symptom_list:
            if symptom and symptom in guide:
                score += 2
                matched.append(symptom)
        for token in re.split(r"[、，,及和與/／\s]+", guide):
            token = token.strip()
            if len(token) >= 2 and token in text and token not in matched:
                score += 1
                matched.append(token)
        if score > 0:
            guide_scores[dept] = {'score': score, 'matched': matched[:5]}

    inferred_scores = infer_common_symptom_departments(text, symptom_list)
    departments = sorted(set(guide_scores.keys()) | set(inferred_scores.keys()))
    scores = []
    for dept in departments:
        guide = guide_scores.get(dept, {'score': 0, 'matched': []})
        inferred = inferred_scores.get(dept, {'score': 0, 'matched': []})
        if guide['score'] and inferred['score']:
            source = '803 指南與常見症狀輔助規則交叉參照'
        elif guide['score']:
            source = '803 官方症狀分流指南'
        else:
            source = '常見症狀輔助規則推估'

        scores.append({
            'department': dept,
            'score': guide['score'] + inferred['score'],
            'guide_score': guide['score'],
            'inferred_score': inferred['score'],
            'matched': list(dict.fromkeys(guide['matched'] + inferred['matched']))[:6],
            'guide_matched': guide['matched'],
            'inferred_matched': inferred['matched'],
            'source': source
        })

    scores.sort(key=lambda item: item['score'], reverse=True)
    return scores[:3], symptom_list

def get_related_symptom_hint(department, symptom_list):
    guide = OFFICIAL_SYMPTOM_GUIDE.get(department, '')
    symptoms = []
    for token in re.split(r"[、，,及和與/／\s]+", guide):
        token = token.strip()
        if len(token) >= 2 and token not in symptom_list and token not in symptoms:
            symptoms.append(token)
        if len(symptoms) >= 4:
            break
    return '、'.join(symptoms) if symptoms else '症狀是否持續、變嚴重，或影響日常活動'

def generate_local_symptom_result(user_input):
    # 本地端症狀評估功能：不呼叫 Gemini，用白話摘要回答民眾最需要知道的問題。
    ranked_departments, symptom_list = rank_local_departments(user_input)
    top_dept = ranked_departments[0]['department'] if ranked_departments else '家庭醫學科'
    top_source = ranked_departments[0]['source'] if ranked_departments else '常見症狀輔助規則推估'
    matched_text = '、'.join(ranked_departments[0]['matched']) if ranked_departments and ranked_departments[0]['matched'] else '依輸入症狀進行初步分流'
    urgent_keywords = ['胸痛', '呼吸困難', '喘', '昏倒', '意識不清', '大量出血', '劇烈頭痛', '半身無力', '抽搐', '冒冷汗', '持續嘔吐']
    is_urgent = any(keyword in str(user_input) for keyword in urgent_keywords)
    urgency_badge = '偏嚴重，建議盡快就醫' if is_urgent else '目前看起來可先門診評估'
    urgency_class = 'danger' if is_urgent else 'success'
    urgency_text = '有出現需要提高警覺的描述。若正在胸痛、喘不過氣、意識不清、半身無力、劇烈疼痛或持續惡化，請直接去急診。' if is_urgent else '目前沒有明顯急診警訊。可先掛門診；如果症狀變嚴重、持續不退，或出現喘、胸痛、意識不清等狀況，就不要等門診。'
    symptom_badges = ''.join(f"<span class='badge text-bg-light border me-1 mb-1'>{html.escape(sym)}</span>" for sym in symptom_list) or "<span class='text-muted'>未擷取到明確症狀</span>"
    related_symptoms = get_related_symptom_hint(top_dept, symptom_list)
    other_depts = ''.join(
        f"""
        <div class="small border rounded-3 p-2 mb-2 bg-white">
            <strong>{html.escape(item['department'])}</strong>
            <span class="text-muted ms-2">也可參考：{html.escape('、'.join(item['matched']) or '相關症狀')}</span>
        </div>
        """
        for item in ranked_departments[1:]
    ) or ""

    return f"""
    <div class="card border-0 shadow-sm mb-3 triage-simple-card">
        <div class="card-body p-4">
            <div class="mb-3">
                <div class="text-muted fw-bold mb-1">你可能要掛</div>
                <div class="display-6 fw-bold text-primary">{html.escape(top_dept)}</div>
                <div class="text-muted mt-2">如果不確定，也可以先掛家庭醫學科或一般內科做初步評估。</div>
            </div>

            <div class="row g-3 mb-3">
                <div class="col-md-6">
                    <div class="border rounded-3 p-3 h-100">
                        <div class="fw-bold mb-1"><i class="fas fa-triangle-exclamation me-2 text-{urgency_class}"></i>嚴不嚴重？</div>
                        <div class="h5 fw-bold text-{urgency_class} mb-2">{html.escape(urgency_badge)}</div>
                        <div class="text-muted small">{html.escape(urgency_text)}</div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="border rounded-3 p-3 h-100">
                        <div class="fw-bold mb-1"><i class="fas fa-hospital me-2 text-primary"></i>要不要馬上去醫院？</div>
                        <div class="text-muted small">{'建議現在就去急診或請家人陪同就醫。' if is_urgent else '可以先掛門診；但若症狀快速變差，就改去急診。'}</div>
                    </div>
                </div>
            </div>

            <div class="border rounded-3 p-3 mb-3 bg-light">
                <div class="fw-bold mb-2"><i class="fas fa-magnifying-glass me-2 text-primary"></i>還要注意哪些症狀？</div>
                <div class="text-dark">{html.escape(related_symptoms)}</div>
                <div class="small text-muted mt-2">如果這些症狀一起出現或越來越明顯，請提高就醫急迫性。</div>
            </div>

            <div class="border rounded-3 p-3 mb-3">
                <div class="fw-bold mb-2"><i class="fas fa-clipboard-check me-2 text-primary"></i>判斷依據</div>
                <div class="mb-2">{symptom_badges}</div>
                <div class="small text-muted">
                    依據：{html.escape(top_source)}；系統從描述中命中「{html.escape(matched_text)}」，所以先建議 {html.escape(top_dept)}。
                </div>
            </div>

            {f'<div class="mb-3"><div class="fw-bold mb-2">其他可能科別</div>{other_depts}</div>' if other_depts else ''}

            <p class="text-muted small mb-0">提醒：這是掛號前參考，不能取代醫師診斷。若你覺得「和平常不一樣」或症狀變很快，請直接就醫。</p>
        </div>
    </div>
    """

def generate_local_symptom_trend_announcement(top_symptoms):
    # 本地端症狀趨勢公告功能：不呼叫 Gemini，依 Top 症狀群組套用公衛公告模板。
    public_symptoms = filter_public_health_symptoms(top_symptoms)
    if not public_symptoms:
        return "目前症狀趨勢多屬個人事件或外傷查詢，暫不建議發布社區健康公告。"

    symptom_counts = {str(row[0]): row[1] for row in public_symptoms}
    symptom_text = "、".join(symptom_counts.keys())
    respiratory = ['咳嗽', '發燒', '喉嚨痛', '流鼻水', '鼻塞', '胸悶', '呼吸困難']
    digestive = ['腹痛', '腹瀉', '嘔吐', '噁心', '胃痛', '肚子痛']
    cardio = ['胸痛', '心悸', '胸悶', '頭暈', '冒冷汗']

    def has_any(keywords):
        return any(keyword in symptom_text for keyword in keywords)

    if has_any(respiratory):
        message = "近期呼吸道相關查詢增加，請留意口罩、手部衛生與室內通風。"
    elif has_any(digestive):
        message = "近期腸胃不適查詢增加，請注意飲食衛生、補充水分並觀察症狀變化。"
    elif has_any(cardio):
        message = "近期胸悶胸痛相關查詢增加，如伴隨冒冷汗、呼吸困難或昏厥請立即就醫。"
    else:
        message = "近期健康症狀查詢增加，若症狀持續或加劇，建議及早安排就醫評估。"
    return message

PERSONAL_EVENT_SYMPTOM_KEYWORDS = [
    '骨折', '斷掉', '腳斷', '手斷', '腿斷', '扭傷', '拉傷', '撞傷', '跌倒', '摔倒',
    '車禍', '割傷', '擦傷', '刺傷', '刀傷', '燙傷', '燒傷', '外傷', '瘀青',
    '脫臼', '挫傷', '被打', '咬傷', '夾傷'
]

def is_public_health_symptom(symptom_text):
    text = str(symptom_text or '').strip()
    if not text:
        return False
    return not any(keyword in text for keyword in PERSONAL_EVENT_SYMPTOM_KEYWORDS)

def filter_public_health_symptoms(top_symptoms):
    return [row for row in top_symptoms if is_public_health_symptom(row[0])]

def get_gemini_usage_summary():
    daily_limit = get_gemini_daily_limit()
    today_used = 0
    month_used = 0
    last_success = None
    last_failure = None
    model_rows = []

    try:
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*)
                FROM ai_usage_logs
                WHERE provider = 'gemini'
                  AND status = 'success'
                  AND date(created_at) = date('now', 'localtime')
            """)
            today_used = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*)
                FROM ai_usage_logs
                WHERE provider = 'gemini'
                  AND status = 'success'
                  AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime')
            """)
            month_used = c.fetchone()[0]

            c.execute("""
                SELECT model, COUNT(*) AS count
                FROM ai_usage_logs
                WHERE provider = 'gemini'
                  AND status = 'success'
                  AND date(created_at) = date('now', 'localtime')
                GROUP BY model
                ORDER BY count DESC
            """)
            model_rows = [{'model': row['model'], 'count': row['count']} for row in c.fetchall()]

            c.execute("""
                SELECT model, feature, created_at
                FROM ai_usage_logs
                WHERE provider = 'gemini' AND status = 'success'
                ORDER BY id DESC
                LIMIT 1
            """)
            row = c.fetchone()
            if row:
                last_success = dict(row)

            c.execute("""
                SELECT model, feature, error_message, created_at
                FROM ai_usage_logs
                WHERE provider = 'gemini' AND status = 'failed'
                ORDER BY id DESC
                LIMIT 1
            """)
            row = c.fetchone()
            if row:
                last_failure = dict(row)
    except Exception as e:
        print(f"⚠️ Gemini 用量統計讀取失敗: {e}")

    return {
        'configured': bool(GOOGLE_API_KEY),
        'models': GEMINI_MODELS,
        'blocked_models': get_gemini_quota_blocks(),
        'active_model': GEMINI_MODELS[0] if GEMINI_MODELS else None,
        'fallback_enabled': len(GEMINI_MODELS) > 1,
        'today_used': today_used,
        'month_used': month_used,
        'daily_limit': daily_limit,
        'estimated_remaining_today': max(daily_limit - today_used, 0) if daily_limit is not None else None,
        'model_usage_today': model_rows,
        'last_success': last_success,
        'last_failure': last_failure
    }

def get_local_ai_usage_summary():
    today_used = 0
    month_used = 0
    feature_rows = []
    last_success = None

    try:
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*)
                FROM ai_usage_logs
                WHERE provider = 'local'
                  AND status = 'success'
                  AND date(created_at) = date('now', 'localtime')
            """)
            today_used = c.fetchone()[0]

            c.execute("""
                SELECT COUNT(*)
                FROM ai_usage_logs
                WHERE provider = 'local'
                  AND status = 'success'
                  AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now', 'localtime')
            """)
            month_used = c.fetchone()[0]

            c.execute("""
                SELECT feature, COUNT(*) AS count
                FROM ai_usage_logs
                WHERE provider = 'local'
                  AND status = 'success'
                  AND date(created_at) = date('now', 'localtime')
                GROUP BY feature
                ORDER BY count DESC
            """)
            feature_rows = [{'feature': row['feature'], 'count': row['count']} for row in c.fetchall()]

            c.execute("""
                SELECT model, feature, created_at
                FROM ai_usage_logs
                WHERE provider = 'local' AND status = 'success'
                ORDER BY id DESC
                LIMIT 1
            """)
            row = c.fetchone()
            if row:
                last_success = dict(row)
    except Exception as e:
        print(f"⚠️ 本地端 AI 用量統計讀取失敗: {e}")

    return {
        'today_used': today_used,
        'month_used': month_used,
        'feature_usage_today': feature_rows,
        'last_success': last_success
    }

def get_backup_history(limit=8):
    try:
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, file_name, file_size_mb, file_size_bytes, created_at, actor_username
                FROM backup_history
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"⚠️ 備份紀錄讀取失敗: {e}")
        return []

def log_backup_history(file_name, file_size_bytes):
    file_size_mb = round((file_size_bytes or 0) / 1024 / 1024, 2)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    actor_id = getattr(current_user, 'id', None)
    actor_username = getattr(current_user, 'username', None)
    try:
        with sqlite3.connect(HR_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO backup_history
                    (file_name, file_size_mb, file_size_bytes, created_at, created_by, actor_username)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (file_name, file_size_mb, file_size_bytes or 0, created_at, actor_id, actor_username))
            conn.commit()
    except Exception as e:
        print(f"⚠️ 備份紀錄寫入失敗: {e}")

# ==========================================
# 🤖 前台評論懶人包：Gemini 優先，本地統計備援
# ==========================================
@app.route('/api/generate_summary', methods=['POST'])
@login_required
@limiter.limit("3 per minute")
def generate_summary():
    data = request.get_json()
    hospital_name = data.get('hospital_name')

    if not hospital_name:
        return jsonify({'error': '未提供醫院名稱'}), 400
    
    # ✅ 加入這行超級防呆：讓 AI 去資料庫找資料前，也強制把「臺」轉成「台」！
    hospital_name = hospital_name.replace("臺", "台").strip()

    print(f"🤖 收到 AI 請求，正在分析：{hospital_name}...") 

    try:
        review_rows = []
        with sqlite3.connect(HR_DB) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM hospitals WHERE name = ?", (hospital_name,))
            row = cursor.fetchone()
            
            if not row:
                return jsonify({'summary': '找不到該醫院資料，請先執行爬蟲分析。'})
            
            hospital_id = row[0]
            cursor.execute("""
                SELECT content, analyzed_sentiment
                FROM reviews
                WHERE hospital_id = ?
                ORDER BY review_time DESC
                LIMIT 24
            """, (hospital_id,))
            rows = cursor.fetchall()
            review_rows = [
                {'content': r[0], 'sentiment': r[1] or 'NEUTRAL'}
                for r in rows
                if r[0] and len(r[0]) > 2
            ]

        if not review_rows:
            return jsonify({'summary': '評論數量不足，無法生成報告。'})

        summary_mode = get_ai_summary_mode()
        if summary_mode == 'local':
            log_ai_usage("local", "local_statistics", "review_summary", "success")
            return jsonify({
                'summary': generate_local_review_summary(hospital_name, review_rows),
                'fallback': True,
                'mode': 'local'
            })

        if not GOOGLE_API_KEY:
            notify_admin_ai_quota('review_summary', 'Gemini API Key 未設定')
            log_ai_usage("local", "local_statistics", "review_summary", "success", "Gemini API Key 未設定")
            return jsonify({
                'summary': generate_local_review_summary(hospital_name, review_rows),
                'fallback': True,
                'mode': 'local',
                'reason': 'gemini_not_configured'
            })

        reviews_combined = "\n".join([
            f"- [{row['sentiment']}] {row['content'][:220]}"
            for row in review_rows[:20]
        ])
        
        prompt = f"""
        你是一位專業的醫療數據分析師。請閱讀以下關於「{hospital_name}」的 Google 評論，
        並用【繁體中文】撰寫一份簡短的分析報告。
        
        請直接輸出 HTML 格式 (不要 Markdown 語法)，排版如下：
        <h5 class="text-success fw-bold"><i class="fas fa-thumbs-up me-2"></i>值得讚賞</h5>
        <p>...請總結優點...</p>
        <h5 class="text-danger fw-bold"><i class="fas fa-thumbs-down me-2"></i>待改進</h5>
        <p>...請總結缺點...</p>
        <hr>
        <div class="alert alert-info border-0">
            <strong>💡 總結建議：</strong>...請給出一句總結...
        </div>

        以下是評論數據：
        {reviews_combined}
        ⚠️【重要格式限制】：請直接輸出純 HTML 程式碼。絕對不要使用 ```html 這種 Markdown 語法標籤包裝，也不要有任何額外的開場白或結語。
        """

        response = generate_gemini_content(prompt, feature='review_summary', timeout_seconds=15)
        
        print("✅ AI 回應成功！") 
        return jsonify({'summary': clean_ai_html_output(response.text)})

    except GeminiQuotaExceeded as e:
        print(f"⚠️ Gemini 額度已滿，改用本機統計版懶人包: {e}")
        notify_admin_ai_quota('review_summary', e)
        log_ai_usage("local", "local_statistics", "review_summary", "success", "Gemini quota exceeded")
        return jsonify({
            'summary': generate_local_review_summary(hospital_name, review_rows),
            'fallback': True,
            'mode': 'local',
            'reason': 'gemini_quota_exceeded'
        })

    except Exception as e:
        print(f"❌ AI 生成失敗，改用本機統計版懶人包: {e}")
        log_ai_usage("local", "local_statistics", "review_summary", "success", e)
        return jsonify({
            'summary': generate_local_review_summary(hospital_name, review_rows),
            'fallback': True,
            'mode': 'local',
            'reason': 'gemini_timeout_or_error'
        })

@app.route('/google')
@login_required
def google_page():
    return render_template('google.html', all_hospitals=FLAT_HOSPITAL_LIST)

@app.route('/api/nearby_hospitals')
@login_required
def nearby_hospitals():
    lat = request.args.get('lat')
    lng = request.args.get('lng')
    if not lat or not lng:
        return jsonify({'status': 'error', 'message': '缺少 lat 或 lng 參數。'}), 400

    try:
        user_lat = float(lat)
        user_lng = float(lng)
    except (TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'lat 和 lng 必須是有效數值。'}), 400

    try:
        sync_hospital_locations_from_excel()
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, address, latitude, longitude
                FROM hospitals
                WHERE latitude IS NOT NULL
                  AND longitude IS NOT NULL
                  AND latitude != ''
                  AND longitude != ''
            """)
            rows = cursor.fetchall()

        if not rows:
            return jsonify({
                'status': 'empty',
                'message': '目前沒有可排序的醫院定位資料',
                'hospitals': []
            })

        nearby_items = []
        seen_names = set()
        seen_coordinates = set()
        for row in rows:
            try:
                hospital_lat = float(row['latitude'])
                hospital_lng = float(row['longitude'])
            except (TypeError, ValueError):
                continue
            name_key = normalize_hospital_name(row['name'])
            coordinate_key = (round(hospital_lat, 6), round(hospital_lng, 6))
            if name_key in seen_names or coordinate_key in seen_coordinates:
                continue
            seen_names.add(name_key)
            seen_coordinates.add(coordinate_key)
            display_address, _ = resolve_hospital_address(row['name'], row['address'])
            distance_km = calculate_distance_km(
                user_lat,
                user_lng,
                hospital_lat,
                hospital_lng
            )
            nearby_items.append({
                'id': row['id'],
                'name': row['name'],
                'address': display_address,
                'latitude': hospital_lat,
                'longitude': hospital_lng,
                'distance_km': round(distance_km, 2)
            })

        if not nearby_items:
            return jsonify({
                'status': 'empty',
                'message': '目前沒有可排序的醫院定位資料',
                'hospitals': []
            })

        nearby_items.sort(key=lambda item: item['distance_km'])
        return jsonify({
            'status': 'ok',
            'hospitals': nearby_items[:10]
        })
    except Exception as e:
        print(f"❌ 附近醫院推薦失敗: {e}")
        return jsonify({'status': 'error', 'message': '附近醫院推薦暫時無法使用，請稍後再試。'}), 500

# ==========================================
# 🏥 醫院檔案資料整理：統計、趨勢、獎項與收藏狀態
# ==========================================
def get_hospital_profile_data(hospital_id):
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM hospitals WHERE id = ?", (hospital_id,))
        hospital = cursor.fetchone()
        if not hospital:
            return None

        cursor.execute("""
            SELECT id, content, analyzed_sentiment, review_time, stored_at, department
            FROM reviews
            WHERE hospital_id = ?
            ORDER BY
                CASE
                    WHEN review_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN review_time
                    ELSE stored_at
                END DESC,
                id DESC
        """, (hospital_id,))
        review_rows = cursor.fetchall()

        cursor.execute("""
            SELECT department, award_name
            FROM hospital_awards
            WHERE REPLACE(hospital_name, '臺', '台') = REPLACE(?, '臺', '台')
            ORDER BY department, award_name
        """, (hospital['name'],))
        awards = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT id, department, award_name, status, admin_note, proof_document, created_at, reviewed_at
            FROM hospital_award_applications
            WHERE hospital_id = ?
               OR REPLACE(hospital_name, '臺', '台') = REPLACE(?, '臺', '台')
            ORDER BY id DESC
            LIMIT 8
        """, (hospital_id, hospital['name']))
        award_applications = [dict(row) for row in cursor.fetchall()]

        award_history_map = {}
        if award_applications:
            placeholders = ",".join(["?"] * len(award_applications))
            cursor.execute(f"""
                SELECT
                    h.application_id, h.action, h.note, h.proof_document,
                    h.actor_id, h.created_at, u.username AS actor_username
                FROM hospital_award_application_history h
                LEFT JOIN users u ON h.actor_id = u.id
                WHERE h.application_id IN ({placeholders})
                ORDER BY h.id DESC
            """, [item['id'] for item in award_applications])
            for row in cursor.fetchall():
                award_history_map.setdefault(row['application_id'], []).append(dict(row))
            for item in award_applications:
                item['history'] = award_history_map.get(item['id'], [])

        notifications = []
        if getattr(current_user, 'role', None) == 'hospital' and current_user.hospital_id == hospital_id:
            cursor.execute("""
                SELECT id, title, content, status, category, link_url, created_at
                FROM hospital_notifications
                WHERE hospital_id = ?
                  AND (user_id IS NULL OR user_id = ?)
                ORDER BY id DESC
                LIMIT 1
            """, (hospital_id, current_user.id))
            notifications = [dict(row) for row in cursor.fetchall()]

            cursor.execute("""
                SELECT COUNT(*)
                FROM hospital_notifications
                WHERE hospital_id = ?
                  AND (user_id IS NULL OR user_id = ?)
                  AND status = 'unread'
            """, (hospital_id, current_user.id))
            unread_notification_count = cursor.fetchone()[0]
        else:
            unread_notification_count = 0

    reviews = []
    sentiment_items = []
    for row in review_rows:
        sentiment = row['analyzed_sentiment'] or 'NEUTRAL'
        issue_category = classify_negative_issue(row['content'] or '', sentiment)
        score = 100.0 if sentiment == 'POSITIVE' else 0.0
        normalized_time = normalize_stored_review_time(row['review_time'], row['stored_at'])
        review_date = None
        try:
            review_date = datetime.strptime(normalized_time, "%Y/%m/%d").strftime("%Y-%m-%d")
        except ValueError:
            review_date = None

        review_item = {
            'id': row['id'],
            'content': row['content'] or '',
            'text': row['content'] or '',
            'sentiment': sentiment,
            'label': sentiment,
            'time': normalized_time,
            'review_date': review_date,
            'stored_at': row['stored_at'],
            'department': row['department'] or '綜合/未提及',
            'score': score,
            'issue_category': issue_category
        }
        reviews.append(review_item)
        sentiment_items.append({
            'text': review_item['text'],
            'label': sentiment,
            'time': review_item['time'],
            'score': score,
            'department': review_item['department'],
            'issue_category': issue_category
        })

    total_count = len(reviews)
    pos_count = sum(1 for item in reviews if item['sentiment'] == 'POSITIVE')
    neg_count = sum(1 for item in reviews if item['sentiment'] == 'NEGATIVE')
    positive_rate = round(pos_count / total_count * 100) if total_count else 0
    negative_rate = round(neg_count / total_count * 100) if total_count else 0
    satisfaction_score = round(positive_rate / 10, 1) if total_count else 0

    issue_rows = get_negative_issue_rows(sentiment_items, limit=8)
    suggestions = generate_improvement_suggestions(issue_rows, neg_count, total_count)
    representative_reviews = get_representative_reviews(reviews, issue_rows)
    keywords = extract_keywords(sentiment_items, top_n=10) if sentiment_items else {'labels': [], 'data': []}
    feature_tags = generate_hospital_feature_tags(reviews, issue_rows, awards, {
        'total': total_count,
        'positive_rate': positive_rate,
        'negative_rate': negative_rate
    })

    department_counter = Counter(item['department'] for item in reviews)
    department_rows = [
        {'department': dept, 'count': count}
        for dept, count in department_counter.most_common(8)
    ]

    trend_by_date = {}
    for item in reviews:
        date_label = item['time'] or '未知時間'
        if date_label not in trend_by_date:
            trend_by_date[date_label] = {'total_score': 0, 'count': 0}

        trend_by_date[date_label]['total_score'] += 10 if item['sentiment'] == 'POSITIVE' else 0
        trend_by_date[date_label]['count'] += 1

    def trend_sort_key(row):
        try:
            return datetime.strptime(row['label'], "%Y/%m/%d")
        except ValueError:
            return datetime.max

    trend = [
        {
            'label': date_label,
            'score': round(data['total_score'] / data['count'], 1) if data['count'] else 0,
            'count': data['count'],
            'sentiment': 'POSITIVE' if data['total_score'] / data['count'] >= 5 else 'NEGATIVE'
        }
        for date_label, data in trend_by_date.items()
    ]
    trend.sort(key=trend_sort_key)

    latest_update = None
    review_dates = []
    for item in reviews:
        if item['stored_at'] and (not latest_update or item['stored_at'] > latest_update):
            latest_update = item['stored_at']
        if item.get('review_date'):
            review_dates.append(item['review_date'])

    period_start = min(review_dates) if review_dates else '--'
    period_end = max(review_dates) if review_dates else '--'

    hospital_data = dict(hospital)
    display_address, address_source = resolve_hospital_address(hospital_data.get('name'), hospital_data.get('address'))
    hospital_data['display_address'] = display_address
    hospital_data['address_source'] = address_source

    return {
        'hospital': hospital_data,
        'stats': {
            'total': total_count,
            'positive': pos_count,
            'negative': neg_count,
            'positive_rate': positive_rate,
            'negative_rate': negative_rate,
            'satisfaction_score': satisfaction_score,
            'latest_update': latest_update or hospital['created_at'] or '--',
            'period_start': period_start,
            'period_end': period_end
        },
        'issues': issue_rows,
        'suggestions': suggestions,
        'representative_reviews': representative_reviews,
        'keywords': keywords,
        'feature_tags': feature_tags,
        'departments': department_rows,
        'trend': trend,
        'reviews': reviews,
        'awards': awards,
        'award_applications': award_applications,
        'notifications': notifications,
        'unread_notification_count': unread_notification_count,
        'award_departments': AWARD_DEPARTMENTS,
        'favorite': get_favorite_info(current_user.id, hospital_id)
    }

@app.route('/hospital/<int:hospital_id>')
@login_required
def hospital_profile(hospital_id):
    if not can_view_hospital_profile(hospital_id):
        flash('您只能查看已授權的醫院詳細檔案', 'analyze_error')
        return redirect(url_for('index'))

    profile = get_hospital_profile_data(hospital_id)
    if not profile:
        flash('找不到該醫院檔案', 'analyze_error')
        return redirect(url_for('google_page'))

    return render_template('hospital_profile.html', profile=profile)

@app.route('/hospital/<int:hospital_id>/report')
@login_required
def hospital_report(hospital_id):
    if not can_view_hospital_profile(hospital_id):
        flash('您只能匯出已授權的醫院報告', 'analyze_error')
        return redirect(url_for('index'))

    profile = get_hospital_profile_data(hospital_id)
    if not profile:
        flash('找不到該醫院檔案', 'analyze_error')
        return redirect(url_for('google_page'))

    return render_template('hospital_report.html', profile=profile)

@app.route('/hospital/<int:hospital_id>/award_application', methods=['POST'])
@login_required
def submit_award_application(hospital_id):
    if not (
        getattr(current_user, 'role', None) == 'hospital'
        and current_user.approval_status == 'approved'
        and current_user.hospital_id == hospital_id
    ):
        flash('只有已審核通過的醫院帳號可以提出獎項或認證申請。', 'analyze_error')
        return redirect(url_for('hospital_profile', hospital_id=hospital_id))

    department = request.form.get('department', '').strip()
    award_name = request.form.get('award_name', '').strip()
    proof_filename = None

    if not department or not award_name:
        flash('請選擇所屬科別並填寫獎項/認證名稱。', 'analyze_error')
        return redirect(url_for('hospital_profile', hospital_id=hospital_id))

    if 'proof_document' in request.files:
        proof_filename, upload_error = save_proof_document(request.files['proof_document'])
        if upload_error:
            flash(upload_error, 'analyze_error')
            return redirect(url_for('hospital_profile', hospital_id=hospital_id))

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM hospitals WHERE id = ?", (hospital_id,))
        hospital = cursor.fetchone()
        if not hospital:
            flash('找不到醫院資料，無法送出申請。', 'analyze_error')
            return redirect(url_for('hospital_dashboard'))

        cursor.execute("""
            SELECT id FROM hospital_award_applications
            WHERE hospital_id = ?
              AND department = ?
              AND award_name = ?
              AND status = 'pending'
            LIMIT 1
        """, (hospital_id, department, award_name))
        if cursor.fetchone():
            flash('這筆獎項/認證已在待審核清單中，請等待管理員審核。', 'analyze_error')
            return redirect(url_for('hospital_profile', hospital_id=hospital_id))

        cursor.execute("""
            INSERT INTO hospital_award_applications
                (hospital_id, hospital_name, user_id, department, award_name, status, proof_document, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """, (
            hospital_id,
            normalize_hospital_name(hospital['name']),
            current_user.id,
            department,
            award_name,
            proof_filename,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        application_id = cursor.lastrowid
        log_award_application_history(
            cursor,
            application_id,
            'submitted',
            '院方送出獎項/認證申請',
            proof_filename,
            current_user.id
        )
        conn.commit()

    flash('獎項/認證申請已送出，待管理員審核後才會公開顯示。', 'analyze_success')
    return redirect(url_for('hospital_profile', hospital_id=hospital_id))

@app.route('/hospital/by-name/<path:hospital_name>')
@login_required
def hospital_profile_by_name(hospital_name):
    normalized_name = hospital_name.replace("臺", "台").strip()
    place_id = normalized_name.lower().replace(" ", "_")

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id
            FROM hospitals
            WHERE google_place_id = ?
               OR REPLACE(name, '臺', '台') = ?
            ORDER BY id DESC
            LIMIT 1
        """, (place_id, normalized_name))
        row = cursor.fetchone()

    if row:
        return redirect(url_for('hospital_profile', hospital_id=row['id']))

    return redirect(url_for('google_page', hospital=normalized_name))

@app.route('/favorites')
@login_required
def favorites_page():
    return render_template('favorites.html', favorites=get_user_favorites(current_user.id))

@app.route('/hospital/<int:hospital_id>/favorite', methods=['POST'])
@login_required
def toggle_hospital_favorite(hospital_id):
    action = request.form.get('action', 'add')
    note = request.form.get('note', '').strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM hospitals WHERE id = ?", (hospital_id,))
        if not cursor.fetchone():
            flash('找不到該醫院，無法加入收藏。', 'analyze_error')
            return redirect(url_for('favorites_page'))

        if action == 'remove':
            cursor.execute("""
                DELETE FROM user_hospital_favorites
                WHERE user_id = ? AND hospital_id = ?
            """, (current_user.id, hospital_id))
            flash('已從收藏清單移除。', 'analyze_success')
        else:
            cursor.execute("""
                INSERT INTO user_hospital_favorites(user_id, hospital_id, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, hospital_id)
                DO UPDATE SET note = excluded.note, updated_at = excluded.updated_at
            """, (current_user.id, hospital_id, note, now, now))
            flash('已儲存到我的收藏。', 'analyze_success')
        conn.commit()

    return redirect(request.referrer or url_for('favorites_page'))

@app.route('/api/hospital/<int:hospital_id>/favorite', methods=['POST'])
@login_required
def api_toggle_hospital_favorite(hospital_id):
    payload = request.get_json(silent=True) or {}
    action = payload.get('action', 'add')
    note = str(payload.get('note') or '').strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM hospitals WHERE id = ?", (hospital_id,))
        hospital = cursor.fetchone()
        if not hospital:
            return jsonify({'status': 'error', 'message': '找不到該醫院，無法加入收藏。'}), 404

        if action == 'remove':
            cursor.execute("""
                DELETE FROM user_hospital_favorites
                WHERE user_id = ? AND hospital_id = ?
            """, (current_user.id, hospital_id))
            is_favorite = False
            message = '已從收藏清單移除。'
        else:
            cursor.execute("""
                INSERT INTO user_hospital_favorites(user_id, hospital_id, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, hospital_id)
                DO UPDATE SET note = excluded.note, updated_at = excluded.updated_at
            """, (current_user.id, hospital_id, note, now, now))
            is_favorite = True
            message = f'已將「{hospital["name"]}」加入收藏。'
        conn.commit()

    return jsonify({
        'status': 'ok',
        'message': message,
        'is_favorite': is_favorite
    })

@app.route('/favorites/<int:hospital_id>/note', methods=['POST'])
@login_required
def update_favorite_note(hospital_id):
    note = request.form.get('note', '').strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE user_hospital_favorites
            SET note = ?, updated_at = ?
            WHERE user_id = ? AND hospital_id = ?
        """, (note, now, current_user.id, hospital_id))
        conn.commit()
    flash('收藏備註已更新。', 'analyze_success')
    return redirect(url_for('favorites_page'))

@app.route('/hospital/dashboard')
@login_required
def hospital_dashboard():
    if getattr(current_user, 'role', None) != 'hospital':
        return redirect(url_for('index'))
    if current_user.approval_status != 'approved' or not current_user.hospital_id:
        flash('醫院帳號尚未通過管理員審核，請等待核准。', 'login_error')
        return redirect(url_for('hospital_application_status'))
    return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

@app.route('/hospital/notifications')
@login_required
def hospital_notifications_page():
    if getattr(current_user, 'role', None) != 'hospital':
        flash('只有院方帳號可以查看通知中心。', 'analyze_error')
        return redirect(url_for('index'))

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        if current_user.hospital_id:
            cursor.execute("""
                SELECT id, title, content, status, category, link_url, created_at
                FROM hospital_notifications
                WHERE (
                    (hospital_id = ? AND (user_id IS NULL OR user_id = ?))
                    OR user_id = ?
                )
                  AND COALESCE(category, 'general') != 'ai_quota'
                ORDER BY
                    CASE status WHEN 'unread' THEN 0 ELSE 1 END,
                    id DESC
            """, (current_user.hospital_id, current_user.id, current_user.id))
        else:
            cursor.execute("""
                SELECT id, title, content, status, category, link_url, created_at
                FROM hospital_notifications
                WHERE user_id = ?
                  AND COALESCE(category, 'general') != 'ai_quota'
                ORDER BY
                    CASE status WHEN 'unread' THEN 0 ELSE 1 END,
                    id DESC
            """, (current_user.id,))
        notifications = [dict(row) for row in cursor.fetchall()]

    return render_template('hospital_notifications.html', notifications=notifications)

@app.route('/hospital/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_hospital_notification_read(notification_id):
    if getattr(current_user, 'role', None) != 'hospital':
        return redirect(url_for('index'))

    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        if current_user.hospital_id:
            cursor.execute("""
                UPDATE hospital_notifications
                SET status = 'read'
                WHERE id = ?
                  AND ((hospital_id = ? AND (user_id IS NULL OR user_id = ?)) OR user_id = ?)
            """, (notification_id, current_user.hospital_id, current_user.id, current_user.id))
        else:
            cursor.execute("""
                UPDATE hospital_notifications
                SET status = 'read'
                WHERE id = ?
                  AND user_id = ?
            """, (notification_id, current_user.id))
        conn.commit()

    return redirect(request.referrer or url_for('hospital_notifications_page'))

@app.route('/hospital/notifications/read_all', methods=['POST'])
@login_required
def mark_all_hospital_notifications_read():
    if getattr(current_user, 'role', None) != 'hospital':
        return redirect(url_for('index'))

    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        if current_user.hospital_id:
            cursor.execute("""
                UPDATE hospital_notifications
                SET status = 'read'
                WHERE ((hospital_id = ? AND (user_id IS NULL OR user_id = ?)) OR user_id = ?)
                  AND status = 'unread'
            """, (current_user.hospital_id, current_user.id, current_user.id))
        else:
            cursor.execute("""
                UPDATE hospital_notifications
                SET status = 'read'
                WHERE user_id = ?
                  AND status = 'unread'
            """, (current_user.id,))
        conn.commit()

    flash('所有通知已標記為已讀。', 'analyze_success')
    return redirect(request.referrer or url_for('hospital_notifications_page'))

@app.route('/hospital/application', methods=['GET', 'POST'])
@login_required
def hospital_application_status():
    if getattr(current_user, 'role', None) != 'hospital':
        return redirect(url_for('index'))

    if request.method == 'POST':
        # 🌟 新增：處理重新送審時的證明文件上傳
        proof_filename = None
        if 'proof_document' in request.files:
            proof_filename, upload_error = save_proof_document(request.files['proof_document'])
            if upload_error:
                flash(upload_error, 'analyze_error')
                return redirect(url_for('hospital_application_status'))

        with sqlite3.connect(HR_DB) as conn:
            c = conn.cursor()
            
            if proof_filename:
                # 🌟 有上傳新檔案：更新 proof_document
                c.execute("""
                    UPDATE users
                    SET approval_status = 'pending',
                        hospital_id = NULL,
                        requested_hospital_name = ?,
                        official_email = ?,
                        contact_name = ?,
                        contact_phone = ?,
                        institution_code = ?,
                        rejection_reason = NULL,
                        proof_document = ?
                    WHERE id = ? AND role = 'hospital'
                """, (
                    request.form.get('requested_hospital_name', '').replace("臺", "台").strip(),
                    request.form.get('official_email', '').strip(),
                    request.form.get('contact_name', '').strip(),
                    request.form.get('contact_phone', '').strip(),
                    request.form.get('institution_code', '').strip(),
                    proof_filename,
                    current_user.id
                ))
            else:
                # 🌟 沒上傳新檔案：只更新其他資料（保留原本已上傳的證明）
                c.execute("""
                    UPDATE users
                    SET approval_status = 'pending',
                        hospital_id = NULL,
                        requested_hospital_name = ?,
                        official_email = ?,
                        contact_name = ?,
                        contact_phone = ?,
                        institution_code = ?,
                        rejection_reason = NULL
                    WHERE id = ? AND role = 'hospital'
                """, (
                    request.form.get('requested_hospital_name', '').replace("臺", "台").strip(),
                    request.form.get('official_email', '').strip(),
                    request.form.get('contact_name', '').strip(),
                    request.form.get('contact_phone', '').strip(),
                    request.form.get('institution_code', '').strip(),
                    current_user.id
                ))
            conn.commit()

        logout_user()
        flash('申請資料已重新送出，請等待管理員審核後再登入。', 'register_success')
        return redirect(url_for('login'))

    # ... 以下保持原樣 ...
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT username, approval_status, requested_hospital_name, official_email,
                   contact_name, contact_phone, institution_code, rejection_reason
            FROM users
            WHERE id = ?
        """, (current_user.id,))
        application = c.fetchone()

    return render_template('hospital_application.html', application=application, all_hospitals=FLAT_HOSPITAL_LIST)

@app.route('/dashboard')
@login_required
def dashboard_page():
    if not current_user.is_admin:
        flash('您沒有權限進入管理儀表板', 'login_error')
        return redirect(url_for('index'))
    return redirect(url_for('admin_page') + '#dashboard')

# ==========================================
# 🔎 前台醫院評論查詢：快取、爬蟲、情緒分析與存檔
# ==========================================
@app.route('/analyze', methods=['POST'])
@login_required
@limiter.limit("2 per minute")
def analyze():
    if scrape_lock.locked():
        return jsonify({'status': 'error', 'message': '系統忙碌中，請稍後再試'})

    with scrape_lock:
        hospital_name = request.form.get('hospital')
        if not hospital_name:
            return jsonify({'status': 'error', 'message': '請輸入醫院名稱'})
        
        hospital_name = hospital_name.replace("臺", "台").strip()

        # 防呆攔截 - 只允許醫療相關機構
        valid_keywords = ['醫院', '診所', '醫學中心', '衛生所', '牙醫', '中醫', '耳鼻喉', '小兒', '眼科', '皮膚', '婦產', '骨科', '復健']
        
        if not any(kw in hospital_name for kw in valid_keywords):
            print(f"🚫 攔截非醫療搜尋：{hospital_name}")
            return jsonify({'status': 'error', 'message': '⚠️ 請輸入正確的醫療機構名稱 (需包含醫院、診所或科別名稱)'})

        # ==========================================
        # 🌟 新增：計算同地區（縣市）的平均分數基準線
        # ==========================================
        regional_avg_score = 5.0 # 預設給個 5 分底線
        current_city = None
        
        # 1. 先從載入的 Excel 名單尋找它在哪個縣市
        for region, cities in GLOBAL_HOSPITALS_DATA.items():
            for city, hospitals in cities.items():
                if any(hospital_name in h for h in hospitals) or any(h in hospital_name for h in hospitals):
                    current_city = city
                    break
            if current_city: break
            
        # 2. 去資料庫算該縣市的平均分
        if current_city:
            try:
                with sqlite3.connect(HR_DB) as conn:
                    c_avg = conn.cursor()
                    c_avg.execute('''
                        SELECT 
                            SUM(CASE WHEN r.analyzed_sentiment = 'POSITIVE' THEN 1 ELSE 0 END) * 1.0 / COUNT(r.id) * 10
                        FROM reviews r
                        JOIN hospitals h ON r.hospital_id = h.id
                        WHERE h.address LIKE ?
                    ''', (f'{current_city}%',))
                    
                    avg_result = c_avg.fetchone()[0]
                    if avg_result:
                        regional_avg_score = round(avg_result, 1)
                        print(f"📊 查到 {hospital_name} 位於 {current_city}，地區平均為 {regional_avg_score} 分")
            except Exception as e:
                print(f"⚠️ 計算地區平均失敗: {e}")

        # ==========================================
        # ⚡ 快取機制 (Cache)
        # ==========================================
        CACHE_DAYS = 7
        MIN_ANALYZE_REVIEWS = 30
        use_cached = False
        cached_sentiments = []
        pos_count = 0
        neg_count = 0
        
        try:
            with sqlite3.connect(HR_DB) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                place_id = hospital_name.lower().strip().replace(" ", "_")
                cursor.execute("SELECT id FROM hospitals WHERE google_place_id = ?", (place_id,))
                existing_hospital = cursor.fetchone()
                
                if existing_hospital:
                    hospital_id = existing_hospital['id']
                    cursor.execute("SELECT MAX(stored_at) as last_update, COUNT(*) as review_count FROM reviews WHERE hospital_id = ?", (hospital_id,))
                    last_update_row = cursor.fetchone()
                    
                    if last_update_row and last_update_row['last_update']:
                        last_update_str = last_update_row['last_update']
                        last_update_date = datetime.strptime(last_update_str, "%Y-%m-%d %H:%M:%S")
                        
                        cached_review_count = last_update_row['review_count'] or 0
                        if (datetime.now() - last_update_date).days < CACHE_DAYS and cached_review_count >= MIN_ANALYZE_REVIEWS:
                            use_cached = True
                            cursor.execute("""
                                SELECT content, analyzed_sentiment, review_time, stored_at, department
                                FROM reviews
                                WHERE hospital_id = ?
                                ORDER BY
                                    CASE
                                        WHEN review_time GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]' THEN review_time
                                        ELSE stored_at
                                    END DESC,
                                    id DESC
                            """, (hospital_id,))
                            for row in cursor.fetchall():
                                issue_category = classify_negative_issue(row['content'], row['analyzed_sentiment'])
                                cached_sentiments.append({
                                    'text': row['content'],
                                    'time': normalize_stored_review_time(row['review_time'], row['stored_at']),
                                    'label': row['analyzed_sentiment'],
                                    'emotion': row['analyzed_sentiment'],
                                    'score': 100.0,
                                    'department': row['department'],
                                    'issue_category': issue_category
                                })
                                if row['analyzed_sentiment'] == 'POSITIVE': pos_count += 1
                                elif row['analyzed_sentiment'] == 'NEGATIVE': neg_count += 1

        except Exception as e:
            print(f"⚠️ 快取讀取失敗: {e}")

        # ⚡ 觸發快取：回傳 JSON
        if use_cached and cached_sentiments:
            print(f"⚡ 觸發快取機制：秒殺載入 [{hospital_name}] 的資料！")
            keywords_data = extract_keywords(cached_sentiments)
            issue_data = summarize_negative_issues(cached_sentiments)
            issue_rows = get_negative_issue_rows(cached_sentiments, limit=8)
            feature_tags = generate_hospital_feature_tags(
                cached_sentiments,
                issue_rows,
                [],
                {
                    'total': len(cached_sentiments),
                    'positive_rate': round(pos_count / len(cached_sentiments) * 100) if cached_sentiments else 0,
                    'negative_rate': round(neg_count / len(cached_sentiments) * 100) if cached_sentiments else 0
                }
            )
            return jsonify({
                'status': 'success',
                'message': '⚡ 已從資料庫為您快速載入近期分析資料！',
                'hospital_id': hospital_id,
                'hospital': hospital_name,
                'pos': pos_count,
                'neg': neg_count,
                'keywords': keywords_data,
                'issues': issue_data,
                'feature_tags': feature_tags,
                'sentiments': cached_sentiments,
                'stored_at': last_update_str,
                'regional_avg': regional_avg_score,
                'is_favorite': is_hospital_favorite(current_user.id, hospital_id)
            })

        # ==========================================
        # 🐌 啟動爬蟲抓取
        # ==========================================
        print(f"🐌 資料庫無近期資料，啟動爬蟲抓取：{hospital_name}")
        reviews = scrape_google_reviews(hospital_name, max_reviews=MIN_ANALYZE_REVIEWS)
        if not reviews:
            return jsonify({'status': 'error', 'message': '❌ 無法取得評論資料，請確認名稱是否正確或稍後再試。'})

        sentiments, pos_count, neg_count = analyze_reviews(reviews)
        # 👉 確保存檔路徑絕對正確
        csv_path = os.path.join(BASE_DIR, 'data', 'google_reviews.csv')
        pd.DataFrame(sentiments).to_csv(csv_path, index=False, encoding='utf-8-sig')

        conn = sqlite3.connect(HR_DB)
        cursor = conn.cursor()
        
        place_id = hospital_name.lower().strip().replace(" ", "_")
        address = hospital_name

        cursor.execute("SELECT id FROM hospitals WHERE google_place_id = ?", (place_id,))
        existing = cursor.fetchone()

        if existing:
            hospital_id = existing[0]
        else:
            cursor.execute('''INSERT INTO hospitals (name, address, google_place_id, created_at) VALUES (?, ?, ?, ?)''', 
                           (hospital_name, address, place_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            hospital_id = cursor.lastrowid

        new_reviews_count = 0 
        refreshed_reviews_count = 0
        crawl_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for s in sentiments:
            cursor.execute("SELECT id FROM reviews WHERE hospital_id = ? AND content = ?", (hospital_id, s['text']))
            existing_review = cursor.fetchone()
            if not existing_review:
                cursor.execute('''INSERT INTO reviews (hospital_id, author, content, rating, review_time, analyzed_sentiment, stored_at, department) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', 
                               (hospital_id, 'Unknown', s['text'], None, s['time'], s['label'], crawl_time, s['department']))
                new_reviews_count += 1
            else:
                cursor.execute('''
                    UPDATE reviews
                    SET review_time = ?, analyzed_sentiment = ?, stored_at = ?, department = ?
                    WHERE id = ?
                ''', (s['time'], s['label'], crawl_time, s['department'], existing_review[0]))
                refreshed_reviews_count += 1
        
        conn.commit()
        conn.close()
        
        keywords_data = extract_keywords(sentiments)
        issue_data = summarize_negative_issues(sentiments)
        issue_rows = get_negative_issue_rows(sentiments, limit=8)
        feature_tags = generate_hospital_feature_tags(
            sentiments,
            issue_rows,
            [],
            {
                'total': len(sentiments),
                'positive_rate': round(pos_count / len(sentiments) * 100) if sentiments else 0,
                'negative_rate': round(neg_count / len(sentiments) * 100) if sentiments else 0
            }
        )
        print(f"📊 爬蟲分析完成：爬取 {len(sentiments)} 筆")

        now_str = crawl_time
    
    # ✅ 爬蟲成功：回傳 JSON
    return jsonify({
        'status': 'success',
        'message': f'📊 分析完成！新增 {new_reviews_count} 則，更新 {refreshed_reviews_count} 則既有評論。',
        'hospital_id': hospital_id,
        'hospital': hospital_name,
        'pos': pos_count,
        'neg': neg_count,
        'keywords': keywords_data,
        'issues': issue_data,
        'feature_tags': feature_tags,
        'sentiments': sentiments,
        'stored_at': now_str,
        'regional_avg': regional_avg_score,
        'is_favorite': is_hospital_favorite(current_user.id, hospital_id)
    })

# ==========================================
# 📊 後台儀表板 API：評論、警示、爬蟲進度與 AI 用量
# ==========================================
@app.route('/api/dashboard-data')
@login_required
def dashboard_data():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    try:
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM reviews WHERE analyzed_sentiment = 'POSITIVE'")
            pos = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE analyzed_sentiment = 'NEGATIVE'")
            neg = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM reviews")
            total_reviews = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM hospitals")
            total_hospitals = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM reviews WHERE date(stored_at) = date('now', 'localtime')")
            today_reviews = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT hospital_id) FROM reviews WHERE date(stored_at) = date('now', 'localtime')")
            today_hospitals = cursor.fetchone()[0]
            cursor.execute("""
                SELECT COUNT(*)
                FROM reviews
                WHERE analyzed_sentiment = 'NEGATIVE'
                  AND date(stored_at) = date('now', 'localtime')
            """)
            today_negative_reviews = cursor.fetchone()[0]
            cursor.execute("""
                SELECT COUNT(*)
                FROM users
                WHERE role = 'hospital'
                  AND approval_status = 'pending'
            """)
            pending_hospital_users = cursor.fetchone()[0]
            cursor.execute("""
                SELECT COUNT(*)
                FROM hospital_award_applications
                WHERE status = 'pending'
            """)
            pending_award_applications = cursor.fetchone()[0]

            cursor.execute("""
                SELECT
                    date(stored_at) AS day,
                    COUNT(*) AS total_count,
                    SUM(CASE WHEN analyzed_sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count
                FROM reviews
                WHERE stored_at IS NOT NULL
                  AND date(stored_at) >= date('now', 'localtime', '-6 day')
                GROUP BY date(stored_at)
                ORDER BY day ASC
            """)
            trend_by_day = {
                row['day']: {
                    'total': row['total_count'] or 0,
                    'negative': row['negative_count'] or 0
                }
                for row in cursor.fetchall()
            }
            review_trend = []
            for i in range(6, -1, -1):
                day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                review_trend.append({
                    'date': day,
                    'label': day[5:],
                    'total': trend_by_day.get(day, {}).get('total', 0),
                    'negative': trend_by_day.get(day, {}).get('negative', 0)
                })

            cursor.execute("""
                SELECT
                    date(stored_at) AS day,
                    COUNT(DISTINCT hospital_id || '|' || stored_at) AS run_count
                FROM reviews
                WHERE stored_at IS NOT NULL
                  AND date(stored_at) >= date('now', 'localtime', '-6 day')
                GROUP BY date(stored_at)
                ORDER BY day ASC
            """)
            crawler_by_day = {
                row['day']: {
                    'review_runs': row['run_count'] or 0,
                    'general': row['run_count'] or 0,
                    'batch': 0,
                    'batch_failed': 0,
                    'jobs': row['run_count'] or 0,
                    'finished': row['run_count'] or 0,
                    'issues': 0
                }
                for row in cursor.fetchall()
            }

            cursor.execute("""
                SELECT
                    date(finished_at) AS day,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS batch_success,
                    SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS batch_failed
                FROM batch_crawl_job_items
                WHERE finished_at IS NOT NULL
                  AND date(finished_at) >= date('now', 'localtime', '-6 day')
                GROUP BY date(finished_at)
                ORDER BY day ASC
            """)
            for row in cursor.fetchall():
                day = row['day']
                values = crawler_by_day.setdefault(day, {
                    'review_runs': 0,
                    'general': 0,
                    'batch': 0,
                    'batch_failed': 0,
                    'jobs': 0,
                    'finished': 0,
                    'issues': 0
                })
                batch_success = row['batch_success'] or 0
                batch_failed = row['batch_failed'] or 0
                values['batch'] = batch_success
                values['batch_failed'] = batch_failed
                values['general'] = max((values.get('review_runs') or 0) - batch_success, 0)
                values['finished'] = values['general'] + batch_success
                values['issues'] = batch_failed
                values['jobs'] = values['finished'] + batch_failed
            crawler_trend = []
            for i in range(6, -1, -1):
                day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                values = crawler_by_day.get(day, {})
                crawler_trend.append({
                    'date': day,
                    'label': day[5:],
                    'count': values.get('jobs', 0),
                    'jobs': values.get('jobs', 0),
                    'finished': values.get('finished', 0),
                    'issues': values.get('issues', 0),
                    'general': values.get('general', 0),
                    'batch': values.get('batch', 0),
                    'batch_failed': values.get('batch_failed', 0)
                })
            today_key = datetime.now().strftime('%Y-%m-%d')
            today_crawler_values = crawler_by_day.get(today_key, {})
            cursor.execute("""
                SELECT MAX(run_at) AS latest_run_at
                FROM (
                    SELECT MAX(stored_at) AS run_at
                    FROM reviews
                    WHERE stored_at IS NOT NULL
                      AND date(stored_at) = date('now', 'localtime')
                    UNION ALL
                    SELECT MAX(finished_at) AS run_at
                    FROM batch_crawl_job_items
                    WHERE finished_at IS NOT NULL
                      AND date(finished_at) = date('now', 'localtime')
                )
            """)
            latest_run_at = cursor.fetchone()['latest_run_at']
            crawler_today_summary = {
                'total': today_crawler_values.get('jobs', 0),
                'general': today_crawler_values.get('general', 0),
                'batch': today_crawler_values.get('batch', 0),
                'batch_failed': today_crawler_values.get('batch_failed', 0),
                'issues': today_crawler_values.get('issues', 0),
                'latest_run_at': latest_run_at or '--'
            }

            cursor.execute("""
                SELECT content, analyzed_sentiment
                FROM reviews
                WHERE analyzed_sentiment = 'NEGATIVE'
            """)
            negative_reviews = [
                {'text': row['content'], 'label': row['analyzed_sentiment']}
                for row in cursor.fetchall()
            ]
            top_issues = get_negative_issue_rows(negative_reviews, limit=8)

            cursor.execute("""
                SELECT
                    h.id,
                    h.name,
                    COALESCE(MAX(r.stored_at), h.created_at) AS last_activity,
                    COUNT(r.id) AS review_count,
                    SUM(CASE WHEN r.analyzed_sentiment = 'POSITIVE' THEN 1 ELSE 0 END) AS positive_count,
                    SUM(CASE WHEN r.analyzed_sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count
                FROM hospitals h
                LEFT JOIN reviews r ON h.id = r.hospital_id
                GROUP BY h.id
                ORDER BY last_activity DESC
                LIMIT 6
            """)
            recent_hospitals = []
            for row in cursor.fetchall():
                review_count = row['review_count'] or 0
                positive_count = row['positive_count'] or 0
                negative_count = row['negative_count'] or 0
                recent_hospitals.append({
                    'id': row['id'],
                    'name': row['name'],
                    'last_activity': row['last_activity'],
                    'review_count': review_count,
                    'positive_count': positive_count,
                    'negative_count': negative_count,
                    'positive_rate': round(positive_count / review_count * 100) if review_count else 0
                })

            cursor.execute("""
                SELECT
                    h.id,
                    h.name,
                    COUNT(r.id) AS review_count,
                    SUM(CASE WHEN r.analyzed_sentiment = 'POSITIVE' THEN 1 ELSE 0 END) AS positive_count,
                    SUM(CASE WHEN r.analyzed_sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count
                FROM hospitals h
                JOIN reviews r ON h.id = r.hospital_id
                GROUP BY h.id
                HAVING review_count >= 5
                ORDER BY (negative_count * 1.0 / review_count) DESC, negative_count DESC
                LIMIT 5
            """)
            risk_hospitals = []
            for row in cursor.fetchall():
                review_count = row['review_count'] or 0
                negative_count = row['negative_count'] or 0
                risk_hospitals.append({
                    'id': row['id'],
                    'name': row['name'],
                    'review_count': review_count,
                    'negative_count': negative_count,
                    'negative_rate': round(negative_count / review_count * 100) if review_count else 0
                })

            cursor.execute("""
                SELECT
                    h.id,
                    h.name,
                    SUM(CASE
                        WHEN r.analyzed_sentiment = 'NEGATIVE'
                         AND date(r.stored_at) >= date('now', 'localtime', '-6 day')
                        THEN 1 ELSE 0 END
                    ) AS recent_negative,
                    SUM(CASE
                        WHEN r.analyzed_sentiment = 'NEGATIVE'
                         AND date(r.stored_at) BETWEEN date('now', 'localtime', '-13 day') AND date('now', 'localtime', '-7 day')
                        THEN 1 ELSE 0 END
                    ) AS previous_negative,
                    SUM(CASE
                        WHEN date(r.stored_at) >= date('now', 'localtime', '-6 day')
                        THEN 1 ELSE 0 END
                    ) AS recent_total
                FROM hospitals h
                JOIN reviews r ON h.id = r.hospital_id
                WHERE r.stored_at IS NOT NULL
                  AND date(r.stored_at) >= date('now', 'localtime', '-13 day')
                GROUP BY h.id
                HAVING recent_negative >= 3
                   AND (previous_negative = 0 OR recent_negative >= previous_negative * 1.5)
                ORDER BY
                    (recent_negative - previous_negative) DESC,
                    recent_negative DESC
                LIMIT 5
            """)
            negative_surge_alerts = []
            for row in cursor.fetchall():
                recent_negative = row['recent_negative'] or 0
                previous_negative = row['previous_negative'] or 0
                recent_total = row['recent_total'] or 0

                cursor.execute("""
                    SELECT content, analyzed_sentiment
                    FROM reviews
                    WHERE hospital_id = ?
                      AND analyzed_sentiment = 'NEGATIVE'
                      AND date(stored_at) >= date('now', 'localtime', '-6 day')
                """, (row['id'],))
                recent_negative_reviews = [
                    {'text': review['content'], 'label': review['analyzed_sentiment']}
                    for review in cursor.fetchall()
                ]
                issue_rows = get_negative_issue_rows(recent_negative_reviews, limit=3)
                top_issue = issue_rows[0]['issue_category'] if issue_rows else '未分類'
                increase_rate = None
                if previous_negative:
                    increase_rate = round((recent_negative - previous_negative) / previous_negative * 100)

                negative_surge_alerts.append({
                    'id': row['id'],
                    'name': row['name'],
                    'recent_negative': recent_negative,
                    'previous_negative': previous_negative,
                    'recent_total': recent_total,
                    'recent_negative_rate': round(recent_negative / recent_total * 100) if recent_total else 0,
                    'increase_rate': increase_rate,
                    'top_issue': top_issue,
                    'issues': issue_rows
                })

            db_size_mb = round(os.path.getsize(HR_DB) / 1024 / 1024, 2) if os.path.exists(HR_DB) else 0
            backup_history = get_backup_history(8)
            last_backup = backup_history[0] if backup_history else None
            has_risk_alert = any(h['negative_rate'] >= 50 for h in risk_hospitals) or bool(negative_surge_alerts)

            return jsonify({
                'positive': pos,
                'negative': neg,
                'total_reviews': total_reviews,
                'total_hospitals': total_hospitals,
                'total_users': total_users,
                'today_reviews': today_reviews,
                'today_hospitals': today_hospitals,
                'today_negative_reviews': today_negative_reviews,
                'negative_rate': round(neg / total_reviews * 100) if total_reviews else 0,
                'positive_rate': round(pos / total_reviews * 100) if total_reviews else 0,
                'top_issues': top_issues,
                'recent_hospitals': recent_hospitals,
                'risk_hospitals': risk_hospitals,
                'negative_surge_alerts': negative_surge_alerts,
                'review_trend': review_trend,
                'crawler_trend': crawler_trend,
                'crawler_today_summary': crawler_today_summary,
                'alerts': {
                    'risk_hospitals': len(risk_hospitals),
                    'negative_surge_alerts': len(negative_surge_alerts),
                    'today_negative_reviews': today_negative_reviews,
                    'pending_hospital_users': pending_hospital_users,
                    'pending_award_applications': pending_award_applications,
                    'has_risk_alert': has_risk_alert,
                    'backup_recommended': db_size_mb >= 20
                },
                'system_status': {
                    'sentiment_model': sentiment_pipeline is not None,
                    'sentiment_model_loaded': sentiment_pipeline is not None,
                    'sentiment_model_error': sentiment_model_error,
                    'sentiment_model_name': SENTIMENT_MODEL_NAME,
                    'ai_summary_mode': get_ai_summary_mode(),
                    'gemini_configured': bool(GOOGLE_API_KEY),
                    'gemini_usage': get_gemini_usage_summary(),
                    'local_ai_usage': get_local_ai_usage_summary(),
                    'database_size_mb': db_size_mb,
                    'backup_history': backup_history,
                    'last_backup': last_backup
                }
            })
    except Exception as e:
        print(f"⚠️ 儀表板資料載入失敗: {e}")
        return jsonify({'error': '儀表板資料載入失敗，請稍後再試。'}), 500

# ==========================================
# 🤖 後台管理：全站 AI 模式切換
# ==========================================
@app.route('/admin/ai_summary_mode', methods=['POST'])
@login_required
def update_ai_summary_mode():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    payload = request.get_json(silent=True) or {}
    mode = payload.get('mode')
    if mode not in ['auto', 'gemini', 'local']:
        return jsonify({'error': '不支援的 AI 模式'}), 400

    set_app_setting('ai_summary_mode', mode)
    mode_labels = {
        'auto': '自動：Gemini 優先，失敗時改用本地端',
        'gemini': '手動：Gemini 優先',
        'local': '手動：只用本地端統計'
    }
    return jsonify({
        'status': 'ok',
        'mode': mode,
        'label': mode_labels[mode]
    })

@app.route('/admin/risk_hospital/<int:hospital_id>')
@login_required
def get_risk_hospital_detail(hospital_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, address FROM hospitals WHERE id = ?", (hospital_id,))
        hospital = cursor.fetchone()
        if not hospital:
            return jsonify({'error': '找不到醫院資料'}), 404

        cursor.execute("""
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN analyzed_sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count
            FROM reviews
            WHERE hospital_id = ?
        """, (hospital_id,))
        stats = cursor.fetchone()
        total = stats['total'] or 0
        negative_count = stats['negative_count'] or 0

        cursor.execute("""
            SELECT
                SUM(CASE
                    WHEN analyzed_sentiment = 'NEGATIVE'
                     AND date(stored_at) >= date('now', 'localtime', '-6 day')
                    THEN 1 ELSE 0 END
                ) AS recent_negative,
                SUM(CASE
                    WHEN analyzed_sentiment = 'NEGATIVE'
                     AND date(stored_at) BETWEEN date('now', 'localtime', '-13 day') AND date('now', 'localtime', '-7 day')
                    THEN 1 ELSE 0 END
                ) AS previous_negative,
                SUM(CASE
                    WHEN date(stored_at) >= date('now', 'localtime', '-6 day')
                    THEN 1 ELSE 0 END
                ) AS recent_total
            FROM reviews
            WHERE hospital_id = ?
              AND stored_at IS NOT NULL
              AND date(stored_at) >= date('now', 'localtime', '-13 day')
        """, (hospital_id,))
        recent_stats = cursor.fetchone()
        recent_negative = recent_stats['recent_negative'] or 0
        previous_negative = recent_stats['previous_negative'] or 0
        recent_total = recent_stats['recent_total'] or 0

        cursor.execute("""
            SELECT id, username, official_email, contact_name, approval_status
            FROM users
            WHERE role = 'hospital'
              AND hospital_id = ?
            ORDER BY
                CASE approval_status WHEN 'approved' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
                id DESC
        """, (hospital_id,))
        accounts = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT id, title, content, category, link_url, created_at
            FROM hospital_notifications
            WHERE hospital_id = ?
            ORDER BY id DESC
            LIMIT 5
        """, (hospital_id,))
        notifications = [dict(row) for row in cursor.fetchall()]

    return jsonify({
        'hospital': {'id': hospital['id'], 'name': hospital['name'], 'address': hospital['address']},
        'stats': {
            'total': total,
            'negative_count': negative_count,
            'negative_rate': round(negative_count / total * 100) if total else 0,
            'recent_negative': recent_negative,
            'previous_negative': previous_negative,
            'recent_total': recent_total,
            'recent_negative_rate': round(recent_negative / recent_total * 100) if recent_total else 0
        },
        'accounts': accounts,
        'notifications': notifications
    })

@app.route('/admin/send_risk_notice/<int:hospital_id>', methods=['POST'])
@login_required
def send_risk_notice(hospital_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    payload = request.get_json(silent=True) or {}
    content = (payload.get('content') or '').strip()
    user_id = payload.get('user_id')
    if not content:
        return jsonify({'error': '請填寫提醒內容'}), 400

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM hospitals WHERE id = ?", (hospital_id,))
        if not cursor.fetchone():
            return jsonify({'error': '找不到醫院資料'}), 404

        if user_id:
            cursor.execute("""
                SELECT id FROM users
                WHERE id = ? AND role = 'hospital' AND hospital_id = ?
            """, (user_id, hospital_id))
            if not cursor.fetchone():
                return jsonify({'error': '找不到可通知的院方帳號'}), 404

        cursor.execute("""
            INSERT INTO hospital_notifications
                (hospital_id, user_id, title, content, status, category, link_url, created_at, created_by)
            VALUES (?, ?, ?, ?, 'unread', 'risk', ?, ?, ?)
        """, (
            hospital_id,
            user_id,
            '負評比例提醒',
            content,
            url_for('hospital_profile', hospital_id=hospital_id),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            current_user.id
        ))
        conn.commit()

    return jsonify({'status': 'ok', 'message': '已發送提醒給院方帳號。'})

@app.route('/admin/send_all_risk_notices', methods=['POST'])
@login_required
def send_all_risk_notices():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sent_notifications = 0
    sent_hospital_ids = set()
    skipped_hospitals = []

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                h.id,
                h.name,
                COUNT(r.id) AS review_count,
                SUM(CASE WHEN r.analyzed_sentiment = 'NEGATIVE' THEN 1 ELSE 0 END) AS negative_count
            FROM hospitals h
            JOIN reviews r ON h.id = r.hospital_id
            GROUP BY h.id
            HAVING review_count >= 5
            ORDER BY (negative_count * 1.0 / review_count) DESC, negative_count DESC
            LIMIT 5
        """)
        risk_hospitals = cursor.fetchall()

        for hospital in risk_hospitals:
            cursor.execute("""
                SELECT id
                FROM users
                WHERE role = 'hospital'
                  AND approval_status = 'approved'
                  AND hospital_id = ?
                ORDER BY id ASC
            """, (hospital['id'],))
            accounts = cursor.fetchall()
            if not accounts:
                skipped_hospitals.append(hospital['name'])
                continue

            review_count = hospital['review_count'] or 0
            negative_count = hospital['negative_count'] or 0
            negative_rate = round(negative_count / review_count * 100) if review_count else 0
            content = (
                f"{hospital['name']} 近期負評比例為 {negative_rate}%，"
                f"共 {negative_count} 則負評。建議儘速檢視主要負評原因，"
                "並追蹤掛號流程、等候時間、醫護溝通與服務態度等項目。"
            )

            for account in accounts:
                cursor.execute("""
                    INSERT INTO hospital_notifications
                        (hospital_id, user_id, title, content, status, category, link_url, created_at, created_by)
                    VALUES (?, ?, ?, ?, 'unread', 'risk', ?, ?, ?)
                """, (
                    hospital['id'],
                    account['id'],
                    '負評比例提醒',
                    content,
                    url_for('hospital_profile', hospital_id=hospital['id']),
                    now,
                    current_user.id
                ))
                sent_notifications += 1
                sent_hospital_ids.add(hospital['id'])

        conn.commit()

    return jsonify({
        'status': 'ok',
        'message': f"已發送 {sent_notifications} 則提醒，涵蓋 {len(sent_hospital_ids)} 家高風險醫院。",
        'sent_notifications': sent_notifications,
        'sent_hospitals': len(sent_hospital_ids),
        'skipped_hospitals': skipped_hospitals
    })

@app.route('/admin/today_negative_reviews')
@login_required
def today_negative_reviews():
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    hospital_id = request.args.get('hospital_id', type=int)
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        base_query = """
            SELECT r.id, r.content, r.analyzed_sentiment, r.review_time, r.stored_at,
                   h.id AS hospital_id, h.name AS hospital_name
            FROM reviews r
            JOIN hospitals h ON r.hospital_id = h.id
            WHERE r.analyzed_sentiment = 'NEGATIVE'
              AND date(r.stored_at) = date('now', 'localtime')
        """
        params = []
        if hospital_id:
            base_query += " AND h.id = ?"
            params.append(hospital_id)
        base_query += " ORDER BY r.stored_at DESC, r.id DESC"
        cursor.execute(base_query, params)
        rows = cursor.fetchall()

    data = []
    for row in rows:
        data.append({
            'id': row['id'],
            'content': row['content'] or '',
            'sentiment': row['analyzed_sentiment'],
            'issue_category': classify_negative_issue(row['content'] or '', row['analyzed_sentiment']),
            'time': normalize_stored_review_time(row['review_time'], row['stored_at']),
            'stored_at': row['stored_at'] or '',
            'hospital_id': row['hospital_id'],
            'hospital': row['hospital_name']
        })

    if request.args.get('detail') == '1' or hospital_id:
        return jsonify(data)

    grouped = {}
    for item in data:
        group = grouped.setdefault(item['hospital_id'], {
            'hospital_id': item['hospital_id'],
            'hospital': item['hospital'],
            'count': 0,
            'latest_time': item['time'],
            'latest_stored_at': item.get('stored_at') or '',
            'issues': Counter()
        })
        group['count'] += 1
        group['issues'][item['issue_category']] += 1
        if (item.get('stored_at') or '') > (group.get('latest_stored_at') or ''):
            group['latest_stored_at'] = item.get('stored_at') or ''
            group['latest_time'] = item['time']
    summary = []
    for group in grouped.values():
        top_issue = group['issues'].most_common(1)[0][0] if group['issues'] else '未分類'
        summary.append({
            'hospital_id': group['hospital_id'],
            'hospital': group['hospital'],
            'count': group['count'],
            'latest_time': group['latest_time'],
            'latest_stored_at': group['latest_stored_at'],
            'top_issue': top_issue
        })
    summary.sort(key=lambda item: item.get('latest_stored_at') or '', reverse=True)
    return jsonify({'total': len(data), 'hospitals': summary})

# ==========================================
# 🔐 使用者登入、註冊、登出與共用公告注入
# ==========================================
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user_captcha = request.form.get('captcha', '').upper()
        real_captcha = session.pop('captcha_code', None) 
        
        if not real_captcha or user_captcha != real_captcha:
            flash('驗證碼錯誤', 'login_error')
            return redirect(url_for('login'))
        
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row 
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=?", (username,))
            row = c.fetchone()
            
        if row and bcrypt.check_password_hash(row['password'], password):
            user = User(
                id_=row['id'],
                username=row['username'],
                password=row['password'],
                is_admin=row['is_admin'],
                role=row['role'],
                hospital_id=row['hospital_id'],
                approval_status=row['approval_status'],
                rejection_reason=row['rejection_reason']
            )
            login_user(user)
            session['username'] = username
            if user.role == 'hospital':
                if user.approval_status != 'approved' or not user.hospital_id:
                    return redirect(url_for('hospital_application_status'))
                return redirect(url_for('hospital_dashboard'))
            if user.is_admin:
                return redirect(url_for('admin_page'))
            return redirect(url_for('index'))
        else:
            flash('帳號或密碼錯誤','login_error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        account_type = request.form.get('account_type', 'user')
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        
        # 🌟 新增：處理證明文件上傳
        proof_filename = None
        if 'proof_document' in request.files:
            proof_filename, upload_error = save_proof_document(request.files['proof_document'])
            if upload_error:
                flash(upload_error, 'register_error')
                return redirect(url_for('register'))

        try:
            with sqlite3.connect(HR_DB) as conn:
                c = conn.cursor()
                if account_type == 'hospital':
                    # 🌟 修改：SQL 語法加入 proof_document
                    c.execute("""
                        INSERT INTO users (
                            username, password, is_admin, role, approval_status,
                            official_email, contact_name, contact_phone, institution_code, requested_hospital_name, proof_document
                        )
                        VALUES (?, ?, 0, 'hospital', 'pending', ?, ?, ?, ?, ?, ?)
                    """, (
                        username,
                        hashed_pw,
                        request.form.get('official_email', '').strip(),
                        request.form.get('contact_name', '').strip(),
                        request.form.get('contact_phone', '').strip(),
                        request.form.get('institution_code', '').strip(),
                        request.form.get('requested_hospital_name', '').replace("臺", "台").strip(),
                        proof_filename  # 存入檔名
                    ))
                else:
                    c.execute(
                        "INSERT INTO users (username, password, is_admin, role, approval_status) VALUES (?, ?, 0, 'user', 'approved')",
                        (username, hashed_pw)
                    )
                conn.commit()
            flash('醫院帳號申請已送出，請等待管理員審核。' if account_type == 'hospital' else '註冊成功','register_success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('帳號已存在','register_error')
    return render_template('register.html', all_hospitals=FLAT_HOSPITAL_LIST)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.context_processor
def inject_announcement():
    active_ann = None
    unread_hospital_notifications = 0
    try:
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            c.execute("SELECT content FROM announcements WHERE is_active = 1 ORDER BY id DESC LIMIT 1")
            row = c.fetchone()
            if row: active_ann = row['content']

            if getattr(current_user, 'is_authenticated', False) and getattr(current_user, 'role', None) == 'hospital':
                if current_user.hospital_id:
                    c.execute("""
                        SELECT COUNT(*)
                        FROM hospital_notifications
                        WHERE ((hospital_id = ? AND (user_id IS NULL OR user_id = ?)) OR user_id = ?)
                          AND status = 'unread'
                    """, (current_user.hospital_id, current_user.id, current_user.id))
                else:
                    c.execute("""
                        SELECT COUNT(*)
                        FROM hospital_notifications
                        WHERE user_id = ?
                          AND status = 'unread'
                    """, (current_user.id,))
                unread_hospital_notifications = c.fetchone()[0]
    except: pass
    return dict(
        active_announcement=active_ann,
        unread_hospital_notifications=unread_hospital_notifications
    )

# ==========================================
# 🛡️ Admin 管理後台功能
# ==========================================
@app.route('/admin')
@login_required
def admin_page():
    if not current_user.is_admin:
        flash('您沒有權限進入管理後台', 'login_error')
        return redirect(url_for('index'))

    users_data = []
    hospitals_data = []
    stats = {}
    stop_words_data = [] 
    awards_data = []
    award_applications_data = []
    top_negative_issues = []
    admin_system_notifications = []
    uses_default_admin_password = (
        current_user.username == 'admin'
        and bcrypt.check_password_hash(current_user.password, '123456')
    )

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row # 讓資料可以用字典方式讀取
        cursor = conn.cursor()

        # 新增：撈取公告清單
        cursor.execute("SELECT * FROM announcements ORDER BY id DESC")
        announcements_list = cursor.fetchall()

        cursor.execute("""
            SELECT id, title, content, category, created_at
            FROM hospital_notifications
            WHERE 1 = 0
              AND status = 'unread'
              AND (user_id IS NULL OR user_id = ?)
            ORDER BY id DESC
            LIMIT 5
        """, (current_user.id,))
        admin_system_notifications = cursor.fetchall()

        # 取得儀表板統計數字
        cursor.execute("SELECT COUNT(*) FROM users")
        stats['total_users'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM hospitals")
        stats['total_hospitals'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM reviews")
        stats['total_reviews'] = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT hospital_id) FROM reviews WHERE date(stored_at) = date('now', 'localtime')")
        stats['today_crawls'] = cursor.fetchone()[0]

        cursor.execute("""
            SELECT
                date(stored_at) AS day,
                COUNT(DISTINCT hospital_id || '|' || stored_at) AS run_count
            FROM reviews
            WHERE stored_at IS NOT NULL
              AND date(stored_at) >= date('now', 'localtime', '-6 day')
            GROUP BY date(stored_at)
        """)
        crawler_rows = {
            row['day']: {
                'review_runs': row['run_count'] or 0,
                'general': row['run_count'] or 0,
                'batch': 0,
                'batch_failed': 0,
                'jobs': row['run_count'] or 0,
                'finished': row['run_count'] or 0,
                'issues': 0
            }
            for row in cursor.fetchall()
        }

        cursor.execute("""
            SELECT
                date(finished_at) AS day,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS batch_success,
                SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS batch_failed
            FROM batch_crawl_job_items
            WHERE finished_at IS NOT NULL
              AND date(finished_at) >= date('now', 'localtime', '-6 day')
            GROUP BY date(finished_at)
        """)
        for row in cursor.fetchall():
            day = row['day']
            values = crawler_rows.setdefault(day, {
                'review_runs': 0,
                'general': 0,
                'batch': 0,
                'batch_failed': 0,
                'jobs': 0,
                'finished': 0,
                'issues': 0
            })
            batch_success = row['batch_success'] or 0
            batch_failed = row['batch_failed'] or 0
            values['batch'] = batch_success
            values['batch_failed'] = batch_failed
            values['general'] = max((values.get('review_runs') or 0) - batch_success, 0)
            values['finished'] = values['general'] + batch_success
            values['issues'] = batch_failed
            values['jobs'] = values['finished'] + batch_failed
        crawler_trend_data = []
        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            values = crawler_rows.get(day, {})
            crawler_trend_data.append({
                'date': day,
                'label': day[5:],
                'jobs': values.get('jobs', 0),
                'finished': values.get('finished', 0),
                'issues': values.get('issues', 0),
                'general': values.get('general', 0),
                'batch': values.get('batch', 0),
                'batch_failed': values.get('batch_failed', 0)
            })
        crawler_trend_max = max(
            [1] + [max(item['jobs'], item['finished'], item['issues']) for item in crawler_trend_data]
        )

        # 取得會員資料 (加上 u.proof_document 讓它變成第 13 個欄位)
        cursor.execute("""
            SELECT
                u.id, u.username, u.is_admin, u.role, u.approval_status, u.hospital_id,
                u.official_email, u.contact_name, u.contact_phone, u.institution_code,
                h.name AS bound_hospital_name, u.requested_hospital_name, u.rejection_reason,
                u.proof_document
            FROM users u
            LEFT JOIN hospitals h ON u.hospital_id = h.id
            ORDER BY
                CASE u.approval_status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                u.id DESC
        """)
        users_data = cursor.fetchall()
        hospital_user_ids = [row['id'] for row in users_data if row['role'] == 'hospital']
        hospital_user_history_map = {}
        if hospital_user_ids:
            placeholders = ",".join(["?"] * len(hospital_user_ids))
            cursor.execute(f"""
                SELECT
                    h.user_id, h.action, h.note, h.created_at,
                    actor.username AS actor_username,
                    hospital.name AS hospital_name
                FROM hospital_user_review_history h
                LEFT JOIN users actor ON h.actor_id = actor.id
                LEFT JOIN hospitals hospital ON h.hospital_id = hospital.id
                WHERE h.user_id IN ({placeholders})
                ORDER BY h.created_at DESC, h.id DESC
            """, hospital_user_ids)
            for history_row in cursor.fetchall():
                hospital_user_history_map.setdefault(history_row['user_id'], []).append(dict(history_row))

        try:
            cursor.execute("SELECT id, hospital_name, department, award_name FROM hospital_awards ORDER BY id DESC")
            awards_data = cursor.fetchall()
        except Exception as e:
            print(f"⚠️ 讀取得獎紀錄失敗: {e}")

        try:
            cursor.execute("""
                SELECT
                    a.id, a.hospital_id, a.hospital_name, a.department, a.award_name,
                    a.status, a.admin_note, a.proof_document, a.created_at, a.reviewed_at,
                    u.username AS applicant_username
                FROM hospital_award_applications a
                LEFT JOIN users u ON a.user_id = u.id
                ORDER BY
                    CASE a.status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                    a.id DESC
            """)
            award_applications_data = [dict(row) for row in cursor.fetchall()]
            if award_applications_data:
                placeholders = ",".join(["?"] * len(award_applications_data))
                cursor.execute(f"""
                    SELECT
                        h.application_id, h.action, h.note, h.proof_document,
                        h.actor_id, h.created_at, u.username AS actor_username
                    FROM hospital_award_application_history h
                    LEFT JOIN users u ON h.actor_id = u.id
                    WHERE h.application_id IN ({placeholders})
                    ORDER BY h.id DESC
                """, [item['id'] for item in award_applications_data])
                history_map = {}
                for row in cursor.fetchall():
                    history_map.setdefault(row['application_id'], []).append(dict(row))
                for item in award_applications_data:
                    item['history'] = history_map.get(item['id'], [])
        except Exception as e:
            print(f"⚠️ 讀取得獎申請失敗: {e}")

        # 取得醫院爬取紀錄
        query = '''
            SELECT 
                h.id, 
                h.name, 
                h.address, 
                COALESCE(MAX(r.stored_at), h.created_at) as last_activity, 
                COUNT(r.id) as review_count
            FROM hospitals h
            LEFT JOIN reviews r ON h.id = r.hospital_id
            GROUP BY h.id
            ORDER BY last_activity DESC 
        '''
        cursor.execute(query)
        hospital_rows = cursor.fetchall()
        cursor.execute("""
            SELECT hospital_id, COUNT(*) AS account_count
            FROM users
            WHERE role = 'hospital'
              AND approval_status = 'approved'
              AND hospital_id IS NOT NULL
            GROUP BY hospital_id
        """)
        hospital_account_counts = {
            row['hospital_id']: row['account_count']
            for row in cursor.fetchall()
        }
        hospitals_data = []
        for row in hospital_rows:
            display_address, address_source = resolve_hospital_address(row['name'], row['address'])
            hospital_user_count = hospital_account_counts.get(row['id'], 0)
            hospitals_data.append({
                'id': row['id'],
                'name': row['name'],
                'address': row['address'],
                'display_address': display_address,
                'address_source': address_source,
                'last_activity': row['last_activity'],
                'review_count': row['review_count'],
                'hospital_user_count': hospital_user_count,
                'has_hospital_account': hospital_user_count > 0
            })

        # 取得動態過濾詞
        try:
            cursor.execute("CREATE TABLE IF NOT EXISTS stop_words(id INTEGER PRIMARY KEY AUTOINCREMENT, word TEXT UNIQUE NOT NULL)")
            cursor.execute("SELECT id, word FROM stop_words ORDER BY id DESC")
            stop_words_data = cursor.fetchall()
            
        except Exception as e:
            print(f"⚠️ 讀取過濾詞失敗: {e}")

        # ==========================================
        # 📊 新增：撈取 Top 10 最常出現的症狀
        # ==========================================
        top_symptoms = []
        try:
            # 檢查表格是否存在，避免報錯
            cursor.execute("CREATE TABLE IF NOT EXISTS symptom_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, symptom_text TEXT NOT NULL, created_at TEXT)")
            
            cursor.execute('''
                SELECT symptom_text, COUNT(*) as count 
                FROM symptom_logs 
                GROUP BY symptom_text 
                ORDER BY count DESC, symptom_text ASC
                LIMIT 20
            ''')
            top_symptoms = cursor.fetchall()
        except Exception as e:
            print(f"⚠️ 讀取症狀統計失敗: {e}")
        # ==========================================

        try:
            cursor.execute("""
                SELECT content, analyzed_sentiment
                FROM reviews
                WHERE analyzed_sentiment = 'NEGATIVE'
            """)
            negative_reviews = [
                {'text': row['content'], 'label': row['analyzed_sentiment']}
                for row in cursor.fetchall()
            ]
            top_negative_issues = get_negative_issue_rows(negative_reviews, limit=10)
        except Exception as e:
            print(f"⚠️ 讀取負評原因統計失敗: {e}")

    return render_template('admin.html', 
                           users=users_data, 
                           hospitals=hospitals_data, 
                           stats=stats,
                           stop_words=stop_words_data,
                           awards=awards_data,
                           award_applications=award_applications_data,
                           award_departments=AWARD_DEPARTMENTS,
                           top_symptoms=top_symptoms,
                           top_negative_issues=top_negative_issues,
                           hospital_user_history=hospital_user_history_map,
                           crawler_trend_data=crawler_trend_data,
                           crawler_trend_max=crawler_trend_max,
                           announcements=announcements_list,
                           admin_system_notifications=admin_system_notifications,
                           uses_default_admin_password=uses_default_admin_password)

@app.route('/admin/log_view', methods=['POST'])
@login_required
def admin_log_view():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    data = request.get_json(silent=True) or {}
    view = str(data.get('view') or '').strip()
    label = str(data.get('label') or '').strip()
    allowed_views = {
        'dashboard': '工作台總覽',
        'reviews': '評論監控',
        'crawler': '爬蟲管理',
        'health': '健康警示',
        'data': '醫院資料庫',
        'users': '會員權限'
    }
    if view not in allowed_views:
        return jsonify({'error': '未知頁面'}), 400

    print(f"📍 Admin 目前頁面：{label or allowed_views[view]} (#{view})", flush=True)
    return jsonify({'ok': True})

@app.route('/admin/backup')
@login_required
def backup_db():
    if not current_user.is_admin:
        flash('權限不足，無法執行備份操作', 'analyze_error')
        return redirect(url_for('index'))
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M')
    file_name = f"backup_{timestamp}.db"
    file_size_bytes = os.path.getsize(HR_DB) if os.path.exists(HR_DB) else 0
    log_backup_history(file_name, file_size_bytes)
    return send_file(HR_DB, as_attachment=True, download_name=file_name)

@app.route('/admin/add_stop_word', methods=['POST'])
@login_required
def add_stop_word():
    if not current_user.is_admin: return redirect(url_for('index'))
    word = request.form.get('word', '').strip()
    if word:
        try:
            with sqlite3.connect(HR_DB) as conn:
                c = conn.cursor()
                c.execute("INSERT INTO stop_words (word) VALUES (?)", (word,))
                conn.commit()
            flash(f'已新增過濾詞：{word}', 'analyze_success')
        except sqlite3.IntegrityError:
            flash(f'過濾詞「{word}」已經存在囉！', 'analyze_error')
    return redirect(url_for('admin_page'))

@app.route('/admin/delete_stop_word/<int:word_id>', methods=['POST'])
@login_required
def delete_stop_word(word_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM stop_words WHERE id = ?", (word_id,))
        conn.commit()
    flash('過濾詞已刪除', 'analyze_success')
    return redirect(url_for('admin_page'))

# ==========================================
# 🗑️ 後台管理：刪除特定症狀紀錄
# ==========================================
@app.route('/admin/delete_symptom', methods=['POST'])
@login_required
def delete_symptom():
    if not current_user.is_admin: 
        return redirect(url_for('index'))
    
    symptom_text = request.form.get('symptom_text', '').strip()
    
    if symptom_text:
        try:
            with sqlite3.connect(HR_DB) as conn:
                c = conn.cursor()
                # 把資料庫裡所有符合這個文字的紀錄一次刪掉
                c.execute("DELETE FROM symptom_logs WHERE symptom_text = ?", (symptom_text,))
                conn.commit()
            flash(f'🗑️ 已成功刪除所有關於「{symptom_text}」的紀錄！', 'analyze_success')
        except Exception as e:
            print(f"⚠️ 刪除症狀失敗: {e}")
            flash('⚠️ 刪除失敗，請稍後再試。', 'analyze_error')
            
    return redirect(url_for('admin_page') + '#health')

# ==========================================
# 📢 後台管理：系統公告功能
# ==========================================
@app.route('/admin/add_announcement', methods=['POST'])
@login_required
def add_announcement():
    if not current_user.is_admin: return redirect(url_for('index'))
    content = request.form.get('content', '').strip()
    if content:
        with sqlite3.connect(HR_DB) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO announcements (content, is_active, created_at) VALUES (?, 0, ?)", 
                      (content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            announcement_id = c.lastrowid
            conn.commit()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'status': 'ok', 'message': '公告已建立', 'id': announcement_id, 'content': content})
        flash('✅ 公告已建立（預設為關閉狀態，請手動開啟）', 'analyze_success')
    return redirect(url_for('admin_page')+ '#health')

@app.route('/admin/toggle_announcement/<int:ann_id>', methods=['POST'])
@login_required
def toggle_announcement(ann_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        # 先將所有公告設為關閉 (確保同時只有一條公告在跑)
        c.execute("UPDATE announcements SET is_active = 0")
        # 開啟指定的公告
        c.execute("UPDATE announcements SET is_active = 1 WHERE id = ?", (ann_id,))
        conn.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'ok', 'message': '公告狀態已更新'})
    flash('📢 公告狀態已更新！', 'analyze_success')
    return redirect(url_for('admin_page')+ '#health')

@app.route('/admin/delete_announcement/<int:ann_id>', methods=['POST'])
@login_required
def delete_announcement(ann_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
        conn.commit()
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'status': 'ok', 'message': '公告已刪除'})
    flash('🗑️ 公告已刪除', 'analyze_success')
    return redirect(url_for('admin_page')+ '#health')

@app.route('/admin/get_reviews/<int:hospital_id>')
@login_required
def get_hospital_reviews(hospital_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403
        
    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        query = '''
            SELECT id, content, analyzed_sentiment, review_time, stored_at
            FROM reviews 
            WHERE hospital_id = ? 
            ORDER BY id DESC 
        '''
        cursor.execute(query, (hospital_id,))
        reviews = cursor.fetchall()
        
    data = []
    issue_source = []
    for r in reviews:
        issue_category = classify_negative_issue(r[1], r[2])
        data.append({
            'id': r[0],
            'content': r[1],
            'sentiment': r[2],
            'time': normalize_stored_review_time(r[3], r[4]),
            'issue_category': issue_category
        })

        issue_source.append({
            'text': r[1],
            'label': r[2]
        })

    pos_count = sum(1 for item in data if item['sentiment'] == 'POSITIVE')
    neg_count = sum(1 for item in data if item['sentiment'] == 'NEGATIVE')
    issue_summary = get_negative_issue_rows(issue_source)

    return jsonify({
        'reviews': data,
        'issue_summary': issue_summary,
        'suggestions': generate_improvement_suggestions(issue_summary, neg_count, len(data)),
        'representative_reviews': get_representative_reviews(data, issue_summary),
        'pos': pos_count,
        'neg': neg_count,
        'total': len(data)
    })

@app.route('/admin/get_issue_reviews/<path:issue_category>')
@login_required
def get_issue_reviews(issue_category):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        query = '''
            SELECT r.id, r.content, r.analyzed_sentiment, r.review_time, h.id, h.name, r.stored_at
            FROM reviews r
            JOIN hospitals h ON r.hospital_id = h.id
            WHERE r.analyzed_sentiment = 'NEGATIVE'
            ORDER BY r.id DESC
        '''
        cursor.execute(query)
        reviews = cursor.fetchall()

    data = []
    for r in reviews:
        detected_issue = classify_negative_issue(r[1], r[2])
        if detected_issue != issue_category:
            continue

        data.append({
            'id': r[0],
            'content': r[1],
            'sentiment': r[2],
            'time': normalize_stored_review_time(r[3], r[6]),
            'hospital_id': r[4],
            'hospital': r[5],
            'issue_category': detected_issue
        })

    return jsonify(data)

@app.route('/admin/delete_review/<int:review_id>', methods=['POST'])
@login_required
def delete_review(review_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
        
    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
        conn.commit()
    
    flash('評論已刪除', 'analyze_success')
    return redirect(url_for('admin_page'))

@app.route('/admin/export_csv/<int:hospital_id>')
@login_required
def export_hospital_csv(hospital_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))

    conn = sqlite3.connect(HR_DB)
    query = """
        SELECT r.review_time as '評論時間',
               r.stored_at as '爬取時間',
               r.content as '評論內容', 
               r.analyzed_sentiment as '情緒分析',
               h.name as '醫院名稱'
        FROM reviews r
        JOIN hospitals h ON r.hospital_id = h.id
        WHERE r.hospital_id = ?
        ORDER BY r.review_time DESC
    """
    df = pd.read_sql_query(query, conn, params=(hospital_id,))
    conn.close()

    if df.empty:
        flash('該醫院沒有評論可匯出', 'analyze_error')
        return redirect(url_for('admin_page'))

    df['評論時間'] = df.apply(
        lambda row: normalize_stored_review_time(row['評論時間'], row['爬取時間']),
        axis=1
    )
    df = df.drop(columns=['爬取時間'])

    df['負評原因'] = df.apply(
        lambda row: classify_negative_issue(row['評論內容'], row['情緒分析']),
        axis=1
    )
    df = df[['醫院名稱', '評論時間', '情緒分析', '負評原因', '評論內容']]

    output = io.BytesIO()
    df.to_csv(output, index=False, encoding='utf-8-sig')
    output.seek(0)
    hospital_name = df.iloc[0]['醫院名稱']
    filename = f"{hospital_name}_評論報表_{datetime.now().strftime('%Y%m%d')}.csv"
    from urllib.parse import quote
    filename = quote(filename)

    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename 
    )

@app.route('/admin/toggle_admin/<int:user_id>', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    
    if user_id == current_user.id:
        flash('您不能取消自己的管理員權限', 'analyze_error')
        return redirect(url_for('admin_page'))

    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("SELECT is_admin FROM users WHERE id=?", (user_id,))
        status = c.fetchone()[0]
        new_status = 0 if status == 1 else 1
        new_role = 'admin' if new_status == 1 else 'user'
        c.execute("""
            UPDATE users
            SET is_admin = ?, role = ?, approval_status = 'approved', hospital_id = NULL
            WHERE id = ?
        """, (new_status, new_role, user_id))
        conn.commit()
    
    msg = '已升級為管理員' if new_status == 1 else '已降級為一般會員'
    flash(f'權限變更成功：{msg}', 'analyze_success')
    return redirect(url_for('admin_page'))

@app.route('/admin/update_user_role/<int:user_id>', methods=['POST'])
@login_required
def update_user_role(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if user_id == current_user.id:
        flash('不能在這裡變更自己的角色', 'analyze_error')
        return redirect(url_for('admin_page') + '#users')

    role = request.form.get('role', 'user')
    approval_status = request.form.get('approval_status', 'approved')
    review_action = request.form.get('review_action', '').strip()
    hospital_id = request.form.get('hospital_id') or None
    admin_note = request.form.get('admin_note', '').strip()
    rejection_reason = request.form.get('rejection_reason', '').strip()
    custom_rejection_reason = request.form.get('custom_rejection_reason', '').strip()

    if role not in ['user', 'hospital', 'admin']:
        role = 'user'
    if approval_status not in ['pending', 'approved', 'rejected']:
        approval_status = 'pending' if role == 'hospital' else 'approved'

    is_admin_value = 1 if role == 'admin' else 0
    if role != 'hospital':
        hospital_id = None
        approval_status = 'approved'
    elif review_action == 'reject':
        approval_status = 'rejected'
    elif review_action == 'approve':
        approval_status = 'approved'
    elif approval_status == 'approved' and not hospital_id:
        # 先往下用申請醫院名稱自動比對資料庫醫院；找不到時後面會再提示。
        pass

    if role == 'hospital' and approval_status == 'rejected':
        hospital_id = None
        if rejection_reason == '其他':
            rejection_reason = custom_rejection_reason
        if not rejection_reason:
            flash('退回醫院帳號時，請選擇或填寫退回原因', 'analyze_error')
            return redirect(url_for('admin_page') + '#users')
    else:
        rejection_reason = None

    if approval_status == 'approved':
        rejection_reason = None

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("""
            SELECT id, username, requested_hospital_name, hospital_id, approval_status
            FROM users
            WHERE id = ?
        """, (user_id,))
        target_user = c.fetchone()

        notification_hospital_id = hospital_id
        if role == 'hospital' and not notification_hospital_id and target_user and target_user['requested_hospital_name']:
            c.execute("""
                SELECT id
                FROM hospitals
                WHERE REPLACE(name, '臺', '台') = REPLACE(?, '臺', '台')
                   OR REPLACE(?, '臺', '台') LIKE '%' || REPLACE(name, '臺', '台') || '%'
                   OR REPLACE(name, '臺', '台') LIKE '%' || REPLACE(?, '臺', '台') || '%'
                ORDER BY
                    CASE
                        WHEN REPLACE(name, '臺', '台') = REPLACE(?, '臺', '台') THEN 0
                        ELSE 1
                    END,
                    LENGTH(name) DESC
                LIMIT 1
            """, (
                target_user['requested_hospital_name'],
                target_user['requested_hospital_name'],
                target_user['requested_hospital_name'],
                target_user['requested_hospital_name']
            ))
            hospital_row = c.fetchone()
            if hospital_row:
                notification_hospital_id = hospital_row['id']
                if role == 'hospital' and approval_status == 'approved' and not hospital_id:
                    hospital_id = str(hospital_row['id'])
                    notification_hospital_id = hospital_id

        if role == 'hospital' and approval_status == 'approved' and not hospital_id:
            flash('找不到申請醫院可綁定，請先確認醫院名稱是否已收錄', 'analyze_error')
            return redirect(url_for('admin_page') + '#users')

        c.execute("""
            UPDATE users
            SET role = ?, is_admin = ?, approval_status = ?, hospital_id = ?, rejection_reason = ?
            WHERE id = ?
        """, (role, is_admin_value, approval_status, hospital_id, rejection_reason, user_id))

        if role == 'hospital':
            old_status = target_user['approval_status'] if target_user else None
            old_hospital_id = str(target_user['hospital_id']) if target_user and target_user['hospital_id'] else None
            new_hospital_id = str(hospital_id) if hospital_id else None
            if old_status != approval_status or old_hospital_id != new_hospital_id or approval_status in ['approved', 'rejected']:
                history_note = rejection_reason if approval_status == 'rejected' else (admin_note or None)
                c.execute("""
                    INSERT INTO hospital_user_review_history
                        (user_id, action, hospital_id, note, actor_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    user_id,
                    approval_status,
                    hospital_id,
                    history_note,
                    current_user.id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))

        if role == 'hospital' and approval_status in ['approved', 'rejected']:
            if approval_status == 'approved':
                title = '院方帳號審核通過'
                content = '您的院方帳號已審核通過，現在可以查看院方儀表板、評論分析與管理員提醒。'
                if admin_note:
                    content += f' 審核備註：{admin_note}'
            else:
                title = '院方帳號申請退回'
                content = f'您的院方帳號申請已被退回。退回原因：{rejection_reason}。請補齊資料後重新送審。'

            c.execute("""
                INSERT INTO hospital_notifications
                    (hospital_id, user_id, title, content, status, category, link_url, created_at, created_by)
                VALUES (?, ?, ?, ?, 'unread', 'account', ?, ?, ?)
            """, (
                notification_hospital_id,
                user_id,
                title,
                content,
                url_for('hospital_application_status'),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                current_user.id
            ))
        conn.commit()

    flash('使用者角色與醫院綁定已更新', 'analyze_success')
    return redirect(url_for('admin_page') + '#users')

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if user_id == current_user.id:
        flash('不能刪除目前登入中的管理員帳號', 'analyze_error')
        return redirect(url_for('admin_page') + '#users')

    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ? AND role = 'hospital'", (user_id,))
        deleted = c.rowcount
        conn.commit()

    flash('醫院帳號已刪除' if deleted else '找不到可刪除的醫院帳號', 'analyze_success' if deleted else 'analyze_error')
    return redirect(url_for('admin_page') + '#users')

# ==========================================
# 🏆 後台管理：得獎紀錄 (新增)
# ==========================================
@app.route('/admin/add_award', methods=['POST'])
@login_required
def add_award():
    if not current_user.is_admin: return redirect(url_for('index'))
    
    hospital_name = request.form.get('hospital_name', '').replace("臺", "台").strip()
    department = request.form.get('department', '').strip()
    award_name = request.form.get('award_name', '').strip()
    
    if hospital_name and department and award_name:
        try:
            with sqlite3.connect(HR_DB) as conn:
                c = conn.cursor()
                c.execute('''
                    INSERT INTO hospital_awards (hospital_name, department, award_name) 
                    VALUES (?, ?, ?)
                ''', (hospital_name, department, award_name))
                conn.commit()
            flash(f'✅ 已成功新增：{hospital_name} 的得獎紀錄！', 'analyze_success')
        except sqlite3.IntegrityError:
            flash(f'⚠️ 該獎項 ({hospital_name} - {award_name}) 已經存在囉！', 'analyze_error')
    else:
        flash('⚠️ 請填寫完整資訊！', 'analyze_error')
        
    return redirect(url_for('admin_page') + '#data')

@app.route('/admin/award_application/<int:application_id>/<action>', methods=['POST'])
@login_required
def review_award_application(application_id, action):
    if not current_user.is_admin:
        return redirect(url_for('index'))
    if action not in ['approve', 'reject']:
        flash('不支援的審核操作。', 'analyze_error')
        return redirect(url_for('admin_page') + '#data')

    admin_note = request.form.get('admin_note', '').strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hospital_award_applications WHERE id = ?", (application_id,))
        application = cursor.fetchone()

        if not application:
            flash('找不到這筆獎項/認證申請。', 'analyze_error')
            return redirect(url_for('admin_page') + '#data')

        if application['status'] != 'pending':
            flash('這筆申請已審核過。', 'analyze_error')
            return redirect(url_for('admin_page') + '#data')

        if action == 'approve':
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO hospital_awards (hospital_name, department, award_name)
                    VALUES (?, ?, ?)
                """, (
                    normalize_hospital_name(application['hospital_name']),
                    application['department'],
                    application['award_name']
                ))
                cursor.execute("""
                    UPDATE hospital_award_applications
                    SET status = 'approved', admin_note = ?, reviewed_at = ?, reviewed_by = ?
                    WHERE id = ?
                """, (admin_note, now, current_user.id, application_id))
                flash('已通過申請，該獎項/認證會顯示在醫院詳細檔案中。', 'analyze_success')
            except sqlite3.IntegrityError:
                flash('正式得獎紀錄已存在，申請已標記為通過。', 'analyze_success')
                cursor.execute("""
                    UPDATE hospital_award_applications
                    SET status = 'approved', admin_note = ?, reviewed_at = ?, reviewed_by = ?
                    WHERE id = ?
                """, (admin_note, now, current_user.id, application_id))
            notice_title = '獎項/認證申請已通過'
            notice_content = f"您申請的「{application['department']} - {application['award_name']}」已通過審核，將顯示在醫院詳細檔案中。"
            if admin_note:
                notice_content += f" 管理員備註：{admin_note}"
            history_action = 'approved'
            history_note = admin_note or '管理員通過申請'
        else:
            if not admin_note:
                admin_note = '申請資料不足或需補充佐證資料'
            cursor.execute("""
                UPDATE hospital_award_applications
                SET status = 'rejected', admin_note = ?, reviewed_at = ?, reviewed_by = ?
                WHERE id = ?
            """, (admin_note, now, current_user.id, application_id))
            notice_title = '獎項/認證申請已退回'
            notice_content = f"您申請的「{application['department']} - {application['award_name']}」已被退回。退回原因：{admin_note}。請修正後重新送出。"
            history_action = 'rejected'
            history_note = admin_note
            flash('已拒絕這筆獎項/認證申請。', 'analyze_success')

        log_award_application_history(
            cursor,
            application_id,
            history_action,
            history_note,
            application['proof_document'] if 'proof_document' in application.keys() else None,
            current_user.id
        )

        link_url = url_for(
            'hospital_profile',
            hospital_id=application['hospital_id'],
            _anchor=f"award-application-{application_id}"
        ) if application['hospital_id'] else url_for('hospital_notifications_page')
        cursor.execute("""
            INSERT INTO hospital_notifications
                (hospital_id, user_id, title, content, status, category, link_url, created_at, created_by)
            VALUES (?, ?, ?, ?, 'unread', 'award', ?, ?, ?)
        """, (
            application['hospital_id'],
            application['user_id'],
            notice_title,
            notice_content,
            link_url,
            now,
            current_user.id
        ))

        conn.commit()

    return redirect(url_for('admin_page') + '#data')

# ==========================================
# 🏆 後台管理：得獎紀錄 (連動刪除)
# ==========================================
@app.route('/admin/delete_award/<int:award_id>', methods=['POST'])
@login_required
def delete_award(award_id):
    if not current_user.is_admin: return redirect(url_for('index'))
    
    with sqlite3.connect(HR_DB) as conn:
        c = conn.cursor()
        
        # 1. 先查出這筆獎項的資料 (用來去申請表中尋找對應紀錄)
        c.execute("SELECT hospital_name, department, award_name FROM hospital_awards WHERE id = ?", (award_id,))
        award = c.fetchone()
        
        # 2. 刪除正式得獎紀錄
        c.execute("DELETE FROM hospital_awards WHERE id = ?", (award_id,))
        
        # 3. 終極清理：連同申請紀錄 (hospital_award_applications) 裡的「已通過」資料一起殺掉，確保資料庫不留痕跡
        if award:
            h_name, dept, a_name = award
            c.execute("""
                DELETE FROM hospital_award_applications 
                WHERE hospital_name = ? AND department = ? AND award_name = ? AND status = 'approved'
            """, (h_name, dept, a_name))
            
        conn.commit()
        
    flash('🗑️ 得獎紀錄與相關申請資料已徹底刪除', 'analyze_success')
    return redirect(url_for('admin_page') + '#data')

# ==========================================
# 🏥 醫院端：重新編輯並送出被退回的申請
# ==========================================
@app.route('/hospital/award_application/<int:app_id>/resubmit', methods=['POST'])
@login_required
def resubmit_award_application(app_id):
    # 1. 檢查目前登入的使用者是不是醫院帳號，且審核狀態是通過的
    if getattr(current_user, 'role', None) != 'hospital' or current_user.approval_status != 'approved':
        flash('無權限操作。', 'analyze_error')
        return redirect(url_for('index'))

    # 2. 接收前端表單傳過來的修正資料
    department = request.form.get('department', '').strip()
    award_name = request.form.get('award_name', '').strip()
    proof_filename = None

    if not department or not award_name:
        flash('請選擇科別並填寫獎項名稱。', 'analyze_error')
        return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

    if 'proof_document' in request.files:
        proof_filename, upload_error = save_proof_document(request.files['proof_document'])
        if upload_error:
            flash(upload_error, 'analyze_error')
            return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # 3. 安全檢查：確保這筆申請紀錄真的屬於這間醫院，而且目前的狀態確實是 'rejected'（被退回）
        cursor.execute("""
            SELECT id, proof_document FROM hospital_award_applications
            WHERE id = ? AND hospital_id = ? AND status = 'rejected'
        """, (app_id, current_user.hospital_id))
        application = cursor.fetchone()

        if not application:
            flash('找不到該退回紀錄或已無法編輯。', 'analyze_error')
            return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

        final_proof_document = proof_filename or application['proof_document']

        # 4. 更新資料庫：把狀態改回 'pending'（待審核），並把之前 admin 寫的退回原因（admin_note）清空
        cursor.execute("""
            UPDATE hospital_award_applications
            SET department = ?, award_name = ?, status = 'pending',
                admin_note = NULL, proof_document = ?, created_at = ?
            WHERE id = ?
        """, (
            department,
            award_name,
            final_proof_document,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            app_id
        ))
        log_award_application_history(
            cursor,
            app_id,
            'resubmitted',
            '院方修正後重新送審',
            final_proof_document,
            current_user.id
        )
        conn.commit()

    flash('✅ 獎項已修正並重新送出申請，請等待管理員審核。', 'analyze_success')
    return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

@app.route('/hospital/award_application/<int:app_id>/delete', methods=['POST'])
@login_required
def delete_award_application(app_id):
    if getattr(current_user, 'role', None) != 'hospital' or current_user.approval_status != 'approved':
        flash('無權限操作。', 'analyze_error')
        return redirect(url_for('index'))

    if not current_user.hospital_id:
        flash('找不到您的院方資料，無法刪除申請。', 'analyze_error')
        return redirect(url_for('index'))

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, status FROM hospital_award_applications
            WHERE id = ? AND hospital_id = ?
        """, (app_id, current_user.hospital_id))
        application = cursor.fetchone()

        if not application:
            flash('找不到該申請紀錄，或您沒有權限刪除。', 'analyze_error')
            return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

        if application['status'] != 'rejected':
            flash('只能刪除已退回的申請；審核中的申請請等待管理員處理。', 'analyze_error')
            return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

        cursor.execute(
            "DELETE FROM hospital_award_application_history WHERE application_id = ?",
            (app_id,)
        )
        cursor.execute(
            "DELETE FROM hospital_award_applications WHERE id = ? AND hospital_id = ?",
            (app_id, current_user.hospital_id)
        )
        conn.commit()

    flash('已刪除這筆退回申請。', 'analyze_success')
    return redirect(url_for('hospital_profile', hospital_id=current_user.hospital_id))

# ==========================================
# ⚔️ 醫院 PK 模式邏輯 (雙重比對 + 7 天快取防禦)
# ==========================================
def resolve_known_hospital_name(raw_name):
    name = (raw_name or '').replace("臺", "台").strip()
    if len(name) < 3:
        return None

    normalized_map = {
        hospital.replace("臺", "台").strip(): hospital
        for hospital in FLAT_HOSPITAL_LIST
        if hospital
    }
    if name in normalized_map:
        return normalized_map[name].replace("臺", "台").strip()

    try:
        with sqlite3.connect(HR_DB) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT name
                FROM hospitals
                WHERE REPLACE(name, '臺', '台') = ?
                   OR ? LIKE '%' || REPLACE(name, '臺', '台') || '%'
                   OR REPLACE(name, '臺', '台') LIKE '%' || ? || '%'
                ORDER BY
                    CASE WHEN REPLACE(name, '臺', '台') = ? THEN 0 ELSE 1 END,
                    LENGTH(name) DESC
                LIMIT 1
            """, (name, name, name, name))
            row = cursor.fetchone()
            if row:
                return row['name'].replace("臺", "台").strip()
    except Exception as e:
        print(f"⚠️ 醫院名稱解析失敗: {e}")

    return None

def load_pk_reviews_from_database(hospital_name, target_dept=None, limit=10, allow_general_fallback=True, max_age_days=None):
    place_id = hospital_name.lower().strip().replace(" ", "_")
    normalized_name = hospital_name.replace("臺", "台").strip()
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name
            FROM hospitals
            WHERE google_place_id = ?
               OR REPLACE(name, '臺', '台') = ?
               OR ? LIKE '%' || REPLACE(name, '臺', '台') || '%'
               OR REPLACE(name, '臺', '台') LIKE '%' || ? || '%'
            ORDER BY
                CASE WHEN google_place_id = ? OR REPLACE(name, '臺', '台') = ? THEN 0 ELSE 1 END,
                LENGTH(name) DESC
            LIMIT 1
        """, (place_id, normalized_name, normalized_name, normalized_name, place_id, normalized_name))
        hospital = cursor.fetchone()
        if not hospital:
            print(f"  ⚠️ PK fallback 找不到資料庫醫院：{hospital_name}")
            return [], 0, 0, None

        hospital_id = hospital['id']
        print(f"  👉 PK fallback 使用資料庫醫院：{hospital['name']} (ID: {hospital_id})")
        query_params = [hospital_id]
        department_filter = ""
        cache_filter = ""
        fallback_used = None
        if target_dept:
            department_filter = "AND department = ?"
            query_params.append(target_dept)
        if max_age_days:
            cache_cutoff = (datetime.now() - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
            cache_filter = "AND stored_at IS NOT NULL AND stored_at >= ?"
            query_params.append(cache_cutoff)

        cursor.execute(f"""
            SELECT id, content, analyzed_sentiment, review_time, stored_at, department
            FROM reviews
            WHERE hospital_id = ?
              {department_filter}
              {cache_filter}
            ORDER BY
                CASE WHEN stored_at IS NULL THEN 1 ELSE 0 END,
                stored_at DESC,
                id DESC
            LIMIT ?
        """, (*query_params, limit))
        rows = cursor.fetchall()

        if target_dept and allow_general_fallback and len(rows) < limit:
            fallback_params = [hospital_id]
            fallback_cache_filter = ""
            if max_age_days:
                fallback_cache_filter = "AND stored_at IS NOT NULL AND stored_at >= ?"
                fallback_params.append(cache_cutoff)
            used_review_ids = [row['id'] for row in rows]
            exclude_filter = ""
            if used_review_ids:
                exclude_filter = f"AND id NOT IN ({','.join(['?'] * len(used_review_ids))})"
                fallback_params.extend(used_review_ids)
            remaining_limit = limit - len(rows)
            cursor.execute("""
                SELECT id, content, analyzed_sentiment, review_time, stored_at, department
                FROM reviews
                WHERE hospital_id = ?
                  """ + fallback_cache_filter + """
                  """ + exclude_filter + """
                ORDER BY
                    CASE
                        WHEN department IS NULL OR department = '' OR department = '綜合/未提及' THEN 0
                        ELSE 1
                    END,
                    CASE WHEN stored_at IS NULL THEN 1 ELSE 0 END,
                    stored_at DESC,
                    id DESC
                LIMIT ?
            """, (*fallback_params, remaining_limit))
            general_rows = cursor.fetchall()
            if general_rows:
                rows = list(rows) + list(general_rows)
                fallback_used = 'department_plus_general_reviews'
            elif not rows:
                fallback_used = 'general_reviews'

    sentiments = []
    pos_count = 0
    neg_count = 0
    for row in rows:
        sentiment = row['analyzed_sentiment'] or 'NEUTRAL'
        sentiments.append({
            'text': row['content'],
            'time': normalize_stored_review_time(row['review_time'], row['stored_at']),
            'label': sentiment,
            'emotion': sentiment,
            'score': 100.0,
            'department': row['department'],
            'fallback_source': fallback_used or 'database_reviews'
        })
        if sentiment == 'POSITIVE':
            pos_count += 1
        elif sentiment == 'NEGATIVE':
            neg_count += 1

    return sentiments, pos_count, neg_count, fallback_used or ('database_reviews' if sentiments else None)

def fallback_pk_stats_from_database(hospital_name, target_dept=None, reason='PK 爬蟲失敗'):
    sentiments, pos_count, neg_count, fallback_source = load_pk_reviews_from_database(
        hospital_name,
        target_dept=target_dept,
        limit=10,
        allow_general_fallback=True
    )
    if sentiments:
        print(f"  ✅ {reason}，已改用資料庫一般評論 fallback：{fallback_source}，共 {len(sentiments)} 筆。")
        return sentiments, pos_count, neg_count
    print(f"  ❌ {reason}，但資料庫也找不到可用的一般評論。")
    return [], 0, 0

def build_pk_stats_from_reviews(hospital_name, sentiments, pos_count=None, neg_count=None):
    pos_count = sum(1 for item in sentiments if item.get('label') == 'POSITIVE') if pos_count is None else pos_count
    neg_count = sum(1 for item in sentiments if item.get('label') == 'NEGATIVE') if neg_count is None else neg_count
    total = pos_count + neg_count
    total_raw_points = 0

    for item in sentiments:
        confidence = item.get('score', 100.0)
        if item.get('label') == 'POSITIVE':
            total_raw_points += confidence
        elif item.get('label') == 'NEGATIVE':
            total_raw_points += (100 - confidence)

    final_score = round((total_raw_points / total) / 10, 1) if total else 0.0
    return {
        'name': hospital_name,
        'pos': pos_count,
        'neg': neg_count,
        'total': total,
        'avg_score': final_score,
        'reviews': sentiments
    }

def get_hospital_stats(hospital_name, target_dept=None):
    print(f"\n[{hospital_name}] 🕵️‍♂️ PK 檢查 7 天快取...")
    sentiments = []
    pos_count = 0
    neg_count = 0

    # ==========================================
    # ⚡ 步驟 1：優先使用 7 天內資料庫快取
    # ==========================================
    cached_sentiments, cached_pos, cached_neg, cache_source = load_pk_reviews_from_database(
        hospital_name,
        target_dept=target_dept,
        limit=10,
        allow_general_fallback=True,
        max_age_days=7
    )
    if cached_sentiments:
        print(f"⚡ PK 命中 7 天內快取：{hospital_name}，來源 {cache_source}，共 {len(cached_sentiments)} 筆，直接載入。")
        return build_pk_stats_from_reviews(hospital_name, cached_sentiments, cached_pos, cached_neg)

    # ==========================================
    # 🐌 步驟 2：快取沒有命中，才啟動爬蟲抓 Google 評論
    # ==========================================
    print(f"🐌 PK 沒有 7 天內快取，啟動爬蟲抓取：{hospital_name}")
    raw_reviews = None
    try:
        raw_reviews = scrape_google_reviews(hospital_name, max_reviews=10, target_dept=target_dept)
    except Exception as scrape_err:
        print(f"⚠️ PK 爬蟲失敗，準備改用資料庫一般評論：{scrape_err}")

    # ==========================================
    # 🗂️ 步驟 3：爬蟲失敗 / 抓不到 / 分析無結果，才改用資料庫既有一般評論
    # ==========================================
    if not raw_reviews:
        sentiments, pos_count, neg_count = fallback_pk_stats_from_database(
            hospital_name,
            target_dept=target_dept,
            reason='PK 沒有抓到 Google 評論'
        )
        if not sentiments:
            return None
    else:
        try:
            sentiments, pos_count, neg_count = analyze_reviews(raw_reviews)
        except Exception as analyze_err:
            print(f"⚠️ PK 情緒分析失敗，準備改用資料庫一般評論：{analyze_err}")
            sentiments, pos_count, neg_count = [], 0, 0
        
        if not sentiments:
            sentiments, pos_count, neg_count = fallback_pk_stats_from_database(
                hospital_name,
                target_dept=target_dept,
                reason='PK 情緒分析無結果'
            )
            if not sentiments:
                return None

        # 將新爬取的資料寫入資料庫
        try:
            if target_dept:
                for s in sentiments:
                    s['department'] = target_dept
            new_reviews_count, updated_reviews_count = save_batch_sentiments_for_hospital(hospital_name, sentiments)
            print(f"💾 PK 模式儲存：成功存入 {new_reviews_count} 筆新評論！(並自動校正了 {updated_reviews_count} 筆舊資料的科別)")
        except Exception as e:
            print(f"⚠️ PK 儲存資料庫失敗: {e}")
            
    # ==========================================
    # 🏆 步驟 4：結算分數
    # ==========================================
    total = pos_count + neg_count
    total_raw_points = 0  
    
    for s in sentiments:
        confidence = s.get('score', 100.0) 
        if s['label'] == 'POSITIVE':
            total_raw_points += confidence
        else:
            total_raw_points += (100 - confidence)

    final_score = 0.0
    if total > 0:
        avg_100 = total_raw_points / total
        final_score = round(avg_100 / 10, 1)

    return {
        'name': hospital_name,
        'pos': pos_count,
        'neg': neg_count,
        'total': total,
        'avg_score': final_score, 
        'reviews': sentiments     
    }

def build_pk_comparison(h1, h2):
    def rate(stats, key):
        total = stats.get('total') or 0
        return round((stats.get(key) or 0) / total * 100) if total else 0

    def issue_count(stats, category):
        return sum(
            1 for review in stats.get('reviews', [])
            if review.get('label') == 'NEGATIVE'
            and classify_negative_issue(review.get('text', ''), review.get('label')) == category
        )

    def issue_score(count):
        if count == 0:
            return None
        return max(0, 10 - count * 2)

    h1_issues = get_negative_issue_rows(h1.get('reviews', []), limit=3)
    h2_issues = get_negative_issue_rows(h2.get('reviews', []), limit=3)
    dimensions = []
    for category in ["等候時間", "醫護態度", "掛號流程", "醫療溝通", "環境設備"]:
        h1_count = issue_count(h1, category)
        h2_count = issue_count(h2, category)
        if h1_count == 0 or h2_count == 0:
            better = '資料不足'
        elif h1_count < h2_count:
            better = h1['name']
        elif h2_count < h1_count:
            better = h2['name']
        else:
            better = '相近'
        dimensions.append({
            'category': category,
            'h1_count': h1_count,
            'h2_count': h2_count,
            'h1_score': issue_score(h1_count),
            'h2_score': issue_score(h2_count),
            'better': better
        })

    scenario_tips = []
    if h1['avg_score'] > h2['avg_score']:
        scenario_tips.append(f"若重視整體滿意度，可優先參考 {h1['name']}。")
    elif h2['avg_score'] > h1['avg_score']:
        scenario_tips.append(f"若重視整體滿意度，可優先參考 {h2['name']}。")
    else:
        scenario_tips.append("兩家整體滿意度接近，建議改看特定需求面向。")

    wait_dimension = next((item for item in dimensions if item['category'] == '等候時間'), None)
    if wait_dimension and wait_dimension['better'] not in ('相近', '資料不足'):
        scenario_tips.append(f"若在意等候時間，目前 {wait_dimension['better']} 的相關抱怨較少。")

    attitude_dimension = next((item for item in dimensions if item['category'] == '醫護態度'), None)
    if attitude_dimension and attitude_dimension['better'] not in ('相近', '資料不足'):
        scenario_tips.append(f"若重視服務互動與態度，可多參考 {attitude_dimension['better']}。")

    return {
        'h1_positive_rate': rate(h1, 'pos'),
        'h2_positive_rate': rate(h2, 'pos'),
        'h1_negative_rate': rate(h1, 'neg'),
        'h2_negative_rate': rate(h2, 'neg'),
        'h1_top_issue': h1_issues[0]['issue_category'] if h1_issues else '無明顯負評原因',
        'h2_top_issue': h2_issues[0]['issue_category'] if h2_issues else '無明顯負評原因',
        'dimensions': dimensions,
        'scenario_tips': scenario_tips
    }

# ==========================================
# 🏆 科別英雄榜 (Ranking) 邏輯與路由
# ==========================================
def get_top_hospitals_by_dept(department_name, city=None):
    """取得特定科別與地區的醫院排行 (嚴格區分：已爬取有排名 vs 未爬取無排名)"""
    def build_recommendation_score(has_award, pos_rate, total_reviews, city_match):
        award_points = 25 if has_award else 0
        sentiment_points = min(max(pos_rate, 0), 100) * 0.45
        review_points = min(total_reviews, 50) / 50 * 25
        city_points = 5 if city_match else 0
        return round(award_points + sentiment_points + review_points + city_points, 1)

    def build_recommendation_explanation(hospital_name, department_name, has_award, award_count, pos_rate, total_reviews, city_match, selected_city):
        if total_reviews > 0:
            review_text = f"此醫院在{department_name}相關評論中共有 {total_reviews} 則評論，AI 情緒分析顯示正面評論比例為 {pos_rate}%。"
        else:
            review_text = f"此醫院目前尚未累積{department_name}相關評論，因此評論情緒分數仍不足。"

        award_text = (
            f"此外，該醫院具有 {award_count} 筆{department_name}相關獎項或認證，系統會提高推薦優先度。"
            if has_award else
            f"目前尚未找到該醫院的{department_name}相關獎項或認證。"
        )

        city_text = (
            f"此醫院符合使用者選擇的「{selected_city}」篩選條件。"
            if selected_city and city_match else
            "本次未指定縣市，因此未額外套用地區加分。"
        )

        return (
            f"{review_text}{award_text}{city_text}"
            "此排名主要依據評論情緒分析、科別評論數、獎項資料與縣市篩選條件綜合評估。"
        )
    
    # 1. 準備該城市的醫院名稱清單 (來自 Excel 官方名單)
    city_hospitals_excel = set()
    if city:
        alt_city = city.replace("台", "臺") if "台" in city else city.replace("臺", "台")
        for region_dict in GLOBAL_HOSPITALS_DATA.values():
            for c_name, h_list in region_dict.items():
                if city in c_name or alt_city in c_name:
                    for h in h_list:
                        # 🌟 強制統一：把 Excel 名單裡的「臺」全部轉成「台」
                        city_hospitals_excel.add(h.replace("臺", "台"))

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 2. 取得該科別的權威得獎名單
        cursor.execute("SELECT hospital_name, award_name FROM hospital_awards WHERE department = ?", (department_name,))
        awards_data = {}
        for row in cursor.fetchall():
            # 🌟 強制統一：處理舊得獎紀錄裡的「臺」
            h_name = row['hospital_name'].replace("臺", "台")
            if h_name not in awards_data:
                awards_data[h_name] = []
            awards_data[h_name].append(row['award_name'])

        # 3. 取得該科別的網友評價真實數據
        cursor.execute('''
            SELECT 
                h.name as hospital_name,
                h.address,
                COUNT(r.id) as total_reviews,
                SUM(CASE WHEN r.analyzed_sentiment = 'POSITIVE' THEN 1 ELSE 0 END) as pos_reviews
            FROM reviews r
            JOIN hospitals h ON r.hospital_id = h.id
            WHERE r.department = ?
            GROUP BY h.id
        ''', (department_name,))
        
        reviews_data = {}
        for row in cursor.fetchall():
            # 🌟 強制統一：處理舊醫院紀錄裡的「臺」
            h_name = row['hospital_name'].replace("臺", "台")
            
            # 如果因為統一字體，導致兩家醫院被合併了，就把數據加起來！
            if h_name in reviews_data:
                reviews_data[h_name]['total'] += row['total_reviews']
                reviews_data[h_name]['pos'] += row['pos_reviews']
                reviews_data[h_name]['rate'] = round((reviews_data[h_name]['pos'] / reviews_data[h_name]['total']) * 100, 1) if reviews_data[h_name]['total'] > 0 else 0
            else:
                reviews_data[h_name] = {
                    'total': row['total_reviews'],
                    'pos': row['pos_reviews'],
                    'rate': round((row['pos_reviews'] / row['total_reviews']) * 100, 1) if row['total_reviews'] > 0 else 0,
                    'address': row['address']
                }

        # 4. 智慧合併與地區模糊比對過濾
        all_hospitals = set(list(awards_data.keys()) + list(reviews_data.keys()) + list(city_hospitals_excel))
        
        ranked_list = []      
        unranked_list = []    
        
        for h in all_hospitals:
            stats = reviews_data.get(h, None)
            
            if stats:
                address = stats['address']
                total_reviews = stats['total']
                pos_rate = stats['rate']
            else:
                address = '系統尚未爬取評論，等待啟用中...'
                total_reviews = 0
                pos_rate = 0.0
            
            if city:
                alt_city = city.replace("台", "臺") if "台" in city else city.replace("臺", "台")
                short_city = city.replace("市", "").replace("縣", "")
                alt_short = alt_city.replace("市", "").replace("縣", "")
                
                name_has_city = (short_city in h or alt_short in h)
                address_has_city = address and (short_city in address or alt_short in address)
                
                excel_matched = False
                if h in city_hospitals_excel:
                    excel_matched = True
                else:
                    import re
                    clean_h = re.sub(r'(醫療財團法人|衛生福利部|醫療社團法人|醫院|診所|紀念|綜合|國立|大學|附設|市立)', '', h).strip()
                    clean_h = clean_h.replace("台大", "臺灣大學").replace("臺大", "臺灣大學")
                    
                    if len(clean_h) >= 2:
                        for excel_h in city_hospitals_excel:
                            if clean_h in excel_h:
                                excel_matched = True
                                break
                
                if not (name_has_city or address_has_city or excel_matched):
                    continue 
                city_match = True
            else:
                city_match = True

            has_award = h in awards_data
            award_count = len(awards_data.get(h, []))
            recommendation_score = build_recommendation_score(
                has_award=has_award,
                pos_rate=pos_rate,
                total_reviews=total_reviews,
                city_match=city_match
            )
            hospital_item = {
                'name': h,
                'address': address,
                'awards': awards_data.get(h, []),
                'has_award': has_award,
                'total_reviews': total_reviews,
                'pos_rate': pos_rate,
                'recommendation_score': recommendation_score,
                'explanation': build_recommendation_explanation(
                    hospital_name=h,
                    department_name=department_name,
                    has_award=has_award,
                    award_count=award_count,
                    pos_rate=pos_rate,
                    total_reviews=total_reviews,
                    city_match=city_match,
                    selected_city=city
                ),
                'sources': [
                    'Google Maps 評論文字',
                    'AI 情緒分析結果 analyzed_sentiment',
                    '評論科別辨識結果 department',
                    '醫院獎項 / 認證資料 hospital_awards',
                    '醫院地址與縣市篩選資料'
                ],
                'ranking_factors': {
                    'has_award': has_award,
                    'positive_rate': pos_rate,
                    'total_reviews': total_reviews,
                    'award_count': award_count,
                    'city_match': city_match
                }
            }
            
            if has_award or total_reviews > 0:
                ranked_list.append(hospital_item)
            else:
                unranked_list.append(hospital_item)

        # 5. 【有排名醫院】排序邏輯
        ranked_list.sort(key=lambda x: (x['recommendation_score'], x['has_award'], x['pos_rate'], x['total_reviews']), reverse=True)
        
        # 6. 【未排名醫院】排序邏輯
        unranked_list.sort(key=lambda x: x['name'])
        
        # 7. 🌟 幫有排名的醫院加上明確的 'rank_num'
        final_results = []
        current_rank = 1
        
        for i, h_item in enumerate(ranked_list):
            if i > 0:
                prev_item = ranked_list[i-1]
                if (h_item['recommendation_score'] == prev_item['recommendation_score'] and
                    h_item['has_award'] == prev_item['has_award'] and 
                    h_item['pos_rate'] == prev_item['pos_rate'] and 
                    h_item['total_reviews'] == prev_item['total_reviews']):
                    h_item['rank_num'] = current_rank
                else:
                    current_rank = i + 1
                    h_item['rank_num'] = current_rank
            else:
                h_item['rank_num'] = 1
                
            final_results.append(h_item)
            
        # 8. 🌟 將未排名的醫院接在後面
        for h_item in unranked_list:
            h_item['rank_num'] = None
            final_results.append(h_item)

        return final_results

@app.route('/ranking', methods=['GET', 'POST'])
@login_required
def ranking_page():
    # 直接指定台灣標準地理排序 (北 -> 中 -> 南 -> 東 -> 離島)
    cities = [
        "基隆市", "台北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣",
        "台中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "台南市",
        "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "台東縣", "澎湖縣", "金門縣", "連江縣"
    ]
    
    departments = list(DEPARTMENT_KEYWORDS.keys()) 
    selected_dept = request.form.get('department', "")
    selected_city = request.form.get('city', "")
    
    top_hospitals = []
    
    # 👇 新增：用來存放 PK 結果的變數
    h1_stats = None
    h2_stats = None
    show_pk_result = False
    pk_comparison = None
    ai_pk_summary = ""

    if request.method == 'POST':
        action_type = request.form.get('action_type', 'search')
        
        # 情況 A：使用者點擊「搜尋前段班」
        if action_type == 'search':
            if selected_dept:
                top_hospitals = get_top_hospitals_by_dept(selected_dept, city=selected_city)
                
        # 情況 B：使用者勾選了兩家醫院，點擊「進入 PK 對決」
        elif action_type == 'run_pk':
            h1_name = request.form.get('hospital1')
            h2_name = request.form.get('hospital2')
            
            if h1_name and h2_name:
                h1_name = resolve_known_hospital_name(h1_name)
                h2_name = resolve_known_hospital_name(h2_name)
                if not h1_name or not h2_name:
                    flash('請從推薦名單中選擇兩家已收錄醫院，不要輸入科別或單字關鍵字。', 'analyze_error')
                    return redirect(url_for('ranking_page'))
                
                # 啟動你寫好的神級爬蟲與快取過濾機制！
                with scrape_lock:
                    try:
                        h1_stats = get_hospital_stats(h1_name, target_dept=selected_dept)
                    except Exception as err:
                        print(f"⚠️ 科別推薦 PK 取得 {h1_name} 統計失敗，直接改用一般評論：{err}")
                        h1_reviews, h1_pos, h1_neg = fallback_pk_stats_from_database(h1_name, selected_dept, 'ranking route 例外')
                        h1_stats = build_pk_stats_from_reviews(h1_name, h1_reviews, h1_pos, h1_neg) if h1_reviews else None

                    try:
                        h2_stats = get_hospital_stats(h2_name, target_dept=selected_dept)
                    except Exception as err:
                        print(f"⚠️ 科別推薦 PK 取得 {h2_name} 統計失敗，直接改用一般評論：{err}")
                        h2_reviews, h2_pos, h2_neg = fallback_pk_stats_from_database(h2_name, selected_dept, 'ranking route 例外')
                        h2_stats = build_pk_stats_from_reviews(h2_name, h2_reviews, h2_pos, h2_neg) if h2_reviews else None

                if h1_stats and h2_stats:
                    pk_comparison = build_pk_comparison(h1_stats, h2_stats)
                    ai_pk_summary = generate_pk_ai_summary(h1_name, h2_name, h1_stats, h2_stats, selected_dept)
                
                show_pk_result = True

    return render_template('ranking.html', 
                           departments=departments, 
                           cities=cities,
                           selected_dept=selected_dept, 
                           selected_city=selected_city,
                           top_hospitals=top_hospitals,
                           h1=h1_stats,
                           h2=h2_stats,
                           pk_comparison=pk_comparison,
                           ai_pk_summary=ai_pk_summary,
                           show_pk_result=show_pk_result)

# ==========================================
# 🚀 隱藏版大絕招：背景批次自動爬蟲
# ==========================================
def create_batch_job_record(hospital_names, start_index, max_reviews, rest_every, rest_seconds, retry_of_job_id=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO batch_crawl_jobs
                (status, start_index, hospital_count, max_reviews, rest_every, rest_seconds,
                 total, retry_of_job_id, requested_hospitals, message, created_at)
            VALUES ('queued', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            start_index,
            len(hospital_names),
            max_reviews,
            rest_every,
            rest_seconds,
            len(hospital_names),
            retry_of_job_id,
            json.dumps(hospital_names, ensure_ascii=False),
            '等待批次爬蟲啟動',
            now
        ))
        job_id = cursor.lastrowid
        cursor.executemany("""
            INSERT INTO batch_crawl_job_items(job_id, hospital_name, status)
            VALUES (?, ?, 'pending')
        """, [(job_id, name) for name in hospital_names])
        conn.commit()
    return job_id

def update_batch_job_record(job_id, **kwargs):
    if not job_id or not kwargs:
        return
    allowed = {
        'status', 'processed', 'success', 'skipped', 'failed', 'new_reviews',
        'refreshed_reviews', 'risk_count', 'top_issue', 'message', 'started_at',
        'finished_at'
    }
    fields = [key for key in kwargs if key in allowed]
    if not fields:
        return
    values = [kwargs[key] for key in fields]
    values.append(job_id)
    with sqlite3.connect(HR_DB) as conn:
        conn.execute(
            f"UPDATE batch_crawl_jobs SET {', '.join([field + ' = ?' for field in fields])} WHERE id = ?",
            values
        )
        conn.commit()

def update_batch_job_item(job_id, hospital_name, **kwargs):
    if not job_id or not hospital_name:
        return
    allowed = {
        'status', 'new_reviews', 'refreshed_reviews', 'positive_reviews',
        'negative_reviews', 'total_reviews', 'top_issue', 'error_message',
        'failure_category', 'review_samples', 'started_at', 'finished_at'
    }
    fields = [key for key in kwargs if key in allowed]
    if not fields:
        return
    values = [kwargs[key] for key in fields]
    values.extend([job_id, hospital_name])
    with sqlite3.connect(HR_DB) as conn:
        conn.execute(
            f"UPDATE batch_crawl_job_items SET {', '.join([field + ' = ?' for field in fields])} WHERE job_id = ? AND hospital_name = ?",
            values
        )
        conn.commit()

def refresh_batch_job_summary(job_id):
    if not job_id:
        return
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status IN ('success', 'skipped', 'failed') THEN 1 ELSE 0 END) AS processed,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success,
                SUM(CASE WHEN status = 'skipped' THEN 1 ELSE 0 END) AS skipped,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed,
                SUM(new_reviews) AS new_reviews,
                SUM(refreshed_reviews) AS refreshed_reviews,
                SUM(CASE WHEN negative_reviews >= 3 OR (total_reviews >= 5 AND negative_reviews * 1.0 / total_reviews >= 0.5) THEN 1 ELSE 0 END) AS risk_count
            FROM batch_crawl_job_items
            WHERE job_id = ?
        """, (job_id,))
        row = cursor.fetchone()
        cursor.execute("""
            SELECT top_issue, COUNT(*) AS count
            FROM batch_crawl_job_items
            WHERE job_id = ? AND top_issue IS NOT NULL AND top_issue != ''
            GROUP BY top_issue
            ORDER BY count DESC
            LIMIT 1
        """, (job_id,))
        issue_row = cursor.fetchone()
        conn.execute("""
            UPDATE batch_crawl_jobs
            SET total = ?, processed = ?, success = ?, skipped = ?, failed = ?,
                new_reviews = ?, refreshed_reviews = ?, risk_count = ?, top_issue = ?
            WHERE id = ?
        """, (
            row['total'] or 0,
            row['processed'] or 0,
            row['success'] or 0,
            row['skipped'] or 0,
            row['failed'] or 0,
            row['new_reviews'] or 0,
            row['refreshed_reviews'] or 0,
            row['risk_count'] or 0,
            issue_row['top_issue'] if issue_row else None,
            job_id
        ))
        conn.commit()

def normalize_review_for_dedup(text):
    clean = remove_emojis(text or '')
    clean = re.sub(r"\s+", "", clean)
    clean = re.sub(r"[，。！？、,.!?;；:：\"'「」『』（）()\\[\\]【】]", "", clean)
    return clean.lower()

def find_similar_existing_review(cursor, hospital_id, content, threshold=0.94):
    normalized_content = normalize_review_for_dedup(content)
    if not normalized_content:
        return None

    cursor.execute("""
        SELECT id, content
        FROM reviews
        WHERE hospital_id = ?
        ORDER BY id DESC
        LIMIT 300
    """, (hospital_id,))
    for row in cursor.fetchall():
        review_id = row[0]
        existing_content = row[1] or ''
        normalized_existing = normalize_review_for_dedup(existing_content)
        if not normalized_existing:
            continue
        if normalized_existing == normalized_content:
            return review_id
        if min(len(normalized_existing), len(normalized_content)) < 12:
            continue
        similarity = SequenceMatcher(None, normalized_existing, normalized_content).ratio()
        if similarity >= threshold:
            return review_id
    return None

def classify_crawl_failure(error_text):
    text = str(error_text or '')
    lowered = text.lower()
    if not text:
        return '未分類'
    if '未抓到評論' in text or 'no reviews' in lowered:
        return '找不到評論'
    if 'timeout' in lowered or 'timed out' in lowered or '載入' in text:
        return '頁面載入逾時'
    if 'webdriver' in lowered or 'selenium' in lowered or 'chrome' in lowered:
        return '瀏覽器爬蟲錯誤'
    if 'database' in lowered or 'sqlite' in lowered or '資料庫' in text:
        return '資料庫寫入失敗'
    if '分析' in text or 'model' in lowered or 'transformers' in lowered:
        return '情緒分析失敗'
    if '停止' in text:
        return '手動停止'
    return '其他錯誤'

def save_batch_sentiments_for_hospital(hospital_name, sentiments):
    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        place_id = hospital_name.lower().strip().replace(" ", "_")
        excel_address = get_hospital_address_from_excel(hospital_name)
        address = excel_address or hospital_name
        cursor.execute("SELECT id FROM hospitals WHERE google_place_id = ? OR name = ?", (place_id, hospital_name))
        existing = cursor.fetchone()

        if existing:
            hospital_id = existing[0]
        else:
            cursor.execute("""
                INSERT INTO hospitals (name, address, google_place_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (hospital_name, address, place_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            hospital_id = cursor.lastrowid

        new_reviews = 0
        refreshed_reviews = 0
        for s in sentiments:
            existing_review_id = find_similar_existing_review(cursor, hospital_id, s['text'])
            stored_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if not existing_review_id:
                cursor.execute("""
                    INSERT INTO reviews
                        (hospital_id, author, content, rating, review_time, analyzed_sentiment, stored_at, department)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (hospital_id, 'Unknown', s['text'], None, s['time'], s['label'], stored_at, s['department']))
                new_reviews += 1
            else:
                cursor.execute("""
                    UPDATE reviews
                    SET review_time = ?, analyzed_sentiment = ?, stored_at = ?, department = ?
                    WHERE id = ?
                """, (s['time'], s['label'], stored_at, s['department'], existing_review_id))
                refreshed_reviews += 1
        conn.commit()
    return new_reviews, refreshed_reviews

def append_batch_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    with batch_crawl_status_lock:
        logs = batch_crawl_status.setdefault('recent_logs', [])
        logs.insert(0, {'time': timestamp, 'message': message})
        del logs[8:]
        batch_crawl_status['message'] = message
        batch_crawl_status['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def update_batch_status(**kwargs):
    with batch_crawl_status_lock:
        batch_crawl_status.update(kwargs)
        started_at = batch_crawl_status.get('started_at')
        if started_at:
            elapsed = max((datetime.now() - started_at).total_seconds(), 0)
            processed = batch_crawl_status.get('processed', 0) or 0
            total = batch_crawl_status.get('total', 0) or 0
            current_review_count = batch_crawl_status.get('current_review_count', 0) or 0
            target_review_count = batch_crawl_status.get('target_review_count', 0) or 0
            partial_progress = min(current_review_count / target_review_count, 0.95) if target_review_count else 0
            effective_processed = processed + partial_progress
            batch_crawl_status['elapsed_seconds'] = round(elapsed)
            if batch_crawl_status.get('running') and effective_processed > 0 and total > processed:
                avg_seconds = elapsed / effective_processed
                batch_crawl_status['estimated_remaining_seconds'] = round(avg_seconds * max(total - effective_processed, 0))
            elif batch_crawl_status.get('running') and effective_processed == 0:
                batch_crawl_status['estimated_remaining_seconds'] = None
            else:
                batch_crawl_status['estimated_remaining_seconds'] = 0
        batch_crawl_status['last_updated'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def mark_batch_job_queued(job_id, hospital_names, review_limit, message='批次爬蟲已排隊，正在啟動背景任務...'):
    update_batch_status(
        running=True,
        status='queued',
        stop_requested=False,
        pause_requested=False,
        current_job_id=job_id,
        started_at=datetime.now(),
        finished_at=None,
        total=len(hospital_names),
        current_index=0,
        current_hospital='',
        processed=0,
        success=0,
        failed=0,
        skipped=0,
        new_reviews=0,
        refreshed_reviews=0,
        current_review_count=0,
        target_review_count=review_limit,
        scroll_round=0,
        phase='queued',
        elapsed_seconds=0,
        estimated_remaining_seconds=None,
        last_error='',
        recent_logs=[],
        message=message
    )

def get_batch_status_snapshot():
    with batch_crawl_status_lock:
        snapshot = dict(batch_crawl_status)
        snapshot['recent_logs'] = list(batch_crawl_status.get('recent_logs', []))
        started_at = snapshot.get('started_at')
        finished_at = snapshot.get('finished_at')
        if started_at:
            end_time = finished_at or datetime.now()
            elapsed = max((end_time - started_at).total_seconds(), 0)
            processed = snapshot.get('processed', 0) or 0
            total = snapshot.get('total', 0) or 0
            current_review_count = snapshot.get('current_review_count', 0) or 0
            target_review_count = snapshot.get('target_review_count', 0) or 0
            partial_progress = min(current_review_count / target_review_count, 0.95) if target_review_count else 0
            effective_processed = processed + partial_progress
            snapshot['elapsed_seconds'] = round(elapsed)
            if snapshot.get('running') and effective_processed > 0 and total > processed:
                avg_seconds = elapsed / effective_processed
                snapshot['estimated_remaining_seconds'] = round(avg_seconds * max(total - effective_processed, 0))
            elif snapshot.get('running') and effective_processed == 0:
                snapshot['estimated_remaining_seconds'] = None
            elif not snapshot.get('running'):
                snapshot['estimated_remaining_seconds'] = 0
        snapshot['started_at'] = started_at.strftime("%Y-%m-%d %H:%M:%S") if started_at else None
        snapshot['finished_at'] = finished_at.strftime("%Y-%m-%d %H:%M:%S") if finished_at else None
        total = snapshot.get('total', 0) or 0
        processed = snapshot.get('processed', 0) or 0
        current_review_count = snapshot.get('current_review_count', 0) or 0
        target_review_count = snapshot.get('target_review_count', 0) or 0
        partial_progress = min(current_review_count / target_review_count, 0.95) if target_review_count else 0
        snapshot['percent'] = min(round((processed + partial_progress) / total * 100), 100) if total else 0
        snapshot['active_index'] = snapshot.get('current_index') or processed
    return snapshot

@app.route('/admin/batch_auto_run', methods=['POST'])
@login_required
def batch_auto_run():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    if batch_crawl_status.get('running'):
        return jsonify({'error': '批次爬蟲正在執行中，請等待目前任務完成。'}), 409

    batch_crawl_stop_event.clear()
    batch_crawl_pause_event.clear()

    start_number = max(int(request.form.get('start_index', 1) or 1), 1)
    start_index = start_number - 1
    hospital_count = min(max(int(request.form.get('hospital_count', 5) or 5), 1), 300)
    max_reviews = min(max(int(request.form.get('max_reviews', 30) or 30), 1), 200)
    rest_every = min(max(int(request.form.get('rest_every', 5) or 5), 1), 100)
    rest_seconds = min(max(int(request.form.get('rest_seconds', 20) or 20), 0), 600)
    target_list = FLAT_HOSPITAL_LIST[start_index:start_index + hospital_count]

    if not target_list:
        return jsonify({'error': '這個範圍沒有可爬取的醫院'}), 400

    job_id = create_batch_job_record(target_list, start_index, max_reviews, rest_every, rest_seconds)
    mark_batch_job_queued(job_id, target_list, max_reviews)
    update_batch_status(
        running=True,
        status='queued',
        stop_requested=False,
        pause_requested=False,
        current_job_id=job_id,
        started_at=datetime.now(),
        finished_at=None,
        total=len(target_list),
        current_index=0,
        current_hospital='',
        processed=0,
        success=0,
        failed=0,
        skipped=0,
        new_reviews=0,
        refreshed_reviews=0,
        current_review_count=0,
        target_review_count=max_reviews,
        scroll_round=0,
        phase='queued',
        elapsed_seconds=0,
        estimated_remaining_seconds=None,
        last_error='',
        recent_logs=[],
        message=f"已建立批次爬蟲任務，共 {len(target_list)} 家醫院，正在啟動..."
    )

    def background_worker(job_id, hospital_names, review_limit, pause_every, pause_seconds):
        started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        update_batch_job_record(
            job_id,
            status='running',
            started_at=started_at,
            message=f"批次爬蟲執行中，共 {len(hospital_names)} 家醫院。"
        )
        update_batch_status(
            running=True,
            status='running',
            stop_requested=False,
            pause_requested=False,
            current_job_id=job_id,
            started_at=datetime.now(),
            finished_at=None,
            total=len(hospital_names),
            current_index=0,
            current_hospital='',
            processed=0,
            success=0,
            failed=0,
            skipped=0,
            new_reviews=0,
            refreshed_reviews=0,
            current_review_count=0,
            target_review_count=review_limit,
            scroll_round=0,
            phase='starting',
            elapsed_seconds=0,
            estimated_remaining_seconds=None,
            last_error='',
            recent_logs=[]
        )
        append_batch_log(f"已啟動批次爬蟲，共 {len(hospital_names)} 家醫院。")
        print(f"[批次自動化] 啟動：{len(hospital_names)} 家，每家最多 {review_limit} 則。")

        for index, hospital_name in enumerate(hospital_names, start=1):
            if batch_crawl_stop_event.is_set():
                append_batch_log("收到停止要求，批次爬蟲已停止。")
                break
            wait_if_pause_requested(batch_crawl_pause_event, batch_crawl_stop_event, update_batch_status)

            update_batch_job_item(
                job_id,
                hospital_name,
                status='running',
                started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                error_message=''
            )
            update_batch_status(
                current_index=index,
                current_hospital=hospital_name,
                status='running',
                phase='starting',
                current_review_count=0,
                target_review_count=review_limit,
                scroll_round=0
            )
            append_batch_log(f"正在爬取第 {index}/{len(hospital_names)} 家：{hospital_name}")
            with scrape_lock:
                print(f"[批次自動化] ({index}/{len(hospital_names)}) {hospital_name}")
                def report_crawl_progress(**progress):
                    if batch_crawl_stop_event.is_set():
                        progress.setdefault('phase', 'stopping')
                        progress.setdefault('message', '正在停止批次爬蟲...')
                    update_batch_status(**progress)

                try:
                    reviews = scrape_google_reviews(
                        hospital_name,
                        max_reviews=review_limit,
                        progress_callback=report_crawl_progress,
                        stop_event=batch_crawl_stop_event,
                        pause_event=batch_crawl_pause_event
                    )
                except BatchCrawlStopped:
                    update_batch_status(
                        status='stopping',
                        phase='stopping',
                        current_review_count=0,
                        scroll_round=0,
                        message='正在停止批次爬蟲...'
                    )
                    append_batch_log(f"{hospital_name} 爬取中收到停止要求。")
                    update_batch_job_item(
                        job_id,
                        hospital_name,
                        status='stopped',
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        failure_category=classify_crawl_failure('手動停止'),
                        error_message='手動停止'
                    )
                    refresh_batch_job_summary(job_id)
                    break
                except Exception as crawl_err:
                    print(f"[批次自動化] {hospital_name} 爬取失敗：{crawl_err}")
                    update_batch_status(
                        processed=index,
                        current_review_count=0,
                        scroll_round=0,
                        phase='error',
                        failed=batch_crawl_status.get('failed', 0) + 1,
                        last_error=str(crawl_err)
                    )
                    append_batch_log(f"{hospital_name} 爬取失敗：{crawl_err}")
                    update_batch_job_item(
                        job_id,
                        hospital_name,
                        status='failed',
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        failure_category=classify_crawl_failure(crawl_err),
                        error_message=str(crawl_err)
                    )
                    refresh_batch_job_summary(job_id)
                    continue

                if not reviews:
                    if batch_crawl_stop_event.is_set():
                        append_batch_log(f"{hospital_name} 爬取中收到停止要求。")
                        break
                    print(f"[批次自動化] {hospital_name} 未抓到評論，記為失敗。")
                    update_batch_status(
                        processed=index,
                        current_review_count=0,
                        scroll_round=0,
                        phase='error',
                        failed=batch_crawl_status.get('failed', 0) + 1,
                        last_error='未抓到評論'
                    )
                    append_batch_log(f"{hospital_name} 未抓到評論，已列入失敗重爬。")
                    update_batch_job_item(
                        job_id,
                        hospital_name,
                        status='failed',
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        failure_category=classify_crawl_failure('未抓到評論'),
                        error_message='未抓到評論'
                    )
                    refresh_batch_job_summary(job_id)
                    continue

                try:
                    if batch_crawl_stop_event.is_set():
                        append_batch_log("收到停止要求，已停止後續分析與寫入。")
                        break
                    wait_if_pause_requested(batch_crawl_pause_event, batch_crawl_stop_event, update_batch_status)
                    update_batch_status(
                        phase='analyzing',
                        message=f"正在分析 {hospital_name} 的 {len(reviews)} 則評論"
                    )
                    sentiments, pos_count, neg_count = analyze_reviews(reviews)
                except Exception as analyze_err:
                    print(f"[批次自動化] {hospital_name} 分析失敗：{analyze_err}")
                    update_batch_status(
                        processed=index,
                        current_review_count=0,
                        scroll_round=0,
                        phase='error',
                        failed=batch_crawl_status.get('failed', 0) + 1,
                        last_error=str(analyze_err)
                    )
                    append_batch_log(f"{hospital_name} 分析失敗：{analyze_err}")
                    update_batch_job_item(
                        job_id,
                        hospital_name,
                        status='failed',
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        failure_category=classify_crawl_failure(analyze_err),
                        error_message=str(analyze_err)
                    )
                    refresh_batch_job_summary(job_id)
                    continue

                try:
                    if batch_crawl_stop_event.is_set():
                        append_batch_log("收到停止要求，已停止資料庫寫入。")
                        break
                    wait_if_pause_requested(batch_crawl_pause_event, batch_crawl_stop_event, update_batch_status)
                    update_batch_status(
                        phase='saving',
                        message=f"正在寫入 {hospital_name} 的分析結果"
                    )
                    new_reviews, refreshed_reviews = save_batch_sentiments_for_hospital(hospital_name, sentiments)
                    print(f"[批次自動化] {hospital_name} 新增 {new_reviews} 則，更新 {refreshed_reviews} 則。")
                    issue_rows = get_negative_issue_rows(sentiments, limit=3)
                    top_issue = issue_rows[0]['issue_category'] if issue_rows else ''
                    review_samples = [
                        {
                            'sentiment': s.get('label'),
                            'issue_category': s.get('issue_category'),
                            'time': s.get('time'),
                            'text': s.get('text')
                        }
                        for s in sentiments[:5]
                    ]
                    update_batch_status(
                        processed=index,
                        current_review_count=0,
                        scroll_round=0,
                        phase='done',
                        success=batch_crawl_status.get('success', 0) + 1,
                        new_reviews=batch_crawl_status.get('new_reviews', 0) + new_reviews,
                        refreshed_reviews=batch_crawl_status.get('refreshed_reviews', 0) + refreshed_reviews
                    )
                    append_batch_log(f"{hospital_name} 完成：新增 {new_reviews} 則，更新 {refreshed_reviews} 則。")
                    update_batch_job_item(
                        job_id,
                        hospital_name,
                        status='success',
                        new_reviews=new_reviews,
                        refreshed_reviews=refreshed_reviews,
                        positive_reviews=pos_count,
                        negative_reviews=neg_count,
                        total_reviews=len(sentiments),
                        top_issue=top_issue,
                        review_samples=json.dumps(review_samples, ensure_ascii=False),
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    refresh_batch_job_summary(job_id)
                except Exception as db_err:
                    print(f"[批次自動化] 資料庫寫入失敗：{db_err}")
                    update_batch_status(
                        processed=index,
                        current_review_count=0,
                        scroll_round=0,
                        phase='error',
                        failed=batch_crawl_status.get('failed', 0) + 1,
                        last_error=str(db_err)
                    )
                    append_batch_log(f"{hospital_name} 資料庫寫入失敗：{db_err}")
                    update_batch_job_item(
                        job_id,
                        hospital_name,
                        status='failed',
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        failure_category=classify_crawl_failure(db_err),
                        error_message=str(db_err)
                    )
                    refresh_batch_job_summary(job_id)

            if pause_seconds > 0 and index < len(hospital_names) and index % pause_every == 0:
                if batch_crawl_stop_event.is_set():
                    append_batch_log("收到停止要求，已停止休息並結束。")
                    break
                print(f"[批次自動化] 已跑 {index} 家，休息 {pause_seconds} 秒。")
                update_batch_status(status='resting', phase='resting')
                append_batch_log(f"已跑 {index} 家，休息 {pause_seconds} 秒。")
                try:
                    interruptible_sleep(pause_seconds, batch_crawl_stop_event, batch_crawl_pause_event, update_batch_status)
                except BatchCrawlStopped:
                    append_batch_log("休息期間收到停止要求，批次爬蟲已停止。")
                    break
                update_batch_status(status='running', phase='running')

        if batch_crawl_stop_event.is_set():
            print("[批次自動化] 任務已手動停止。")
            update_batch_status(
                running=False,
                status='stopped',
                stop_requested=False,
                pause_requested=False,
                finished_at=datetime.now(),
                current_hospital='',
                current_review_count=0,
                scroll_round=0,
                phase='stopped',
                estimated_remaining_seconds=0,
                message='批次爬蟲已手動停止'
            )
            append_batch_log("批次爬蟲已手動停止。")
            refresh_batch_job_summary(job_id)
            update_batch_job_record(
                job_id,
                status='stopped',
                finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                message='批次爬蟲已手動停止'
            )
            batch_crawl_stop_event.clear()
            batch_crawl_pause_event.clear()
        else:
            print("[批次自動化] 任務完成。")
            update_batch_status(
                running=False,
                status='finished',
                stop_requested=False,
                pause_requested=False,
                finished_at=datetime.now(),
                current_hospital='',
                current_review_count=0,
                scroll_round=0,
                phase='finished',
                estimated_remaining_seconds=0
            )
            append_batch_log("批次爬蟲任務完成。")
            refresh_batch_job_summary(job_id)
            update_batch_job_record(
                job_id,
                status='finished',
                finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                message='批次爬蟲任務完成'
            )
            batch_crawl_pause_event.clear()

    t = threading.Thread(
        target=background_worker,
        args=(job_id, target_list, max_reviews, rest_every, rest_seconds),
        daemon=True
    )
    t.start()

    return jsonify({
        'status': 'ok',
        'message': f'已開始背景爬取 {len(target_list)} 家醫院，每家最多 {max_reviews} 則評論。',
        'batch_status': get_batch_status_snapshot()
    })

@app.route('/admin/batch_auto_stop', methods=['POST'])
@login_required
def batch_auto_stop():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    if not batch_crawl_status.get('running'):
        return jsonify({
            'status': 'idle',
            'message': '目前沒有執行中的批次爬蟲。',
            'batch_status': get_batch_status_snapshot()
        })

    batch_crawl_stop_event.set()
    batch_crawl_pause_event.clear()
    current_job_id = batch_crawl_status.get('current_job_id')
    update_batch_status(
        status='stopping',
        phase='stopping',
        stop_requested=True,
        pause_requested=False,
        message='已送出停止要求，正在關閉目前爬蟲...'
    )
    update_batch_job_record(
        current_job_id,
        status='stopping',
        message='已送出停止要求，正在關閉目前爬蟲...'
    )
    append_batch_log("已送出停止要求，正在關閉目前爬蟲。")
    return jsonify({
        'status': 'stopping',
        'message': '已送出停止要求，正在關閉目前爬蟲...',
        'batch_status': get_batch_status_snapshot()
    })

@app.route('/admin/batch_auto_pause', methods=['POST'])
@login_required
def batch_auto_pause():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    if not batch_crawl_status.get('running'):
        return jsonify({
            'status': 'idle',
            'message': '目前沒有執行中的批次爬蟲。',
            'batch_status': get_batch_status_snapshot()
        }), 409

    if batch_crawl_stop_event.is_set() or batch_crawl_status.get('status') == 'stopping':
        return jsonify({
            'status': 'stopping',
            'message': '批次爬蟲正在停止中，無法暫停或繼續。',
            'batch_status': get_batch_status_snapshot()
        }), 409

    action = request.form.get('action', '').strip().lower()
    should_resume = action == 'resume' or (not action and batch_crawl_pause_event.is_set())

    if should_resume:
        batch_crawl_pause_event.clear()
        current_job_id = batch_crawl_status.get('current_job_id')
        update_batch_status(
            status='running',
            phase='running',
            pause_requested=False,
            message='批次爬蟲已繼續'
        )
        update_batch_job_record(current_job_id, status='running', message='批次爬蟲已繼續')
        append_batch_log("批次爬蟲已繼續。")
        message = '批次爬蟲已繼續'
        state = 'running'
    else:
        batch_crawl_pause_event.set()
        current_job_id = batch_crawl_status.get('current_job_id')
        update_batch_status(
            status='paused',
            phase='paused',
            pause_requested=True,
            message='批次爬蟲已暫停，按繼續可接著爬。'
        )
        update_batch_job_record(current_job_id, status='paused', message='批次爬蟲已暫停')
        append_batch_log("批次爬蟲已暫停。")
        message = '批次爬蟲已暫停，按繼續可接著爬。'
        state = 'paused'

    return jsonify({
        'status': state,
        'message': message,
        'batch_status': get_batch_status_snapshot()
    })

@app.route('/admin/batch_auto_status')
@login_required
@limiter.exempt
def batch_auto_status():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403
    return jsonify(get_batch_status_snapshot())

@app.route('/admin/batch_preview')
@login_required
@limiter.exempt
def batch_preview():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    total = len(FLAT_HOSPITAL_LIST)
    start_number = max(int(request.args.get('start_index', 1) or 1), 1)
    start_index = start_number - 1
    hospital_count = min(max(int(request.args.get('hospital_count', 5) or 5), 1), 300)
    target_list = FLAT_HOSPITAL_LIST[start_index:start_index + hospital_count]

    return jsonify({
        'total_hospitals': total,
        'start_index': start_index + 1,
        'hospital_count': hospital_count,
        'end_index': start_index + len(target_list) if target_list else None,
        'hospitals': target_list
    })

@app.route('/admin/batch_jobs')
@login_required
@limiter.exempt
def batch_jobs():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM batch_crawl_jobs
            ORDER BY id DESC
            LIMIT 30
        """)
        jobs = [dict(row) for row in cursor.fetchall()]

    return jsonify({'jobs': jobs})

@app.route('/admin/batch_jobs/<int:job_id>')
@login_required
@limiter.exempt
def batch_job_detail(job_id):
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM batch_crawl_jobs WHERE id = ?", (job_id,))
        job = cursor.fetchone()
        if not job:
            return jsonify({'error': '找不到批次任務'}), 404

        cursor.execute("""
            SELECT *
            FROM batch_crawl_job_items
            WHERE job_id = ?
            ORDER BY id ASC
        """, (job_id,))
        items = []
        for row in cursor.fetchall():
            item = dict(row)
            cursor.execute("SELECT id FROM hospitals WHERE name = ? LIMIT 1", (item['hospital_name'],))
            hospital_row = cursor.fetchone()
            item['hospital_id'] = hospital_row['id'] if hospital_row else None
            try:
                item['review_samples'] = json.loads(item.get('review_samples') or '[]')
            except Exception:
                item['review_samples'] = []
            items.append(item)

    return jsonify({'job': dict(job), 'items': items})

def retry_failed_batch_worker(job_id, hospital_names, review_limit, pause_every, pause_seconds, job_label='失敗重試'):
    update_batch_job_record(
        job_id,
        status='running',
        started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message=f'正在執行{job_label}'
    )
    update_batch_status(
        running=True,
        status='running',
        stop_requested=False,
        pause_requested=False,
        current_job_id=job_id,
        started_at=datetime.now(),
        finished_at=None,
        total=len(hospital_names),
        current_index=0,
        current_hospital='',
        processed=0,
        success=0,
        failed=0,
        skipped=0,
        new_reviews=0,
        refreshed_reviews=0,
        current_review_count=0,
        target_review_count=review_limit,
        scroll_round=0,
        phase='starting',
        elapsed_seconds=0,
        estimated_remaining_seconds=None,
        last_error='',
        recent_logs=[]
    )
    append_batch_log(f"已啟動{job_label}，共 {len(hospital_names)} 家醫院。")

    for index, hospital_name in enumerate(hospital_names, start=1):
        if batch_crawl_stop_event.is_set():
            break
        wait_if_pause_requested(batch_crawl_pause_event, batch_crawl_stop_event, update_batch_status)
        update_batch_job_item(
            job_id,
            hospital_name,
            status='running',
            started_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            error_message=''
        )
        update_batch_status(
            current_index=index,
            current_hospital=hospital_name,
            status='running',
            phase='starting',
            current_review_count=0,
            target_review_count=review_limit,
            scroll_round=0
        )
        append_batch_log(f"{job_label}第 {index}/{len(hospital_names)} 家：{hospital_name}")

        with scrape_lock:
            def report_crawl_progress(**progress):
                if batch_crawl_stop_event.is_set():
                    progress.setdefault('phase', 'stopping')
                    progress.setdefault('message', '正在停止批次爬蟲...')
                update_batch_status(**progress)

            try:
                reviews = scrape_google_reviews(
                    hospital_name,
                    max_reviews=review_limit,
                    progress_callback=report_crawl_progress,
                    stop_event=batch_crawl_stop_event,
                    pause_event=batch_crawl_pause_event
                )
                if not reviews:
                    update_batch_status(
                        processed=index,
                        failed=batch_crawl_status.get('failed', 0) + 1,
                        phase='error',
                        last_error='未抓到評論'
                    )
                    update_batch_job_item(
                        job_id,
                        hospital_name,
                        status='failed',
                        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        failure_category=classify_crawl_failure('未抓到評論'),
                        error_message='未抓到評論'
                    )
                    append_batch_log(f"{hospital_name} 未抓到評論，已列入失敗重爬。")
                    refresh_batch_job_summary(job_id)
                    continue

                sentiments, pos_count, neg_count = analyze_reviews(reviews)
                new_reviews, refreshed_reviews = save_batch_sentiments_for_hospital(hospital_name, sentiments)
                issue_rows = get_negative_issue_rows(sentiments, limit=3)
                top_issue = issue_rows[0]['issue_category'] if issue_rows else ''
                review_samples = [
                    {
                        'sentiment': s.get('label'),
                        'issue_category': s.get('issue_category'),
                        'time': s.get('time'),
                        'text': s.get('text')
                    }
                    for s in sentiments[:5]
                ]
                update_batch_status(
                    processed=index,
                    current_review_count=0,
                    scroll_round=0,
                    phase='done',
                    success=batch_crawl_status.get('success', 0) + 1,
                    new_reviews=batch_crawl_status.get('new_reviews', 0) + new_reviews,
                    refreshed_reviews=batch_crawl_status.get('refreshed_reviews', 0) + refreshed_reviews
                )
                update_batch_job_item(
                    job_id,
                    hospital_name,
                    status='success',
                    new_reviews=new_reviews,
                    refreshed_reviews=refreshed_reviews,
                    positive_reviews=pos_count,
                    negative_reviews=neg_count,
                    total_reviews=len(sentiments),
                    top_issue=top_issue,
                    review_samples=json.dumps(review_samples, ensure_ascii=False),
                    finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
                append_batch_log(f"{hospital_name} 完成：新增 {new_reviews} 則，更新 {refreshed_reviews} 則。")
                refresh_batch_job_summary(job_id)
            except BatchCrawlStopped:
                update_batch_job_item(
                    job_id,
                    hospital_name,
                    status='stopped',
                    finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    failure_category=classify_crawl_failure('手動停止'),
                    error_message='手動停止'
                )
                refresh_batch_job_summary(job_id)
                break
            except Exception as err:
                update_batch_status(
                    processed=index,
                    phase='error',
                    failed=batch_crawl_status.get('failed', 0) + 1,
                    last_error=str(err)
                )
                update_batch_job_item(
                    job_id,
                    hospital_name,
                    status='failed',
                    finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    failure_category=classify_crawl_failure(err),
                    error_message=str(err)
                )
                append_batch_log(f"{hospital_name} 執行失敗：{err}")
                refresh_batch_job_summary(job_id)

        if pause_seconds > 0 and index < len(hospital_names) and index % pause_every == 0:
            try:
                update_batch_status(status='resting', phase='resting')
                interruptible_sleep(pause_seconds, batch_crawl_stop_event, batch_crawl_pause_event, update_batch_status)
            except BatchCrawlStopped:
                break

    final_status = 'stopped' if batch_crawl_stop_event.is_set() else 'finished'
    final_message = f'{job_label}已手動停止' if final_status == 'stopped' else f'{job_label}完成'
    refresh_batch_job_summary(job_id)
    update_batch_job_record(
        job_id,
        status=final_status,
        finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        message=final_message
    )
    update_batch_status(
        running=False,
        status=final_status,
        stop_requested=False,
        pause_requested=False,
        finished_at=datetime.now(),
        current_hospital='',
        current_review_count=0,
        scroll_round=0,
        phase=final_status,
        estimated_remaining_seconds=0,
        message=final_message
    )
    append_batch_log(final_message)
    batch_crawl_stop_event.clear()
    batch_crawl_pause_event.clear()

def compute_next_schedule_run(frequency, run_time, from_time=None):
    from_time = from_time or datetime.now()
    try:
        hour, minute = [int(part) for part in (run_time or '02:00').split(':')[:2]]
    except Exception:
        hour, minute = 2, 0
    candidate = from_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= from_time:
        if frequency == 'weekly':
            candidate += timedelta(days=7)
        else:
            candidate += timedelta(days=1)
    return candidate

def pick_schedule_hospitals(start_index, hospital_count):
    if not FLAT_HOSPITAL_LIST:
        return [], 0
    total = len(FLAT_HOSPITAL_LIST)
    start_index = max(int(start_index or 0), 0) % total
    hospital_count = min(max(int(hospital_count or 1), 1), total)
    names = []
    for offset in range(hospital_count):
        names.append(FLAT_HOSPITAL_LIST[(start_index + offset) % total])
    next_index = (start_index + hospital_count) % total
    return names, next_index

def start_schedule_job(schedule):
    if batch_crawl_status.get('running'):
        return False

    hospital_names, next_index = pick_schedule_hospitals(schedule['next_start_index'], schedule['hospital_count'])
    if not hospital_names:
        return False

    batch_crawl_stop_event.clear()
    batch_crawl_pause_event.clear()
    job_id = create_batch_job_record(
        hospital_names,
        schedule['next_start_index'] or 0,
        schedule['max_reviews'] or 30,
        schedule['rest_every'] or 5,
        schedule['rest_seconds'] or 20
    )
    update_batch_job_record(job_id, message=f"排程「{schedule['name']}」自動建立")
    mark_batch_job_queued(
        job_id,
        hospital_names,
        schedule['max_reviews'] or 30,
        f"排程「{schedule['name']}」已排隊，正在啟動背景任務..."
    )

    now = datetime.now()
    next_run = compute_next_schedule_run(schedule['frequency'], schedule['run_time'], now)
    with sqlite3.connect(HR_DB) as conn:
        conn.execute("""
            UPDATE batch_crawl_schedules
            SET next_start_index = ?, last_run_at = ?, next_run_at = ?, updated_at = ?
            WHERE id = ?
        """, (
            next_index,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            next_run.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S"),
            schedule['id']
        ))
        conn.commit()

    thread = threading.Thread(
        target=retry_failed_batch_worker,
        args=(job_id, hospital_names, schedule['max_reviews'] or 30, schedule['rest_every'] or 5, schedule['rest_seconds'] or 20, f"排程「{schedule['name']}」"),
        daemon=True
    )
    thread.start()
    return True

def batch_schedule_loop():
    while True:
        try:
            with sqlite3.connect(HR_DB) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT *
                    FROM batch_crawl_schedules
                    WHERE enabled = 1
                      AND next_run_at IS NOT NULL
                      AND datetime(next_run_at) <= datetime('now', 'localtime')
                    ORDER BY next_run_at ASC
                    LIMIT 1
                """)
                schedule = cursor.fetchone()
            if schedule:
                start_schedule_job(dict(schedule))
        except Exception as err:
            print(f"⚠️ 排程爬蟲檢查失敗: {err}")
        time.sleep(60)

def ensure_batch_scheduler_started():
    global batch_scheduler_started
    if batch_scheduler_started:
        return
    batch_scheduler_started = True
    thread = threading.Thread(target=batch_schedule_loop, daemon=True)
    thread.start()

@app.route('/admin/batch_jobs/<int:job_id>/retry_failed', methods=['POST'])
@login_required
def retry_failed_batch_job(job_id):
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403
    if batch_crawl_status.get('running'):
        return jsonify({'error': '批次爬蟲正在執行中，請先暫停/停止或等待完成。'}), 409

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM batch_crawl_jobs WHERE id = ?", (job_id,))
        job = cursor.fetchone()
        if not job:
            return jsonify({'error': '找不到批次任務'}), 404
        cursor.execute("""
            SELECT hospital_name
            FROM batch_crawl_job_items
            WHERE job_id = ? AND status IN ('failed', 'skipped')
            ORDER BY id ASC
        """, (job_id,))
        failed_names = [row['hospital_name'] for row in cursor.fetchall()]

    if not failed_names:
        return jsonify({'error': '這個任務沒有失敗醫院可重試。'}), 400

    batch_crawl_stop_event.clear()
    batch_crawl_pause_event.clear()
    retry_job_id = create_batch_job_record(
        failed_names,
        job['start_index'] or 0,
        job['max_reviews'] or 30,
        job['rest_every'] or 5,
        job['rest_seconds'] or 20,
        retry_of_job_id=job_id
    )
    thread = threading.Thread(
        target=retry_failed_batch_worker,
        args=(retry_job_id, failed_names, job['max_reviews'] or 30, job['rest_every'] or 5, job['rest_seconds'] or 20),
        daemon=True
    )
    thread.start()

    return jsonify({
        'status': 'ok',
        'message': f'已建立失敗重試任務，共 {len(failed_names)} 家醫院。',
        'job_id': retry_job_id,
        'batch_status': get_batch_status_snapshot()
    })

@app.route('/admin/batch_schedules')
@login_required
@limiter.exempt
def batch_schedules():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    ensure_batch_scheduler_started()
    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM batch_crawl_schedules ORDER BY id DESC")
        schedules = [dict(row) for row in cursor.fetchall()]
    return jsonify({'schedules': schedules})

@app.route('/admin/batch_schedules', methods=['POST'])
@login_required
def create_batch_schedule():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    name = request.form.get('name', '').strip() or '自動排程爬蟲'
    frequency = request.form.get('frequency', 'daily')
    if frequency not in ['daily', 'weekly']:
        frequency = 'daily'
    run_time = request.form.get('run_time', '02:00')
    hospital_count = min(max(int(request.form.get('hospital_count', 10) or 10), 1), 300)
    max_reviews = min(max(int(request.form.get('max_reviews', 30) or 30), 1), 200)
    rest_every = min(max(int(request.form.get('rest_every', 5) or 5), 1), 100)
    rest_seconds = min(max(int(request.form.get('rest_seconds', 20) or 20), 0), 600)
    next_start_number = max(int(request.form.get('next_start_index', 1) or 1), 1)
    next_start_index = next_start_number - 1
    now = datetime.now()
    next_run = compute_next_schedule_run(frequency, run_time, now)

    with sqlite3.connect(HR_DB) as conn:
        conn.execute("""
            INSERT INTO batch_crawl_schedules
                (name, enabled, frequency, run_time, hospital_count, max_reviews, rest_every,
                 rest_seconds, next_start_index, next_run_at, created_at, updated_at)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, frequency, run_time, hospital_count, max_reviews, rest_every,
            rest_seconds, next_start_index, next_run.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
    ensure_batch_scheduler_started()
    return jsonify({'status': 'ok', 'message': '排程已建立'})

@app.route('/admin/batch_schedules/<int:schedule_id>/toggle', methods=['POST'])
@login_required
def toggle_batch_schedule(schedule_id):
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403
    enabled = 1 if request.form.get('enabled') == '1' else 0
    with sqlite3.connect(HR_DB) as conn:
        conn.execute("""
            UPDATE batch_crawl_schedules
            SET enabled = ?, updated_at = ?
            WHERE id = ?
        """, (enabled, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), schedule_id))
        conn.commit()
    return jsonify({'status': 'ok', 'message': '排程已更新'})

@app.route('/admin/batch_schedules/<int:schedule_id>/delete', methods=['POST'])
@login_required
def delete_batch_schedule(schedule_id):
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403
    with sqlite3.connect(HR_DB) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM batch_crawl_schedules WHERE id = ?", (schedule_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'error': '找不到排程'}), 404
    return jsonify({'status': 'ok', 'message': '排程已刪除'})

@app.route('/admin/batch_schedules/<int:schedule_id>/run_now', methods=['POST'])
@login_required
def run_batch_schedule_now(schedule_id):
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403
    if batch_crawl_status.get('running'):
        return jsonify({'error': '批次爬蟲正在執行中，請稍後再執行排程。'}), 409

    with sqlite3.connect(HR_DB) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM batch_crawl_schedules WHERE id = ?", (schedule_id,))
        schedule = cursor.fetchone()
    if not schedule:
        return jsonify({'error': '找不到排程'}), 404

    started = start_schedule_job(dict(schedule))
    if not started:
        return jsonify({'error': '排程目前無法啟動'}), 409
    return jsonify({'status': 'ok', 'message': '排程已立即執行', 'batch_status': get_batch_status_snapshot()})

@app.route('/pk', methods=['GET', 'POST'])
@login_required
def pk_page():
    if request.method == 'POST':
        h1_name = request.form.get('hospital1')
        h2_name = request.form.get('hospital2')
        target_dept = request.form.get('department') 
        
        if not h1_name or not h2_name:
            flash("請輸入兩家醫院名稱", "analyze_error")
            return redirect(url_for('pk_page'))
        
        h1_name = resolve_known_hospital_name(h1_name)
        h2_name = resolve_known_hospital_name(h2_name)
        if not h1_name or not h2_name:
            flash("⚠️ 請從建議清單選擇兩家已收錄醫院，不要輸入科別或單字關鍵字。", "analyze_error")
            return redirect(url_for('pk_page'))

        # 執行爬蟲與數據統計
        with scrape_lock:
            try:
                stats1 = get_hospital_stats(h1_name, target_dept=target_dept)
            except Exception as err:
                print(f"⚠️ PK 取得 {h1_name} 統計失敗，直接改用一般評論：{err}")
                stats1_reviews, stats1_pos, stats1_neg = fallback_pk_stats_from_database(h1_name, target_dept, 'PK route 例外')
                stats1 = build_pk_stats_from_reviews(h1_name, stats1_reviews, stats1_pos, stats1_neg) if stats1_reviews else None

            try:
                stats2 = get_hospital_stats(h2_name, target_dept=target_dept)
            except Exception as err:
                print(f"⚠️ PK 取得 {h2_name} 統計失敗，直接改用一般評論：{err}")
                stats2_reviews, stats2_pos, stats2_neg = fallback_pk_stats_from_database(h2_name, target_dept, 'PK route 例外')
                stats2 = build_pk_stats_from_reviews(h2_name, stats2_reviews, stats2_pos, stats2_neg) if stats2_reviews else None
        
        if not stats1:
            flash(f"找不到「{h1_name}」的資料", "analyze_error")
            return redirect(url_for('pk_page'))
        if not stats2:
            flash(f"找不到「{h2_name}」的資料", "analyze_error")
            return redirect(url_for('pk_page'))

        pk_comparison = build_pk_comparison(stats1, stats2)

        # ==========================================
        # 🤖 同步觸發：AI 醫療決策輔助分析 (專業版)
        # ==========================================
        ai_pk_summary = ""
        if get_ai_summary_mode() == 'local':
            ai_pk_summary = generate_local_pk_summary(h1_name, h2_name, stats1, stats2, target_dept)
            log_ai_usage("local", "local_statistics", "pk_analysis", "success")
            return render_template('pk.html',
                                   h1=stats1,
                                   h2=stats2,
                                   target_dept=target_dept,
                                   all_hospitals=FLAT_HOSPITAL_LIST,
                                   pk_comparison=pk_comparison,
                                   ai_pk_summary=ai_pk_summary)

        try:
            print(f"🤖 正在同步生成 {h1_name} vs {h2_name} 的專業分析報告...")
            h1_score = stats1['avg_score']
            h2_score = stats2['avg_score']
            
            prompt = f"""
            你現在是一位專業、客觀且具備同理心的「醫療數據分析顧問」。
            有民眾正在猶豫要選擇哪家醫療機構就診，請根據以下真實的滿意度數據，提供一段約 100~150 字的專業分析與就醫建議。
            
            【機構 A】{h1_name}：綜合滿意度 {h1_score} 分 (滿分10分)，正面 {stats1['pos']} 則，負面 {stats1['neg']} 則。
            【機構 B】{h2_name}：綜合滿意度 {h2_score} 分 (滿分10分)，正面 {stats2['pos']} 則，負面 {stats2['neg']} 則。
            查詢科別：{target_dept if target_dept else '綜合門診'}
            
            寫作要求：
            1. 語氣必須嚴謹、專業，但確保一般大眾能輕鬆讀懂。
            2. 絕對不可使用「完勝」、「鄉民」、「賽評」等過於輕浮的網路用語。
            3. 請基於數據客觀陳述兩者的滿意度差異，並給出中肯的評估建議。
            
            請直接輸出 HTML 格式（絕對不要使用 ```html 這種 Markdown 語法標記，也不要有開場白）。
            排版規格如下：
            <div class="card border-0 shadow-sm mb-4" style="border-left: 5px solid #17a2b8; border-radius: 12px; background: white;">
                <div class="card-body p-4">
                    <h5 class="fw-bold text-info mb-3"><i class="fas fa-chart-line me-2"></i>AI 醫療決策輔助分析</h5>
                    <p class="fs-6 text-dark mb-3" style="line-height: 1.8;">
                        [請在此填寫客觀的綜合分析。例如：根據近期的滿意度數據顯示，這兩家醫療機構在整體評價上呈現...]
                    </p>
                    <div class="p-3 rounded-3" style="background-color: #f8f9fa; border: 1px solid #e9ecef;">
                        <strong class="text-secondary"><i class="fas fa-user-md me-2"></i>綜合評估建議：</strong>
                        <span class="text-dark fw-bold">[給出具體且專業的就醫建議。例如：若您考量整體的就診體驗，建議可優先考慮 A 醫院；若重視特定醫療資源，B 醫院亦是可靠的選擇。]</span>
                    </div>
                </div>
            </div>
            """
            
            response = generate_gemini_content(prompt, feature='pk_analysis')
            ai_pk_summary = response.text.strip()
            print("✅ AI 專業分析生成成功！")
        except GeminiQuotaExceeded as e:
            print(f"⚠️ PK 分析 Gemini 額度已滿，改用本地端: {e}")
            notify_admin_ai_quota('pk_analysis', e)
            ai_pk_summary = generate_local_pk_summary(h1_name, h2_name, stats1, stats2, target_dept)
            log_ai_usage("local", "local_statistics", "pk_analysis", "success", "Gemini quota exceeded")
        except Exception as e:
            print(f"❌ AI 分析生成失敗: {e}")
            ai_pk_summary = generate_local_pk_summary(h1_name, h2_name, stats1, stats2, target_dept)
            log_ai_usage("local", "local_statistics", "pk_analysis", "success", e)
        # 將數據與 AI 講評一次性回傳給前端
        return render_template('pk.html', 
                               h1=stats1, 
                               h2=stats2, 
                               target_dept=target_dept, 
                               all_hospitals=FLAT_HOSPITAL_LIST,
                               pk_comparison=pk_comparison,
                               ai_pk_summary=ai_pk_summary)

    return render_template('pk.html', all_hospitals=FLAT_HOSPITAL_LIST)

# ==========================================
# 🏥 症狀自我評估 AI 判斷
# ==========================================
@app.route('/symptom_checker', methods=['GET', 'POST'])
@login_required
@limiter.limit("5 per minute")
def symptom_checker():
    if request.method == 'POST':
        user_input = request.form.get('symptoms')
        print(f"🩺 收到症狀分流請求：{str(user_input or '')[:60]}")
        
        if not user_input:
            return jsonify({'error': '請輸入您的症狀描述'})
        
        if get_ai_summary_mode() == 'local':
            symptom_list = extract_local_symptoms(user_input)
            try:
                save_symptom_logs(symptom_list, "本地症狀")
            except Exception as e:
                print(f"⚠️ 本地症狀紀錄儲存失敗: {e}")

            log_ai_usage("local", "local_statistics", "symptom_checker", "success")
            return jsonify({'result': generate_local_symptom_result(user_input), 'mode': 'local'})

        # ==========================================
        # 💾 進階版：利用 AI 萃取並標準化症狀，再分開存入資料庫
        # ==========================================
        try:
            # 1. 建立「萃取專用」的 Prompt，要求 AI 將口語轉換為標準名詞並用逗號分隔
            extract_prompt = f"""
            請從以下民眾的口語描述中，萃取出「核心症狀」。
            請將口語轉為簡潔的標準名詞（例如「肚子超痛」轉為「腹痛」，「頭有點痛」轉為「頭痛」）。
            請「嚴格只回傳」用半形逗號分隔的關鍵字，不要包含任何其他解釋或引言。
            使用者描述：{user_input}
            """
            
            # 呼叫 Gemini 進行萃取
            extract_response = generate_gemini_content(extract_prompt, feature='symptom_extract', timeout_seconds=8)
            
            # 取得 AI 整理好的關鍵字 (例如: "頭痛,發燒")
            keywords_str = extract_response.text.strip()
            
            # 用逗號將字串拆解成 Python 的 List (陣列)
            symptom_list = [s.strip() for s in keywords_str.split(',') if s.strip()]

            # 2. 將拆分後的標準化症狀「一筆一筆」獨立存入資料庫
            save_symptom_logs(symptom_list, "Gemini 症狀")

        except Exception as e:
            print(f"⚠️ 症狀萃取或儲存失敗: {e}")
            try:
                fallback_symptoms = extract_local_symptoms(user_input)
                save_symptom_logs(fallback_symptoms, "本地備援症狀")
            except Exception as fallback_error:
                print(f"⚠️ 本地備援症狀紀錄儲存失敗: {fallback_error}")
        # ==========================================

        try:
            # 將官方指南轉換為文字格式給 AI 參考
            guide_text = "\n".join([f"- {dept}: {symptoms}" for dept, symptoms in OFFICIAL_SYMPTOM_GUIDE.items()])

            # 建立 Prompt，強制 AI 參考官方資料
            prompt = f"""
            你是一位專業但說話白話的醫院分流護理師。
            
            【權威參考資料：國軍臺中總醫院症狀分流指南】
            請優先參考以下官方科別對應的症狀來做判斷：
            {guide_text}
            
            使用者描述了以下症狀：『{user_input}』
            
            請根據此描述與上述官方指南進行初步判斷，但語氣要像對一般民眾說明，不要寫成專業報告。
            使用者只需要知道：
            1. 這些症狀建議先看哪一科
            2. 嚴不嚴重
            3. 要不要馬上去醫院或急診
            4. 還要注意哪些症狀
            5. 你判斷的依據是什麼

            請只回傳 HTML 片段，不要 Markdown，不要 **粗體符號**，不要 ```，不要外層說明文字。
            文字限制：每個區塊 1 到 2 句話，務必白話、短句、可直接看懂。
            
            <div class="card border-0 shadow-sm mb-3 triage-simple-card">
                <div class="card-body p-4">
                    <div class="mb-3">
                        <div class="text-muted fw-bold mb-1">你可能要掛</div>
                        <div class="display-6 fw-bold text-primary">[建議科別，盡量符合官方指南科別名稱]</div>
                        <div class="text-muted mt-2">[一句話說明為什麼是這科。若不確定，提醒可先掛家庭醫學科或一般內科。]</div>
                    </div>

                    <div class="row g-3 mb-3">
                        <div class="col-md-6">
                            <div class="border rounded-3 p-3 h-100">
                                <div class="fw-bold mb-1"><i class="fas fa-triangle-exclamation me-2 text-warning"></i>嚴不嚴重？</div>
                                <div class="h5 fw-bold text-warning mb-2">[例如：目前看起來可先門診評估 / 偏嚴重，建議盡快就醫]</div>
                                <div class="text-muted small">[用白話說明嚴重程度，不要恐嚇。]</div>
                            </div>
                        </div>
                        <div class="col-md-6">
                            <div class="border rounded-3 p-3 h-100">
                                <div class="fw-bold mb-1"><i class="fas fa-hospital me-2 text-primary"></i>要不要馬上去醫院？</div>
                                <div class="text-muted small">[明確回答：可先掛門診，或建議現在去急診。列出立刻就醫條件。]</div>
                            </div>
                        </div>
                    </div>

                    <div class="border rounded-3 p-3 mb-3 bg-light">
                        <div class="fw-bold mb-2"><i class="fas fa-magnifying-glass me-2 text-primary"></i>還要注意哪些症狀？</div>
                        <div class="text-dark">[列出 3 到 5 個相關警訊或伴隨症狀，例如發燒、持續嘔吐、呼吸困難等。]</div>
                        <div class="small text-muted mt-2">如果這些症狀一起出現或越來越明顯，請提高就醫急迫性。</div>
                    </div>

                    <div class="border rounded-3 p-3 mb-3">
                        <div class="fw-bold mb-2"><i class="fas fa-clipboard-check me-2 text-primary"></i>判斷依據</div>
                        <div class="small text-muted">[說明依據：使用者提到的症狀 + 官方指南中相近症狀，所以建議此科。]</div>
                    </div>

                    <p class="text-muted small mb-0">提醒：這是掛號前參考，不能取代醫師診斷。若你覺得和平常不一樣或症狀變很快，請直接就醫。</p>
                </div>
            </div>
            """

            response = generate_gemini_content(prompt, feature='symptom_checker', timeout_seconds=18)
            
            return jsonify({'result': response.text})
            
        except GeminiQuotaExceeded as e:
            print(f"⚠️ 症狀評估 Gemini 額度已滿，改用本地端: {e}")
            notify_admin_ai_quota('symptom_checker', e)
            log_ai_usage("local", "local_statistics", "symptom_checker", "success", "Gemini quota exceeded")
            return jsonify({'result': generate_local_symptom_result(user_input), 'mode': 'local'})

        except Exception as e:
            print(f"❌ Gemini 判斷失敗: {e}")
            log_ai_usage("local", "local_statistics", "symptom_checker", "success", e)
            return jsonify({'result': generate_local_symptom_result(user_input), 'mode': 'local'})

    return render_template('symptom_checker.html')

# ==========================================
# 🤖 後台管理：AI 症狀趨勢分析 (系統公告建議草稿)
# ==========================================
@app.route('/api/analyze_symptom_trends', methods=['POST'])
@login_required
def analyze_symptom_trends():
    if not current_user.is_admin:
        return jsonify({'error': '權限不足'}), 403

    top_symptoms = []
    try:
        # 1. 撈取目前的 Top 10 症狀
        with sqlite3.connect(HR_DB) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT symptom_text, COUNT(*) as count 
                FROM symptom_logs 
                GROUP BY symptom_text 
                ORDER BY count DESC, symptom_text ASC
                LIMIT 10
            ''')
            top_symptoms = cursor.fetchall()

        if not top_symptoms:
            return jsonify({'result': '目前還沒有收集到足夠的症狀數據來讓 AI 分析喔！'})

        public_health_symptoms = filter_public_health_symptoms(top_symptoms)
        excluded_count = len(top_symptoms) - len(public_health_symptoms)
        if not public_health_symptoms:
            return jsonify({
                'result': '目前症狀趨勢多屬個人事件或外傷查詢，暫不建議發布社區健康公告。',
                'mode': 'filtered',
                'excluded_personal_symptoms': excluded_count
            })

        if get_ai_summary_mode() == 'local':
            log_ai_usage("local", "local_statistics", "symptom_trend_announcement", "success")
            return jsonify({
                'result': generate_local_symptom_trend_announcement(public_health_symptoms),
                'mode': 'local',
                'excluded_personal_symptoms': excluded_count
            })

        # 2. 將症狀組合成文字 (例如: 頭痛(3次), 胸悶(2次)...)
        symptom_str = ", ".join([f"{row[0]}({row[1]}次)" for row in public_health_symptoms])
        
        # 3. 呼叫 Gemini 撰寫公告草稿
        prompt = f"""
        你是一位專業的醫療公衛管理員。
        請根據我們醫院系統近期民眾最常查詢的 Top 10 症狀數據：
        【{symptom_str}】
        
        請幫我撰寫一段「簡短、溫暖且專業」的系統公告提醒文字（嚴格限制在 50 字左右）。
        內容需要包含：
        1. 根據這些症狀，推測近期可能流行的疾病（如流感、腸胃炎、心血管問題等）。
        2. 給予民眾一句簡單的預防衛教提醒。
        
        ※ 請直接回傳純文字，不要包含任何 HTML 標籤、星號(*)或 Markdown 語法，因為這將直接讓管理員複製成跑馬燈使用。
        """

        response = generate_gemini_content(prompt, feature='symptom_trend_announcement')
        
        return jsonify({'result': response.text.strip()})
        
    except GeminiQuotaExceeded as e:
        print(f"⚠️ 症狀趨勢 Gemini 額度已滿，改用本地端: {e}")
        notify_admin_ai_quota('symptom_trend_announcement', e)
        log_ai_usage("local", "local_statistics", "symptom_trend_announcement", "success", "Gemini quota exceeded")
        return jsonify({'result': generate_local_symptom_trend_announcement(top_symptoms), 'mode': 'local'})

    except Exception as e:
        print(f"❌ AI 趨勢分析失敗: {e}")
        log_ai_usage("local", "local_statistics", "symptom_trend_announcement", "success", e)
        return jsonify({'result': generate_local_symptom_trend_announcement(top_symptoms), 'mode': 'local'})

ensure_batch_scheduler_started()

def get_network_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(('8.8.8.8', 80))
            return sock.getsockname()[0]
    except OSError:
        return None

if __name__ == '__main__':
    host = '0.0.0.0'
    port = 5008
    local_url = f'http://127.0.0.1:{port}'
    network_ip = get_network_ip()
    network_url = f'http://{network_ip}:{port}' if network_ip else None

    print('\n' + '=' * 50)
    print('網站已啟動，請在瀏覽器開啟：')
    print(f'* Running on {local_url}')
    if network_url:
        print(f'* Running on {network_url}')
    print('=' * 50 + '\n')

    app.run(host=host, debug=False, port=port)
