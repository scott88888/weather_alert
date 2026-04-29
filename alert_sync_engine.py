import datetime
import logging
import json
from db_manager import DBManager
from formatter import transform_to_tcss_format, transform_to_cancel_format
from config import INCIDENT_TYPE_MAP

logger = logging.getLogger("AlertSyncEngine")

class AlertSyncEngine:
    def __init__(self):
        self.db = DBManager()

    def sync(self, parsed_results, current_folder):
        """
        parsed_results: 本次解析出的路段
        current_folder: 目前正在處理的資料夾 (例如 "W-C0033-001")
        """
        now = datetime.datetime.now()
        # 取得目前檔案對應的數字代碼
        current_inc_code = str(INCIDENT_TYPE_MAP.get(current_folder, 99))
        
        # 修正：只撈取資料庫中「同類型」的發送中警報進行比對
        conn = self.db.get_connection()
        db_records = []
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM RoadAlertControlSwitchTbl WHERE is_active = 1 AND alertType = %s"
                cursor.execute(sql, (current_inc_code,))
                db_records = cursor.fetchall()
        finally:
            conn.close()

        db_map = {
            (str(r['freewayId']), str(r['mainDirection']), 
             float(r['fmileAge']), float(r['tmileAge'])): r 
            for r in db_records
        }

        to_send_level2 = [] 
        to_send_level1 = [] 

        # 建立本次解析的 Key Set
        current_keys = set()
        for res in parsed_results:
            key = (str(res['freewayId']), str(res['mainDirection']), 
                   float(res['fmileAge']), float(res['tmileAge']))
            current_keys.add(key)

        # 1. 檢查解除 (針對同類型)
        for key, record in db_map.items():
            is_in_current = key in current_keys
            
            # 找對應路段比對時間
            current_res = next((r for r in parsed_results if (
                str(r['freewayId']), str(r['mainDirection']), 
                float(r['fmileAge']), float(r['tmileAge'])) == key), None)
            
            time_changed = (current_res and record['expiresTime'] != current_res['expiresTime'])
            is_expired = now > record['expiresTime']

            if not is_in_current or time_changed or is_expired:
                logger.info(f"觸發解除 [{current_folder}]: {record['incidentId']}")
                to_send_level1.append(transform_to_cancel_format(record))
                self.db.delete_alert(record['incidentId'])

        # 2. 檢查成立
        # 重新確認 DB 剩餘狀態       
        conn = self.db.get_connection()
        existing_ids = set()
        remaining_db_keys = set()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT freewayId, mainDirection, fmileAge, tmileAge FROM RoadAlertControlSwitchTbl WHERE alertType = %s", (current_inc_code,))
                for r in cursor.fetchall():
                    remaining_db_keys.add((str(r['freewayId']), str(r['mainDirection']), float(r['fmileAge']), float(r['tmileAge'])))
        finally:
            conn.close()

        for i, res in enumerate(parsed_results, 1):
            key = (str(res['freewayId']), str(res['mainDirection']), 
                   float(res['fmileAge']), float(res['tmileAge']))
            
            if key not in remaining_db_keys:
                time_info = {"effective": res['effectiveTime'], "expires": res['expiresTime']}
                new_json = transform_to_tcss_format(res, current_folder, time_info, sequence=i)
                to_send_level2.append(new_json)
                
                db_data = {
                    "incidentId": new_json['content']['incidentId'],
                    "alertType": current_inc_code,
                    "freewayId": res['freewayId'],
                    "mainDirection": res['mainDirection'],
                    "fmileAge": res['fmileAge'],
                    "tmileAge": res['tmileAge'],
                    "expiresTime": res['expiresTime'],
                    "controlCenterId": res['controlCenterId']
                }
                self.db.insert_alert(db_data)

        return to_send_level1, to_send_level2