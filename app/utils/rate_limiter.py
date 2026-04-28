import time
from collections import defaultdict

from fastapi import Request, HTTPException

from app.core.config import settings

_EVICT_INTERVAL = 300  # evict stale keys every 5 minutes


class InMemoryRateLimiter:
    def __init__(self, requests_per_minute: int, requests_per_hour: int):
        self.rpm = requests_per_minute
        self.rph = requests_per_hour
        self._minute: dict[str, list] = defaultdict(list)
        self._hour: dict[str, list] = defaultdict(list)
        self._last_evict: float = time.time()

    def _clean(self, records: list, window: int) -> list:
        cutoff = time.time() - window
        return [t for t in records if t > cutoff]

    def _evict_stale_keys(self) -> None:
        """Remove keys that have had no activity within the hour window to prevent unbounded growth."""
        now = time.time()
        if now - self._last_evict < _EVICT_INTERVAL:
            return
        cutoff = now - 3600
        stale = [k for k, ts in self._hour.items() if not ts or ts[-1] < cutoff]
        for k in stale:
            self._minute.pop(k, None)
            self._hour.pop(k, None)
        self._last_evict = now

    def check(self, key: str) -> None:
        now = time.time()
        self._evict_stale_keys()
        self._minute[key] = self._clean(self._minute[key], 60)
        self._hour[key] = self._clean(self._hour[key], 3600)

        if len(self._minute[key]) >= self.rpm:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in 60 seconds.")
        if len(self._hour[key]) >= self.rph:
            raise HTTPException(status_code=429, detail="Hourly rate limit exceeded.")

        self._minute[key].append(now)
        self._hour[key].append(now)


rate_limiter = InMemoryRateLimiter(
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
)


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
