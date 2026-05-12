import json
import logging
import xml.etree.ElementTree as ET
from line_sender import LineSender
from config import LINE_REDIS_KEYS

logger = logging.getLogger("Line_Notify")

class LineNotifyEngine:
    def __init__(self):
        self.sender = LineSender()
        self.cap_ns = {'cap': 'urn:oasis:names:tc:emergency:cap:1.2'}
        # 台灣標準 22 縣市清單，用於精準比對
        self.taiwan_cities = [
            "基隆市", "臺北市", "新北市", "桃園市", "新竹市", "新竹縣", "苗栗縣", 
            "臺中市", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "臺南市", 
            "高雄市", "屏東縣", "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣", "金門縣", "連江縣"
        ]

    def _extract_city(self, location_name):
        """
        從地名中擷取出縣市層級。
        例如：「新竹縣竹北市」->「新竹縣」、「臺南市」->「臺南市」
        """
        if not location_name:
            return None
        for city in self.taiwan_cities:
            if city in location_name:
                return city
        return None

    def run(self, latest_files):
        for folder_name in LINE_REDIS_KEYS.keys():
            file_path = latest_files.get(folder_name)
            if not file_path:
                continue
            
            try:
                if folder_name == "W-C0033-001":  # 濃霧
                    self._handle_fog(file_path)
                elif folder_name == "W-C0033-003": # 豪大雨
                    self._handle_rain(file_path)
                elif folder_name == "W-C0033-006": # 強風
                    self._handle_wind(file_path)
            except Exception as e:
                logger.error(f" [LINE引擎異常] 處理 {folder_name} 失敗: {str(e)}", exc_info=True)

    def _handle_fog(self, path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            cities = set()
            locations = data.get("records", {}).get("location", [])
            for loc in locations:
                name = loc.get("locationName")
                hazards = loc.get("hazardConditions", {}).get("hazards", [])
                if any("濃霧" in h.get("info", {}).get("phenomena", "") for h in hazards):
                    city = self._extract_city(name)
                    if city: cities.add(city)
            
            if cities:
                sorted_cities = sorted(list(cities))
                template = lambda locs: f"【濃霧特報】\n目前{'、'.join(locs)}易有局部濃霧，請注意行車安全。"
                self.sender.check_state_and_push("W-C0033-001", sorted_cities, template)
        except Exception as e:
            logger.error(f" [解析錯誤-濃霧] {path.name}: {e}")

    def _handle_rain(self, path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            cities = set()
            # 進入 records -> info 
            infos = data.get("records", {}).get("info", [])
            
            for info in infos:
                # 1. 判斷燈號條件：valueName=alert_color 且 value=橙色或紅色 
                parameters = info.get("parameter", [])
                is_target_color = False
                
                for p in parameters:
                    if p.get("valueName") == "alert_color" and p.get("value") in ["橙色", "紅色"]:
                        is_target_color = True
                        break
                
                # 2. 如果燈號符合，開始擷取地區 
                if is_target_color:
                    areas = info.get("area", [])
                    for area in areas:
                        # 來源：records -> info -> area -> areaDesc 
                        desc = area.get("areaDesc", "")
                        city = self._extract_city(desc)
                        if city:
                            cities.add(city)
                else:
                    logger.debug(f" [LINE-RAIN] {path.name} 燈號未達發送標準，跳過。")

            # 3. 執行發送檢查
            if cities:
                sorted_cities = sorted(list(cities))
                template = lambda locs: f"【豪雨/大豪雨特報】\n目前{'、'.join(locs)}有局部豪雨/大豪雨，請注意行車安全。"
                self.sender.check_state_and_push("W-C0033-003", sorted_cities, template)
                
        except Exception as e:
            logger.error(f" [解析錯誤-降雨] {path.name}: {e}")
    def _handle_wind(self, path):
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            info = root.find('cap:info', self.cap_ns)
            if info is None: return

            color = ""
            criteria = ""
            for p in info.findall('cap:parameter', self.cap_ns):
                v_n = p.findtext('cap:valueName', '', self.cap_ns)
                v_v = p.findtext('cap:value', '', self.cap_ns)
                if v_n == "alert_color": color = v_v
                if v_n == "alert_criteria": criteria = v_v

            if color not in ["黃色", "橙色", "紅色"]:
                return

            cities = set()
            for area in info.findall('cap:area', self.cap_ns):
                desc = area.findtext('cap:areaDesc', '', self.cap_ns)
                city = self._extract_city(desc)
                if city: cities.add(city)
            
            if cities:
                sorted_cities = sorted(list(cities))
                headline = info.findtext('cap:headline', '強風特報', self.cap_ns)
                template = lambda locs: f"【{headline}】\n{','.join(locs)}有「{criteria}」發生機率。"
                self.sender.check_state_and_push("W-C0033-006", sorted_cities, template)
        except Exception as e:
            logger.error(f" [解析錯誤-強風] {path.name}: {e}")