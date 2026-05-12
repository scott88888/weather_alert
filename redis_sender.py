import redis
import json
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from config import REDIS_CONFIG, FIXED_REDIS_KEY, REDIS_LOG_FILE

# --- 獨立 Logger 配置 ---
if not os.path.exists("logs"):
    os.makedirs("logs")

redis_logger = logging.getLogger("RedisSender")
redis_logger.setLevel(logging.INFO)

if not redis_logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    # 使用時間滾動紀錄，與主系統日誌區隔
    handler = TimedRotatingFileHandler(REDIS_LOG_FILE, when="midnight", interval=1, backupCount=30, encoding='utf-8')
    handler.setFormatter(formatter)
    redis_logger.addHandler(handler)

class RedisSender:
    def __init__(self):
        self.config = REDIS_CONFIG
        self.redis_key = FIXED_REDIS_KEY

    def send_alert_to_redis(self, alert_data: dict):
        """
        將高低溫特報資料發送到 Redis。
        alert_data 格式需包含: counties, alert_type, effective, expires
        """
        # 額外安全性檢查：如果有效結束時間小於現在，則不發送
        try:
            expires_dt = datetime.strptime(alert_data['expires'], "%Y/%m/%d %H:%M:%S")
            # if datetime.now() > expires_dt:
            #     redis_logger.info(f" [跳過] 資料已過期 (Expires: {alert_data['expires']}), 不發送到 Redis。")
            #     return False
        except Exception as e:
            redis_logger.error(f" [錯誤] 時間格式解析失敗，無法判斷是否過期: {e}")

        try:
            r = redis.StrictRedis(**self.config)
            
            # 將字典轉換為 JSON 字串
            json_data = json.dumps(alert_data, ensure_ascii=False)
            
            # 儲存 24 小時 (86400 秒)
            r.setex(self.redis_key, 86400, json_data)
            
            redis_logger.info(f" [成功] 已推送至 Redis ({self.redis_key}): {json_data}")
            return True
            
        except redis.exceptions.ConnectionError as e:
            redis_logger.error(f" [失敗] 無法連線到 Redis 伺服器: {e}")
        except Exception as e:
            redis_logger.error(f" [失敗] 發送資料到 Redis 時發生未知錯誤: {e}")
        return False    