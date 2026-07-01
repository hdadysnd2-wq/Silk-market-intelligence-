"""مهام سِلك الخلفية — Silk background jobs (RQ + Redis; sync fallback offline).

Wraps silk_engine.analyze() so a slow (multi-agent, multi-Claude-call) analysis
never blocks an HTTP request: enqueue_analysis() returns a job_id immediately;
the caller polls job_status(job_id). Uses RQ (Redis Queue) when REDIS_URL is
set — the production path, with a separate worker process consuming the queue
(silk_worker.py, run via the Procfile's "worker:" line). Without REDIS_URL
(dev/CI/offline) the job runs SYNCHRONOUSLY inline and returns an
already-finished job_id — same public contract, no Redis required locally.

The 30-day analysis-result cache (silk_cache) is checked BEFORE any agent or
Claude call: a cache hit short-circuits to a "finished" job immediately,
matching the platform's cost-control requirement (no repeat agent/Claude
spend for an identical product+markets+year+flags request).
"""
from __future__ import annotations

import json
import logging
import os

import silk_cache
import silk_db
from silk_jsonutil import to_jsonable

log = logging.getLogger(__name__)

_QUEUE_NAME = "silk-analysis"


def _cache_key(request: dict) -> dict:
    """مفتاح كاش مستقر — the subset of the request that defines cache identity."""
    return {k: request.get(k) for k in (
        "product", "year", "with_trends", "with_tariffs", "with_faostat",
        "with_maps", "with_websearch", "with_localprice", "own_price",
        "with_market_size", "with_demographics", "with_competition",
        "with_compliance", "with_culture",
        "with_volza", "with_explee", "with_ai", "with_synthesis",
    )}


def _run_analysis(request: dict) -> dict:
    """نفّذ التحليل فعلياً — call the engine, return a JSON-safe result dict."""
    import silk_engine
    result = silk_engine.analyze(
        request.get("product"), countries=request.get("countries"),
        year=request.get("year"),
        with_trends=bool(request.get("with_trends")),
        with_tariffs=bool(request.get("with_tariffs")),
        with_faostat=bool(request.get("with_faostat")),
        with_maps=bool(request.get("with_maps")),
        with_websearch=bool(request.get("with_websearch")),
        with_localprice=bool(request.get("with_localprice")),
        own_price=request.get("own_price"),
        with_market_size=bool(request.get("with_market_size")),
        with_demographics=bool(request.get("with_demographics")),
        with_competition=bool(request.get("with_competition")),
        with_compliance=bool(request.get("with_compliance")),
        with_culture=bool(request.get("with_culture")),
        with_volza=bool(request.get("with_volza")),
        with_explee=bool(request.get("with_explee")),
        with_ai=bool(request.get("with_ai")),
        with_synthesis=bool(request.get("with_synthesis")),
        persist=bool(request.get("persist")),
    )
    return to_jsonable(result)


def _execute_job(job_id: str, request: dict) -> None:
    """نفّذ مهمة وخزّن نتيجتها — run one job to completion, updating its row.

    Shared by both the RQ worker path and the synchronous fallback so the
    cache-write/error-handling behavior is identical either way.
    """
    silk_db.update_job(job_id, "running")
    try:
        result = _run_analysis(request)
        silk_cache.set_cached_analysis(_cache_key(request), result)
        _remember(result)  # RAG memory (best-effort; no-op without embeddings key)
        silk_db.update_job(job_id, "finished", result_json=json.dumps(result))
    except Exception as e:  # noqa: BLE001 — a job failure must not crash the worker
        log.warning("analysis job %s failed: %s", job_id, e)
        silk_db.update_job(job_id, "failed", error=str(e))


def _remember(result: dict) -> None:
    """خزّن التقرير في الذاكرة التراكمية — best-effort RAG store; never crashes."""
    try:
        import silk_vectors
        silk_vectors.remember_report(result)
    except Exception as e:  # noqa: BLE001 — memory is optional context
        log.warning("RAG remember skipped: %s", e)


def _rq_queue():
    """طابور RQ إن توفّر Redis — an RQ Queue, or None to use the sync fallback."""
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis
        from rq import Queue
        conn = redis.from_url(url)
        conn.ping()
        return Queue(_QUEUE_NAME, connection=conn)
    except Exception as exc:  # noqa: BLE001 — queueing is best-effort in dev
        log.warning("RQ/Redis unavailable (%s); running jobs synchronously", exc)
        return None


def enqueue_analysis(request: dict, user_id: int | None) -> dict:
    """أرسل تحليلاً للتنفيذ — enqueue (or run inline) one analysis request.

    Returns {"job_id", "status", "cached": bool} immediately. A cache hit
    short-circuits to a "finished" job with no agent/Claude calls at all.
    """
    cached = silk_cache.get_cached_analysis(_cache_key(request))
    job_id = silk_db.create_job(user_id)
    if cached is not None:
        silk_db.update_job(job_id, "finished", result_json=json.dumps(cached))
        return {"job_id": job_id, "status": "finished", "cached": True}

    queue = _rq_queue()
    if queue is not None:
        queue.enqueue(_execute_job, job_id, request, job_timeout=180)
        return {"job_id": job_id, "status": "queued", "cached": False}

    # لا Redis: نفّذ فوراً بالتزامن — no Redis: run inline, same public contract.
    _execute_job(job_id, request)
    status = job_status(job_id)
    return {"job_id": job_id, "status": status["status"] if status else "failed",
           "cached": False}


def job_status(job_id: str) -> dict | None:
    """حالة مهمة — job status dict, or None if unknown. result is parsed JSON."""
    row = silk_db.get_job(job_id)
    if row is None:
        return None
    result = json.loads(row["result_json"]) if row.get("result_json") else None
    return {"job_id": row["id"], "status": row["status"], "result": result,
           "error": row.get("error")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk jobs — demo (no REDIS_URL -> synchronous fallback)")
    demo_request = {"product": "تمور", "year": 2022,
                    "countries": [{"iso3": "ARE", "m49": "784"}]}  # keep the demo fast
    out = enqueue_analysis(demo_request, user_id=None)
    print("  enqueue:", out)
    print("  status:", job_status(out["job_id"]))
