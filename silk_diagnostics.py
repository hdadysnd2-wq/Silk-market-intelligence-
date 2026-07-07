"""تشخيص المصادر الحيّ لسِلك — Silk live source diagnostics.

يجيب سؤال «لماذا لا تشتغل الوكلاء؟» بصدق: يفحص كل مصدر بيانات **فعلياً** ويصنّف
حالته — متصل بنتائج، أم متصل بلا نتائج (سقف المعاينة/الحدّ)، أم غير قابل للوصول
(شبكة/بروكسي محجوب) — مع تلميح إصلاح لكل حالة. لا يختلق: يستعمل نفس نقطة الجلب
(`silk_data_layer._http_get`)، فما يراه المستخدم هو حال نشره الحقيقي.

Answers "why aren't the agents working?" honestly: probes each data source live
and classifies it (ok / reachable-but-empty / unreachable) with a fix hint. It
never raises; a total failure degrades to a fully-declared unreachable report.
"""
from __future__ import annotations

import logging
import os
import time

import silk_data_layer as dl

log = logging.getLogger(__name__)

# حالات المصدر — one of these three, never guessed.
OK = "ok"                    # متصل وأعاد بيانات
EMPTY = "reachable_empty"    # متصل لكن بلا صفوف (سقف المعاينة/الحدّ/سنة فارغة)
UNREACHABLE = "unreachable"  # شبكة/بروكسي/DNS محجوب — لم يصل أصلاً


def _timed_get(url: str, params: dict) -> dict:
    """جلب مؤقّت لا يرمي — timed GET; classifies reach vs failure (never raises)."""
    t0 = time.time()
    try:
        r = dl._http_get(url, params)
        r.raise_for_status()
        payload = r.json()
        return {"reachable": True, "payload": payload,
                "ms": int((time.time() - t0) * 1000)}
    except Exception as e:  # noqa: BLE001 — the probe must never raise
        return {"reachable": False, "error": f"{type(e).__name__}: {e}",
                "ms": int((time.time() - t0) * 1000)}


def _probe_comtrade(year: int) -> dict:
    """افحص Comtrade — نداء معاينة صغير + تمييز الحدّ عن الحجب عن وجود المفتاح."""
    key_set = bool(os.environ.get("COMTRADE_API_KEY", "").strip())
    params = {"reporterCode": "784", "period": str(year), "cmdCode": "080410",
              "flowCode": "M", "partnerCode": "0"}
    if key_set:
        params["subscription-key"] = os.environ["COMTRADE_API_KEY"].strip()
    res = _timed_get(dl._comtrade_url(), params)
    if not res["reachable"]:
        return {"name": "UN Comtrade", "state": UNREACHABLE, "key_set": key_set,
                "ms": res["ms"], "detail": res["error"],
                "hint": ("الخادم لا يصل إلى comtradeapi.un.org — تحقّق من أن سياسة "
                         "شبكة النشر تسمح بالنطاق (Railway: شبكة مفتوحة). "
                         "Host cannot reach Comtrade — allow the domain in the "
                         "deployment network policy.")}
    rows = (res["payload"] or {}).get("data") or []
    if rows:
        return {"name": "UN Comtrade", "state": OK, "key_set": key_set,
                "ms": res["ms"], "detail": f"{len(rows)} row(s)",
                "hint": "المصدر يعمل — Comtrade returns data."}
    # متصل لكن فارغ — أشهر سبب: بلا مفتاح، سقف المعاينة منخفض/متقطّع.
    return {"name": "UN Comtrade", "state": EMPTY, "key_set": key_set,
            "ms": res["ms"], "detail": "reachable but 0 rows",
            "hint": (("أضِف COMTRADE_API_KEY (تسجيل مجاني) — نقطة المعاينة بلا "
                      "مفتاح محدودة السقف وكثيراً ما تعيد فراغاً. "
                      "Add COMTRADE_API_KEY: the keyless preview endpoint is "
                      "rate-capped and often returns empty.") if not key_set else
                     ("المفتاح مضبوط لكن لا صفوف لهذه السنة/الرمز — جرّب سنة أقدم. "
                      "Key set but no rows for this period — try an earlier year."))}


def _probe_world_bank(year: int) -> dict:
    """افحص البنك الدولي — مؤشر دخل صغير لدولة معروفة."""
    url = f"{dl.ENDPOINTS['world_bank']}/country/SAU/indicator/NY.GDP.PCAP.PP.CD"
    res = _timed_get(url, {"format": "json", "per_page": "5", "date": str(year)})
    if not res["reachable"]:
        return {"name": "World Bank", "state": UNREACHABLE, "key_set": None,
                "ms": res["ms"], "detail": res["error"],
                "hint": ("الخادم لا يصل إلى api.worldbank.org — سياسة الشبكة. "
                         "Host cannot reach the World Bank API — network policy.")}
    payload = res["payload"]
    recs = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    has = any(r.get("value") is not None for r in recs)
    return {"name": "World Bank", "state": OK if has else EMPTY, "key_set": None,
            "ms": res["ms"],
            "detail": f"{len(recs)} record(s)" if has else "reachable but no value",
            "hint": ("المصدر يعمل — World Bank returns data." if has else
                     "متصل بلا قيمة لهذه السنة — جرّب سنة أخرى. Reachable, no value "
                     "for this year — try another.")}


def run_diagnostics(year: int = 2022) -> dict:
    """شخّص كل المصادر — probe every source; overall = worst case, all declared."""
    sources = [_probe_comtrade(year), _probe_world_bank(year)]
    states = {s["state"] for s in sources}
    if UNREACHABLE in states:
        overall = UNREACHABLE
    elif EMPTY in states:
        overall = EMPTY
    else:
        overall = OK
    agents_can_work = all(s["state"] == OK for s in sources)
    return {
        "overall": overall,
        "agents_can_work": agents_can_work,
        "year_probed": year,
        "sources": sources,
        "note": ("طبقة الوكلاء سليمة بنيوياً؛ نتائجها تعتمد على وصول هذه المصادر. "
                 "The agent layer is structurally sound; its output depends on "
                 "these sources being reachable."),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json
    print(json.dumps(run_diagnostics(), ensure_ascii=False, indent=2))
