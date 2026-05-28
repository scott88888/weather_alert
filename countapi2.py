import os
import json
from pathlib import Path

def count_alert_colors(base_dir, start_date, end_date):
    base_path = Path(base_dir)
    
    # 初始化總計數器
    total_counts = {
        "黃色": 0,
        "橙色": 0,
        "紅色": 0
    }
    
    # 定義我們要尋找的目標顏色
    target_colors = set(total_counts.keys())
    
    if not base_path.exists():
        print(f"錯誤：找不到路徑 {base_dir}")
        return
    

    print(f"開始搜尋目錄：{base_dir}")
    print(f"時間範圍：{start_date} ~ {end_date}")
    print("-" * 60)

    # 遍歷基礎目錄下的所有子項目
    for date_dir in sorted(base_path.iterdir()):
        if date_dir.is_dir():
            dir_name = date_dir.name
            
            # 判斷資料夾名稱是否在指定日期範圍內
            if start_date <= dir_name <= end_date:
                print(f"正在檢查資料夾: {dir_name}...", end="")
                
                # 用來記錄這個資料夾「已經出現過」的顏色
                colors_found_in_day = set()
                
                # 搜尋該資料夾內所有的 .json 檔案
                for json_file in date_dir.glob("*.json"):
                    # 如果這個資料夾已經把三種顏色都集滿了，就不用再讀剩下的 JSON 了
                    if colors_found_in_day == target_colors:
                        break
                        
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 依照新的 JSON 結構解析：records -> info -> parameter
                        info_list = data.get("records", {}).get("info", [])
                        
                        for info in info_list:
                            parameters = info.get("parameter", [])
                            for param in parameters:
                                # 尋找 valueName 為 alert_color 的項目
                                if param.get("valueName") == "alert_color":
                                    color_val = param.get("value", "")
                                    
                                    # 如果是我們要的黃/橙/紅色，就加入當天的集合
                                    if color_val in target_colors:
                                        colors_found_in_day.add(color_val)
                                        
                    except (json.JSONDecodeError, IOError) as e:
                        print(f"\n[警告] 檔案 {json_file.name} 讀取失敗: {e}")
                        continue
                
                # 將當天統計到的顏色，累加到總計數器中
                for color in colors_found_in_day:
                    total_counts[color] += 1
                
                # 顯示當天活潑的小結
                if colors_found_in_day:
                    print(f" 發現顏色: {', '.join(colors_found_in_day)}")
                else:
                    print(" 無符合的顏色警告。")

    # 輸出最終結果
    print("-" * 60)
    print("【最終統計結果】（每個資料夾每種顏色最多計算一次）")
    for color, count in total_counts.items():
        print(f" - {color}: {count} 次")
        
    return total_counts

if __name__ == "__main__":
    # 1. 這次改成 W-C0033-003 資料夾
    TARGET_DIR = "/home/sc/getapi/data/incoming/W-C0033-003"
    START = "20260420"
    END = "20260520"
    
    # 執行程式
    count_alert_colors(TARGET_DIR, START, END)