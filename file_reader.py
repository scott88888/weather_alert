import logging
from pathlib import Path
from config import SOURCE_FOLDER, TARGET_FOLDERS # 從 config 引入

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("WeatherFileReader")

class WeatherFileReader:
    def __init__(self):
        self.source_root = SOURCE_FOLDER
        self.target_folders = TARGET_FOLDERS

    def get_latest_files(self):
        """僅針對 config 指定的 TARGET_FOLDERS 讀取最新檔案"""
        latest_files = {}

        if not self.source_root.exists():
            logger.error(f"來源根目錄不存在: {self.source_root}")
            return latest_files

        for folder_name in self.target_folders:
            folder_path = self.source_root / folder_name
            
            if not folder_path.exists():
                continue

            # 搜尋 .json 與 .cap
            valid_files = [
                f for f in folder_path.iterdir() 
                if f.is_file() and f.suffix.lower() in ['.json', '.cap']
            ]

            if not valid_files:
                continue

            # 依檔名排序取最新 (檔名含 YYYYMMDDHHMMSS)
            latest_file = max(valid_files, key=lambda x: x.name)
            latest_files[folder_name] = latest_file
            logger.info(f"成功確認 [{folder_name}] 最新檔案: {latest_file.name}")

        return latest_files