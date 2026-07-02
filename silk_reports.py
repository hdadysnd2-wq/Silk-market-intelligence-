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
