"""مساعد JSON مشترك — shared JSON-safety helper (DataPoint/dataclass -> dict).

Extracted from api.py so both the API layer and the background-job layer
(silk_jobs.py, which caches results via silk_cache) can convert an analyze()
result into a JSON-safe structure without importing FastAPI. Pure stdlib.
"""
from __future__ import annotations

import dataclasses


def to_jsonable(obj: object) -> object:
    """حوّل DataPoint وغيره إلى JSON — make DataPoints/dataclasses JSON-safe."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    return obj
