#!/bin/bash

# 設定基礎路徑
BASE_LOG_DIR="/home/sc/weather_forecast/logs"
# 取得昨天日期 (格式: 20260513)
YESTERDAY=$(date -d "yesterday" +%Y%m%d)

# 定義要處理的 Log 檔案名稱 (不含副檔名)
LOG_NAMES=("weather_redis" "weather_mq" "weather_line" "redis_sync.log")

for NAME in "${LOG_NAMES[@]}"; do
    # 定義原始檔案路徑與目標目錄
    SOURCE_FILE="$BASE_LOG_DIR/$NAME.log"
    TARGET_DIR="$BASE_LOG_DIR/$NAME"
    
    # 1. 確保子目錄存在 (例如 /logs/weather_redis)
    mkdir -p "$TARGET_DIR"

    # 2. 檢查原始 Log 是否存在，存在才進行搬移
    if [ -f "$SOURCE_FILE" ]; then
        # 搬移並重新命名為 weather_redis_20260513.log
        mv "$SOURCE_FILE" "$TARGET_DIR/${NAME}_$YESTERDAY.log"
        
        # 3. 建立新的空白 Log 檔，讓服務繼續寫入
        touch "$SOURCE_FILE"
    fi

    # 4. 清理該目錄下超過 90 天的舊 Log
    # 搜尋該子目錄下所有 .log 檔，超過 90 天則刪除
    find "$TARGET_DIR" -name "${NAME}_*.log" -type f -mtime +90 -exec rm -f {} +
done

echo "[$YESTERDAY] Log 歸檔至各自目錄與清理完成。"