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


# ── Stage 2A: تغطية المصادر لكل قسم + ملحق الأثر — coverage & provenance ──────

_SECTION_FIELDS = {
    "market_size": ("components",),                # سيُفصَّل داخلياً
    "regulatory": ("requirements", "tariff"),
    "competitors": ("competitors", "competitors_named", "maps"),
    "pricing": ("prices", "localprice"),
    "demand": ("faostat", "trends"),
    "risk": ("risk",),
    "trend": ("trend",),
}


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
    for section, fields in _SECTION_FIELDS.items():
        dps: list[dict] = []
        if section == "market_size":
            comps = row.get("components") or {}
            for k in ("market_size", "saudi_position", "competition"):
                if k in comps:
                    _walk_dps(comps[k], dps)
        elif section == "demand":
            comps = row.get("components") or {}
            if "demand_capacity" in comps:
                _walk_dps(comps["demand_capacity"], dps)
            for f in fields:
                _walk_dps(row.get(f), dps)
        else:
            for f in fields:
                _walk_dps(row.get(f), dps)
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


def build_view(result: dict) -> dict:
    """ابنِ نموذج العرض القانوني — the ONE canonical view-model (vision §10.1).

    كل المخرجات (لوحة/طرفية/Streamlit/مختصر) تشتق من هذا النموذج حصراً.
    """
    markets = result.get("markets") or []
    top = markets[0] if markets else None
    decision = _decision(top)
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
        })
    limits = [f"{m['country']}: {f}" for m in markets[:5]
              for f in (m.get("quality_flags") or [])]
    if not result.get("classified"):
        limits.insert(0, result.get("hs_note") or "تعذّر التصنيف")
    view = {
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
    L = ["═" * 60, f"المنتج / Product : {view.get('product')}"]
    if not view.get("classified"):
        L += ["الحالة: تعذّر التصنيف — could not classify",
              *(f"  حد: {x}" for x in view.get("limits", [])[:3]), "═" * 60]
        return "\n".join(L)
    d = view["decision"]
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
                L.append(f"  {t['name'][:40]}: {t['price_flag']} "
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
