"""مولّد تقارير سِلك — Silk Word/PDF report generators (المخرجات · V3 deliverables).

يبني مخرجين من نتيجة المحرّك (engine.analyze):
  • build_full_report  — تقرير Word كامل: غلاف + خلاصة تنفيذية (الحكم + أهم ٣ فرص +
    أهم ٣ مخاطر + التوصية الأولى) + تركيب كلود + تفاصيل كل مجموعة (جداول) + ملاحق
    + تذييل إخلاء مسؤولية + ترقيم صفحات + فهرس محتويات.
  • build_short_report — تقرير Word مختصر (١–٢ صفحة): الحكم + أهم ٣ فرص/مخاطر +
    التوصية الأولى + جدول ٥ أرقام رئيسية + تذييل إخلاء المسؤولية.
  • to_pdf            — تحويل docx إلى PDF عبر LibreOffice headless؛ يتدهور بأمان
    إلى None لو LibreOffice غير مثبّت (لا يفشل، لا يختلق).

مبدأ: لا اختلاق — ما ينقص في النتيجة يظهر «غير متوفّر» لا رقماً مُقدّراً. كل الأرقام
تُقرأ من نتيجة المحرّك فقط. python-docx يُستورد بكسل داخل الدوال فيبقى استيراد
الوحدة يعمل بدونه (نفس مبدأ التدهور الآمن في بقية المنصّة).
"""
from __future__ import annotations

import datetime
import io
import logging
import os
import subprocess
import tempfile

log = logging.getLogger(__name__)

# هوية بصرية — brand palette (petrol + gold), matching the platform direction.
_PETROL = (0x0C, 0x3A, 0x3A)
_GOLD = (0xC9, 0xA2, 0x27)
_INK = (0x0C, 0x0E, 0x1A)

# تذييل إخلاء المسؤولية (إلزامي على كل مخرج) — mandatory legal disclaimer footer.
DISCLAIMER = (
    "هذا التقرير أداة مساعدة لاتخاذ القرار مبنية على مصادر عامة، وليس استشارة "
    "قانونية أو جمركية أو مالية رسمية. يُنصح بالتحقق من الجهات الرسمية المختصة "
    "(الجمارك، الهيئات التنظيمية) قبل اتخاذ قرارات تصدير نهائية."
)

_NA = "غير متوفّر"  # not available (never fabricated)


def available() -> bool:
    """هل python-docx متاح؟ — is the docx generator usable right now?"""
    try:
        import docx  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


# ── low-level docx helpers ───────────────────────────────────────────────────

def _rgb(t):
    from docx.shared import RGBColor
    return RGBColor(*t)


def _rtl(paragraph):
    """اجعل الفقرة من اليمين لليسار — mark a paragraph right-to-left (Arabic)."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    pPr = paragraph._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    pPr.append(bidi)
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return paragraph


def _heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    _rtl(p)
    for run in p.runs:
        run.font.color.rgb = _rgb(_PETROL if level <= 1 else _GOLD)
    return p


def _para(doc, text, *, bold=False, size=None, color=None):
    from docx.shared import Pt
    p = doc.add_paragraph()
    _rtl(p)
    run = p.add_run(text)
    run.bold = bold
    if size:
        run.font.size = Pt(size)
    if color:
        run.font.color.rgb = _rgb(color)
    return p


def _page_number_footer(doc):
    """رقم الصفحة في التذييل — add a PAGE field to the section footer."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    footer = doc.sections[0].footer
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    fldChar1 = OxmlElement("w:fldChar"); fldChar1.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText"); instr.set(qn("xml:space"), "preserve")
    instr.text = "PAGE"
    fldChar2 = OxmlElement("w:fldChar"); fldChar2.set(qn("w:fldCharType"), "end")
    run._r.append(fldChar1); run._r.append(instr); run._r.append(fldChar2)


