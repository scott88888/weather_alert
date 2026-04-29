from file_reader import WeatherFileReader
from weather_parser import WeatherParser
from gecode_to_range import RoadNetworkLookup

def get_direction_text(freeway_id, direction_code):
    """
    根據國道編號判定是南北向還是東西向
    一般而言，國道編號末兩位為 2, 4, 6, 8, 0 (如 10020, 10040) 為東西向
    """
    fid_str = str(freeway_id)
    # 東西向判定：國2, 國4, 國6, 國8, 國10 (對應 10020, 10040, 10060, 10080, 10100)
    is_east_west = any(fid_str.endswith(x) for x in ['20', '40', '60', '80', '100'])
    
    if direction_code == 1:
        return "東向" if is_east_west else "北向"
    elif direction_code == 3:
        return "西向" if is_east_west else "南向"
    return f"未知({direction_code})"

def run_step4_test():
    reader = WeatherFileReader()
    parser = WeatherParser()
    road_lookup = RoadNetworkLookup()
    
    latest_files = reader.get_latest_files()
    
    for folder, path in latest_files.items():
        result = parser.parse(folder, path)
        
        if result and "geocodes" in result:
            # 排除純行政區類型 (004, 005)，這些通常是縣市名稱字串
            if isinstance(result['geocodes'], (list, set)) and len(result['geocodes']) > 0:
                # 檢查第一個元素是否為數字開頭，避免誤入縣市名稱
                first_item = str(list(result['geocodes'])[0])
                if not first_item.isdigit() and '.' not in first_item:
                    print(f"[{folder}] {result['type']} 為行政區警報，跳過里程轉化")
                    continue

                segments = road_lookup.get_segments_by_geocodes(result['geocodes'])
                
                print(f"[{folder}] {result['type']} 解析成功")
                print(f" -> 原始區域數: {len(result['geocodes'])}")
                print(f" -> 轉化後路段數: {len(segments)}")
                
                for seg in segments:
                    dir_label = get_direction_text(seg['freewayId'], seg['mainDirection'])
                    print(f"    🚗 國道{seg['freewayId']} ({dir_label}): "
                          f"{seg['fmileAge']}k ~ {seg['tmileAge']}k")
        else:
            print(f"[{folder}] 跳過或無符合條件資料")

if __name__ == "__main__":
    run_step4_test()