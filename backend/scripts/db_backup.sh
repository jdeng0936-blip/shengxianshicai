#!/bin/bash
# 数据库备份脚本 — 掘进工作面规程智能生成平台
# 用法: bash scripts/db_backup.sh [输出目录]
#
# 示例:
#   bash scripts/db_backup.sh                    # 备份到 ./backups/
#   bash scripts/db_backup.sh /path/to/backup    # 备份到指定目录

set -euo pipefail

# 配置
CONTAINER_NAME="excavation-postgres"
DB_NAME="excavation_platform"
DB_USER="postgres"
OUTPUT_DIR="${1:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${OUTPUT_DIR}/excavation_${TIMESTAMP}.dump"

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

# 创建输出目录
mkdir -p "$OUTPUT_DIR"

# 执行备份
echo "🔄 开始备份数据库 ${DB_NAME}..."
$DOCKER exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" -Fc "$DB_NAME" > "$BACKUP_FILE"

# 验证
FILE_SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
echo "✅ 备份完成: ${BACKUP_FILE} (${FILE_SIZE})"
echo ""
echo "恢复命令: bash scripts/db_restore.sh ${BACKUP_FILE}"
