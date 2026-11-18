# cache.py — кэш живого пула с TTL
# Python 3.10+, только stdlib
import json
import time
from pathlib import Path

from core2 import Endpoint

CACHE_PATH = Path("pool_healthy.json")
DEFAULT_TTL = 3600.0


def _now() -> float:
    return time.time()


def save(alive: list[Endpoint], flood: list[Endpoint],
         dead_names: list[str], ttl: float = DEFAULT_TTL) -> None:
    payload = {
        "saved_at": _now(),
        "ttl": ttl,
        "alive": [ep.__dict__ for ep in alive],
        "flood": [ep.__dict__ for ep in flood],
        "dead": dead_names,
    }
    CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                          encoding="utf-8")


def load() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    age = _now() - payload.get("saved_at", 0)
    
    alive = [Endpoint(**ep) for ep in payload.get("alive", [])
             if not ep.get("dead")]
    flood = [Endpoint(**ep) for ep in payload.get("flood", [])
             if not ep.get("dead")]
             
    return {
        "alive": alive,
        "flood": flood,
        "dead": payload.get("dead", []),
        "age": age,
        "fresh": age <= payload.get("ttl", 0),
    }


def invalidate() -> None:
    CACHE_PATH.unlink(missing_ok=True)
