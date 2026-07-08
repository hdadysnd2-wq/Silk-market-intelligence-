"""مشتقا التقارير لسِلك — Silk report derivatives (wave 5c, vision §10.3-§10.4).

مشتقان جديدان من القالب الموحّد (`silk_render.build_view`) — لا مسار عرض
مستقلاً جديداً، بل اشتقاقان فوق النموذج القانوني نفسه:

  - **التقرير الكامل (Word)** — §10.3: الخلاصة التنفيذية أولاً، ثم
    "موقعك التنافسي"، ثم الأسواق **بسطر مصدر تحت كل رقم** (مبني في القالب
    نفسه — `components_detail` — فيستحيل بنيوياً رقم بلا نسب)، ثم قسم
    **"حدود هذا التقرير" قبل التوصيات**.
  - **المختصر** — §10.4: منتج مختلف لا نسخة مصغرة — صفحة "رسالة جوال":
    القرار + ٣ أرقام حاسمة + سطرا الموقع التنافسي + إحالة اللوحة.

python-docx تبعية اختيارية: غيابها = RuntimeError واضحة (الاستيراد كسول)،
والمختصر نصّ خالص يعمل دوماً. صفر شبكة، صفر تعديل أرقام — عرض صرف.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_DOCX_HINT = "python-docx غير مثبتة — pip install python-docx"

# آثار برهانية لا يجوز أن تبلغ تقرير إنتاج أبداً — hermetic-only markers.
_HERMETIC_MARKERS = ("MagicMock", "example.org", "hermetic", "demo double",
                     "بدائل موسومة")


def _assert_production_clean(view: dict) -> None:
    """حارس الإنتاج (إصلاح مراجعة Stage 5): أي أثر برهاني في تشغيلة غير موسومة
    SILK_HERMETIC = رفض توليد التقرير بصوت عالٍ — لا تقرير مسموماً بصمت.
    التشغيلات البرهانية الموسومة تمرّ وتحمل لافتة TEST RUN الظاهرة بدلاً من ذلك.
    """
    import os as _os
    if _os.environ.get("SILK_HERMETIC") or view.get("test_run"):
        return
    import json as _json
    blob = _json.dumps(view, ensure_ascii=False, default=str)
    for marker in _HERMETIC_MARKERS:
        if marker in blob:
            raise RuntimeError(
                f"hermetic artifact '{marker}' found in a production report "
                "view — رفض التوليد: أثر برهاني في تقرير إنتاجي (اضبط "
                "SILK_HERMETIC=1 للتشغيلات البرهانية)")


def _fmt(v: object) -> str:
    """تنسيق قيمة للعرض — display formatting (None = فجوة معلنة)."""
    if v is None:
        return "— (لا بيانات)"
    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 1000:
        return f"{v:,.0f}"
    return str(v)


def _data_year_label(view: dict) -> str:
    """سنة البيانات الفعلية — the year actually used, flagging the declared fallback.

    عند تراجُع المحرّك إلى أحدث سنةٍ منشورة (السنة المطلوبة لم تُنشر بعد) نعرض السنة
    الفعلية مع سبب التراجُع — لا يظهر رقمُ سنةٍ فارغةٍ كأنه سنة التحليل.
    """
    dy = view.get("data_year", view.get("year"))
    if view.get("year_fell_back") and dy != view.get("year"):
        return f"{dy} (أحدث سنة منشورة؛ {view.get('year')} لم تُنشر بعد)"
    return str(dy)


# ── مساعدو حزمة البحث وقرار الدخول (§7) — research/decision display helpers ──
# عرض صرف فوق view.markets[i]: لا شبكة، لا تعديل أرقام، الفجوات تُعلن بنصّها.
# Pure display over the canonical view; gaps are declared verbatim, never filled.

_MODELED_TAG = "مُقدَّر — نموذج بافتراضات معلنة"

_PILLAR_AR = {"market": "جاذبية السوق", "competition": "المنافسة",
              "regulatory": "التنظيم", "profit": "الربحية",
              "risk": "أمان السوق (المخاطر)"}

_SEC_AR = {"market_size": "حجم السوق والمنافسة", "demand": "الطلب والقدرة",
           "regulatory": "الاشتراطات والتعريفة", "competitors": "المنافسون بالاسم",
           "pricing": "الأسعار", "risk": "المخاطر", "trend": "الاتجاه"}


def _research_bundle(m: dict) -> tuple[dict | None, str]:
    """حزمة البحث أو غيابها المعلّل — the research bundle, or a declared absence."""
    r = (m or {}).get("research")
    if isinstance(r, dict) and r.get("error"):
        return None, f"حزمة البحث فشلت — research bundle error: {r['error']}"
    if not isinstance(r, dict) or not r.get("agents"):
        return None, ("حزمة وكلاء البحث غير مفعّلة (with_research) — "
                      "لا اكتشافات مرصودة لهذا القسم")
    return r, ""


def _ragent(m: dict, name: str) -> dict:
    """وكيل بحث بالاسم من الحزمة — one research agent's block ({} if absent)."""
    r, _ = _research_bundle(m)
    return ((r or {}).get("agents") or {}).get(name) or {}


def _rfind(agent: dict, metric: str) -> dict | None:
    """اكتشاف بالاسم — the finding dict for a metric, or None."""
    for f in agent.get("findings") or []:
        if f.get("metric") == metric:
            return f
    return None


def _f_text(f: dict) -> str:
    """سطر الاكتشاف — metric: value unit [+ وسم «مُقدَّر» ونص المعادلة إن نموذجاً]."""
    unit = f" {f.get('unit')}" if f.get("unit") else ""
    txt = f"{f.get('metric')}: {_fmt(f.get('value'))}{unit}"
    if f.get("modeled"):
        txt += f" [{_MODELED_TAG}]"
        if f.get("formula"):
            txt += f" — المعادلة: {f['formula']}"
    return txt


def _f_src_bare(f: dict | None) -> str:
    """نص المصدر بلا بادئة — source text without the "المصدر: " label.

    لخلايا الجداول (`_add_table`) التي تحمل عمود "المصدر" بذاتها — البادئة
    هناك تتكرر ("المصدر: المصدر: ..."). `_f_srcline` تبقى للاستخدام السردي.
    """
    parts = []
    for s in (f or {}).get("sources") or []:
        seg = str(s.get("source") or "غير مرصود")
        if s.get("retrieved_at"):
            seg += f" | سُحب: {s['retrieved_at']}"
        if s.get("confidence") is not None:
            seg += f" | ثقة: {s['confidence']}"
        if s.get("url"):
            seg += f" | {s['url']}"
        parts.append(seg)
    return "؛ ".join(parts) if parts else "غير مرصود"


def _f_srcline(f: dict | None) -> str:
    """سطر المصدر لاكتشاف — source line (source | retrieved_at | confidence | url)."""
    return "المصدر: " + _f_src_bare(f)


