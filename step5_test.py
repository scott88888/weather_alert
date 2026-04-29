import logging
import json
import datetime
from pathlib import Path
from weather_parser import WeatherParser 
from gecode_to_range import RoadNetworkLookup
from alert_sync_engine import AlertSyncEngine
from config import SOURCE_FOLDER

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Step5_Test")

def run_integration_test():
    parser = WeatherParser()
    road_lookup = RoadNetworkLookup()
    sync_engine = AlertSyncEngine()

    folder_name = "W-C0033-003"
    json_files = [
        f for f in (SOURCE_FOLDER / folder_name).iterdir() 
        if f.is_file() and f.suffix.lower() in ['.json', '.cap']
    ]
    if not json_files: 
        logger.error(f"在 {folder_name} 找不到任何 JSON 或 CAP 檔案")
        return
        
    mock_file_path = max(json_files, key=lambda x: x.name)
    logger.info(f"[階段 1] 自動偵測到最新檔案: {mock_file_path.name}")

    # 1. 解析
    parsed_data = parser.parse(folder_name, mock_file_path)
    if parsed_data is None: # 只有發生 Exception 時才中斷
        return

    # 2. 對照
    matched_segments = road_lookup.get_segments_by_geocodes(parsed_data.get('geocodes', set()))
    
    # 3. 整理格式
    final_parsed_results = []
    # 即使 matched_segments 為空，也會產生一個空的 final_parsed_results 傳給 sync
    for seg in matched_segments:
        eff = parsed_data.get('startTime') or parsed_data.get('effective')
        exp = parsed_data.get('endTime') or parsed_data.get('expires')
        exp_dt = datetime.datetime.strptime(exp, "%Y-%m-%d %H:%M:%S") if isinstance(exp, str) else exp
        
        final_parsed_results.append({
            **seg,
            "folderName": folder_name,
            "effectiveTime": eff,
            "expiresTime": exp_dt
        })

    # 4. 同步 (此時若 final_parsed_results 為空，sync 會觸發所有舊事件解除)
    to_cancel, to_active = sync_engine.sync(final_parsed_results, folder_name)

    print(f"\n[同步結果] 解除: {len(to_cancel)}, 成立: {len(to_active)}")
    if to_active:
        print("\n--- 成立 JSON 範例 ---")
        print(json.dumps(to_active[0], indent=4, ensure_ascii=False))

    if to_cancel:
        print("\n--- 解除 JSON 範例 ---")
        print(json.dumps(to_cancel[0], indent=4, ensure_ascii=False))

if __name__ == "__main__":
    run_integration_test()