def _toc(doc):
    """فهرس محتويات يُحدّثه Word عند الفتح — a TOC field (populated on open)."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    p = _para(doc, "")
    run = p.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), r'TOC \o "1-2" \h \z \u')
    cache = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = "فهرس المحتويات — يُحدَّث بالضغط F9 في Word."
    cache.append(t)
    fld.append(cache)
    p._p.append(fld)


def _disclaimer_block(doc):
    from docx.shared import Pt
    doc.add_paragraph()
    p = _para(doc, "إخلاء مسؤولية", bold=True, color=_GOLD)
    d = _para(doc, DISCLAIMER, size=9, color=_INK)
    for run in d.runs:
        run.italic = True


# ── data extraction (result -> report inputs; never fabricated) ───────────────

def _dpv(comp):
    return comp.get("value") if isinstance(comp, dict) else comp


def _fmt_usd(v):
    if v is None:
        return _NA
    try:
        n = float(v)
    except (TypeError, ValueError):
        return str(v)
    if n >= 1e9:
        return f"${n/1e9:.1f}B"
    if n >= 1e6:
        return f"${n/1e6:.1f}M"
    if n >= 1e3:
        return f"${n/1e3:.0f}K"
    return f"${n:,.0f}"


def _fmt_num(v):
    if v is None:
        return _NA
    try:
        return f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return str(v)


def _exec_summary(result: dict) -> dict:
    """الخلاصة التنفيذية — verdict + top-3 opportunities/risks + first recommendation.

    Prefers the Claude synthesis of the top market; falls back to the
    deterministic jury verdict. Missing pieces are marked _NA — never invented.
    """
    markets = result.get("markets") or []
    top = markets[0] if markets else {}
    syn = top.get("synthesis") or {}
    jury = top.get("jury") or {}
    verdict = syn.get("verdict") or (jury.get("verdict") or _NA)
    opportunities = (syn.get("opportunities") or [])[:3]
    risks = (syn.get("risks") or [])[:3]
    recs = syn.get("recommendations") or []
    first_rec = recs[0] if recs else _NA
    return {
        "top_market": top.get("country") or _NA,
        "verdict": verdict,
        "opportunities": opportunities,
        "risks": risks,
        "first_recommendation": first_rec,
        "has_synthesis": bool(syn),
    }


def _key_numbers(result: dict) -> list[tuple[str, str]]:
    """أهم ٥ أرقام للسوق الأعلى — headline numbers table rows (label, value)."""
    markets = result.get("markets") or []
    top = markets[0] if markets else {}
    comps = top.get("components", {}) or {}
    tariff = top.get("tariff")
    tariff_v = _dpv(tariff) if tariff else None
    return [
        ("حجم الاستيراد (السوق)", _fmt_usd(_dpv(comps.get("market_size")))),
        ("حصة السعودية %", (_NA if _dpv(comps.get("saudi_position")) is None
                            else f"{_dpv(comps.get('saudi_position'))}%")),
        ("دخل الفرد (PPP)", _fmt_usd(top.get("income_ppp"))),
        ("عدد السكان", _fmt_num(top.get("population"))),
        ("التعريفة المطبّقة %", (_NA if tariff_v is None else f"{tariff_v}%")),
    ]


# ── report builders ──────────────────────────────────────────────────────────

def _new_doc():
    import docx
    doc = docx.Document()
    _page_number_footer(doc)
    return doc


def _cover(doc, result, subtitle):
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    for _ in range(3):
        doc.add_paragraph()
    t = _para(doc, "منصة سِلك · ذكاء الأسواق", bold=True, size=26, color=_PETROL)
    t.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s = _para(doc, subtitle, bold=True, size=16, color=_GOLD)
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    prod = f"{result.get('product', _NA)}  (HS {result.get('hs_code', _NA)})"
    p = _para(doc, prod, size=14)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    yr = _para(doc, f"سنة البيانات: {result.get('year', _NA)}", size=12)
    yr.alignment = WD_ALIGN_PARAGRAPH.CENTER
    today = datetime.date.today().isoformat()
    d = _para(doc, f"تاريخ التقرير: {today}", size=11, color=_INK)
    d.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _summary_section(doc, result):
    _heading(doc, "الخلاصة التنفيذية", level=1)
    es = _exec_summary(result)
    _para(doc, f"السوق الأعلى ترشيحاً: {es['top_market']}", bold=True)
    _para(doc, f"الحكم: {es['verdict']}", bold=True, color=_PETROL)
    if not es["has_synthesis"]:
        _para(doc, "ملاحظة: لم تُفعّل طبقة التركيب (Claude)؛ الحكم من اللجنة "
                   "الحتمية. فعّل with_synthesis لفرص/مخاطر مفصّلة.", size=9)
    _heading(doc, "أهم الفرص", level=2)
    if es["opportunities"]:
        for o in es["opportunities"]:
            _rtl(doc.add_paragraph(str(o), style="List Bullet"))
    else:
        _para(doc, _NA)
    _heading(doc, "أهم المخاطر", level=2)
    if es["risks"]:
        for r in es["risks"]:
            _rtl(doc.add_paragraph(str(r), style="List Bullet"))
    else:
        _para(doc, _NA)
    _heading(doc, "التوصية الأولى", level=2)
    _para(doc, str(es["first_recommendation"]))


def _key_numbers_table(doc, result):
    _heading(doc, "أهم الأرقام", level=2)
    rows = _key_numbers(result)
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    hdr[0].paragraphs[0].add_run("المؤشّر").bold = True
    hdr[1].paragraphs[0].add_run("القيمة").bold = True
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value


def _markets_ranking_table(doc, result):
    _heading(doc, "الأسواق مرتّبة", level=1)
    markets = result.get("markets") or []
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(("#", "السوق", "الاستيراد", "حصة السعودية %", "النقاط")):
        table.rows[0].cells[i].paragraphs[0].add_run(h).bold = True
    for i, m in enumerate(markets, 1):
        comps = m.get("components", {}) or {}
        share = _dpv(comps.get("saudi_position"))
        cells = table.add_row().cells
        cells[0].text = str(i)
        cells[1].text = str(m.get("country") or _NA)
        cells[2].text = _fmt_usd(_dpv(comps.get("market_size")))
        cells[3].text = _NA if share is None else f"{share}%"
        cells[4].text = _NA if m.get("total_score") is None else f"{m.get('total_score')}"


def _synthesis_section(doc, result):
    markets = result.get("markets") or []
    top = markets[0] if markets else {}
    syn = top.get("synthesis")
    if not syn:
        return
    _heading(doc, f"تحليل كلود — {top.get('country', '')}", level=1)
    if syn.get("gaps"):
        _heading(doc, "فجوات البيانات", level=2)
        for g in syn["gaps"]:
            _rtl(doc.add_paragraph(str(g), style="List Bullet"))
    _para(doc, f"المصدر: {syn.get('by', 'Claude')} · قرار أوّلي", size=9, color=_INK)


def _group_details(doc, result):
    """تفاصيل كل مجموعة للسوق الأعلى — per-group detail tables (real findings only)."""
    markets = result.get("markets") or []
    top = markets[0] if markets else {}
    _heading(doc, f"التفاصيل حسب المجموعة — {top.get('country', '')}", level=1)
    group_keys = {
        "التجارة وحجم السوق": ["production", "market_size"],
        "الاقتصاد والديموغرافيا": ["cities", "religion", "currency_risk"],
        "المنافسة والتوزيع": ["competitors_web", "distribution_channels",
                              "ecommerce", "bestsellers", "maps", "volza", "explee"],
        "السعر والاشتراطات": ["localprice", "price_comparison", "tariff",
                             "regulatory", "customs_web"],
        "الثقافة والسلوك التجاري": ["cultural", "business_culture", "exhibitions",
                                   "trends", "faostat"],
    }
    any_data = False
    for label, keys in group_keys.items():
        facts = []
        for k in keys:
            facts += _facts_of(top.get(k))
        if not facts:
            continue
        any_data = True
        _heading(doc, label, level=2)
        for f in facts[:6]:
            _rtl(doc.add_paragraph(f, style="List Bullet"))
    if not any_data:
        _para(doc, "لم تُفعَّل طبقات المجموعات الإضافية لهذا التحليل.", size=9)


def _facts_of(items):
    """حقائق حقيقية مقروءة من عنصر — real (non-None) HUMAN-READABLE short facts.

    يستخرج الحقل المقروء من القيم المُهيكلة (اسم/عنوان/شركة…) بدل طباعة dict خام،
    ويُلحق الملاحظة لتوضيح الأرقام المجرّدة (تعريفة 0، مؤشّر تريندز 78…). Never a
    raw ``{'name': ...}`` repr, never a context-free bare number."""
    out = []
    if items is None:
        return out
    seq = items if isinstance(items, list) else [items]
    for it in seq:
        if isinstance(it, dict) and "value" in it:
            val, note = it.get("value"), (it.get("note") or "")
        else:
            val, note = it, ""
        if val is None or val == "" or val == []:
            continue
        if isinstance(val, dict):  # قيمة مُهيكلة -> الحقل المقروء لا الـdict الخام
            label = (val.get("name") or val.get("title") or val.get("company")
                     or val.get("importer") or val.get("store"))
            if label is None:
                label = "، ".join(f"{k}: {v}" for k, v in val.items()
                                  if v not in (None, "", []))
            s = str(label)
        else:
            s = str(val)
        if note and note not in s:  # سياق للأرقام المجرّدة والقيم القصيرة
            s = f"{s} — {note}"
        out.append(s[:220])
    return out


def _save(doc) -> bytes:
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def build_full_report(result: dict) -> bytes:
    """التقرير الكامل — full Word report bytes. Raises RuntimeError if docx absent."""
    if not available():
        raise RuntimeError("python-docx not installed — run: pip install python-docx")
    doc = _new_doc()
    _cover(doc, result, "تقرير دراسة سوق تصديري — كامل")
    doc.add_page_break()
    _heading(doc, "المحتويات", level=1)
    _toc(doc)
    doc.add_page_break()
    _summary_section(doc, result)
    _synthesis_section(doc, result)
    _markets_ranking_table(doc, result)
    _group_details(doc, result)
    _disclaimer_block(doc)
    return _save(doc)


def build_short_report(result: dict) -> bytes:
    """التقرير المختصر — 1–2 page Word report bytes. Raises if docx absent."""
    if not available():
        raise RuntimeError("python-docx not installed — run: pip install python-docx")
    doc = _new_doc()
    _cover(doc, result, "الخلاصة التنفيذية — مختصر")
    doc.add_page_break()
    _summary_section(doc, result)
    _key_numbers_table(doc, result)
    _disclaimer_block(doc)
    return _save(doc)


def to_pdf(docx_bytes: bytes) -> bytes | None:
    """حوّل docx إلى PDF عبر LibreOffice — None if LibreOffice is unavailable.

    Graceful: on a missing soffice binary or any conversion error returns None
    (caller surfaces a clear message) — never raises, never fabricates a file.
    """
    soffice = _soffice_bin()
    if not soffice:
        log.warning("LibreOffice not found — PDF export unavailable")
        return None
    try:
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "report.docx")
            with open(src, "wb") as f:
                f.write(docx_bytes)
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", d, src],
                check=True, capture_output=True, timeout=120)
            pdf = os.path.join(d, "report.pdf")
            if not os.path.exists(pdf):
                log.warning("LibreOffice produced no PDF")
                return None
            with open(pdf, "rb") as f:
                return f.read()
    except Exception as e:  # noqa: BLE001 — conversion is best-effort
        log.warning("PDF conversion failed: %s", e)
        return None


def _soffice_bin() -> str | None:
    """موقع LibreOffice — locate the soffice/libreoffice binary, or None."""
    import shutil
    for name in ("soffice", "libreoffice"):
        path = shutil.which(name)
        if path:
            return path
    return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo = {"product": "تمور", "hs_code": "080410", "year": 2022,
            "markets": [{"country": "مصر",
                         "components": {"market_size": {"value": 2.4e8},
                                        "saudi_position": {"value": 44}},
                         "income_ppp": 14800, "population": 111000000,
                         "total_score": 0.74,
                         "jury": {"verdict": "PRELIMINARY GO"},
                         "synthesis": {"verdict": "WATCH",
                                       "opportunities": ["سوق كبير"],
                                       "risks": ["منافسة عراقية"],
                                       "recommendations": ["ابدأ بشحنة تجريبية"],
                                       "gaps": ["مجموعة غير متوفّرة: الثقافة"],
                                       "by": "Claude"}}]}
    if available():
        full = build_full_report(demo)
        short = build_short_report(demo)
        print(f"full report: {len(full)} bytes; short: {len(short)} bytes")
        pdf = to_pdf(short)
        print("short PDF:", f"{len(pdf)} bytes" if pdf else "unavailable (no LibreOffice)")
    else:
        print("python-docx not installed — reports unavailable (graceful)")