def _entry_text(e: object) -> str:
    """سطر مرشّح (شركة/مورّد) — one candidate line: name/url/address/via/date.

    إصلاح مراجعة Stage 5 (ثغرة ٢): بند kind=reference عنوانُ صفحة ويب لا اسم
    كيان — يُطبع دائماً بوسم «مرجع للمراجعة اليدوية»، لا كمنافس بالاسم.
    """
    if not isinstance(e, dict):
        return str(e)
    is_ref = _candidate_kind(e) == "reference"
    label = str(e.get("name") or e.get("title") or "؟")
    if is_ref:
        bits = [f"مرجع للمراجعة اليدوية: {label}"]
    elif e.get("business_hint") == "retail_or_food_service":
        # بلاغ مالك حقيقي: محلات عصير/مطاعم ظهرت كأنها مستوردون — تصنيف
        # جوجل الفعلي (types) يكشف ذلك، فنُعلِنه بدل تسميته موزّعاً بالجملة.
        bits = [f"⚠ {label} — يبدو محل تجزئة/مطعماً حسب تصنيف Google Maps، "
               "ليس بالضرورة موزّعاً بالجملة"]
    else:
        bits = [label]
    if e.get("url"):
        bits.append(str(e["url"]))
    if e.get("address"):
        bits.append(f"العنوان: {e['address']}")
    if e.get("via"):
        bits.append(f"عبر {e['via']}")
    if e.get("retrieved_at"):
        bits.append(f"سُحب: {e['retrieved_at']}")
    # كياناتٌ مُستخلَصة (كلود) تحمل ملاحظةَ «غير موثَّق، أكّده» — تُظهَر لا تُخفى.
    if not is_ref and e.get("note") and "مُستخلَص" in str(e.get("note")):
        bits.append(str(e["note"]))
    return " — ".join(bits)


def _candidate_kind(e: object) -> str:
    """نوع المرشّح — entity (اسم Google Places) أم reference (عنوان بحث ويب)."""
    if not isinstance(e, dict):
        return "reference"
    if e.get("kind") in ("entity", "reference"):
        return e["kind"]
    # توافُق خلفي: بنود قديمة بلا kind — Maps كيان، وكل ما جاء من بحث الويب مرجع.
    if e.get("via") == "Google Maps":
        return "entity"
    return "reference"


def _split_candidates(items: list) -> tuple[list, list]:
    """افصل الكيانات عن المراجع — entities first, web references second."""
    ents = [e for e in (items or []) if _candidate_kind(e) == "entity"]
    refs = [e for e in (items or []) if _candidate_kind(e) == "reference"]
    return ents, refs


def _listing_text(v: object) -> str:
    """سطر قائمة سعر تجزئة — one retail listing line (title/price/currency/store)."""
    if not isinstance(v, dict):
        return str(v)
    t = str(v.get("title") or v.get("name") or "قائمة")
    if v.get("price") is not None:
        t += f": {_fmt(v['price'])}" + (f" {v['currency']}" if v.get("currency") else "")
    if v.get("store"):
        t += f" — {v['store']}"
    return t


def _req_text(it: object) -> str:
    """سطر بند اشتراطات — one requirements-checklist item (بنده وجهته ورابطه)."""
    if not isinstance(it, dict):
        return str(it)
    bits = [str(it.get("item") or it.get("requirement") or "؟")]
    if it.get("authority"):
        bits.append(f"الجهة: {it['authority']}")
    if it.get("direction"):
        bits.append(f"الاتجاه: {it['direction']}")
    if it.get("source_url"):
        bits.append(str(it["source_url"]))
    return " — ".join(bits)


def _entry_decision_of(m: dict) -> tuple[dict | None, str]:
    """قرار الدخول §8 أو غيابه المعلّل — the §8 decision, or a declared absence."""
    ed = (m or {}).get("entry_decision")
    if isinstance(ed, dict) and ed.get("error"):
        return None, f"محرك القرار (§8) أبلغ خطأً — decision error: {ed['error']}"
    if not isinstance(ed, dict) or not ed.get("schema"):
        return None, ("قرار الدخول غير متاح — المحرك الموزون (§8) لم يعمل لهذا "
                      "التحليل (يتطلب with_research)")
    return ed, ""


def render_brief(view: dict, dashboard_url: str = "/") -> str:
    """المختصر (§10.4) — صفحة واحدة بتصميم "رسالة جوال"، من القالب حصراً."""
    _assert_production_clean(view)
    d = view.get("decision") or {}
    cp = view.get("competitive_position") or {}
    top = (view.get("markets") or [{}])[0]
    numbers = []
    for c in (top.get("components_detail") or []):
        if c.get("value") is not None:
            numbers.append(f"• {c['name']}: {_fmt(c['value'])} "
                           f"[{c.get('source', '؟')}]")
        if len(numbers) == 3:
            break
    if not numbers:
        numbers = ["• لا أرقام مرصودة — الفجوات معلنة بالتقرير الكامل"]
    L = ([] if not view.get("test_run") else
         ["⚠ TEST RUN — تشغيل برهاني ببدائل موسومة، ليس تقريراً إنتاجياً"])
    L += [f"سِلك | {view.get('product')} (HS {view.get('hs_code')}) — "
         f"{view.get('year')} | مبدئي",
         "",
         view.get("brief", [""])[0] if view.get("brief") else
         f"القرار: {d.get('verdict') or 'تعذّر الحكم'}",
         "", "أرقام حاسمة (بمصادرها):", *numbers, ""]
    if len(view.get("brief") or []) > 1:
        L += view["brief"][1:3]
    else:
        L.append(cp.get("note", ""))
    L += ["", f"التفاصيل الكاملة باللوحة: {dashboard_url}",
          "كل رقم بمصدره؛ النواقص معلنة لا مخمّنة — قرار أوّلي لا نهائي."]
    return "\n".join(L)


# ── بناة أقسام Word الجديدة (§7) — new docx section builders (pure display) ──

def _add_table(doc, headers: list[str], rows: list[list]) -> None:
    """جدول Word موحّد — bordered table, bold header row; no rows => no-op.

    مراجعة المشروع: النسخة الحية من التقرير (docx، ما يُرسله المستخدم فعلياً)
    كانت نقاطاً سردية بحتة بينما نظيرتها Markdown تستخدم جداول فعلية لنفس
    البيانات (قرار الدخول مثلاً) — تناقضٌ بين الصيغتين، وواحدة من أوضح علامات
    "تقرير غير احترافي" بمقارنة أي منصة أبحاث سوق مرجعية (Country Commercial
    Guides وITC Trade Map وEuromonitor). لا بيانات جديدة، عرضٌ صرفٌ فقط —
    "Table Grid" نمطٌ مدمج في python-docx (بلا قالب خارجي).
    """
    if not rows:
        return
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = str(h)
        if hdr[i].paragraphs[0].runs:
            hdr[i].paragraphs[0].runs[0].bold = True
    for vals in rows:
        cells = table.add_row().cells
        for i, v in enumerate(vals):
            cells[i].text = str(v) if v is not None else "—"


