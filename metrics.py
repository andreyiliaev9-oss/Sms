# metrics.py — кольцевой буфер метрик
# Python 3.10+, только stdlib
import threading
import time
from collections import deque


class Metrics:
    def __init__(self, window_sec: int = 60):
        self._window = window_sec
        self._lock = threading.Lock()
        self._buckets: dict[str, deque] = {}
        self._started_at = time.time()
        self._totals = {"sent": 0, "failed": 0, "flood": 0}
        self._by_profile = {"fast": 0, "slow": 0}

    def tick(self, profile: str, sent: int = 0, failed: int = 0, flood: int = 0) -> None:
        now = time.time()
        with self._lock:
            q = self._buckets.setdefault(profile, deque())
            q.append((now, sent, failed))
            cutoff = now - self._window
            while q and q[0][0] < cutoff:
                q.popleft()
            self._totals["sent"] += sent
            self._totals["failed"] += failed
            self._totals["flood"] += flood
            self._by_profile[profile] = self._by_profile.get(profile, 0) + sent
            
        if sent:
            from prom2 import SENT
            SENT.labels(profile).inc(sent)
        if failed:
            from prom2 import FAILED
            FAILED.labels(profile).inc(failed)
        if flood:
            from prom2 import FLOOD
            FLOOD.inc(flood)

    def snapshot(self) -> dict:
        now = time.time()
        cutoff = now - self._window
        with self._lock:
            per_profile = {}
            for prof, q in self._buckets.items():
                while q and q[0][0] < cutoff:
                    q.popleft()
                n = sum(s for _, s, _ in q)
                per_profile[prof] = round(n / self._window, 2)
            return {
                "uptime": round(now - self._started_at, 1),
                "totals": dict(self._totals),
                "by_profile": dict(self._by_profile),
                "rps_by_profile": per_profile,
                "window": self._window,
            }


METRICS = Metrics(window_sec=60)
