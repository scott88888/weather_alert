import datetime
import logging
from db_manager import DBManager
from formatter import transform_to_tcss_format, transform_to_cancel_format
from config import INCIDENT_TYPE_MAP

logger = logging.getLogger("AlertSyncEngine")

class AlertSyncEngine:
    def __init__(self):
        self.db = DBManager()

    def sync(self, parsed_results, current_folder):
        """
        核心邏輯：將解除與成立分離，確保順序性。
        """
        now = datetime.datetime.now()
        current_inc_code = str(INCIDENT_TYPE_MAP.get(current_folder, 99))
        
        # 1. 撈取資料庫中「同類型」的發送中警報
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

        to_cancel_actions = [] # 存放 (MQ訊息, 原DB紀錄)
        to_active_msgs = []   # 存放 MQ訊息

        # 建立本次解析的 Key Set
        current_keys = set()
        for res in parsed_results:
            key = (str(res['freewayId']), str(res['mainDirection']), 
                   float(res['fmileAge']), float(res['tmileAge']))
            current_keys.add(key)

        # --- 階段 A: 判定解除 (針對同類型) ---
        for key, record in db_map.items():
            is_in_current = key in current_keys
            
            # 尋找對應路段比對結束時間是否變更
            current_res = next((r for r in parsed_results if (
                str(r['freewayId']), str(r['mainDirection']), 
                float(r['fmileAge']), float(r['tmileAge'])) == key), None)
            time_changed = False
            if current_res:
                def to_compare_str(t_val):
                    if not t_val:
                        return ""
                    if isinstance(t_val, datetime.datetime):
                        return t_val.strftime("%Y-%m-%d %H:%M:%S")
                    # 將斜線與 T 替換，取前 19 碼字元
                    return str(t_val).replace('T', ' ').replace('/', '-').split('+')[0][:19]

                db_time = to_compare_str(record['expiresTime'])
                curr_time = to_compare_str(current_res['expiresTime'])
                time_changed = (db_time != curr_time)
            is_expired = now > record['expiresTime']

            if not is_in_current or time_changed or is_expired:
                # 封裝解除訊息與原始紀錄，以便發送成功後刪除
                cancel_msg = transform_to_cancel_format(record)
                to_cancel_actions.append((cancel_msg, record))

        # --- 階段 B: 判定成立 ---
        # 重新確認 DB 剩餘狀態 (排除掉即將解除的，避免重複插入)
        remaining_db_keys = set(db_map.keys()) - { (str(r[1]['freewayId']), str(r[1]['mainDirection']), float(r[1]['fmileAge']), float(r[1]['tmileAge'])) for r in to_cancel_actions }

        for i, res in enumerate(parsed_results, 1):
            key = (str(res['freewayId']), str(res['mainDirection']), 
                   float(res['fmileAge']), float(res['tmileAge']))
            
            if key not in remaining_db_keys:
                time_info = {"effective": res['effectiveTime'], "expires": res['expiresTime']}
                new_json = transform_to_tcss_format(res, current_folder, time_info, sequence=i)
                to_active_msgs.append(new_json)
                
                # 準備寫入 DB 的資料
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
                # 注意：這裡我們先不 insert，等 step6 循環到該處處理
                # 但為了邏輯完整，我們將 db_data 帶在 msg 旁邊回傳
                new_json['_db_payload'] = db_data

        return to_cancel_actions, to_active_msgs