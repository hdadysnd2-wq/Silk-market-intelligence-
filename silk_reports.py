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


def _fmt(v: object) -> str:
    """تنسيق قيمة للعرض — display formatting (None = فجوة معلنة)."""
    if v is None:
        return "— (لا بيانات)"
    if isinstance(v, float) and v >= 1000:
        return f"{v:,.0f}"
    return str(v)


def render_brief(view: dict, dashboard_url: str = "/") -> str:
    """المختصر (§10.4) — صفحة واحدة بتصميم "رسالة جوال"، من القالب حصراً."""
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
    L = [f"سِلك | {view.get('product')} (HS {view.get('hs_code')}) — "
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


def render_docx(view: dict, path: str) -> str:
    """التقرير الكامل Word (§10.3) — من القالب الموحّد حصراً.

    يعيد المسار عند النجاح؛ RuntimeError واضحة بلا python-docx.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(_DOCX_HINT) from exc

    doc = Document()
    # ١) الخلاصة التنفيذية أولاً (نجحت باختبار الخمس ثوانٍ — تُثبَّت).
    doc.add_heading(f"سِلك — تقرير سوق: {view.get('product')}", 0)
    d = view.get("decision") or {}
    doc.add_heading("الخلاصة التنفيذية", level=1)
    doc.add_paragraph(f"القرار: {d.get('verdict') or 'تعذّر الحكم'} "
                      f"(ثقة {d.get('confidence')}) — السوق الأول: "
                      f"{d.get('market') or '؟'}")
    doc.add_paragraph(f"لماذا: {d.get('why') or ''}")
    doc.add_paragraph(f"رمز HS: {view.get('hs_code')} "
                      f"(ثقة التصنيف {view.get('hs_confidence')}) | "
                      f"سنة البيانات: {view.get('year')} | "
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
                doc.add_paragraph(f"{t['name']}: {t['price_flag']} "
                                  f"(اكتمال الخيط {t['thread_completeness']})",
                                  style="List Bullet")
    else:
        doc.add_paragraph(cp.get("note") or "")

    # ٢ب) مشهد السوق الأول — أسعار/منافسون/موردون/اتجاه/ثقافة (الموجة ٩).
    #     يُعرض المرصود، ويُعلن الغائب «غير مرصود» بمصدره/مفتاحه المطلوب — لا
    #     اختلاق، وتقرير لا يعود «ناقصاً» بل صريحاً بما لديه وما ينقصه.
    top_m = (view.get("markets") or [{}])[0]

    def _sec(title: str, items: list, empty_hint: str, fmt) -> None:
        doc.add_heading(title, level=1)
        if items:
            for it in items:
                doc.add_paragraph(fmt(it), style="List Bullet")
        else:
            doc.add_paragraph(f"غير مرصود — {empty_hint}")

    _sec("أسعار المنتجات في السوق", top_m.get("prices"),
         "يتطلب طبقة أسعار السوق (LOCALPRICE_API_KEY) عبر «الدراسة العميقة»",
         lambda p: f"{p.get('title') or 'قائمة'}: {_fmt(p.get('price'))}"
                   + (f" {p['currency']}" if p.get("currency") else "")
                   + (f" — {p['store']}" if p.get("store") else ""))

    doc.add_heading("المنافسون", level=1)
    countries = top_m.get("supplier_countries") or []
    named = top_m.get("named_competitors") or []
    if countries:
        doc.add_paragraph("الدول المورّدة وحصصها:")
        for c in countries[:6]:
            doc.add_paragraph(f"{c.get('partner')}: {c.get('share')}% "
                              f"({_fmt(c.get('value_usd'))}$)", style="List Bullet")
    if named:
        doc.add_paragraph("شركات منافسة بالاسم:")
        for n in named[:8]:
            doc.add_paragraph(str(n), style="List Bullet")
    if not countries and not named:
        doc.add_paragraph("غير مرصود — الدول المورّدة تتطلب Comtrade (شبكة)؛ "
                          "والشركات بالاسم تتطلب مفتاح بحث (SEARCH_API_KEY).")

    _sec("الموردون والأعمال بالاسم", top_m.get("suppliers"),
         "يتطلب Google Maps / Volza / explee (مفاتيح)",
         lambda s: f"{s.get('name')} — {s.get('source')}")

    tr = top_m.get("trend") or {}
    doc.add_heading("اتجاه الاستيراد متعدد السنوات", level=1)
    if tr.get("series") and (tr.get("observed_years") or []):
        doc.add_paragraph(f"النمو {tr.get('growth_pct')}% "
                          f"(CAGR {tr.get('cagr_pct')}%) — {tr.get('note')}")
    else:
        doc.add_paragraph("غير مرصود — فعّل «مدى السنوات» (with_trend) وتحقّق من الشبكة.")

    doc.add_heading("ثقافة المستهلك ونبض السوق", level=1)
    culture = view.get("culture") or []
    if culture:
        for c in culture[:6]:
            doc.add_paragraph(str(c.get("title"))[:200], style="List Bullet")
    else:
        doc.add_paragraph("غير مرصود — يتطلب مفتاح بحث الويب (SEARCH_API_KEY).")

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
