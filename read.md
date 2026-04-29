氣象預警自動化系統開發進度 (2026-04-27)
本文件紀錄了氣象預警自動化系統目前的開發狀態與已完成之技術規格。
✅ 已完成事項 (Completed)
檔案名稱 功能說明 關鍵邏輯

config.py 系統全域配置 包含 TARGET_FOLDERS 清
單、DB/Redis 連線資訊、災害
類型代碼對照表。

file_reader.py 最新檔案讀取器 精確讀取:僅掃描 config 指定
的資料夾。日期排序:根據檔
名時間戳記(
YYYYMMDDHHMMSS)抓取
最新 .json 或 .cap。
weather_parser.py 專屬解析引擎 ● 分流機制:使用
dispatch_map 確保不
同類型的檔案進入獨立
的私有方法。
● 001 濃霧:過濾
phenomena == "濃霧"
,保留時間資訊。
● 003/006:顏色過濾(黃/
紅)並提取告警基準。
● 004/005:標題嚴格比對
,Regex 提取行政區並
支援複合區域拆解。
gecode_to_range.py 路網轉化模組 ● 模糊比對:支援縣市級
Geocode(如 10017)自
動匹配下轄所有路段。
● 方向判定:統一 1=北/
東向,3=南/西向。
● 里程合併:自動將連續
行政區路段合併為單一
里程範圍。

️ 待開發事項 (To-Do)

第五步:產生標準 TCSS JSON (formatter.py 重構)
● 格式標準化:將路段里程、時間、告警基準組合成 TCSS Level 2 (成立) JSON。
● 動態描述生成:根據類型自動產出警報文字(如:國道一號南向...濃霧特報)。
第六步:主流程整合與發送 (main.py)
● 循環調度:定時掃描並執行全流程。
● 事件去重:記錄已發送事件,避免重複告警,並處理解除(Level 1)訊息。
● 多路徑發送:同時推送至 Redis 告警系統與 MariaDB 資料庫。
💾 下次開發續接指令
「我正在開發氣象預警自動化系統,目前已完成:
1. weather_parser.py:解析氣象原始碼,產出 geocodes 與時間。
2. gecode_to_range.py:將 geocodes 轉化為高速公路里程(支援模糊匹配與方向判
定)。
現在我要進行第五步:產生標準 TCSS JSON (formatter.py)
請幫我設計一個 formatter.py,將解析出的里程區間與時間,依照 TCSS 規範組合成
Level 2 (成立) 的訊息格式,並串接 config.py 中的 INCIDENT_TYPE_MAP。」