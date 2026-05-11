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

# --- 日誌配置 ---
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
    now = datetime.datetime.now()

    for folder in TEST_FOLDERS:
        try:
            if folder not in latest_files:
                # 即使沒新檔案，也要進去檢查是否有過期事件要解除
                logger.debug(f"[{folder}] 無新檔案，執行例行過期檢查...")
                file_path = None
                parsed_data = None
            else:
                file_path = latest_files[folder]
                logger.info(f"===== 開始處理 {folder}: {file_path.name} =====")
                parsed_data = parser.parse(folder, file_path)

            # 準備解析結果
            final_parsed_results = []
            if parsed_data:
                geocodes = parsed_data.get('geocodes', set())
                matched_segments = road_lookup.get_segments_by_geocodes(geocodes)
                
                for seg in matched_segments:
                    eff = parsed_data.get('startTime') or parsed_data.get('effective')
                    exp = parsed_data.get('endTime') or parsed_data.get('expires')
                    if isinstance(exp, str) and exp:
                        exp_dt = datetime.datetime.strptime(exp[:19].replace('T', ' '), "%Y-%m-%d %H:%M:%S")
                    else:
                        exp_dt = exp
                    final_parsed_results.append({
                        **seg, 
                        "folderName": folder, 
                        "effectiveTime": eff, 
                        "expiresTime": exp_dt
                    })

            # --- 取得待處理清單 (包含檔案比對 & DB 強制過期掃描) ---
            to_cancel_actions, to_active_msgs = sync_engine.sync(final_parsed_results, folder)

            # 1. 處理解除階段 (Level 1) - 必須 MQ 成功才刪除 DB
            if to_cancel_actions:
                logger.info(f" > [解除階段] 發現 {len(to_cancel_actions)} 筆待結束事件")
                for msg, db_record in to_cancel_actions:
                    inc_id = db_record['incidentId']
                    routing_key = f"aprOpPt.{msg['content'].get('controlCenterId', '10')}"
                    
                    success = False
                    for retry in range(2): # 簡單重試 1 次 (共 2 次嘗試)
                        try:
                            mq.send_alert(msg, routing_key)
                            sync_engine.db.delete_alert(inc_id)
                            logger.info(f"   [DB更新] 解除成功，已移除 ID: {inc_id}")
                            success = True
                            break
                        except Exception as e:
                            logger.warning(f"   [MQ重試] ID {inc_id} 解除發送失敗(第{retry+1}次): {e}")
                            time.sleep(1)
                    
                    if not success:
                        logger.error(f"   [關鍵失敗] ID {inc_id} 經過重試仍無法發送，保留 DB 以待下次循環。")

            # 2. 處理成立階段 (Level 2) - 必須 MQ 成功才寫入 DB
            if to_active_msgs:
                logger.info(f" > [成立階段] 發現 {len(to_active_msgs)} 筆新事件")
                for msg in to_active_msgs:
                    db_data = msg.pop('_db_payload', None)
                    inc_id = msg['content']['incidentId']
                    routing_key = f"aprOpPt.{msg['content'].get('controlCenterId', '10')}"

                    try:
                        mq.send_alert(msg, routing_key)
                        if db_data:
                            sync_engine.db.insert_alert(db_data)
                            logger.info(f"   [DB更新] 成立成功，已記錄新警報 ID: {inc_id}")
                    except Exception as e:
                        logger.error(f"   [致命錯誤] ID {inc_id} 成立發送失敗，不寫入 DB，留待下次循環重試: {e}")

            if file_path:
                logger.info(f"===== {folder} 處理完成 =====\n")

        except Exception as folder_err:
            logger.error(f"處理資料夾 {folder} 時發生未預期錯誤: {folder_err}", exc_info=True)

def main():
    logger.info("氣象同步服務啟動 (原子性增強模式)...")
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
            logger.error(f"主程序循環異常: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()