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


def _hex(t):
    return "%02X%02X%02X" % t


def _shade(cell, rgb_tuple):
    """ظلّل خلية جدول بلون — fill a table cell background (for bands/cards/verdict)."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), _hex(rgb_tuple))
    tcPr.append(shd)


def _no_borders(table):
    """أزل حدود الجدول — borderless table (used for bands & KPI cards)."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "none")
        borders.append(el)
    tblPr.append(borders)


def _band(doc, text, *, fill=_PETROL, color=(0xFF, 0xFF, 0xFF), size=22, bold=True):
    """شريط لوني عرضيّ — a full-width colored band (cover header/footer, section rule)."""
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    table = doc.add_table(rows=1, cols=1)
    _no_borders(table)
    cell = table.rows[0].cells[0]
    _shade(cell, fill)
    p = cell.paragraphs[0]
    _rtl(p)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.color.rgb = _rgb(color)
    return table


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
    # شريط الهوية العلوي — top brand band gives immediate visual weight.
    _band(doc, "منصة سِلك · ذكاء الأسواق", fill=_PETROL, color=(0xFF, 0xFF, 0xFF), size=24)
    # شعار/رمز — a simple emblem mark under the band.
    for _ in range(2):
        doc.add_paragraph()
    emblem = _para(doc, "◆", bold=True, size=40, color=_GOLD)
    emblem.alignment = WD_ALIGN_PARAGRAPH.CENTER
    s = _para(doc, subtitle, bold=True, size=17, color=_GOLD)
    s.alignment = WD_ALIGN_PARAGRAPH.CENTER
    prod = _para(doc, str(result.get("product", _NA)), bold=True, size=22, color=_PETROL)
    prod.alignment = WD_ALIGN_PARAGRAPH.CENTER
    hs = _para(doc, f"رمز HS {result.get('hs_code', _NA)}", size=13, color=_INK)
    hs.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for _ in range(2):
        doc.add_paragraph()
    # شريط ملخّص على الغلاف: السوق الأعلى + الحكم + النقاط — a cover KPI strip.
    markets = result.get("markets") or []
    top = markets[0] if markets else {}
    es = _exec_summary(result)
    score = top.get("total_score")
    score_s = _NA if score is None else f"{int(score * 100)}/100" if score <= 1 else f"{score}"
    _kpi_cards(doc, [
        ("السوق الأعلى", str(es["top_market"])),
        ("الحكم المبدئي", str(es["verdict"])),
        ("قوة الترشيح", score_s),
    ])
    for _ in range(3):
        doc.add_paragraph()
    today = datetime.date.today().isoformat()
    meta = _para(doc, f"سنة البيانات: {result.get('year', _NA)}   ·   تاريخ التقرير: {today}",
                 size=11, color=_INK)
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _kpi_cards(doc, pairs):
    """صف بطاقات مؤشّرات — a row of shaded KPI cards (label + big value)."""
    from docx.shared import Pt
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    table = doc.add_table(rows=2, cols=len(pairs))
    _no_borders(table)
    table.alignment = 1  # center
    for i, (label, value) in enumerate(pairs):
        lc = table.rows[0].cells[i]
        vc = table.rows[1].cells[i]
        _shade(lc, _PETROL)
        _shade(vc, (0xF2, 0xF4, 0xF4))
        lp = lc.paragraphs[0]; _rtl(lp); lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        lr = lp.add_run(label); lr.bold = True; lr.font.size = Pt(10)
        lr.font.color.rgb = _rgb((0xFF, 0xFF, 0xFF))
        vp = vc.paragraphs[0]; _rtl(vp); vp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        vr = vp.add_run(str(value)); vr.bold = True; vr.font.size = Pt(15)
        vr.font.color.rgb = _rgb(_PETROL)
    return table


def _summary_section(doc, result):
    _heading(doc, "الخلاصة التنفيذية", level=1)
    es = _exec_summary(result)
    _para(doc, f"السوق الأعلى ترشيحاً: {es['top_market']}", bold=True)
    # شريط الحكم البارز — a prominent verdict banner (gold), not a plain line.
    _band(doc, f"الحكم المبدئي:  {es['verdict']}", fill=_GOLD, color=_INK, size=15)
    doc.add_paragraph()
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


def _score_bar(score):
    """شريط نصّي لقوة الترشيح — a compact text bar (████░░) for a 0..1 or 0..100 score."""
    if score is None:
        return _NA
    pct = score * 100 if score <= 1 else score
    pct = max(0, min(100, pct))
    filled = int(round(pct / 10))
    return "█" * filled + "░" * (10 - filled) + f"  {int(pct)}"


