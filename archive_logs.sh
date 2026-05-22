#!/bin/bash

# ==========================================
# 強制補足環境變數 (Cron 必備)
# ==========================================
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

# ==========================================
# 設定區 (已修正為你實際的 freeway 路徑)
# ==========================================
BASE_LOG_DIR="/home/freeway/SC/weather/weather_forecast/logs"

# 取得昨天日期 (格式: 20260521)
YESTERDAY=$(date -d "yesterday" +%Y%m%d)

# 定義要處理的 Log 檔案名稱 (不含副檔名)
LOG_NAMES=("weather_redis" "weather_mq" "weather_line" "redis_sync")

# ==========================================
# 核心邏輯
# ==========================================
for NAME in "${LOG_NAMES[@]}"; do
    # 定義原始檔案路徑與目標目錄
    SOURCE_FILE="$BASE_LOG_DIR/$NAME.log"
    TARGET_DIR="$BASE_LOG_DIR/$NAME"
    
    # 1. 確保子目錄存在 (例如 /logs/weather_redis)
    mkdir -p "$TARGET_DIR"

    # 2. 檢查原始 Log 是否存在，存在才進行備份與清空
    if [ -f "$SOURCE_FILE" ]; then
        # 複製到子目錄，並加上昨天日期
        cp "$SOURCE_FILE" "$TARGET_DIR/${NAME}_$YESTERDAY.log"
        
        # 利用 > 符號直接清空原始 Log 檔案，維持 Inode，Python 服務不中斷
        > "$SOURCE_FILE"
    fi

    # 4. 清理該目錄下超過 90 天的舊 Log
    find "$TARGET_DIR" -name "${NAME}_*.log" -type f -mtime +90 -exec rm -f {} +
done

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$YESTERDAY] Log 歸檔至各自目錄與清空完成。" >> "$BASE_LOG_DIR/archive_exec.log"