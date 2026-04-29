import pymysql
import redis
from pathlib import Path

# --- 基礎路徑 ---
BASE_DIR = Path(__file__).resolve().parent
SOURCE_FOLDER = BASE_DIR / "source"

# --- 目標監控資料夾清單 ---
# 將 target_folders 定義在此，方便管理
TARGET_FOLDERS = ["W-C0033-001", "W-C0033-003", "W-C0033-006", "W-C0033-004", "W-C0033-005"]

# --- 災害類別與 TCSS 代碼對照 ---
INCIDENT_TYPE_MAP = {
    "W-C0033-001": 80,  # 濃霧
    "W-C0033-003": 78,  # 豪大雨
    "W-C0033-004": 82,  # 低溫
    "W-C0033-005": 81,  # 高溫
    "W-C0033-006": 79,  # 強風
}

# --- 資料庫連線配置 ---
DB_CONFIG = {
    "host": "192.168.2.110",
    "port": 3306,
    "user": "freeway",
    "password": "sochamp999",
    "database": "tcss",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# --- Redis 連線配置 ---
REDIS_CONFIG = {
    "host": "192.168.2.107",
    "port": 6379,
    "db": 0,
    "password": "sochamp999",
    "decode_responses": True
}

def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def get_redis_client():
    return redis.StrictRedis(**REDIS_CONFIG)