"""طبقة قاعدة بيانات سِلك (V3) — users/auth/jobs backing store.

Real backing store for magic-link auth (users, one-time links, sessions) and
background-job status/usage tracking. Uses DATABASE_URL (Postgres in
production, e.g. Railway's Postgres template) when set; falls back to a local
SQLite file otherwise so dev/CI/tests work with zero external services — same
graceful-degrade principle as the rest of Silk. SQLAlchemy Core only (no ORM):
plain tables + explicit statements, portable across both dialects without
hand-writing two SQL flavors.

Scope note: this is a NEW store for V3's auth/jobs concerns. The existing
`silk_storage.py` (analyze() persistence, `persist=True`) is untouched in this
phase — it keeps using its own SQLite file exactly as before. Merging the two
(per-user analysis history in the same Postgres) is a follow-up once auth is
wired through the whole request path, not done silently here.
"""
from __future__ import annotations

import datetime
import logging
import os
import uuid

log = logging.getLogger(__name__)

_DEFAULT_SQLITE_URL = "sqlite:///data/silk_app.db"


def _database_url() -> str:
    """رابط قاعدة البيانات — DATABASE_URL (Postgres) or a local SQLite fallback."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        return _DEFAULT_SQLITE_URL
    # Railway/Heroku-style URLs use postgres:// ; SQLAlchemy 2.x needs postgresql://
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def new_id() -> str:
    """معرّف فريد — a short random id (job ids, etc.), stdlib-only."""
    return uuid.uuid4().hex


def _now() -> "datetime.datetime":
    return datetime.datetime.utcnow()


_engine = None
_metadata = None
_tables: dict = {}


def _build_schema():
    """ابنِ الجداول — define the schema once SQLAlchemy is known to be importable."""
    from sqlalchemy import (
        MetaData, Table, Column, Integer, String, Text, DateTime, Boolean,
    )
    metadata = MetaData()
    users = Table(
        "users", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("email", String(255), unique=True, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    magic_links = Table(
        "magic_links", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("email", String(255), nullable=False),
        Column("token_hash", String(128), unique=True, nullable=False),
        Column("expires_at", DateTime, nullable=False),
        Column("used", Boolean, nullable=False, default=False),
        Column("created_at", DateTime, nullable=False),
    )
    sessions = Table(
        "sessions", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("token_hash", String(128), unique=True, nullable=False),
        Column("user_id", Integer, nullable=False),
        Column("expires_at", DateTime, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    jobs = Table(
        "jobs", metadata,
        Column("id", String(64), primary_key=True),
        Column("user_id", Integer, nullable=True),
        Column("status", String(20), nullable=False),  # queued|running|finished|failed
        Column("result_json", Text, nullable=True),
        Column("error", Text, nullable=True),
        Column("created_at", DateTime, nullable=False),
        Column("updated_at", DateTime, nullable=False),
    )
    # ذاكرة تراكمية (RAG) — cumulative report memory. Embedding is stored as a
    # portable JSON text array so it works on both Postgres and SQLite; a native
    # pgvector column + ANN index is the production optimization (see silk_vectors).
    market_vectors = Table(
        "market_vectors", metadata,
        Column("id", Integer, primary_key=True, autoincrement=True),
        Column("product", String(255), nullable=True),
        Column("hs_code", String(16), nullable=True),
        Column("market", String(128), nullable=True),
        Column("year", Integer, nullable=True),
        Column("summary", Text, nullable=True),
        Column("embedding", Text, nullable=False),   # JSON array of floats
        Column("dim", Integer, nullable=False),
        Column("created_at", DateTime, nullable=False),
    )
    return metadata, {"users": users, "magic_links": magic_links,
                      "sessions": sessions, "jobs": jobs,
                      "market_vectors": market_vectors}


def get_engine():
    """المحرك المشترك — a process-wide lazy SQLAlchemy engine (Postgres or SQLite)."""
    global _engine, _metadata, _tables
    if _engine is None:
        from sqlalchemy import create_engine  # lazy: keep module importable without it
        url = _database_url()
        if url.startswith("sqlite"):
            path = url.replace("sqlite:///", "", 1)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        _metadata, _tables = _build_schema()
        _engine = create_engine(url, future=True)
        _metadata.create_all(_engine)
    return _engine


def _t(name: str):
    get_engine()  # ensures _tables is populated
    return _tables[name]


# ── users ──────────────────────────────────────────────────────────────────

def get_or_create_user(email: str) -> int:
    """أحضر المستخدم أو أنشئه — idempotent get-or-create by email, returns user id."""
    from sqlalchemy import select, insert
    email = email.strip().lower()
    engine = get_engine()
    users = _t("users")
    with engine.begin() as conn:
        row = conn.execute(select(users.c.id).where(users.c.email == email)).fetchone()
        if row:
            return int(row[0])
        result = conn.execute(insert(users).values(email=email, created_at=_now()))
        return int(result.inserted_primary_key[0])


# ── magic links ────────────────────────────────────────────────────────────

def store_magic_link(email: str, token_hash: str, ttl_minutes: int = 15) -> None:
    """خزّن رابطاً سحرياً — store a one-time login token hash (never the raw token)."""
    from sqlalchemy import insert
    engine = get_engine()
    links = _t("magic_links")
    expires_at = _now() + datetime.timedelta(minutes=ttl_minutes)
    with engine.begin() as conn:
        conn.execute(insert(links).values(
            email=email.strip().lower(), token_hash=token_hash,
            expires_at=expires_at, used=False, created_at=_now()))


def consume_magic_link(token_hash: str) -> str | None:
    """استهلك الرابط مرة واحدة — validate+expire-check+single-use; returns email or None."""
    from sqlalchemy import select, update
    engine = get_engine()
    links = _t("magic_links")
    with engine.begin() as conn:
        row = conn.execute(select(links.c.id, links.c.email, links.c.expires_at,
                                  links.c.used)
                           .where(links.c.token_hash == token_hash)).fetchone()
        if row is None or row.used or row.expires_at < _now():
            return None
        conn.execute(update(links).where(links.c.id == row.id).values(used=True))
        return row.email


# ── sessions ───────────────────────────────────────────────────────────────

def store_session(user_id: int, token_hash: str, ttl_days: int = 30) -> None:
    """خزّن جلسة — store a session token hash for a user."""
    from sqlalchemy import insert
    engine = get_engine()
    sess = _t("sessions")
    expires_at = _now() + datetime.timedelta(days=ttl_days)
    with engine.begin() as conn:
        conn.execute(insert(sess).values(
            token_hash=token_hash, user_id=user_id, expires_at=expires_at,
            created_at=_now()))


def session_user_id(token_hash: str) -> int | None:
    """تحقق من الجلسة — user id for a valid, unexpired session token, else None."""
    from sqlalchemy import select
    engine = get_engine()
    sess = _t("sessions")
    with engine.begin() as conn:
        row = conn.execute(select(sess.c.user_id, sess.c.expires_at)
                           .where(sess.c.token_hash == token_hash)).fetchone()
        if row is None or row.expires_at < _now():
            return None
        return int(row.user_id)


# ── jobs (also doubles as the usage ledger for /usage) ─────────────────────

def create_job(user_id: int | None) -> str:
    """أنشئ مهمة — create a queued job row, returns its id."""
    from sqlalchemy import insert
    engine = get_engine()
    jobs = _t("jobs")
    job_id = new_id()
    now = _now()
    with engine.begin() as conn:
        conn.execute(insert(jobs).values(
            id=job_id, user_id=user_id, status="queued",
            result_json=None, error=None, created_at=now, updated_at=now))
    return job_id


def update_job(job_id: str, status: str, result_json: str | None = None,
              error: str | None = None) -> None:
    """حدّث حالة مهمة — update a job's status/result/error."""
    from sqlalchemy import update
    engine = get_engine()
    jobs = _t("jobs")
    with engine.begin() as conn:
        conn.execute(update(jobs).where(jobs.c.id == job_id).values(
            status=status, result_json=result_json, error=error,
            updated_at=_now()))


