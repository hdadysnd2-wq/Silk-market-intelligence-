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
import re

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


def _degraded_banner_text(view: dict) -> str | None:
    """نص لافتة التدهور — None إن لم يكن التشغيل متدهوراً (بلاغ حي: بوابة
    ما قبل التشغيل في api.py توسم `degraded=true` فقط عند allow_degraded=
    true صريح أو سباق نادر على حجز الميزانية؛ هذه اللافتة تجعل التدهور
    مرئياً في كل مشتق بدل هيكل يبدو كالمنتج النهائي)."""
    if not view.get("degraded"):
        return None
    reason = view.get("degraded_reason") or "طبقة كلود غير متاحة"
    return f"⚠ DEGRADED — نظام الذكاء الاصطناعي غير متاح ({reason})"


def _stamp_degraded_banner(doc, view: dict) -> None:
    """اطبع لافتة تدهور حمراء بارزة — تُستدعى عند الغلاف وأعلى كل قسم رئيسي
    من قسم البحث العميق. لا أثر إن لم يكن التشغيل متدهوراً."""
    text = _degraded_banner_text(view)
    if not text:
        return
    from docx.shared import RGBColor
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.color.rgb = RGBColor(0xCC, 0x00, 0x00)


def _fmt(v: object) -> str:
    """تنسيق قيمة للعرض — display formatting (None = فجوة معلنة)."""
    if v is None:
        return "—"
    if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) >= 1000:
        return f"{v:,.0f}"
    return str(v)


def _truncate_at_word(text: str, max_len: int) -> str:
    """قصّ نص عند حدّ كلمة كاملة — بلاغ حي (الموجة ٩): "لا تتوفر من أد"
    (كلمة مقطوعة منتصفها) كانت ناتجة عن قصّ حرفي بلا مراعاة حدود الكلمات
    (هنا، وفي ملاحظة استشهاد `run_llm_agent` — راجع الإصلاح المقابل هناك).
    لا يقصّ أبداً منتصف كلمة؛ يتراجع لآخر مسافة قبل الحد."""
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    sp = cut.rfind(" ")
    if sp > max_len * 0.5:  # لا تراجُع مفرط إن كانت الكلمة الأخيرة طويلة جداً
        cut = cut[:sp]
    return cut.rstrip() + "…"


def _clean_report_text(s: object, max_len: int = 300) -> str:
    """نص آمن للعرض — بلاغ حي (الموجة ٨): لا يجوز أن يتسرّب رد كلود الخام
    غير المفسَّر (كتلة JSON/سياج ```) لواجهة تقرير — يُستبدَل بملخّص نظيف
    بدل عرضه حرفياً؛ التفاصيل الكاملة تبقى في أثر التتبّع (data/traces/).
    القصّ عند حدّ كلمة (الموجة ٩) — لا كلمة مقطوعة منتصفها بعد الآن."""
    text = str(s or "").strip()
    if not text:
        return text
    if text.lstrip().startswith(("{", "```")):
        return "بند تقني غير قابل للعرض المباشر — التفاصيل الكاملة في أثر التتبّع."
    return _truncate_at_word(text, max_len)


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")
_CODE_SPAN_RE = re.compile(r"`([^`]*)`")


def _strip_inline_markdown(line: str) -> str:
    """أزل تنسيق Markdown من فقرة عادية — بلاغ حي (الموجة ٩): "**عريض**"/
    "`كود`"/"#" خام كانت تظهر حرفياً على وجه التقرير. العناوين '## '/'### '
    تتحوّل لعناوين حقيقية في موضع آخر (قبل بلوغ هذه الدالة) — هذه للفقرات
    العادية التي تحوي تنسيقاً inline فقط."""
    line = _BOLD_RE.sub(r"\1", line)
    line = _ITALIC_RE.sub(r"\1", line)
    line = _CODE_SPAN_RE.sub(r"\1", line)
    if line.lstrip().startswith("#"):
        line = line.lstrip("#").strip()
    return line


def _is_markdown_table_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _is_markdown_table_separator(line: str) -> bool:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return bool(cells) and all(c and set(c) <= {"-", ":"} for c in cells)


# شارة الأدلة رُحِّلت إلى silk_narrative.evidence_badge (P2) — لتُستعمل من
# نموذج العرض (silk_render._deep_research_view) لا من طبقة عرض النص وحدها.
# الاسم القديم يبقى هنا كتوافق خلفي لكل مستدعي هذا الملف.
from silk_narrative import (  # noqa: E402
    EVIDENCE_SECONDARY_MIN as _EVIDENCE_SECONDARY_MIN,
    EVIDENCE_VERIFIED_MIN as _EVIDENCE_VERIFIED_MIN,
    evidence_badge as _evidence_badge,
)


# سدّ تسريب (الطبقة ٦): _verdict_tone/_VERDICT_LABELS_AR انتقلتا إلى
# silk_render.py — مصدر واحد يستهلكه غلاف/خلاصة docx هنا ولوحة الويب معاً
# (view["deep_research"]["verdict_tone"/"verdict_label"])، بدل نسخة بايثون
# ونسخة JS منفصلتين قد تختلفان لنفس الرمز.
from silk_render import _VERDICT_LABELS_AR, _verdict_tone  # noqa: E402


# ── هوية سِلك البصرية (الموجة ١١، §11.1) — config/branding.yaml ─────────

_BRANDING_PATH = "config/branding.yaml"
_BRANDING_DEFAULTS = {
    "logo_path": "", "primary_color": "1B3B6F", "secondary_color": "C9A227",
    "contact_footer": "سِلك لذكاء الأسواق",
}


