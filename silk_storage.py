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


def _db_path() -> str:
    """مسار قاعدة التحليلات وقت النداء — resolve at call time (env or default).

    `SILK_DB` يوجّه الملف لقرص دائم في النشر (Railway volume على /data مثلًا)
    دون حجب ملفات data/ المرجعية؛ يليه اشتقاق من `SILK_DATA_DIR` (متغير واحد
    يوجّه كل المخازن للقرص). Env override for persistent-disk deploys;
    SILK_DATA_DIR derives the path when SILK_DB itself is unset.
    """
    explicit = os.environ.get("SILK_DB", "").strip()
    if explicit:
        return explicit
    base = os.environ.get("SILK_DATA_DIR", "").strip()
    if base:
        return os.path.join(base, "silk.db")
    return _DEFAULT_PATH


def _connect(path: str) -> sqlite3.Connection:
    """افتح اتصالًا وأنشئ المجلد — open a connection, making parent dir if needed."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path: str | None = None) -> None:
    """أنشئ الجداول (idempotent) — create tables if absent. Safe to call repeatedly.

    الموجة ١: عمودا `outcome` + `outcome_date` (سجل النتائج الفعلية التراكمي).
    قواعد قديمة بلا العمودين تُرحَّل بـ ALTER TABLE آمن لا يمسّ أي بيانات قائمة.

    حادثة نقطة تفتيش/استئناف (P0): أعمدة `status`/`kind`/`request_json`/
    `updated_at` على `analyses` + جدول `research_missions` جديد — كل بعثة
    من الاثنتي عشرة تُخزَّن فور اكتمالها (لا بعد التشغيلة كاملة)، فتشغيلة
    فاشلة منتصف الطريق لا تُعيد دفع ثمن ما اكتمل بالفعل (راجع
    `docs/DEEP_RESEARCH_DECISIONS.md`، حادثة نفاد الاعتمادات).
    """
    path = path or _db_path()
    with _connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS analyses ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "product TEXT, hs_code TEXT, year INTEGER, created_at TEXT, "
            "preliminary INTEGER, json_blob TEXT, "
            "outcome TEXT, outcome_date TEXT)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS market_scores ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "analysis_id INTEGER, country TEXT, iso3 TEXT, "
            "total_score REAL, confidence REAL, "
            "FOREIGN KEY(analysis_id) REFERENCES analyses(id))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS research_missions ("
            "analysis_id INTEGER, mission_key TEXT, status TEXT, "
            "report_json TEXT, completed_at TEXT, "
            "PRIMARY KEY (analysis_id, mission_key))"
        )
        # ترحيل القواعد الأقدم — additive migration; existing rows untouched.
        existing = {r[1] for r in conn.execute("PRAGMA table_info(analyses)")}
        for col in ("outcome", "outcome_date", "status", "kind",
                   "request_json", "updated_at"):
            if col not in existing:
                conn.execute(f"ALTER TABLE analyses ADD COLUMN {col} TEXT")


def save_analysis(result: dict, path: str | None = None,
                  analysis_id: int | None = None) -> int:
    """خزّن نتيجة تحليل وأعد المعرّف — store an analyze() result, return its row id.

    The full dict is json.dumps'd into json_blob; per-market scores are also
    flattened into market_scores for quick listing/querying.

    `analysis_id`: مرّره لتحديث صفّ **موجود بالفعل** بدل إدراج صفّ جديد —
    يستعمله مسار `/research` (نقطة تفتيش/استئناف، P0) حين يكون المعرّف
    قد خُصِّص مسبقاً عبر `create_research_run` قبل بدء البعثات، فتنتهي
    التشغيلة بنفس المعرّف الذي بدأت به لا معرّفاً جديداً.
    """
    path = path or _db_path()
    init_db(path)
    blob = json.dumps(result, ensure_ascii=False, default=_json_default)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with _connect(path) as conn:
        if analysis_id is not None:
            conn.execute(
                "UPDATE analyses SET product = ?, hs_code = ?, year = ?, "
                "preliminary = ?, json_blob = ?, status = 'completed', "
                "updated_at = ? WHERE id = ?",
                (result.get("product"), result.get("hs_code"),
                 result.get("year"), 1 if result.get("preliminary") else 0,
                 blob, now, analysis_id),
            )
        else:
            cur = conn.execute(
                "INSERT INTO analyses "
                "(product, hs_code, year, created_at, preliminary, "
                "json_blob, status, kind, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'completed', 'analyze', ?)",
                (result.get("product"), result.get("hs_code"),
                 result.get("year"), now,
                 1 if result.get("preliminary") else 0, blob, now),
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


# ── نقطة تفتيش/استئناف البحث العميق (P0، حادثة نفاد الاعتمادات) ─────────────

def create_research_run(product: str, market_iso3: str, hs_code: str | None,
                        request_snapshot: dict,
                        path: str | None = None) -> int:
    """خصّص معرّف تشغيلة بحث عميق **قبل** تشغيل أي بعثة — allocate the
    analysis_id up front so per-mission checkpoints can attach to it from
    the very first mission that finishes, not only at the very end.

    `request_snapshot`: كل ما يلزم لاستئناف التشغيلة لاحقاً بلا إعادة
    إرسال الطلب الأصلي (product/market/hs_code/product_card/agent_prefs/...)
    — يُقرأ عبر `get_research_run` حين يُمرَّر `resume=<id>` لاحقاً.
    """
    path = path or _db_path()
    init_db(path)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    placeholder = json.dumps({"status": "running", "product": product,
                              "hs_code": hs_code}, ensure_ascii=False)
    with _connect(path) as conn:
        cur = conn.execute(
            "INSERT INTO analyses "
            "(product, hs_code, year, created_at, preliminary, json_blob, "
            "status, kind, request_json, updated_at) "
            "VALUES (?, ?, NULL, ?, 1, ?, 'running', 'research', ?, ?)",
            (product, hs_code, now, placeholder,
             json.dumps(request_snapshot, ensure_ascii=False,
                        default=_json_default), now),
        )
        return int(cur.lastrowid)


def update_research_status(analysis_id: int, status: str,
                           path: str | None = None) -> None:
    """حدّث حالة تشغيلة — 'running'|'completed'|'failed'. لا يمسّ json_blob."""
    path = path or _db_path()
    now = datetime.datetime.now().isoformat(timespec="seconds")
    with _connect(path) as conn:
        conn.execute(
            "UPDATE analyses SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, analysis_id))


def mark_research_failed(analysis_id: int, error_message: str,
                         path: str | None = None) -> None:
    """سجّل فشل تشغيلة (استثناء غير متوقع خارج الحلقات المحروسة أصلاً) —
    الحالة 'failed' + سبب موجز في json_blob؛ نقاط تفتيش البعثات المكتملة
    فعلاً **تبقى** في research_missions (لا تُمسَح) — استئناف لاحق يقرأها."""
    path = path or _db_path()
    init_db(path)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    blob = json.dumps({"status": "failed",
                       "error": str(error_message)[:2000]}, ensure_ascii=False)
    with _connect(path) as conn:
        conn.execute(
            "UPDATE analyses SET status = 'failed', json_blob = ?, "
            "updated_at = ? WHERE id = ?", (blob, now, analysis_id))


def get_research_run(analysis_id: int, path: str | None = None) -> dict | None:
    """معلومات تشغيلة بحث عميق (بلا json_blob الكامل) — لاستعمالَي الاستئناف
    ونقطة نهاية الحالة (`GET /research/{id}/status`). None إن لم توجد."""
    path = path or _db_path()
    if not os.path.exists(path):
        return None
    init_db(path)  # ترحيل آمن للقواعد الأقدم قبل قراءة الأعمدة الجديدة
    with _connect(path) as conn:
        row = conn.execute(
            "SELECT id, product, hs_code, created_at, updated_at, status, "
            "kind, request_json FROM analyses WHERE id = ?", (analysis_id,)
        ).fetchone()
    if row is None:
        return None
    d = dict(row)
    try:
        d["request"] = json.loads(d.get("request_json") or "{}")
    except Exception:  # noqa: BLE001 — سجل فاسد = طلب فارغ، لا كسر
        d["request"] = {}
    return d


def save_mission_checkpoint(analysis_id: int, mission_key: str, report: object,
                            path: str | None = None) -> None:
    """خزّن نتيجة بعثة واحدة فور اكتمالها — the checkpoint write itself
    (P0). `report`: AgentReport حيّ — يُسلسَل كما تُسلسَل نتائج التحليل
    الكاملة (`_json_default`، dataclasses.asdict)."""
    path = path or _db_path()
    init_db(path)
    now = datetime.datetime.now().isoformat(timespec="seconds")
    status = "failed" if getattr(report, "failed", False) else "completed"
    blob = json.dumps(report, ensure_ascii=False, default=_json_default)
    with _connect(path) as conn:
        conn.execute(
            "INSERT INTO research_missions "
            "(analysis_id, mission_key, status, report_json, completed_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(analysis_id, mission_key) DO UPDATE SET "
            "status = excluded.status, report_json = excluded.report_json, "
            "completed_at = excluded.completed_at",
            (analysis_id, mission_key, status, blob, now))


def _agent_report_from_dict(d: dict):
    """أعد بناء AgentReport حيّ من JSON مُخزَّن — the resume-side inverse of
    `_json_default`'s dataclasses.asdict. يُستعمَل فقط عند تحميل نقاط
    تفتيش — لا يمسّ أي مسار تشغيل حيّ آخر."""
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    findings = []
    for f in (d.get("findings") or []):
        findings.append(DataPoint(**f) if isinstance(f, dict) else f)
    return AgentReport(agent_name=d.get("agent_name", ""), findings=findings,
                       failed=bool(d.get("failed")),
                       summary=d.get("summary", ""))


def load_mission_checkpoints(analysis_id: int,
                             path: str | None = None) -> dict:
    """كل نقاط تفتيش البعثات المكتملة لتشغيلة — {mission_key: AgentReport}.
    قاموس فارغ إن لم توجد قاعدة/تشغيلة — لا استثناء، لا اختلاق."""
    path = path or _db_path()
    if not os.path.exists(path):
        return {}
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT mission_key, report_json FROM research_missions "
            "WHERE analysis_id = ?", (analysis_id,)
        ).fetchall()
    out = {}
    for r in rows:
        try:
            out[r["mission_key"]] = _agent_report_from_dict(
                json.loads(r["report_json"]))
        except Exception as e:  # noqa: BLE001 — نقطة تفتيش فاسدة تُهمَل لا تكسر الاستئناف
            log.warning("corrupt checkpoint %s/%s ignored: %s",
                       analysis_id, r["mission_key"], e)
    return out


def mission_status_map(analysis_id: int, path: str | None = None) -> dict:
    """{mission_key: 'completed'|'failed'} للبعثات المخزَّنة فقط — البعثات
    الغائبة تعني 'pending' (لم تكتمل/تبدأ بعد) من منظور المستدعي."""
    path = path or _db_path()
    if not os.path.exists(path):
        return {}
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT mission_key, status FROM research_missions "
            "WHERE analysis_id = ?", (analysis_id,)
        ).fetchall()
    return {r["mission_key"]: r["status"] for r in rows}


def set_outcome(analysis_id: int, outcome: str,
                path: str | None = None) -> bool:
    """سجّل نتيجة تحليل فعلية — record what actually happened (wave 1).

    يضبط `outcome` (نص حر: "entered/GO confirmed/رفض العميل"...) و`outcome_date`
    (تاريخ اليوم). يعيد False إن لم يوجد التحليل — لا إنشاء ضمني.
    path=None يقرأ المسار الافتراضي وقت النداء (قابل للتوجيه في الاختبارات).
    """
    path = path or _db_path()
    if not os.path.exists(path):
        return False
    init_db(path)  # يضمن وجود العمودين على القواعد الأقدم (ترحيل آمن)
    with _connect(path) as conn:
        cur = conn.execute(
            "UPDATE analyses SET outcome = ?, outcome_date = ? WHERE id = ?",
            (outcome, datetime.date.today().isoformat(), analysis_id),
        )
    return cur.rowcount > 0


def list_analyses(path: str | None = None) -> list[dict]:
    """اسرد التحليلات المحفوظة — list saved analyses (newest first), metadata only."""
    path = path or _db_path()
    if not os.path.exists(path):
        return []
    init_db(path)  # ترحيل آمن للقواعد الأقدم قبل قراءة عمودي outcome
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT id, product, hs_code, year, created_at, preliminary, "
            "outcome, outcome_date FROM analyses ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_analysis(analysis_id: int, path: str | None = None) -> dict | None:
    """أعد تحليلًا كاملًا — fetch one full analysis dict, or None if absent.

    path=None يقرأ المسار الافتراضي وقت النداء (قابل للتوجيه في الاختبارات).
    """
    path = path or _db_path()
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
