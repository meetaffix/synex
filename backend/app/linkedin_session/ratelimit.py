"""In-process sliding-window limiter for the unauthenticated reconnect routes.
Use a shared edge limit when running more than one API instance."""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float = 60) -> None:
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 10_000:
                self._hits.clear()
            hits = self._hits[key]
            while hits and hits[0] < now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


public_limiter = SlidingWindowLimiter(limit=120)
connect_limiter = SlidingWindowLimiter(limit=10)
proxy_test_limiter = SlidingWindowLimiter(limit=10)


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def limit_public(request: Request) -> None:
    if not public_limiter.allow(_client(request)):
        raise HTTPException(429, "Too many requests. Try again in a minute.")


def limit_connect(request: Request) -> None:
    if not connect_limiter.allow(_client(request)):
        raise HTTPException(429, "Too many connection attempts. Try again in a minute.")