def _load_branding(path: str = _BRANDING_PATH) -> dict:
    """اقرأ هوية سِلك البصرية — محلّل مسطّح خفيف (key: value فقط، بلا
    تعشيش) بلا PyYAML (ليست ضمن requirements.txt؛ المشروع stdlib-first —
    راجع تعليق أعلى config/branding.yaml). ملف غائب/سطر مشوَّه = القيمة
    الافتراضية لذلك المفتاح فقط، لا فشل كامل."""
    out = dict(_BRANDING_DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or ":" not in s:
                    continue
                k, v = s.split(":", 1)
                k, v = k.strip(), v.strip()
                if k in out and v:
                    out[k] = v
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001 — الهوية تحسين عرض لا شرط توليد
        log.warning("branding config unavailable (%s): %s", path, e)
    return out


def _hex_to_rgbcolor(hex_str: str):
    from docx.shared import RGBColor
    h = (hex_str or "").lstrip("#")
    try:
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except Exception:  # noqa: BLE001 — لون مشوَّه = الكحلي الافتراضي
        return RGBColor(0x1B, 0x3B, 0x6F)


def _set_cell_shading(cell, hex_color: str) -> None:
    """ظلّل خلفية خلية جدول — python-docx لا يعرض هذا كخاصية عليا؛ عنصر
    w:shd عبر oxml مباشرة (نمط موثَّق شائع لتلوين رؤوس/أشرطة الجداول)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), (hex_color or "").lstrip("#") or "FFFFFF")
    cell._tc.get_or_add_tcPr().append(shd)


def _add_page_number_field(paragraph) -> None:
    """أدرج حقل رقم الصفحة الديناميكي (PAGE) — python-docx لا يعرض حقول
    Word كخاصية عليا؛ نمط oxml موثَّق شائع (w:fldChar begin/instrText/end)."""
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def _add_cover_wordmark(doc, branding: dict) -> None:
    """شعار سِلك على الغلاف — صورة فعلية إن وُجد `logo_path` صالح، وإلا
    نص نائب ("[شعار سِلك]") بلون سِلك الأساس. لا استثناء يُسقِط التوليد
    إن تعذّرت قراءة الصورة (مسار خاطئ/صيغة غير مدعومة) — رجوع للنص النائب."""
    logo_path = branding.get("logo_path")
    if logo_path:
        try:
            import os
            if os.path.exists(logo_path):
                doc.add_picture(logo_path, width=_docx_inches(1.5))
                return
        except Exception as e:  # noqa: BLE001 — الشعار تحسين عرض لا شرط
            log.warning("cover logo unavailable (%s): %s", logo_path, e)
    p = doc.add_paragraph()
    run = p.add_run("[شعار سِلك]")
    run.bold = True
    run.font.color.rgb = _hex_to_rgbcolor(branding["primary_color"])


def _docx_inches(n: float):
    from docx.shared import Inches
    return Inches(n)


def _add_page_header_footer(doc, title: str) -> None:
    """رأس/تذييل ثابتان لكل صفحة — عنوان التقرير أعلى، ورقم صفحة ديناميكي
    + سطر هوية سِلك أسفل (الموجة ١١، §11.1: تناسق بصري عبر كل صفحات
    التقرير، لا الغلاف فقط)."""
    branding = _load_branding()
    section = doc.sections[0]
    hp = section.header.paragraphs[0] if section.header.paragraphs \
        else section.header.add_paragraph()
    hp.text = title
    fp = section.footer.paragraphs[0] if section.footer.paragraphs \
        else section.footer.add_paragraph()
    fp.add_run(branding["contact_footer"] + " — صفحة ")
    _add_page_number_field(fp)


# لون شارة الحكم بالـtone — conditional (دخول مشروط) لون مستقل (أخضر مزرقّ)
# يميّزه عن go الأخضر وwatch الكهرماني (بلاغ مراجعة المالك على النموذج).
_VERDICT_TEXT_COLORS = {"go": (0x1E, 0x7D, 0x32), "conditional": (0x00, 0x69, 0x5C),
                        "watch": (0xB8, 0x86, 0x0B),
                        "nogo": (0xC0, 0x00, 0x00), "unknown": (0x60, 0x60, 0x60)}
_VERDICT_HIGHLIGHTS = {"go": "BRIGHT_GREEN", "conditional": "TEAL",
                       "watch": "YELLOW", "nogo": "RED"}


def _add_verdict_badge(doc, vtxt: str) -> None:
    """شارة حكم ملوّنة على الغلاف — بلاغ حي (الموجة ٩، P0-A): "درجات تبدو
    بلا سند" — الحكم النصي وحده مدفون بين حقول الجدول؛ شارة بصرية بارزة
    (تظليل + لون + حجم) تجعل التوصية أول ما تراه العين، كتقرير احترافي."""
    from docx.shared import Pt, RGBColor
    tone = _verdict_tone(vtxt)
    p = doc.add_paragraph()
    run = p.add_run(f"  {_VERDICT_LABELS_AR[tone]}  ")
    run.bold = True
    run.font.size = Pt(16)
    rgb = _VERDICT_TEXT_COLORS[tone]
    run.font.color.rgb = RGBColor(*rgb)
    try:
        from docx.enum.text import WD_COLOR_INDEX
        name = _VERDICT_HIGHLIGHTS.get(tone)
        if name:
            run.font.highlight_color = getattr(WD_COLOR_INDEX, name)
            run.font.color.rgb = RGBColor(0x00, 0x00, 0x00)
    except Exception:  # noqa: BLE001 — التظليل تحسين عرض لا شرط توليد
        pass


def _render_markdown_table(doc, table_lines: list[str]) -> None:
    """حوّل جدول Markdown (| عمود | عمود |) لجدول Word حقيقي — بلاغ حي
    (الموجة ٩): سلاسل رقمية (تدفقات استيراد، سلّم أسعار، اشتراطات،
    ديموغرافيا) كانت تُعرض نقاطاً سردية مبعثرة بدل جدول واحد يقارَن بنظرة."""
    rows = []
    for ln in table_lines:
        if _is_markdown_table_separator(ln):
            continue
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:  # رأس فقط أو فارغ — لا جدول ذو معنى
        return
    headers, *data = rows
    n = len(headers)
    norm = [(r + [""] * n)[:n] for r in data]
    caption = "جدول: " + " · ".join(h for h in headers if h)  # الموجة ١١
    _add_table(doc, headers, norm, caption=caption)


def _narrative_exec_summary(view: dict) -> list[str]:
    """خلاصة تنفيذية — التحليل الاحترافي (ai_report) إن توفر، وإلا exec_summary.

    `view["ai_report"]` (silk_ai_judge.ai_report، كلود) فقرات سردية احترافية
    مبنية على حزمة البحث الكاملة للسوق الأول + الأسواق المرتّبة؛ عند غيابه
    (لا مفتاح/فشل النداء) يُرجَع لـ `exec_summary` الحتمية في silk_narrative
    (النسخة الأولى هنا كانت تعيد صياغة الحقول لكنها ما تزال تمرّر «السبب
    التجاري: score 0.636 في النطاق الشرطي» حرفياً — شرط كود على وجه التقرير؛
    exec_summary تبني الفقرات الثلاث من الأرقام المرصودة نفسها بعربية بشرية،
    بلا درجة معيارية ولا اسم وكيل ولا شرط كود). كلا المسارين مبنيّ حصراً على
    حقول محسوبة فعلاً — لا اختلاق.
    """
    ai_text = view.get("ai_report")
    if ai_text:
        return [p.strip() for p in str(ai_text).split("\n") if p.strip()]
    from silk_narrative import exec_summary
    paras = exec_summary(view)
    note = view.get("ai_report_note")
    return paras + [str(note)] if note else paras


def _market_scope_paragraph(view: dict) -> str:
    """فقرة تعريف السوق ونطاقه (مواصفة تقرير عالمي §3) — ما يشمله التقرير
    وما يستثنيه بجملة واحدة، من حقول محسوبة — لا حكم جديد يُضاف."""
    h = view.get("header") or {}
    product = h.get("product") or view.get("product") or "—"
    hs = view.get("hs_code") or h.get("hs_code") or "—"
    n_markets = len(view.get("markets") or [])
    top_market = h.get("target_market") or "—"
    scope_txt = ("سوق واحد مرشّح" if n_markets == 1
                else f"{n_markets} أسواق مرشّحة")
    return (f"يشمل هذا التقرير: صادرات {product} (رمز HS {hs}) من المملكة "
            f"العربية السعودية، مُقيَّمة عبر {scope_txt}، "
            f"ومفصَّلة بعمق للسوق الأعلى ترتيباً ({top_market}). يستثني "
            "هذا التقرير: التسعير التفصيلي بالتجزئة والملفات المالية "
            "للمنافسين (تتطلبان خدمة التعميق المدفوعة)، وتحليل "
            "الشرائح السلوكية للعملاء واستخبارات الطلب المباشرة (تتطلبان "
            "بحثاً أولياً — مقابلات أو استبيانات — لم يُجرَ بعد).")


def _methodology_lines(view: dict) -> list[str]:
    """أسطر قسم المنهجية (مواصفة تقرير عالمي §2) — من حقول محسوبة فعلاً.

    P1: تحفّظ «قراءة أولية» يُقال هنا مرة واحدة هادئة — لا يتكرر في كل قسم؛
    وسطر كفاية البيانات يُترجم (لا اسم صنف وكيل على وجه التقرير).
    """
    from silk_narrative import translate_gaps
    h = view.get("header") or {}
    prov = view.get("provenance") or []
    sources = sorted({str(b.get("source")) for b in prov
                      if b.get("contributed")})
    lines = [f"سنة البيانات المعتمدة: {_data_year_label(view)}.",
             f"تغطية البيانات الإجمالية لهذا التحليل: {h.get('coverage_pct')}%."]
    if sources:
        lines.append("المصادر التي أسهمت فعلياً في هذا التشغيل: "
                     + "، ".join(sources) + ".")
    lines.append("كل رقم في هذا التقرير يُعرض مع مصدره وتاريخ سحبه؛ "
                 "القيمة غير المتاحة تُعرض «—».")
    suff = (view.get("decision") or {}).get("sufficiency")
    if suff:
        lines.append(translate_gaps([suff])[0])
    lines.append("هذه قراءة أولية مبنية على البيانات العامة المتاحة "
                 "وقت الإعداد.")
    return lines


def _gap_ar(g: object) -> str:
    """فجوة داخلية → عربية هادئة للعرض — display-only translation (5b)."""
    from silk_narrative import translate_gaps
    return translate_gaps([g])[0]


def _gap_list_ar(gaps: list) -> list[str]:
    """قائمة فجوات مترجمة للعرض — display-only batch translation (5b)."""
    from silk_narrative import translate_gaps
    return translate_gaps(gaps)


def _data_year_label(view: dict) -> str:
    """سنة البيانات الفعلية — the year actually used, flagging the declared fallback.

    عند تراجُع المحرّك إلى أحدث سنةٍ منشورة (السنة المطلوبة لم تُنشر بعد) نعرض السنة
    الفعلية مع سبب التراجُع — لا يظهر رقمُ سنةٍ فارغةٍ كأنه سنة التحليل.
    """
    dy = view.get("data_year", view.get("year"))
    if dy is None:
        return "—"   # فجوة معلنة — لا يُطبع نص "None" الحرفي (تدقيق: /research بلا سنة)
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
    """سطر الاكتشاف — metric: value unit [+ وسم «مُقدَّر» ونص المعادلة إن نموذجاً].

    اسم المقياس الداخلي (snake_case) يُعرَّب دوماً — لا يصل وجه العميل
    خاماً (بلاغ تدقيق: "tam_usd"/"hhi" ظهرت حرفياً في جداول docx/markdown)."""
    from silk_narrative import internal_ar
    unit = f" {f.get('unit')}" if f.get("unit") else ""
    txt = f"{internal_ar(f.get('metric'))}: {_fmt(f.get('value'))}{unit}"
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
    from silk_narrative import confidence_phrase
    parts = []
    for s in (f or {}).get("sources") or []:
        seg = str(s.get("source") or "غير مرصود")
        if s.get("retrieved_at"):
            seg += f" | سُحب: {s['retrieved_at']}"
        if s.get("confidence") is not None:
            seg += f" | ثقة: {confidence_phrase(s['confidence'])}"
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
    """المختصر (§10.4) — صفحة واحدة بتصميم "رسالة جوال"، من القالب حصراً.

    P1 (طبقة السرد): أسماء المقاييس الداخلية (market_size) ورمز الحكم الآلي
    وشعارات النزاهة أُزيلت من الوجه — سطر المصدر مع كل رقم حاضر هو إشارة
    النزاهة الوحيدة، والقيم نفسها بلا أي تغيير.
    """
    from silk_narrative import (GAP_WORD, competition_phrase, country_ar,
                                fmt_money, fmt_pct, internal_ar, verdict_ar)
    _assert_production_clean(view)
    d = view.get("decision") or {}
    cp = view.get("competitive_position") or {}
    top = (view.get("markets") or [{}])[0]
    dr = view.get("deep_research")
    numbers = []
    if dr:  # الموجة ٤: أرقام من تقاطعات المحلل الشامل لا components_detail
        by_cat = (dr.get("analyst") or {}).get("by_category") or {}
        for cat in ("demand", "price_competitiveness", "entry_cost"):
            items = by_cat.get(cat) or []
            if items:
                numbers.append(f"• {_CATEGORY_AR.get(cat, cat)}: "
                               f"{items[0].get('value')} "
                               f"[{items[0].get('source', '؟')}]")
    else:
        for c in (top.get("components_detail") or []):
            if c.get("value") is None:
                continue
            name = c.get("name")
            # كل مقياس بصيغته البشرية — مؤشر HHI الخام لا يصل وجه المستخدم أبداً.
            val = (fmt_money(c["value"]) if name in ("market_size",
                                                     "demand_capacity")
                   else fmt_pct(c["value"]) if name == "saudi_position"
                   else competition_phrase(c["value"]) if name == "competition"
                   else _fmt(c["value"]))
            numbers.append(f"• {internal_ar(name)}: {val} "
                           f"[{c.get('source', '؟')}]")
            if len(numbers) == 3:
                break
    if not numbers:
        numbers = [f"• {GAP_WORD}"]
    L = ([] if not view.get("test_run") else
         ["⚠ TEST RUN — تشغيل برهاني ببدائل موسومة، ليس تقريراً إنتاجياً"])
    market_ar = (((dr or {}).get("market") or {}).get("name_ar")
                if dr else country_ar(top.get("iso3"), d.get("market")))
    L += [f"سِلك | {view.get('product')} — سوق {market_ar} | "
          f"قراءة أولية {view.get('year')}",
         "",
         view.get("brief", [""])[0] if view.get("brief") else
         f"التوصية: {verdict_ar(d.get('verdict'))}",
         "", "أبرز الأرقام:", *numbers, ""]
    if len(view.get("brief") or []) > 1:
        L += view["brief"][1:3]
    else:
        L.append(cp.get("note", ""))
    L += ["", f"التفاصيل الكاملة باللوحة: {dashboard_url}"]
    return "\n".join(L)


# ── بناة أقسام Word الجديدة (§7) — new docx section builders (pure display) ──

def _add_table(doc, headers: list[str], rows: list[list],
               caption: str | None = None) -> None:
    """جدول Word موحّد سِلك — رأس بلون سِلك الأساس وخط أبيض، أشرطة متناوبة
    خفيفة، تسمية اختيارية أعلاه؛ no rows => no-op.

    مراجعة المشروع: النسخة الحية من التقرير (docx، ما يُرسله المستخدم فعلياً)
    كانت نقاطاً سردية بحتة بينما نظيرتها Markdown تستخدم جداول فعلية لنفس
    البيانات (قرار الدخول مثلاً) — تناقضٌ بين الصيغتين، وواحدة من أوضح علامات
    "تقرير غير احترافي" بمقارنة أي منصة أبحاث سوق مرجعية (Country Commercial
    Guides وITC Trade Map وEuromonitor). لا بيانات جديدة، عرضٌ صرفٌ فقط —
    "Table Grid" نمطٌ مدمج في python-docx (بلا قالب خارجي). الموجة ١١
    (§11.1): رأس/أشرطة ملوّنة من `config/branding.yaml` — تقرير موحَّد
    الهوية بصرياً بدل جدول Word افتراضي عادي.
    """
    if not rows:
        return
    if caption:
        cap = doc.add_paragraph()
        run = cap.add_run(caption)
        run.italic = True
        run.bold = True
    branding = _load_branding()
    primary = branding["primary_color"]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = str(h)
        _set_cell_shading(hdr[i], primary)
        if hdr[i].paragraphs[0].runs:
            r = hdr[i].paragraphs[0].runs[0]
            r.bold = True
            r.font.color.rgb = _hex_to_rgbcolor("FFFFFF")
    for row_idx, vals in enumerate(rows):
        cells = table.add_row().cells
        for i, v in enumerate(vals):
            cells[i].text = str(v) if v is not None else "—"
        if row_idx % 2 == 1:  # شريط متناوب خفيف كل صف زوجي (١-مرتكز)
            for c in cells:
                _set_cell_shading(c, "F2F2F2")


def _docx_entry_strategy(doc, m: dict) -> None:
    """استراتيجية دخول السوق — فصلٌ مستقل يركّب توصية الدخول من أرقامٍ مرصودة.

    مراجعة المشروع: التوصية («ادخل عبر موزّع قائم») كانت مدفونة كسطرٍ واحد
    داخل «الخطوات الأولى» — أي منصة مرجعية (Country Commercial Guides) تُفرد
    لها فصلاً. يُركِّب هنا فقط ما هو مرصود فعلاً (تركّز الموردين + بوابة
    الأهلية + عدد المرشّحين بالاسم) في فقرة واحدة مسبَّبة؛ لا رقم جديد، لا
    اختلاق — تجميعٌ لحقائق موجودة أصلاً في أقسام أخرى من نفس التقرير.
    """
    doc.add_heading("استراتيجية دخول السوق", level=2)
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
    """قرار الدخول — verdict/score/pillars/conditions/risks.

    سدّ تسريب (الطبقة ٨، قرار المالك): العنوان والنص كانا يحملان رطانة
    مسار العمل الداخلي ("المحرك الموزون §8"، "بوابة GATE 3") ورمز مفتاح
    خام (A/B) — عنوان تجاري صرف الآن، وخيار الأوزان يُعرض باسمه الوصفي
    (`weights_label`) لا رمزه (`weights_option` يبقى كما هو في المصدر
    لأغراض داخلية/تتبّع فقط)."""
    doc.add_heading("قرار الدخول", level=2)
    ed, absent = _entry_decision_of(m)
    if ed is None:
        doc.add_paragraph(absent)
        return
    from silk_decision import _WEIGHT_LABEL_AR
    from silk_narrative import confidence_phrase, verdict_ar
    doc.add_paragraph(f"الحكم: {verdict_ar(ed.get('verdict'))} | "
                      f"النقاط: {_fmt(ed.get('score'))}"
                      f" | الثقة: {confidence_phrase(ed.get('confidence'))}")
    doc.add_paragraph(f"أساس الثقة: {ed.get('confidence_basis')}")
    sbo = ed.get("scores_by_option") or {}
    weights_label = ed.get("weights_label") or ed.get("weights_option") or ""
    other_label = _WEIGHT_LABEL_AR.get(
        "B" if ed.get("weights_option") == "A" else "A", "")
    other_score = sbo.get("B" if ed.get("weights_option") == "A" else "A")
    doc.add_paragraph(f"منهجية الترجيح المعتمدة: {weights_label} — النقاط "
                      f"{_fmt(ed.get('score'))} (بديل مقارنة، {other_label}: "
                      f"{_fmt(other_score)})")
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
    doc.add_heading("حجم السوق — TAM/SAM/SOM", level=2)
    r, absent = _research_bundle(m)
    if r is None:
        doc.add_paragraph(absent)
        return
    ag = _ragent(m, "market_size")
    valued = [f for f in (ag.get("findings") or []) if f.get("value") is not None]
    if valued:
        from silk_narrative import internal_ar
        _add_table(
            doc, ["المؤشر", "القيمة", "النوع", "المصدر"],
            [[internal_ar(f.get("metric")),
              f"{_fmt(f.get('value'))}{(' ' + f['unit']) if f.get('unit') else ''}",
              (_MODELED_TAG if f.get("modeled") else "رصد مباشر"),
              _f_src_bare(f)]
             for f in valued])
        for f in valued:
            if f.get("modeled") and f.get("formula"):
                doc.add_paragraph(
                    f"معادلة «{internal_ar(f.get('metric'))}»: {f['formula']}",
                    style="Intense Quote")
    else:
        doc.add_paragraph("لا اكتشافات مرصودة لحجم السوق")
    for g in ag.get("gaps") or []:
        doc.add_paragraph(f"غير متوفر: {_gap_ar(g)}", style="List Bullet")


def _docx_competition_research(doc, m: dict) -> None:
    """طبقتا المنافسة من حزمة البحث — شركات بالاسم + أرقام الطبقة الدولية."""
    ag = _ragent(m, "competitor")
    if not ag:
        return
    doc.add_heading("شركات بالاسم (مرشّحون غير موثَّقين)", level=3)
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
        from silk_narrative import confidence_phrase
        doc.add_paragraph(f"كيانات غير موثَّقة — الثقة {confidence_phrase(0.4)} "
                          "— أكّدها قبل أي تعاقد.")
    else:
        doc.add_paragraph("لا شركات مرصودة بالاسم في هذا التشغيل "
                          "(أسماء الأعمال تأتي من Google Places حصراً)")
    if refs:
        doc.add_heading("مراجع ويب للمراجعة اليدوية (ليست أسماء منافسين)",
                        level=3)
        for n in refs[:8]:
            doc.add_paragraph(_entry_text(n), style="List Bullet")
    doc.add_paragraph("الطبقة الدولية (تركّز الموردين — UN Comtrade):")
    from silk_narrative import internal_ar
    metrics_rows = []
    for metric in ("hhi", "top_supplier_share_pct", "saudi_share_pct"):
        f = _rfind(ag, metric)
        metric_ar = internal_ar(metric)
        if f and f.get("value") is not None:
            # وحدة الحقيقة (%) كانت تُسقَط هنا — نفس البند في نسخة الماركداون
            # (_f_text) يعرضها صحيحة؛ إصلاح تناسق: كلاهما يقرأ f['unit'] الآن.
            unit = f" {f['unit']}" if f.get("unit") else ""
            metrics_rows.append([metric_ar, f"{_fmt(f.get('value'))}{unit}",
                                 _f_src_bare(f)])
            if f.get("note"):
                metrics_rows[-1].append(_gap_ar(f["note"]))
        else:
            metrics_rows.append([metric_ar, "—", "—"])
    max_cols = max(len(r) for r in metrics_rows)
    for r in metrics_rows:
        while len(r) < max_cols:
            r.append("")
    _add_table(doc, ["المؤشر", "القيمة", "المصدر", "ملاحظة"][:max_cols],
              metrics_rows)


def _docx_pricing_layers(doc, m: dict) -> None:
    """التسعير بطبقتيه — الحدودية (نماذج موسومة بمعادلاتها) ثم التجزئة ومراجعها."""
    doc.add_heading("التسعير بطبقتيه", level=2)
    r, absent = _research_bundle(m)
    if r is None:
        doc.add_paragraph(absent)
        return
    ag = _ragent(m, "pricing")
    doc.add_paragraph("الطبقة الحدودية (قيم وحدة كومتريد):")
    from silk_narrative import internal_ar
    border_rows, border_formulas = [], []
    for metric in ("border_unit_value_usd_kg", "saudi_border_unit_value_usd_kg",
                   "margin_at_border_pct"):
        f = _rfind(ag, metric)
        metric_ar = internal_ar(metric)
        if f and f.get("value") is not None:
            unit = f" {f['unit']}" if f.get("unit") else ""
            border_rows.append([
                metric_ar, f"{_fmt(f.get('value'))}{unit}",
                (_MODELED_TAG if f.get("modeled") else "رصد مباشر"),
                _f_src_bare(f)])
            if f.get("modeled") and f.get("formula"):
                border_formulas.append(f"معادلة «{metric_ar}»: {f['formula']}")
        else:
            border_rows.append([metric_ar, "—", "—", "—"])
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
        # فجوة القسم المعلنة تُطبع مترجمةً للعرض (_gap_ar) — لا سباكة
        # إنجليزية (ملاحظة الحارس المدفوع/أسماء المفاتيح) على وجه التقرير.
        gap = next((g for g in (ag.get("gaps") or []) if "retail_prices" in g),
                   "أسعار التجزئة: غير متوفرة في هذا التشغيل")
        doc.add_paragraph(_gap_ar(gap), style="List Bullet")
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
    doc.add_heading("تحليل SWOT (قاعدي من حقائق مرصودة)", level=2)
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
                cell.add_paragraph("—")
            for it in items:
                cell.add_paragraph(f"{it.get('text')} — الدليل: "
                                   f"{it.get('evidence')}", style="List Bullet")
    if sw.get("note"):
        doc.add_paragraph(str(sw["note"]))


def _docx_segments(doc, m: dict) -> None:
    """شرائح العملاء — segment + basis؛ الفارغ يُعلن لا يُخترع."""
    doc.add_heading("شرائح العملاء", level=2)
    segs = m.get("segments") or []
    if not segs:
        doc.add_paragraph("بيانات غير كافية للشرائح — التقسيم السلوكي/"
                          "الديموغرافي يتطلب بحثاً أولياً (مقابلات أو "
                          "استبيانات) لم يُجرَ بعد؛ لا يُشتق من بيانات ثانوية")
        return
    for s in segs:
        doc.add_paragraph(f"{s.get('segment')} — الأساس: {s.get('basis')}",
                          style="List Bullet")


def _docx_supplier_directory(doc, m: dict) -> None:
    """دليل المورّدين والمصنّعين — قائمتا السعودية والسوق المستهدف + الملاحظة."""
    doc.add_heading("دليل المورّدين والمصنّعين", level=2)
    sd = m.get("supplier_directory") or {}
    for key, title in (("saudi", "مورّدون ومصنّعون سعوديون:"),
                       ("target", "موزّعون ومستوردون في السوق المستهدف:")):
        doc.add_paragraph(title)
        items = sd.get(key) or []
        if not items:
            doc.add_paragraph("—",
                              style="List Bullet")
        for e in items[:10]:
            doc.add_paragraph(_entry_text(e), style="List Bullet")
    if sd.get("note"):
        doc.add_paragraph(str(sd["note"]))


def _docx_regulatory(doc, m: dict) -> None:
    """الاشتراطات التنظيمية — بوابة الأهلية أولاً ثم بنود L1 بجهاتها وروابطها."""
    doc.add_heading("الاشتراطات التنظيمية", level=2)
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
        doc.add_paragraph("لا بنود اشتراطات في مرجع سِلك لهذا السوق — غير متوفر")
    tf = _rfind(ag, "tariff_applied_pct")
    if tf and tf.get("value") is not None:
        doc.add_paragraph(_f_text(tf))
        doc.add_paragraph(_f_srcline(tf), style="Intense Quote")
    for g in ag.get("gaps") or []:
        doc.add_paragraph(f"غير متوفر: {_gap_ar(g)}", style="List Bullet")


_CATEGORY_AR = {
    "demand": "الطلب الفعلي القابل للتوجيه",
    "entry_cost": "تكلفة وصعوبة الدخول",
    "price_competitiveness": "التنافسية السعرية",
    "entry_door": "أبواب الدخول الأكثر أماناً",
    "swot": "SWOT من منظور المصدّر السعودي",
}


def _docx_deep_research(doc, view: dict) -> None:
    """قسم البحث العميق (الموجة ٤، V5) — ١٢ بعثة + محلل + حكم + تقرير مراجَع.

    يُستدعى إضافياً فقط عند `view["deep_research"]` (نتيجة /research) — لا
    يمسّ الأقسام الأربعة عشر القائمة لتقرير /analyze الكلاسيكي.
    """
    dr = view.get("deep_research")
    if not dr:
        return
    doc.add_heading("قسم البحث العميق — التقاطعات الخمسة والمحلل الشامل",
                    level=1)
    _stamp_degraded_banner(doc, view)

    # نفس تصنيف/تعريب الحكم المستعمَل في الغلاف (_VERDICT_LABELS_AR عبر
    # _verdict_tone) — لا مصدر عرض ثانٍ قد يختلف نصّه عن الأول لنفس الرمز
    # (اختبار اتساق: الحكم يظهر متطابقاً حرفياً في الخلاصة وهنا معاً).
    market = dr.get("market") or {}
    verdict = dr.get("verdict") or {}
    ai = verdict.get("ai") or {}
    v_raw = ai.get("verdict") or verdict.get("verdict") or ""
    doc.add_paragraph(
        f"السوق: {market.get('name_ar') or market.get('name_en')} "
        f"({market.get('iso3')}) — الحكم: "
        f"{_VERDICT_LABELS_AR[_verdict_tone(v_raw)]}")
    if ai.get("reasoning"):
        doc.add_paragraph(str(ai["reasoning"]), style="Intense Quote")

    doc.add_heading("ملخّص مصادر البحث", level=2)
    _stamp_degraded_banner(doc, view)
    missions = dr.get("missions") or {}
    # الاسم التجاري العربي (view label) بدل مفتاح snake_case الداخلي —
    # بلاغ مالك: "pricing_scout" وأخواتها ظهرت حرفياً في جدول العميل.
    _add_table(doc, ["البعثة", "الحالة", "الملخّص"], [
        [m.get("label") or key,
         "فشلت/بلا أدلة" if m.get("failed") else "ناجحة",
         _clean_report_text(m.get("summary"))]
        for key, m in missions.items()])

    # Phase 3 (بلاغ حي: "تقرير احترافي لا تفريغ بيانات"): التقرير السردي
    # (كاتب التقرير) يُعرض أولاً — فقرات تحليلية تُفسّر الأرقام لقرار الدخول،
    # بما فيها التقاطعات الخمسة كأقسام فرعية '### ' سردية — قبل ملحق الأدلة
    # الرقمية الخام (كان الترتيب معكوساً: نقاط خام تسبق أي سرد).
    if dr.get("report", {}).get("text"):
        doc.add_heading("التقرير الكامل (كاتب التقرير، مراجَع)", level=2)
        _stamp_degraded_banner(doc, view)
        lines = str(dr["report"]["text"]).splitlines()
        i, n = 0, len(lines)
        while i < n:
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            if line.startswith("### "):
                # عناوين فرعية عامة (الموجة ١٠: "خارطة طريق الدخول" داخل
                # "التوصيات الاستراتيجية" مثلاً) — بلا هذا كانت "### السطر"
                # تظهر نصاً خاماً بثلاث علامات # حرفية بدل عنوان فعلي.
                doc.add_heading(line[4:].strip(), level=4)
                i += 1
                continue
            if line.startswith("## "):
                heading_text = line[3:].strip()
                doc.add_heading(heading_text, level=3)
                # الموجة ١٠: نتائج بوابة الجودة غير القابلة للإصلاح تُلحَق
                # هنا برمجياً داخل قسم "منهجية البحث ونطاقه" — مهنياً، لا
                # لافتة تحذير على الغلاف ولا صمت (silk_quality_gate.py).
                if "منهجية" in heading_text:
                    notes = ((dr.get("quality_gate") or {})
                            .get("methodology_notes") or [])
                    if notes:
                        doc.add_heading("حدود المنهجية وجودة البيانات",
                                        level=4)
                        for note in notes:
                            doc.add_paragraph(str(note), style="List Bullet")
                i += 1
                continue
            if _is_markdown_table_row(line):
                # بلاغ حي (الموجة ٩): سلاسل رقمية (استيراد/أسعار/اشتراطات/
                # ديموغرافيا) كانت نقاطاً سردية مبعثرة — تُجمَع أسطر الجدول
                # المتتالية وتُحوَّل لجدول Word حقيقي واحد.
                block = []
                while i < n and _is_markdown_table_row(lines[i].strip()):
                    block.append(lines[i].strip())
                    i += 1
                _render_markdown_table(doc, block)
                continue
            stripped = _strip_inline_markdown(line)
            # سطر الخلاصة الإلزامي لكل قسم (P0-C، الموجة ٩) — يُكتشَف نصياً
            # (لا بالاعتماد على ** الحرفية من كلود، التي تُزال أعلاه أصلاً)
            # ويُغمَّق برمجياً — إخلاص شكلي لا يعتمد على انضباط كلود بالسياج.
            if stripped.startswith("ماذا يعني هذا لقرارك:"):
                p = doc.add_paragraph()
                p.add_run(stripped).bold = True
            else:
                doc.add_paragraph(stripped)
            i += 1

    doc.add_heading("ملحق — الأدلة الرقمية الداعمة للتقاطعات الخمسة", level=2)
    _stamp_degraded_banner(doc, view)
    doc.add_paragraph("كل نقطة أدناه هي الحقيقة الخام (بمصدرها) التي بُني "
                      "عليها السرد أعلاه — للتحقق المباشر لا كبديل عنه.",
                      style="Intense Quote")
    analyst = dr.get("analyst") or {}
    by_cat = analyst.get("by_category") or {}
    for cat, ar_label in _CATEGORY_AR.items():
        doc.add_heading(ar_label, level=3)
        items = by_cat.get(cat) or []
        if not items:
            doc.add_paragraph("دليل غير كافٍ لهذا التقاطع في هذا التشغيل — "
                              "فجوة معلنة")
            continue
        for f in items:
            doc.add_paragraph(str(f.get("value")), style="List Bullet")
            doc.add_paragraph(f"[{f.get('source')} — {_evidence_badge(f.get('confidence'))}] "
                              f"{f.get('note') or ''}", style="Intense Quote")

    # سدّ خلل (الطبقة ٨): كان هذا الشرط متداخلاً داخل حلقة التقاطعات
    # أعلاه فيتكرّر عنوان "ملاحظات مراجعة لم تُحلّ" وقائمتها مرة لكل تقاطع
    # له أدلة — خارج الحلقة الآن فيظهر مرة واحدة فقط. النص مُعرَّب أصلاً
    # (clean_unresolved في _deep_research_view، الطبقة ٢) — لا حاجة لمُطهِّر
    # إضافي هنا، القيمة نظيفة عند وصولها.
    if dr["report"].get("unresolved_notes"):
        doc.add_heading("ملاحظات مراجعة لم تُحلّ", level=3)
        for n in dr["report"]["unresolved_notes"]:
            doc.add_paragraph(str(n), style="List Bullet")

    if dr.get("next_step"):
        doc.add_paragraph(dr["next_step"], style="Intense Quote")

    if dr.get("limits"):
        doc.add_heading("حدود قسم البحث العميق", level=2)
        for x in dr["limits"][:12]:
            doc.add_paragraph(_clean_report_text(x), style="List Bullet")

    _docx_technical_appendix(doc, dr)


def _docx_technical_appendix(doc, dr: dict) -> None:
    """ملحق تقني للمدقّقين — بلاغ حي (P0-B، الموجة ٩): الأرقام الكاملة
    (ثقة/مصدر/تاريخ) نُقلت من متن السرد (شارات مبسّطة فقط هناك) لجدول واحد
    شامل هنا — لا معلومة ضاعت، فقط انتقلت لموضع المدقّق لا القارئ العادي."""
    rows = []
    for key, m in (dr.get("missions") or {}).items():
        findings = m.get("findings") if isinstance(m, dict) else None
        label = (m.get("label") if isinstance(m, dict) else None) or key
        for f in (findings or []):
            rows.append([
                label, _clean_report_text(f.get("value"), max_len=120),
                f.get("source") or "—",
                f.get("retrieved_at") or "—",
                f"{f.get('confidence')} ({_evidence_badge(f.get('confidence'))})"])
    if not rows:
        return
    doc.add_heading("ملحق تقني — كل الاستشهادات بثقتها الرقمية الكاملة",
                    level=2)
    doc.add_paragraph("للمدقّقين فقط — القيمة الرقمية الكاملة لكل بند مذكور "
                      "أعلاه بشارته المبسّطة.", style="Intense Quote")
    _add_table(doc, ["البعثة", "الادّعاء", "المصدر", "تاريخ الجلب", "الثقة"],
              rows[:80])


def _render_research_docx(doc, view: dict) -> None:
    """تقرير /research الكامل — بلاغ حي (الموجة ٨): التقرير السردي (كاتب
    التقرير) هو متن التقرير من الصفحة الأولى، لا ملحقاً بعد هيكل كلاسيكي
    غير مُغذّى. الأقسام الأربعة عشر الكلاسيكية (render_docx العادي) مبنية
    لتحليل /analyze متعدد الأسواق (`top_m` من `markets[0]`) — /research
    يحلّل سوقاً واحداً بعمق عبر البعثات الاثنتي عشر فتبقى `markets=[]`
    بنيوياً دوماً هنا، فبناء تلك الأقسام كان يُنتج هيكلاً فارغاً ("التغطية
    0.0%"، "0 أسواق"، "تعذّر إصدار توصية") يسبق المحتوى الحقيقي ويحمل حكماً
    غير مُغذّى (محرك موزون بلا مدخلات) يناقض حكم التوليف الفعلي — حكم واحد
    لا حكمان، ومتن واحد لا متنان (b). لذا: تُحذَف كلياً هنا، لا تُبنى فارغة.
    """
    dr = view.get("deep_research") or {}
    h = view.get("header") or {}
    market = dr.get("market") or {}
    verdict = dr.get("verdict") or {}
    ai = verdict.get("ai") or {}
    # vtxt يبقى الرمز الخام (GO/WATCH/...) لتصنيف اللون (_verdict_tone) —
    # لا يُطبَع حرفياً على وجه العميل أبداً؛ كل موضع عرض يمرّ عبر
    # _VERDICT_LABELS_AR[_verdict_tone(vtxt)] العربي الكامل (بلاغ تدقيق:
    # كانت الشارة تُترجَم بينما سطر «الحكم:» أسفل الخلاصة التنفيذية يطبع
    # الرمز الخام مباشرة — نفس التصنيف، مصدر عرض واحد لا اثنان).
    vtxt = ai.get("verdict") or verdict.get("verdict") or ""
    verdict_label = _VERDICT_LABELS_AR[_verdict_tone(vtxt)]

    # ٠) الغلاف وبطاقة التعريف — هوية سِلك (الموجة ١١، §11.1)
    branding = _load_branding()
    _add_page_header_footer(doc, f"سِلك — تقرير بحث عميق: {view.get('product')}")
    _add_cover_wordmark(doc, branding)
    doc.add_heading(f"سِلك — تقرير بحث عميق: {view.get('product')}", 0)
    doc.add_paragraph("أُعد بواسطة منصة سِلك لذكاء الأسواق", style="Intense Quote")
    if view.get("test_run"):
        doc.add_paragraph("⚠ TEST RUN — تشغيل برهاني ببدائل موسومة، "
                          "ليس تقريراً إنتاجياً")
    _stamp_degraded_banner(doc, view)
    _add_verdict_badge(doc, vtxt)
    _add_table(doc, ["البند", "القيمة"], [
        ["المنتج", h.get("product")],
        ["رمز HS", h.get("hs_code")],
        ["المنشأ", "المملكة العربية السعودية"],
        ["السوق المستهدف", h.get("target_market")
         or market.get("name_ar") or market.get("name_en")],
        ["تاريخ الإعداد", h.get("date")]])

    # جدول محتويات مطابق لبنية البحث العميق الفعلية — لا الأقسام الكلاسيكية
    # التي لا تُبنى هنا أصلاً (لا جدول محتويات يَعِد بأقسام غائبة).
    doc.add_heading("المحتويات", level=1)
    for i, ttl in enumerate((
            "الخلاصة التنفيذية", "ملخّص مصادر البحث",
            "التقرير الكامل (كاتب التقرير، مراجَع)",
            "ملحق — الأدلة الرقمية الداعمة للتقاطعات الخمسة",
            "حدود هذا التقرير"), 1):
        doc.add_paragraph(f"{i}. {ttl}")

    # ١) الخلاصة التنفيذية — من حكم التوليف حصراً (المصدر الوحيد للحكم في
    # هذا التقرير) — لا محرك §8 الموزون غير المُغذّى، ولا نص JSON خام.
    doc.add_heading("١. الخلاصة التنفيذية", level=1)
    doc.add_paragraph(f"الحكم: {verdict_label}")
    reasoning = ai.get("reasoning") or verdict.get("note") or ""
    if reasoning:
        doc.add_paragraph(_clean_report_text(reasoning, max_len=600))
    missions = dr.get("missions") or {}
    n_ok = sum(1 for m in missions.values()
              if not (m.get("failed") if isinstance(m, dict) else
                      getattr(m, "failed", False)))
    doc.add_paragraph(f"مبني على {n_ok}/{len(missions)} بعثة بحث نجحت في "
                      "جمع نتائج مبنية على استشهاد، إضافة إلى المحلل "
                      "الشامل وكاتب التقرير (راجع «حدود هذا التقرير» "
                      "أدناه لكل فجوة معلنة).")

    _docx_deep_research(doc, view)


# ══════════════════════════════════════════════════════════════════════════
# تقرير العميل (Word) — القالب الثاني (فصل الجمهور)
# ══════════════════════════════════════════════════════════════════════════
# البصيرة الجوهرية (بلاغ المالك): التصدير الحالي (_render_research_docx) يعرض
# تِلِمِتري النظام لقارئ نهائي — خطأ جمهور لا خطأ كود. اللوحة (web/index.html)
# تبقى جمهور المشغّل (بعثات، حالات، اقتصاد بيانات). هذا القالب هو جمهور
# العميل: مفردات تجارية بحتة، بلا أي مصطلح تشغيلي. حارس نصّي يرفض التصدير
# إن تسرّب أيّ مصطلح ممنوع (نفس نمط _assert_production_clean).
#
# لا مسار عرض جديد: هذا مُشتقّ آخر فوق build_view (كـrender_docx/render_brief/
# render_markdown) — يستهلك view["deep_research"] نفسه، لا يحسب رقماً جديداً.

# المصطلحات الممنوعة في تصدير العميل — الطبقة ١: قائمة المالك الصريحة
# (mission/status/successful/run/call/declared gap/tool names). الطبقة ٢:
# لغة الخوارزمية (score/confidence/verdict-token/الدرجة) — ممنوعة أيضاً في
# متن العميل (متطلَّب المرحلة ١: لا لغة نظام تصنيف، الأحكام الرقمية للملحق).
_CLIENT_TOOL_NAMES = (
    "comtrade_imports", "comtrade_competitors", "worldbank_indicator",
    "wits_tariff", "trends_interest", "faostat_supply", "web_search",
    "gdelt_news", "openalex_search", "channels_importers", "lookup_reference",
    "eurostat_eu_signals")

# أنماط الرفض — كلٌّ يُطابَق ضد نص التصدير المُجمَّع كاملاً (فقرات + خلايا
# جداول). عربية تشغيلية + أسماء أدوات snake_case + كلمات إنجليزية تشغيلية
# ككلمات كاملة (لا تظهر في نثر عربي إلا تسرّباً). أسماء المصادر البشرية
# (UN Comtrade/World Bank/Eurostat...) مسموحة — استشهاد مشروع لا أداة داخلية.
_CLIENT_FORBIDDEN_PATTERNS = [
    # بلاغ حي إنتاجي (تمور/هولندا، 501 التصدير): "بعثتي"/"بعثتا"/"بعثتها"
    # (المثنى والصيغ ذات ضمير متصل تُبدِّل تاء التأنيث المربوطة ة إلى ت
    # المفتوحة نحوياً) تُفلِت تماماً من هذا الحارس — الصيغة القديمة
    # `بعث(?:ة|ات)` تطابق حرفياً فقط الحالتين المفردة والجمع. الفرع "ت"
    # الجديد يطابق أيّ كلمة تبدأ بـ"بعثت" (مثنى/ضمير) دون تعداد كل صيغة.
    ("mission", re.compile(r"بعث(?:ة|ت|ات)|\bmissions?\b", re.I)),
    ("status", re.compile(r"\bstatus\b", re.I)),
    ("successful", re.compile(r"ناجحة|نجحت|\bsuccessful\b", re.I)),
    ("run", re.compile(r"تشغيلة|\brun\b", re.I)),
    ("call", re.compile(r"نداء(?:ات)?\s+أدوات?|استدعاء\s+أداة|\bcall\b", re.I)),
    # "الفجوات المعلنة" (بأداة التعريف على الكلمتين) لم تكن تطابق الصيغة غير
    # المعرَّفة "فجوات معلنة" — أداة التعريف الاختيارية تسدّ هذه الفجوة.
    ("declared_gap", re.compile(
        r"(?:ال)?فجوة\s+(?:ال)?معلنة|(?:ال)?فجوات\s+(?:ال)?معلنة")),
    ("tool_name", re.compile(
        r"\b(?:" + "|".join(_CLIENT_TOOL_NAMES) + r")\b")),
    ("agent_role", re.compile(
        r"المحلل الشامل|كاتب التقرير|بوابة الجودة|LLMMissionAgent|LLMAgent")),
    ("citation_plumbing", re.compile(r"مبنيّ?ة?\s+على استشهاد|بلا استشهاد|"
                                     r"\bdatapoint\b|\bdp\d+\b", re.I)),
    # الطبقة ٢ — لغة الخوارزمية في المتن (الأحكام الرقمية تعيش في الملحق فقط).
    ("algorithm_language", re.compile(
        r"\bverdict\b|\bconfidence\b|\bscore\b|الدرجة الرقمية|درجة الثقة|"
        r"النتيجة الرقمية", re.I)),
]

# استبدالات التطهير — تُطبَّق على كل كتلة نص من سرد الكاتب قبل عرضها، فتحوّل
# أيّ مصطلح تشغيلي تسرّب من الكاتب إلى مفردة تجارية. الحارس النهائي يلتقط ما
# فات. الترتيب مهم (الأطول أولاً).
_CLIENT_SANITIZE = [
    # تمرير النثر (R1): مصطلحات مترجَمة حرفياً عن الإنجليزية التقنية → لغة
    # الأعمال الخليجية. المصدر مُصلَح في الكاتب/البعثة، وهذه شبكة أمان تلتقط
    # أيّ مخرَج حيّ (أو تشغيلة مخزَّنة قديمة) لا يزال يحمل الصياغة الحرفية.
    (re.compile(r"سعر جملة مرجعي"), "متوسط سعر الاستيراد الرسمي"),
    (re.compile(r"كومتريد"), "UN Comtrade"),        # لا تعريب لاسم مصدر
    (re.compile(r"تكلفة\s+هبوط"), "التكلفة الواصلة"),  # landed cost
    (re.compile(r"\|\s*الدليل\s*\|"), "| مستوى التوثيق |"),  # خلية عمود الجدول
    (re.compile(r"مطبَّع(?:ةً|ة|اً|ًا)?\s+لكل\s+(?:كيلوغرام|كجم|كيلو|وحدة)"),
     "محسوبةً بسعر الكيلوغرام الواحد للمقارنة العادلة"),
    (re.compile(r"\b(?:" + "|".join(_CLIENT_TOOL_NAMES) + r")\b"),
     "السجلّات الرسمية"),
    (re.compile(r"من\s+السجلّات الرسمية"), "من السجلّات الرسمية"),
    (re.compile(r"LLMMissionAgent|LLMAgent"), "مسار البحث"),
    # صيغ المثنى/الضمير المتصل لـ"بعثة" (ة→ت نحوياً) — يجب أن تُحوَّل قبل
    # الصيغتين المفردة/الجمع أدناه وإلا يلتقطها فرع الحارس "ت" الجديد فيُسقِط
    # التصدير بدل تحويله لمفردة تجارية آمنة.
    (re.compile(r"بعثت\w*"), "مسار بحث"),
    (re.compile(r"بعثات"), "مسارات البحث"),
    (re.compile(r"بعثة"), "مسار بحث"),
    (re.compile(r"نجحت في جمع"), "أنتجت"),
    (re.compile(r"ناجحة"), "مكتملة"),
    (re.compile(r"نجحت"), "اكتملت"),
    (re.compile(r"فشلت"), "لم تكتمل"),
    # أداة التعريف الاختيارية (نفس تمديد الحارس أعلاه) قبل الصيغتين الأصليتين.
    (re.compile(r"(?:ال)?فجوات\s+(?:ال)?معلنة"), "بنود تحتاج تحققاً"),
    (re.compile(r"(?:ال)?فجوة\s+(?:ال)?معلنة"), "بند يحتاج تحققاً"),
    (re.compile(r"تشغيلة"), "دورة تحليل"),
    (re.compile(r"مبنيّة على استشهاد|مبني على استشهاد"), "موثّقة بمصادرها"),
    (re.compile(r"المحلل الشامل"), "فريق التحليل"),
    (re.compile(r"كاتب التقرير"), "فريق الإعداد"),
    # بلاغ حي إنتاجي (تدقيق تمور/هولندا، 501 تصدير العميل): سرد الكاتب يمرّ
    # عبر `_strip_internal_plumbing` (silk_render) الذي يعرّب حقول الحكم
    # الإنجليزية (confidence→«درجة الثقة»، verdict→«الحكم»، score→«الدرجة»)،
    # فتصل الصيغة العربية «درجة الثقة»/«الدرجة الرقمية» متن العميل وتُسقِطه
    # حارسُ لغة الخوارزمية (_client_assert_clean) بـ501. تُحوَّل هنا لمفردة
    # توثيق تجارية — الأحكام الرقمية تبقى للملحق/التصدير التشغيلي فقط.
    (re.compile(r"الدرجة الرقمية|النتيجة الرقمية"), "التقييم"),
    (re.compile(r"درجة الثقة"), "مستوى التوثيق"),
    (re.compile(r"\bconfidence\b", re.I), "مستوى التوثيق"),
    (re.compile(r"\bverdict\b", re.I), "التوصية"),
    (re.compile(r"\bscore\b", re.I), "التقييم"),
]


def _client_sanitize(text: object) -> str:
    """طهّر كتلة نص من سرد الكاتب لجمهور العميل — يحوّل المصطلحات التشغيلية
    المتسرّبة لمفردات تجارية. الحارس النهائي (_client_assert_clean) يرفض أي
    بقايا. لا يمسّ الأرقام ولا المصادر البشرية."""
    s = str(text or "")
    for pat, repl in _CLIENT_SANITIZE:
        s = pat.sub(repl, s)
    return re.sub(r"[ \t]{2,}", " ", s).strip()


def _client_forbidden_hits(blob: str) -> list[str]:
    """أرجع كل مصطلح ممنوع ظهر في نص التصدير — للاختبار وللحارس."""
    hits = []
    for label, pat in _CLIENT_FORBIDDEN_PATTERNS:
        m = pat.search(blob or "")
        if m:
            hits.append(f"{label}: «{m.group(0)}»")
    return hits


def _client_assert_clean(doc) -> None:
    """حارس تصدير العميل — يرفض المستند إن تسرّب أيّ مصطلح تشغيلي/خوارزمي
    (نفس نمط _assert_production_clean: رفض بصوت عالٍ لا تسليم مسموم). يمسح
    كل الفقرات وخلايا الجداول المُجمَّعة."""
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                parts.append(cell.text)
    blob = "\n".join(parts)
    hits = _client_forbidden_hits(blob)
    if hits:
        raise RuntimeError(
            "تصدير العميل يحوي مصطلحات ممنوعة (تسريب تِلِمِتري لجمهور "
            "العميل) — رُفض التوليد: " + "؛ ".join(hits[:8]))


# خريطة أقسام الكاتب (البنية الدولية بأحد عشر قسماً) → أقسام تقرير العميل
# السبعة. أقسام "منهجية البحث ونطاقه" و"الملاحق" تُسقَط (تُستبدَل بفقرة
# منهجية مضبوطة وملحق أدلة). الترتيب النهائي للعميل يُبنى صراحة في المُصيّر.
_CLIENT_SECTION_MAP = {
    "الخلاصة التنفيذية": "القرار وأساسه",
    "التوصيات الاستراتيجية": "القرار وأساسه",
    "نظرة عامة على السوق وحجمه": "السوق بالأرقام",
    "ديناميكيات السوق": "السوق بالأرقام",
    "تحليل المستهلك والطلب": "السوق بالأرقام",
    "المشهد التنافسي": "المنافسة والتسعير والهامش",
    "التنظيم والوصول للسوق": "مسار الدخول والمتطلبات",
    "اللوجستيات وسلسلة الإمداد": "مسار الدخول والمتطلبات",
    "تقييم المخاطر": "المخاطر",
}
# ترتيب أقسام العميل النهائي (بلاغ المالك، البنية المطلوبة).
_CLIENT_SECTION_ORDER = (
    "القرار وأساسه", "السوق بالأرقام", "المنافسة والتسعير والهامش",
    "مسار الدخول والمتطلبات", "المخاطر")

_WRITER_HEADING_RE = re.compile(r"^##\s+\d+\.\s*(.+?)\s*$")
_ROADMAP_SUBHEAD_RE = re.compile(r"^###\s+خارطة طريق الدخول")


def _split_at_roadmap(body: list[str]) -> "tuple[list[str], list[str]]":
    """قسّم متن التوصيات عند العنوان الفرعي "### خارطة طريق الدخول" — الجزء
    قبله (تعليل الحكم) والجزء منه فصاعداً (الخارطة). نقطة قسم حتمية (عنوان
    فرعي ثابت يفرضه كاتب التقرير) لا تحليل نصّي هشّ."""
    for idx, line in enumerate(body):
        if _ROADMAP_SUBHEAD_RE.match(line.strip()):
            return body[:idx], body[idx:]
    return body, []


def _parse_writer_sections(report_text: str) -> "list[tuple[str, list[str]]]":
    """قسّم سرد الكاتب إلى (عنوان القسم، أسطر متنه) — يعيد استعمال بنية
    '## N. العنوان' نفسها التي يفرضها كاتب التقرير (silk_ai_judge._REPORT_
    SECTIONS). العناوين الفرعية '### ' والجداول تبقى ضمن متن قسمها."""
    sections: list[tuple[str, list[str]]] = []
    cur_title, cur_body = None, []
    for line in str(report_text or "").splitlines():
        m = _WRITER_HEADING_RE.match(line.strip())
        if m:
            if cur_title is not None:
                sections.append((cur_title, cur_body))
            cur_title, cur_body = m.group(1).strip(), []
        elif cur_title is not None:
            cur_body.append(line)
    if cur_title is not None:
        sections.append((cur_title, cur_body))
    return sections


def _client_render_body_block(doc, lines: list[str]) -> None:
    """اعرض أسطر متن قسم (فقرات + جداول Markdown + سطر الخلاصة الغامق) بعد
    التطهير — نفس ميكانيكا _docx_deep_research لكن عبر _client_sanitize،
    ويُسقِط أيّ جدول بقي فيه مصطلح ممنوع بعد التطهير (جداول الدرجات الرقمية
    verdict/confidence — لغة خوارزمية لا تُعرَض للعميل)."""
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i].strip()
        if not raw:
            i += 1
            continue
        if raw.startswith("### "):
            doc.add_heading(_client_sanitize(raw[4:]), level=3)
            i += 1
            continue
        if raw.startswith("## "):  # عنوان قسم فرعي غير متوقّع — كفقرة مطهَّرة
            doc.add_paragraph(_client_sanitize(raw[3:]))
            i += 1
            continue
        if _is_markdown_table_row(raw):
            block = []
            while i < n and _is_markdown_table_row(lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            joined = _client_sanitize("\n".join(block))
            if _client_forbidden_hits(joined):
                continue  # جدول درجات/تِلِمِتري — يُسقَط من متن العميل
            _render_markdown_table(doc, joined.splitlines())
            continue
        stripped = _strip_inline_markdown(_client_sanitize(raw))
        if stripped.startswith("ماذا يعني هذا لقرارك:"):
            p = doc.add_paragraph()
            p.add_run(stripped).bold = True
        else:
            doc.add_paragraph(stripped)
        i += 1


def _client_methodology_paragraph(dr: dict) -> str:
    """فقرة المنهجية المضبوطة (٣ أسطر) — تحلّ محل جدول البعثات التشغيلي في
    تصدير العميل (بلاغ المالك، النقطة ٤): عدد مسارات البحث، المصادر، تاريخ
    الجلب — بمفردات تجارية بحتة، من حقول محسوبة فعلاً لا اختلاق."""
    missions = dr.get("missions") or {}
    n_tracks = len(missions)
    n_producing = sum(
        1 for m in missions.values()
        if not (m.get("failed") if isinstance(m, dict) else False))
    # المصادر البشرية الفريدة الظاهرة فعلاً في النتائج (لا أسماء أدوات).
    sources = set()
    for m in missions.values():
        for f in (m.get("findings") or []) if isinstance(m, dict) else []:
            src = str(f.get("source") or "").strip()
            if src and not _client_forbidden_hits(src):
                # اسم مصدر بشري فقط (قبل أيّ شرطة توضيحية).
                sources.add(re.split(r"\s+[—\-(]", src)[0].strip())
    src_list = "، ".join(sorted(s for s in sources if s)[:6]) or "مصادر رسمية عامة"
    dates = sorted({str(f.get("retrieved_at"))
                    for m in missions.values()
                    if isinstance(m, dict)
                    for f in (m.get("findings") or [])
                    if f.get("retrieved_at")})
    date_txt = (f"أحدث تاريخ جمع بيانات: {dates[-1]}" if dates
                else "تواريخ الجمع مسجّلة في سجل الأدلة أدناه")
    return (
        f"اعتمد هذا التقرير على {n_tracks} مسار بحث مستقل، أنتج منها "
        f"{n_producing} نتائج موثّقة بمصادرها، مع تحليل تقاطعي ومراجعة "
        f"للاتساق. المصادر الأساسية: {src_list}. {date_txt}. تفاصيل كل "
        "رقم بمصدره وتاريخه في «سجل الأدلة للمدققين» ختام التقرير.")


# صياغة تجارية لكل فجوة في قسم "ما لم يكتمل للقرار" (بلاغ المالك، النقطة ٣):
# لا عناوين فارغة متتالية، بل جملة تجارية موحّدة القالب لكل تقاطع بلا أدلة.
_CLIENT_GAP_TEMPLATE = ("لم نتمكّن من توثيق {what} من مصدر موثّق ضمن هذا "
                        "التقرير — إغلاق هذه الفجوة يتطلّب {how}.")
_CLIENT_GAP_WHAT = {
    "demand": ("الحجم الدقيق للطلب الفعلي القابل للتوجيه",
               "بحثاً ميدانياً أوّلياً (مقابلات موزّعين أو استبيان طلب)"),
    "entry_cost": ("تكلفة الدخول الكاملة بما فيها الشحن الفعلي",
                   "عرض أسعار شحن ملزماً من وكيل لوجستي"),
    "price_competitiveness": ("موقعك السعري الدقيق مقابل المنافسين",
                              "بطاقة منتجك (تكلفتك للكيلوغرام) وخدمة رصد "
                              "أسعار مدفوعة"),
    "entry_door": ("قائمة موزّعين/مستوردين مؤكَّدين بالاسم",
                   "خدمة تحقّق جهات اتصال مدفوعة (قواعد بيانات تجارية)"),
    "swot": ("الموقف التنافسي المؤكَّد من منظور مصدّر سعودي",
             "دمج نتائج التحقّق الميداني أعلاه في تقييم موحّد"),
}


def _client_confidence_section(doc, dr: dict) -> None:
    """مؤشّر ثقة الدراسة (S3) — عدّ شارات الأدلة (✓ موثّق/◐ ثانوي/○ غير متحقق)
    عبر بعثات الدراسة وتقاطعات المحلل، فيرى العميل شفافياً كم من الدراسة
    مرصود بمصدر رسمي مقابل مُقدَّر أو فجوة. تجميع بحت من درجات ثقة قائمة —
    لا رقم جديد ولا حكم، ويمرّ بحارس المصطلحات كأيّ قسم عميل."""
    from silk_narrative import evidence_badge
    counts = {"verified": 0, "secondary": 0, "unverified": 0}

    def _tally(conf) -> None:
        badge = evidence_badge(conf)
        if badge.startswith("✓"):
            counts["verified"] += 1
        elif badge.startswith("◐"):
            counts["secondary"] += 1
        else:
            counts["unverified"] += 1

    for m in (dr.get("missions") or {}).values():
        if not isinstance(m, dict) or m.get("failed"):
            continue
        for f in (m.get("findings") or []):
            if _dp_conf(f) is not None:
                _tally(_dp_conf(f))
    for dps in ((dr.get("analyst") or {}).get("by_category") or {}).values():
        for f in (dps or []):
            if _dp_conf(f) is not None:
                _tally(_dp_conf(f))

    total = sum(counts.values())
    if not total:
        return   # لا مؤشرات معدودة — لا قسم فارغ
    verified_pct = round(100 * counts["verified"] / total)
    doc.add_heading("مؤشّر ثقة الدراسة", level=1)
    doc.add_paragraph(
        f"من إجمالي {total} مؤشراً مرصوداً في هذه الدراسة، "
        f"{counts['verified']} موثّق بمصدر رسمي (نحو {verified_pct}%)، "
        f"{counts['secondary']} من مصدر ثانوي، و{counts['unverified']} غير "
        "متحقق. كلّ رقم في التقرير يحمل شارة توثيقه ومصدره في سجل الأدلة، "
        "فالقرار يُتَّخذ بمعرفة درجة اليقين خلف كل رقم لا على ثقة عمياء.")
    _add_table(doc, ["درجة التوثيق", "عدد المؤشرات"], [
        ["✓ موثّق (مصدر رسمي)", str(counts["verified"])],
        ["◐ ثانوي (مصدر واحد غير رسمي)", str(counts["secondary"])],
        ["○ غير متحقق", str(counts["unverified"])]])


def _client_gaps_section(doc, dr: dict) -> None:
    """قسم "ما لم يكتمل للقرار والخطوة التالية" — يحوّل كل تقاطع بلا أدلة
    كافية لصياغة تجارية موحّدة (بلاغ المالك النقطة ٣)، ثم الخطوة التالية.
    لا عناوين فارغة متتالية: إن اكتمل كل شيء، سطر إيجابي واحد."""
    doc.add_heading("ما لم يكتمل للقرار، والخطوة التالية", level=1)
    analyst = dr.get("analyst") or {}
    missing = analyst.get("missing_categories") or []
    by_cat = analyst.get("by_category") or {}

    gap_lines: list[str] = []
    for cat in missing:
        what, how = _CLIENT_GAP_WHAT.get(
            cat, ("بند تحليلي إضافي", "بحثاً تكميلياً موجّهاً"))
        gap_lines.append(_CLIENT_GAP_TEMPLATE.format(what=what, how=how))
    # بلاغ مراجعة المالك (منطق قسم الفجوات): بند حاسم للقرار موسوم ○ غير
    # متحقق (قناة الدخول الأولى) يجب أن يظهر هنا حتى لو اكتملت التقاطعات —
    # لا يُقال «لا فجوة جوهرية» بينما الموزّع الأول غير مؤكَّد. باب الدخول
    # المرصود بثقة دون عتبة «الثانوي» (0.5) = مرشّح غير محقَّق، لا حقيقة.
    if "entry_door" not in missing:
        from silk_narrative import EVIDENCE_SECONDARY_MIN
        unverified_doors = [
            f for f in (by_cat.get("entry_door") or [])
            if _dp_conf(f) is not None and _dp_conf(f) < EVIDENCE_SECONDARY_MIN]
        if unverified_doors:
            names = "، ".join(
                _client_sanitize(_clean_report_text(f.get("value"), 80))
                for f in unverified_doors[:2])
            gap_lines.append(
                f"لم نتمكّن من تأكيد قناة الدخول الأولى ({names}) من مصدر "
                "موثّق — إغلاق هذه الفجوة يتطلّب خدمة تحقّق جهات اتصال مدفوعة "
                "(قواعد بيانات تجارية) قبل الالتزام بالموزّع.")

    if gap_lines:
        doc.add_paragraph(
            "النقاط التالية لم تكتمل توثيقاً ضمن هذا التقرير؛ هي ما يفصل "
            "التوصية الحالية عن قرار نهائي كامل، وكلٌّ منها قابل للإغلاق "
            "بخطوة محدّدة:")
        for line in gap_lines:
            doc.add_paragraph(line, style="List Bullet")
    else:
        doc.add_paragraph(
            "اكتملت التقاطعات التحليلية الأساسية بأدلة موثّقة بمصادرها، ولا "
            "بند حاسم للقرار موسوم بأنه غير محقَّق؛ لا فجوة جوهرية تمنع "
            "اتخاذ القرار ضمن نطاق هذا التقرير.")
    nxt = dr.get("next_step")
    if nxt:
        doc.add_heading("الخطوة التالية المقترحة", level=2)
        doc.add_paragraph(_client_sanitize(nxt))


_CAT_TAG_RE = re.compile(
    r"^\[(?:demand|price_competitiveness|entry_cost|entry_door|swot|[a-z_]+)\]\s*")


def _dp_conf(f: object) -> "float | None":
    """درجة الثقة لبند أدلة (dict أو DataPoint) — None إن تعذّر."""
    if isinstance(f, dict):
        c = f.get("confidence")
    else:
        c = getattr(f, "confidence", None)
    try:
        return float(c)
    except (TypeError, ValueError):
        return None


def _readable_number(v: object) -> str:
    """رقم بصيغة عربية مقروءة — 38000000.0 → «38 مليون» (بلاغ مراجعة المالك:
    عشريات خام في سجل الأدلة). الوحدة (دولار/نسمة/…) تأتي من الملاحظة لا
    تُختلَق هنا."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    a = abs(n)
    if a >= 1e9:
        return f"{n / 1e9:.1f} مليار".replace(".0 ", " ")
    if a >= 1e6:
        return f"{n / 1e6:.1f} مليون".replace(".0 ", " ")
    if a >= 1e3:
        return f"{n:,.0f}"
    return f"{n:g}"


def _client_readable_fact(value: object, note: object) -> "str | None":
    """حوّل قيمة أدلة إلى حقيقة مقروءة لعمود «الحقيقة» — بلاغ مراجعة المالك
    (النقطة ٤): (أ) البنود التي لا تُعرَض مباشرة (قيمة dict غير معروفة/رد
    خام) تُسقَط (None) بدل سطر «بند تقني غير قابل للعرض» عديم المعنى؛ (ب)
    العشريات الخام تُنسَّق مقروءةً مع سياق ملاحظتها. لا اختلاق وحدة."""
    clean_note = _client_sanitize(_CAT_TAG_RE.sub("", str(note or "")).strip())
    if isinstance(value, dict):
        if value.get("partner") is not None and value.get("share") is not None:
            return f"{value['partner']}: حصة {value['share']}%"
        if value.get("hhi") is not None:
            return f"مؤشر تركّز المورّدين HHI={value['hhi']}"
        return None  # بنية غير معروفة — لا سطر عديم المعنى
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        num = _readable_number(value)
        return f"{num} — {clean_note}" if clean_note else num
    txt = _client_sanitize(_clean_report_text(value, max_len=140))
    if not txt or txt.startswith("بند تقني غير قابل للعرض"):
        return None  # بند لا يُعرَض — يُسقَط بدل ضجيج للمدقّق
    return txt


def _client_evidence_appendix(doc, dr: dict) -> None:
    """سجل الأدلة للمدققين (بلاغ المالك النقطة ٤) — جدول الأدلة الكامل ينتقل
    لملحق ختامي بهذا العنوان، بمفردات محايدة (المصدر البشري، لا اسم الأداة).
    يبدأ بفقرة المنهجية المضبوطة (٣ أسطر). البنود عديمة المعنى تُسقَط،
    والعشريات الخام تُنسَّق مقروءةً."""
    doc.add_heading("المنهجية وسجل الأدلة للمدققين", level=1)
    doc.add_paragraph(_client_methodology_paragraph(dr))
    doc.add_heading("سجل الأدلة للمدققين", level=2)
    rows = []
    for m in (dr.get("missions") or {}).values():
        if not isinstance(m, dict):
            continue
        for f in (m.get("findings") or []):
            fact = _client_readable_fact(f.get("value"), f.get("note"))
            if fact is None:  # بند عديم المعنى/غير قابل للعرض — يُسقَط
                continue
            src = str(f.get("source") or "—")
            if _client_forbidden_hits(src):  # لا اسم أداة في عمود المصدر
                src = "سجلّات رسمية"
            rows.append([fact, src, f.get("retrieved_at") or "—",
                        _evidence_badge(f.get("confidence"))])
    if not rows:
        doc.add_paragraph("لا بنود أدلة مفصّلة في هذا التقرير.")
        return
    doc.add_paragraph(
        "كل بند أدناه هو حقيقة موثّقة بمصدرها وتاريخها، أساس السرد أعلاه — "
        "للتحقّق المباشر. رمز الأدلة: ✓ موثّق مباشرةً · ◐ تقديري مسنَد · "
        "○ يحتاج تحققاً.", style="Intense Quote")
    _add_table(doc, ["الحقيقة", "المصدر", "تاريخ الجمع", "قوة الدليل"],
               rows[:80])


def render_client_docx(view: dict, path: str) -> str:
    """تقرير العميل (Word) — القالب الثاني، جمهور العميل (بلاغ المالك: فصل
    الجمهور). يستهلك view["deep_research"] نفسه (لا مسار عرض جديد) وينتج
    بنية العميل السبع: القرار وأساسه → السوق بالأرقام → المنافسة والتسعير →
    مسار الدخول والمتطلبات → المخاطر → ما لم يكتمل للقرار → المنهجية وسجل
    الأدلة. حارس نصّي يرفض التصدير إن تسرّب أيّ مصطلح تشغيلي/خوارزمي.

    نتيجة /analyze الكلاسيكية (بلا deep_research) ليست ضمن نطاق هذا القالب
    — تُوجَّه لـrender_docx العادي من المستدعي. يعيد المسار عند النجاح.
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(_DOCX_HINT) from exc

    _assert_production_clean(view)
    dr = view.get("deep_research") or {}
    if not dr:
        raise RuntimeError("render_client_docx يتطلّب نتيجة بحث عميق "
                           "(view['deep_research']) — استخدم render_docx "
                           "لتقارير /analyze الكلاسيكية")

    doc = Document()
    h = view.get("header") or {}
    market = dr.get("market") or {}
    verdict = dr.get("verdict") or {}
    ai = verdict.get("ai") or {}
    vtxt = ai.get("verdict") or verdict.get("verdict") or ""
    branding = _load_branding()

    # ٠) الغلاف — هوية سِلك، بلا أيّ تِلِمِتري
    _add_page_header_footer(doc, f"سِلك — دراسة سوق تصديرية: {view.get('product')}")
    _add_cover_wordmark(doc, branding)
    doc.add_heading(f"دراسة سوق تصديرية: {view.get('product')}", 0)
    doc.add_paragraph("أُعدّت بواسطة منصة سِلك لذكاء الأسواق",
                      style="Intense Quote")
    if view.get("test_run"):
        doc.add_paragraph("⚠ نموذج توضيحي ببيانات موسومة — ليس تقريراً "
                          "إنتاجياً")
    _stamp_degraded_banner(doc, view)
    _add_verdict_badge(doc, vtxt)
    _add_table(doc, ["البند", "القيمة"], [
        ["المنتج", h.get("product") or view.get("product")],
        ["رمز HS", h.get("hs_code") or view.get("hs_code")],
        ["بلد المنشأ", "المملكة العربية السعودية"],
        ["السوق المستهدف", h.get("target_market")
         or market.get("name_ar") or market.get("name_en")],
        ["تاريخ الإعداد", h.get("date")]])

    # بنية الأقسام: اجمع أقسام الكاتب المطهَّرة تحت عناوين العميل السبعة.
    sections = _parse_writer_sections((dr.get("report") or {}).get("text") or "")
    buckets: dict[str, list[list[str]]] = {c: [] for c in _CLIENT_SECTION_ORDER}
    for title, body in sections:
        # قسم التوصيات يُقسَم عند "### خارطة طريق الدخول": تعليل الحكم يبقى
        # في "القرار وأساسه"، وخارطة الدخول (الأبواب والخطوات) تنتقل لـ
        # "مسار الدخول والمتطلبات" — مطابقة أدقّ للبنية المطلوبة (بلاغ المالك).
        if title == "التوصيات الاستراتيجية":
            decision_part, roadmap_part = _split_at_roadmap(body)
            buckets["القرار وأساسه"].append(decision_part)
            if roadmap_part:
                buckets["مسار الدخول والمتطلبات"].append(roadmap_part)
            continue
        client_head = _CLIENT_SECTION_MAP.get(title)
        if client_head:
            buckets[client_head].append(body)

    # ١) القرار وأساسه — يبدأ دوماً بالحكم وتعليله (المصدر الوحيد للحكم)،
    # ثم سرد الكاتب (الخلاصة + التوصيات) إن توفّر.
    doc.add_heading("القرار وأساسه", level=1)
    doc.add_paragraph(f"التوصية: {_VERDICT_LABELS_AR[_verdict_tone(vtxt)]}")
    reasoning = ai.get("reasoning") or verdict.get("note") or ""
    if reasoning:
        doc.add_paragraph(_client_sanitize(_clean_report_text(reasoning, 700)))
    # تصدير متدهور بدل فشل صامت (بلاغ المالك، القضية ٣): حين يتعذّر توليد
    # التقرير السردي (report=None بعد فشل نداء الكاتب) نُصدّر مستنداً كاملاً
    # بما هو متاح — الحكم أعلاه + الأدلة المرصودة + الفجوات المعلنة — مع
    # سطر صريح يوضّح أن السرد التفصيلي غاب لأسباب تقنية (لا نكشف تفصيلاً
    # تشغيلياً خاماً للعميل — حارس _client_assert_clean؛ التفصيل الكامل في
    # التصدير التشغيلي ?internal=1 وسبب الفشل المُهيكَل في نتيجة التحليل).
    if not (dr.get("report") or {}).get("text"):
        doc.add_paragraph(
            "تعذّر إنجاز التقرير السردي التفصيلي في هذه المحاولة لأسباب "
            "تقنية مؤقتة؛ القرار أعلاه والأدلة المرصودة في «سجل الأدلة "
            "للمدققين» ختام هذا التقرير قائمة وصحيحة، ويمكن إعادة توليد "
            "النص السردي دون إعادة البحث الكامل.")
    _client_body_or_fallback(doc, buckets["القرار وأساسه"], dr,
                             "القرار وأساسه")

    # ٢-٥) بقية أقسام العميل بالترتيب
    for client_head in _CLIENT_SECTION_ORDER[1:]:
        doc.add_heading(client_head, level=1)
        _client_body_or_fallback(doc, buckets[client_head], dr, client_head)

    # ٦) مؤشّر ثقة الدراسة (S3) — شفافية درجة التوثيق قبل إعلان ما لم يكتمل
    _client_confidence_section(doc, dr)

    # ٧) ما لم يكتمل للقرار والخطوة التالية (صياغة تجارية للفجوات)
    _client_gaps_section(doc, dr)

    # ٧) المنهجية وسجل الأدلة للمدققين (يحلّ محل جدول البعثات)
    _client_evidence_appendix(doc, dr)

    _client_assert_clean(doc)  # الحارس النهائي — رفض إن تسرّب مصطلح ممنوع
    doc.save(path)
    return path


def _client_body_or_fallback(doc, bodies: list[list[str]], dr: dict,
                             client_head: str) -> None:
    """اعرض متون الكاتب لهذا القسم إن توفّرت؛ وإلا صياغة تجارية موجزة من
    التقاطعات المهيكلة (سرد الكاتب غائب = فشل النداء) — بلا تِلِمِتري، بلا
    عنوان فارغ. لا اختلاق: يذكر فقط ما رُصد فعلاً أو يصرّح تجارياً بغيابه."""
    if bodies:
        for body in bodies:
            _client_render_body_block(doc, body)
        return
    # مسار احتياطي: لا سرد كاتب — اعرض من التقاطعات المهيكلة إن وُجدت.
    cat_for_head = {
        "القرار وأساسه": ("swot",),
        "السوق بالأرقام": ("demand",),
        "المنافسة والتسعير والهامش": ("price_competitiveness",),
        "مسار الدخول والمتطلبات": ("entry_cost", "entry_door"),
        "المخاطر": (),
    }.get(client_head, ())
    by_cat = (dr.get("analyst") or {}).get("by_category") or {}
    shown = False
    for cat in cat_for_head:
        for f in (by_cat.get(cat) or []):
            doc.add_paragraph(
                _client_sanitize(_clean_report_text(f.get("value"), 220)),
                style="List Bullet")
            shown = True
    if not shown:
        doc.add_paragraph(
            "التحليل السردي التفصيلي لهذا القسم غير متاح ضمن هذا التقرير؛ "
            "الأدلة المرصودة ذات الصلة مُدرجة في «سجل الأدلة للمدققين» ختام "
            "التقرير.")


def render_docx(view: dict, path: str) -> str:
    """التقرير الكامل Word (§10.3) — من القالب الموحّد حصراً.

    يعيد المسار عند النجاح؛ RuntimeError واضحة بلا python-docx.

    نتيجة `/research` (`view["deep_research"]` موجود) تُبنى عبر مسار مخصّص
    (`_render_research_docx`) لا الأقسام الأربعة عشر الكلاسيكية — راجع
    تعليق التصميم هناك (بلاغ حي، الموجة ٨: كانت تُبنى هيكلاً فارغاً يسبق
    التقرير الحقيقي).
    """
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(_DOCX_HINT) from exc

    _assert_production_clean(view)
    doc = Document()

    if view.get("deep_research"):
        _render_research_docx(doc, view)
        doc.save(path)
        return path

    top_m = (view.get("markets") or [{}])[0]

    # ═══ 0) الغلاف وبطاقة التعريف — cover + report card ═══
    # هوية سِلك (الموجة ١١، §11.1) — رأس/تذييل موحّدان لكل تقارير docx.
    _add_page_header_footer(doc, f"سِلك — تقرير بحث سوق: {view.get('product')}")
    _add_cover_wordmark(doc, _load_branding())
    doc.add_heading(f"سِلك — تقرير بحث سوق: {view.get('product')}", 0)
    if view.get("test_run"):
        doc.add_paragraph("⚠ TEST RUN — تشغيل برهاني ببدائل موسومة، "
                          "ليس تقريراً إنتاجياً")
    _stamp_degraded_banner(doc, view)  # لافتة الغلاف — بلاغ حي
    h = view.get("header") or {}
    _add_table(doc, ["البند", "القيمة"], [
        ["المنتج", h.get("product")],
        ["رمز HS", h.get("hs_code")],
        ["المنشأ", "المملكة العربية السعودية"],
        ["السوق المستهدف", h.get("target_market")],
        ["تاريخ الإعداد", h.get("date")],
        ["سنة البيانات", _data_year_label(view)],
        ["تغطية البيانات", f"{h.get('coverage_pct')}%"]])

    # جدول المحتويات الثابت — الأقسام الأربعة عشر المرقّمة، ثم الأقسام
    # غير المرقّمة بترتيبها الفعلي في المتن (نفس اصطلاح المتن — "حدود هذا
    # التقرير"/"دليل المورّدين والمستوردين"/"الملحق" بلا رقم فيه أيضاً).
    # سدّ تسريب (الطبقة ٩): "حدود هذا التقرير" و"دليل المورّدين والمستوردين"
    # (رُقّي من عنوان فرعي مدفون تحت التوصيات) كانا غائبين عن هذا الجدول.
    doc.add_heading("المحتويات", level=1)
    for i, ttl in enumerate((
            "الخلاصة التنفيذية", "منهجية البحث", "تعريف السوق ونطاقه",
            "نظرة عامة على السوق", "ديناميكيات السوق",
            "حجم السوق والتوقعات", "تحليل التقسيم",
            "تحليل التجارة (استيراد/تصدير)", "الأسواق المرشّحة الأخرى",
            "المشهد التنافسي", "استخبارات العميل والطلب",
            "المشهد التنظيمي والمخاطر", "الاتجاهات والتوقع المستقبلي",
            "التوصيات الاستراتيجية"), 1):
        doc.add_paragraph(f"{i}. {ttl}", style="List Number" if False
                          else None)
    # نص مختلف حرفياً عن العنوان الفعلي عمداً (نفس أسلوب سطر "الملحق" أدناه
    # أصلاً) — لا تطابق نصّي حرفي بين فقرة الفهرس وعنوان القسم قد يُربك أي
    # فحص نصّي لاحق على ترتيب العناوين.
    doc.add_paragraph("حدود التحليل (الفجوات المعلنة)")
    doc.add_paragraph("دليل المورّدين (الاتصال بالموردين والمستوردين)")
    doc.add_paragraph("الملحق (تغطية المصادر وأثرها)")

    # ═══ ١) الخلاصة التنفيذية — ٣ فقرات بشرية (P1) ═══
    doc.add_heading("١. الخلاصة التنفيذية", level=1)
    for para in _narrative_exec_summary(view):
        doc.add_paragraph(para)

    # ═══ ٢) منهجية البحث ═══
    doc.add_heading("٢. منهجية البحث", level=1)
    for line in _methodology_lines(view):
        doc.add_paragraph(line, style="List Bullet")

    # ═══ ٣) تعريف السوق ونطاقه ═══
    doc.add_heading("٣. تعريف السوق ونطاقه", level=1)
    doc.add_paragraph(_market_scope_paragraph(view))

    # سدّ تسريب (الطبقة ٩): قرار الدخول (المحرك الموزون §8) كان مدفوناً
    # في القسم ١٤ الأخير (التوصيات) — القارئ يصل التوصية الفعلية بعد كل
    # التفاصيل. رُفع هنا قرب الخلاصة التنفيذية (نفس ترتيب render_markdown
    # أصلاً، الذي كان صحيحاً بالفعل: "قرار الدخول" يظهر بعد تعريف السوق
    # مباشرة). _docx_entry_strategy تبقى في التوصيات — نموذج دخول تفصيلي
    # لا حكم.
    _docx_entry_decision(doc, top_m)

    # ═══ ٤) نظرة عامة على السوق — إشارات نوعية مرصودة أو غياب هادئ ═══
    doc.add_heading("٤. نظرة عامة على السوق", level=1)
    cc = view.get("consumer_culture") or {}
    overview_ins = (cc.get("insights") or [])[:3]
    if overview_ins:
        for o in overview_ins:
            doc.add_paragraph(str(o.get("point") or ""), style="List Bullet")
            ev = "؛ ".join(map(str, (o.get("evidence") or [])[:2]))
            if ev:
                doc.add_paragraph(f"الدليل: {ev}", style="Intense Quote")
    else:
        doc.add_paragraph("لم تُجمع إشارات نوعية عن حالة الصناعة في هذا "
                          "التشغيل — يتطلب مفتاح بحث الويب.")

    # ═══ ٥) ديناميكيات السوق — وكيل الديناميكيات (P2-8) ═══
    doc.add_heading("٥. ديناميكيات السوق", level=1)
    dyn = view.get("dynamics") or {}
    dyn_v = dyn.get("value") if isinstance(dyn, dict) else None
    if isinstance(dyn_v, dict) and dyn_v.get("classified"):
        _AR_DYN = (("drivers", "الدوافع"), ("restraints", "الكوابح"),
                   ("opportunities", "الفرص"), ("threats", "التحديات"))
        for key, ttl in _AR_DYN:
            items = dyn_v.get(key) or []
            if not items:
                continue
            doc.add_heading(ttl, level=2)
            for it in items[:5]:
                doc.add_paragraph(str(it.get("point")), style="List Bullet")
                ev = "؛ ".join(map(str, (it.get("evidence") or [])[:2]))
                if ev:
                    doc.add_paragraph(f"الدليل: {ev}", style="Intense Quote")
        for key, ttl, label in (("porter", "قوى المنافسة الخمس", "force"),
                                ("pestel", "تحليل PESTEL", "dimension")):
            items = dyn_v.get(key) or []
            if items:
                doc.add_heading(ttl, level=2)
                _add_table(doc, ["البُعد", "الملاحظة", "الدليل"],
                           [[it.get(label), it.get("point"),
                             "؛ ".join(map(str, (it.get("evidence") or [])[:1]))]
                            for it in items[:7]])
        if dyn_v.get("note"):
            doc.add_paragraph(str(dyn_v["note"]), style="Intense Quote")
    elif isinstance(dyn_v, dict) and dyn_v.get("raw_signals"):
        doc.add_paragraph("إشارات ويب خام (لم تُصنَّف بعد — التصنيف في "
                          "الأطر يتطلب مفتاح كلود):")
        for sig in dyn_v["raw_signals"][:6]:
            t = sig.get("title") if isinstance(sig, dict) else sig
            doc.add_paragraph(str(t)[:180], style="List Bullet")
    else:
        doc.add_paragraph(str(dyn.get("note") or
                          "تحليل الدوافع والكوابح والفرص والتحديات يتطلب "
                          "مفتاح بحث الويب — لم يُشغَّل في هذا التحليل."))

    # ═══ ٦) حجم السوق والتوقعات — TAM/SAM/SOM + النمو ═══
    doc.add_heading("٦. حجم السوق والتوقعات", level=1)
    _docx_market_size(doc, top_m)
    tr = top_m.get("trend") or {}
    if tr.get("growth_pct") is not None or tr.get("cagr_pct") is not None:
        from silk_narrative import growth_phrase
        doc.add_paragraph(growth_phrase(tr.get("cagr_pct"),
                                        tr.get("growth_pct"),
                                        years="سنوات الدراسة"))
        doc.add_paragraph(f"المصدر: {tr.get('source') or 'UN Comtrade'}",
                          style="Intense Quote")

    # ═══ ٧) تحليل التقسيم ═══
    doc.add_heading("٧. تحليل التقسيم", level=1)
    _docx_segments(doc, top_m)

    # ═══ ٨) تحليل التجارة — قوّة كومتريد الفريدة ═══
    doc.add_heading("٨. تحليل التجارة (استيراد/تصدير)", level=1)
    from silk_narrative import fmt_money, fmt_pct
    # صفّ بلا مورّد ولا قيمة بند زائف — يُستبعد قبل الحكم على الفراغ، وإلا
    # ظهر جدول "بيانات" فارغة الخلايا فوق سطر مصدر يتيم (P2: حدود بلا محتوى).
    countries = [c for c in (top_m.get("supplier_countries") or [])
                if c.get("partner") or c.get("value_usd") is not None]
    if countries:
        _add_table(doc, ["الدولة المورّدة", "الحصة", "القيمة"],
                   [[c.get("partner"), fmt_pct(c.get("share")),
                     fmt_money(c.get("value_usd"))] for c in countries[:8]])
        doc.add_paragraph("المصدر: UN Comtrade", style="Intense Quote")
    else:
        doc.add_paragraph("لا بيانات تجارة ثنائية مرصودة لهذا التحليل — "
                          "فجوة معلنة (تتطلب with_research/UN Comtrade).")

    # ═══ ٩) الأسواق المرشّحة الأخرى — كل سوق بجمل تجارية سردية، لا تفريغ ═══
    # مكوّنات خام. سدّ تسريب (الطبقة ٩): "التحليل الإقليمي" اسم مضلِّل —
    # القسم يقارن أسواقاً مرشّحة عالمياً، لا مناطق فرعية داخل سوق واحد؛
    # نفس عنوان المرآة في markdown الآن (كانت هي وحدها سليمة التسمية).
    doc.add_heading("٩. الأسواق المرشّحة الأخرى", level=1)
    from silk_narrative import market_component_lines, confidence_phrase
    for i, m in enumerate((view.get("markets") or [])[:8], 1):
        doc.add_heading(f"٩.{i} {m.get('country')}", level=2)
        lines = market_component_lines(m)
        if lines:
            for line in lines:
                doc.add_paragraph(line, style="List Bullet")
        else:
            doc.add_paragraph("لا مكوّنات مرصودة لهذا السوق — فجوة معلنة")
        doc.add_paragraph(f"الثقة الإجمالية لهذا التقييم: "
                          f"{confidence_phrase(m.get('confidence'))}",
                          style="Intense Quote")

    # ═══ ١٠) المشهد التنافسي ═══
    doc.add_heading("١٠. المشهد التنافسي", level=1)
    _docx_competition_research(doc, top_m)
    _docx_swot(doc, top_m)
    _docx_pricing_layers(doc, top_m)
    prices = top_m.get("prices") or []
    if prices:
        doc.add_heading("أسعار المنتجات في السوق", level=2)
        for pr in prices[:8]:
            doc.add_paragraph(
                f"{pr.get('title') or 'قائمة'}: {_fmt(pr.get('price'))}"
                + (f" {pr['currency']}" if pr.get("currency") else "")
                + (f" — {pr['store']}" if pr.get("store") else ""),
                style="List Bullet")
    named = top_m.get("named_competitors") or []
    if named:
        doc.add_heading("مراجع ويب للمراجعة اليدوية (ليست أسماء منافسين)",
                        level=2)
        for n in named[:8]:
            doc.add_paragraph(str(n), style="List Bullet")
    cp = view.get("competitive_position") or {}
    doc.add_heading("موقعك التنافسي", level=2)
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
                doc.add_paragraph(f"مرجع ويب للمراجعة: {t['name']}",
                                  style="List Bullet")
    else:
        doc.add_paragraph(cp.get("note") or "—")

    # ═══ ١١) استخبارات العميل والطلب ═══
    doc.add_heading("١١. استخبارات العميل والطلب", level=1)
    ins = (cc.get("insights") or [])
    raw_culture = view.get("culture") or []
    if ins:
        for o in ins[:5]:
            doc.add_paragraph(str(o.get("point") or ""), style="List Bullet")
            ev = "؛ ".join(map(str, (o.get("evidence") or [])[:3]))
            if ev:
                doc.add_paragraph(f"الدليل: {ev}", style="Intense Quote")
    elif raw_culture:
        doc.add_paragraph("عناوين مرصودة من بحث الويب (لم تُحلَّل بعد):")
        for c in raw_culture[:6]:
            doc.add_paragraph(str(c.get("title"))[:200], style="List Bullet")
    else:
        doc.add_paragraph("—")
    doc.add_paragraph("صوت العميل المباشر (ما الذي يقدّره المشترون وكيف "
                      "يقيّمون المورّدين) يتطلب بحثاً أولياً — مقابلات أو "
                      "استبيانات — لم يُجرَ بعد؛ هذا القسم يعرض إشارات "
                      "ثانوية فقط.")

    # ═══ ١٢) المشهد التنظيمي والمخاطر ═══
    doc.add_heading("١٢. المشهد التنظيمي والمخاطر", level=1)
    _docx_regulatory(doc, top_m)
    ed_top = top_m.get("entry_decision") or {}
    risks = ed_top.get("risks") or []
    if risks:
        doc.add_heading("سجل المخاطر", level=2)
        _add_table(doc, ["الخطر", "الشدة", "الدليل"],
                   [[r.get("risk"), r.get("severity"), r.get("evidence")]
                    for r in risks if isinstance(r, dict)])

    # ═══ ١٣) الاتجاهات والتوقع المستقبلي ═══
    doc.add_heading("١٣. الاتجاهات والتوقع المستقبلي", level=1)
    series = [p for p in (tr.get("series") or []) if p.get("value") is not None]
    if len(series) >= 2:
        _add_table(doc, ["السنة", "قيمة الاستيراد (دولار)"],
                   [[p.get("year"), _fmt(p.get("value"))] for p in series])
        doc.add_paragraph(f"المصدر: {tr.get('source') or 'UN Comtrade'}",
                          style="Intense Quote")
        # سيناريوهات من المدى التاريخي المرصود حصراً — لا توقع مخترع:
        # التغيّرات السنوية الفعلية => أدنى/وسيط/أقصى نمو ملحوظ.
        changes = []
        for a, b in zip(series, series[1:]):
            va, vb = float(a["value"]), float(b["value"])
            if va > 0:
                changes.append((vb - va) / va * 100.0)
        if changes:
            changes.sort()
            lo, hi = changes[0], changes[-1]
            mid = changes[len(changes) // 2]
            doc.add_paragraph(
                "سيناريوهات مشتقة من المدى التاريخي المرصود (أدنى/أوسط/"
                "أعلى تغيّر سنوي فعلي خلال سنوات الدراسة — ليست تنبؤاً): "
                f"متحفّظ {lo:.1f}% | أساسي {mid:.1f}% | متفائل {hi:.1f}% "
                "سنوياً.")
    else:
        doc.add_paragraph("بيانات الاتجاه غير كافية لهذه السنوات.")

    # ═══ حدود هذا التقرير — قبل التوصيات (§10.3) ═══
    doc.add_heading("حدود هذا التقرير", level=1)
    limits = view.get("limits") or []
    if limits:
        for x in _gap_list_ar(limits[:12]):
            doc.add_paragraph(str(x), style="List Bullet")
    else:
        doc.add_paragraph("لا حدود مسجّلة لهذا التحليل.")

    # ═══ ١٤) التوصيات الاستراتيجية ═══ (قرار الدخول انتقل قرب الخلاصة
    # التنفيذية أعلاه — راجع القسم ٣)
    doc.add_heading("١٤. التوصيات الاستراتيجية", level=1)
    _docx_entry_strategy(doc, top_m)
    for line in view.get("brief") or []:
        doc.add_paragraph(line)

    # ═══ دليل المورّدين والمستوردين ═══ سدّ تسريب (الطبقة ٩): كان هذا
    # القسم مدفوناً كعنوان فرعي (level=2) داخل التوصيات — قسم رئيسي مستقل
    # الآن (level=1، بلا رقم — نفس اصطلاح "حدود هذا التقرير"/"الملحق"
    # القائم أصلاً خارج تسلسل الأقسام الأربعة عشر المرقّم، فلا يكسر قفل
    # الهيكل ١٤ الذي يختبره test_p2_report_structure.py). يظهر دوماً —
    # كما كان قبل النقل — والفجوة (لا مرشّحين) تُعلَن داخل القسم لا بإخفائه.
    doc.add_heading("دليل المورّدين والمستوردين", level=1)
    if top_m.get("suppliers"):
        doc.add_heading("الموردون والأعمال بالاسم", level=2)
        for sup in top_m["suppliers"][:10]:
            doc.add_paragraph(f"{sup.get('name')} — {sup.get('source')}",
                              style="List Bullet")
    _docx_supplier_directory(doc, top_m)

    # ═══ الملحق: تغطية المصادر وأثرها (للمحلّل) ═══
    doc.add_heading("الملحق: تغطية المصادر وأثرها", level=1)
    cov = top_m.get("section_coverage") or {}
    if cov:
        _add_table(doc, ["القسم", "المُسهم/المُحاوَل", "الدرجة"],
                   [[_SEC_AR.get(sec, sec),
                     f"{c['contributed']}/{c['attempted']}", c["score"]]
                    for sec, c in cov.items()])
    # 2B في الملحق: الأقسام دون عتبة الكفاية تُسرد هنا بجملة النقص الوحيدة
    # المسموح بها (مصادر مُحاوَلة) — شفافية المحلّل، لا صياح على وجه التقرير.
    st_all = top_m.get("section_status") or {}
    insuff = [(sec, st) for sec, st in st_all.items()
              if st.get("status") == "insufficient"]
    if insuff:
        doc.add_heading("أقسام دون عتبة الكفاية", level=2)
        from silk_render import insufficient_line
        for sec, st in insuff:
            doc.add_paragraph(insufficient_line(_SEC_AR.get(sec, sec), st))
    prov = view.get("provenance") or []
    if prov:
        doc.add_heading("أثر المصادر (المحاولات والإسهام)", level=2)
        for b in prov:
            doc.add_paragraph(f"{b['source']}: أسهم {b['contributed']} من "
                              f"{b['attempted']} محاولة")
            for f in b.get("failures") or []:
                doc.add_paragraph(f"    فشل مُسجَّل: {f}",
                                  style="Intense Quote")

    _docx_deep_research(doc, view)

    doc.save(path)
    return path


def _md_cell(x: object) -> str:
    """خلية جدول Markdown آمنة — escape pipes/newlines for a table cell."""
    return str(x if x is not None else "—").replace("|", "/").replace("\n", " ")


def _md_deep_research(view: dict, prefix: list[str]) -> str:
    """التقرير الكامل Markdown لنتيجة /research — يُصيَّر من `view["deep_research"]`
    (نفس مصدر اللوحة وتصدير Word عبر `_docx_deep_research`)، لا من قالب /analyze.

    بلاغ حي إنتاجي (تدقيق تمور/هولندا): `render_markdown` كان يُصيّر قالب
    /analyze حصراً — و`markets:[]` لنتيجة بحث عميق تُفرِّغ كل أقسامه («تغطية
    0.0%»، «0 أسواق»، SWOT فارغ، «with_research غير مفعّلة») بينما النصّ
    السردي الغنيّ (HHI، أسعار الرفّ، لوائح EU) موجود في `dr["report"]["text"]`
    ولا يُقرأ أبداً. هذا الفرع يُصيّره فعلاً: ترويسة صادقة + الحكم + السرد
    الكامل + ملحق الأدلة + أثر المصادر + الحدود.
    """
    dr = view.get("deep_research") or {}
    h = view.get("header") or {}
    L = list(prefix)
    verdict = dr.get("verdict") or {}
    ai = verdict.get("ai") or {}

    # ── الترويسة كجدول — نفس القالب لكن بلا حقول /analyze الفارغة ─────────────
    market = dr.get("market") or {}
    L += [f"# سِلك — تقرير بحث سوق معمّق: {view.get('product')}", "",
          "| البند | القيمة |", "| --- | --- |",
          f"| المنتج | {_md_cell(h.get('product') or view.get('product'))} |",
          f"| رمز HS | {_md_cell(h.get('hs_code') or view.get('hs_code'))} "
          f"(ثقة التصنيف {_md_cell(view.get('hs_confidence'))}) |",
          "| المنشأ | السعودية (SAU) |",
          f"| السوق المستهدف | {_md_cell(h.get('target_market') or market.get('name_ar') or market.get('name_en'))} |",
          f"| التاريخ | {_md_cell(h.get('date'))} |",
          f"| الحكم | {_md_cell(view.get('verdict_label') or dr.get('verdict_label'))} |"]
    rc = (dr.get("report") or {}).get("review_cycles") or 0
    if rc:
        L.append(f"| مراجعة التقرير | روجِع عبر {rc} دورة تنقيح |")
    L.append("")

    _bnr = _degraded_banner_text(view)
    if _bnr:
        L += [f"> {_bnr}", ""]

    # ── الحكم وأساسه — من synthesize (نقطة الحكم الوحيدة) ────────────────────
    L += ["## الحكم وأساسه", ""]
    L.append(f"- التوصية: **{view.get('verdict_label') or dr.get('verdict_label') or '—'}**")
    reasoning = ai.get("reasoning") or verdict.get("note")
    if reasoning:
        L += ["", str(reasoning)]
    L.append("")

    # ── التقرير السردي الكامل (كاتب التقرير، مراجَع) — النصّ الغنيّ نفسه ──────
    report_text = (dr.get("report") or {}).get("text")
    if report_text:
        L += [str(report_text).rstrip(), ""]
    else:
        fr = (dr.get("report") or {}).get("failure_reason")
        L += ["## التقرير السردي الكامل", "",
              ("تعذّر إنجاز التقرير السردي التفصيلي في هذه المحاولة"
               + (f" — {fr}" if fr else "")
               + "؛ الأدلة المرصودة والحكم أعلاه قائمة، ويمكن إعادة التوليد "
                 "دون إعادة البحث الكامل."), ""]

    # ── ملحق الأدلة الرقمية — التقاطعات (raw supporting evidence) ────────────
    by_cat = (dr.get("analyst") or {}).get("by_category") or {}
    if any(by_cat.values()):
        L += ["## ملحق: الأدلة الرقمية الداعمة", ""]
        for cat, items in by_cat.items():
            if not items:
                continue
            L.append(f"### {_CATEGORY_AR.get(cat, cat)}")
            for f in items:
                badge = f.get("confidence_badge") or ""
                L.append(f"- {_md_cell(f.get('value'))} "
                         f"[{_md_cell(f.get('source'))} {badge}] "
                         f"{_md_cell(f.get('note') or '')}".rstrip())
            L.append("")

    # ── ملحق أثر المصادر — provenance (البعثات الاثنتا عشرة وإسهامها) ────────
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

    # ── حدود هذا التقرير — declared limits ──────────────────────────────────
    L += ["## حدود هذا التقرير", ""]
    limits = view.get("limits") or ["لا فجوات مرصودة"]
    for x in _gap_list_ar(limits[:12]):
        L.append(f"- {x}")
    L.append("")

    # ── التوصية / المختصر — نفس سطور المختصر (لا صياغة موازية) ───────────────
    L += ["## التوصية / المختصر", ""]
    for line in view.get("brief") or []:
        L.append(f"- {line}")
    if view.get("note"):
        L += ["", str(view["note"])]
    L.append("")
    return "\n".join(L)


def render_markdown(view: dict) -> str:
    """التقرير الكامل Markdown (§7) — نفس أقسام Word وترتيبها، من القالب حصراً.

    كل رقم يليه سطر مصدره بين قوسين؛ المنمذج موسوم «مُقدَّر — نموذج بافتراضات
    معلنة» بمعادلته؛ بوابة 2B نفسها: قسم دون العتبة يطبع سطر النقص الصريح فقط.
    Full Markdown report derived from the ONE canonical view — pure display.
    نتيجة /research (`view["deep_research"]`) تُصيَّر عبر `_md_deep_research`
    (من السرد المراجَع نفسه، لا قالب /analyze الفارغ) — نفس فرع `render_docx`.
    """
    from silk_render import insufficient_line

    _assert_production_clean(view)
    h = view.get("header") or {}
    top_m = (view.get("markets") or [{}])[0]
    st_all = top_m.get("section_status") or {}
    L: list[str] = []
    if view.get("test_run"):
        # بلا اسم متغيّر البيئة على وجه التقرير — نفس صياغة render_text
        # و render_brief (اتساق المشتقات، وإزالة سباكة داخلية من نص عميل).
        L += ["> ⚠ **TEST RUN** — تشغيل برهاني ببدائل موسومة، "
              "ليس تقريراً إنتاجياً", ""]

    # بلاغ حي (تدقيق /research): نتيجة بحث عميق تُصيَّر من deep_research لا من
    # قالب /analyze (markets:[] يُفرّغه) — نفس فرع render_docx.
    if view.get("deep_research"):
        return _md_deep_research(view, L)

    # ── الترويسة كجدول — header table ────────────────────────────────────────
    L += [f"# سِلك — تقرير سوق: {view.get('product')}", "",
          "| البند | القيمة |", "| --- | --- |",
          f"| المنتج | {_md_cell(h.get('product'))} |",
          f"| رمز HS | {_md_cell(h.get('hs_code'))} "
          f"(ثقة التصنيف {_md_cell(view.get('hs_confidence'))}) |",
          "| المنشأ | السعودية (SAU) |",
          f"| السوق المستهدف | {_md_cell(h.get('target_market'))} |",
          f"| التاريخ | {_md_cell(h.get('date'))} |",
          f"| سنة البيانات | {_md_cell(_data_year_label(view))} |",
          f"| تغطية البيانات الإجمالية | {h.get('coverage_pct')}% |", ""]

    # ── ١. الخلاصة التنفيذية — narrative executive summary (حكم واحد لا حكمان) ─
    # P1: ثلاث فقرات بشرية فقط — كفاية البيانات و«قراءة أولية» في المنهجية.
    d = view.get("decision") or {}
    L += ["## الخلاصة التنفيذية", ""]
    L += [f"{para}" for para in _narrative_exec_summary(view)]
    L.append("")

    # ── ٢. منهجية البحث — قسم مستقل ظاهر (§2) ────────────────────────────────
    L += ["## منهجية البحث", ""]
    L += [f"- {line}" for line in _methodology_lines(view)]
    L.append("")

    # ── ٣. تعريف السوق ونطاقه — جملة نطاق صريحة (§3) ─────────────────────────
    L += ["## تعريف السوق ونطاقه", "", _market_scope_paragraph(view), ""]

    # ── قرار الدخول — weighted entry decision ───────────────────────────────
    L += ["## قرار الدخول", ""]
    ed, ed_absent = _entry_decision_of(top_m)
    if ed is None:
        L += [ed_absent, ""]
    else:
        from silk_decision import _WEIGHT_LABEL_AR
        from silk_narrative import confidence_phrase, verdict_ar
        sbo = ed.get("scores_by_option") or {}
        weights_label = ed.get("weights_label") or ed.get("weights_option") or ""
        other_key = "B" if ed.get("weights_option") == "A" else "A"
        other_label = _WEIGHT_LABEL_AR.get(other_key, "")
        L += [f"- الحكم: **{verdict_ar(ed.get('verdict'))}** | "
              f"النقاط: {_fmt(ed.get('score'))}"
              f" | الثقة: {confidence_phrase(ed.get('confidence'))}",
              f"- أساس الثقة: {ed.get('confidence_basis')}",
              f"- منهجية الترجيح المعتمدة: {weights_label} — النقاط "
              f"{_fmt(ed.get('score'))} (بديل مقارنة، {other_label}: "
              f"{_fmt(sbo.get(other_key))})"]
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
            L.append(f"- فجوة معلنة: {_gap_ar(g)}")
        L.append("")

    # ── الأسواق المرشّحة الأخرى — جمل تجارية سردية لا تفريغ مكوّنات خام ──────
    other_markets = (view.get("markets") or [])[1:8]
    if other_markets:
        from silk_narrative import market_component_lines, confidence_phrase
        L += ["## الأسواق المرشّحة الأخرى", ""]
        for m in other_markets:
            L.append(f"### {m.get('country')}")
            lines = market_component_lines(m)
            if lines:
                L += [f"- {line}" for line in lines]
            else:
                L.append("- لا مكوّنات مرصودة لهذا السوق — فجوة معلنة")
            L.append(f"- الثقة الإجمالية لهذا التقييم: "
                     f"{confidence_phrase(m.get('confidence'))}")
            L.append("")

    # ── المنافسة بطبقتيها — دولية (كومتريد) + شركات بالاسم + طبقة الإثراء ────
    L += ["## المنافسة بطبقتيها", ""]
    comp = _ragent(top_m, "competitor")
    if comp:
        from silk_narrative import internal_ar
        L.append("**الطبقة الدولية (تركّز الموردين — UN Comtrade):**")
        for metric in ("hhi", "top_supplier_share_pct", "saudi_share_pct"):
            f = _rfind(comp, metric)
            if f and f.get("value") is not None:
                L.append(f"- {_f_text(f)} ({_f_srcline(f)})")
                if f.get("note"):
                    L.append(f"  - {_gap_ar(f['note'])}")
            else:
                L.append(f"- {internal_ar(metric)}: غير مرصود")
        sc_f = _rfind(comp, "supplier_countries")
        for c in ((sc_f or {}).get("value") or [])[:6]:
            if isinstance(c, dict):
                from silk_narrative import fmt_money
                L.append(f"- {c.get('partner')}: {c.get('share')}% "
                         f"({fmt_money(c.get('value_usd'))}) ({_f_srcline(sc_f)})")
        named_rc = (_rfind(comp, "named_companies") or {}).get("value") or []
        ents_rc, refs_rc = _split_candidates(named_rc)
        L += ["", "**شركات بالاسم (كيانات Google Places، غير موثَّقة):**"]
        if ents_rc:
            for n in ents_rc[:10]:
                L.append(f"- {_entry_text(n)}")
            from silk_narrative import confidence_phrase
            L.append(f"- ملاحظة: كيانات غير موثَّقة — الثقة "
                     f"{confidence_phrase(0.4)} — أكّدها قبل أي تعاقد.")
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
        from silk_narrative import fmt_money
        for c in (top_m.get("supplier_countries") or [])[:6]:
            L.append(f"- {c.get('partner')}: {c.get('share')}% "
                     f"({fmt_money(c.get('value_usd'))}) (المصدر: UN Comtrade)")
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
        from silk_narrative import internal_ar
        L.append("**الطبقة الحدودية (قيم وحدة كومتريد):**")
        for metric in ("border_unit_value_usd_kg",
                       "saudi_border_unit_value_usd_kg", "margin_at_border_pct"):
            f = _rfind(pr, metric)
            if f and f.get("value") is not None:
                L.append(f"- {_f_text(f)} ({_f_srcline(f)})")
                if f.get("note"):
                    L.append(f"  - {_gap_ar(f['note'])}")
            else:
                L.append(f"- {internal_ar(metric)}: غير مرصود")
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
                L.append(f"- فجوة معلنة: {_gap_ar(gap)}")
        else:
            for p in top_m.get("prices") or []:
                L.append(f"- {_listing_text(p)}")
            if not top_m.get("prices"):
                gap = next((g for g in (pr.get("gaps") or [])
                            if "retail_prices" in g),
                           "retail_prices: غير مرصود — فجوة معلنة")
                L.append(f"- {_gap_ar(gap)}")
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
    # سدّ انحراف (الطبقة ٨): عناوين الأرباع كانت ثنائية اللغة هنا
    # ("القوة Strengths") بينما docx عربية صرفة لنفس القسم — نفس الاصطلاح
    # الآن في كلا المشتقّين، لا لغة إنجليزية إضافية على وجه التقرير.
    L += ["## تحليل SWOT (قاعدي من حقائق مرصودة)", ""]
    for key, title in (("S", "القوة"), ("W", "الضعف"),
                       ("O", "الفرص"), ("T", "التهديدات")):
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
        L.append("بيانات غير كافية للشرائح — التقسيم السلوكي/الديموغرافي "
                "يتطلب بحثاً أولياً (مقابلات أو استبيانات) لم يُجرَ بعد؛ "
                "لا يُشتق من بيانات ثانوية")
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
            L.append(f"- فجوة معلنة: {_gap_ar(g)}")
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
    # سدّ انحراف (الطبقة ٨): كانت هذه القائمة تُطبع خامة بلا _gap_list_ar
    # — الآن نفس المعالجة المطبَّقة في docx (اتساق المشتقّين، لا مسارين).
    L += ["## حدود هذا التقرير", ""]
    limits = view.get("limits") or ["لا فجوات مرصودة في الأسواق العليا"]
    for x in _gap_list_ar(limits[:12]):
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
