"""القالب الموحّد لسِلك — Silk unified render template (wave 4, vision §10.1).

قالب واحد «أصل» والباقي مشتقات: `build_view()` يبني نموذج العرض القانوني
الوحيد من نتيجة المحرّك، وكل المخرجات تشتق منه:
  - اللوحة (الواجهة تستهلك `result["view"]` من الـ API)
  - نص الطرفية (`render_text` — يحل محل جسد format_result القديم)
  - أداة المطوّر Streamlit (`tools/dev_console.py` تقرأ الجدول من النموذج نفسه)
  - سطور المختصر (`view["brief"]` — القرار + الموقع التنافسي بسطرين)

المبرر (vision §10.1): خلل «التحليل الأجوف» كان خلل ربط عرض — مسارات
عرض منفصلة = فرص متعددة لنفس الخطأ؛ مسار مشترك = الخطأ يقع مرة ويُصلح مرة.

منطق عرض صرف: صفر شبكة، صفر تعديل على الأرقام — قراءة وتشكيل فقط.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)


def _dp(obj: object) -> dict:
    """طبّع DataPoint/dict — normalize a DataPoint or dict to a plain dict."""
    if isinstance(obj, dict):
        return obj
    return {"value": getattr(obj, "value", None),
            "source": getattr(obj, "source", ""),
            "confidence": getattr(obj, "confidence", 0.0),
            "note": getattr(obj, "note", ""),
            "retrieved_at": getattr(obj, "retrieved_at", "")}


def _decision(top: dict | None) -> dict:
    """القرار أولاً (vision §10.2) — verdict + confidence + one-line why."""
    if not top:
        return {"verdict": None, "confidence": None,
                "why": "لا أسواق مرتّبة — لا بيانات كافية"}
    jury = top.get("jury") or {}
    ai = jury.get("ai") or {}
    verdict = ai.get("verdict") or jury.get("verdict")
    confidence = (ai.get("confidence") if ai.get("confidence") is not None
                  else jury.get("confidence"))
    why = (ai.get("reasoning")
           or f"تغطية الوكلاء {jury.get('agents_with_data', 0)}/"
              f"{jury.get('agents_total', 0)} وفجوات: "
              f"{', '.join(jury.get('data_gaps', [])) or 'لا شيء'}")
    return {"verdict": verdict, "confidence": confidence,
            "why": (why or "")[:280], "market": top.get("country"),
            "stage": jury.get("synthesis_stage")}


def _competitive_position(top: dict | None) -> dict:
    """قسم "موقعك التنافسي" — the correlation section, or an honest absence."""
    cp = (top or {}).get("competitive_position")
    if not cp or "error" in (cp or {}):
        return {"available": False,
                "note": (cp or {}).get("error")
                or "أضف بطاقة منتجك (product_card) للحصول على موقعك التنافسي"}
    feas = cp.get("feasibility_threads") or []
    best = max(feas, key=lambda f: f.get("margin_at_match_pct", -9e9),
               default=None)
    doors = (cp.get("entry_thread") or {}).get("doors") or []
    realistic = next((d for d in doors if str(d.get("assessment", ""))
                      .startswith("واقعية")), doors[0] if doors else None)
    return {
        "available": True,
        "market": (top or {}).get("country"),
        "coverage": cp.get("coverage"),
        "competitor_threads": cp.get("competitor_threads"),
        "feasibility_threads": feas,
        "entry_thread": cp.get("entry_thread"),
        "contacts_thread": cp.get("contacts_thread"),
        "nearest_beatable": best,
        "best_door": realistic,
        "note": cp.get("note"),
    }


def _brief(decision: dict, cp: dict) -> list[str]:
    """المختصر — سطران للموقع التنافسي فوق سطر القرار (vision §6, §10.4)."""
    lines = [f"القرار: {decision.get('verdict') or 'تعذّر الحكم'} "
             f"(ثقة {decision.get('confidence')}) — {decision.get('market') or '؟'}"]
    if cp.get("available"):
        best = cp.get("nearest_beatable")
        lines.append(
            f"أقرب منافس قابل للمنافسة: {best['competitor']} — هامشك عند "
            f"مضاهاته {best['margin_at_match_pct']}%" if best else
            "لا منافس بسعر مرصود بعد — فعّل with_localprice/deepen")
        door = cp.get("best_door")
        lines.append(f"أفضل باب دخول مرصود: {door['name']} ({door['assessment']})"
                     if door else "لا أبواب دخول مرصودة — فعّل with_channels")
    else:
        lines.append(cp.get("note", ""))
    return lines


def _completeness(markets: list) -> dict:
    """مؤشر اكتمال الدراسة — how much of the study is OBSERVED vs. declared gaps.

    يعدّ المكوّنات المرصودة (`value is not None`) عبر كل الأسواق ويعطي نسبة
    مئوية + تفصيلاً لكل مكوّن. لا يعدّل رقماً — قراءة فقط؛ يبني ثقة المستخدم
    بإظهار «كم% من الدراسة مرصود فعلاً» بدل إيحاء زائف بالاكتمال (المبدأ
    التأسيسي: الفجوات معلنة). Pure read-only; observed/total across markets.
    """
    total = observed = 0
    by_component: dict[str, dict] = {}
    for row in markets:
        for name, c in (row.get("components") or {}).items():
            present = _dp(c).get("value") is not None
            total += 1
            observed += 1 if present else 0
            b = by_component.setdefault(name, {"observed": 0, "total": 0})
            b["total"] += 1
            b["observed"] += 1 if present else 0
    pct = round(100.0 * observed / total, 1) if total else 0.0
    if pct >= 75:
        label = "دراسة شبه مكتملة — most components observed"
    elif pct >= 40:
        label = "دراسة جزئية — الفجوات معلنة، partial with declared gaps"
    else:
        label = "بيانات ضعيفة — thin data, gaps dominate"
    return {"observed": observed, "total": total, "pct": pct,
            "gap_count": total - observed, "by_component": by_component,
            "label": label}


def _fval(f: object) -> object:
    """قيمة نتيجة — .value whether DataPoint, dict, or a plain value."""
    if isinstance(f, dict):
        return f.get("value")
    return getattr(f, "value", f)


def _real_list(x: object) -> list:
    """قيم مرصودة فقط — real values from a DataPoint-or-list field ([] if none)."""
    if x is None:
        return []
    items = x if isinstance(x, list) else [x]
    out = []
    for f in items:
        v = _fval(f)
        if v is not None:
            out.append(v)
    return out


def _prices(row: dict) -> list:
    """أسعار السوق المرصودة — observed retail listings (localprice layer)."""
    out = []
    for v in _real_list(row.get("localprice")):
        if isinstance(v, dict) and v.get("price") is not None:
            out.append({"title": v.get("title"), "price": v.get("price"),
                        "currency": v.get("currency"), "store": v.get("store")})
    return out


def _named_competitors(row: dict) -> list:
    """منافسون بالاسم — named-competitor candidates (web layer)."""
    out = []
    for v in _real_list(row.get("competitors_named")):
        name = (v.get("title") or v.get("name")) if isinstance(v, dict) else v
        if name:
            out.append(str(name))
    return out


def _suppliers(row: dict) -> list:
    """موردون/أعمال بالاسم — named businesses (maps/volza/explee)."""
    out = []
    for key, src in (("maps", "Google Maps"), ("volza", "Volza"),
                     ("explee", "explee")):
        for v in _real_list(row.get(key)):
            name = v.get("name") if isinstance(v, dict) else v
            if name:
                out.append({"name": str(name), "source": src})
    return out


def _culture(result: dict) -> list:
    """ثقافة المستهلك — consumer-culture web findings (websearch layer)."""
    out = []
    for v in _real_list(result.get("websearch")):
        if isinstance(v, dict):
            title = v.get("title") or v.get("snippet")
            if title:
                out.append({"title": str(title), "link": v.get("link")})
        elif v:
            out.append({"title": str(v), "link": None})
    return out


def _t_today() -> str:
    import datetime
    return datetime.date.today().isoformat()


# ── Stage 2A: تغطية المصادر لكل قسم + ملحق الأثر — coverage & provenance ──────

_SECTION_FIELDS = {
    "market_size": ("components",),                # سيُفصَّل داخلياً
    "regulatory": ("requirements", "tariff"),
    "competitors": ("competitors", "competitors_named", "maps"),
    "pricing": ("prices", "localprice"),
    "demand": ("faostat",),
    "risk": ("risk",),
    # إصلاح مراجعة Stage 5 (ثغرة ٣): حقائق Google Trends تُحسب لقسم الاتجاه —
    # كانت «الاتجاه 0/0» بينما Trends أسهمت فعلاً لأن خط السنوات dict بلا
    # حقل value مباشر وطبقة trends كانت محسوبة على الطلب.
    "trend": ("trends",),
}


def _section_dps(row: dict, sec: str) -> list[dict]:
    """نقاط بيانات قسم واحد — the ONE fact-to-section extractor (تُستخدم في
    التغطية والبوابة معاً كي يستحيل اختلافهما)."""
    dps: list[dict] = []
    if sec == "market_size":
        comps = row.get("components") or {}
        for k in ("market_size", "saudi_position", "competition"):
            _walk_dps(comps.get(k), dps)
    elif sec == "demand":
        comps = row.get("components") or {}
        _walk_dps(comps.get("demand_capacity"), dps)
        _walk_dps(row.get("faostat"), dps)
    elif sec == "trend":
        # سلسلة الاتجاه متعدد السنوات: dict بسنوات مرصودة/فجوات — كل سنة حقيقة.
        tr = row.get("trend") or {}
        for pt in tr.get("series") or []:
            dps.append({"source": tr.get("source", "UN Comtrade"),
                        "value": pt.get("value"),
                        "note": f"سنة {pt.get('year')} من خط الاتجاه"})
        _walk_dps(row.get("trends"), dps)      # إشارة Google Trends
    else:
        for f in _SECTION_FIELDS.get(sec, ()):
            _walk_dps(row.get(f), dps)
    return dps


def _walk_dps(obj, out):
    """اجمع كل نقاط البيانات (dict أو DataPoint) — collect every datapoint-shaped node."""
    if isinstance(obj, dict):
        if "source" in obj and "value" in obj:
            out.append(obj)
        for v in obj.values():
            _walk_dps(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _walk_dps(v, out)
    elif hasattr(obj, "source") and hasattr(obj, "value"):
        out.append({"source": obj.source, "value": obj.value,
                    "note": getattr(obj, "note", "")})


def _provenance(result: dict) -> list[dict]:
    """ملحق الأثر (Stage 2A) — لكل مصدر: المحاولات، المُسهم، وأمثلة أسباب الفشل.
    لا فشل صامتاً: كل نداء فاشل يظهر هنا بملاحظته الموسومة."""
    dps: list[dict] = []
    _walk_dps(result, dps)
    by: dict[str, dict] = {}
    for d in dps:
        src = str(d.get("source") or "?")
        b = by.setdefault(src, {"source": src, "attempted": 0,
                                "contributed": 0, "failures": []})
        b["attempted"] += 1
        if d.get("value") is not None:
            b["contributed"] += 1
        elif len(b["failures"]) < 3 and d.get("note"):
            b["failures"].append(str(d.get("note"))[:140])
    return sorted(by.values(), key=lambda b: -b["contributed"])


def _section_coverage(row: dict) -> dict:
    """درجة تغطية لكل قسم — {section: {attempted, contributed, score, single_source,
    low_confidence}}. قسم بمصدر واحد فقط يُعلَّم منخفض الثقة (قاعدة 2A)."""
    out: dict[str, dict] = {}
    for section in _SECTION_FIELDS:
        dps = _section_dps(row, section)
        att = len(dps)
        con = sum(1 for d in dps if d.get("value") is not None)
        srcs = {str(d.get("source")) for d in dps if d.get("value") is not None}
        out[section] = {
            "attempted": att, "contributed": con,
            "score": round(con / att, 2) if att else 0.0,
            "single_source": len(srcs) == 1 and con > 0,
            "low_confidence": (len(srcs) <= 1),
        }
    return out


# ── Stage 2B: بوابة الخصوصية — per-section specificity gate ──────────────────
# العتبات المقترحة (قابلة للضبط): أدنى عدد حقائق سوقية حقيقية ليُعرض القسم كنثر؛
# دونها يُعرض «بيانات غير كافية» + قائمة المصادر المُحاوَلة — لا نثر عام أبداً.
SECTION_THRESHOLDS = {
    "market_size": 2,   # الحجم + (حصة أو تركّز) — رقم واحد لا يصنع قسم سوق
    "demand": 1,
    "regulatory": 2,    # بند اشتراطات + التعريفة (بند خروج عام وحده لا يكفي)
    "competitors": 2,
    "pricing": 1,
    "risk": 2,
    "trend": 2,         # سنتان على الأقل لخط اتجاه
}


def _section_status(row: dict) -> dict:
    """حالة كل قسم بعد بوابة العتبة — {section: {status, contributed, threshold,
    sources_attempted}}. status: ok | insufficient."""
    cov = _section_coverage(row)
    out: dict[str, dict] = {}
    for sec, c in cov.items():
        thr = SECTION_THRESHOLDS.get(sec, 1)
        # نفس المستخرج الواحد — يستحيل اختلاف البوابة عن التغطية (ثغرة ٣).
        dps = _section_dps(row, sec)
        attempted_sources = sorted({str(d.get("source")) for d in dps
                                    if d.get("source")})
        out[sec] = {
            "status": "ok" if c["contributed"] >= thr else "insufficient",
            "contributed": c["contributed"], "threshold": thr,
            "sources_attempted": attempted_sources,
        }
    return out


def insufficient_line(sec_ar: str, st: dict) -> str:
    """جملة النقص الوحيدة المسموح بها (2B-ب) — the only allowed insufficiency text."""
    srcs = "، ".join(st.get("sources_attempted") or []) or "لا مصادر مُحاوَلة"
    return (f"بيانات غير كافية لقسم «{sec_ar}» "
            f"({st['contributed']}/{st['threshold']} حقائق سوقية) — "
            f"المصادر المُحاوَلة: {srcs}")


# ── Stage 5: مشتقات حزمة البحث (§7) — SWOT قاعدي، شرائح، دليل مورّدين ─────────

def _rmetric(research: dict | None, agent: str, metric: str):
    """قيمة مقياس من حزمة §4b — value of a metric from the research bundle."""
    for f in ((research or {}).get("agents", {}).get(agent, {})
              .get("findings") or []):
        if f.get("metric") == metric and f.get("value") is not None:
            return f.get("value")
    return None


def _swot(research: dict | None) -> dict:
    """SWOT قاعدي (§7-5) — كل خلية من حقيقة مرصودة بدليلها؛ الفارغ يُعلَن.

    اشتقاق عرض صرف: قواعد معلنة فوق حقائق حزمة البحث — لا نثر حر ولا تخمين.
    """
    S, W, O, T = [], [], [], []
    if not research or not research.get("agents"):
        return {"S": S, "W": W, "O": O, "T": T,
                "note": "يتطلب حزمة وكلاء البحث (with_research)"}
    sau = _rmetric(research, "competitor", "saudi_share_pct")
    if sau:
        S.append({"text": f"حضور سعودي قائم بحصة {sau}% من واردات السوق",
                  "evidence": "UN Comtrade — saudi_share_pct"})
    uv = _rmetric(research, "pricing", "border_unit_value_usd_kg")
    suv = _rmetric(research, "pricing", "saudi_border_unit_value_usd_kg")
    if uv and suv and suv <= uv:
        S.append({"text": f"سعر حدودي سعودي منافس ({suv}$ مقابل متوسط {uv}$/kg)",
                  "evidence": "UN Comtrade — قيم الوحدة"})
    for g in (research.get("agents", {}).get("pricing", {}).get("gaps") or []):
        if "بطاقة" in g or "margin" in g:
            W.append({"text": "الهامش غير محسوب — بطاقة المنتج غير مكتملة",
                      "evidence": g[:120]})
            break
    gate = _rmetric(research, "regulatory", "eligibility_gate")
    if gate:
        W.append({"text": "بوابة أهلية أوروبية مفتوحة (منشأة معتمدة EU 2017/625)",
                  "evidence": "مرجع L1 — eligibility_gate"})
    cagr = _rmetric(research, "market_size", "import_cagr_pct")
    if cagr is not None and cagr > 5:
        O.append({"text": f"واردات السوق تنمو {cagr}% سنوياً مركّباً",
                  "evidence": "UN Comtrade — import_cagr_pct"})
    hhi = _rmetric(research, "competitor", "hhi")
    if hhi is not None and hhi < 0.15:
        O.append({"text": f"سوق مفتّت (HHI {hhi}) — لا مورّد مهيمناً",
                  "evidence": "UN Comtrade — hhi"})
    rr = _rmetric(research, "consumer_demand", "ramadan_seasonality")
    if rr and "مرجّحة" in str(rr):
        O.append({"text": "موسمية رمضان/العيدين فرصة ذروة طلب",
                  "evidence": "قاعدة معلنة فوق مرجع Pew"})
    top = _rmetric(research, "competitor", "top_supplier_share_pct")
    if top is not None and top > 50:
        T.append({"text": f"مورّد مهيمن بحصة {top}% — حرب أسعار محتملة",
                  "evidence": "UN Comtrade — top_supplier_share_pct"})
    tariff = _rmetric(research, "regulatory", "tariff_applied_pct")
    if tariff is not None and tariff > 10:
        T.append({"text": f"تعريفة مطبّقة مرتفعة {tariff}%",
                  "evidence": "WITS — tariff_applied_pct"})
    fx = _rmetric(research, "risk", "fx_volatility_pct")
    if fx is not None and fx > 5:
        T.append({"text": f"تقلب عملة {fx}% (معامل اختلاف)",
                  "evidence": "World Bank — PA.NUS.FCRF"})
    if _rmetric(research, "risk", "critical_risk"):
        T.append({"text": "خطر سياسي حرج (WGI دون −1.5)",
                  "evidence": "World Bank — PV.EST"})
    return {"S": S, "W": W, "O": O, "T": T,
            "note": "خلايا قاعدية من حقائق مرصودة حصراً — الخلية الفارغة تعني "
                    "لا بند مرصوداً، لا أنها سليمة"}


def _segments(research: dict | None) -> list[dict]:
    """شرائح العملاء (§7-8) — دخل × ثقافة استهلاك، بقواعد معلنة وفجوات مصرّحة."""
    if not research or not research.get("agents"):
        return []
    out = []
    gdp = _rmetric(research, "consumer_demand", "gdp_per_capita_usd")
    if gdp is not None:
        tier = ("مرتفع" if gdp > 25_000 else
                "متوسط" if gdp > 8_000 else "منخفض")
        out.append({"segment": f"شريحة الدخل: {tier}",
                    "basis": f"نصيب الفرد {round(gdp):,}$ (World Bank) — "
                             "عتبات معلنة 8k/25k"})
    ms = _rmetric(research, "consumer_demand", "muslim_share_pct")
    if ms is not None:
        out.append({"segment": f"شريحة الحلال/رمضان: {ms}% من السكان",
                    "basis": "مرجع Pew الساكن — muslim_share_pct"})
    si = _rmetric(research, "consumer_demand", "search_interest")
    if si is not None:
        out.append({"segment": f"اهتمام البحث بالمنتج: {si}/100",
                    "basis": "Google Trends — search_interest"})
    return out


def _supplier_directory(research: dict | None) -> dict:
    """دليل المورّدين (§7 بتوجيه المالك) — مرشّحون موسومون غير موثَّقين."""
    return {"saudi": _rmetric(research, "supplier", "saudi_suppliers") or [],
            "target": _rmetric(research, "supplier", "target_distributors")
                      or [],
            "note": "مرشّحون غير موثَّقين (ثقة 0.4) — أكّدهم قبل التعاقد؛ "
                    "الترقية الموثّقة عبر /deepen"}


def build_view(result: dict) -> dict:
    """ابنِ نموذج العرض القانوني — the ONE canonical view-model (vision §10.1).

    كل المخرجات (لوحة/طرفية/Streamlit/مختصر) تشتق من هذا النموذج حصراً.
    """
    markets = result.get("markets") or []
    top = markets[0] if markets else None
    decision = _decision(top)
    # حكم واحد لا حكمان (إصلاح مراجعة Stage 5): عند وجود قرار المحرك الموزون
    # (§8) الصالح فهو **الحكم الوحيد** في كل التقرير — هيئة المحلفين تتحول إلى
    # سطر كفاية بيانات بلا كلمة حكم (خطة §8a: الجورية بوابة كفاية لا قرار).
    ed_top = (top or {}).get("decision") or {}
    if ed_top.get("schema") and not ed_top.get("error"):
        jury = (top or {}).get("jury") or {}
        decision = {
            "verdict": ed_top.get("verdict"),
            "confidence": ed_top.get("confidence"),
            "score": ed_top.get("score"),
            "why": ed_top.get("why"),
            "market": (top or {}).get("country"),
            "stage": "silk.decision/v1 — المحرك الموزون §8 (الحكم الوحيد)",
            "sufficiency": (f"بوابة كفاية البيانات: {jury.get('agents_with_data', 0)}/"
                            f"{jury.get('agents_total', 0)} وكلاء أساسيون لديهم "
                            f"بيانات؛ فجوات: "
                            f"{'، '.join(jury.get('data_gaps', [])) or 'لا شيء'}"),
        }
    cp = _competitive_position(top)
    view_markets = []
    for row in markets:
        comps = row.get("components") or {}
        present = sum(1 for c in comps.values() if _dp(c).get("value") is not None)
        view_markets.append({
            "country": row.get("country"), "iso3": row.get("iso3"),
            "score": row.get("total_score"), "confidence": row.get("confidence"),
            "components_present": f"{present}/{len(comps) or 4}",
            # §10.3: سطر مصدر تحت كل رقم — مبني في القالب نفسه فيستحيل
            # بنيوياً ظهور رقم بلا نسب في أي مشتق (docx/نص/لوحة).
            "components_detail": [
                {"name": name, "value": _dp(c).get("value"),
                 "source": _dp(c).get("source"),
                 "confidence": _dp(c).get("confidence"),
                 "retrieved_at": _dp(c).get("retrieved_at", ""),
                 "note": _dp(c).get("note", "")}
                for name, c in comps.items()],
            "recommendation": row.get("recommendation"),
            "quality_flags": row.get("quality_flags") or [],
            "has_competitive_position": "competitive_position" in row,
            # §سنوات الدراسة: خط الاتجاه متعدد السنوات إن فُعِّل (with_trend)،
            # وإلا None — الواجهة تعرضه أو تعلن «يتطلب تفعيل مدى السنوات».
            "trend": row.get("trend"),
            # طبقات الإثراء المرصودة (أسعار/منافسون/موردون) — يعرضها التقرير
            # والواجهة؛ الفارغ يُعلن «غير مرصود» لا يُخترع.
            "prices": _prices(row),
            "named_competitors": _named_competitors(row),
            "supplier_countries": row.get("competitors") or [],
            "suppliers": _suppliers(row),
            # Stage 2A: مخاطر (WGI/LPI/FX) + درجة تغطية المصادر لكل قسم
            "risk": [_dp(f) for f in (row.get("risk") or [])],
            "section_coverage": _section_coverage(row),
            "section_status": _section_status(row),   # بوابة 2B
            # Stage 5: حزمة §4b كما تحقق منها المنسّق + قرار §8 + مشتقاتها
            # القاعدية (SWOT/شرائح/دليل مورّدين) — اشتقاق عرض صرف.
            "research": row.get("research"),
            "entry_decision": row.get("decision"),
            "swot": _swot(row.get("research")),
            "segments": _segments(row.get("research")),
            "supplier_directory": _supplier_directory(row.get("research")),
        })
    limits = [f"{m['country']}: {f}" for m in markets[:5]
              for f in (m.get("quality_flags") or [])]
    if not result.get("classified"):
        limits.insert(0, result.get("hs_note") or "تعذّر التصنيف")
    # ترويسة 2B: التغطية الإجمالية % = مُسهم/مُحاوَل عبر أقسام السوق الأعلى.
    top_cov = _section_coverage(markets[0]) if markets else {}
    att = sum(c["attempted"] for c in top_cov.values())
    con = sum(c["contributed"] for c in top_cov.values())
    header = {
        "product": result.get("product"), "hs_code": result.get("hs_code"),
        "origin": "SAU",
        "target_market": (markets[0].get("country") or markets[0].get("iso3"))
                         if markets else None,
        "date": _t_today(),
        "coverage_pct": round(100 * con / att, 1) if att else 0.0,
    }
    view = {
        # راية التشغيل البرهاني: العواذف تضبط SILK_HERMETIC — كل المشتقات تطبع
        # لافتة TEST RUN؛ وفي الإنتاج يرفض المولّد أي أثر برهاني (silk_reports).
        "test_run": bool(os.environ.get("SILK_HERMETIC")),
        "header": header,
        "product": result.get("product"), "hs_code": result.get("hs_code"),
        "hs_confidence": result.get("hs_confidence"),
        "year": result.get("year"), "preliminary": True,
        "classified": result.get("classified", False),
        "decision": decision,
        "competitive_position": cp,
        "completeness": _completeness(markets),
        "markets": view_markets,
        "culture": _culture(result),          # ثقافة المستهلك (بحث الويب)
        "brief": _brief(decision, cp),
        "limits": limits,
        "provenance": _provenance(result),   # Stage 2A: لا فشل صامتاً
        "note": result.get("note"),
    }
    return view


def render_text(view: dict) -> str:
    """نص الطرفية من القالب — terminal rendering derived from the view only."""
    L = ["═" * 60]
    if view.get("test_run"):
        L.append("⚠ TEST RUN — تشغيل برهاني ببدائل موسومة، ليس تقريراً إنتاجياً")
    L.append(f"المنتج / Product : {view.get('product')}")
    if not view.get("classified"):
        L += ["الحالة: تعذّر التصنيف — could not classify",
              *(f"  حد: {x}" for x in view.get("limits", [])[:3]), "═" * 60]
        return "\n".join(L)
    d = view["decision"]
    h = view.get("header") or {}
    L.append(f"المنتج: {h.get('product')} | HS: {h.get('hs_code')} | "
             f"السوق: {h.get('target_market')} | {h.get('date')} | "
             f"تغطية: {h.get('coverage_pct')}%")
    st0 = (view.get("markets") or [{}])[0].get("section_status") or {}
    for sec, st in st0.items():
        if st.get("status") == "insufficient":
            L.append("  " + insufficient_line(sec, st))
    cov0 = (view.get("markets") or [{}])[0].get("section_coverage") or {}
    if cov0:
        L.append("تغطية الأقسام: " + " | ".join(
            f"{k}:{c['contributed']}/{c['attempted']}" for k, c in cov0.items()))
    prov = view.get("provenance") or []
    if prov:
        L.append("أثر المصادر: " + " ، ".join(
            f"{b['source']}={b['contributed']}/{b['attempted']}"
            for b in prov[:6]))
    L += [f"رمز HS: {view['hs_code']} (ثقة {view['hs_confidence']}) | "
          f"سنة {view['year']} | مبدئي",
          f"القرار: {d.get('verdict') or 'تعذّر الحكم'} "
          f"(ثقة {d.get('confidence')}) — {d.get('market')}",
          f"لماذا: {d.get('why')}", "─" * 60]
    ed = (view.get("markets") or [{}])[0].get("entry_decision") or {}
    if ed.get("schema"):
        L.append(f"قرار الدخول (§8): {ed.get('verdict')} score={ed.get('score')} "
                 f"ثقة={ed.get('confidence')} [أوزان {ed.get('weights_option')}]"
                 f" — {ed.get('why')}")
        for c in (ed.get("conditions") or [])[:3]:
            L.append(f"  شرط: {c}")
    cp = view["competitive_position"]
    L.append("موقعك التنافسي:")
    if cp.get("available"):
        L.append(f"  التغطية: {cp.get('coverage')}")
        for f in cp.get("feasibility_threads") or []:
            L.append(f"  ضد {f['competitor'][:40]}: سعر مرصود "
                     f"{f['observed_price']} — هامشك عند المضاهاة "
                     f"{f['margin_at_match_pct']}% وعند البيع أقل 10% "
                     f"{f['margin_at_10pct_below']}%")
        for t in cp.get("competitor_threads") or []:
            if not t.get("observed_price"):
                # خيوط بحث الويب مراجع لا كيانات (إصلاح مراجعة Stage 5، ثغرة ٢).
                L.append(f"  مرجع ويب للمراجعة: {t['name'][:40]} — "
                         f"{t['price_flag']} "
                         f"(اكتمال الخيط {t['thread_completeness']})")
    else:
        L.append(f"  {cp.get('note')}")
    L.append("─" * 60)
    L.append("الأسواق (الأفضل أولاً):")
    for i, m in enumerate(view["markets"], 1):
        L.append(f"  {i:>2}. {m['country']:<22} score={m['score']:.3f} "
                 f"conf={m['confidence']} ({m['components_present']})")
    if view.get("limits"):
        L.append("حدود هذا التقرير:")
        L += [f"  - {x}" for x in view["limits"][:6]]
    L += ["المختصر:", *(f"  {x}" for x in view["brief"]), "═" * 60]
    return "\n".join(L)
