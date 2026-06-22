#!/bin/bash

# 定義基礎日誌目錄
LOG_DIR="/home/sc/weather_forecast/logs"

# 切換到 logs 目錄，如果目錄不存在就結束，避免後面指令出錯
cd "${LOG_DIR}" || exit 1

# 定義四個固定的服務名稱（對應檔名前綴與資料夾名稱）
SERVICES=("weather_redis" "weather_mq" "weather_line" "redis_sync")

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 開始執行日誌歸檔與清理作業 ==="

# ==========================================
# 功能一：遍歷四個服務，建立資料夾並移動檔案
# ==========================================
for SERVICE in "${SERVICES[@]}"; do
    # 確保對應的目標資料夾存在，不存在就建立
    if [ ! -d "${SERVICE}" ]; then
        mkdir -p "${SERVICE}"
        echo "建立資料夾: ${LOG_DIR}/${SERVICE}"
    fi

    # 【這裡修正了】加上 -regextype posix-extended 才能正確辨識 {4} 和 {2}
    find . -maxdepth 1 -regextype posix-extended -type f -name "${SERVICE}\.log\.[0-9]{4}-[0-9]{2}-[0-9]{2}" 2>/dev/null | while read -r log_file; do
        if [ -f "${log_file}" ]; then
            echo "正在歸檔: ${log_file} -> ${SERVICE}/"
            mv "${log_file}" "${SERVICE}/"
        fi
    done
done

# ==========================================
# 功能二：檢查這四個資料夾，刪除大於 90 天的舊檔案
# ==========================================
echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 開始檢查並清理 90 天前的舊檔案 ==="

for SERVICE in "${SERVICES[@]}"; do
    if [ -d "${SERVICE}" ]; then
        echo "檢查資料夾: ${SERVICE}/"
        
        # 尋找該資料夾下，修改時間超過 90 天的檔案，並直接刪除 (-delete)
        find "${SERVICE}" -type f -mtime +90 -print -delete | while read -r deleted_file; do
            echo "已刪除過期檔案: ${deleted_file}"
        done
    fi
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] === 作業完成 ==="