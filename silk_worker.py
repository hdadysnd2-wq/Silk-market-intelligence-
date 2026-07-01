"""عامل سِلك الخلفي — Silk RQ worker entrypoint (Procfile's "worker:" process).

Consumes the "silk-analysis" queue populated by silk_jobs.enqueue_analysis().
Requires REDIS_URL; without it there is nothing to consume — local dev doesn't
need this process at all, since silk_jobs runs analyses synchronously when no
Redis is configured.
"""
from __future__ import annotations

import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def main() -> None:
    """شغّل العامل — block, consuming jobs until stopped."""
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        print("REDIS_URL not set — nothing to consume; silk_jobs runs analyses "
              "synchronously without a worker process.")
        sys.exit(0)
    try:
        import redis
        from rq import Queue, Worker
    except ImportError as e:
        print(f"redis/rq not installed — run: pip install redis rq ({e})")
        sys.exit(1)

    conn = redis.from_url(url)
    worker = Worker([Queue("silk-analysis", connection=conn)], connection=conn)
    worker.work()


if __name__ == "__main__":
    main()
