import json
import xml.etree.ElementTree as ET
from pathlib import Path
import logging
import re

logger = logging.getLogger("WeatherParser")

class WeatherParser:
    def __init__(self):
        self.cap_ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        
        # 建立資料夾與解析函數的對照表
        self.dispatch_map = {
            "W-C0033-001": self._parse_001_fog,
            "W-C0033-003": self._parse_003_rain,
            "W-C0033-006": self._parse_006_wind,
            "W-C0033-004": self._parse_004_cold,
            "W-C0033-005": self._parse_005_heat,
        }

    def parse(self, folder_name: str, file_path: Path):
        """根據資料夾名稱直接呼叫對應的解析函數"""
        handler = self.dispatch_map.get(folder_name)
        if handler:
            return handler(file_path)
        logger.warning(f"無效的資料夾類型: {folder_name}")
        return None

    def _parse_001_fog(self, path: Path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            geocodes = set()
            start_time, end_time = "", ""
            
            locations = data.get('records', {}).get('location', [])
            for loc in locations:
                hazards = loc.get('hazardConditions', {}).get('hazards', [])
                is_fog = any(h.get('info', {}).get('phenomena') == "濃霧" for h in hazards)
                
                if is_fog:
                    geo = str(loc.get('geocode', '')).split('.')[0]
                    if geo: geocodes.add(geo)
                    for h in hazards:
                        if h.get('info', {}).get('phenomena') == "濃霧":
                            vt = h.get('validTime', {})
                            start_time = vt.get('startTime', start_time)
                            end_time = vt.get('endTime', end_time)

            # 修正：即便 geocodes 為空也回傳，確保後續 sync 流程能執行解除
            return {
                "type": "濃霧", 
                "geocodes": geocodes, 
                "startTime": start_time, 
                "endTime": end_time,
                "headline": "濃霧特報"
            }
        except Exception as e:
            logger.error(f"001 解析錯誤: {e}")
            return None
        
    def _parse_003_rain(self, path: Path):
        """[專屬] 003 大雨/豪雨特報"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            infos = data.get("records", {}).get("info", [])
            if not infos: return None
            
            info = infos[0]
            
            # 檢查顏色：必須是 黃色 或 紅色
            parameters = info.get("parameter", [])
            is_valid_color = any(p.get("valueName") == "alert_color" and p.get("value") in ["黃色", "紅色"] for p in parameters)
            
            if not is_valid_color:
                return None

            return {
                "type": "降雨",
                "headline": info.get("headline", ""), # 保留標題
                "geocodes": {str(a.get("geocode", {}).get("value", "")).split('.')[0] for a in info.get("area", [])},
                "effective": info.get("effective", ""), # 保留 effective
                "onset": info.get("onset", ""),         # 保留 onset
                "expires": info.get("expires", "")      # 保留 expires
            }
        except Exception as e:
            logger.error(f"003 解析錯誤: {e}")
            return None

    def _parse_006_wind(self, path: Path):
        """
        [專屬] 006 強風特報 (CAP 格式)
        1. 保留 headline
        2. 保留 effective, onset, expires
        3. 過濾 alert_color 為 黃色或紅色
        4. 提取 alert_criteria 供未來告警使用
        """
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            
            # 尋找 info 節點
            info = root.find('.//cap:info', self.cap_ns)
            if info is None:
                return None

            # --- 3. 檢查 Alert Color (黃色或紅色) ---
            parameters = info.findall('cap:parameter', self.cap_ns)
            is_valid_color = False
            alert_criteria = ""
            
            for param in parameters:
                v_name = param.findtext('cap:valueName', '', self.cap_ns)
                v_val = param.findtext('cap:value', '', self.cap_ns)
                
                # 判斷顏色
                if v_name == "alert_color" and (v_val == "黃色" or v_val == "紅色"):
                    is_valid_color = True
                
                # --- 4. 提取告警基準 (alert_criteria) ---
                if v_name == "alert_criteria":
                    alert_criteria = v_val
            
            if not is_valid_color:
                logger.info(f"006 檔案 {path.name} 未達警戒顏色標記，跳過解析")
                return None

            # --- 1. & 2. 提取標題與時間欄位 ---
            headline = info.findtext('cap:headline', '', self.cap_ns)
            effective = info.findtext('cap:effective', '', self.cap_ns)
            onset = info.findtext('cap:onset', '', self.cap_ns)
            expires = info.findtext('cap:expires', '', self.cap_ns)

            # 提取 Geocodes
            geocodes = set()
            for area in info.findall('cap:area', self.cap_ns):
                for geo in area.findall('cap:geocode', self.cap_ns):
                    val = geo.findtext('cap:value', '', self.cap_ns)
                    if val:
                        geocodes.add(val.split('.')[0])

            return {
                "type": "強風",
                "headline": headline,      # 保留標題 
                "geocodes": geocodes,      # 區域代碼 [cite: 5, 6, 7]
                "effective": effective,    # 保留有效時間 
                "onset": onset,            # 保留開始時間 
                "expires": expires,        # 保留結束時間 
                "alert_criteria": alert_criteria  # 告警基準字串 
            }
        except Exception as e:
            logger.error(f"006 解析錯誤: {e}")
            return None

    def _parse_004_cold(self, path: Path):
        """[專屬] 004 低溫特報 - 未來僅發送至 Redis"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            infos = data.get("records", {}).get("info", [])
            for info in infos:
                # 1. 標題判斷
                if "低溫" not in info.get("headline", ""): 
                    continue
                
                # 2. 顏色判斷 (黃色、紅色)
                parameters = info.get("parameter", [])
                is_valid_color = any(p.get("valueName") == "alert_color" and p.get("value") in ["黃色", "橙色", "紅色"] for p in parameters)
                if not is_valid_color:
                    continue

                # 3. 提取縣市 (排除 geocode)
                cities = self._extract_cities(info.get("area", []))

                # 4. 回傳格式 (增加 geocodes key 是為了讓您的測試腳本 len() 不崩潰，內容改放 cities)
                return {
                    "type": "低溫",
                    "headline": info.get("headline"),
                    "effective": info.get("effective"),
                    "onset": info.get("onset"),
                    "expires": info.get("expires"),
                    "cities": cities,
                    "geocodes": cities  # 暫時保留 key 供測試腳本使用
                }
            return None
        except Exception as e:
            logger.error(f"004 解析錯誤: {e}")
            return None

    def _parse_005_heat(self, path: Path):
        """[專屬] 005 高溫特報 - 未來僅發送至 Redis"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            infos = data.get("records", {}).get("info", [])
            for info in infos:
                # 1. 標題判斷 (氣象署高溫通常標題為 '高溫資訊')
                if "高溫" not in info.get("headline", ""): 
                    continue
                
                # 2. 顏色判斷
                parameters = info.get("parameter", [])
                is_valid_color = any(p.get("valueName") == "alert_color" and p.get("value") in ["黃色", "橙色", "紅色"] for p in parameters)
                if not is_valid_color:
                    continue

                # 3. 提取縣市
                cities = self._extract_cities(info.get("area", []))

                return {
                    "type": "高溫",
                    "headline": info.get("headline"),
                    "effective": info.get("effective"),
                    "onset": info.get("onset"),
                    "expires": info.get("expires"),
                    "cities": cities,
                    "geocodes": cities  # 暫時保留 key 供測試腳本使用
                }
            return None
        except Exception as e:
            logger.error(f"005 解析錯誤: {e}")
            return None
    def _extract_cities(self, areas):
        """
        精準提取台灣縣市名稱
        支援格式：新竹縣新竹市 -> 提取出 ["新竹縣", "新竹市"]
        """
        cities = set()
        # 定義台灣所有縣市名單
        city_pattern = r"(基隆市|臺北市|台北市|新北市|桃園市|新竹市|新竹縣|苗栗縣|臺中市|台中市|彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|臺南市|台南市|高雄市|屏東縣|宜蘭縣|花蓮縣|臺東縣|台東縣|澎湖縣|金門縣|連江縣)"
        
        for area in areas:
            desc = area.get("areaDesc", "")
            matches = re.findall(city_pattern, desc)
            if matches:
                for match in matches:
                    cities.add(match)
        
        return list(cities)