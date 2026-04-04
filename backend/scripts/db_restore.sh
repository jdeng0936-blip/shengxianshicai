#!/bin/bash
# 数据库恢复脚本 — 掘进工作面规程智能生成平台
# 用法: bash scripts/db_restore.sh <备份文件路径>
#
# 示例:
#   bash scripts/db_restore.sh ./backups/excavation_20260322_213000.dump
#
# ⚠️ 警告: 此操作会删除当前数据库并从备份恢复！

set -euo pipefail

# 配置
CONTAINER_NAME="excavation-postgres"
DB_NAME="excavation_platform"
DB_USER="postgres"
BACKUP_FILE="${1:-}"

# 参数检查
if [ -z "$BACKUP_FILE" ]; then
    echo "❌ 用法: bash scripts/db_restore.sh <备份文件路径>"
    echo "   例如: bash scripts/db_restore.sh ./backups/excavation_20260322_213000.dump"
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ 备份文件不存在: ${BACKUP_FILE}"
    exit 1
fi

# 检查 Docker
if ! command -v docker &>/dev/null; then
    DOCKER="/Applications/Docker.app/Contents/Resources/bin/docker"
    if [ ! -f "$DOCKER" ]; then
        echo "❌ 未找到 docker 命令"
        exit 1
    fi
else
    DOCKER="docker"
fi

# 检查容器运行状态
if ! $DOCKER ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "❌ 容器 ${CONTAINER_NAME} 未运行"
    exit 1
fi

# 二次确认
FILE_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "⚠️  即将从备份恢复数据库（当前数据将被覆盖）"
echo "   备份文件: ${BACKUP_FILE} (${FILE_SIZE})"
echo ""
read -p "确认恢复? (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "已取消"
    exit 0
fi

# 断开所有活跃连接
echo "🔄 断开数据库活跃连接..."
$DOCKER exec "$CONTAINER_NAME" psql -U "$DB_USER" -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${DB_NAME}' AND pid <> pg_backend_pid();" \
    >/dev/null 2>&1

# 重建数据库
echo "🔄 重建数据库..."
$DOCKER exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "DROP DATABASE IF EXISTS ${DB_NAME};"
$DOCKER exec "$CONTAINER_NAME" psql -U "$DB_USER" -c "CREATE DATABASE ${DB_NAME};"
$DOCKER exec "$CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 拷入容器并恢复
echo "🔄 恢复数据..."
$DOCKER cp "$BACKUP_FILE" "${CONTAINER_NAME}:/tmp/backup.dump"
$DOCKER exec "$CONTAINER_NAME" pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl /tmp/backup.dump
$DOCKER exec "$CONTAINER_NAME" rm /tmp/backup.dump

echo "✅ 数据库恢复完成！"
echo ""
echo "⚠️  如果后端正在运行，请重启后端以重新建立数据库连接。"
