import pymysql
import redis
from pathlib import Path

# --- 基礎路徑 ---
BASE_DIR = Path(__file__).resolve().parent
SOURCE_FOLDER = BASE_DIR / "source2"
# ==========================================
# 氣象整合監控服務 - 運行模式控制
# 0 = 全開 (預設)
# 1 = 僅 MQ 開啟
# 2 = 僅 Redis 開啟
# 3 = 僅 LINE 開啟
# 4 = 全關
# ==========================================
SERVICE_MODE = 0


# --- 目標監控資料夾清單 ---
# 包含所有需要監控的氣象類型
TARGET_FOLDERS = [
    "W-C0033-001", "W-C0033-003", "W-C0033-006", 
    "W-C0033-004", "W-C0033-005", "W-C0034-001"
]

# --- LINE 通知配置 (新增切換開關) ---
LINE_CONFIG = {
    # 發送模式切換：'forward' (中繼伺服器) 或 'official' (官方API)
    "METHOD": "forward", 
    
    # 官方管道參數
    "CHANNEL_ACCESS_TOKEN": "QgQgHW0MwarV3GgnBEA7VKodK7eDonwWXI1bNLAmsZNFkMvOCuvUtFwnfPSpvj63KS/DsvmUL9luRjirNb8iH2XfEztqQIzcymA0udHMsrs+n9kALDn5lWRZhvxyKj0uL5TDm2C+2i5iyVm5UfzjBgdB04t89/1O/w1cDnyilFU=",
    "TARGET_USER_ID": "U48aa97f68f7ee05fe7f74b042c4ccf96",
}

# 中繼伺服器管道參數
FORWARD_API_CONFIG = {
    "URL": "https://10.104.6.31/api/apiSendMessage",
    "BEARER_TOKEN": "141355|td5aFdvHR1s4Z6KCsJ9A6y3MS2lpZncFdOExlys91115ccc1",
    "GROUP_ID": "tfb-test-a"
}

# --- LINE 專用 Redis Key 命名規範 ---
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

# =================================================================
# 👑 資料庫（MySQL）連線配置 (含模式切換開關)
# =================================================================
# 模式切換：'pool' (正式線上機) 或 'single' (測試機 110)
DB_ENV_METHOD = "pool" 

# 測試機 110 設定
_DB_SINGLE_CONFIG = {
    "host": "192.168.2.110",
    "port": 3306,
    "user": "freeway",
    "password": "sochamp999",
    "database": "tcss",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

# 正式線上機設定
_DB_POOL_CONFIG = {
    "host": "10.105.6.9",
    "port": 3306,
    "user": "freeway",
    "password": "sochamp999",
    "database": "tcss",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

if DB_ENV_METHOD == "pool":
    DB_CONFIG = _DB_POOL_CONFIG
else:
    DB_CONFIG = _DB_SINGLE_CONFIG


# =================================================================
# 👑 Redis 連線與分流配置 (優化開關邏輯)
# =================================================================
# 模式切換：'pool' (四區分流) 或 'single' (單一固定測試機)
_REDIS_METHOD = "pool"

# 各區伺服器配置 (當 _REDIS_METHOD = 'pool' 時使用)
REDIS_HOSTS = {
    "10": {"host": "10.105.6.110", "port": 6379},  # 北區
    "20": {"host": "10.105.6.120", "port": 6379},  # 坪林
    "30": {"host": "10.105.6.130", "port": 6379},  # 中區
    "40": {"host": "10.105.6.140", "port": 6379},  # 南區
}

# Redis 其他共用配置
REDIS_COMMON_CONFIG = {
    "db": 0,
    "password": "sochamp999",
    "decode_responses": True
}

# 👑 統一對外格式：讓 redis_sender.py 讀取標準的變數
REDIS_CONFIG = {
    "METHOD": _REDIS_METHOD,
    "host": "192.168.2.107",   # 預設測試機 IP，當 single 模式時固定用此值
    "port": 6379,
    **REDIS_COMMON_CONFIG       # 合併密碼與庫別
}
# 👑 補上 redis_sender.py 所缺少的常數變數
FIXED_REDIS_KEY = "weather:tcss_alert_data"  # 請根據你原本 redis_sender 用的 Key 命名，若不確定可先用這個
REDIS_LOG_FILE = "weather_redis.log"        # Redis 專屬 Log 檔名

# =================================================================
# 👑 RabbitMQ 連線與分流配置 (優化開關邏輯)
# =================================================================
# 模式切換：'pool' (四區分流) 或 'single' (單一固定測試機)
_MQ_METHOD = "pool"

# 各區伺服器配置 (當 _MQ_METHOD = 'pool' 時使用)
MQ_HOSTS = {
    "10": "10.105.6.119",      # 北區
    "20": "10.105.6.129",      # 坪林
    "30": "10.105.6.139",      # 中區
    "40": "10.105.6.72",       # 南區
}

# 其他共用連線配置
MQ_CONFIG = {
    "METHOD": _MQ_METHOD,      # 保留開關供後續發送端判斷是否分流
    "host": "192.168.2.106",   # 👑 預設值直接寫在這裡！當單機模式時就固定用此 IP
    "port": 5672,
    "user": "freeway",
    "password": "sochamp999",
    "virtual_host": "/freeway",
    "exchange": "tcss.AprOpPt",
}


# =================================================================
# 👑 工具函數 (確保定義在所有變數之後)
# =================================================================
def get_db_connection():
    """ 保持相容性的工具函數，直接解包變數即可 """
    return pymysql.connect(**DB_CONFIG)

def get_redis_client():
    """ 讓 LINE 模組獲取 Redis Client 時也支援模式切換 """
    if REDIS_CONFIG.get("METHOD") == "pool":
        # 分流模式下，LINE 狀態預設紀錄在北區 (10) 的 Redis
        node = REDIS_HOSTS["10"]
        conn_config = {**REDIS_COMMON_CONFIG, **node}
    else:
        # 單機模式 (修正為對應 REDIS_CONFIG 的小寫欄位)
        conn_config = {
            **REDIS_COMMON_CONFIG, 
            "host": REDIS_CONFIG["host"], 
            "port": REDIS_CONFIG["port"]
        }
    return redis.StrictRedis(**conn_config)