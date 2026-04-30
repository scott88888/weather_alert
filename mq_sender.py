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
        """
        將 dict 格式的訊息發送到指定的 Routing Key
        """
        try:
            self._connect()
            message = json.dumps(message_dict, ensure_ascii=False)
            
            self.channel.basic_publish(
                exchange=self.config['exchange'],
                routing_key=routing_key,
                body=message,
                properties=pika.BasicProperties(
                    content_type='application/json',
                    delivery_mode=2,  # 訊息持久化
                )
            )
            logger.info(f" [MQ] 成功發送至 {routing_key}")
        except Exception as e:
            logger.error(f" [MQ] 發送失敗: {e}")

    def close(self):
        if self.connection and self.connection.is_open:
            self.connection.close()