#!/usr/bin/env bash
# backup.sh — суточный бэкап конфигов и состояния
# запуск по cron: 0 3 * * * /path/backup.sh >> /path/backup.log 2>&1
set -euo pipefail

STACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${STACK_DIR}/backups"
KEEP_DAYS=14
STAMP="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="${BACKUP_DIR}/panel_${STAMP}.tar.gz"

mkdir -p "$BACKUP_DIR"

# собираем только то, что реально нужно
FILES=()
for f in pool.json dropped.json pool_healthy.json proxies.txt .env; do
    [ -f "${STACK_DIR}/${f}" ] && FILES+=("$f")
done

if [ ${#FILES[@]} -eq 0 ]; then
    echo "нечего бэкапить"
    exit 0
fi

tar -czf "$ARCHIVE" -C "$STACK_DIR" "${FILES[@]}"
echo "создан: $ARCHIVE ($(du -h "$ARCHIVE" | cut -f1))"

# ротация: удаляем старше KEEP_DAYS
find "$BACKUP_DIR" -name 'panel_*.tar.gz' -type f -mtime "+${KEEP_DAYS}" -delete
echo "ротация: оставлено $(find "$BACKUP_DIR" -name 'panel_*.tar.gz' | wc -l)"
