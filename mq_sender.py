import pika
import json
import logging
import time
from config import MQ_CONFIG

logger = logging.getLogger("MQSender")

class MQSender:
    def __init__(self):
        self.config = MQ_CONFIG
        self.credentials = pika.PlainCredentials(self.config['user'], self.config['password'])
        self.connection = None
        self.channel = None

    def _connect(self):
        if not self.connection or self.connection.is_closed:
            params = pika.ConnectionParameters(
                host=self.config['host'],
                port=self.config['port'],
                virtual_host=self.config['virtual_host'],
                credentials=self.credentials,
                connection_attempts=3,
                retry_delay=5
            )
            self.connection = pika.BlockingConnection(params)
            self.channel = self.connection.channel()
            self.channel.exchange_declare(
                exchange=self.config['exchange'], 
                exchange_type='topic', 
                durable=False
            )

    def send_alert(self, message_dict, routing_key):
        """
        發送警報訊息 (👑 補強版：遇到連線中斷，原地自動重試 3 次)
        """
        max_retries = 3
        retry_delay = 2  # 每次重試中斷 2 秒
        
        # 將字典轉為 JSON 字串
        message = json.dumps(message_dict, ensure_ascii=False)

        for attempt in range(1, max_retries + 1):
            try:
                # 確保連線存在
                if not self.connection or self.connection.is_closed:
                    logger.info(f" [MQ] 連線不存在或已關閉，正在建立連線... (嘗試第 {attempt} 次)")
                    self._connect()
                
                # 嘗試發送訊息
                self.channel.basic_publish(
                    exchange=self.config['exchange'],
                    routing_key=routing_key,
                    body=message,
                    properties=pika.BasicProperties(content_type='application/json', delivery_mode=2)
                )
                logger.info(f" [MQ] 成功發送至 {routing_key}")
                return  # 🎉 發送成功，直接結束函式跳出！

            except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError, 
                    pika.exceptions.ChannelClosedByBroker, ConnectionResetError) as e:
                
                logger.warning(f" [MQ失敗] 第 {attempt} 次發送失敗，原因: {e}")
                
                # 發生連線類錯誤，強制清空連線物件，以便下一次迴圈能重新開線
                self.connection = None
                self.channel = None
                
                if attempt < max_retries:
                    logger.info(f" 等待 {retry_delay} 秒後進行下一次重試...")
                    time.sleep(retry_delay)
                else:
                    # ❌ 3次都失敗了，倒下並拋出異常
                    logger.error(" [MQ嚴重失敗] 原地重試 3 次均宣告失敗，全面中斷任務。")
                    raise e
            except Exception as e:
                # 遇上其他非網路連線的未知錯誤（如語法錯誤），不重試直接拋出
                logger.error(f" [MQ] 發送發生未知錯誤: {e}")
                raise e

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()