import pymysql
import logging
from config import get_db_connection

logger = logging.getLogger("RoadLookup")

class RoadNetworkLookup:
    def __init__(self):
        self.lookup_table = {}
        self._load_data()

    def _load_data(self):
        conn = None
        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                sql = """
                    SELECT freewayId, mainDirection, fmileAge, tmileAge, 
                           controlCenterId, countyName, townName, geocode
                    FROM RoadMergedLocationTbl 
                    WHERE geocode IS NOT NULL
                    ORDER BY freewayId, mainDirection, fmileAge
                """
                cursor.execute(sql)
                rows = cursor.fetchall()
                
                for row in rows:
                    # 確保轉為字串存儲
                    code = str(row['geocode']).split('.')[0]
                    if code not in self.lookup_table:
                        self.lookup_table[code] = []
                    self.lookup_table[code].append(row)
                
                logger.info(f"路網預載完成，共 {len(rows)} 筆。")
        except Exception as e:
            logger.error(f"預載失敗: {e}")
            raise
        finally:
            if conn: conn.close()

    def get_segments_by_geocodes(self, geocodes):
        """
        支援前綴匹配，例如 '64' (高雄) 可以對應到 '6401700'
        """
        all_segments = []
        seen_segments = set()
        
        # 清理 geocodes，確保都是乾淨的數字字串 (處理 64.0 -> '64')
        clean_geocodes = [str(g).split('.')[0] for g in geocodes]

        for target_geo in clean_geocodes:
            for table_geo, segments in self.lookup_table.items():
                # 關鍵修正：判斷路段表的碼是否以氣象局的碼開頭
                if table_geo.startswith(target_geo):
                    for seg in segments:
                        seg_id = (seg['freewayId'], seg['mainDirection'], seg['fmileAge'], seg['tmileAge'])
                        if seg_id not in seen_segments:
                            all_segments.append(seg)
                            seen_segments.add(seg_id)

        all_segments.sort(key=lambda x: (x['freewayId'], x['mainDirection'], x['fmileAge']))
        # 如果要基隆維持 5 筆，請直接改為: return all_segments
        return self._merge_road_segments(all_segments)

    def _merge_road_segments(self, segments):
        if not segments: return []
        merged = []
        current = None
        for seg in segments:
            is_continue = (
                current and 
                seg['freewayId'] == current['freewayId'] and 
                seg['mainDirection'] == current['mainDirection'] and
                seg['controlCenterId'] == current['controlCenterId'] and
                seg['fmileAge'] <= current['tmileAge']
            )
            if not is_continue:
                if current: merged.append(current)
                current = seg.copy()
            else:
                current['tmileAge'] = max(current['tmileAge'], seg['tmileAge'])
        if current: merged.append(current)
        return merged