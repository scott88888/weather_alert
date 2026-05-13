import time
import logging
import json
import os
import datetime
from logging.handlers import TimedRotatingFileHandler

# 基礎組件
from file_reader import WeatherFileReader
from weather_parser import WeatherParser
from gecode_to_range import RoadNetworkLookup

# 三大任務模組
from alert_sync_engine import AlertSyncEngine
from mq_sender import MQSender
from redis_sender import RedisSender
from line_notify_engine import LineNotifyEngine
from config import TARGET_FOLDERS, SOURCE_FOLDER, INCIDENT_TYPE_MAP
# ==========================================
# 獨立日誌配置 (確保 Log 分開)
# ==========================================
def setup_task_logger(name, filename):
    if not os.path.exists("logs"):
        os.makedirs("logs")
    
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # 避免重複添加 Handler
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler = TimedRotatingFileHandler(
            os.path.join("logs", filename), 
            when="midnight", 
            interval=1, 
            backupCount=30, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 終端機同步輸出 (可選)
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)
        
    return logger

# 初始化三組 Logger
mq_log = setup_task_logger("MQ_Sync", "weather_mq.log")
redis_log = setup_task_logger("Redis_Sync", "weather_redis.log")
line_log = setup_task_logger("Line_Notify", "weather_line.log")

def run_mq_task(reader, parser, road_lookup, sync_engine, mq_sender, latest_files):
    """任務 A：MQ 路網同步"""
    mq_log.info("--- 開始執行 MQ 同步任務 ---")
    
    # 這裡應使用 TARGET_FOLDERS 或從 config 引入的監控清單
    for folder in TARGET_FOLDERS:
        # 僅處理 MQ 相關的資料夾 (濃霧、雨、風、颱風)
        if folder not in ["W-C0033-001", "W-C0033-003", "W-C0033-006", "W-C0034-001"]:
            continue
            
        try:
            file_path = latest_files.get(folder)
            parsed_data = None
            
            if file_path:
                mq_log.info(f"===== 開始處理 {folder}: {file_path.name} =====")
                parsed_data = parser.parse(folder, file_path)
            else:
                mq_log.debug(f"[{folder}] 無新檔案，執行例行過期檢查...")

            # 準備解析結果與路網比對
            final_parsed_results = []
            if parsed_data:
                geocodes = parsed_data.get('geocodes', set())
                matched_segments = road_lookup.get_segments_by_geocodes(geocodes)
                
                for seg in matched_segments:
                    # 統一時間格式處理
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

            # 同步資料庫與發送 MQ
            to_cancel_actions, to_active_msgs = sync_engine.sync(final_parsed_results, folder)

            # 處理解除
            for msg, db_record in to_cancel_actions:
                inc_id = db_record['incidentId']
                routing_key = f"aprOpPt.{msg['content'].get('controlCenterId', '10')}"
                try:
                    mq_sender.send_alert(msg, routing_key)
                    sync_engine.db.delete_alert(inc_id)
                    mq_log.info(f"   [DB更新] 解除成功 ID: {inc_id}")
                except Exception as e:
                    mq_log.warning(f"   [MQ失敗] ID {inc_id} 解除發送失敗: {e}")

            # 處理成立
            for msg in to_active_msgs:
                db_data = msg.pop('_db_payload', None)
                inc_id = msg['content']['incidentId']
                routing_key = f"aprOpPt.{msg['content'].get('controlCenterId', '10')}"
                try:
                    mq_sender.send_alert(msg, routing_key)
                    if db_data:
                        sync_engine.db.insert_alert(db_data)
                        mq_log.info(f"   [DB更新] 成立成功 ID: {inc_id}")
                except Exception as e:
                    mq_log.error(f"   [MQ失敗] ID {inc_id} 成立發送失敗: {e}")

        except Exception as folder_err:
            mq_log.error(f"處理 {folder} 時發生錯誤: {folder_err}", exc_info=True)

def run_redis_task(parser, redis_sender, latest_files):
    """任務 B：高低溫 Redis 備存"""
    redis_log.info("--- 開始執行 Redis 資料備存任務 ---")
    
    target_configs = {
        "W-C0033-004": parser._parse_004_cold,
        "W-C0033-005": parser._parse_005_heat
    }
    
    for folder, parse_func in target_configs.items():
        file_path = latest_files.get(folder)
        
        if not file_path:
            redis_log.debug(f" [{folder}] 目前無新檔案可同步。")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            
            parsed_result = parse_func(raw_data)
            
            if parsed_result:
                redis_log.info(f" [{folder}] 解析成功，推送內容: {json.dumps(parsed_result, ensure_ascii=False)}")
                success = redis_sender.send_alert_to_redis(parsed_result)
                if success:
                    redis_log.info(f" [{folder}] 成功推送至 Redis。")
            else:
                redis_log.info(f" [{folder}] 此檔案不含橙色或紅色警報，跳過。")

        except Exception as e:
            redis_log.error(f" [{folder}] 處理異常: {e}")

def run_line_task(line_engine, latest_files):
    """任務 C：LINE 即時通知 (新整合功能)"""
    line_log.info("--- 開始執行 LINE 通知任務 ---")
    line_engine.run(latest_files)
    line_log.info("--- 結束本次執行 LINE 通知任務 ---")
def main():
    # 1. 實例化所有共用組件
    reader = WeatherFileReader() #
    parser = WeatherParser() #
    road_lookup = RoadNetworkLookup()
    
    # 2. 實例化任務引擎
    sync_engine = AlertSyncEngine() #
    mq_sender = MQSender() #
    redis_sender = RedisSender() #
    line_engine = LineNotifyEngine()

    mq_log.info("氣象整合監控服務啟動...")

    while True:
        start_time = time.time()
        
        try:
            # 取得當前所有資料夾的最新檔案清單
            latest_files = reader.get_latest_files()

            # # --- 執行 MQ 同步 (獨立 Try-Catch) ---
            try:
                run_mq_task(reader, parser, road_lookup, sync_engine, mq_sender, latest_files)
            except Exception as e:
                mq_log.error(f"MQ 任務異常: {e}", exc_info=True)

            # # --- 執行 Redis 備存 (獨立 Try-Catch) ---
            try:
                run_redis_task(parser, redis_sender, latest_files)
            except Exception as e:
                redis_log.error(f"Redis 任務異常: {e}", exc_info=True)

            # --- 執行 LINE 通知 (獨立 Try-Catch) ---
            try:
                run_line_task(line_engine, latest_files)
            except Exception as e:
                line_log.error(f"LINE 任務異常: {e}", exc_info=True)

        except Exception as global_e:
            mq_log.error(f"主循環全局異常: {global_e}")

        # --- 控制每分鐘執行一次 ---
        elapsed = time.time() - start_time
        sleep_time = max(1, 60 - elapsed)
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()