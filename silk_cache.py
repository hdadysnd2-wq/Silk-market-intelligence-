"""ذاكرة تخزين مؤقت للطلبات — tiny on-disk JSON cache for GET responses.

Pure-stdlib import (json+hashlib+os). `requests` is imported lazily inside
cached_get so `import silk_cache` works offline / without the library.
Founding principle: on any network error return None — never crash, never
fabricate. Cache files live under data/cache/ (gitignored).
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


def _key(url: str, params: dict | None) -> str:
    """مفتاح التخزين — sha1 of url + sorted params."""
    raw = url + "?" + urlencode(sorted((params or {}).items()))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def cached_get(
    url: str, params: dict | None = None, ttl_seconds: int = 86400
) -> dict | list | None:
    """جلب مع تخزين مؤقت — GET JSON, serving fresh cache or fetching live.

    Returns parsed JSON (dict|list), or None on any network/parse error.
    """
    path = os.path.join(_CACHE_DIR, _key(url, params) + ".json")
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < ttl_seconds:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError) as exc:  # corrupt cache → refetch
            log.warning("cache read failed (%s); refetching", exc)

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

    try:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except OSError as exc:  # caching is best-effort
        log.warning("cache write failed (%s)", exc)
    return data
