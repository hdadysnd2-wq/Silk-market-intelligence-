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

import json
import logging
import os
import re

log = logging.getLogger(__name__)


def _dp(obj: object) -> dict:
    """طبّع DataPoint/dict — normalize a DataPoint or dict to a plain dict."""
    if isinstance(obj, dict):
        return obj
    return {"value": getattr(obj, "value", None),
            "source": getattr(obj, "source", ""),
            "confidence": getattr(obj, "confidence", 0.0),
            "note": getattr(obj, "note", ""),
            "retrieved_at": getattr(obj, "retrieved_at", ""),
            "status": getattr(obj, "status", "")}


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
    # أسماء أصناف الوكلاء الداخلية (TradeFlowAgent...) لا تصل وجه المستخدم —
    # تُعرَّب في المصدر هنا كي يرث كل مستهلك (نص/docx/markdown) الترجمة
    # نفسها، بدل ترقيعها في مستهلك واحد فقط (كانت docx وحدها تُعرِّبها).
    from silk_narrative import internal_ar
    gaps_ar = ", ".join(internal_ar(g) for g in jury.get("data_gaps", [])) or "لا شيء"
    why = (ai.get("reasoning")
           or f"تغطية الوكلاء {jury.get('agents_with_data', 0)}/"
              f"{jury.get('agents_total', 0)} وفجوات: {gaps_ar}")
    return {"verdict": verdict, "confidence": confidence,
            "why": (why or "")[:280], "market": top.get("country"),
            "stage": jury.get("synthesis_stage"),
            # سدّ تسريب (الطبقة ٦): تصنيف الشارة محسوب هنا — لوحة الويب
            # تستهلكه بدل حساب تصنيفها الخاص من الرمز الخام (نفس الإصلاح
            # المطبَّق على شارة البحث العميق).
            "tone": _verdict_tone(verdict)}


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
    """المختصر — سطران للموقع التنافسي فوق سطر القرار (vision §6, §10.4).

    P1 (طبقة السرد): رمز الحكم الآلي (CONDITIONAL-GO) والكسر العشري الخام
    وأسماء أعلام الكود (with_localprice) لا تصل وجه المستخدم — تُترجم عبر
    silk_narrative. القيم نفسها بلا تغيير.
    """
    import silk_narrative as N
    market = N.country_ar(decision.get("market"), decision.get("market"))
    lines = [f"التوصية: {N.verdict_ar(decision.get('verdict'))} — "
             f"سوق {market} (ثقة {N.confidence_phrase(decision.get('confidence'))})"]
    if cp.get("available"):
        best = cp.get("nearest_beatable")
        lines.append(
            f"أقرب منافس قابل للمنافسة: {best['competitor']} — هامشك عند "
            f"مضاهاته {best['margin_at_match_pct']}%" if best else
            "أسعار المنافسين على الرفّ لم تُجمع بعد — تتوافر مع الدراسة العميقة")
        door = cp.get("best_door")
        lines.append(f"أفضل باب دخول مرصود: {door['name']} ({door['assessment']})"
                     if door else "قنوات الدخول التفصيلية تتوافر مع الدراسة العميقة")
    else:
        lines.append(cp.get("note", ""))
    return lines


def _deep_research_brief(dr_view: dict) -> list[str]:
    """مختصر البحث العميق — القرار + أرقام حاسمة + الموقع التنافسي (الموجة ٤).

    نفس فلسفة `_brief` (§10.4: سطر جوال) لكن على شكل view["deep_research"]
    (١٢ بعثة + محلل، لا قائمة أسواق مرتّبة)."""
    from silk_narrative import verdict_ar
    verdict = dr_view.get("verdict") or {}
    ai = verdict.get("ai") or {}
    v_raw = ai.get("verdict") or verdict.get("verdict")
    v = verdict_ar(v_raw) if v_raw else "تعذّر إصدار توصية"
    market = ((dr_view.get("market") or {}).get("name_ar")
             or (dr_view.get("market") or {}).get("name_en") or "؟")
    lines = [f"التوصية: {v} — سوق {market} (بحث عميق شامل)"]
    demand = (dr_view.get("analyst") or {}).get("by_category", {}).get("demand") or []
    if demand:
        lines.append(f"الطلب الفعلي المقدَّر: {demand[0].get('value')}")
    entry_door = (dr_view.get("analyst") or {}).get("by_category", {}).get(
        "entry_door") or []
    if entry_door:
        lines.append(f"أفضل باب دخول: {entry_door[0].get('value')}")
    if dr_view.get("next_step"):
        lines.append(dr_view["next_step"])
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
    """روابطُ بحثِ الويب الخام — raw web headlines (fallback only, links kept as citations)."""
    out = []
    for v in _real_list(result.get("websearch")):
        if isinstance(v, dict):
            title = v.get("title") or v.get("snippet")
            if title:
                out.append({"title": str(title), "link": v.get("link")})
        elif v:
            out.append({"title": str(v), "link": None})
    return out


