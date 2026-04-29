import pymysql
import logging
from config import DB_CONFIG

logger = logging.getLogger("DBManager")

class DBManager:
    def __init__(self):
        self.config = DB_CONFIG

    def get_connection(self):
        return pymysql.connect(**self.config)

    def fetch_active_alerts(self):
        """撈取目前所有發送中的警報"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT * FROM RoadAlertControlSwitchTbl WHERE is_active = 1"
                cursor.execute(sql)
                return cursor.fetchall()
        finally:
            conn.close()

    def insert_alert(self, data):
        """插入新警報事件"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                    INSERT INTO RoadAlertControlSwitchTbl (
                        incidentId, alertType, freewayId, mainDirection, 
                        fmileAge, tmileAge, expiresTime, controlCenterId, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                """
                cursor.execute(sql, (
                    data['incidentId'], data['alertType'], data['freewayId'],
                    data['mainDirection'], data['fmileAge'], data['tmileAge'],
                    data['expiresTime'], data['controlCenterId']
                ))
            conn.commit()
        finally:
            conn.close()

    def delete_alert(self, incident_id):
        """物理刪除或標記解除 (依您需求採 DELETE)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "DELETE FROM RoadAlertControlSwitchTbl WHERE incidentId = %s"
                cursor.execute(sql, (incident_id,))
            conn.commit()
        finally:
            conn.close()
            
    def insert_alert(self, data):
        """插入新警報事件 (改用 REPLACE 避免主鍵衝突)"""
        conn = self.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                    REPLACE INTO RoadAlertControlSwitchTbl (
                        incidentId, alertType, freewayId, mainDirection, 
                        fmileAge, tmileAge, expiresTime, controlCenterId, is_active
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 1)
                """
                cursor.execute(sql, (
                    data['incidentId'], data['alertType'], data['freewayId'],
                    data['mainDirection'], data['fmileAge'], data['tmileAge'],
                    data['expiresTime'], data['controlCenterId']
                ))
            conn.commit()
        finally:
            conn.close()