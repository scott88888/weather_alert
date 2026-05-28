import os
import json
from pathlib import Path

def count_alert_colors_v4(base_dir, start_date, end_date):
    base_path = Path(base_dir)
    
    # 初始化黃、橙、紅三色的總計數器
    total_counts = {
        "黃色": 0,
        "橙色": 0,
        "紅色": 0
    }
    
    # 定義我們要尋找的目標顏色集合
    target_colors = set(total_counts.keys())
    
    if not base_path.exists():
        print(f"錯誤：找不到路徑 {base_dir}")
        return None
    
    print(f"開始搜尋新目錄：{base_dir}")
    print(f"時間範圍：{start_date} ~ {end_date}")
    print("-" * 60)

    # 依序讀取日期資料夾
    for date_dir in sorted(base_path.iterdir()):
        if date_dir.is_dir():
            dir_name = date_dir.name
            
            # 限制在指定的日期區間內 (例如 20260420 到 20260520)
            if start_date <= dir_name <= end_date:
                print(f"正在檢查資料夾: {dir_name}...", end="")
                
                # 用於記錄當天「已捕獲」的顏色，自動去重
                colors_found_in_day = set()
                
                # 遍歷該日期資料夾內所有的 .json 檔案
                for json_file in date_dir.glob("*.json"):
                    # 效能優化：如果當天已經把黃、橙、紅三色都搜集到了，直接提早結束該資料夾的搜尋
                    if colors_found_in_day == target_colors:
                        break
                        
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 解析 JSON 結構
                        info_list = data.get("records", {}).get("info", [])
                        
                        for info in info_list:
                            parameters = info.get("parameter", [])
                            for param in parameters:
                                # 比對欄位名稱是否為 alert_color
                                if param.get("valueName") == "alert_color":
                                    color_val = param.get("value", "")
                                    
                                    # 檢查是否為我們要的目標顏色，是的話放入集合
                                    if color_val in target_colors:
                                        colors_found_in_day.add(color_val)
                                        
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"\n[警告] 檔案 {json_file.name} 讀取損毀或無法開啟: {e}")
                        continue
                
                # 將當天去重後的顏色統計結果，累加到總計數器中
                for color in colors_found_in_day:
                    total_counts[color] += 1
                
                # 即時印出當天狀態
                if colors_found_in_day:
                    print(f" 發現顏色: {', '.join(sorted(colors_found_in_day))}")
                else:
                    print(" 無符合的顏色警告。")

    # 輸出統計總結
    print("-" * 60)
    print("【最終統計結果】（每個資料夾每種顏色每天最多計算一次）")
    for color, count in total_counts.items():
        print(f" - {color}: {count} 次")
        
    return total_counts

if __name__ == "__main__":
    # 1. 調整為新的目標資料夾 W-C0033-004
    TARGET_DIR = "/home/sc/getapi/data/incoming/W-C0033-005"
    START = "20260420"
    END = "20260520"
    
    # 執行統計程式
    count_alert_colors_v4(TARGET_DIR, START, END)