def _docx_entry_strategy(doc, m: dict) -> None:
    """استراتيجية دخول السوق — فصلٌ مستقل يركّب توصية الدخول من أرقامٍ مرصودة.

    مراجعة المشروع: التوصية («ادخل عبر موزّع قائم») كانت مدفونة كسطرٍ واحد
    داخل «الخطوات الأولى» — أي منصة مرجعية (Country Commercial Guides) تُفرد
    لها فصلاً. يُركِّب هنا فقط ما هو مرصود فعلاً (تركّز الموردين + بوابة
    الأهلية + عدد المرشّحين بالاسم) في فقرة واحدة مسبَّبة؛ لا رقم جديد، لا
    اختلاق — تجميعٌ لحقائق موجودة أصلاً في أقسام أخرى من نفس التقرير.
    """
    doc.add_heading("استراتيجية دخول السوق", level=1)
    comp = _ragent(m, "competitor")
    reg = _ragent(m, "regulatory")
    if not comp and not reg:
        doc.add_paragraph("بيانات غير كافية لتركيب استراتيجية دخول — "
                          "يتطلب with_research")
        return
    hhi_f = _rfind(comp, "hhi")
    top_f = _rfind(comp, "top_supplier_share_pct")
    gate_f = _rfind(reg, "eligibility_gate")
    sd = m.get("supplier_directory") or {}
    n_target = len(sd.get("target") or [])
    n_saudi = len(sd.get("saudi") or [])
    hhi = hhi_f.get("value") if hhi_f else None
    top_share = top_f.get("value") if top_f else None
    concentrated = hhi is not None and hhi > 0.25
    model = ("عبر موزّع/مستورد محلي قائم" if (concentrated or n_target)
             else "مباشر أو عبر موزّع محلي — لا تفضيل واضح من بيانات التركّز")
    reasons = []
    if hhi is not None:
        reasons.append(f"مؤشر تركّز الموردين HHI={hhi} "
                       + ("(سوق مركّز)" if concentrated else "(سوق مفتّت)"))
    if top_share is not None:
        reasons.append(f"أكبر حصة مورّد واحد {top_share}%")
    if n_target:
        reasons.append(f"{n_target} موزّعاً/مستورداً محتملاً مرصوداً بالاسم "
                       "بالسوق المستهدف")
    if n_saudi:
        reasons.append(f"{n_saudi} مورّداً سعودياً مرصوداً بالاسم كمرشّح تعاقد")
    if gate_f and gate_f.get("value"):
        reasons.append("بوابة أهلية أمامية مفتوحة — لا خطوة لاحقة تُعتبر "
                       "سالكة قبل اجتيازها")
    doc.add_paragraph(f"النموذج الموصى به: {model}")
    if reasons:
        doc.add_paragraph("الأساس (من الأقسام أعلاه، لا رقم جديد):")
        for r in reasons:
            doc.add_paragraph(r, style="List Bullet")
    else:
        doc.add_paragraph("لا مؤشرات تركّز أو مرشّحين مرصودة — التوصية أعلاه "
                          "افتراضية حتى تتوفر بيانات المنافسة/الموردين")


def _docx_entry_decision(doc, m: dict) -> None:
    """قرار الدخول (المحرك الموزون §8) — verdict/score/pillars/conditions/risks."""
    doc.add_heading("قرار الدخول (المحرك الموزون §8)", level=1)
    ed, absent = _entry_decision_of(m)
    if ed is None:
        doc.add_paragraph(absent)
        return
    doc.add_paragraph(f"الحكم: {ed.get('verdict')} | النقاط: {_fmt(ed.get('score'))}"
                      f" | الثقة: {ed.get('confidence')}")
    doc.add_paragraph(f"أساس الثقة: {ed.get('confidence_basis')}")
    sbo = ed.get("scores_by_option") or {}
    doc.add_paragraph(f"خيار الأوزان المعتمد: {ed.get('weights_option')} — "
                      f"النقاط بالخيارين: A = {_fmt(sbo.get('A'))} | "
                      f"B = {_fmt(sbo.get('B'))}")
    if ed.get("weights_note"):
        doc.add_paragraph(f"ملاحظة الأوزان: {ed['weights_note']}")
    # الأعمدة الأربعة كجدول (توازي render_markdown) — لا نقاط سردية مبعثرة.
    _add_table(
        doc, ["العمود", "القيمة", "الأساس", "مكوّنات غائبة"],
        [[_PILLAR_AR.get(key, key), _fmt(p.get("value")), p.get("basis"),
          "، ".join(map(str, p.get("missing") or [])) or "—"]
         for key, p in (ed.get("pillars") or {}).items()])
    if ed.get("missing_pillars"):
        doc.add_paragraph("أعمدة غائبة كلياً: " + "، ".join(
            _PILLAR_AR.get(k, k) for k in ed["missing_pillars"]))
    if ed.get("critical_risk"):
        doc.add_paragraph("تحذير: خطر حرج مرصود — راجع سجل المخاطر أدناه.")
    doc.add_paragraph("الشروط:")
    for c in ed.get("conditions") or ["لا شروط مفتوحة"]:
        doc.add_paragraph(str(c), style="List Bullet")
    doc.add_paragraph("سجل المخاطر:")
    for r in ed.get("risks") or []:
        doc.add_paragraph(f"{r.get('risk')} (الشدة: {r.get('severity')}) — "
                          f"الدليل: {r.get('evidence')}", style="List Bullet")
    if not ed.get("risks"):
        doc.add_paragraph("لا مخاطر مسجّلة في محرك القرار", style="List Bullet")
    doc.add_paragraph("الخطوات الأولى:")
    for s in ed.get("first_steps") or ["لا خطوات مقترحة"]:
        doc.add_paragraph(str(s), style="List Bullet")
    doc.add_paragraph(f"لماذا: {ed.get('why')}")
    if ed.get("note"):
        doc.add_paragraph(str(ed["note"]))


def _docx_market_size(doc, m: dict) -> None:
    """حجم السوق TAM/SAM/SOM — كل اكتشاف بمصدره؛ المنمذج موسوم بمعادلته."""
    doc.add_heading("حجم السوق — TAM/SAM/SOM", level=1)
    r, absent = _research_bundle(m)
    if r is None:
        doc.add_paragraph(absent)
        return
    ag = _ragent(m, "market_size")
    valued = [f for f in (ag.get("findings") or []) if f.get("value") is not None]
    if valued:
        _add_table(
            doc, ["المؤشر", "القيمة", "النوع", "المصدر"],
            [[f.get("metric"),
              f"{_fmt(f.get('value'))}{(' ' + f['unit']) if f.get('unit') else ''}",
              (_MODELED_TAG if f.get("modeled") else "رصد مباشر"),
              _f_src_bare(f)]
             for f in valued])
        for f in valued:
            if f.get("modeled") and f.get("formula"):
                doc.add_paragraph(f"معادلة «{f.get('metric')}»: {f['formula']}",
                                  style="Intense Quote")
    else:
        doc.add_paragraph("لا اكتشافات مرصودة لحجم السوق")
    for g in ag.get("gaps") or []:
        doc.add_paragraph(f"فجوة معلنة: {g}", style="List Bullet")


def _docx_competition_research(doc, m: dict) -> None:
    """طبقتا المنافسة من حزمة البحث — شركات بالاسم + أرقام الطبقة الدولية."""
    ag = _ragent(m, "competitor")
    if not ag:
        return
    doc.add_heading("شركات بالاسم (مرشّحون غير موثَّقين)", level=2)
    named = (_rfind(ag, "named_companies") or {}).get("value") or []
    ents, refs = _split_candidates(named)
    if ents:
        _add_table(
            doc, ["الاسم", "العنوان", "المصدر", "ملاحظة"],
            [[e.get("name") or e.get("title") or "؟", e.get("address"),
              e.get("via"),
              ("مُستخلَص، غير موثَّق" if "مُستخلَص" in str(e.get("note") or "")
               else "غير موثَّق")]
             for e in ents[:10]])
        doc.add_paragraph("كيانات غير موثَّقة (ثقة 0.4) — أكّدها قبل أي تعاقد.")
    else:
        doc.add_paragraph("لا كيانات مرصودة بالاسم — فجوة معلنة "
                          "(أسماء الأعمال تأتي من Google Places حصراً)")
    if refs:
        doc.add_heading("مراجع ويب للمراجعة اليدوية (ليست أسماء منافسين)",
                        level=2)
        for n in refs[:8]:
            doc.add_paragraph(_entry_text(n), style="List Bullet")
    doc.add_paragraph("الطبقة الدولية (تركّز الموردين — UN Comtrade):")
    metrics_rows = []
    for metric in ("hhi", "top_supplier_share_pct", "saudi_share_pct"):
        f = _rfind(ag, metric)
        if f and f.get("value") is not None:
            metrics_rows.append([metric, _fmt(f.get("value")), _f_src_bare(f)])
            if f.get("note"):
                metrics_rows[-1].append(str(f["note"]))
        else:
            metrics_rows.append([metric, "غير مرصود", "—"])
    max_cols = max(len(r) for r in metrics_rows)
    for r in metrics_rows:
        while len(r) < max_cols:
            r.append("")
    _add_table(doc, ["المؤشر", "القيمة", "المصدر", "ملاحظة"][:max_cols],
              metrics_rows)


