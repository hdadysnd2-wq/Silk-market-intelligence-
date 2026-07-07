"""تشخيص المصادر الحيّ لسِلك — Silk live source diagnostics.

يجيب سؤال «أيّ مصدر يعمل فعلاً على نشري؟» بصدق: يفحص كل مصدر بيانات **حيّاً**
(نداءً حقيقياً بمفتاحك) ويصنّف حالته — متصل بنتائج، أم متصل بلا نتائج (حدّ/سنة
فارغة)، أم غير قابل للوصول (شبكة محجوبة)، أم بلا مفتاح — مع تلميح إصلاح لكل حالة.
لا يختلق. Answers "which source actually works on my deployment?" — probes each
live with your key and classifies it. Never raises; degrades to a declared report.

يفحص: UN Comtrade · World Bank · بحث الويب (Serper) · Google Maps · Claude.
"""
from __future__ import annotations

import logging
import os
import time

log = logging.getLogger(__name__)

OK = "ok"                    # متصل وأعاد بيانات
EMPTY = "reachable_empty"    # متصل لكن بلا نتائج (حدّ/سنة/استعلام فارغ)
UNREACHABLE = "unreachable"  # شبكة/بروكسي محجوب — لم يصل
NO_KEY = "no_key"            # المصدر يتطلب مفتاحاً وهو غير مضبوط


def _timed(fn) -> dict:
    """نفّذ مؤقّتاً بلا رمي — run a probe fn; classify reach vs failure."""
    t0 = time.time()
    try:
        r = fn()
        return dict(r, ms=int((time.time() - t0) * 1000))
    except Exception as e:  # noqa: BLE001 — a probe must never raise
        return {"state": UNREACHABLE, "detail": f"{type(e).__name__}: {e}",
                "ms": int((time.time() - t0) * 1000)}


def _probe_comtrade(year: int) -> dict:
    import silk_data_layer as dl
    key = bool(os.environ.get("COMTRADE_API_KEY", "").strip())

    def go():
        params = {"reporterCode": "784", "period": str(year), "cmdCode": "080410",
                  "flowCode": "M", "partnerCode": "0"}
        if key:
            params["subscription-key"] = os.environ["COMTRADE_API_KEY"].strip()
        r = dl._http_get(dl._comtrade_url(), params)
        r.raise_for_status()
        rows = (r.json() or {}).get("data") or []
        if rows:
            return {"state": OK, "detail": f"{len(rows)} صف"}
        return {"state": EMPTY, "detail": "متصل بلا صفوف"}
    out = _timed(go)
    out["name"] = "UN Comtrade"
    out["key_set"] = key
    out["hint"] = _hint_comtrade(out["state"], key)
    return out


def _hint_comtrade(state, key):
    if state == UNREACHABLE:
        return "الخادم لا يصل إلى comtradeapi.un.org — تحقّق من سياسة شبكة النشر."
    if state == EMPTY:
        return ("أضِف COMTRADE_API_KEY (تسجيل مجاني) — نقطة المعاينة بلا مفتاح "
                "محدودة السقف وتعيد فراغاً كثيراً." if not key else
                "المفتاح مضبوط لكن لا صفوف لهذه السنة — جرّب سنة أقدم.")
    return "المصدر يعمل — Comtrade returns data."


def _probe_worldbank(year: int) -> dict:
    import silk_data_layer as dl

    def go():
        url = f"{dl.ENDPOINTS['world_bank']}/country/SAU/indicator/NY.GDP.PCAP.PP.CD"
        r = dl._http_get(url, {"format": "json", "per_page": "5", "date": str(year)})
        r.raise_for_status()
        p = r.json()
        recs = p[1] if isinstance(p, list) and len(p) > 1 else []
        has = any(x.get("value") is not None for x in recs)
        return {"state": OK if has else EMPTY,
                "detail": f"{len(recs)} سجل" if has else "متصل بلا قيمة"}
    out = _timed(go)
    out["name"] = "World Bank"
    out["key_set"] = None
    out["hint"] = ("الخادم لا يصل إلى api.worldbank.org — سياسة الشبكة."
                   if out["state"] == UNREACHABLE else
                   ("متصل بلا قيمة لهذه السنة — جرّب أخرى." if out["state"] == EMPTY
                    else "المصدر يعمل."))
    return out


