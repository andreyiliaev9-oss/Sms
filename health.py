# health.py — прогон пула вхолостую
# Python 3.10+, requests
import json
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

import requests
from core2 import Endpoint, Limiter


@dataclass
class CheckResult:
    name: str
    status: str
    latency_ms: float
    code: int | None = None
    reason: str = ""


def _payload(ep: Endpoint, phone: str):
    raw = ep.body.format(phone=phone)
    hdrs = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", **ep.headers}
    if ep.body_type == "json":
        hdrs["Content-Type"] = "application/json"
        return raw.encode(), hdrs
    if ep.body_type == "form":
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        return raw.encode(), hdrs
    return dict(urllib.parse.parse_qsl(raw)), hdrs


def check_one(ep: Endpoint, phone: str, s: requests.Session, timeout: float = 6.0):
    data, hdrs = _payload(ep, phone)
    t0 = time.monotonic()
    try:
        r = s.request(ep.method, ep.url, data=data, headers=hdrs, timeout=timeout)
        ms = (time.monotonic() - t0) * 1000
        if r.status_code == 429:
            return CheckResult(ep.name, "flood", ms, r.status_code, "retry-after")
        if 200 <= r.status_code < 300:
            return CheckResult(ep.name, "ok", ms, r.status_code)
        return CheckResult(ep.name, "fail", ms, r.status_code, "bad status")
    except requests.RequestException as e:
        ms = (time.monotonic() - t0) * 1000
        return CheckResult(ep.name, "fail", ms, None, type(e).__name__)


def healthcheck(pool: list[Endpoint], phone: str, limiter: Limiter | None = None) -> dict:
    limiter = limiter or Limiter(start_rps=10, min_rps=5, max_rps=10)
    results, alive, flood, dead = [], [], [], []
    with requests.Session() as s:
        for ep in pool:
            limiter.wait()
            res = check_one(ep, phone, s)
            results.append(res)
            if res.status == "ok":
                alive.append(ep)
            elif res.status == "flood":
                flood.append(ep)
            else:
                dead.append(ep)
    return {
        "total": len(pool),
        "alive": [e.name for e in alive],
        "flood": [e.name for e in flood],
        "dead": [e.name for e in dead],
        "details": [r.__dict__ for r in results],
        "_alive_eps": alive,
        "_flood_eps": flood,
    }


def load_pool(path: Path | str = "pool.json") -> list[Endpoint]:
    p = Path(path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    return [Endpoint(**item) for item in raw]


if __name__ == "__main__":
    import sys
    pool = load_pool()
    phone = sys.argv[1] if len(sys.argv) > 1 else "79990000000"
    rep = healthcheck(pool, phone)
    rep.pop("_alive_eps", None)
    rep.pop("_flood_eps", None)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
