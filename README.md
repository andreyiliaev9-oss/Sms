# sms-panel

Стек: движок рассылки + бот + API + Prometheus + Grafana + Alertmanager.

## Файлы

- `core2.py` — движок: реестр, автобан, регенерация
- `metrics.py` — кольцевой буфер метрик
- `prom2.py` — экспорт в Prometheus
- `health.py` — healthcheck пула
- `cache.py` — кэш живого пула с TTL
- `cleanup.py` — вычистка мёртвых эндпоинтов
- `scheduler.py` — ротация номеров, профили
- `api.py` — FastAPI: веб-панель, `/prom`, `/alert`
- `panel.py` — бот-нотифаер
- `scraper.py` — сборщик пула из каталогов
- `prometheus.yml`, `alerts.yml`, `alertmanager.yml` — мониторинг
- `grafana-dashboard.json` — дашборд
- `Dockerfile`, `docker-compose.yml` — сборка
- `install.sh`, `backup.sh`, `restore.sh` — скрипты

## Быстрый старт

```bash
bash install.sh
