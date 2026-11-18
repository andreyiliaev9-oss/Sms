# cleanup.py — вычищает мёртвые эндпоинты с диска и из кэша
# Python 3.10+, только stdlib
import json
import threading
import time
from pathlib import Path

POOL_PATH = Path("pool.json")
CACHE_PATH = Path("pool_healthy.json")
DROPPED_PATH = Path("dropped.json")
_lock = threading.Lock()


def load_dropped() -> set[str]:
    if not DROPPED_PATH.exists():
        return set()
    try:
        raw = json.loads(DROPPED_PATH.read_text(encoding="utf-8"))
        return set(raw.get("names", []))
    except json.JSONDecodeError:
        return set()


def save_dropped(names: set[str]) -> None:
    payload = {"names": sorted(names), "updated_at": time.time()}
    DROPPED_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                            encoding="utf-8")


def mark(name: str) -> None:
    """Помечает эндпоинт на выброс. Потокобезопасно."""
    with _lock:
        names = load_dropped()
        names.add(name)
        save_dropped(names)


def unmark(name: str) -> None:
    with _lock:
        names = load_dropped()
        names.discard(name)
        save_dropped(names)


def purge(dry_run: bool = False) -> dict:
    """Удаляет помеченные из pool.json и кэша. Возвращает отчёт."""
    with _lock:
        dropped = load_dropped()
        if not dropped:
            return {"removed": [], "kept": 0, "dry_run": dry_run}

        # pool.json
        removed: list[str] = []
        kept_pool: list[dict] = []
        if POOL_PATH.exists():
            pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
            for ep in pool:
                if ep.get("name") in dropped:
                    removed.append(ep.get("name", "?"))
                else:
                    kept_pool.append(ep)
            if not dry_run:
                POOL_PATH.write_text(
                    json.dumps(kept_pool, ensure_ascii=False, indent=2),
                    encoding="utf-8")

        # pool_healthy.json — помечаем dead: true
        if CACHE_PATH.exists():
            try:
                cache = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
                for key in ("alive", "flood"):
                    for ep in cache.get(key, []):
                        if ep.get("name") in dropped:
                            ep["dead"] = True
                if not dry_run:
                    CACHE_PATH.write_text(
                        json.dumps(cache, ensure_ascii=False, indent=2),
                        encoding="utf-8")
            except json.JSONDecodeError:
                pass

        if not dry_run:
            save_dropped(set())

        return {"removed": removed, "kept": len(kept_pool), "dry_run": dry_run}


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    rep = purge(dry_run=dry)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
