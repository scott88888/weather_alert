import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
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

    def _is_expired(self, time_str, label="警報"):
        """
        統一時效檢查：若傳入的時間超過 6 小時，返回 True (過期)
        """
        if not time_str:
            return True
        try:
            # 氣象署標準格式通常包含時區，如 "2026-07-20T09:00:00+08:00"
            alert_time = datetime.fromisoformat(time_str)
            current_time = datetime.now(timezone(timedelta(hours=8))) # 統一用台灣時區對齊
            if current_time - alert_time > timedelta(hours=6):
                logger.info(f" [時效攔截-{label}] 發布時間 {time_str} 已超過 6 小時，判定過期。")
                return True
        except Exception as e:
            logger.warning(f" [時效檢查異常-{label}] 解析時間失敗 {time_str}: {e}")
        return False

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
                elif folder_name == "W-C0034-001": # 颱風警報
                    self._handle_typhoon(file_path)
            except Exception as e:
                logger.error(f" [LINE引擎異常] 處理 {folder_name} 失敗: {str(e)}", exc_info=True)

    def _handle_fog(self, path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            cities = set()
            locations = data.get("records", {}).get("location", [])
            
            # 【時機 C】尋找第一個符合「濃霧」的生效時間進行時效檢查
            fog_start_time_str = None
            for loc in locations:
                hazards = loc.get("hazardConditions", {}).get("hazards", [])
                if any("濃霧" in h.get("info", {}).get("phenomena", "") for h in hazards):
                    # 抓取有濃霧特報縣市的 startTime
                    for h in hazards:
                        if "濃霧" in h.get("info", {}).get("phenomena", ""):
                            fog_start_time_str = h.get("validTime", {}).get("startTime")
                            break
                if fog_start_time_str:
                    break

            # 如果連一個濃霧特報的時間都找不到，代表此檔案無效
            if not fog_start_time_str:
                logger.debug(f" [LINE-FOG] {path.name} 找不到任何濃霧特報事件，跳過。")
                return

            # 相容性處理：因為濃霧的 "2026-07-20 11:21:00" 缺少時區後綴
            # 如果字串裡沒有 'T' 和 '+'，幫它轉換成 ISO 標準格式，以便符合 _is_expired 的解析
            if " " in fog_start_time_str and "+" not in fog_start_time_str:
                normalized_time_str = fog_start_time_str.replace(" ", "T") + "+08:00"
            else:
                normalized_time_str = fog_start_time_str

            # 進行 6 小時時效檢查
            if self._is_expired(normalized_time_str, "濃霧"):
                return

            # 【時機 A】開始擷取所有符合濃霧條件的縣市地區
            for loc in locations:
                name = loc.get("locationName")
                hazards = loc.get("hazardConditions", {}).get("hazards", [])
                if any("濃霧" in h.get("info", {}).get("phenomena", "") for h in hazards):
                    city = self._extract_city(name)
                    if city: 
                        cities.add(city)
            
            # 【時機 B】執行發送檢查 (交由 check_state_and_push 阻擋重複未異動名單)
            if cities:
                sorted_cities = sorted(list(cities))
                template = lambda locs: f"【濃霧特報】\n{'、'.join(locs)}易有局部濃霧，請注意行車安全。"
                self.sender.check_state_and_push("W-C0033-001", sorted_cities, template)
                
        except Exception as e:
            logger.error(f" [解析錯誤-濃霧] {path.name}: {e}", exc_info=True)

    def _handle_rain(self, path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            cities = set()
            infos = data.get("records", {}).get("info", [])
            
            for info in infos:
                # 檢查降雨公告生效時間是否過期 (路徑: records -> info -> onset)
                if self._is_expired(info.get("onset"), "降雨"):
                    continue

                parameters = info.get("parameter", [])
                is_target_color = False
                
                for p in parameters:
                    if p.get("valueName") == "alert_color" and p.get("value") in ["黃色", "橙色", "紅色"]:
                        is_target_color = True
                        break
                
                if is_target_color:
                    areas = info.get("area", [])
                    for area in areas:
                        desc = area.get("areaDesc", "")
                        city = self._extract_city(desc)
                        if city:
                            cities.add(city)
                else:
                    logger.debug(f" [LINE-RAIN] {path.name} 燈號未達發送標準，跳過。")

            if cities:
                sorted_cities = sorted(list(cities))
                template = lambda locs: f"【豪雨/大豪雨特報】\n未來可能有{'、'.join(locs)}有局部豪雨/大豪雨，請注意行車安全。"
                self.sender.check_state_and_push("W-C0033-003", sorted_cities, template)
                
        except Exception as e:
            logger.error(f" [解析錯誤-降雨] {path.name}: {e}")
    
    def _handle_wind(self, path):
        try:
            tree = ET.parse(path)
            root = tree.getroot()
            info = root.find('cap:info', self.cap_ns)
            if info is None: return

            # XML 格式檢查強風發布時間是否過期 (路徑: cap:info -> cap:onset)
            onset_time = info.findtext('cap:onset', '', self.cap_ns)
            if self._is_expired(onset_time, "強風"):
                return

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
    
    def _handle_typhoon(self, path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            
            cities = set()
            infos = data.get("records", {}).get("info", [])
            
            for info in infos:
                # 檢查颱風公告生效時間是否過期 (路徑: records -> info -> onset)
                if self._is_expired(info.get("onset"), "颱風"):
                    continue

                headline = info.get("headline", "")
                if headline == "海上陸上颱風警報":
                    areas = info.get("area", [])
                    for area in areas:
                        desc = area.get("areaDesc", "")
                        city = self._extract_city(desc)
                        if city:
                            cities.add(city)
                else:
                    logger.debug(f" [LINE-TYPHOON] {path.name} 標題為 {headline}，未達發送標準，跳過。")

            if cities:
                sorted_cities = sorted(list(cities))
                
                # 直接精準定位抓取颱風中文名稱 (第 0 個區塊的第 3 個 section)
                try:
                    cwa_name = data["records"]["info"][0]["description"]["typhoon-info"][0]["section"][3]["analysis"].get("cwa_typhoon_name", "")
                except (KeyError, IndexError):
                    cwa_name = ""
                
                typhoon_label = f"「{cwa_name}」颱風" if cwa_name else "颱風"
                template = lambda locs: f"【海上陸上颱風警報】\n氣象署已發布{typhoon_label}陸上警報，目前陸上警戒區域：{'、'.join(locs)}。請嚴防強風豪雨，注意自身安全！"
                
                self.sender.check_state_and_push("W-C0034-001", sorted_cities, template)
                
        except Exception as e:
            logger.error(f" [解析錯誤-颱風] {path.name}: {e}")