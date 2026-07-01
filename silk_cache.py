"""ذاكرة تخزين مؤقت لسِلك — Silk cache layer (Redis in prod, disk offline/dev).

Pure-stdlib import (json+hashlib+os). `requests`/`redis` are imported lazily so
`import silk_cache` works offline / without either library. Founding principle:
on any cache/network error, degrade — never crash, never fabricate.

Two independent caches share this module:
  - cached_get()              — raw HTTP GET JSON cache used by the data layer.
  - get/set_cached_analysis() — a dedicated 30-day cache for full analyze()
    results (product+markets+year+flags), so a repeat request skips the
    agents AND the Claude call entirely (this is the platform's primary cost
    control, not an optional nicety).

Both use REDIS_URL (Railway Redis) when set; otherwise fall back to on-disk
JSON files under data/cache/ (gitignored) — identical behavior to before V3
when no Redis is configured (local dev / CI / offline).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from urllib.parse import urlencode

log = logging.getLogger(__name__)

_CACHE_DIR = os.path.join("data", "cache")
_TIMEOUT = 30
_ANALYSIS_TTL_SECONDS = 30 * 24 * 3600  # 30 يوماً — mandatory per the cost-control spec


def _redis_client():
    """عميل Redis إن توفّر — lazy Redis client from REDIS_URL, else None."""
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis  # lazy: optional dep, only needed when REDIS_URL is set
        client = redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 — cache is best-effort, never break callers
        log.warning("Redis unavailable (%s); falling back to disk cache", exc)
        return None


def _key(url: str, params: dict | None) -> str:
    """مفتاح التخزين — sha1 of url + sorted params."""
    raw = url + "?" + urlencode(sorted((params or {}).items()))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _disk_read(cache_key: str, ttl_seconds: int) -> object:
    path = os.path.join(_CACHE_DIR, cache_key + ".json")
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl_seconds:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError) as exc:  # corrupt cache → treat as miss
            log.warning("cache read failed (%s); refetching", exc)
    return None


def _disk_write(cache_key: str, data: object) -> None:
    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(os.path.join(_CACHE_DIR, cache_key + ".json"), "w",
                 encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError as exc:  # caching is best-effort
        log.warning("cache write failed (%s)", exc)


def cached_get(
    url: str, params: dict | None = None, ttl_seconds: int = 86400
) -> dict | list | None:
    """جلب مع تخزين مؤقت — GET JSON, serving fresh cache (Redis or disk) or fetching live.

    Returns parsed JSON (dict|list), or None on any network/parse error.
    """
    cache_key = "http:" + _key(url, params)
    client = _redis_client()
    if client is not None:
        try:
            raw = client.get(cache_key)
            if raw is not None:
                return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis read failed (%s); treating as cache miss", exc)
    else:
        cached = _disk_read(cache_key, ttl_seconds)
        if cached is not None:
            return cached

    try:
        import requests  # lazy: keep module importable offline
    except ImportError:
        log.warning("requests not installed — cannot fetch %s", url)
        return None

    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # network/HTTP/JSON — never crash, never fabricate
        log.warning("cached_get failed for %s: %s", url, exc)
        return None

    if client is not None:
        try:
            client.set(cache_key, json.dumps(data), ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis write failed (%s); not cached", exc)
    else:
        _disk_write(cache_key, data)
    return data


def _analysis_cache_key(key: dict) -> str:
    """مفتاح ثابت لتركيبة التحليل — stable, order-independent key for one
    (product, markets, year, flags) request combination."""
    raw = json.dumps(key, sort_keys=True, default=str)
    return "analysis:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def get_cached_analysis(key: dict) -> dict | None:
    """استرجع نتيجة تحليل مخزّنة — a previously cached, already-JSON-safe
    analyze() result for this exact request combination, or None on a miss."""
    cache_key = _analysis_cache_key(key)
    client = _redis_client()
    if client is not None:
        try:
            raw = client.get(cache_key)
            return json.loads(raw) if raw is not None else None
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis read failed (%s); treating as cache miss", exc)
            return None
    return _disk_read(cache_key, _ANALYSIS_TTL_SECONDS)


def set_cached_analysis(key: dict, result: dict) -> None:
    """خزّن نتيجة تحليل ٣٠ يوماً — cache an already-JSON-safe analyze() result.

    `result` must already be JSON-safe (no DataPoint/dataclass instances) —
    callers convert first (see silk_jsonutil.to_jsonable).
    """
    cache_key = _analysis_cache_key(key)
    client = _redis_client()
    if client is not None:
        try:
            client.set(cache_key, json.dumps(result), ex=_ANALYSIS_TTL_SECONDS)
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("Redis write failed (%s); falling back to disk", exc)
    _disk_write(cache_key, result)