def _consumer_culture(result: dict) -> dict:
    """ثقافةُ المستهلك المستخلَصة — Layer-3 extracted insights over the raw headlines.

    بلاغ المالك «ترسل روابط = أنت قوقل»: القسم يعرض رؤًى مبنيّة (كلود) لا روابطَ خام.
    يعيد {"insights":[{point, evidence}], "note", "raw": [عناوين للاستشهاد]}. إن غاب
    الاستخلاص (بلا مفتاح كلود) يبقى raw فقط ويُعلَن أنه لم يُحلَّل بعد — لا يُدَّعى تحليلٌ.
    """
    cc = result.get("consumer_culture")
    raw = _culture(result)
    if isinstance(cc, dict) and cc.get("insights"):
        return {"insights": _sanitize_points(cc.get("insights")),
                "note": _strip_internal_plumbing(cc.get("note", "")),
                "grounded": True, "raw": raw}
    return {"insights": [], "note": "", "grounded": False, "raw": raw}


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
    elif sec == "pricing":
        for f in _SECTION_FIELDS.get(sec, ()):
            _walk_dps(row.get(f), dps)
        # إصلاح مراجعة المالك («هل الوكلاء يعملون؟»): الطبقة الحدودية المجانية
        # لوكيل pricing (border_unit_value_usd_kg من كومتريد، §4b) كانت تُحسب
        # فعلاً لكن لا تُقرأ هنا أبداً — فتُعرض «تسعير 0/0» رغم نجاح الوكيل،
        # بنفس علّة قسم trend المُصلَحة أعلاه (تعليق سطر ٢٢٢). "prices"/
        # "localprice" وحدهما (طبقة التجزئة المدفوعة) لا يكفيان على المسار
        # المجاني إذ يبقيان فارغَين بنيوياً خارج /deepen.
        research = row.get("research") or {}
        pricing_agent = (research.get("agents") or {}).get("pricing") or {}
        _walk_dps(pricing_agent.get("findings"), dps)
    else:
        for f in _SECTION_FIELDS.get(sec, ()):
            _walk_dps(row.get(f), dps)
    return dps


def _walk_dps(obj, out):
    """اجمع كل نقاط البيانات (dict أو DataPoint) — collect every datapoint-shaped node.

    إصلاح مراجعة التشغيل الحي: اكتشافات حزمة البحث (Stage 3، §4b) تحمل
    `sources[]` جمعاً لا `source` مفرداً فتغيب عن ملحق الأثر الإجمالي —
    Serper/Maps/مرآة السعودية كانت تُسهم فعلياً دون أن يظهر ذلك في الملحق.
    كل مصدر في sources[] يُسجَّل هنا مساهماً بقيمة الاكتشاف نفسها (المخطط
    يفرض sources غير فارغة فقط عند نجاح القيمة). محاولات §4b الفاشلة تبقى
    نصاً حراً في gaps[] لا نقاط بيانات مفردة — تُقرأ من قسم الفجوات مباشرة
    لا من هذا الملحق (قيد معروف، لا فشل صامتاً داخل قسمها الخاص).
    """
    if isinstance(obj, dict):
        if "source" in obj and "value" in obj:
            out.append(obj)
        elif "metric" in obj and isinstance(obj.get("sources"), list):
            for s in obj["sources"]:
                if isinstance(s, dict) and s.get("source"):
                    out.append({"source": s["source"], "value": obj.get("value"),
                               "note": obj.get("note", "")})
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
            # سدّ تسريب: ملاحظة DataPoint فاشلة خام (مثل "PV.EST fetch
            # failed for CHN: HTTPSConnectionPool(...)") كانت تصل ملحق
            # الأثر — أضمن ملحق ظهوراً بنيوياً (كل DataPoint فاشل في شجرة
            # النتيجة كلها يمرّ هنا) فتُعرَّب عند الجمع لا عند كل مستهلك.
            failure = _strip_internal_plumbing(str(d.get("note")))
            b["failures"].append(failure[:140])
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
    from silk_narrative import internal_ar
    S, W, O, T = [], [], [], []
    if not research or not research.get("agents"):
        return {"S": S, "W": W, "O": O, "T": T,
                "note": "يتطلب حزمة وكلاء البحث (with_research)"}
    sau = _rmetric(research, "competitor", "saudi_share_pct")
    if sau:
        S.append({"text": f"حضور سعودي قائم بحصة {sau}% من واردات السوق",
                  "evidence": f"UN Comtrade — {internal_ar('saudi_share_pct')}"})
    uv = _rmetric(research, "pricing", "border_unit_value_usd_kg")
    suv = _rmetric(research, "pricing", "saudi_border_unit_value_usd_kg")
    if uv and suv and suv <= uv:
        S.append({"text": f"سعر حدودي سعودي منافس ({suv}$ مقابل متوسط {uv}$/kg)",
                  "evidence": "UN Comtrade — قيم الوحدة"})
    for g in (research.get("agents", {}).get("pricing", {}).get("gaps") or []):
        if "بطاقة" in g or "margin" in g:
            W.append({"text": "الهامش غير محسوب — بطاقة المنتج غير مكتملة",
                      "evidence": _humanize_gap_note(g[:120])})
            break
    gate = _rmetric(research, "regulatory", "eligibility_gate")
    if gate:
        W.append({"text": "بوابة أهلية أوروبية مفتوحة (منشأة معتمدة EU 2017/625)",
                  "evidence": f"مرجع L1 — {internal_ar('eligibility_gate')}"})
    cagr = _rmetric(research, "market_size", "import_cagr_pct")
    if cagr is not None and cagr > 5:
        O.append({"text": f"واردات السوق تنمو {cagr}% سنوياً مركّباً",
                  "evidence": f"UN Comtrade — {internal_ar('import_cagr_pct')}"})
    hhi = _rmetric(research, "competitor", "hhi")
    if hhi is not None and hhi < 0.15:
        O.append({"text": f"سوق مفتّت (HHI {hhi}) — لا مورّد مهيمناً",
                  "evidence": f"UN Comtrade — {internal_ar('hhi')}"})
    rr = _rmetric(research, "consumer_demand", "ramadan_seasonality")
    if rr and "مرجّحة" in str(rr):
        O.append({"text": "موسمية رمضان/العيدين فرصة ذروة طلب",
                  "evidence": "قاعدة معلنة فوق مرجع Pew"})
    top = _rmetric(research, "competitor", "top_supplier_share_pct")
    if top is not None and top > 50:
        T.append({"text": f"مورّد مهيمن بحصة {top}% — حرب أسعار محتملة",
                  "evidence": f"UN Comtrade — {internal_ar('top_supplier_share_pct')}"})
    tariff = _rmetric(research, "regulatory", "tariff_applied_pct")
    if tariff is not None and tariff > 10:
        T.append({"text": f"تعريفة مطبّقة مرتفعة {tariff}%",
                  "evidence": f"WITS — {internal_ar('tariff_applied_pct')}"})
    fx = _rmetric(research, "risk", "fx_volatility_pct")
    if fx is not None and fx > 5:
        T.append({"text": f"تقلب عملة {fx}% (معامل اختلاف)",
                  "evidence": f"World Bank — {internal_ar('PA.NUS.FCRF')}"})
    if _rmetric(research, "risk", "critical_risk"):
        T.append({"text": "خطر سياسي حرج (WGI دون −1.5)",
                  "evidence": f"World Bank — {internal_ar('PV.EST')}"})
    return {"S": S, "W": W, "O": O, "T": T,
            "note": "خلايا مشتقة من الحقائق المتاحة — الخلية الفارغة تعني "
                    "غياب البيانات، لا سلامة الجانب"}


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
            # بلا كسر ثقة خام ولا اسم مسار API داخلي على وجه التقرير
            # (تسريب سباكة): الشارة الثلاثية بدل "(ثقة 0.4)"، و«خدمة
            # التعميق المدفوعة» بدل "/deepen".
            "note": "مرشّحون غير موثَّقين (○ غير متحقق) — أكّدهم قبل "
                    "التعاقد؛ الترقية الموثّقة عبر خدمة التعميق المدفوعة"}