def _markets_ranking_table(doc, result):
    _heading(doc, "الأسواق مرتّبة", level=1)
    markets = result.get("markets") or []
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 1"
    for i, h in enumerate(("#", "السوق", "الاستيراد", "حصة السعودية %", "قوة الترشيح")):
        table.rows[0].cells[i].paragraphs[0].add_run(h).bold = True
    for i, m in enumerate(markets, 1):
        comps = m.get("components", {}) or {}
        share = _dpv(comps.get("saudi_position"))
        cells = table.add_row().cells
        cells[0].text = str(i)
        cells[1].text = str(m.get("country") or _NA)
        cells[2].text = _fmt_usd(_dpv(comps.get("market_size")))
        cells[3].text = _NA if share is None else f"{share}%"
        cells[4].text = _score_bar(m.get("total_score"))


def _synthesis_section(doc, result):
    """تحليل كلود السردي الكامل — the FULL narrative analysis for the top market:
    verdict + confidence, per-group narrative summaries, opportunities, risks,
    recommendations, then data gaps + source. This is the platform's core written
    decision (V3 goal: «دراسة سوق شاملة + قرار دخول مبدئي واضح») — never a hollow
    heading. Renders only what the synthesis really produced (no fabrication)."""
    markets = result.get("markets") or []
    top = markets[0] if markets else {}
    syn = top.get("synthesis")
    if not syn:
        return
    _heading(doc, f"تحليل كلود — {top.get('country', '')}", level=1)
    # الحكم المبدئي + الثقة (نوعية محسوبة) — decision + DERIVED qualitative confidence.
    conf = syn.get("confidence")
    conf_s = "" if conf is None else f"  ·  الثقة: {conf}"
    _para(doc, f"الحكم المبدئي: {syn.get('verdict', _NA)}{conf_s}",
          bold=True, color=_PETROL)
    if syn.get("confidence_basis"):  # مصدر الثقة صريح — no false-precision decimal.
        _para(doc, str(syn["confidence_basis"]), size=9, color=_INK)

    def _bullets(title, items):
        _heading(doc, title, level=2)
        if items:
            for it in items:
                _rtl(doc.add_paragraph(str(it), style="List Bullet"))
        else:
            _para(doc, _NA)

    # السرد التحليلي حسب المجموعة (ملخّصات المرحلة ١) — the written reasoning body.
    summaries = syn.get("summaries") or {}
    if summaries:
        _heading(doc, "التحليل حسب المجموعة", level=2)
        for label, text in summaries.items():
            _para(doc, str(label), bold=True, color=_GOLD)
            _para(doc, str(text))

    _bullets("الفرص", syn.get("opportunities"))
    _bullets("المخاطر", syn.get("risks"))
    _bullets("التوصيات", syn.get("recommendations"))
    if syn.get("gaps"):
        _bullets("فجوات البيانات", syn.get("gaps"))
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


def _kv_table(doc, pairs, *, header=("المؤشّر", "القيمة")):
    """جدول مؤشّر/قيمة — a labeled two-column table (overview blocks)."""
    table = doc.add_table(rows=1, cols=2)
    table.style = "Light Grid Accent 1"
    h = table.rows[0].cells
    h[0].paragraphs[0].add_run(header[0]).bold = True
    h[1].paragraphs[0].add_run(header[1]).bold = True
    for label, value in pairs:
        c = table.add_row().cells
        c[0].text = str(label)
        c[1].text = _NA if value in (None, "") else str(value)
    return table


def _competitor_table(doc, competitors):
    """جدول الدول المنافسة وحصصها — competing suppliers table (partner/share/value)."""
    rows = [c for c in (competitors or []) if isinstance(c, dict)]
    if not rows:
        return False
    _para(doc, "الدول المنافسة على السوق (بحصصها من الاستيراد):", bold=True, color=_PETROL)
    table = doc.add_table(rows=1, cols=3)
    table.style = "Light Grid Accent 1"
    for i, hh in enumerate(("المورّد المنافس", "الحصة %", "القيمة")):
        table.rows[0].cells[i].paragraphs[0].add_run(hh).bold = True
    for c in rows[:8]:
        cells = table.add_row().cells
        cells[0].text = str(c.get("partner") or c.get("name") or _NA)
        sh = c.get("share")
        cells[1].text = _NA if sh is None else f"{sh}%"
        cells[2].text = _fmt_usd(c.get("value_usd"))
    return True


