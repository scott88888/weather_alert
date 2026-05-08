import logging
import datetime
import os
import time
from logging.handlers import TimedRotatingFileHandler
from file_reader import WeatherFileReader
from weather_parser import WeatherParser
from gecode_to_range import RoadNetworkLookup
from alert_sync_engine import AlertSyncEngine
from mq_sender import MQSender
from config import TEST_FOLDERS

# --- 日誌配置保持不變 ---
log_dir = "logs"
if not os.path.exists(log_dir): os.makedirs(log_dir)

logger = logging.getLogger("Step6_MQ_Integration")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    log_file = os.path.join(log_dir, "weather_sync.log")
    log_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=30, encoding='utf-8')
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

logger.propagate = False
logging.getLogger("pika").setLevel(logging.WARNING)

def run_sync_task(reader, parser, road_lookup, sync_engine, mq):
    latest_files = reader.get_latest_files()

    for folder in TEST_FOLDERS:
        if folder not in latest_files: continue

        file_path = latest_files[folder]
        logger.info(f"===== 開始處理 {folder}: {file_path.name} =====")

        parsed_data = parser.parse(folder, file_path)
        if not parsed_data: continue

        geocodes = parsed_data.get('geocodes', set())
        matched_segments = road_lookup.get_segments_by_geocodes(geocodes)

        final_parsed_results = []
        for seg in matched_segments:
            eff = parsed_data.get('startTime') or parsed_data.get('effective')
            exp = parsed_data.get('endTime') or parsed_data.get('expires')
            if isinstance(exp, str) and exp:
                exp_dt = datetime.datetime.strptime(exp[:19].replace('T', ' '), "%Y-%m-%d %H:%M:%S")
            else:
                exp_dt = exp
            final_parsed_results.append({**seg, "folderName": folder, "effectiveTime": eff, "expiresTime": exp_dt})

        # --- 取得待處理清單 ---
        to_cancel_actions, to_active_msgs = sync_engine.sync(final_parsed_results, folder)

        # 1. 優先處理解除事件 (Level 1)
        if to_cancel_actions:
            logger.info(f" > [解除階段] 發現 {len(to_cancel_actions)} 筆待結束事件")
            for msg, db_record in to_cancel_actions:
                inc_id = db_record['incidentId']
                cc_id = msg['content'].get('controlCenterId')
                routing_key = f"aprOpPt.{cc_id}"
                
                try:
                    # 先發送 MQ
                    logger.info(f"   [MQ發送] 解除警報 ID: {inc_id} (路由: {routing_key})")
                    mq.send_alert(msg, routing_key)
                    
                    # MQ 發送成功後，才刪除 DB 紀錄
                    sync_engine.db.delete_alert(inc_id)
                    logger.info(f"   [DB更新] 已成功從資料庫移除 ID: {inc_id}")
                except Exception as e:
                    logger.error(f"   [錯誤] 解除 ID {inc_id} 失敗: {e}")

        # 2. 成立階段
        if to_active_msgs:
            for msg in to_active_msgs:
                db_data = msg.pop('_db_payload', None)
                inc_id = msg['content']['incidentId']
                routing_key = f"aprOpPt.{msg['content'].get('controlCenterId')}"

                try:
                    # 先發送 MQ
                    mq.send_alert(msg, routing_key)
                    
                    # 只有 MQ 沒拋出異常，這行才會執行
                    if db_data:
                        sync_engine.db.insert_alert(db_data)
                        logger.info(f"   [DB更新] 已成功記錄新警報 ID: {inc_id}")
                except Exception as e:
                    # 這裡如果失敗，db.insert_alert 不會執行
                    # 下一次 60 秒後的循環，sync_engine 會因為 DB 沒紀錄而再次判定為「新事件」並重發
                    logger.error(f"   [致命錯誤] ID {inc_id} 發送 MQ 失敗，不執行 DB 更新，留待下次循環重試: {e}")

        logger.info(f"===== {folder} 處理完成 =====\n")

def main():
    logger.info("氣象同步服務啟動 (順序優化模式)...")
    reader = WeatherFileReader(); parser = WeatherParser()
    road_lookup = RoadNetworkLookup(); sync_engine = AlertSyncEngine()
    mq = MQSender()

    while True:
        try:
            start_time = time.time()
            run_sync_task(reader, parser, road_lookup, sync_engine, mq)
            elapsed = time.time() - start_time
            sleep_time = max(1, 60 - elapsed)
            time.sleep(sleep_time)
        except Exception as e:
            logger.error(f"服務運行異常: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()