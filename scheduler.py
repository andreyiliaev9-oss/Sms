# scheduler.py — ротация номеров и профили эндпоинтов
# Python 3.10+, только stdlib
import random
import threading
import time
import urllib.parse
import requests
from dataclasses import dataclass

from core2 import Endpoint


@dataclass
class Target:
    phone: str
    rounds: int = 10
    profile: str = "fast"


class RoundRobin:
    def __init__(self, targets: list[Target]):
        self._targets = targets
        self._idx = 0
        self._lock = threading.Lock()

    def next(self) -> Target | None:
        with self._lock:
            if not self._targets:
                return None
            t = self._targets[self._idx % len(self._targets)]
            self._idx += 1
            return t

    def done(self) -> bool:
        with self._lock:
            return self._idx >= len(self._targets)


class Shuffle:
    def __init__(self, targets: list[Target]):
        self._pool = list(targets)
        random.shuffle(self._pool)
        self._lock = threading.Lock()

    def next(self) -> Target | None:
        with self._lock:
            if not self._pool:
                return None
            return self._pool.pop(0)

    def done(self) -> bool:
        with self._lock:
            return not self._pool


class ProfileLimiter:
    def __init__(self, fast_rps: float = 20.0, slow_rps: float = 1.0):
        self._rps = {"fast": fast_rps, "slow": slow_rps}
        self._lock = threading.Lock()
        self._next_at = {"fast": 0.0, "slow": 0.0}

    def wait(self, profile: str) -> None:
        with self._lock:
            rps = self._rps.get(profile, 1.0)
            now = time.monotonic()
            nxt = self._next_at.get(profile, 0.0)
            delay = max(0.0, nxt - now)
            self._next_at[profile] = max(now, nxt) + 1.0 / rps
        if delay > 0:
            time.sleep(delay)

    def set_rps(self, profile: str, rps: float) -> None:
        with self._lock:
            self._rps[profile] = max(0.1, rps)

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._rps)


def split_by_profile(pool: list[Endpoint]) -> dict[str, list[Endpoint]]:
    out: dict[str, list[Endpoint]] = {"fast": [], "slow": []}
    for ep in pool:
        out.setdefault(getattr(ep, "profile", "fast"), []).append(ep)
    return out


class RotationRunner:
    def __init__(self, strategy, pool: list[Endpoint],
                 proxies: list[str], limiter: ProfileLimiter | None = None):
        self._strategy = strategy
        self._pool = pool
        self._proxies = proxies
        self._limiter = limiter or ProfileLimiter()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.sent = 0
        self.failed = 0
        self.by_profile = {"fast": 0, "slow": 0}

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> dict:
        by_prof = split_by_profile(self._pool)
        while not self._stop.is_set():
            target = self._strategy.next()
            if target is None:
                break
            self._run_one(target, by_prof)
            if self._strategy.done():
                break
        return self.report()

    def _run_one(self, target: Target, by_prof: dict[str, list[Endpoint]]) -> None:
        for _ in range(target.rounds):
            if self._stop.is_set():
                return
            for ep in by_prof.get(target.profile, []):
                if self._stop.is_set():
                    return
                self._limiter.wait(target.profile)
                raw = ep.body.format(phone=target.phone)
                hdrs = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)", **ep.headers}
                
                if ep.body_type == "json":
                    hdrs["Content-Type"] = "application/json"
                    data = raw.encode()
                elif ep.body_type == "form":
                    hdrs["Content-Type"] = "application/x-www-form-urlencoded"
                    data = raw.encode()
                else:
                    data = dict(urllib.parse.parse_qsl(raw))
                    
                proxy = None
                if self._proxies:
                    p = random.choice(self._proxies)
                    proxy = {"http": p, "https": p}
                    
                kind = "fail"
                try:
                    r = requests.request(ep.method, ep.url, data=data, headers=hdrs,
                                         timeout=5, proxies=proxy)
                    kind = "ok" if 200 <= r.status_code < 300 else "fail"
                except requests.RequestException:
                    pass
                    
                with self._lock:
                    if kind == "ok":
                        self.sent += 1
                        self.by_profile[target.profile] += 1
                    else:
                        self.failed += 1

    def report(self) -> dict:
        return {"sent": self.sent, "failed": self.failed,
                "by_profile": dict(self.by_profile),
                "rps": self._limiter.snapshot()}
