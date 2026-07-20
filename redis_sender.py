import redis
import json
import logging
import os
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
# 👑 調整引入：加入 REDIS_CONFIG
from config import REDIS_HOSTS, REDIS_COMMON_CONFIG, FIXED_REDIS_KEY, REDIS_LOG_FILE, REDIS_CONFIG

# --- 獨立 Logger 配置 ---
if not os.path.exists("logs"):
    os.makedirs("logs")

redis_logger = logging.getLogger("RedisSender")
redis_logger.setLevel(logging.INFO)

if not redis_logger.handlers:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler = TimedRotatingFileHandler(REDIS_LOG_FILE, when="midnight", interval=1, backupCount=30, encoding='utf-8')
    handler.setFormatter(formatter)
    redis_logger.addHandler(handler)

class RedisSender:
    def __init__(self):
        # 基底共用設定
        self.common_config = REDIS_COMMON_CONFIG
        self.redis_key = FIXED_REDIS_KEY
        self.config = REDIS_CONFIG  # 👑 引入對外標準設定

    def send_alert_to_redis(self, alert_data: dict):      
        # 額外安全性檢查：如果有效結束時間小於現在，則不發送
        try:
            expires_dt = datetime.strptime(alert_data['expires'], "%Y/%m/%d %H:%M:%S")
            if datetime.now() > expires_dt:
                redis_logger.info(f" [跳過] 資料已過期 (Expires: {alert_data['expires']}), 不發送到 Redis。")
                return False
        except Exception as e:
            redis_logger.error(f" [錯誤] 時間格式解析失敗，無法判斷是否過期: {e}")

        try:
            # 👑 讀取開關狀態，判斷是單機測試還是正式分流
            current_method = self.config.get("METHOD", "pool")

            if current_method == "single":
                # 【單機測試模式】直接使用 config 中定義好的測試機 host 與 port
                target_node = {
                    "host": self.config.get("host", "192.168.2.107"),
                    "port": self.config.get("port", 6379)
                }
                center_id = "single"
            else:
                # 【正式分流模式】動態取得控制中心 ID 并查詢對應的正式機 IP
                center_id = alert_data.get('controlCenterId') or alert_data.get('content', {}).get('controlCenterId', '10')
                target_node = REDIS_HOSTS.get(str(center_id), REDIS_HOSTS["10"])
            
            conn_config = {**self.common_config, **target_node}
            
            # 建立 Redis 連線實例
            r = redis.StrictRedis(**conn_config)
            
            # 將字典轉換為 JSON 字串
            json_data = json.dumps(alert_data, ensure_ascii=False)
            
            # 儲存 24 小時 (86400 秒)
            r.setex(self.redis_key, 86400, json_data)
            redis_logger.info(f" [Redis成功] 成功寫入控制中心 {center_id} 的 Redis 伺服器 ({conn_config['host']}) -> Key: {self.redis_key}")
            return True
            
        except Exception as e:
            redis_logger.error(f" [Redis失敗] 寫入 Redis 發生異常: {e}", exc_info=True)
            return False