def _docx_pricing_layers(doc, m: dict) -> None:
    """التسعير بطبقتيه — الحدودية (نماذج موسومة بمعادلاتها) ثم التجزئة ومراجعها."""
    doc.add_heading("التسعير بطبقتيه", level=1)
    r, absent = _research_bundle(m)
    if r is None:
        doc.add_paragraph(absent)
        return
    ag = _ragent(m, "pricing")
    doc.add_paragraph("الطبقة الحدودية (قيم وحدة كومتريد):")
    border_rows, border_formulas = [], []
    for metric in ("border_unit_value_usd_kg", "saudi_border_unit_value_usd_kg",
                   "margin_at_border_pct"):
        f = _rfind(ag, metric)
        if f and f.get("value") is not None:
            unit = f" {f['unit']}" if f.get("unit") else ""
            border_rows.append([
                metric, f"{_fmt(f.get('value'))}{unit}",
                (_MODELED_TAG if f.get("modeled") else "رصد مباشر"),
                _f_src_bare(f)])
            if f.get("modeled") and f.get("formula"):
                border_formulas.append(f"معادلة «{metric}»: {f['formula']}")
        else:
            border_rows.append([metric, "غير مرصود", "—", "—"])
    _add_table(doc, ["المؤشر", "القيمة", "النوع", "المصدر"], border_rows)
    for line in border_formulas:
        doc.add_paragraph(line, style="Intense Quote")
    doc.add_paragraph("طبقة التجزئة:")
    rp = _rfind(ag, "retail_prices")
    vals = (rp or {}).get("value") or []
    if vals:
        for v in vals[:8]:
            doc.add_paragraph(_listing_text(v), style="List Bullet")
        doc.add_paragraph(_f_srcline(rp), style="Intense Quote")
    else:
        # فجوة القسم المعلنة تُطبع بنصّها — the section's declared gap, verbatim.
        gap = next((g for g in (ag.get("gaps") or []) if "retail_prices" in g),
                   "retail_prices: غير مرصود — فجوة معلنة")
        doc.add_paragraph(gap, style="List Bullet")
    # نقاطُ الأسعار المُستخلَصة (كلود) — أرقامٌ مذكورةٌ صراحةً، لا روابط.
    points = (_rfind(ag, "retail_price_points") or {}).get("value") or []
    if points:
        doc.add_paragraph("أسعار مُستخلَصة (مذكورة صراحةً في عناوين الويب — مؤشِّر "
                          "لا سعرَ رفٍّ مؤكَّد):")
        for p in points[:8]:
            p = p or {}
            doc.add_paragraph(
                f"{p.get('price')} {p.get('currency')}/{p.get('unit')}".rstrip("/")
                + (f" — {p.get('url')}" if p.get("url") else ""),
                style="List Bullet")
    refs = (_rfind(ag, "retail_references") or {}).get("value") or []
    if refs:
        doc.add_paragraph("مصادر الأسعار (للاستشهاد):")
        for ref in refs[:3]:
            doc.add_paragraph(f"{(ref or {}).get('title')} — {(ref or {}).get('url')}"
                              f" — سُحب: {(ref or {}).get('retrieved_at')}",
                              style="List Bullet")
    elif not points:
        doc.add_paragraph("مراجع الأسعار: غير مرصودة")


def _docx_swot(doc, m: dict) -> None:
    """SWOT قاعدي — شبكة ٢×٢ حقيقية (لا أربع عناوين متتالية)؛ كل خلية بدليلها.

    مراجعة المشروع: شكل SWOT كأربعة عناوين متسلسلة لا يُقرأ كمصفوفة عند
    الطباعة، بينما كل مرجعية بحث سوق (IBISWorld، Euromonitor) تعرضه شبكةً
    ٢×٢ فعلية — نفس المحتوى، عرضٌ مطابق للتعارف الصناعي.
    """
    doc.add_heading("تحليل SWOT (قاعدي من حقائق مرصودة)", level=1)
    sw = m.get("swot") or {}
    table = doc.add_table(rows=2, cols=2)
    table.style = "Table Grid"
    layout = [(("S", "القوة"), ("W", "الضعف")),
             (("O", "الفرص"), ("T", "التهديدات"))]
    for row_idx, pair in enumerate(layout):
        for col_idx, (key, title) in enumerate(pair):
            cell = table.rows[row_idx].cells[col_idx]
            cell.paragraphs[0].add_run(title).bold = True
            items = sw.get(key) or []
            if not items:
                cell.add_paragraph("لا بند مرصوداً")
            for it in items:
                cell.add_paragraph(f"{it.get('text')} — الدليل: "
                                   f"{it.get('evidence')}", style="List Bullet")
    if sw.get("note"):
        doc.add_paragraph(str(sw["note"]))


def _docx_segments(doc, m: dict) -> None:
    """شرائح العملاء — segment + basis؛ الفارغ يُعلن لا يُخترع."""
    doc.add_heading("شرائح العملاء", level=1)
    segs = m.get("segments") or []
    if not segs:
        doc.add_paragraph("بيانات غير كافية للشرائح — يتطلب وكيل المستهلك")
        return
    for s in segs:
        doc.add_paragraph(f"{s.get('segment')} — الأساس: {s.get('basis')}",
                          style="List Bullet")


def _docx_supplier_directory(doc, m: dict) -> None:
    """دليل المورّدين والمصنّعين — قائمتا السعودية والسوق المستهدف + الملاحظة."""
    doc.add_heading("دليل المورّدين والمصنّعين", level=1)
    sd = m.get("supplier_directory") or {}
    for key, title in (("saudi", "مورّدون ومصنّعون سعوديون:"),
                       ("target", "موزّعون ومستوردون في السوق المستهدف:")):
        doc.add_paragraph(title)
        items = sd.get(key) or []
        if not items:
            doc.add_paragraph("لا مرشّحين مرصودين — فجوة معلنة",
                              style="List Bullet")
        for e in items[:10]:
            doc.add_paragraph(_entry_text(e), style="List Bullet")
    if sd.get("note"):
        doc.add_paragraph(str(sd["note"]))


def _docx_regulatory(doc, m: dict) -> None:
    """الاشتراطات التنظيمية — بوابة الأهلية أولاً ثم بنود L1 بجهاتها وروابطها."""
    doc.add_heading("الاشتراطات التنظيمية", level=1)
    r, absent = _research_bundle(m)
    ag = _ragent(m, "regulatory")
    if r is None or not ag:
        doc.add_paragraph(absent or "وكيل الاشتراطات لم يعمل في هذا التحليل")
        return
    gate_f = _rfind(ag, "eligibility_gate")
    if gate_f and gate_f.get("value"):
        doc.add_paragraph("تحذير — بوابة أهلية أمامية: هذا السوق يتطلب منشأة "
                          "معتمدة (EU 2017/625) قبل أي بند لاحق؛ لا بند أدناه "
                          "يُعتبر سالكاً قبل اجتيازها.")
    checklist_f = _rfind(ag, "requirements_checklist")
    checklist = (checklist_f or {}).get("value") or []
    if checklist:
        _add_table(
            doc, ["البند", "الجهة", "الاتجاه", "الرابط"],
            [[it.get("item") or it.get("requirement"), it.get("authority"),
              it.get("direction"), it.get("source_url")]
             for it in checklist if isinstance(it, dict)])
        doc.add_paragraph(_f_srcline(checklist_f), style="Intense Quote")
    else:
        doc.add_paragraph("لا بنود اشتراطات مرصودة في مرجع L1 لهذا السوق "
                          "— فجوة معلنة")
    tf = _rfind(ag, "tariff_applied_pct")
    if tf and tf.get("value") is not None:
        doc.add_paragraph(_f_text(tf))
        doc.add_paragraph(_f_srcline(tf), style="Intense Quote")
    for g in ag.get("gaps") or []:
        doc.add_paragraph(f"فجوة معلنة: {g}", style="List Bullet")


