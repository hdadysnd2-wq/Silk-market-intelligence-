"""عدّاد الاستهلاك المدفوع اليومي — daily paid-layer usage counter (stdlib SQLite).

سقف التكلفة (الموجة ٠): يَعُدّ تفعيلات الطبقات المدفوعة في اليوم ويرفض ما يتجاوز
السقف قبل تشغيل أي وكيل. The cap is enforced by api.py BEFORE any agent runs:
requests that would exceed it get HTTP 429, so a public deployment cannot be
drained of paid credits.

- الحد من متغير البيئة `SILK_PAID_DAILY_CAP` (عدد صحيح). غير مضبوط => لا سقف
  (وضع التطوير) — الإنتاج يضبطه دوماً. Unset => no cap (dev mode); production
  must set it.
- العدّاد في ملف SQLite مستقل (`data/usage.db` افتراضياً، أو `SILK_USAGE_DB`)
  حتى لا يلمس بيانات التحليلات في `data/silk.db` إطلاقاً.
- كل شيء stdlib، ولا نداء شبكة — نفس فلسفة `silk_storage.py`.
"""
from __future__ import annotations

import datetime
import logging
import os
import sqlite3

log = logging.getLogger(__name__)

_DEFAULT_PATH = os.path.join("data", "usage.db")


def _db_path() -> str:
    """مسار قاعدة العدّاد — usage DB path (env-overridable)."""
    return os.environ.get("SILK_USAGE_DB", "").strip() or _DEFAULT_PATH


def daily_cap() -> int | None:
    """السقف اليومي من البيئة — the daily paid-call cap, or None when unset.

    غير مضبوط/غير صالح => None (لا سقف — وضع التطوير). Production sets
    SILK_PAID_DAILY_CAP to a non-negative integer.
    """
    raw = os.environ.get("SILK_PAID_DAILY_CAP", "").strip()
    if not raw:
        return None
    try:
        cap = int(raw)
    except ValueError:
        log.warning("SILK_PAID_DAILY_CAP=%r is not an integer — cap ignored", raw)
        return None
    return cap if cap >= 0 else None


def _connect(path: str) -> sqlite3.Connection:
    """افتح الاتصال وأنشئ الجدول — open connection, ensure table exists."""
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS paid_usage ("
        "day TEXT PRIMARY KEY, calls INTEGER NOT NULL DEFAULT 0)"
    )
    return conn


def _today() -> str:
    """يوم اليوم — today's ISO date (the counter's bucket key)."""
    return datetime.date.today().isoformat()


def paid_calls_today(path: str | None = None) -> int:
    """استهلاك اليوم — paid-layer activations recorded today (0 on any error)."""
    try:
        with _connect(path or _db_path()) as conn:
            row = conn.execute(
                "SELECT calls FROM paid_usage WHERE day = ?", (_today(),)
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception as e:  # noqa: BLE001 — counter must never crash the API
        log.warning("usage counter read failed: %s", e)
        return 0


def record_paid_calls(n: int, path: str | None = None) -> None:
    """سجّل تفعيلات مدفوعة — add n paid-layer activations to today's bucket."""
    if n <= 0:
        return
    try:
        with _connect(path or _db_path()) as conn:
            conn.execute(
                "INSERT INTO paid_usage (day, calls) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls",
                (_today(), n),
            )
    except Exception as e:  # noqa: BLE001 — counter must never crash the API
        log.warning("usage counter write failed: %s", e)


def would_exceed_cap(requested: int, path: str | None = None) -> bool:
    """هل يتجاوز الطلب السقف؟ — True when cap is set AND today+requested > cap.

    فحص إخباري فقط (قراءة بلا حجز) — للحجز الفعلي استعمل
    try_reserve_paid_calls الذرّية. Informational read only; the enforcing
    path must use the atomic try_reserve_paid_calls instead.
    """
    cap = daily_cap()
    if cap is None or requested <= 0:
        return False
    return paid_calls_today(path) + requested > cap


def try_reserve_paid_calls(n: int, path: str | None = None) -> bool:
    """احجز n تفعيلات ذرّيًا — atomic check-and-reserve in ONE transaction.

    سدّ ثغرة السباق (TOCTOU): القراءة والتسجيل داخل معاملة واحدة
    (BEGIN IMMEDIATE تأخذ قفل الكتابة قبل القراءة)، فلا يمكن لطلبين
    متزامنين قرب حدّ السقف أن يقرآ "تحت السقف" معًا ثم يسجّلا معًا.
    Two concurrent /deepen requests can no longer both pass the cap check.

    - يعيد True والحجز مسجَّل، أو False (تجاوز السقف) وبلا أي تسجيل.
    - بلا سقف (SILK_PAID_DAILY_CAP غير مضبوط) => يسجّل ويعيد True دائمًا.
    - **عند فشل القاعدة يعيد False (fail-closed، M-2):** إن تعذّر التحقق من
      العدّاد (قفل/تلف/قرص) لا نسمح بصرف رصيد مدفوع بلا محاسبة — الرفض أأمن
      من التجاوز الصامت للسقف. (المسار المجاني لا يمرّ من هنا إطلاقاً، فلا
      يتأثر بهذا القرار.) On DB failure: log and **deny** the paid call.
    """
    if n <= 0:
        return True
    cap = daily_cap()
    try:
        with _connect(path or _db_path()) as conn:
            # قفل كتابة فوري قبل القراءة — write lock BEFORE the read.
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT calls FROM paid_usage WHERE day = ?", (_today(),)
            ).fetchone()
            current = int(row[0]) if row else 0
            if cap is not None and current + n > cap:
                conn.rollback()  # لا حجز عند الرفض — nothing recorded on refusal
                return False
            conn.execute(
                "INSERT INTO paid_usage (day, calls) VALUES (?, ?) "
                "ON CONFLICT(day) DO UPDATE SET calls = calls + excluded.calls",
                (_today(), n),
            )
        return True  # الخروج من with يُنهي المعاملة بالالتزام — commits on exit
    except Exception as e:  # noqa: BLE001 — counter must never crash the API
        log.warning("usage counter reserve failed (failing closed): %s", e)
        return False  # M-2: deny the paid call when accounting is unavailable
