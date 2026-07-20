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
# 修正與新增：每天午夜 (00:00~00:59) 自動將昨天舊檔歸檔至日期資料夾
# --------------------------------------------------
CURRENT_HOUR=$(date +%H)
if true; then
  YESTERDAY=$(date -d "yesterday" +%Y%m%d)
  log_msg "[歸檔機制] 偵測到目前為午夜時段，啟動昨天 (${YESTERDAY}) 檔案歸檔程序..."
  
  for FOLDER in "${FOLDERS[@]}"
  do
    TARGET_DIR="${LOCAL_BASE_PATH}/${FOLDER}/${YESTERDAY}"
    
    # 檢查該資料夾下是否有昨天的檔案，有的話才處理
    # 這裡使用 find 尋找檔名包含昨天日期，且「不在」剛建立的日期資料夾內的檔案
    FILES_TO_MOVE=$(find "${LOCAL_BASE_PATH}/${FOLDER}" -maxdepth 1 -type f \( -name "*_${YESTERDAY}*.json" -o -name "*_${YESTERDAY}*.cap" \))
    
    if [ -n "$FILES_TO_MOVE" ]; then
      mkdir -p "$TARGET_DIR"
      log_msg "[歸檔機制] 建立歸檔資料夾: ${TARGET_DIR}"
      
      echo "$FILES_TO_MOVE" | while read -r file; do
        mv "$file" "$TARGET_DIR/"
        log_msg "[歸檔機制] 已搬移: $(basename "$file") -> ${YESTERDAY}/"
      done
    fi
  done
  log_msg "[歸檔機制] 昨天舊檔案歸檔完畢。"
  log_msg "----------------------------------------------------"
fi

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

  # 修改判斷：本機根目錄或歸檔目錄有相同檔案，都視為已下載
  if [ -f "${LOCAL_BASE_PATH}/${FOLDER}/${FILE_NAME}" ] || [ -f "${LOCAL_BASE_PATH}/${FOLDER}/${YESTERDAY}/${FILE_NAME}" ]; then
    log_msg "【資料夾: ${FOLDER}】本機（或歸檔區）已存在相同檔案 [${FILE_NAME}]。略過不下載。"
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


