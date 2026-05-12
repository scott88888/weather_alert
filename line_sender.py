import requests
import json
import logging
import re
from config import LINE_CONFIG, get_redis_client, LINE_REDIS_KEYS

# 確保名稱與 main_service 中的 setup_task_logger 一致
logger = logging.getLogger("Line_Notify") 

class LineSender:
    def __init__(self):
        self.token = LINE_CONFIG["CHANNEL_ACCESS_TOKEN"]
        self.target_id = LINE_CONFIG["TARGET_USER_ID"]
        self.redis = get_redis_client()

    def _send_push(self, message: str):
        url = "https://api.line.me/v2/bot/message/push"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        payload = {
            "to": self.target_id,
            "messages": [{"type": "text", "text": message}]
        }
        try:
            response = requests.post(url, headers=headers, data=json.dumps(payload))
            response.raise_for_status()
            
            # 修正 SyntaxError: 預先處理換行符號
            clean_msg = message.replace('\n', ' ')
            logger.info(f" [LINE推送成功] 內容: {clean_msg}")
            return True
        except Exception as e:
            logger.error(f" [LINE推送失敗] 錯誤原因: {str(e)} | 嘗試發送內容: {message}")
            return False

    def check_state_and_push(self, folder_name: str, current_locs: list, message_template_func):
        redis_key = LINE_REDIS_KEYS.get(folder_name)
        if not redis_key:
            return

        current_locs.sort()
        curr_str = ",".join(current_locs)
        last_str = self.redis.get(redis_key)

        if not current_locs:
            if last_str:
                self.redis.delete(redis_key)
                logger.info(f" [LINE狀態變更] {folder_name} 警報解除，清空 Redis。")
            return

        if last_str != curr_str:
            msg = message_template_func(current_locs)
            if self._send_push(msg):
                self.redis.set(redis_key, curr_str)
                logger.info(f" [LINE狀態變更] {folder_name} 更新地區: {curr_str}")
        else:
            # 使用 debug 等級避免正式 Log 太雜
            logger.debug(f" [LINE跳過] {folder_name} 地區無變動。")