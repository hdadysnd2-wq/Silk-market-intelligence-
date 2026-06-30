"""تخزين التحليلات لسِلك — Silk analysis persistence (SQLite, stdlib only).

Persists engine.analyze() results to a local SQLite file so analyses can be
listed and re-opened later. Pure stdlib (sqlite3 + json), fully offline. The
.db file is gitignored; nothing here ever touches the network or fabricates.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import sqlite3

log = logging.getLogger(__name__)

_DEFAULT_PATH = "data/silk.db"


def _connect(path: str) -> sqlite3.Connection:
    """افتح اتصالًا وأنشئ المجلد — open a connection, making parent dir if needed."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str = _DEFAULT_PATH) -> None:
    """أنشئ الجداول (idempotent) — create tables if absent. Safe to call repeatedly."""
    with _connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS analyses ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "product TEXT, hs_code TEXT, year INTEGER, created_at TEXT, "
            "preliminary INTEGER, json_blob TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS market_scores ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "analysis_id INTEGER, country TEXT, iso3 TEXT, "
            "total_score REAL, confidence REAL, "
            "FOREIGN KEY(analysis_id) REFERENCES analyses(id))"
        )


def save_analysis(result: dict, path: str = _DEFAULT_PATH) -> int:
    """خزّن نتيجة تحليل وأعد المعرّف — store an analyze() result, return its row id.

    The full dict is json.dumps'd into json_blob; per-market scores are also
    flattened into market_scores for quick listing/querying.
    """
    init_db(path)
    blob = json.dumps(result, ensure_ascii=False, default=_json_default)
    with _connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO analyses "
            "(product, hs_code, year, created_at, preliminary, json_blob) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (result.get("product"), result.get("hs_code"), result.get("year"),
             datetime.datetime.now().isoformat(timespec="seconds"),
             1 if result.get("preliminary") else 0, blob),
        )
        analysis_id = int(cur.lastrowid)
        for row in result.get("markets", []):
            conn.execute(
                "INSERT INTO market_scores "
                "(analysis_id, country, iso3, total_score, confidence) "
                "VALUES (?, ?, ?, ?, ?)",
                (analysis_id, row.get("country"), row.get("iso3"),
                 row.get("total_score"), row.get("confidence")),
            )
    log.info("saved analysis id=%s product=%s", analysis_id, result.get("product"))
    return analysis_id


def list_analyses(path: str = _DEFAULT_PATH) -> list[dict]:
    """اسرد التحليلات المحفوظة — list saved analyses (newest first), metadata only."""
    if not os.path.exists(path):
        return []
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT id, product, hs_code, year, created_at, preliminary "
            "FROM analyses ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_analysis(analysis_id: int, path: str = _DEFAULT_PATH) -> dict | None:
    """أعد تحليلًا كاملًا — fetch one full analysis dict, or None if absent."""
    if not os.path.exists(path):
        return None
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT json_blob FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if row is None:
        return None
    return json.loads(row["json_blob"])


def _json_default(obj: object) -> object:
    """تسلسل DataPoint وغيره — JSON fallback (DataPoint and dataclasses -> dict)."""
    import dataclasses
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    return str(obj)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import tempfile
    demo_path = os.path.join(tempfile.mkdtemp(), "silk_demo.db")
    fake = {  # هيكل فقط، ليست بيانات حقيقية — STRUCTURE only, not real data.
        "product": "demo-product", "hs_code": "000000", "year": 2022,
        "preliminary": True,
        "markets": [{"country": "Demo-Land", "iso3": "XXX",
                     "total_score": 0.0, "confidence": 0.0}],
    }
    aid = save_analysis(fake, demo_path)
    print("saved id:", aid)
    print("list:", list_analyses(demo_path))
    print("get product:", get_analysis(aid, demo_path)["product"])
