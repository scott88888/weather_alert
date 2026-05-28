import os
from pathlib import Path
import xml.etree.ElementTree as ET

def count_cap_alert_colors(base_dir, start_date, end_date):
    base_path = Path(base_dir)
    
    # 初始化黃、橙、紅三色的總計數器
    total_counts = {
        "黃色": 0,
        "橙色": 0,
        "紅色": 0
    }
    
    target_colors = set(total_counts.keys())
    
    if not base_path.exists():
        print(f"錯誤：找不到路徑 {base_dir}")
        return None
    
    print(f"開始搜尋 XML/CAP 目錄：{base_dir}")
    print(f"時間範圍：{start_date} ~ {end_date}")
    print("-" * 60)

    # 遍歷日期資料夾
    for date_dir in sorted(base_path.iterdir()):
        if date_dir.is_dir():
            dir_name = date_dir.name
            
            # 判斷資料夾名稱是否在範圍內
            if start_date <= dir_name <= end_date:
                print(f"正在檢查資料夾: {dir_name}...", end="")
                
                colors_found_in_day = set()
                
                # 搜尋該資料夾內所有的 .cap 檔案 (若副檔名是大寫 .CAP 也能相容，或改用 *.xml)
                cap_files = list(date_dir.glob("*.cap")) + list(date_dir.glob("*.CAP")) + list(date_dir.glob("*.xml"))
                # 去除重複取得的檔案（以防萬一）
                cap_files = sorted(list(set(cap_files)))
                
                for cap_file in cap_files:
                    # 效能優化：如果當天已經集滿黃、橙、紅三色，直接跳過這天剩下的檔案
                    if colors_found_in_day == target_colors:
                        break
                        
                    try:
                        # 解析 XML
                        tree = ET.parse(cap_file)
                        root = tree.getroot()
                        
                        # 自動獲取 XML 的命名空間 (處理 xmlns="urn:oasis:names:tc:emergency:cap:1.2")
                        # 標籤在解析後會變成 {urn:oasis:names:tc:emergency:cap:1.2}info 的形式
                        ns = ""
                        if root.tag.startswith("{"):
                            ns = root.tag.split("}")[0] + "}"
                        
                        # 尋找所有的 <parameter> 標籤
                        # 結構： root -> info -> parameter
                        for info in root.findall(f"{ns}info"):
                            for parameter in info.findall(f"{ns}parameter"):
                                v_name_el = parameter.find(f"{ns}valueName")
                                v_val_el = parameter.find(f"{ns}value")
                                
                                # 確保標籤內有文字
                                if v_name_el is not None and v_val_el is not None:
                                    v_name = v_name_el.text.strip() if v_name_el.text else ""
                                    v_val = v_val_el.text.strip() if v_val_el.text else ""
                                    
                                    # 尋找 alert_color
                                    if v_name == "alert_color" and v_val in target_colors:
                                        colors_found_in_day.add(v_val)
                                        
                    except (ET.ParseError, IOError) as e:
                        print(f"\n[警告] 檔案 {cap_file.name} 格式損毀或無法開啟: {e}")
                        continue
                
                # 將當天統計到的顏色，累加到總計數器
                for color in colors_found_in_day:
                    total_counts[color] += 1
                
                # 印出當天結果
                if colors_found_in_day:
                    print(f" 發現顏色: {', '.join(sorted(colors_found_in_day))}")
                else:
                    print(" 無符合的顏色警告。")

    # 輸出最終統計結果
    print("-" * 60)
    print("【最終統計結果】（每個資料夾每種顏色每天最多計算一次）")
    for color, count in total_counts.items():
        print(f" - {color}: {count} 次")
        
    return total_counts

if __name__ == "__main__":
    # 1. 改成搜尋 W-C0033-006 資料夾
    TARGET_DIR = "/home/sc/getapi/data/incoming/W-C0033-006"
    START = "20260420"
    END = "20260520"
    
    # 執行程式
    count_cap_alert_colors(TARGET_DIR, START, END)