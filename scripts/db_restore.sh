#!/bin/bash
# 数据库恢复脚本: 自动探测运行环境 (Docker/本地) 执行 pg_restore
# 用法: bash scripts/db_restore.sh <备份文件路径>

set -e

export PATH=$PATH:/usr/local/bin:/opt/homebrew/bin:/Applications/Postgres.app/Contents/Versions/latest/bin:/Applications/Docker.app/Contents/Resources/bin

# 环境配置
DB_NAME="excavation_platform"
DB_USER="postgres"
CONTAINER_NAME="excavation-postgres"

if [ -z "$1" ]; then
    echo "❌ 错误: 未指定备份文件！"
    echo "用法: bash scripts/db_restore.sh <备份文件路径>"
    echo "现有备份文件："
    ls -1 $(pwd)/backups/*.dump 2>/dev/null || echo "(无可用备份)"
    exit 1
fi

RESTORE_FILE="$1"

if [ ! -f "$RESTORE_FILE" ]; then
    echo "❌ 错误: 备份文件 '$RESTORE_FILE' 不存在！"
    exit 1
fi

echo "======================================"
echo "⚠️  准备恢复数据库: $DB_NAME"
echo "⚠️  警告: 将执行清空覆盖操作 (-c --if-exists)"
echo ">> 使用备份文件: $RESTORE_FILE"
echo "======================================"

read -p "是否确认恢复？输入 'yes' 继续: " confirm
if [ "$confirm" != "yes" ]; then
    echo "已取消操作。"
    exit 0
fi

if command -v docker &> /dev/null && docker ps | grep -q "$CONTAINER_NAME"; then
    echo ">> 检测到 Docker 环境，使用容器内 pg_restore..."
    docker cp "$RESTORE_FILE" "$CONTAINER_NAME":/tmp/restore.dump
    # -c 先删除对象, --if-exists 可以忽略对象不存在报错, -d 指定数据库名
    docker exec -t "$CONTAINER_NAME" pg_restore -U "$DB_USER" -d "$DB_NAME" -c --if-exists -v /tmp/restore.dump || true
    docker exec -t "$CONTAINER_NAME" rm /tmp/restore.dump
    echo "✅ 容器内恢复执行完毕！(请向上检查日志有无严重报错, warning可忽略)"
elif command -v pg_restore &> /dev/null; then
    echo ">> 检测到原生 Postgres 环境，使用本地 pg_restore..."
    export PGPASSWORD=postgres
    pg_restore -U "$DB_USER" -h localhost -p 5432 -d "$DB_NAME" -c --if-exists -v "$RESTORE_FILE" || true
    echo "✅ 本地恢复执行完毕！(请向上检查日志有无严重报错, warning可忽略)"
else
    echo "❌ 错误: 未找到 docker 或 pg_restore，请检查环境变量 PATH！"
    exit 1
fi
