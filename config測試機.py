import pymysql
import redis
from pathlib import Path

# --- 基礎路徑 ---
BASE_DIR = Path(__file__).resolve().parent
SOURCE_FOLDER = BASE_DIR / "source2"

# --- 目標監控資料夾清單 ---
# 包含所有需要監控的氣象類型
TARGET_FOLDERS = [
    "W-C0033-001", "W-C0033-003", "W-C0033-006", 
    "W-C0033-004", "W-C0033-005", "W-C0034-001"
]
# TARGET_FOLDERS = ["W-C0033-001", "W-C0033-003", "W-C0033-006", "W-C0034-001"]
# --- LINE 通知配置 (新增) ---
# LINE_CONFIG = {
#     "CHANNEL_ACCESS_TOKEN": "mWxt76XBmn49LyKrny9x3swvE+llc3eoqlILbaI52BA9hrPBg/Kgg1ntTQ94i+kynCYZOISdgPXxsm0YtZwmktYZHXSS+fRDRmeomvqTeT0WR8GvQzlYv9Xjo4uJ7y8PT6PmgU50X6RRbknt2H3VJgdB04t89/1O/w1cDnyilFU=",
#     "TARGET_USER_ID": "U3bcbfaef1c6613b2ec00f429b194aaed",
# }
LINE_CONFIG = {
    "CHANNEL_ACCESS_TOKEN": "QgQgHW0MwarV3GgnBEA7VKodK7eDonwWXI1bNLAmsZNFkMvOCuvUtFwnfPSpvj63KS/DsvmUL9luRjirNb8iH2XfEztqQIzcymA0udHMsrs+n9kALDn5lWRZhvxyKj0uL5TDm2C+2i5iyVm5UfzjBgdB04t89/1O/w1cDnyilFU=",
    "TARGET_USER_ID": "U48aa97f68f7ee05fe7f74b042c4ccf96",
}
# --- LINE 專用 Redis Key 命名規範 (新增) ---
# 依照要求調整為 weather_s:line_英文名
LINE_REDIS_KEYS = {
    "W-C0033-001": "weather_s:line_fog",      # 濃霧
    "W-C0033-003": "weather_s:line_rain",     # 豪大雨
    "W-C0033-006": "weather_s:line_wind",     # 強風
    "W-C0033-004": "weather_s:line_cold",     # 低溫
    "W-C0033-005": "weather_s:line_heat",     # 高溫
    "W-C0034-001": "weather_s:line_typhoon",  # 颱風
}

# --- 災害類別與 TCSS 代碼對照 ---
INCIDENT_TYPE_MAP = {
    "W-C0033-001": 80,  # 濃霧
    "W-C0033-003": 78,  # 豪大雨
    "W-C0033-004": 82,  # 低溫
    "W-C0033-005": 81,  # 高溫
    "W-C0033-006": 79,  # 強風
    "W-C0034-001": 77,  # 颱風
}

# --- 資料庫連線配置 (DB 110) ---
DB_CONFIG = {
    "host": "192.168.2.110",
    "port": 3306,
    "user": "freeway",
    "password": "sochamp999",
    "database": "tcss",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}
# --- 資料庫連線配置 (線上) ---
# DB_CONFIG = {
#     "host": "10.105.6.9",
#     "port": 3306,
#     "user": "freeway",
#     "password": "1a2b3c4d5e",
#     "database": "tcss",
#     "charset": "utf8mb4",
#     "cursorclass": pymysql.cursors.DictCursor
# }



# --- Redis 連線配置 (DB 0) ---
REDIS_CONFIG = {
    "host": "192.168.2.107",
    "port": 6379,
    "db": 0,
    "password": "sochamp999",
    "decode_responses": True
}
# --- Redis 連線配置 (線上) ---
# REDIS_CONFIG = {
#     "host": "10.105.6.100",
#     "port": 6379,
#     "db": 0,
#     "password": "sochamp999",
#     "decode_responses": True
# }
# --- 日誌配置路徑 (補上這行) ---
REDIS_LOG_FILE = "logs/redis_sync.log"

# 舊有的高低溫 JSON 同步用 Key
FIXED_REDIS_KEY = "weather_s:high_low"

# --- RabbitMQ 連線配置 ---
MQ_CONFIG = {
    "host": "192.168.2.106",
    "port": 5672,
    "user": "freeway",
    "password": "sochamp999",
    "virtual_host": "/freeway",
    "exchange": "tcss.AprOpPt",
}

# --- 工具函數 ---
def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

def get_redis_client():
    return redis.StrictRedis(**REDIS_CONFIG)