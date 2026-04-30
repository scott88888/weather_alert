import logging
import datetime
from file_reader import WeatherFileReader
from weather_parser import WeatherParser
from gecode_to_range import RoadNetworkLookup
from alert_sync_engine import AlertSyncEngine
from mq_sender import MQSender
from config import TEST_FOLDERS

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Step6_MQ_Integration")

def main():
    # 初始化所有模組
    reader = WeatherFileReader()
    parser = WeatherParser()
    road_lookup = RoadNetworkLookup()
    sync_engine = AlertSyncEngine()
    mq = MQSender()

    # 1. 取得所有目標資料夾的最新檔案
    # 注意：需確保 file_reader.py 中的 TARGET_FOLDERS 包含我們要測的四個
    latest_files = reader.get_latest_files()

    for folder in TEST_FOLDERS:
        if folder not in latest_files:
            logger.warning(f"跳過 {folder}: 找不到最新檔案")
            continue

        file_path = latest_files[folder]
        logger.info(f"--- 開始處理 {folder}: {file_path.name} ---")

        # 2. 解析氣象資料
        parsed_data = parser.parse(folder, file_path)
        if not parsed_data:
            continue

        # 3. 對照路網 (Geocode -> 路段)
        geocodes = parsed_data.get('geocodes', set())
        matched_segments = road_lookup.get_segments_by_geocodes(geocodes)

        # 4. 格式化為同步引擎需要的輸入
        final_parsed_results = []
        for seg in matched_segments:
            eff = parsed_data.get('startTime') or parsed_data.get('effective')
            exp = parsed_data.get('endTime') or parsed_data.get('expires')
            # 轉換 expires 為 datetime 物件供 sync 比較
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

        # 5. 同步資料庫並取得待發送 JSON (Level 1 為解除, Level 2 為成立)
        to_cancel, to_active = sync_engine.sync(final_parsed_results, folder)
        
        # 6. 發送到 RabbitMQ
        # 依據邏輯：解除送 level 1, 成立送 level 2
        for msg in to_cancel:
            # 您可以決定 routing_key：'aprOpPt.10' 或根據中心代碼 'aprOpPt.{id}'
            cc_id = msg['content'].get('controlCenterId', '10')
            routing_key = f"aprOpPt.{cc_id}" 
            mq.send_alert(msg, routing_key)

        for msg in to_active:
            cc_id = msg['content'].get('controlCenterId', '10')
            routing_key = f"aprOpPt.{cc_id}"
            mq.send_alert(msg, routing_key)

        logger.info(f"完成 {folder}: 解除 {len(to_cancel)} 筆, 成立 {len(to_active)} 筆")

    mq.close()
    logger.info("所有類型的 MQ 測試處理完畢。")

if __name__ == "__main__":
    main()