def render_docx(view: dict, path: str) -> str:
    """التقرير الكامل Word (§10.3) — من القالب الموحّد حصراً.

    يعيد المسار عند النجاح؛ RuntimeError واضحة بلا python-docx.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(_DOCX_HINT) from exc

    _assert_production_clean(view)
    doc = Document()
    # ١) الخلاصة التنفيذية أولاً (نجحت باختبار الخمس ثوانٍ — تُثبَّت).
    doc.add_heading(f"سِلك — تقرير سوق: {view.get('product')}", 0)
    if view.get("test_run"):
        doc.add_paragraph("⚠ TEST RUN — تشغيل برهاني ببدائل موسومة "
                          "(SILK_HERMETIC)، ليس تقريراً إنتاجياً")
    # ترويسة 2B-د: منتج/HS/سوق مستهدف/تاريخ/تغطية إجمالية % — في الصدارة دائماً.
    h = view.get("header") or {}
    doc.add_paragraph(
        f"المنتج: {h.get('product')} | HS: {h.get('hs_code')} | "
        f"المنشأ: السعودية | السوق المستهدف: {h.get('target_market')} | "
        f"التاريخ: {h.get('date')} | تغطية البيانات الإجمالية: "
        f"{h.get('coverage_pct')}%")
    d = view.get("decision") or {}
    doc.add_heading("الخلاصة التنفيذية", level=1)
    doc.add_paragraph(f"القرار: {d.get('verdict') or 'تعذّر الحكم'} "
                      f"(ثقة {d.get('confidence')}) — السوق الأول: "
                      f"{d.get('market') or '؟'}")
    doc.add_paragraph(f"لماذا: {d.get('why') or ''}")
    # حكم واحد لا حكمان: عند حكم المحرك §8 تُطبع الجورية سطرَ كفاية بيانات فقط.
    if d.get("sufficiency"):
        doc.add_paragraph(d["sufficiency"])
    doc.add_paragraph(f"رمز HS: {view.get('hs_code')} "
                      f"(ثقة التصنيف {view.get('hs_confidence')}) | "
                      f"سنة البيانات: {_data_year_label(view)} | "
                      "النتيجة أوّلية لا نهائية.")

    # ٢) موقعك التنافسي (محرّك التقاطع) بعد الخلاصة مباشرة.
    cp = view.get("competitive_position") or {}
    doc.add_heading("موقعك التنافسي", level=1)
    if cp.get("available"):
        doc.add_paragraph(cp.get("coverage") or "")
        for f in cp.get("feasibility_threads") or []:
            p = doc.add_paragraph()
            p.add_run(f"ضد {f['competitor']}: ").bold = True
            p.add_run(f"سعر مرصود {_fmt(f['observed_price'])} — هامشك عند "
                      f"المضاهاة {f['margin_at_match_pct']}% وعند البيع "
                      f"أقل 10% {f['margin_at_10pct_below']}%")
            for gap in f.get("assumptions_and_gaps") or []:
                doc.add_paragraph(gap, style="List Bullet")
        for t in cp.get("competitor_threads") or []:
            if not t.get("observed_price"):
                # خيوط بحث الويب مراجع لا كيانات (ثغرة ٢) — لا توحي باسم منافس.
                doc.add_paragraph(f"مرجع ويب للمراجعة: {t['name']} — "
                                  f"{t['price_flag']} "
                                  f"(اكتمال الخيط {t['thread_completeness']})",
                                  style="List Bullet")
    else:
        doc.add_paragraph(cp.get("note") or "")

    # ٢ب) مشهد السوق الأول — أسعار/منافسون/موردون/اتجاه/ثقافة (الموجة ٩).
    #     يُعرض المرصود، ويُعلن الغائب «غير مرصود» بمصدره/مفتاحه المطلوب — لا
    #     اختلاق، وتقرير لا يعود «ناقصاً» بل صريحاً بما لديه وما ينقصه.
    top_m = (view.get("markets") or [{}])[0]

    # §7-1/§7-2: قرار الدخول (§8) ثم TAM/SAM/SOM — بعد الموقع التنافسي مباشرة
    # وقبل مشهد السوق؛ الغائب يُعلن بفقرة صريحة لا يُخترع.
    _docx_entry_decision(doc, top_m)
    _docx_entry_strategy(doc, top_m)
    _docx_market_size(doc, top_m)

    st_all = top_m.get("section_status") or {}

    def _gate(sec_key: str, title: str) -> bool:
        """بوابة 2B: دون العتبة يُطبع سطر النقص الصريح فقط — لا نثر عام أبداً."""
        st = st_all.get(sec_key)
        if st and st.get("status") == "insufficient":
            doc.add_heading(title, level=1)
            doc.add_paragraph("بيانات غير كافية — INSUFFICIENT DATA")
            from silk_render import insufficient_line
            doc.add_paragraph(insufficient_line(title, st))
            return False
        return True

    def _sec(title: str, items: list, sec_key: str, fmt) -> None:
        if not _gate(sec_key, title):
            return
        doc.add_heading(title, level=1)
        for it in items or []:
            doc.add_paragraph(fmt(it), style="List Bullet")

    _sec("أسعار المنتجات في السوق", top_m.get("prices"), "pricing",
         lambda p: f"{p.get('title') or 'قائمة'}: {_fmt(p.get('price'))}"
                   + (f" {p['currency']}" if p.get("currency") else "")
                   + (f" — {p['store']}" if p.get("store") else ""))

    countries = top_m.get("supplier_countries") or []
    named = top_m.get("named_competitors") or []
    if not _gate("competitors", "المنافسون"):
        countries, named = [], None
    else:
        doc.add_heading("المنافسون", level=1)
    if countries:
        doc.add_paragraph("الدول المورّدة وحصصها:")
        for c in countries[:6]:
            doc.add_paragraph(f"{c.get('partner')}: {c.get('share')}% "
                              f"({_fmt(c.get('value_usd'))}$)", style="List Bullet")
    if named:
        # عناوين بحث ويب (الطبقة القديمة) — مراجع للمراجعة اليدوية لا أسماء (ثغرة ٢).
        doc.add_paragraph("مراجع ويب عن المنافسة (للمراجعة اليدوية — "
                          "ليست أسماء منافسين):")
        for n in named[:8]:
            doc.add_paragraph(str(n), style="List Bullet")

    # §7-3: طبقتا المنافسة من حزمة البحث — بعد قسم «المنافسون» القائم مباشرة.
    _docx_competition_research(doc, top_m)
    # §7-4: التسعير بطبقتيه (الحدودية المنمذجة الموسومة + التجزئة ومراجعها).
    _docx_pricing_layers(doc, top_m)

    if top_m.get("suppliers"):
        _sec("الموردون والأعمال بالاسم", top_m.get("suppliers"), "competitors",
             lambda s: f"{s.get('name')} — {s.get('source')}")

    # §7-5..8: SWOT، الشرائح، دليل المورّدين، الاشتراطات — كلها من view.markets[0].
    _docx_swot(doc, top_m)
    _docx_segments(doc, top_m)
    _docx_supplier_directory(doc, top_m)
    _docx_regulatory(doc, top_m)

    tr = top_m.get("trend") or {}
    if _gate("trend", "اتجاه الاستيراد متعدد السنوات"):
        doc.add_heading("اتجاه الاستيراد متعدد السنوات", level=1)
        doc.add_paragraph(f"النمو {tr.get('growth_pct')}% "
                          f"(CAGR {tr.get('cagr_pct')}%) — {tr.get('note')}")

    culture = view.get("culture") or []
    if culture:
        doc.add_heading("ثقافة المستهلك ونبض السوق", level=1)
        for c in culture[:6]:
            doc.add_paragraph(str(c.get("title"))[:200], style="List Bullet")
    else:
        doc.add_heading("ثقافة المستهلك ونبض السوق", level=1)
        doc.add_paragraph("بيانات غير كافية — INSUFFICIENT DATA")
        doc.add_paragraph("بيانات غير كافية لقسم «الثقافة» (0/1) — المصادر "
                          "المُحاوَلة: Web Search (Serper)")

    # ٣) الأسواق — سطر مصدر تحت كل رقم (§10.3، من components_detail).
    doc.add_heading("الأسواق المرشّحة (الأفضل أولاً)", level=1)
    for i, m in enumerate((view.get("markets") or [])[:8], 1):
        doc.add_heading(f"{i}. {m.get('country')} — نقاط "
                        f"{m.get('score')} (ثقة {m.get('confidence')})",
                        level=2)
        for c in m.get("components_detail") or []:
            doc.add_paragraph(f"{c['name']}: {_fmt(c['value'])}")
            src_line = (f"المصدر: {c.get('source') or 'غير مرصود'}"
                        + (f" | سُحب: {c['retrieved_at']}"
                           if c.get("retrieved_at") else "")
                        + f" | ثقة: {c.get('confidence')}")
            doc.add_paragraph(src_line, style="Intense Quote")

    # Stage 2A-١) تغطية المصادر لكل قسم (السوق الأعلى) — coverage per section.
    top_m = (view.get("markets") or [{}])[0]
    cov = top_m.get("section_coverage") or {}
    if cov:
        doc.add_heading("تغطية المصادر حسب القسم", level=1)
        _AR = {"market_size": "حجم السوق والمنافسة", "demand": "الطلب والقدرة",
               "regulatory": "الاشتراطات والتعريفة", "competitors": "المنافسون بالاسم",
               "pricing": "الأسعار", "risk": "المخاطر", "trend": "الاتجاه"}
        for sec, c in cov.items():
            flag = " ⚠ مصدر واحد — ثقة منخفضة" if c.get("low_confidence") else ""
            doc.add_paragraph(
                f"{_AR.get(sec, sec)}: {c['contributed']}/{c['attempted']} "
                f"(درجة {c['score']}){flag}")

    # Stage 2A-٢) ملحق الأثر — provenance appendix: لا فشل صامتاً.
    prov = view.get("provenance") or []
    if prov:
        doc.add_heading("ملحق: أثر المصادر (المحاولات والإسهام)", level=1)
        for b in prov:
            doc.add_paragraph(f"{b['source']}: أسهم {b['contributed']} من "
                              f"{b['attempted']} محاولة")
            for f in b.get("failures") or []:
                doc.add_paragraph(f"    فشل مُسجَّل: {f}", style="Intense Quote")

    # ٤) حدود هذا التقرير — قبل التوصيات (§10.3).
    doc.add_heading("حدود هذا التقرير", level=1)
    limits = view.get("limits") or ["لا فجوات مرصودة في الأسواق العليا"]
    for x in limits[:12]:
        doc.add_paragraph(str(x), style="List Bullet")

    # ٥) التوصية (سطور المختصر نفسها — نفس القالب، لا صياغة موازية).
    doc.add_heading("التوصية الأوّلية", level=1)
    for line in view.get("brief") or []:
        doc.add_paragraph(line)
    doc.add_paragraph(view.get("note") or "")

    doc.save(path)
    return path


def _md_cell(x: object) -> str:
    """خلية جدول Markdown آمنة — escape pipes/newlines for a table cell."""
    return str(x if x is not None else "—").replace("|", "/").replace("\n", " ")


def render_markdown(view: dict) -> str:
    """التقرير الكامل Markdown (§7) — نفس أقسام Word وترتيبها، من القالب حصراً.

    كل رقم يليه سطر مصدره بين قوسين؛ المنمذج موسوم «مُقدَّر — نموذج بافتراضات
    معلنة» بمعادلته؛ بوابة 2B نفسها: قسم دون العتبة يطبع سطر النقص الصريح فقط.
    Full Markdown report derived from the ONE canonical view — pure display.
    """
    from silk_render import insufficient_line

    _assert_production_clean(view)
    h = view.get("header") or {}
    top_m = (view.get("markets") or [{}])[0]
    st_all = top_m.get("section_status") or {}
    L: list[str] = []
    if view.get("test_run"):
        L += ["> ⚠ **TEST RUN** — تشغيل برهاني ببدائل موسومة (SILK_HERMETIC)، "
              "ليس تقريراً إنتاجياً", ""]

    # ── الترويسة كجدول — header table ────────────────────────────────────────
    L += [f"# سِلك — تقرير سوق: {view.get('product')}", "",
          "| البند | القيمة |", "| --- | --- |",
          f"| المنتج | {_md_cell(h.get('product'))} |",
          f"| رمز HS | {_md_cell(h.get('hs_code'))} "
          f"(ثقة التصنيف {view.get('hs_confidence')}) |",
          "| المنشأ | السعودية (SAU) |",
          f"| السوق المستهدف | {_md_cell(h.get('target_market'))} |",
          f"| التاريخ | {_md_cell(h.get('date'))} |",
          f"| سنة البيانات | {_md_cell(_data_year_label(view))} |",
          f"| تغطية البيانات الإجمالية | {h.get('coverage_pct')}% |", ""]

    # ── الخلاصة التنفيذية — executive summary (حكم واحد لا حكمان) ───────────
    d = view.get("decision") or {}
    L += ["## الخلاصة التنفيذية", "",
          f"- القرار: **{d.get('verdict') or 'تعذّر الحكم'}** "
          f"(ثقة {d.get('confidence')}) — السوق الأول: {d.get('market') or '؟'}",
          f"- لماذا: {d.get('why') or ''}"]
    if d.get("sufficiency"):
        L.append(f"- {d['sufficiency']}")
    L += ["- النتيجة أوّلية لا نهائية.", ""]

    # ── قرار الدخول §8 — weighted entry decision ────────────────────────────
    L += ["## قرار الدخول (المحرك الموزون §8)", ""]
    ed, ed_absent = _entry_decision_of(top_m)
    if ed is None:
        L += [ed_absent, ""]
    else:
        sbo = ed.get("scores_by_option") or {}
        L += [f"- الحكم: **{ed.get('verdict')}** | النقاط: {_fmt(ed.get('score'))}"
              f" | الثقة: {ed.get('confidence')}",
              f"- أساس الثقة: {ed.get('confidence_basis')}",
              f"- خيار الأوزان المعتمد: {ed.get('weights_option')} — النقاط "
              f"بالخيارين: A = {_fmt(sbo.get('A'))} | B = {_fmt(sbo.get('B'))}"]
        if ed.get("weights_note"):
            L.append(f"- ملاحظة الأوزان: {ed['weights_note']}")
        L += ["", "| العمود | القيمة | الأساس | مكوّنات غائبة |",
              "| --- | --- | --- | --- |"]
        for key, p in (ed.get("pillars") or {}).items():
            missing = "، ".join(map(str, p.get("missing") or [])) or "—"
            L.append(f"| {_PILLAR_AR.get(key, key)} | {_fmt(p.get('value'))} | "
                     f"{_md_cell(p.get('basis'))} | {_md_cell(missing)} |")
        L.append("")
        if ed.get("missing_pillars"):
            L.append("- أعمدة غائبة كلياً: " + "، ".join(
                _PILLAR_AR.get(k, k) for k in ed["missing_pillars"]))
        if ed.get("critical_risk"):
            L.append("- **خطر حرج مرصود** — راجع سجل المخاطر أدناه.")
        if ed.get("conditions"):
            L += ["", "**الشروط:**",
                  *[f"- {c}" for c in ed["conditions"]]]
        if ed.get("first_steps"):
            L += ["", "**الخطوات الأولى:**",
                  *[f"{i}. {s}" for i, s in enumerate(ed["first_steps"], 1)]]
        L += ["", f"لماذا: {ed.get('why')}"]
        if ed.get("note"):
            L.append(str(ed["note"]))
        L.append("")

    # ── موقعك التنافسي — competitive position (correlation) ─────────────────
    cp = view.get("competitive_position") or {}
    L += ["## موقعك التنافسي", ""]
    if cp.get("available"):
        L.append(f"- التغطية: {cp.get('coverage')}")
        for f in cp.get("feasibility_threads") or []:
            L.append(f"- ضد {f['competitor']}: سعر مرصود "
                     f"{_fmt(f['observed_price'])} — هامشك عند المضاهاة "
                     f"{f['margin_at_match_pct']}% وعند البيع أقل 10% "
                     f"{f['margin_at_10pct_below']}%")
            for gap in f.get("assumptions_and_gaps") or []:
                L.append(f"  - {gap}")
        for t in cp.get("competitor_threads") or []:
            if not t.get("observed_price"):
                # خيوط بحث الويب مراجع لا كيانات (ثغرة ٢).
                L.append(f"- مرجع ويب للمراجعة: {t['name']} — {t['price_flag']} "
                         f"(اكتمال الخيط {t['thread_completeness']})")
    else:
        L.append(str(cp.get("note") or ""))
    L.append("")

    # ── حجم السوق TAM/SAM/SOM — من حزمة البحث ───────────────────────────────
    L += ["## حجم السوق — TAM/SAM/SOM", ""]
    r_bundle, r_absent = _research_bundle(top_m)
    if r_bundle is None:
        L += [r_absent, ""]
    else:
        ms = _ragent(top_m, "market_size")
        shown = False
        for f in ms.get("findings") or []:
            if f.get("value") is None:
                continue
            L.append(f"- {_f_text(f)} ({_f_srcline(f)})")
            shown = True
        if not shown:
            L.append("- لا اكتشافات مرصودة لحجم السوق")
        for g in ms.get("gaps") or []:
            L.append(f"- فجوة معلنة: {g}")
        L.append("")

    # ── المنافسة بطبقتيها — دولية (كومتريد) + شركات بالاسم + طبقة الإثراء ────
    L += ["## المنافسة بطبقتيها", ""]
    comp = _ragent(top_m, "competitor")
    if comp:
        L.append("**الطبقة الدولية (تركّز الموردين — UN Comtrade):**")
        for metric in ("hhi", "top_supplier_share_pct", "saudi_share_pct"):
            f = _rfind(comp, metric)
            if f and f.get("value") is not None:
                L.append(f"- {_f_text(f)} ({_f_srcline(f)})")
                if f.get("note"):
                    L.append(f"  - {f['note']}")
            else:
                L.append(f"- {metric}: غير مرصود")
        sc_f = _rfind(comp, "supplier_countries")
        for c in ((sc_f or {}).get("value") or [])[:6]:
            if isinstance(c, dict):
                L.append(f"- {c.get('partner')}: {c.get('share')}% "
                         f"({_fmt(c.get('value_usd'))}$) ({_f_srcline(sc_f)})")
        named_rc = (_rfind(comp, "named_companies") or {}).get("value") or []
        ents_rc, refs_rc = _split_candidates(named_rc)
        L += ["", "**شركات بالاسم (كيانات Google Places، غير موثَّقة):**"]
        if ents_rc:
            for n in ents_rc[:10]:
                L.append(f"- {_entry_text(n)}")
            L.append("- ملاحظة: كيانات غير موثَّقة (ثقة 0.4) — أكّدها قبل "
                     "أي تعاقد.")
        else:
            L.append("- لا كيانات مرصودة بالاسم — فجوة معلنة (أسماء الأعمال "
                     "تأتي من Google Places حصراً)")
        if refs_rc:
            L += ["", "**مراجع ويب للمراجعة اليدوية (ليست أسماء منافسين):**",
                  *[f"- {_entry_text(n)}" for n in refs_rc[:8]]]
        L.append("")
    else:
        L += [r_absent or "وكيل المنافسة بلا اكتشافات — فجوة معلنة", ""]
    # طبقة الإثراء المحلية خلف بوابة 2B — سطر النقص الصريح فقط دون العتبة.
    st_c = st_all.get("competitors")
    if st_c and st_c.get("status") == "insufficient":
        L += [insufficient_line("المنافسون", st_c), ""]
    else:
        for c in (top_m.get("supplier_countries") or [])[:6]:
            L.append(f"- {c.get('partner')}: {c.get('share')}% "
                     f"({_fmt(c.get('value_usd'))}$) (المصدر: UN Comtrade)")
        for n in (top_m.get("named_competitors") or [])[:8]:
            # عناوين بحث (الطبقة القديمة) — مراجع لا أسماء منافسين (ثغرة ٢).
            L.append(f"- مرجع ويب للمراجعة اليدوية: {n}")
        L.append("")

    # ── التسعير بطبقتيه — border models + gated retail layer ────────────────
    L += ["## التسعير بطبقتيه", ""]
    if r_bundle is None:
        L += [r_absent, ""]
    else:
        pr = _ragent(top_m, "pricing")
        L.append("**الطبقة الحدودية (قيم وحدة كومتريد):**")
        for metric in ("border_unit_value_usd_kg",
                       "saudi_border_unit_value_usd_kg", "margin_at_border_pct"):
            f = _rfind(pr, metric)
            if f and f.get("value") is not None:
                L.append(f"- {_f_text(f)} ({_f_srcline(f)})")
                if f.get("note"):
                    L.append(f"  - {f['note']}")
            else:
                L.append(f"- {metric}: غير مرصود")
        L += ["", "**طبقة التجزئة:**"]
        rp = _rfind(pr, "retail_prices")
        vals = (rp or {}).get("value") or []
        st_p = st_all.get("pricing")
        if vals:
            for v in vals[:8]:
                L.append(f"- {_listing_text(v)} ({_f_srcline(rp)})")
        elif st_p and st_p.get("status") == "insufficient":
            # بوابة 2B: سطر النقص الصريح فقط + فجوة القسم المعلنة بنصّها.
            L.append(insufficient_line("الأسعار", st_p))
            gap = next((g for g in (pr.get("gaps") or [])
                        if "retail_prices" in g), None)
            if gap:
                L.append(f"- فجوة معلنة: {gap}")
        else:
            for p in top_m.get("prices") or []:
                L.append(f"- {_listing_text(p)}")
            if not top_m.get("prices"):
                gap = next((g for g in (pr.get("gaps") or [])
                            if "retail_prices" in g),
                           "retail_prices: غير مرصود — فجوة معلنة")
                L.append(f"- {gap}")
        points = (_rfind(pr, "retail_price_points") or {}).get("value") or []
        if points:
            L += ["", "**أسعار مُستخلَصة (مذكورة صراحةً في عناوين الويب — مؤشِّر لا "
                      "سعرَ رفٍّ مؤكَّد):**"]
            for p in points[:8]:
                p = p or {}
                L.append(f"- {p.get('price')} {p.get('currency')}/{p.get('unit')}"
                         .rstrip("/")
                         + (f" — {p.get('url')}" if p.get("url") else ""))
        refs = (_rfind(pr, "retail_references") or {}).get("value") or []
        if refs:
            L += ["", "**مصادر الأسعار (للاستشهاد):**"]
            for ref in refs[:3]:
                L.append(f"- {(ref or {}).get('title')} — {(ref or {}).get('url')}"
                         f" — سُحب: {(ref or {}).get('retrieved_at')}")
        elif not points:
            L.append("- مراجع الأسعار: غير مرصودة")
        L.append("")

    # ── SWOT — أربع قوائم بدليل كل بند؛ الربع الفارغ معلن ────────────────────
    sw = top_m.get("swot") or {}
    L += ["## تحليل SWOT (قاعدي من حقائق مرصودة)", ""]
    for key, title in (("S", "القوة Strengths"), ("W", "الضعف Weaknesses"),
                       ("O", "الفرص Opportunities"), ("T", "التهديدات Threats")):
        L.append(f"### {title}")
        items = sw.get(key) or []
        if not items:
            L.append("- لا بند مرصوداً")
        for it in items:
            L.append(f"- {it.get('text')} — الدليل: {it.get('evidence')}")
        L.append("")
    if sw.get("note"):
        L += [f"> {sw['note']}", ""]

    # ── شرائح العملاء — segments with declared basis ─────────────────────────
    L += ["## شرائح العملاء", ""]
    segs = top_m.get("segments") or []
    if segs:
        for s in segs:
            L.append(f"- {s.get('segment')} — الأساس: {s.get('basis')}")
    else:
        L.append("بيانات غير كافية للشرائح — يتطلب وكيل المستهلك")
    L.append("")

    # ── دليل المورّدين والمصنّعين — supplier directory ───────────────────────
    L += ["## دليل المورّدين والمصنّعين", ""]
    sd = top_m.get("supplier_directory") or {}
    for key, title in (("saudi", "**مورّدون ومصنّعون سعوديون:**"),
                       ("target", "**موزّعون ومستوردون في السوق المستهدف:**")):
        L.append(title)
        items = sd.get(key) or []
        if not items:
            L.append("- لا مرشّحين مرصودين — فجوة معلنة")
        for e in items[:10]:
            L.append(f"- {_entry_text(e)}")
        L.append("")
    if sd.get("note"):
        L += [f"> {sd['note']}", ""]

    # ── الاشتراطات التنظيمية — بوابة الأهلية أولاً ثم بنود L1 ────────────────
    L += ["## الاشتراطات التنظيمية", ""]
    reg = _ragent(top_m, "regulatory")
    if r_bundle is None or not reg:
        L += [r_absent or "وكيل الاشتراطات لم يعمل في هذا التحليل", ""]
    else:
        gate_f = _rfind(reg, "eligibility_gate")
        if gate_f and gate_f.get("value"):
            L += ["**تحذير — بوابة أهلية أمامية:** هذا السوق يتطلب منشأة معتمدة "
                  "(EU 2017/625) قبل أي بند لاحق؛ لا بند أدناه يُعتبر سالكاً "
                  "قبل اجتيازها.", ""]
        checklist_f = _rfind(reg, "requirements_checklist")
        checklist = (checklist_f or {}).get("value") or []
        if checklist:
            for it in checklist:
                L.append(f"- {_req_text(it)}")
            L.append(f"- ({_f_srcline(checklist_f)})")
        else:
            L.append("- لا بنود اشتراطات مرصودة في مرجع L1 لهذا السوق "
                     "— فجوة معلنة")
        tf = _rfind(reg, "tariff_applied_pct")
        if tf and tf.get("value") is not None:
            L.append(f"- {_f_text(tf)} ({_f_srcline(tf)})")
        for g in reg.get("gaps") or []:
            L.append(f"- فجوة معلنة: {g}")
        L.append("")

    # ── سجل المخاطر — decision risks + raw WGI/LPI datapoints ───────────────
    L += ["## سجل المخاطر", ""]
    ed_risks = (ed or {}).get("risks") or []
    if ed_risks:
        for rk in ed_risks:
            L.append(f"- {rk.get('risk')} (الشدة: {rk.get('severity')}) — "
                     f"الدليل: {rk.get('evidence')}")
    else:
        L.append("- لا مخاطر مسجّلة في محرك القرار (§8)" if ed else
                 f"- {ed_absent}")
    for dp in top_m.get("risk") or []:
        if dp.get("value") is not None:
            src = str(dp.get("source") or "غير مرصود")
            if dp.get("retrieved_at"):
                src += f" | سُحب: {dp['retrieved_at']}"
            L.append(f"- {dp.get('note') or 'مؤشر خطر'}: {_fmt(dp['value'])} "
                     f"(المصدر: {src})")
    L.append("")

    # ── تغطية الأقسام — لكل قسم دون العتبة سطر النقص الصريح ─────────────────
    L += ["## تغطية الأقسام", ""]
    cov = top_m.get("section_coverage") or {}
    if cov:
        for sec, c in cov.items():
            flag = " ⚠ مصدر واحد — ثقة منخفضة" if c.get("low_confidence") else ""
            L.append(f"- {_SEC_AR.get(sec, sec)}: {c['contributed']}/"
                     f"{c['attempted']} (درجة {c['score']}){flag}")
            st = st_all.get(sec)
            if st and st.get("status") == "insufficient":
                L.append(f"  - {insufficient_line(_SEC_AR.get(sec, sec), st)}")
    else:
        L.append("- لا تغطية أقسام محسوبة")
    L.append("")

    # ── ملحق أثر المصادر — provenance appendix (لا فشل صامتاً) ──────────────
    L += ["## ملحق: أثر المصادر (المحاولات والإسهام)", ""]
    prov = view.get("provenance") or []
    if prov:
        for b in prov:
            L.append(f"- {b['source']}: أسهم {b['contributed']} من "
                     f"{b['attempted']} محاولة")
            for fl in b.get("failures") or []:
                L.append(f"  - فشل مُسجَّل: {fl}")
    else:
        L.append("- لا أثر مصادر مسجّلاً")
    L.append("")

    # ── حدود هذا التقرير — declared limits before the recommendation ────────
    L += ["## حدود هذا التقرير", ""]
    for x in (view.get("limits") or ["لا فجوات مرصودة في الأسواق العليا"])[:12]:
        L.append(f"- {x}")
    L.append("")

    # ── التوصية / المختصر — نفس سطور القالب، لا صياغة موازية ────────────────
    L += ["## التوصية / المختصر", ""]
    for line in view.get("brief") or []:
        L.append(f"- {line}")
    if view.get("note"):
        L += ["", str(view["note"])]
    L.append("")
    return "\n".join(L)
