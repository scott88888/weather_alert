#!/bin/bash
BACKUP_DIR="/home/sc/weather_forecast/backups/logs"
SOURCE_DIR="/home/sc/weather_forecast/logs"
DATE=$(date +%Y%m%d)

mkdir -p $BACKUP_DIR
# 將昨天的日誌壓縮備份
tar -czf $BACKUP_DIR/weather_log_$DATE.tar.gz -C $SOURCE_DIR .