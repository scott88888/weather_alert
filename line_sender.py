import requests
import json
import logging
import re
from config import LINE_CONFIG, get_redis_client, LINE_REDIS_KEYS, FORWARD_API_CONFIG

logger = logging.getLogger("Line_Notify") 

class LineSender:
    def __init__(self):
        # 👑 讀取切換模式 ('forward' 或 'official')
        self.method = LINE_CONFIG.get("METHOD", "official")
        
        # 官方 API 參數
        self.token = LINE_CONFIG["CHANNEL_ACCESS_TOKEN"]
        self.target_id = LINE_CONFIG["TARGET_USER_ID"]
        
        # 中繼伺服器 API 參數
        self.forward_url = FORWARD_API_CONFIG["URL"]
        self.forward_token = FORWARD_API_CONFIG["BEARER_TOKEN"]
        self.forward_group_id = FORWARD_API_CONFIG["GROUP_ID"]
        
        # Redis 組件
        self.redis = get_redis_client()

    def _send_push(self, message: str):
        """
        發送 LINE 訊息調度核心 (👑 支援動態切換通道)
        """
        if self.method == "forward":
            return self._send_via_forward(message)
        else:
            return self._send_via_official(message)

    def _send_via_official(self, message: str):
        """
        管道 A：原本的 LINE 官方 Push 訊息
        """
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
            
            clean_msg = message.replace('\n', ' ')
            logger.info(f" [LINE官方推送成功] 內容: {clean_msg}")
            return True
        except Exception as e:
            logger.error(f" [LINE官方推送失敗] 錯誤原因: {str(e)} | 嘗試發送內容: {message}")
            return False

    def _send_via_forward(self, message: str):
        """
        管道 B：發送到中繼伺服器 API
        """
        headers = {
            "Authorization": f"Bearer {self.forward_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "group_id": self.forward_group_id,
            "text": message
        }
        try:
            response = requests.post(self.forward_url, headers=headers, data=json.dumps(payload), verify=False, timeout=10)
            response.raise_for_status()
            
            # 檢查轉發平台回傳的狀態是否為 success
            res_data = response.json()
            if res_data.get("status") == "success":
                clean_msg = message.replace('\n', ' ')
                logger.info(f" [LINE中繼轉發成功] 內容: {clean_msg}")
                return True
            else:
                logger.error(f" [LINE中繼轉發失敗] 平台回應錯誤: {res_data} | 嘗試發送內容: {message}")
                return False
                
        except Exception as e:
            logger.error(f" [LINE中繼轉發連線失敗] 錯誤原因: {str(e)} | 嘗試發送內容: {message}")
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
            logger.debug(f" [LINE跳過] {folder_name} 地區無變動。")