#!/bin/bash
# 数据库备份脚本: 自动探测运行环境 (Docker/本地) 执行 pg_dump
# 输出到 backups 目录，格式为主机兼容的自定义流 (-F c)

set -e

# 确保必要的路径在环境变量中
export PATH=$PATH:/usr/local/bin:/opt/homebrew/bin:/Applications/Postgres.app/Contents/Versions/latest/bin:/Applications/Docker.app/Contents/Resources/bin

# 环境配置
BACKUP_DIR="$(pwd)/backups"
DB_NAME="excavation_platform"
DB_USER="postgres"
CONTAINER_NAME="excavation-postgres"

# 创建目录
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_${TIMESTAMP}.dump"

echo "======================================"
echo "🛡️  开始备份数据库: $DB_NAME"
echo "======================================"

if command -v docker &> /dev/null && docker ps | grep -q "$CONTAINER_NAME"; then
    echo ">> 检测到 Docker 环境，使用容器内 pg_dump..."
    docker exec -t "$CONTAINER_NAME" pg_dump -U "$DB_USER" -F c -b -v -f "/tmp/db.dump" "$DB_NAME"
    docker cp "$CONTAINER_NAME":/tmp/db.dump "$BACKUP_FILE"
    docker exec -t "$CONTAINER_NAME" rm /tmp/db.dump
elif command -v pg_dump &> /dev/null; then
    echo ">> 检测到原生 Postgres 环境，使用本地 pg_dump..."
    export PGPASSWORD=postgres
    pg_dump -U "$DB_USER" -h localhost -p 5432 -F c -b -v -f "$BACKUP_FILE" "$DB_NAME"
else
    echo "❌ 错误: 未找到 docker 或 pg_dump，请检查环境变量 PATH！"
    exit 1
fi

echo "======================================"
echo "✅ 备份成功！文件已保存至:"
echo "   $BACKUP_FILE"
echo "======================================"
