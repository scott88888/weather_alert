#!/bin/bash

# ==========================================
# 設定區
# ==========================================
REMOTE_USER="freeway"
REMOTE_IP="10.104.6.31"
REMOTE_BASE_PATH="/home/freeway/sc/getapi/data/incoming"
LOCAL_BASE_PATH="/home/freeway/SC/weather/weather_forecast/source" 

FOLDERS=("W-C0033-001" "W-C0034-001" "W-C0033-003" "W-C0033-004" "W-C0033-005" "W-C0033-006")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
mkdir -p "$LOG_DIR"

TODAY=$(date +%Y%m%d)
YESTERDAY=$(date -d "yesterday" +%Y%m%d)
LOG_FILE="${LOG_DIR}/source_data_${TODAY}.log"
LOCK_FILE="/tmp/sftp_cron_sync.lock"

log_msg() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# ==========================================
# 核心邏輯 (最穩健的 Linux 標準 flock 宣告)
# ==========================================

# 用最直覺的方式檢查鎖。如果鎖失敗，直接寫 Log 並退出
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [警告] 偵測到上一分鐘的同步尚未結束，本次自動退出。" >> "$LOG_FILE"
  exit 1
fi

log_msg "=================== 同步作業開始 ==================="

# --------------------------------------------------
# 自動歸檔與根目錄清理機制：
# 掃描根目錄下所有「非今天」的舊檔案，依檔名日期搬移至對應資料夾
# 註：mv 搬移後即可確保根目錄舊檔完全清除，不殘留歷史檔案
# --------------------------------------------------
log_msg "[歸檔機制] 啟動歷史檔案歸檔與根目錄清理程序..."

for FOLDER in "${FOLDERS[@]}"
do
  # 搜尋根目錄下 (-maxdepth 1) 所有不是今天檔名 (*_${TODAY}*) 的舊檔案
  FILES_TO_MOVE=$(find "${LOCAL_BASE_PATH}/${FOLDER}" -maxdepth 1 -type f \( -name "*.json" -o -name "*.cap" \) ! -name "*_${TODAY}*" 2>/dev/null)
  
  if [ -n "$FILES_TO_MOVE" ]; then
    echo "$FILES_TO_MOVE" | while read -r file; do
      [ -f "$file" ] || continue
      file_name=$(basename "$file")
      
      # 自動從檔名提取 8 位數日期 (YYYYMMDD)，若無則預設用昨天日期
      file_date=$(echo "$file_name" | grep -oE '[0-9]{8}' | head -n 1)
      if [ -z "$file_date" ]; then
        file_date="$YESTERDAY"
      fi
      
      target_dir="${LOCAL_BASE_PATH}/${FOLDER}/${file_date}"
      mkdir -p "$target_dir"
      
      # 使用 mv 將檔案搬移進日期資料夾（從根目錄移除）
      mv "$file" "$target_dir/"
      log_msg "[歸檔機制] 已將舊檔搬移離根目錄: ${file_name} -> ${file_date}/"
    done
  fi

  # (選用) 如需自動清理超過 30 天的歷史歸檔資料夾，可取消下一行註解
  # find "${LOCAL_BASE_PATH}/${FOLDER}" -mindepth 1 -maxdepth 1 -type d -mtime +30 -exec rm -rf {} +
done
log_msg "[歸檔機制] 歷史舊檔案歸檔與清理完畢。"
log_msg "----------------------------------------------------"

# --------------------------------------------------
# SFTP 撈取最新檔案
# --------------------------------------------------
for FOLDER in "${FOLDERS[@]}"
do
  log_msg "【資料夾: ${FOLDER}】開始處理..."
  mkdir -p "${LOCAL_BASE_PATH}/${FOLDER}/"

  REMOTE_LATEST_FILE=$(ssh -o ConnectTimeout=5 "${REMOTE_USER}@${REMOTE_IP}" "ls -t ${REMOTE_BASE_PATH}/${FOLDER}/*.json ${REMOTE_BASE_PATH}/${FOLDER}/*.cap 2>/dev/null | head -n 1" || true)

  if [ -z "$REMOTE_LATEST_FILE" ]; then
    log_msg "【資料夾: ${FOLDER}】遠端目錄為空，或無任何 .json / .cap 檔案。跳過。"
    log_msg "----------------------------------------------------"
    continue
  fi

  FILE_NAME=$(basename "$REMOTE_LATEST_FILE")
  log_msg "【資料夾: ${FOLDER}】偵測到遠端最新檔案為: ${FILE_NAME}"

  # 從遠端檔名自動解析日期
  REMOTE_FILE_DATE=$(echo "$FILE_NAME" | grep -oE '[0-9]{8}' | head -n 1)
  if [ -z "$REMOTE_FILE_DATE" ]; then
    REMOTE_FILE_DATE="$TODAY"
  fi

  # 判斷：本機根目錄或對應歸檔目錄中已有相同檔案，則略過不重複下載
  if [ -f "${LOCAL_BASE_PATH}/${FOLDER}/${FILE_NAME}" ] || [ -f "${LOCAL_BASE_PATH}/${FOLDER}/${REMOTE_FILE_DATE}/${FILE_NAME}" ]; then
    log_msg "【資料夾: ${FOLDER}】本機（或歸檔區 ${REMOTE_FILE_DATE}/）已存在相同檔案 [${FILE_NAME}]。略過不下載。"
  else
    log_msg "【資料夾: ${FOLDER}】本機無此檔案，開始透過 SFTP 下載..."
    
    sftp -b - "${REMOTE_USER}@${REMOTE_IP}" <<EOF >> "$LOG_FILE" 2>&1 || true
get "${REMOTE_BASE_PATH}/${FOLDER}/${FILE_NAME}" "${LOCAL_BASE_PATH}/${FOLDER}/${FILE_NAME}"
quit
EOF
    
    if [ -f "${LOCAL_BASE_PATH}/${FOLDER}/${FILE_NAME}" ]; then
      log_msg "【資料夾: ${FOLDER}】成功下載檔案: ${FILE_NAME}"
    else
      log_msg "【資料夾: ${FOLDER}】[錯誤] 檔案傳輸失敗。"
    fi
  fi
  log_msg "----------------------------------------------------"
done

log_msg "=================== 同步作業結束 ==================="