def _report_fields(rep: object) -> dict:
    """طبّع AgentReport/dict — a live AgentReport dataclass OR a dict reloaded
    from storage (json_blob)، نفس نمط `_dp` أعلاه."""
    if isinstance(rep, dict):
        return {"agent_name": rep.get("agent_name"),
               "findings": rep.get("findings") or [],
               "failed": bool(rep.get("failed")), "summary": rep.get("summary") or ""}
    return {"agent_name": getattr(rep, "agent_name", None),
           "findings": getattr(rep, "findings", None) or [],
           "failed": bool(getattr(rep, "failed", False)),
           "summary": getattr(rep, "summary", "") or ""}


_TOOL_CALLS_RE = re.compile(r"نداءات أدوات:\s*(\d+)")
_DROPPED_RE = re.compile(r"أُسقطت\s*(\d+)\s*بند")
_GAPS_RE = re.compile(r"فجوات:\s*([^|]*)")

# بلاغ منتج من المالك: التقرير المعروض للعميل كان يكشف السباكة الداخلية
# ("LLMAgent:tariffs_agreements"، وسوم استشهاد خام مثل "dp7") — كلود
# (الكاتب أو بعثة) يستشهد أحياناً حرفياً بوسوم رآها في مدخلاته الخام بدل
# تلخيصها بلغة تجارية. الإصلاح تطبيع حتمي في طبقة العرض، لا تعديل على
# الأرقام: راجع _mission_label/_strip_internal_plumbing تحت.
_INTERNAL_AGENT_RE = re.compile(r"LLM(?:Mission)?Agent:([A-Za-z_]+)")
_DP_TAG_RE = re.compile(r"\[?dp\d+\]?")
_WHOLE_JSON_RE = re.compile(r"^\s*[{\[].*[}\]]\s*$", re.S)
# تسريب حقول داخلية إنجليزية في نص معروض (بلاغ مالك: "verdict" و
# "confidence 0.64" وصلا جدولاً في متن تقرير العميل) — الكاتب يردّد أحياناً
# أسماء حقول رآها في مدخلاته. القيمة العشرية بعد confidence تُصاغ بشرياً
# (confidence_phrase) والوسمان يُعرَّبان؛ لا تعديل على أي رقم آخر.
# سدّ تسريب (الطبقة ٥): الفاصل الأصلي [|:：] يطابق خلية جدول ("| confidence
# | 0.64 |") لكن ليس نثراً حرّاً بفاصلة فراغ ("confidence 0.64") — الشكل
# الذي ظهر فعلياً في جواب الدردشة السياقية الحرّ (سطح جديد لهذا المُطهِّر).
_EN_CONF_VALUE_RE = re.compile(r"\bconfidence\b(\s*[|:：]?\s*)(\d?\.\d{1,4})")
_EN_FIELD_RE = re.compile(r"\b(verdict|confidence)\b")
_EN_FIELD_AR = {"verdict": "الحكم", "confidence": "درجة الثقة"}
# رمز حكم آلة خام (GO/WATCH/NO-GO/CONDITIONAL-GO) داخل نثر حرّ كتبه الكاتب
# نفسه (بلاغ اختبار: "الحكم WATCH — مراقبة قبل الدخول مبني على...") — لا
# حقل مُهيكَل يلتقطه verdict_ar عند مصدره هنا، فالتقاط نصّي مباشر داخل
# السرد. الأطول أولاً (CONDITIONAL-GO/NO-GO قبل GO المجرّدة) كي لا يتبقّى
# "-GO" يتيماً بعد الاستبدال.
_RAW_VERDICT_RE = re.compile(r"\b(CONDITIONAL-GO|NO-GO|GO|WATCH)\b")


