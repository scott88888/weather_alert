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
        
        # 臺灣完整 22 縣市清單 (用於精準比對)
        self.taiwan_cities = [
            "基隆市", "臺北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣", 
            "臺中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "臺南市", 
            "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣", "金門縣", "連江縣"
        ]
        
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
        """[濃霧]"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            geocodes = set()
            eff_time, exp_time = "", ""
            locations = data.get('records', {}).get('location', [])
            for loc in locations:
                hazards = loc.get('hazardConditions', {}).get('hazards', [])
                for h in hazards:
                    if h.get('info', {}).get('phenomena') == "濃霧":
                        vt = h.get('validTime', {})
                        eff_time = vt.get('startTime', "").replace('T', ' ').split('+')[0]
                        exp_time = vt.get('endTime', "").replace('T', ' ').split('+')[0]
                        if not self._check_is_expired(exp_time):
                            geo = str(loc.get('geocode', '')).split('.')[0]
                            if geo: geocodes.add(geo)
            return {"type": "濃霧", "geocodes": geocodes, "effective": eff_time, "expires": exp_time, "folderName": "W-C0033-001"}
        except Exception as e:
            logger.error(f"001 解析錯誤: {e}"); return None

    def _parse_006_wind(self, path: Path):
        """[強風]"""
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            def clean_time(t_str): return t_str.replace('T', ' ').split('+')[0] if t_str else ""
            geocodes = set()
            eff_time, exp_time = "", ""
            info = root.find('.//cap:info', self.cap_ns)
            if info is not None:
                event = info.find('cap:event', self.cap_ns).text or ""
                headline = info.find('cap:headline', self.cap_ns).text or ""
                eff_time = clean_time(info.find('cap:effective', self.cap_ns).text)
                exp_time = clean_time(info.find('cap:expires', self.cap_ns).text)
                if "解除" in headline or "解除" in event:
                    return {"type": "強風", "geocodes": set(), "effective": eff_time, "expires": exp_time, "folderName": "W-C0033-006"}
                if "強風" in event:
                    is_valid_color = False
                    for param in info.findall('cap:parameter', self.cap_ns):
                        value_name = param.find('cap:valueName', self.cap_ns)
                        value = param.find('cap:value', self.cap_ns)
                        if value_name is not None and value is not None:
                            if value_name.text == "alert_color" and value.text in ["橙色", "紅色"]:
                                is_valid_color = True
                                break
                    if not is_valid_color: return None
                    if not self._check_is_expired(exp_time):
                        for area in info.findall('cap:area', self.cap_ns):
                            for geo in area.findall('cap:geocode', self.cap_ns):
                                val = geo.find('cap:value', self.cap_ns).text
                                if val: geocodes.add(val.split('.')[0])
                    return {"type": "強風", "geocodes": geocodes, "effective": eff_time, "expires": exp_time, "folderName": "W-C0033-006"}
            return None
        except Exception as e:
            logger.error(f"006 解析錯誤: {e}"); return None   
            
    def _parse_003_rain(self, path: Path):    
        """[降雨]"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            infos = data.get("records", {}).get("info", [])
            result = {"type": "降雨", "geocodes": set(), "effective": "", "expires": "", "folderName": "W-C0033-003"}
            if not infos: return None  
            info = infos[0]
            headline = info.get("headline", "")
            parameters = info.get("parameter", [])
            exp = info.get("expires", "").replace('T', ' ').split('+')[0]
            eff = info.get("effective", "").replace('T', ' ').split('+')[0]
            result["effective"] = eff
            result["expires"] = exp
            if exp:
                exp_dt = datetime.datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
                if datetime.datetime.now() > (exp_dt + datetime.timedelta(hours=48)): return None
            if "解除" in headline: return result  
            is_valid_color = any(p.get("valueName") == "alert_color" and p.get("value") in ["黃色", "橙色", "紅色"] for p in parameters)
            if is_valid_color:
                if exp:
                    exp_dt = datetime.datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
                    if datetime.datetime.now() > (exp_dt + datetime.timedelta(hours=6)):
                        result["geocodes"] = set(); return result  
                geocodes = set()
                for a in info.get("area", []):
                    geo_obj = a.get("geocode", {})
                    geo_val = geo_obj.get("value", "") if isinstance(geo_obj, dict) else str(geo_obj)
                    if geo_val: geocodes.add(str(geo_val).split('.')[0])
                result["geocodes"] = geocodes
                return result
            return None
        except Exception as e:
            logger.error(f"003 解析錯誤: {e}"); return None
        
    def _parse_004_cold(self, data):
        """[低溫]"""
        try:
            records = data.get("records", {})
            info_list = records.get("info", [])
            if not info_list: return None
            found_counties, effective, expires = set(), "", ""
            for info in info_list:
                eff = info.get("effective", "").replace("T", " ")[:19].replace("-", "/")
                exp = info.get("expires", "").replace("T", " ")[:19].replace("-", "/")
                is_target_color = any(p.get("valueName") == "alert_color" and p.get("value") in ["橙色", "紅色"] for p in info.get("parameter", []))
                if is_target_color:
                    effective, expires = eff, exp
                    for area_item in info.get("area", []):
                        area_desc = area_item.get("areaDesc", "")
                        for city in self.taiwan_cities:
                            if city in area_desc: found_counties.add(city)
            if not found_counties: return None
            return {"counties": sorted(list(found_counties)), "alert_type": "low", "effective": effective, "expires": expires}
        except Exception as e:
            logger.error(f"004 低溫解析錯誤: {e}"); return None

    def _parse_005_heat(self, data):
        """[高溫]"""
        try:
            records = data.get("records", {})
            info_list = records.get("info", [])
            if not info_list: return None
            found_counties, effective, expires = set(), "", ""
            for info in info_list:
                eff = info.get("effective", "").replace("T", " ")[:19].replace("-", "/")
                exp = info.get("expires", "").replace("T", " ")[:19].replace("-", "/")
                is_target_color = any(p.get("valueName") == "alert_color" and p.get("value") in ["橙色", "紅色"] for p in info.get("parameter", []))
                if is_target_color:
                    effective, expires = eff, exp
                    for area_item in info.get("area", []):
                        area_desc = area_item.get("areaDesc", "")
                        for city in self.taiwan_cities:
                            if city in area_desc: found_counties.add(city)
            if not found_counties: return None
            return {"counties": sorted(list(found_counties)), "alert_type": "high", "effective": effective, "expires": expires}
        except Exception as e:
            logger.error(f"005 高溫解析錯誤: {e}"); return None

    def _parse_0034_1_typhoon(self, path: Path):
        """[專屬] 0034-001 颱風警報解析 (完備時序防禦乾淨版)"""
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            infos = data.get("records", {}).get("info", [])
            result = {"type": "颱風", "geocodes": set(), "effective": "", "onset": "", "expires": "", "folderName": "W-C0034-001"}

            if not infos:
                logger.warning("颱風警報檔案中無 info 資料區塊。")
                return None
            
            info = infos[0]
            headline = info.get("headline", "")
            parameters = info.get("parameter", [])
            areas = info.get("area", [])
            
            def clean_json_time(t_str):
                return t_str.replace('T', ' ').split('+')[0] if t_str else ""

            eff = clean_json_time(info.get("effective", ""))
            ons = clean_json_time(info.get("onset", ""))
            exp = clean_json_time(info.get("expires", ""))
            
            result["effective"] = eff
            result["onset"] = ons
            result["expires"] = exp

            if exp:
                exp_dt = datetime.datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
                now = datetime.datetime.now()
                if now > (exp_dt + datetime.timedelta(hours=48)):
                    logger.info(f"颱風警報已過期超過 48 小時 ({exp})，視為歷史舊檔，忽略處理。")
                    return None

            if "解除" in headline:
                logger.info(f"偵測到解除颱風警報標題: {headline}，回傳空 geocodes 以執行全域解除。")
                return result

            is_typhoon_alert = any(str(p.get("valueName")).strip() == "alert_title" and str(p.get("value")).strip() == "颱風警報" for p in parameters)
            is_land_sea_warning = any(str(p.get("valueName")).strip() == "severity_level" and str(p.get("value")).strip() == "海上陸上颱風警報" for p in parameters)

            if is_typhoon_alert and is_land_sea_warning:
                if exp:
                    exp_dt = datetime.datetime.strptime(exp, "%Y-%m-%d %H:%M:%S")
                    if datetime.datetime.now() > exp_dt:
                        logger.info(f"颱風警報已過期 ({exp}) 但未滿 48 小時。強制清空 geocodes 以觸發單次下架。")
                        result["geocodes"] = set()
                        return result
                
                geocodes = set()
                for area in areas:
                    geo_obj = area.get("geocode", {})
                    geo_val = geo_obj.get("value") if isinstance(geo_obj, dict) else str(geo_obj)
                    if geo_val:
                        geo_val = str(geo_val).strip()
                        clean_geo = geo_val.split('.')[0]
                        if len(clean_geo) == 8 and clean_geo.endswith('0'):
                            clean_geo = clean_geo[:5]
                        geocodes.add(clean_geo)
                
                result["geocodes"] = geocodes
                logger.info(f"成功解析到『海上陸上颱風警報』，共提取 {len(geocodes)} 個行政區，準備送入同步引擎。")
                return result

            logger.info(f"當前非『海上陸上颱風警報』(當前標題: {headline})，回傳空 geocodes。")
            return result

        except Exception as e:
            logger.error(f"0034-001 颱風解析錯誤: {e}", exc_info=True)
            return None

    def _extract_cities(self, areas):
        cities = set()
        city_pattern = r"(基隆市|臺北市|台北市|新北市|桃園市|新竹市|新竹縣|苗栗縣|臺中市|台中市|彰化縣|南投縣|雲林縣|嘉義市|嘉義縣|臺南市|台南市|高雄市|屏東縣|宜蘭縣|花蓮縣|臺東縣|台東縣|澎湖縣|金門縣|連江縣)"
        for area in areas:
            desc = area.get("areaDesc", "")
            matches = re.findall(city_pattern, desc)
            if matches:
                for match in matches: cities.add(match)
        return list(cities)