def _probe_serper() -> dict:
    key = os.environ.get("SEARCH_API_KEY", "").strip()
    if not key:
        return {"name": "بحث الويب (Serper)", "state": NO_KEY, "key_set": False,
                "ms": 0, "detail": "بلا مفتاح",
                "hint": "أضِف SEARCH_API_KEY (serper.dev) لتفعيل بحث الويب/الثقافة/المرشّحين."}

    def go():
        import requests
        r = requests.post("https://google.serper.dev/search",
                          headers={"X-API-KEY": key, "Content-Type": "application/json"},
                          json={"q": "dates market", "num": 3}, timeout=20)
        r.raise_for_status()
        org = (r.json() or {}).get("organic") or []
        return {"state": OK if org else EMPTY,
                "detail": f"{len(org)} نتيجة" if org else "متصل بلا نتائج"}
    out = _timed(go)
    out["name"] = "بحث الويب (Serper)"
    out["key_set"] = True
    out["hint"] = ("لا يصل إلى google.serper.dev — الشبكة." if out["state"] == UNREACHABLE
                   else ("المفتاح قد يكون غير صالح أو نفد رصيده." if out["state"] == EMPTY
                         else "المصدر يعمل."))
    return out


def _probe_maps() -> dict:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key:
        return {"name": "Google Maps", "state": NO_KEY, "key_set": False, "ms": 0,
                "detail": "بلا مفتاح",
                "hint": "أضِف GOOGLE_MAPS_API_KEY لتفعيل الموردين/الموزّعين بالاسم."}

    def go():
        import requests
        r = requests.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                         params={"query": "dates distributor", "key": key}, timeout=20)
        r.raise_for_status()
        d = r.json() or {}
        st = d.get("status")
        if st == "OK" and (d.get("results") or []):
            return {"state": OK, "detail": f"{len(d['results'])} مكان"}
        if st in ("ZERO_RESULTS",):
            return {"state": EMPTY, "detail": "متصل بلا نتائج"}
        return {"state": EMPTY, "detail": f"حالة Google: {st}"}
    out = _timed(go)
    out["name"] = "Google Maps"
    out["key_set"] = True
    out["hint"] = ("لا يصل إلى maps.googleapis.com — الشبكة." if out["state"] == UNREACHABLE
                   else ("تحقّق من صلاحية المفتاح وتفعيل Places API والفوترة."
                         if out["state"] == EMPTY else "المصدر يعمل."))
    return out


def _probe_anthropic() -> dict:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return {"name": "Claude (Anthropic)", "state": NO_KEY, "key_set": False,
                "ms": 0, "detail": "بلا مفتاح",
                "hint": "أضِف ANTHROPIC_API_KEY لتفعيل طبقة القرار وفلترة الوكيل الذكية."}

    def go():
        import requests
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=25,
                          headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                                   "content-type": "application/json"},
                          json={"model": os.environ.get("SILK_AI_MODEL", "claude-opus-4-8"),
                                "max_tokens": 4,
                                "messages": [{"role": "user", "content": "ping"}]})
        if r.status_code == 200:
            return {"state": OK, "detail": "المفتاح يعمل"}
        return {"state": EMPTY, "detail": f"HTTP {r.status_code}"}
    out = _timed(go)
    out["name"] = "Claude (Anthropic)"
    out["key_set"] = True
    out["hint"] = ("لا يصل إلى api.anthropic.com — الشبكة." if out["state"] == UNREACHABLE
                   else ("المفتاح غير صالح أو نفد رصيده." if out["state"] == EMPTY
                         else "المصدر يعمل."))
    return out


def run_diagnostics(year: int = 2022) -> dict:
    """شخّص كل المصادر حيّاً — probe every source; overall = worst case."""
    sources = [_probe_comtrade(year), _probe_worldbank(year), _probe_serper(),
               _probe_maps(), _probe_anthropic()]
    states = {s["state"] for s in sources}
    if UNREACHABLE in states:
        overall = UNREACHABLE
    elif EMPTY in states or NO_KEY in states:
        overall = EMPTY
    else:
        overall = OK
    # الوكلاء ينتجون دراسة حقيقية متى عمل الأساس (Comtrade) على الأقل.
    core = {s["name"]: s["state"] for s in sources}
    agents_can_work = core.get("UN Comtrade") == OK and core.get("World Bank") == OK
    return {"overall": overall, "agents_can_work": agents_can_work,
            "year_probed": year, "sources": sources,
            "note": ("طبقة الوكلاء سليمة بنيوياً؛ عمقُ الدراسة يتبع أيّ مصدرٍ أخضر. "
                     "Agent layer is structurally sound; study depth follows which "
                     "sources are green.")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import json
    print(json.dumps(run_diagnostics(), ensure_ascii=False, indent=2))
