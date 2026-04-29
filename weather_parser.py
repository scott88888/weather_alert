import json
import xml.etree.ElementTree as ET
from pathlib import Path
import logging
import re
import datetime

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
            "W-C0034-001": self._parse_0034_1_typhoon,
        }
    
    def _check_is_expired(self, time_str, hours=1):
        """共用邏輯：檢查時間字串是否已過期超過指定小時"""
        if not time_str: return False
        try:
            # 統一轉換格式進行比對
            dt = datetime.datetime.strptime(time_str[:19].replace('T', ' '), "%Y-%m-%d %H:%M:%S")
            return dt < (datetime.datetime.now() - datetime.timedelta(hours=hours))
        except Exception as e:
            logger.error(f"時間比對錯誤: {e}")
            return False
        
    def parse(self, folder_name: str, file_path: Path):
        """根據資料夾名稱直接呼叫對應的解析函數"""
        handler = self.dispatch_map.get(folder_name)
        if handler:
            return handler(file_path)
        logger.warning(f"無效的資料夾類型: {folder_name}")
        return None

    def _parse_001_fog(self, path: Path):
        """[濃霧] 增加過期解除邏輯"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            geocodes = set()
            start_time, end_time = "", ""
            locations = data.get('records', {}).get('location', [])
            
            for loc in locations:
                hazards = loc.get('hazardConditions', {}).get('hazards', [])
                for h in hazards:
                    if h.get('info', {}).get('phenomena') == "濃霧":
                        vt = h.get('validTime', {})
                        start_time = vt.get('startTime', start_time)
                        end_time = vt.get('endTime', end_time)
                        # 只有在有效時才加入 geocode
                        if not self._check_is_expired(end_time):
                            geo = str(loc.get('geocode', '')).split('.')[0]
                            if geo: geocodes.add(geo)

            if self._check_is_expired(end_time):
                logger.info(f"濃霧檔案已過期 ({end_time})，觸發全域解除。")
                geocodes = set()

            return {
                "type": "濃霧", "geocodes": geocodes, 
                "startTime": start_time, "endTime": end_time,
                "folderName": "W-C0033-001"
            }
        except Exception as e:
            logger.error(f"001 解析錯誤: {e}"); return None

    def _parse_006_wind(self, path: Path):
        """[強風] 增加過期解除邏輯"""
        try:
            tree = ET.parse(path); root = tree.getroot()
            def clean_time(t_str): return t_str.replace('T', ' ').split('+')[0] if t_str else ""
            
            geocodes = set(); eff_time, exp_time = "", ""
            info = root.find('.//cap:info', self.cap_ns)
            
            if info is not None:
                event = info.find('cap:event', self.cap_ns).text
                if "強風" in event:
                    eff_time = clean_time(info.find('cap:effective', self.cap_ns).text)
                    exp_time = clean_time(info.find('cap:expires', self.cap_ns).text)
                    
                    if not self._check_is_expired(exp_time):
                        for area in info.findall('cap:area', self.cap_ns):
                            for geo in area.findall('cap:geocode', self.cap_ns):
                                val = geo.find('cap:value', self.cap_ns).text
                                if val: geocodes.add(val.split('.')[0])
            
            if self._check_is_expired(exp_time):
                logger.info(f"強風檔案已過期 ({exp_time})，觸發全域解除。")
                geocodes = set()

            return {
                "type": "強風", "geocodes": geocodes,
                "effective": eff_time, "expires": exp_time,
                "folderName": "W-C0033-006"
            }
        except Exception as e:
            logger.error(f"006 解析錯誤: {e}"); return None

    def _parse_003_rain(self, path: Path):
        """[豪大雨] 增加過期解除邏輯"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            infos = data.get("records", {}).get("info", [])
            result = {"type": "降雨", "geocodes": set(), "effective": "", "expires": "", "folderName": "W-C0033-003"}
            if not infos: return result
            
            info = infos[0]
            exp = info.get("expires", "").replace('T', ' ').split('+')[0]
            
            if self._check_is_expired(exp):
                logger.info(f"大雨檔案已過期 ({exp})，觸發全域解除。")
                return result

            # 正常解析流程...
            parameters = info.get("parameter", [])
            is_valid = any(p.get("valueName") == "alert_color" and p.get("value") in ["黃色", "紅色"] for p in parameters)
            if is_valid:
                result["expires"] = exp
                result["geocodes"] = {str(a.get("geocode", {}).get("value", "")).split('.')[0] for a in info.get("area", [])}
            
            return result
        except Exception as e:
            logger.error(f"003 解析錯誤: {e}"); return None
            
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
    
    def _parse_0034_1_typhoon(self, path: Path):
        """[專屬] 0034-001 颱風警報解析"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            infos = data.get("records", {}).get("info", [])
            
            # 初始化結果
            result = {
                "type": "颱風",
                "geocodes": set(),
                "effective": "",
                "onset": "",
                "expires": "",
                "folderName": "W-C0034-001"
            }

            if not infos:
                return result
            
            info = infos[0]
            headline = info.get("headline", "")
            
            # 1. 時間提取與格式化 (處理 T 與時區)
            def clean_json_time(t_str):
                return t_str.replace('T', ' ').split('+')[0] if t_str else ""

            eff = clean_json_time(info.get("effective", ""))
            ons = clean_json_time(info.get("onset", ""))
            exp = clean_json_time(info.get("expires", ""))
            
            # 2. 【核心邏輯 1】時效性檢查
            # 如果 expires 早於現在時間超過 1 小時，視為歷史舊資料，不予處理
            if exp:
                exp_dt = datetime.datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
                now = datetime.datetime.now()
                if exp_dt < (now - datetime.timedelta(hours=1)):
                    logger.info(f"颱風警報已過期超過 1 小時 ({exp})，跳過處理。")
                    return None # 回傳 None 讓測試腳本直接 return，不觸發 DB 變動

            # 填充基本資訊
            result["effective"] = eff
            result["onset"] = ons
            result["expires"] = exp
            result["headline"] = headline

            # 3. 【核心邏輯 2】判定是否為「解除」警報
            # 只要標題包含 "解除"，即便 API 內有地區，也回傳空 geocodes 觸發全域刪除
            if "解除" in headline:
                logger.info("偵測到『解除颱風警報』，將回傳空路網以清空事件。")
                return result

            # 4. 【核心邏輯 3】非解除狀態下，提取 Geocodes
            # 颱風警報通常包含行政區代碼 (如 68000000)
            geocodes = set()
            for area in info.get("area", []):
                geo_val = area.get("geocode", {}).get("value")
                if geo_val:
                    # 處理 68000000 -> 6800000 (轉為與路網表一致的 7 碼或開頭比對格式)
                    clean_geo = str(geo_val).split('.')[0]
                    geocodes.add(clean_geo)
            
            result["geocodes"] = geocodes
            return result

        except Exception as e:
            logger.error(f"0034-001 颱風解析錯誤: {e}")
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