"""Small in-memory sliding-window rate limiter (per process). Use Redis for multi-instance deployments."""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int, scope: str):
        self.limit = limit
        self.window = window_seconds
        self.scope = scope
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                retry = int(self.window - (now - hits[0])) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many {self.scope} requests. Try again in {retry}s.",
                    headers={"Retry-After": str(retry)},
                )
            hits.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


login_limiter = RateLimiter(limit=10, window_seconds=60, scope="login")
register_limiter = RateLimiter(limit=5, window_seconds=60, scope="registration")
analysis_limiter = RateLimiter(limit=10, window_seconds=60, scope="analysis")
collection_limiter = RateLimiter(limit=3, window_seconds=60, scope="collection")

ALL_LIMITERS = [login_limiter, register_limiter, analysis_limiter, collection_limiter]
