"""تحديد معدّل الاستخدام لسِلك — Silk rate limiting (Redis, in-memory fallback).

Fixed-window counters per user (or per IP for unauthenticated calls) guarding
the paid /analyze endpoint — mandatory once auth exists (an unmetered endpoint
in front of Claude + paid tool calls is the platform's biggest cost risk).
Redis-backed (REDIS_URL) so limits are shared across web+worker processes in
production; falls back to an in-memory counter (per-process only — fine for
single-process local dev/tests, NOT a substitute for Redis across replicas).
"""
from __future__ import annotations

import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_PER_HOUR = int(os.environ.get("RATE_LIMIT_PER_HOUR", "20"))
_PER_DAY = int(os.environ.get("RATE_LIMIT_PER_DAY", "100"))

_mem_lock = threading.Lock()
_mem_counters: dict[str, tuple[int, int]] = {}  # key -> (count, window_index)


class RateLimitExceeded(Exception):
    """تجاوز الحد — raised when an identity exceeds its window cap."""

    def __init__(self, scope: str, limit: int, retry_after_seconds: int) -> None:
        self.scope = scope
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit exceeded ({scope}): max {limit}/window")


def _redis_client():
    """عميل Redis إن توفّر — lazy Redis client from REDIS_URL, else None."""
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis  # lazy: optional dep
        client = redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 — limiter must never crash the request
        log.warning("Redis unavailable for rate limiting (%s); using in-memory", exc)
        return None


def _increment(identity: str, scope: str, window_seconds: int) -> int:
    """زد العدّاد — increment and return the count for this identity+window."""
    window_index = int(time.time() // window_seconds)
    key = f"rl:{scope}:{identity}:{window_index}"
    client = _redis_client()
    if client is not None:
        try:
            count = client.incr(key)
            if count == 1:
                client.expire(key, window_seconds)
            return int(count)
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis rate-limit incr failed (%s); using in-memory", exc)
    with _mem_lock:
        count, stored_window = _mem_counters.get(key, (0, window_index))
        if stored_window != window_index:
            count = 0
        count += 1
        _mem_counters[key] = (count, window_index)
        return count


def enforce_analysis_limits(identity: str) -> None:
    """طبّق حدود التحليل — enforce both the hourly and daily caps for `identity`.

    `identity` is typically the user id (authenticated) or client IP (not yet
    authenticated, e.g. the auth endpoints themselves). Raises RateLimitExceeded
    on the first breached window; increments both windows regardless so a
    request never partially counts.
    """
    hour_count = _increment(identity, "hour", 3600)
    day_count = _increment(identity, "day", 86400)
    if hour_count > _PER_HOUR:
        raise RateLimitExceeded("hour", _PER_HOUR, retry_after_seconds=3600)
    if day_count > _PER_DAY:
        raise RateLimitExceeded("day", _PER_DAY, retry_after_seconds=86400)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(f"Silk rate limiter — caps: {_PER_HOUR}/hour, {_PER_DAY}/day "
          "(in-memory demo, no REDIS_URL)")
    ok = 0
    try:
        for i in range(_PER_HOUR + 2):
            enforce_analysis_limits("demo-user")
            ok += 1
    except RateLimitExceeded as e:
        print(f"  allowed {ok} requests, then blocked: {e}")
