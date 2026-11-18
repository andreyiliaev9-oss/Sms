# prom2.py — метрики реестра в Prometheus
# Python 3.10+, prometheus_client
import time
from prometheus_client import Counter, Gauge, CollectorRegistry, generate_latest
from metrics import METRICS
from core2 import Registry

REGISTRY = CollectorRegistry()

# общие счётчики
SENT = Counter("panel_sent_total", "успешные отправки", ["profile"], registry=REGISTRY)
FAILED = Counter("panel_failed_total", "фейлы", ["profile"], registry=REGISTRY)
FLOOD = Counter("panel_flood_total", "флуд-ответы", registry=REGISTRY)
DEDUP = Counter("panel_dedup_total", "отсечённые дубли", registry=REGISTRY)
RPS = Gauge("panel_rps", "запросов в секунду", ["profile"], registry=REGISTRY)
UPTIME = Gauge("panel_uptime_seconds", "аптайм панели", registry=REGISTRY)

# метрики реестра
EP_LIVE = Gauge("panel_endpoint_live", "эндпоинт жив", ["name"], registry=REGISTRY)
EP_BANNED = Gauge("panel_endpoint_banned", "эндпоинт в бане", ["name"], registry=REGISTRY)
EP_STRIKES = Gauge("panel_endpoint_strikes", "страйки эндпоинта", ["name"], registry=REGISTRY)
REG_LIVE = Gauge("panel_registry_live_total", "живых в реестре", registry=REGISTRY)
REG_TOTAL = Gauge("panel_registry_total", "всего в реестре", registry=REGISTRY)
REG_BANNED = Counter("panel_registry_banned_total", "срабатываний бана", registry=REGISTRY)
REG_REGEN = Counter("panel_registry_regen_total", "снятий бана", registry=REGISTRY)


def sync_registry(reg: Registry) -> None:
    now = time.monotonic()
    eps = reg.all()
    live = 0
    for ep in eps:
        is_banned = now < ep.banned_until
        EP_LIVE.labels(ep.name).set(0 if is_banned else 1)
        EP_BANNED.labels(ep.name).set(1 if is_banned else 0)
        EP_STRIKES.labels(ep.name).set(ep.strikes)
        if not is_banned:
            live += 1
    REG_LIVE.set(live)
    REG_TOTAL.set(len(eps))
    REG_BANNED.inc(reg.stats["banned"])
    REG_REGEN.inc(reg.stats["regen"])


def sync_metrics() -> None:
    snap = METRICS.snapshot()
    RPS.labels("fast").set(snap["rps_by_profile"].get("fast", 0.0))
    RPS.labels("slow").set(snap["rps_by_profile"].get("slow", 0.0))
    UPTIME.set(snap["uptime"])
    SENT.labels("fast").inc(snap["by_profile"].get("fast", 0))
    SENT.labels("slow").inc(snap["by_profile"].get("slow", 0))


def render(reg: Registry) -> bytes:
    sync_metrics()
    sync_registry(reg)
    return generate_latest(REGISTRY)
