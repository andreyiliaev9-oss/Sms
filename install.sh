#!/usr/bin/env bash
# install.sh — разворот стека на чистой Linux-машине
# запуск: bash install.sh
set -euo pipefail

RED='\033[0;31m'; GRN='\033[0;32m'; YEL='\033[1;33m'; NC='\033[0m'
say() { printf "${GRN}>>${NC} %s\n" "$*"; }
warn() { printf "${YEL}!!${NC} %s\n" "$*"; }
die() { printf "${RED}XX${NC} %s\n" "$*"; exit 1; }

# 1. зависимости
say "проверка docker"
command -v docker >/dev/null 2>&1 || die "docker не установлен"
if ! docker compose version >/dev/null 2>&1; then
    die "docker compose (v2) не найден"
fi

# 2. .env
if [ ! -f .env ]; then
    say "создаю .env"
    cat > .env <<EOF
TG_BOT_TOKEN=CHANGE_ME
ADMIN_ID=8141670312
GRAFANA_PASS=$(head -c 12 /dev/urandom | base64 | tr -d '/+=' | head -c 12)
EOF
    warn "пропиши TG_BOT_TOKEN в .env, потом перезапусти"
fi

# 3. pool.json / proxies.txt
[ -f pool.json ] || { say "создаю пустой pool.json"; echo '[]' > pool.json; }
[ -f proxies.txt ] || { say "создаю пустой proxies.txt"; echo '' > proxies.txt; }
mkdir -p backups

# 4. сборка и запуск
say "сборка и запуск"
docker compose up -d --build

# 5. ожидание api
say "жду api"
for i in $(seq 1 30); do
    if curl -sf http://127.0.0.1:8080/metrics >/dev/null 2>&1; then
        say "api поднялся"
        break
    fi
    sleep 2
    [ "$i" -eq 30 ] && die "api не отвечает за 60 секунд"
done

# 6. итог
say "стек поднят"
echo
echo "  api:         http://127.0.0.1:8080"
echo "  prometheus:  http://127.0.0.1:9090"
echo "  grafana:     http://127.0.0.1:3000 (admin / \$GRAFANA_PASS)"
echo "  alertmanager:http://127.0.0.1:9093"
echo
say "импорт дашборда: Grafana → Import → Upload JSON → grafana-dashboard.json"
say "заполни pool.json своими эндпоинтами и нажми /maint в боте"
