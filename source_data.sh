#!/bin/bash

# ==========================================
# 強制補足環境變數 (Cron 必備)
# ==========================================
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

# ==========================================
# 設定區
# ==========================================
REMOTE_USER="freeway"
REMOTE_IP="10.104.6.31"
REMOTE_BASE_PATH="/home/freeway/sc/getapi/data/incoming"
LOCAL_BASE_PATH="/home/freeway/SC/weather/weather_forecast/source" 

# 【關鍵】請確保這是你 freeway 帳號用來免密碼登入的私鑰路徑
SSH_KEY="/home/freeway/.ssh/id_rsa"

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
# 核心邏輯
# ==========================================
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [警告] 偵測到上一分鐘的同步尚未結束，本次自動退出。" >> "$LOG_FILE"
  exit 1
fi

log_msg "=================== 同步作業開始 ==================="

# --------------------------------------------------
# 每天晚上 12:10 分自動清理昨天舊檔
# --------------------------------------------------
CURRENT_TIME=$(date +%H%M)
if [ "$CURRENT_TIME" = "0010" ]; then
  YESTERDAY=$(date -d "yesterday" +%Y%m%d)
  log_msg "[清理機制] 偵測到目前時間為午夜 12:10，啟動舊檔清理程序..."
  find "$LOCAL_BASE_PATH" -type f \( -name "*_${YESTERDAY}*.json" -o -name "*_${YESTERDAY}*.cap" \) -delete || true
  log_msg "[清理機制] 昨天舊檔案清理完畢。"
  log_msg "----------------------------------------------------"
fi

# --------------------------------------------------
# SFTP 撈取最新檔案
# --------------------------------------------------
for FOLDER in "${FOLDERS[@]}"
do
  log_msg "【資料夾: ${FOLDER}】開始處理..."
  mkdir -p "${LOCAL_BASE_PATH}/${FOLDER}/"

  # 【修正】加上 -i $SSH_KEY 確保排程環境下能正確使用金鑰，並加入 StrictHostKeyChecking=no 防止阻擋
  REMOTE_LATEST_FILE=$(ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=5 "${REMOTE_USER}@${REMOTE_IP}" "ls -t ${REMOTE_BASE_PATH}/${FOLDER}/*.json ${REMOTE_BASE_PATH}/${FOLDER}/*.cap 2>/dev/null | head -n 1" || true)

  if [ -z "$REMOTE_LATEST_FILE" ]; then
    log_msg "【資料夾: ${FOLDER}】遠端目錄為空，或無任何 .json / .cap 檔案。跳過。"
    log_msg "----------------------------------------------------"
    continue
  fi

  FILE_NAME=$(basename "$REMOTE_LATEST_FILE")
  log_msg "【資料夾: ${FOLDER}】偵測到遠端最新檔案為: ${FILE_NAME}"

  if [ -f "${LOCAL_BASE_PATH}/${FOLDER}/${FILE_NAME}" ]; then
    log_msg "【資料夾: ${FOLDER}】本機已存在相同檔案 [${FILE_NAME}]。略過不下載。"
  else
    log_msg "【資料夾: ${FOLDER}】本機無此檔案，開始透過 SFTP 下載..."
    
    # 【修正】SFTP 下載同樣強制指定金鑰路徑 -i $SSH_KEY
    sftp -i "$SSH_KEY" -o StrictHostKeyChecking=no -b - "${REMOTE_USER}@${REMOTE_IP}" <<EOF >> "$LOG_FILE" 2>&1 || true
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