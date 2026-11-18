#!/usr/bin/env bash
# restore.sh — восстановление из архива
# запуск: bash restore.sh backups/panel_20260101_030000.tar.gz
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $0 <archive.tar.gz>"
    exit 1
fi

ARCHIVE="$1"
[ -f "$ARCHIVE" ] || { echo "нет файла: $ARCHIVE"; exit 1; }

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# стоп api перед восстановлением
if docker compose -f "${STACK_DIR}/docker-compose.yml" ps --quiet api >/dev/null 2>&1; then
    echo "останавливаю api"
    docker compose -f "${STACK_DIR}/docker-compose.yml" stop api
fi

tar -xzf "$ARCHIVE" -C "$STACK_DIR"
echo "восстановлено из $ARCHIVE"

docker compose -f "${STACK_DIR}/docker-compose.yml" start api
echo "api запущен"