def _strip_raw_json_leak(text: str | None) -> str | None:
    """استبدل نصاً هو بالكامل تفريغ JSON خام بنص عربي مقروء — بلاغ حي
    (بعثة risk_news أعادت `{"claim": "..."}` حرفياً كملخّص حين فشل
    `silk_llm_runtime._parse_output` تفسير ردّها كاملاً). يستخرج قيمة
    مفتاح شائع (claim/summary/value/note) إن أمكن، وإلا يُصرَّح بالفجوة
    صراحة بدل عرض بنية JSON خام. نص عادي لا يشبه JSON يمر كما هو."""
    if not text or not _WHOLE_JSON_RE.match(text):
        return text
    try:
        obj = json.loads(text)
    except Exception:  # noqa: BLE001 — تفريغ مشوَّه أيضاً غير قابل للعرض خاماً
        return "تعذّر تفسير رد كلود لهذا البند — بيانات غير مقروءة"
    if isinstance(obj, dict):
        for key in ("claim", "summary", "value", "note"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return "تعذّر تفسير رد كلود لهذا البند — بيانات غير مقروءة"


def _mission_label(key: str) -> str:
    """اسم البعثة التجاري بالعربية — نفس الاسم الذي تعرضه لوحة إعدادات
    الوكلاء (silk_missions.MISSIONS[key]['name']) بدل المفتاح snake_case
    الخام أو agent_name الداخلي ("LLMAgent:<key>")."""
    try:
        from silk_missions import MISSIONS
        row = MISSIONS.get(key)
        if row and row.get("name"):
            return row["name"]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط عرض
        pass
    return key.replace("_", " ")


def _category_label(key: str) -> str:
    """اسم تقاطع المحلل الشامل التجاري بالعربية — نفس معجم
    silk_market_analyst._CATEGORY_LABELS المستعمَل في بوابة الجودة
    (silk_quality_gate._check_intersection_insufficiency)، بدل مفتاح
    إنجليزي خام ("entry_cost") في حدّ معروض للعميل."""
    try:
        from silk_market_analyst import _CATEGORY_LABELS
        if key in _CATEGORY_LABELS:
            return _CATEGORY_LABELS[key]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط عرض
        pass
    return key.replace("_", " ")


def _humanize_gap_note(text: object) -> str:
    """عرّب ملاحظات الحُرّاس/الفجوات الداخلية في سطر حدّ معروض للعميل —
    تفويض للمترجم القانوني الواحد (silk_narrative.translate_gaps /
    INTERNAL_AR): العقود الإنجليزية تبقى كما هي في طبقة البيانات؛
    الترجمة للعرض فقط، لا إعادة صياغة ولا مسّ بالأرقام."""
    from silk_narrative import translate_gaps
    return translate_gaps([text])[0]


_MISSION_KEY_PREFIX_RE = re.compile(r"^([a-z][a-z_]*)(:\s*)")


def _strip_mission_key_prefix(text: str) -> str:
    """بادئة مفتاح بعثة خام أول السطر ("pricing_scout: ...") → الاسم
    التجاري العربي — بلاغ تدقيق: انهيار خيط بعثة يبني الملخّص بـ
    `f"{key}: خطأ غير متوقع: ..."` (silk_missions.py) وهذه البادئة لا
    يلتقطها `_INTERNAL_AGENT_RE` (يطابق "LLMAgent:key" فقط، لا "key:" مجرّدة)."""
    m = _MISSION_KEY_PREFIX_RE.match(text)
    if not m:
        return text
    try:
        from silk_missions import MISSIONS
        if m.group(1) in MISSIONS:
            return _mission_label(m.group(1)) + m.group(2) + text[m.end():]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط عرض
        pass
    return text


def _strip_internal_plumbing(text: str | None) -> str | None:
    """أزل تسريبات السباكة الداخلية من نص معروض للعميل (تقرير مكتوب/حدود
    بحث/ملخّص بعثة) — تفريغ JSON خام كامل يُستبدَل بنص مقروء أو فجوة
    معلنة (`_strip_raw_json_leak`)، "LLMAgent:<key>"/"LLMMissionAgent:
    <key>" وبادئة "<key>: " المجرّدة تُستبدَلان باسم البعثة العربي، ووسوم
    استشهاد خام "dp7"/"[dp7]" تُحذَف، وأسماء الحقول الداخلية الإنجليزية
    (verdict/confidence مع قيمتها العشرية الخامة) تُعرَّب وتُصاغ بشرياً،
    ثم يمرّ النص على `silk_narrative.humanize_technical_note` (نقطة
    التعريب المركزية) لالتقاط أي استثناء بايثون/خطأ HTTP/قالب مصدر متبقٍّ
    لم تلتقطه الأنماط أعلاه. None/فارغ يمر كما هو."""
    if not text:
        return text
    text = _strip_raw_json_leak(text)
    text = _strip_mission_key_prefix(text)
    text = _INTERNAL_AGENT_RE.sub(lambda m: _mission_label(m.group(1)), text)
    text = _DP_TAG_RE.sub("", text)

    def _conf_value(m: "re.Match") -> str:
        from silk_narrative import confidence_phrase
        return f"درجة الثقة{m.group(1)}{confidence_phrase(float(m.group(2)))}"
    text = _EN_CONF_VALUE_RE.sub(_conf_value, text)
    text = _EN_FIELD_RE.sub(lambda m: _EN_FIELD_AR[m.group(1)], text)
    from silk_narrative import humanize_technical_note, verdict_ar
    text = _RAW_VERDICT_RE.sub(lambda m: verdict_ar(m.group(1)), text)
    text = humanize_technical_note(text)
    return re.sub(r"[ \t]{2,}", " ", text)


def _sanitize_points(items: list, extra_key: str | None = None) -> list:
    """طهّر قائمة {point, evidence, [extra_key]} — استخلاصات كلود الحرّة
    (ثقافة المستهلك P1، ديناميكيات السوق P2-8) لم تكن تمرّ عبر
    `_strip_internal_plumbing` إطلاقاً رغم أنها نفس نوع النص الحرّ الذي
    قد يردّد وسماً داخلياً رآه كلود في مدخلاته (تسريب تدقيق). `evidence`
    عناوين ويب خارجية مقتبَسة حرفياً — لا تُعدَّل، ليست سباكة داخلية."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        if "point" in row:
            row["point"] = _strip_internal_plumbing(row.get("point"))
        if extra_key and extra_key in row:
            row[extra_key] = _strip_internal_plumbing(row.get(extra_key))
        out.append(row)
    return out


def _sanitized_dynamics(dynamics: object) -> dict | None:
    """ديناميكيات السوق (P2-8، `silk_ai_judge.classify_dynamics`) مطهَّرة —
    نفس القصور الذي كان في _consumer_culture: قوائم point/evidence حرّة لم
    تمرّ عبر `_strip_internal_plumbing` قط في هذا المسار."""
    if dynamics is None:
        return None
    d = _dp(dynamics)
    v = d.get("value")
    if isinstance(v, dict):
        v = dict(v)
        for key in ("drivers", "restraints", "opportunities", "threats"):
            if key in v:
                v[key] = _sanitize_points(v.get(key))
        if "porter" in v:
            v["porter"] = _sanitize_points(v.get("porter"), extra_key="force")
        if "pestel" in v:
            v["pestel"] = _sanitize_points(v.get("pestel"), extra_key="dimension")
        if v.get("note"):
            v["note"] = _strip_internal_plumbing(v["note"])
        d = {**d, "value": v}
    return d


def _mission_trace_summary(failed: bool, summary: str) -> dict:
    """لوحة تتبّع بلمحة (الموجة ٦، §docs/TUNING.md) — حالة/نداءات أداة/
    بنود مُسقَطة/فجوات، مُستخرَجة من نص ملخّص البعثة (لا تمديد على عقد
    AgentReport — راجع تعليق التصميم في silk_llm_runtime.run_llm_agent)."""
    skipped = "معطّل" in summary
    status = "skipped" if skipped else ("failed" if failed else "succeeded")
    tool_m = _TOOL_CALLS_RE.search(summary)
    dropped_m = _DROPPED_RE.search(summary)
    gaps_m = _GAPS_RE.search(summary)
    gaps_n = len([g for g in (gaps_m.group(1).split("؛") if gaps_m else [])
                 if g.strip()])
    return {"status": status, "tool_calls": int(tool_m.group(1)) if tool_m else 0,
           "dropped": int(dropped_m.group(1)) if dropped_m else 0,
           "gaps": gaps_n}


def _mission_gap_lines(name: str, summary: str) -> list[str]:
    """فجوات بعثة معلنة داخل ملخّصها — كل بعثة، لا الفاشلة (صفر نتائج) فقط.

    بعثة قد "تنجح" (نتائج مبنية على استشهاد ≥١) وتُصرّح بفجوات جزئية داخل
    نفس الملخّص («فجوات: لا بيانات أسعار؛ لا بيانات مخاطر») — كانت هذه
    الفجوات غير مرئية لقسم «حدود التقرير» لأن التجميع القديم فحص `failed`
    فقط. إصلاح مراجعة حية: أي فجوة مُعلَنة في أي مكان يجب أن تظهر هنا.
    """
    m = _GAPS_RE.search(summary or "")
    if not m:
        return []
    return [f"{name}: {g.strip()}" for g in m.group(1).split("؛") if g.strip()]


# تصنيف لون/تسمية شارة الحكم — مصدر واحد يستهلكه ثلاثة عارضين (لوحة
# الويب، غلاف docx، خلاصة docx التنفيذية) بدل تكرار نفس المنطق بايثون +
# JS بمعيارين قد يختلفان لنفس الرمز (سدّ تسريب الطبقة ٦: كانت لوحة الويب
# تحسب تصنيفها الخاص من رمز الحكم الإنجليزي الخام وتعرض الرمز نفسه كنص
# ظاهر — silk_reports._verdict_tone/_VERDICT_LABELS_AR كانتا نسخة موازية).
def _verdict_tone(vtxt: object) -> str:
    """تصنيف لون شارة الحكم — go (أخضر)/conditional (مشروط، أخضر مزرقّ)/
    watch (كهرماني)/nogo (أحمر)/unknown (رمادي).

    بلاغ حي (مراجعة المالك على نموذج تقرير العميل): CONDITIONAL-GO كان
    ينهار إلى tone=watch فتعرض الشارة «مراقبة السوق» بينما متن التقرير
    يقول «دخول مشروط» — تناقض على الصفحة الأولى. صار للحكم المشروط tone
    مستقل بتسميته الخاصة («دخول مشروط»، مطابقة لـsilk_narrative.VERDICT_AR)
    فتتّفق الشارة مع المتن. CONDITIONAL قبل GO (يحوي الرمز كليهما) وقبل
    WATCH (لا يحوي WATCH أصلاً)."""
    t = str(vtxt or "").upper()
    if "NO-GO" in t or "NO GO" in t:
        return "nogo"
    if "CONDITIONAL" in t:
        return "conditional"
    if "WATCH" in t:
        return "watch"
    if "GO" in t:
        return "go"
    return "unknown"


# تسميات الحكم بالعربية مصنَّفةً بالـtone — مطابقة لـsilk_narrative.VERDICT_AR
# (المترجم القانوني الواحد): conditional=«دخول مشروط» تحديداً، لا «مراقبة
# السوق» (بلاغ مراجعة المالك: الشارة كانت تخالف المتن).
_VERDICT_LABELS_AR = {"go": "التوصية بالدخول", "conditional": "دخول مشروط",
                      "watch": "مراقبة السوق", "nogo": "عدم الدخول حالياً",
                      "unknown": "تعذّر إصدار توصية"}


def _deep_research_view(result: dict) -> dict | None:
    """قسم البحث العميق (الموجة ٤، V5) — إضافي بحت، لا يمسّ أي مفتاح قائم.

    **تنبيه تسمية مهم**: هذا المفتاح `view["deep_research"]` مختلف تماماً عن
    `row["research"]` الموجود أصلاً (حزمة وكلاء البحث الثمانية الحتمية،
    Stage 3 §4b) — تعمّد اختيار اسم مختلف لتفادي تصادم دلالي، لا تكرار خطأ.
    None عند غياب `result["deep_research"]` (تحليل /analyze عادي — لا أثر).
    """
    dr = result.get("deep_research")
    if not dr:
        return None
    missions = {}
    for key, rep in (dr.get("missions") or {}).items():
        f = _report_fields(rep)
        # بلاغ حي (risk_news): بعثة قد تعيد JSON خام كملخّص عند فشل تفسير
        # ردّها (silk_llm_runtime._parse_output) — يُطبَّع هنا مرة واحدة
        # فيصل نظيفاً كل مستهلك (جدول الأدلة الخام، حدود البحث، ملخّص
        # التتبّع أدناه).
        clean_summary = _strip_internal_plumbing(f["summary"])
        missions[key] = {
            "name": f["agent_name"], "failed": f["failed"],
            # الاسم التجاري العربي للبعثة — كل مستهلك (جدول docx، لوحة
            # الويب، الملحق التقني) يعرضه بدل مفتاح snake_case الخام
            # (بلاغ مالك: "pricing_scout"/"risk_news" ظهرت حرفياً للعميل).
            "label": _mission_label(key),
            "summary": clean_summary,
            "findings": [_dp(x) for x in f["findings"]],
            "trace": _mission_trace_summary(f["failed"], clean_summary),
        }
    analyst = dr.get("analyst") or {}
    analyst_report = _report_fields(analyst.get("report"))
    # سدّ تسريب: ملخّص المحلل الشامل نص كلود حرّ فوق نفس الحقائق المعزولة
    # التي يقرأها ملخّص كل بعثة — كان الأخير وحده يمرّ عبر التطهير، تاركاً
    # ثغرة مطابقة (نفس نوع النص، لا سبب لتمييزه).
    analyst_report = {**analyst_report,
                      "summary": _strip_internal_plumbing(analyst_report["summary"])}
    # P2: شارة أدلة ثلاثية (✓/◐/○) محسوبة هنا مرة واحدة في النموذج القانوني —
    # لا رقم ثقة خام يصل الواجهة، ولا منطق تصنيف مكرَّر في JS العميل.
    from silk_narrative import evidence_badge
    # سدّ تسريب (الطبقة ٩): ملاحظة اكتشاف المحلل الشامل تحمل أحياناً وسم
    # تقاطع خام بادئاً ("[entry_cost] تعريفة مطبّقة") — وسم تصنيف داخلي
    # للمحلل نفسه، لا معلومة تفيد القارئ (التقاطع معروف أصلاً من عنوان
    # القسم الذي يُدرَج تحته). يُزال، لا يُترجَم — تكرار لا قيمة إضافية له.
    _cat_tag_re = re.compile(
        r"^\[(?:demand|price_competitiveness|entry_cost|entry_door|swot)\]\s*")
    def _with_badge(x):
        d = _dp(x)
        note = d.get("note")
        if isinstance(note, str) and _cat_tag_re.match(note):
            d = {**d, "note": _cat_tag_re.sub("", note)}
        return {**d, "confidence_badge": evidence_badge(d.get("confidence"))}
    by_category = {cat: [_with_badge(x) for x in (dps or [])]
                  for cat, dps in (analyst.get("by_category") or {}).items()}
    report_out = dr.get("report") or {}
    verdict = dr.get("verdict") or {}
    # سدّ تسريب (الطبقة ٦): تعليل حكم كلود (ai.reasoning) نص حرّ — قد يردّد
    # رمز حكم خام أو مصطلحاً داخلياً رآه في مدخلاته (نفس خطر ai.reasoning
    # المذكور في _stage2)، وكان يصل خاماً لكل من لوحة الويب وخلاصة docx
    # التنفيذية بلا أي مُطهِّر. تعقيم هنا مرة واحدة في النموذج القانوني —
    # بقية حقول verdict (الرمز الخام، الثقة) تبقى كما هي لأن تصنيف الشارة
    # (_verdict_tone) يحتاج الرمز الإنجليزي الخام تحديداً.
    if isinstance(verdict.get("ai"), dict) and verdict["ai"].get("reasoning"):
        verdict = {**verdict,
                  "ai": {**verdict["ai"],
                        "reasoning": _strip_internal_plumbing(
                            verdict["ai"]["reasoning"])}}
    # سدّ تسريب: ملاحظات المراجعة غير المحلولة نص كلود حرّ (المراجِع) —
    # كانت تصل limits وview["deep_research"]["report"] خامة تماماً؛ وسبب
    # فشل التقرير (failure_reason) يحمل تفصيل استثناء/HTTP خام متعمَّد
    # لأغراض تشخيص المطوّرين (silk_ai_judge.failure_reason) لكن كان يصل
    # العميل حرفياً بما فيه توجيه تشغيلي ("راجع سجلّات الخادم") — العقد
    # الخام يبقى في `report_out` كما هو؛ التطهير هنا للعرض فقط.
    clean_unresolved = [_strip_internal_plumbing(n)
                        for n in (report_out.get("unresolved_notes") or [])]
    clean_failure_reason = (_strip_internal_plumbing(report_out.get("failure_reason"))
                            if report_out.get("failure_reason") else "")
    # v["summary"] مُطبَّع أصلاً أعلاه (clean_summary) — لا حاجة لإعادة التنظيف.
    limits = ([f"فرصة {_mission_label(k)} بلا نتائج مبنية على استشهاد: "
              f"{v['summary']}"
              for k, v in missions.items() if v["failed"]]
             # فجوات جزئية داخل بعثات "ناجحة" (نتائج ≥١ لكن ببنود ناقصة
             # معلنة) — كانت هذه تُسقَط صامتة من حدود التقرير قبل هذا الإصلاح.
             + [g for k, v in missions.items()
               for g in _mission_gap_lines(_mission_label(k), v["summary"])]
             # سدّ تسريب (الطبقة ٩): مفتاح تقاطع خام إنجليزي ("entry_cost")
             # كان يصل حدّاً معروضاً للعميل حرفياً — الاسم التجاري العربي
             # (نفس معجم silk_market_analyst._CATEGORY_LABELS المستعمَل في
             # بوابة الجودة) يحل محله.
             + [f"تقاطع المحلل بلا أدلة كافية: {_category_label(c)}"
               for c in (analyst.get("missing_categories") or [])]
             + [f"ملاحظة مراجع لم تُعالَج: {n}" for n in clean_unresolved])
    if not report_out.get("report") and clean_failure_reason:
        limits.append(f"التقرير الكامل غائب: {clean_failure_reason}")
    if result.get("hs_resolution_note"):
        limits.append(f"تصنيف HS: {_humanize_gap_note(result['hs_resolution_note'])}")
    if result.get("ai_extras_note"):
        limits.append(f"طبقة كلود: {_humanize_gap_note(result['ai_extras_note'])}")
    if verdict.get("ai_note"):
        limits.append(f"حكم كلود (مرحلة ٢): "
                      f"{_strip_internal_plumbing(verdict['ai_note'])}")
    v_raw = (verdict.get("ai") or {}).get("verdict") or verdict.get("verdict") or ""
    verdict_tone = _verdict_tone(v_raw)
    return {
        "market": result.get("market"),
        "trace_id": dr.get("trace_id"),
        # لافتة التدهور (بلاغ حي، بوابة ما قبل التشغيل api.py) — تصل هنا كي
        # يحملها كل مشتق (docx/مختصر/طرفية/لوحة) لا سطر ملاحظة وحيد مدفون.
        "degraded": bool(result.get("degraded")),
        "degraded_reason": result.get("degraded_reason") or "",
        "missions": missions,
        "analyst": {"summary": analyst_report["summary"],
                   "missing_categories": analyst.get("missing_categories") or [],
                   "by_category": by_category},
        # سدّ تسريب (الطبقة ٦): تصنيف/تسمية الحكم مُحسَّبان هنا مرة واحدة —
        # لوحة الويب تستهلكهما بدل حساب تصنيفها الخاص من الرمز الخام
        # وعرض الرمز نفسه كنص ظاهر (كان "CONDITIONAL-GO"/"WATCH" يظهر
        # حرفياً على شارة الغلاف).
        "verdict_tone": verdict_tone,
        "verdict_label": _VERDICT_LABELS_AR[verdict_tone],
        "verdict": verdict,
        "report": {"text": _strip_internal_plumbing(report_out.get("report")),
                  "review_cycles": report_out.get("review_cycles", 0),
                  "unresolved_notes": clean_unresolved,
                  "failure_reason": clean_failure_reason},
        "limits": limits,
        "next_step": ("فعّل خدمة التعميق المدفوعة للتحقق من المستوردين "
                     "وجهات الاتصال (Volza/Explee)"
                     if str(verdict.get("verdict") or
                           (verdict.get("ai") or {}).get("verdict") or "")
                        .upper().startswith(("GO", "PRELIMINARY GO")) else None),
    }


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
        from silk_narrative import internal_ar
        gaps_ar = ("، ".join(internal_ar(g) for g in jury.get("data_gaps", []))
                  or "لا شيء")
        decision = {
            "verdict": ed_top.get("verdict"),
            "confidence": ed_top.get("confidence"),
            "score": ed_top.get("score"),
            "why": ed_top.get("why"),
            "market": (top or {}).get("country"),
            "stage": "silk.decision/v1 — المحرك الموزون §8 (الحكم الوحيد)",
            "sufficiency": (f"بوابة كفاية البيانات: {jury.get('agents_with_data', 0)}/"
                            f"{jury.get('agents_total', 0)} وكلاء أساسيون لديهم "
                            f"بيانات؛ فجوات: {gaps_ar}"),
            # سدّ تسريب (الطبقة ٦): نفس تصنيف الشارة المحسوب لمسار الجورية
            # الاحتياطي أعلاه — هذا الفرع (محرك §8) هو الشائع فعلياً.
            "tone": _verdict_tone(ed_top.get("verdict")),
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
                 # سدّ تسريب: ملاحظة DataPoint خام (نجاح إنجليزي مثل "HS…
                 # total World… USD" أو فشل يضمّ استثناء) لم تكن تمرّ عبر
                 # أي مُطهِّر رغم وصولها مباشرة لهذا الحقل في نموذج العرض
                 # القانوني — أي مستهلك مستقبلي (JSON خام، ودجت جديد) يرث
                 # النص المُعرَّب الآن، لا الخام.
                 "note": _strip_internal_plumbing(_dp(c).get("note", "")),
                 "status": _dp(c).get("status", "")}
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
    limits = [f"{m['country']}: {_humanize_gap_note(f)}" for m in markets[:5]
              for f in (m.get("quality_flags") or [])]
    if not result.get("classified"):
        limits.insert(0, _humanize_gap_note(result.get("hs_note"))
                     if result.get("hs_note") else "تعذّر التصنيف")
    # قسم البحث العميق (الموجة ٤، V5) — إضافي بحت؛ None لتحليل /analyze عادي.
    dr_view = _deep_research_view(result)
    if dr_view:
        limits = dr_view["limits"] + limits
    # ترويسة 2B: التغطية الإجمالية % = مُسهم/مُحاوَل عبر أقسام السوق الأعلى.
    top_cov = _section_coverage(markets[0]) if markets else {}
    att = sum(c["attempted"] for c in top_cov.values())
    con = sum(c["contributed"] for c in top_cov.values())
    dr_market = (dr_view or {}).get("market") or {}
    header = {
        "product": result.get("product"), "hs_code": result.get("hs_code"),
        "origin": "SAU",
        "target_market": ((markets[0].get("country") or markets[0].get("iso3"))
                          if markets else
                          (dr_market.get("name_ar") or dr_market.get("name_en"))),
        "date": _t_today(),
        "coverage_pct": round(100 * con / att, 1) if att else 0.0,
    }
    view = {
        # راية التشغيل البرهاني: العواذف تضبط SILK_HERMETIC — كل المشتقات تطبع
        # لافتة TEST RUN؛ وفي الإنتاج يرفض المولّد أي أثر برهاني (silk_reports).
        "test_run": bool(os.environ.get("SILK_HERMETIC")),
        # لافتة التدهور (بلاغ حي) — top-level لتظهر في كل مشتق يقرأ
        # view["degraded"] مباشرة، بلا حاجة لفتح deep_research أولاً.
        "degraded": bool((dr_view or {}).get("degraded")),
        "degraded_reason": (dr_view or {}).get("degraded_reason") or "",
        "header": header,
        "product": result.get("product"), "hs_code": result.get("hs_code"),
        "hs_confidence": result.get("hs_confidence"),
        "year": result.get("year"), "preliminary": True,
        "data_year": result.get("data_year", result.get("year")),
        "year_fell_back": bool(result.get("year_fell_back")),
        "classified": result.get("classified", False),
        "decision": decision,
        "dynamics": _sanitized_dynamics(result.get("dynamics")),
        "competitive_position": cp,
        "completeness": _completeness(markets),
        "markets": view_markets,
        "culture": _culture(result),          # روابط خام (تراجُع/استشهاد)
        "consumer_culture": _consumer_culture(result),  # ثقافة المستهلك المستخلَصة (كلود)
        "brief": (_deep_research_brief(dr_view) if dr_view
                 else _brief(decision, cp)),
        "limits": limits,
        "provenance": _provenance(result),   # Stage 2A: لا فشل صامتاً
        # اقتصاد البيانات (persist-5): عدّاد مرصود — مخزن/ذاكرة مقابل جلب حي.
        "data_economics": result.get("data_economics"),
        "note": result.get("note"),
        # التحليل الاحترافي (silk_ai_judge.ai_report) — يحلّ محل الخلاصة
        # الحتمية (exec_summary) في التقرير المصدَّر حين يتوفر؛ None = غياب
        # مفتاح/فشل النداء (ظاهر لا محذوف)، والقالب يرجع حينها لـ exec_summary.
        "ai_report": result.get("report"),
        "ai_report_note": result.get("report_note"),
        # الموجة ٤ (V5): مختلف عن row["research"] القائم — راجع تنبيه التسمية
        # أعلى _deep_research_view. None لتحليل /analyze العادي (لا أثر).
        "deep_research": dr_view,
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
    from silk_narrative import confidence_phrase, verdict_ar
    L += [f"رمز HS: {view['hs_code']} (ثقة {view['hs_confidence']}) | "
          f"سنة {view['year']} | مبدئي",
          f"القرار: {verdict_ar(d.get('verdict'))} "
          f"(ثقة {confidence_phrase(d.get('confidence'))}) — {d.get('market')}",
          f"لماذا: {d.get('why')}", "─" * 60]
    ed = (view.get("markets") or [{}])[0].get("entry_decision") or {}
    if ed.get("schema"):
        L.append(f"قرار الدخول (المحرك الموزون): {verdict_ar(ed.get('verdict'))} "
                 f"— النقاط {ed.get('score')} — الثقة "
                 f"{confidence_phrase(ed.get('confidence'))} — {ed.get('why')}")
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
    if (view.get("data_economics") or {}).get("note"):
        L.append(f"اقتصاد البيانات: {view['data_economics']['note']}")
    L += ["المختصر:", *(f"  {x}" for x in view["brief"]), "═" * 60]
    return "\n".join(L)


def analysis_context(result: dict, max_chars: int = 6000) -> str:
    """سياق نصي مضغوط لتحليل قائم (10b) — للدردشة السياقية فوق النتيجة.

    يقرأ نتيجة المحرّك المخزّنة حصراً — صفر شبكة، صفر إعادة تشغيل وكلاء.
    كل رقم يُذكر بمصدره؛ الفجوات تُذكر كما هي كي يجيب كلود «غير متوفر في
    هذا التحليل» بدل الاختلاق.
    """
    # سدّ تسريب: هذا السياق يُغذّى مباشرة لبرومبت الدردشة السياقية
    # (silk_ai_judge.answer_about_analysis) — كلود مُطالَب بالاستشهاد حرفياً
    # من هذا النص، فأي مفتاح داخلي خام هنا (اسم مكوّن snake_case، مفتاح وكيل)
    # قابل للظهور حرفياً في جواب يصل العميل مباشرة.
    from silk_narrative import internal_ar
    view = result.get("view") if isinstance(result.get("view"), dict) else None
    view = view or build_view(result)
    L: list[str] = []
    h = view.get("header") or {}
    L.append(f"المنتج: {h.get('product')} (HS {h.get('hs_code')}) — "
             f"السوق الأول: {h.get('target_market')} — سنة البيانات: "
             f"{view.get('data_year', view.get('year'))}")
    for b in view.get("brief") or []:
        L.append(f"الخلاصة: {b}")
    top = (view.get("markets") or [{}])[0]
    for c in top.get("components_detail") or []:
        name_ar = internal_ar(c.get("name"))
        if c.get("value") is not None:
            L.append(f"{name_ar} = {c['value']} [المصدر: {c.get('source')}]")
        else:
            why = ("تعذّر الجلب — أعد المحاولة"
                   if c.get("status") == "fetch_failed" else "غير متوفر")
            L.append(f"{name_ar}: {why}")
    for sc in (top.get("supplier_countries") or [])[:6]:
        L.append(f"مورّد: {sc.get('partner')} — حصة {sc.get('share')}% "
                 f"({sc.get('value_usd')}$) [UN Comtrade]")
    ag = ((top.get("research") or {}).get("agents")) or {}
    for k, a in ag.items():
        k_ar = internal_ar(k)
        for f in (a.get("findings") or [])[:4]:
            if f.get("value") is None or isinstance(f.get("value"),
                                                    (list, dict)):
                continue
            srcs = "، ".join(str(x.get("source")) for x in
                             (f.get("sources") or []) if isinstance(x, dict))
            L.append(f"{k_ar} — {internal_ar(f.get('metric'))} = {f['value']}"
                     f"{(' ' + f['unit']) if f.get('unit') else ''}"
                     f" [المصدر: {srcs or '؟'}]")
        for g in (a.get("gaps") or [])[:2]:
            L.append(f"فجوة {k_ar}: {_humanize_gap_note(g)}")
    ed = top.get("entry_decision") or {}
    for cnd in (ed.get("conditions") or [])[:4]:
        L.append(f"شرط مفتوح: {cnd}")
    for x in (view.get("limits") or [])[:6]:
        L.append(f"حدّ معلن: {x}")
    out = "\n".join(L)
    return out[:max_chars]