def _facts_block(doc, title, *keys_source, limit=8):
    """كتلة حقائق مقروءة تحت عنوان — a titled bullet block from one or more fields."""
    facts = []
    for src in keys_source:
        facts += _facts_of(src)
    if not facts:
        return False
    _para(doc, title, bold=True, color=_GOLD)
    for f in facts[:limit]:
        _rtl(doc.add_paragraph(f, style="List Bullet"))
    return True


def _price_positioning(doc, m):
    """موضع السعر — own price vs. observed local listings (if computed)."""
    pc = m.get("price_comparison")
    if not isinstance(pc, dict) or pc.get("your_price") is None or not pc.get("listings_count"):
        return _facts_block(doc, "إشارات أسعار التجزئة (بحث ويب):", m.get("localprice"))
    _kv_table(doc, [
        ("سعرك المُدخل", pc.get("your_price")),
        ("متوسط السوق المرصود", pc.get("market_avg")),
        ("أدنى–أعلى", f"{pc.get('market_min')} – {pc.get('market_max')}"),
        ("عدد القوائم المقارَنة", pc.get("listings_count")),
        ("الموقع التنافسي", pc.get("verdict")),
    ], header=("مقارنة السعر", "القيمة"))
    return True


def _market_deep_dive(doc, m, rank):
    """دراسة سوق معمّقة — a full per-market deep-dive section with tables + narrative."""
    country = m.get("country") or m.get("iso3") or _NA
    comps = m.get("components", {}) or {}
    _heading(doc, f"دراسة السوق #{rank}: {country}", level=1)

    # 1) لمحة عامة — overview KV table
    tariff = m.get("tariff")
    tariff_v = _dpv(tariff) if tariff else None
    _kv_table(doc, [
        ("قوة الترشيح", _score_bar(m.get("total_score"))),
        ("حجم استيراد السوق", _fmt_usd(_dpv(comps.get("market_size")))),
        ("حصة السعودية الحالية", (_NA if _dpv(comps.get("saudi_position")) is None
                                  else f"{_dpv(comps.get('saudi_position'))}%")),
        ("دخل الفرد (PPP)", _fmt_usd(m.get("income_ppp"))),
        ("عدد السكان", _fmt_num(m.get("population"))),
        ("المنافس المهيمن", m.get("top_competitor")),
        ("التعريفة المطبّقة", (_NA if tariff_v is None else f"{tariff_v}%")),
    ], header=("لمحة عامة عن السوق", "القيمة"))

    # 2) المشهد التنافسي — competitive landscape
    _heading(doc, "المشهد التنافسي والتوزيع", level=2)
    _competitor_table(doc, m.get("competitors"))
    _facts_block(doc, "لاعبون بالاسم (بحث ويب):", m.get("competitors_web"),
                 m.get("importers"))
    _facts_block(doc, "قنوات التوزيع والتجارة الإلكترونية:", m.get("distribution_channels"),
                 m.get("ecommerce"))

    # 3) السعر والاشتراطات — price + regulatory
    _heading(doc, "السعر والاشتراطات التنظيمية", level=2)
    _price_positioning(doc, m)
    _facts_block(doc, "اشتراطات التغليف/الملصقات/الشهادات:", m.get("regulatory"))
    _facts_block(doc, "الجمارك الرسمية:", m.get("customs_web"))

    # 4) الثقافة والسلوك التجاري — culture + business
    _heading(doc, "الثقافة والسلوك التجاري", level=2)
    _facts_block(doc, "عادات الاستهلاك ونمط الحياة:", m.get("cultural"))
    _facts_block(doc, "أعراف التفاوض والدفع وآداب العمل:", m.get("business_culture"))
    _facts_block(doc, "المعارض التجارية:", m.get("exhibitions"))
    _facts_block(doc, "مؤشّر الطلب (Google Trends):", m.get("trends"))
    _facts_block(doc, "الديموغرافيا والمدن والعملة:", m.get("cities"),
                 m.get("religion"), m.get("currency_risk"))

    # 5) تحليل كلود لهذا السوق — Claude's synthesis for THIS market
    if m.get("synthesis"):
        _heading(doc, "تحليل كلود", level=2)
        _one_market_synthesis(doc, m["synthesis"])


