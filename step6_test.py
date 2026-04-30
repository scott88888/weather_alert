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

# --- 日誌系統配置 ---
log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

# 1. 取得指定名稱的 Logger
logger = logging.getLogger("Step6_MQ_Integration")
logger.setLevel(logging.INFO)

# 2. 避免重複添加 Handler (重要：先清空舊的)
if not logger.handlers:
    log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    log_file = os.path.join(log_dir, "weather_sync.log")

    # 檔案 Handler
    log_handler = TimedRotatingFileHandler(
        log_file, 
        when="midnight", 
        interval=1, 
        backupCount=30,
        encoding='utf-8'
    )
    log_handler.setFormatter(log_formatter)
    logger.addHandler(log_handler)

    # 控制台 Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)

# 3. 關閉繼承關係，避免訊息傳遞給 Root Logger 導致重複輸出
logger.propagate = False

# 抑制 Pika 詳細日誌
logging.getLogger("pika").setLevel(logging.WARNING)

def run_sync_task(reader, parser, road_lookup, sync_engine, mq):
    """單次執行的同步任務邏輯"""
    # 取得最新檔案
    latest_files = reader.get_latest_files()

    for folder in TEST_FOLDERS:
        if folder not in latest_files:
            continue

        file_path = latest_files[folder]
        logger.info(f"--- 處理 {folder}: {file_path.name} ---")

        # 1. 解析氣象資料
        parsed_data = parser.parse(folder, file_path)
        if not parsed_data:
            continue

        # 2. 對照路網 (Geocode -> 路段)
        geocodes = parsed_data.get('geocodes', set())
        matched_segments = road_lookup.get_segments_by_geocodes(geocodes)

        # 3. 格式化為同步引擎需要的輸入
        final_parsed_results = []
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

        # 4. 同步資料庫並取得待發送訊息
        to_cancel, to_active = sync_engine.sync(final_parsed_results, folder)
        
        # 5. 動態路由發送到 RabbitMQ
        for msg in to_cancel + to_active:
            # 自動從內容中抓取控制中心代碼
            cc_id = msg['content'].get('controlCenterId')
            
            if cc_id:
                # 根據中心代碼自動對應路由
                routing_key = f"aprOpPt.{cc_id}" 
                mq.send_alert(msg, routing_key)
            else:
                logger.error(f"跳過發送：訊息內容缺失 controlCenterId (IncidentId: {msg['content'].get('incidentId')})")

        logger.info(f"完成 {folder}: 解除 {len(to_cancel)} 筆, 成立 {len(to_active)} 筆")

def main():
    logger.info("氣象同步服務啟動（常駐循環模式）...")
    
    # 初始化模組
    reader = WeatherFileReader()
    parser = WeatherParser()
    road_lookup = RoadNetworkLookup()
    sync_engine = AlertSyncEngine()
    mq = MQSender()

    while True:
        try:
            start_time = time.time()
            
            # 執行任務邏輯
            run_sync_task(reader, parser, road_lookup, sync_engine, mq)
            
            # 計算執行時長並計算休眠時間 (確保間隔為 60 秒)
            elapsed = time.time() - start_time
            sleep_time = max(1, 60 - elapsed)
            
            logger.info(f"循環結束，執行耗時 {elapsed:.2f}s，休眠 {sleep_time:.2f}s")
            time.sleep(sleep_time)

        except Exception as e:
            logger.error(f"服務運行異常: {e}")
            time.sleep(10)  # 異常後稍作等待再重試

if __name__ == "__main__":
    main()