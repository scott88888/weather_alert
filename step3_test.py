from file_reader import WeatherFileReader
from weather_parser import WeatherParser

def run_test():
    reader = WeatherFileReader()
    parser = WeatherParser()
    
    # 1. 只會讀取指定的那 5 個資料夾
    latest_files = reader.get_latest_files()
    
    for folder, path in latest_files.items():
        # 2. 傳入 folder 名稱，讓 parser 直接跳到該做的解析函數
        result = parser.parse(folder, path)
        
        if result:
            print(f"[{folder}] 解析成功: {result['type']}, 區域數: {len(result['geocodes'])}")
        else:
            print(f"[{folder}] 跳過或無符合條件資料")

if __name__ == "__main__":
    run_test()