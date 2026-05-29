#!/bin/bash

# ==========================================
# 強制補足環境變數 (Cron 必備)
# ==========================================
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

# ==========================================
# 設定區 (已修正為測試機正確路徑)
# ==========================================
BASE_LOG_DIR="/home/sc/weather_forecast/logs"

# 取得昨天日期 (格式: 20260527)
YESTERDAY=$(date -d "yesterday" +%Y%m%d)

# 定義要處理的 Log 名稱
LOG_NAMES=("weather_redis" "weather_mq" "weather_line" "redis_sync")

# ==========================================
# 核心邏輯
# ==========================================
for NAME in "${LOG_NAMES[@]}"; do
    # 【修正】原始 Log 檔案都在 logs/ 根目錄下
    # 例如: /home/sc/weather_forecast/logs/weather_redis.log
    SOURCE_FILE="$BASE_LOG_DIR/$NAME.log"
    
    # 備份的目標子目錄
    # 例如: /home/sc/weather_forecast/logs/weather_redis
    TARGET_DIR="$BASE_LOG_DIR/$NAME"
    
    # 1. 確保子目錄存在，如果不存在就建立
    mkdir -p "$TARGET_DIR"

    # 2. 檢查原始 Log 是否存在，存在才進行備份與清空
    if [ -f "$SOURCE_FILE" ]; then
        # 複製並命名到子資料夾內 (例如: .../logs/weather_redis/weather_redis_20260527.log)
        cp "$SOURCE_FILE" "$TARGET_DIR/${NAME}_$YESTERDAY.log"
        
        # 利用 > 符號直接清空 logs/ 下的原始 Log 檔案，維持 Inode
        > "$SOURCE_FILE"
    fi

    # 3. 清理該子目錄下超過 90 天的舊 Log
    find "$TARGET_DIR" -name "${NAME}_*.log" -type f -mtime +90 -exec rm -f {} +
done

# 確保紀錄執行的 log 檔資料夾存在
mkdir -p "$BASE_LOG_DIR"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$YESTERDAY] Log 歸檔至各自目錄與清空完成。" >> "$BASE_LOG_DIR/archive_exec.log"