import pika
import json
import logging
import time
# 引入 MQ_HOSTS 對照表
from config import MQ_CONFIG, MQ_HOSTS

logger = logging.getLogger("MQSender")

class MQSender:
    def __init__(self):
        self.config = MQ_CONFIG
        self.credentials = pika.PlainCredentials(self.config['user'], self.config['password'])
        self.connection = None
        self.channel = None
        self.current_host = None  # 👑 新增：紀錄目前連線的 IP

    def _connect(self, target_host):
        if self.connection and (self.connection.is_open and self.current_host != target_host):
            logger.info(f" [MQ] 目標 IP 改變 ({self.current_host} -> {target_host})，關閉舊連線。")
            try:
                self.connection.close()
            except Exception:
                pass
            self.connection = None

        if not self.connection or self.connection.is_closed:
            params = pika.ConnectionParameters(
                host=target_host,
                port=self.config['port'],
                virtual_host=self.config['virtual_host'],
                credentials=self.credentials,
                connection_attempts=1,
                retry_delay=2
            )
            try:
                self.connection = pika.BlockingConnection(params)
                self.channel = self.connection.channel()
                self.channel.exchange_declare(
                    exchange=self.config['exchange'], 
                    exchange_type='topic', 
                    durable=False
                )
                self.current_host = target_host
            # 👑 捕捉特定的認證與 Vhost 錯誤
            except pika.exceptions.ProbableAuthenticationError as auth_err:
                logger.error(f"❌ [MQ連線失敗] 帳號密碼錯誤，或者該帳號沒有權限存取 Virtual Host '{self.config['virtual_host']}'！")
                raise auth_err
            except pika.exceptions.ProbableAccessDeniedError as access_err:
                logger.error(f"❌ [MQ連線失敗] 存取被拒絕！請檢查 Vhost 權限或 Exchange 是否存在。")
                raise access_err
            except Exception as e:
                logger.error(f"❌ [MQ連線失敗] 其他連線錯誤: {e}")
                raise e
    def send_alert(self, message_dict, routing_key):

        max_retries = 3
        retry_delay = 2  # 每次重試中斷 2 秒
        
        # 👑 讀取開關狀態
        current_method = self.config.get("METHOD", "pool")

        if current_method == "single":
            # 【單機測試模式】直接抓 config 設定好的 host，不寫死任何 IP 字串
            target_host = self.config.get("SINGLE_HOST", self.config.get("host"))
            center_id = "single"
        else:
            # 【正式分流模式】從訊息內容中動態取得控制中心 ID，並查出對應的正式機 IP
            center_id = message_dict.get('content', {}).get('controlCenterId', '10')
            target_host = MQ_HOSTS.get(str(center_id), "10.105.6.119")

        # 將字典轉為 JSON 字串
        message = json.dumps(message_dict, ensure_ascii=False)

        for attempt in range(1, max_retries + 1):
            try:
                # 👑 檢查是否需要建立連線（或換 IP 連線）
                if not self.connection or self.connection.is_closed or self.current_host != target_host:
                    logger.info(f" [MQ] 正在連線至控制中心 [{center_id}] IP: {target_host} (嘗試第 {attempt} 次)")
                    self._connect(target_host)
                
                # 嘗試發送訊息
                self.channel.basic_publish(
                    exchange=self.config['exchange'],
                    routing_key=routing_key,
                    body=message,
                    properties=pika.BasicProperties(content_type='application/json', delivery_mode=2)
                )
                logger.info(f" [MQ] 成功發送至 {target_host} -> {routing_key}")
                return  # 🎉 發送成功，直接結束函式跳出！

            except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError, 
                    pika.exceptions.ChannelClosedByBroker, ConnectionResetError) as e:
                
                logger.warning(f" [MQ失敗] 第 {attempt} 次發送失敗，原因: {e}")
                
                self.connection = None
                self.channel = None
                self.current_host = None
                
                if attempt < max_retries:
                    logger.info(f" 等待 {retry_delay} 秒後進行下一次重試...")
                    time.sleep(retry_delay)
                else:
                    logger.error(" [MQ嚴重失敗] 原地重試 3 次均宣告失敗，全面中斷任務。")
                    raise e
            except Exception as e:
                logger.error(f" [MQ] 發送發生未知錯誤: {e}")
                raise e
    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()