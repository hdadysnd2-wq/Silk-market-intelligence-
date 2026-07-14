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


def _verdict_tone(vtxt: str) -> str:
    """تصنيف لون شارة الحكم — go (أخضر)/watch (كهرماني)/nogo (أحمر)/
    unknown (رمادي) — نفس منطق تصنيف الشارة في لوحة الواجهة (web/
    index.html، renderDeepResearch) بالضبط، لا معيار مختلف بمصدرين."""
    t = (vtxt or "").upper()
    if "NO-GO" in t or "NO GO" in t:
        return "nogo"
    if "WATCH" in t or "CONDITIONAL" in t:
        return "watch"
    if "GO" in t:
        return "go"
    return "unknown"


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


_VERDICT_TEXT_COLORS = {"go": (0x1E, 0x7D, 0x32), "watch": (0xB8, 0x86, 0x0B),
                        "nogo": (0xC0, 0x00, 0x00), "unknown": (0x60, 0x60, 0x60)}
_VERDICT_HIGHLIGHTS = {"go": "BRIGHT_GREEN", "watch": "YELLOW", "nogo": "RED"}
_VERDICT_LABELS_AR = {"go": "GO — إيجابي", "watch": "WATCH — مراقبة",
                      "nogo": "NO-GO — سلبي", "unknown": "غير محسوم"}


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
                                fmt_money, fmt_pct, internal_ar)
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
         f"التوصية: {d.get('verdict') or 'تعذّر إصدار توصية'}",
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
    """قرار الدخول (المحرك الموزون §8) — verdict/score/pillars/conditions/risks."""
    doc.add_heading("قرار الدخول (المحرك الموزون §8)", level=2)
    ed, absent = _entry_decision_of(m)
    if ed is None:
        doc.add_paragraph(absent)
        return
    from silk_narrative import confidence_phrase
    doc.add_paragraph(f"الحكم: {ed.get('verdict')} | النقاط: {_fmt(ed.get('score'))}"
                      f" | الثقة: {confidence_phrase(ed.get('confidence'))}")
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
    doc.add_heading("حجم السوق — TAM/SAM/SOM", level=2)
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
        doc.add_paragraph("كيانات غير موثَّقة (ثقة 0.4) — أكّدها قبل أي تعاقد.")
    else:
        doc.add_paragraph("لا شركات مرصودة بالاسم في هذا التشغيل "
                          "(أسماء الأعمال تأتي من Google Places حصراً)")
    if refs:
        doc.add_heading("مراجع ويب للمراجعة اليدوية (ليست أسماء منافسين)",
                        level=3)
        for n in refs[:8]:
            doc.add_paragraph(_entry_text(n), style="List Bullet")
    doc.add_paragraph("الطبقة الدولية (تركّز الموردين — UN Comtrade):")
    metrics_rows = []
    for metric in ("hhi", "top_supplier_share_pct", "saudi_share_pct"):
        f = _rfind(ag, metric)
        if f and f.get("value") is not None:
            # وحدة الحقيقة (%) كانت تُسقَط هنا — نفس البند في نسخة الماركداون
            # (_f_text) يعرضها صحيحة؛ إصلاح تناسق: كلاهما يقرأ f['unit'] الآن.
            unit = f" {f['unit']}" if f.get("unit") else ""
            metrics_rows.append([metric, f"{_fmt(f.get('value'))}{unit}",
                                 _f_src_bare(f)])
            if f.get("note"):
                metrics_rows[-1].append(str(f["note"]))
        else:
            metrics_rows.append([metric, "—", "—"])
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
            border_rows.append([metric, "—", "—", "—"])
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

    market = dr.get("market") or {}
    verdict = dr.get("verdict") or {}
    ai = verdict.get("ai") or {}
    doc.add_paragraph(
        f"السوق: {market.get('name_ar') or market.get('name_en')} "
        f"({market.get('iso3')}) — الحكم: "
        f"{ai.get('verdict') or verdict.get('verdict') or 'غير محسوم'}")
    if ai.get("reasoning"):
        doc.add_paragraph(str(ai["reasoning"]), style="Intense Quote")

    doc.add_heading("البعثات الاثنتا عشرة — ملخّص", level=2)
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
    vtxt = ai.get("verdict") or verdict.get("verdict") or "غير محسوم"

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
            "الخلاصة التنفيذية", "البعثات الاثنتا عشرة — ملخّص",
            "التقرير الكامل (كاتب التقرير، مراجَع)",
            "ملحق — الأدلة الرقمية الداعمة للتقاطعات الخمسة",
            "حدود هذا التقرير"), 1):
        doc.add_paragraph(f"{i}. {ttl}")

    # ١) الخلاصة التنفيذية — من حكم التوليف حصراً (المصدر الوحيد للحكم في
    # هذا التقرير) — لا محرك §8 الموزون غير المُغذّى، ولا نص JSON خام.
    doc.add_heading("١. الخلاصة التنفيذية", level=1)
    doc.add_paragraph(f"الحكم: {vtxt}")
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

    # جدول المحتويات الثابت — الأقسام الأربعة عشر بالترتيب.
    doc.add_heading("المحتويات", level=1)
    for i, ttl in enumerate((
            "الخلاصة التنفيذية", "منهجية البحث", "تعريف السوق ونطاقه",
            "نظرة عامة على السوق", "ديناميكيات السوق",
            "حجم السوق والتوقعات", "تحليل التقسيم",
            "تحليل التجارة (استيراد/تصدير)", "التحليل الإقليمي",
            "المشهد التنافسي", "استخبارات العميل والطلب",
            "المشهد التنظيمي والمخاطر", "الاتجاهات والتوقع المستقبلي",
            "التوصيات الاستراتيجية"), 1):
        doc.add_paragraph(f"{i}. {ttl}", style="List Number" if False
                          else None)
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

    # ═══ ٩) التحليل الإقليمي — كل سوق بجمل تجارية سردية، لا تفريغ مكوّنات خام ═══
    doc.add_heading("٩. التحليل الإقليمي (الأسواق المرشّحة)", level=1)
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

    # ═══ ١٤) التوصيات الاستراتيجية ═══
    doc.add_heading("١٤. التوصيات الاستراتيجية", level=1)
    _docx_entry_decision(doc, top_m)
    _docx_entry_strategy(doc, top_m)
    if top_m.get("suppliers"):
        doc.add_heading("الموردون والأعمال بالاسم", level=2)
        for sup in top_m["suppliers"][:10]:
            doc.add_paragraph(f"{sup.get('name')} — {sup.get('source')}",
                              style="List Bullet")
    _docx_supplier_directory(doc, top_m)
    for line in view.get("brief") or []:
        doc.add_paragraph(line)

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
        # بلا اسم متغيّر البيئة على وجه التقرير — نفس صياغة render_text
        # و render_brief (اتساق المشتقات، وإزالة سباكة داخلية من نص عميل).
        L += ["> ⚠ **TEST RUN** — تشغيل برهاني ببدائل موسومة، "
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

    # ── قرار الدخول §8 — weighted entry decision ────────────────────────────
    L += ["## قرار الدخول (المحرك الموزون §8)", ""]
    ed, ed_absent = _entry_decision_of(top_m)
    if ed is None:
        L += [ed_absent, ""]
    else:
        from silk_narrative import confidence_phrase
        sbo = ed.get("scores_by_option") or {}
        L += [f"- الحكم: **{ed.get('verdict')}** | النقاط: {_fmt(ed.get('score'))}"
              f" | الثقة: {confidence_phrase(ed.get('confidence'))}",
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
                from silk_narrative import fmt_money
                L.append(f"- {c.get('partner')}: {c.get('share')}% "
                         f"({fmt_money(c.get('value_usd'))}) ({_f_srcline(sc_f)})")
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