def get_job(job_id: str) -> dict | None:
    """أحضر مهمة — fetch a job row as a dict, or None if unknown."""
    from sqlalchemy import select
    engine = get_engine()
    jobs = _t("jobs")
    with engine.begin() as conn:
        row = conn.execute(select(jobs).where(jobs.c.id == job_id)).mappings().fetchone()
    return dict(row) if row else None


def count_jobs_this_month(user_id: int) -> int:
    """عدّاد الاستخدام الشهري — job count for a user in the current calendar month."""
    from sqlalchemy import select, func
    engine = get_engine()
    jobs = _t("jobs")
    start = _now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    with engine.begin() as conn:
        row = conn.execute(
            select(func.count()).select_from(jobs)
            .where(jobs.c.user_id == user_id).where(jobs.c.created_at >= start)
        ).fetchone()
    return int(row[0]) if row else 0


# ── cumulative memory vectors (RAG) ────────────────────────────────────────

def try_enable_pgvector() -> bool:
    """فعّل pgvector إن أمكن — best-effort CREATE EXTENSION vector on Postgres.

    Returns True if the extension is available afterward. On SQLite or when the
    DB role can't create extensions, returns False and the layer falls back to a
    portable JSON column + Python cosine (see silk_vectors). Never raises.
    """
    engine = get_engine()
    if engine.dialect.name != "postgresql":
        return False
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        return True
    except Exception as e:  # noqa: BLE001 — extension may be unavailable/forbidden
        log.warning("pgvector unavailable (%s); using JSON+cosine fallback", e)
        return False


def store_market_vector(product, hs_code, market, year, summary,
                        embedding: list, ) -> int:
    """خزّن ناقل تقرير — persist a report embedding for later similarity search."""
    import json as _json
    from sqlalchemy import insert
    engine = get_engine()
    mv = _t("market_vectors")
    with engine.begin() as conn:
        cur = conn.execute(insert(mv).values(
            product=product, hs_code=hs_code, market=market, year=year,
            summary=summary, embedding=_json.dumps(list(embedding)),
            dim=len(embedding), created_at=_now()))
        return int(cur.inserted_primary_key[0])


def list_market_vectors(limit: int = 500) -> list[dict]:
    """اسرد نواقل التقارير — recent stored vectors (newest first) as dicts."""
    import json as _json
    from sqlalchemy import select
    engine = get_engine()
    mv = _t("market_vectors")
    with engine.begin() as conn:
        rows = conn.execute(select(mv).order_by(mv.c.id.desc()).limit(limit)
                            ).mappings().fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["embedding"] = _json.loads(d["embedding"])
        except Exception:  # noqa: BLE001 — skip a corrupt row rather than crash
            continue
        out.append(d)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk DB layer — demo (SQLite fallback without DATABASE_URL)")
    uid = get_or_create_user("demo@example.com")
    print("  user id:", uid)
    jid = create_job(uid)
    update_job(jid, "finished", result_json='{"ok": true}')
    print("  job:", get_job(jid))
    print("  jobs this month:", count_jobs_this_month(uid))
