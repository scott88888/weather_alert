import datetime
import logging
import re
from config import INCIDENT_TYPE_MAP

logger = logging.getLogger(__name__)

SEVERITY_MAPPING = {
    "W-C0033-003": 4, "W-C0033-006": 3,
    "W-C0033-001": 1, "W-C0033-005": 3, "W-C0033-004": 3,
}

def generate_incident_id(effective_time_str, sequence, cc_id, inc_type):
    """ 生成固定的 23 碼 incidentId (14碼時間 + 3碼序號 + 2碼中心 + 4碼類型) """
    time_str = ""
    try:
        if effective_time_str:
            # 修正解析邏輯：提取所有數字字串並取前 14 碼 (YYYYMMDDHHMMSS)
            nums = re.sub(r'\D', '', str(effective_time_str))
            if len(nums) >= 14:
                time_str = nums[:14]
            else:
                time_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        else:
            time_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    except Exception as e:
        logger.error(f"ID 生成發生錯誤: {e}")
        time_str = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    
    return f"{time_str}{str(sequence).zfill(3)}{str(cc_id or 0).zfill(2)}{str(inc_type).zfill(4)}"

def transform_to_tcss_format(segment_data, filename, time_info, sequence):
    now_str = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    inc_type = INCIDENT_TYPE_MAP.get(filename, 99)
    cc_id = segment_data.get('controlCenterId', '10') # 從路網表抓取的中心代碼
    eff_time = time_info.get("effective", "")
    
    def fmt_val(v):
        if isinstance(v, datetime.datetime):
            return v.strftime("%Y/%m/%d %H:%M:%S")
        return str(v)
    
    incident_id = generate_incident_id(eff_time, sequence, cc_id, inc_type)

    return {
        "dsType": "DS_TYPE_AprOpPt",
        "dateTime": now_str,
        "content": {
            "isReturn": 0, "userDef": "127.0.0.1, WeatherSystem", "level": 2,
            "wsIP": "127.0.0.1", "userid": "AutoWeather",
            "controlCenterId": cc_id, # 新增此欄位供 MQ 動態路由使用
            "alarmTime": fmt_val(eff_time), 
            "confirmTime": fmt_val(time_info.get("onset", "") or eff_time),
            "expiresTime": fmt_val(time_info.get("expires", "")), 
            "incidentId": incident_id, "incType": int(inc_type), "inputMode": 1,
            "freewayId": int(segment_data.get('freewayId', 0)),
            "directionId": int(segment_data.get('mainDirection', 0)),
            "fMilepost": int(segment_data.get('fmileAge', 0)),
            "tMilepost": int(segment_data.get('tmileAge', 0)),
            "severity": SEVERITY_MAPPING.get(filename, 1),
            "informFrom": "CWA", "informer": "OpenData", "informId": "",
            "closeRoadStartTime": "", "closeRoadEndTime": "", "rampWay": 0, "tunnelId": 0,
            "congestionLevel": 0, "blockagePattern": "00000000",
            "alarmDescription": f"氣象特報：{filename}",
            "clientPexMode": "0", "incStepRescue": 0
        }
    }

def transform_to_cancel_format(db_record):
    now_str = datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S")
    def fmt_dt(val):
        if isinstance(val, datetime.datetime):
            return val.strftime("%Y/%m/%d %H:%M:%S")
        return str(val)
    
    raw_type = db_record.get('alertType', '99')
    inc_type_code = INCIDENT_TYPE_MAP.get(raw_type, 99) if not str(raw_type).isdigit() else int(raw_type)
    cc_id = db_record.get('controlCenterId', '10') # 從 DB 紀錄中提取原始中心代碼

    return {
        "dsType": "DS_TYPE_AprOpPt",
        "dateTime": now_str,
        "content": {
            "isReturn": 0, "userDef": "127.0.0.1, WeatherSystem", "level": 1,
            "wsIP": "127.0.0.1", "userid": "AutoWeather",
            "controlCenterId": cc_id, # 新增此欄位供解除事件動態路由使用
            "alarmTime": fmt_dt(db_record.get('expiresTime')),
            "confirmTime": now_str, "expiresTime": now_str, 
            "incidentId": db_record['incidentId'], "incType": inc_type_code, "inputMode": 1,
            "freewayId": int(db_record['freewayId']),
            "directionId": int(db_record['mainDirection']),
            "fMilepost": int(db_record['fmileAge']),
            "tMilepost": int(db_record['tmileAge']),
            "severity": 1, "informFrom": "CWA", "informer": "OpenData", "informId": "",
            "closeRoadStartTime": "", "closeRoadEndTime": "", "rampWay": 0, "tunnelId": 0,
            "congestionLevel": 0, "blockagePattern": "00000000",
            "alarmDescription": f"解除警報: {db_record['incidentId']}",
            "clientPexMode": "0", "incStepRescue": 0
        }
    }