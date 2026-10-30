import time
from collections import deque


class MinuteLimiter:
    """IP başına kayan pencereli dakikalık limit (bellekte).

    Tek worker çalıştığımız için bellek yeterli; restart'ta sıfırlanması da
    dakikalık limit için sorun değil. Günlük limitler SQLite'tan sayılır.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            return False
        hits.append(now)
        self._prune(now)
        return True

    def _prune(self, now: float) -> None:
        # Sözlüğün sınırsız büyümesini engelle: penceresi dolmuş anahtarları at.
        if len(self._hits) < 1000:
            return
        stale = [k for k, h in self._hits.items() if not h or now - h[-1] >= self.window]
        for k in stale:
            del self._hits[k]