def _one_market_synthesis(doc, syn):
    """يعرض تركيب كلود لسوق واحد — render one market's synthesis fully (reused)."""
    conf = syn.get("confidence")
    conf_s = "" if conf is None else f"  ·  الثقة: {conf}"
    _band(doc, f"الحكم المبدئي:  {syn.get('verdict', _NA)}{conf_s}", fill=_GOLD,
          color=_INK, size=14)
    if syn.get("confidence_basis"):
        _para(doc, str(syn["confidence_basis"]), size=9, color=_INK)

    def _bul(title, items):
        if not items:
            return
        _para(doc, title, bold=True, color=_PETROL)
        for it in items:
            _rtl(doc.add_paragraph(str(it), style="List Bullet"))

    for label, text in (syn.get("summaries") or {}).items():
        _para(doc, str(label), bold=True, color=_GOLD)
        _para(doc, str(text))
    _bul("الفرص", syn.get("opportunities"))
    _bul("المخاطر", syn.get("risks"))
    _bul("التوصيات", syn.get("recommendations"))
    _bul("فجوات البيانات", syn.get("gaps"))
    _para(doc, f"المصدر: {syn.get('by', 'Claude')} · قرار أوّلي", size=9, color=_INK)


def _methodology_section(doc, result):
    """المنهجية والمصادر — how the study was built (credibility, no fabrication)."""
    _heading(doc, "المنهجية ومبدأ البيانات", level=1)
    _para(doc, "تعتمد هذه الدراسة على بيانات عامة حقيقية فقط، معالَجة عبر طبقات وكلاء "
               "متخصّصة ثم مُركّبة بحكم أوّلي. المبدأ التأسيسي: لا اختلاق — كل قيمة غير "
               "متوفّرة تُعلَّم صراحةً «غير متوفّر» ولا تُقدَّر برقم.")
    _kv_table(doc, [
        ("التجارة وحجم السوق", "UN Comtrade + World Bank WITS (استيراد، حصص، تعريفة)"),
        ("الاقتصاد والديموغرافيا", "World Bank + مراجع سكانية/دينية/عملات"),
        ("المنافسة والتوزيع", "بحث ويب ديناميكي (منافسون، قنوات، تجارة إلكترونية)"),
        ("السعر والاشتراطات", "بحث ويب (أسعار تجزئة، تنظيمي، جمارك رسمية)"),
        ("الثقافة والسلوك", "بحث ويب + Google Trends"),
        ("التركيب والحكم", f"Claude (تركيب على مرحلتين) — قرار أوّلي لا نهائي"),
    ], header=("طبقة البيانات", "المصدر"))
    _para(doc, "الثقة مصنّفة نوعياً (عالية/متوسطة/منخفضة) ومحسوبة من تغطية البيانات "
               "لكل سوق، لا رقماً تقديرياً.", size=9, color=_INK)


def _sources_appendix(doc, result):
    """ملحق المصادر — the consolidated list of provenance tags seen across markets."""
    seen = []
    for m in result.get("markets") or []:
        comps = m.get("components", {}) or {}
        for c in comps.values():
            src = c.get("source") if isinstance(c, dict) else None
            if src and src not in seen:
                seen.append(src)
        for key in ("competitors_web", "distribution_channels", "regulatory",
                    "customs_web", "localprice", "cultural", "business_culture",
                    "exhibitions", "trends", "tariff"):
            for f in (m.get(key) or []) if isinstance(m.get(key), list) else [m.get(key)]:
                src = (f.get("source") if isinstance(f, dict) else
                       getattr(f, "source", None))
                if src and src not in seen:
                    seen.append(src)
    if not seen:
        return
    _heading(doc, "ملحق: المصادر", level=1)
    for s in seen:
        _rtl(doc.add_paragraph(str(s), style="List Bullet"))


def build_full_report(result: dict) -> bytes:
    """التقرير الكامل — a comprehensive multi-section market study (Word bytes).

    غلاف + محتويات + خلاصة تنفيذية + منهجية ومصادر + ترتيب الأسواق + دراسة معمّقة
    لكل سوق من الأعلى (لمحة، منافسة، سعر/تنظيم، ثقافة، حكم كلود) + ملحق مصادر +
    إخلاء مسؤولية. Raises RuntimeError if python-docx is absent."""
    if not available():
        raise RuntimeError("python-docx not installed — run: pip install python-docx")
    doc = _new_doc()
    _cover(doc, result, "تقرير دراسة سوق تصديري — كامل")
    doc.add_page_break()
    _heading(doc, "المحتويات", level=1)
    _toc(doc)
    doc.add_page_break()
    _summary_section(doc, result)
    _key_numbers_table(doc, result)   # أهم الأرقام في التقرير الكامل أيضاً — headline KPIs
    doc.add_page_break()
    _methodology_section(doc, result)
    doc.add_page_break()
    _markets_ranking_table(doc, result)
    # دراسة معمّقة لأعلى ٣ أسواق — a full deep-dive per top market.
    for rank, m in enumerate((result.get("markets") or [])[:3], 1):
        doc.add_page_break()
        _market_deep_dive(doc, m, rank)
    _sources_appendix(doc, result)
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
