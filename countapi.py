import os
import json
from pathlib import Path

def count_fog_days(base_dir, start_date, end_date):
    base_path = Path(base_dir)
    total_fog_count = 0
    
    # 確保基礎路徑存在
    if not base_path.exists():
        print(f"錯誤：找不到路徑 {base_dir}")
        return 0

    print(f"開始搜尋範圍：{start_date} ~ {end_date}")
    print("-" * 50)

    # 遍歷基礎目錄下的所有子項目
    # 這裡假設資料夾名稱格式為 'YYYYMMDD'，可以直接用字串大小來比對範圍
    for date_dir in sorted(base_path.iterdir()):
        if date_dir.is_dir():
            dir_name = date_dir.name
            
            # 判斷資料夾名稱是否在 20260420 到 20260520 之間
            if start_date <= dir_name <= end_date:
                print(f"正在檢查資料夾: {dir_name}...", end="")
                
                fog_found_in_dir = False
                
                # 搜尋該資料夾內所有的 .json 檔案
                for json_file in date_dir.glob("*.json"):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        
                        # 解析 JSON 結構，尋找是否有 "濃霧"
                        # 依照你提供的結構：records -> location -> hazardConditions -> hazards -> info -> phenomena
                        locations = data.get("records", {}).get("location", [])
                        
                        for loc in locations:
                            hazards = loc.get("hazardConditions", {}).get("hazards", [])
                            for hazard in hazards:
                                phenomena = hazard.get("info", {}).get("phenomena", "")
                                if phenomena == "濃霧":
                                    fog_found_in_dir = True
                                    break # 內層：跳出目前 JSON 的 hazards 檢查
                                    
                            if fog_found_in_dir:
                                break # 中層：跳出目前 JSON 的 location 檢查
                                
                        if fog_found_in_dir:
                            print(" 發現濃霧！")
                            total_fog_count += 1
                            break # 外層：只要找到一次，就跳出這個資料夾的 JSON 迴圈，換下一個日期資料夾
                            
                    except (json.JSONDecodeError, IOError) as e:
                        # 預防有毀損或無法讀取的 JSON 檔案，記錄錯誤但程式不中斷
                        print(f"\n[警告] 檔案 {json_file.name} 讀取失敗: {e}")
                        continue
                
                if not fog_found_in_dir:
                    print(" 無濃霧。")

    print("-" * 50)
    print(f"搜尋結束！在該日期區間內，合計有 {total_fog_count} 個資料夾出現過濃霧。")
    return total_fog_count

if __name__ == "__main__":
    # 設定參數
    TARGET_DIR = "/home/sc/getapi/data/incoming/W-C0033-001"
    START = "20260420"
    END = "20260520"
    
    # 執行程式
    count_fog_days(TARGET_DIR, START, END)