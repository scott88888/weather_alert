import pika
import json
import logging
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
            # 宣告 Exchange (Topic 模式)
            self.channel.exchange_declare(
                exchange=self.config['exchange'], 
                exchange_type='topic', 
                durable=False
            )

    def send_alert(self, message_dict, routing_key):
        try:
            # 關鍵：每次發送前確保連線是開啟的
            if not self.connection or self.connection.is_closed:
                logger.info("檢測到 MQ 連線已斷開，嘗試重新連線...")
                self._connect()
                
            message = json.dumps(message_dict, ensure_ascii=False)
            self.channel.basic_publish(
                exchange=self.config['exchange'],
                routing_key=routing_key,
                body=message,
                properties=pika.BasicProperties(content_type='application/json', delivery_mode=2)
            )
            logger.info(f" [MQ] 成功發送至 {routing_key}")
        except (pika.exceptions.AMQPConnectionError, pika.exceptions.StreamLostError):
            logger.error("MQ 連線遺失，正在嘗試清除舊連線以利下次重試...")
            self.connection = None # 清空狀態，下次調用會觸發 _connect
            raise # 務必拋出異常，讓 step6 知道發送失敗
        except Exception as e:
            logger.error(f" [MQ] 發送發生未知錯誤: {e}")
            raise

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()