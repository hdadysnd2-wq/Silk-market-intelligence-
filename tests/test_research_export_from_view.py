"""أقفال إصلاح تصدير /research (تدقيق حيّ: تمور × هولندا).

البلاغ الإنتاجي: اللوحة تعرض تقرير البحث العميق الغنيّ (مراجَع، دورتان، أسعار
رفّ، HHI، لوائح EU)، لكن `GET /analyses/{id}/report.md` كان يعيد قالب /analyze
الفارغ («تغطية 0.0%»، «سنة البيانات None»، «with_research غير مفعّلة»، «0 أسواق»،
SWOT فارغ) و`GET /analyses/{id}/report.docx` يفشل 501 — لأن كلا المُصدِّرَين
لم يقرأا `dr["report"]`.

الأقفال:
  - report.md لنتيجة بحث يُصيَّر من deep_research (السرد نفسه)، لا قالب /analyze.
  - أرقام الصدق: «ثقة التصنيف»/«سنة البيانات» تُعرَض «—» لا نصّ "None".
  - report.docx (تقرير العميل) لا يفشل 501 حين يحمل السرد لغة حكم مُعرَّبة
    («درجة الثقة») — تُحوَّل تجارياً بدل نسف التصدير.

**شكل المدوّنة**: يُعاد بناء المفاتيح الدقيقة من `api._run_research_pipeline`
(الشكل المخزَّن الموثوق: markets:[]، deep_research{missions,analyst,verdict,
report,trace_id,budget_status}، market{iso3,m49,iso2,name_en,name_ar}،
data_economics) — لا مدوّنة مثالية مبسّطة. قاعدة الإنتاج الحيّة على Railway غير
قابلة للوصول من مِعزل CI (البروكسي يمنع مضيف Railway)، والتتبّع غير محلّي؛
فالشكل مُعاد بناؤه من الكود الذي يكتب المدوّنة نفسها.
"""
from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


@contextlib.contextmanager
def _env(**vals):
    old = {k: os.environ.get(k) for k in vals}
    try:
        for k, v in vals.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _dp(value, source="UN Comtrade", conf=0.8, note="", ra="2026-07-15"):
    return {"value": value, "source": source, "confidence": conf,
            "note": note, "retrieved_at": ra}


# السرد الحقيقي — بنية الكاتب الأحد عشر قسماً (silk_ai_judge._REPORT_SECTIONS)
# مع لغة حكم مُعرَّبة ("confidence"→«درجة الثقة» عبر _strip_internal_plumbing)
# التي أسقطت تصدير العميل بـ501، وأرقام غنيّة (HHI، أسعار رفّ، لوائح EU).
_REPORT_TEXT = """## 1. الخلاصة التنفيذية
الحكم WATCH بدرجة ثقة 0.6 (confidence). واردات هولندا من التمور تنمو 8% سنوياً،
والمشهد تنافسي مفتّت (HHI 940). أسعار الرفّ 6.20–9.80 يورو/كغم.

## 2. منهجية البحث ونطاقه
اثنتا عشرة بعثة بحث، جميعها ناجحة، ثم محلّل شامل فكاتب التقرير بدورتَي مراجعة.

## 3. نظرة عامة على السوق وحجمه
واردات 2023 نحو 42 مليون دولار.

## 4. ديناميكيات السوق
نمو مطّرد مدفوع بالطلب على المنتجات الصحية.

## 5. تحليل المستهلك والطلب
شريحتان: تجزئة راقية وجاليات.

## 6. المشهد التنافسي
مورّدون: تونس، الجزائر، إيران. مؤشر التركّز HHI = 940 (سوق مفتّت).

## 7. التنظيم والوصول للسوق
EU 2017/625 (منشأة معتمدة إلزامية)، EU 1169/2011 (وسم المستهلك).

## 8. اللوجستيات وسلسلة الإمداد
شحن بحري عبر ميناء روتردام.

## 9. تقييم المخاطر
تقلّب أسعار المنافسين؛ لا مخاطر تنظيمية حادة.

## 10. التوصيات الاستراتيجية
ابدأ باختبار السوق قبل الالتزام الكامل.
### خارطة طريق الدخول
1. تحقّق من المستوردين. 2. سجّل المنشأة لدى الجهة المختصة.

## 11. الملاحق
UN Comtrade, World Bank, Google Maps."""


def _netherlands_research_blob():
    """المدوّنة كما تُخزَّن وتُقرَأ (dicts خام، لا كائنات AgentReport) — الشكل
    الدقيق من api._run_research_pipeline."""
    def _m(summary, findings=None, failed=False):
        return {"agent_name": "LLMMissionAgent", "summary": summary,
                "findings": findings or [], "failed": failed}
    missions = {
        "trade_flow": _m("واردات تنمو 8% (76/76 بند)", [_dp(42_000_000, note="واردات 2023")]),
        "pricing_scout": _m("أسعار رفّ 6.20–9.80€ (60/60)",
                            [_dp(7.49, "Google Maps", note="Albert Heijn")]),
        "competition": _m("HHI 940 — سوق مفتّت", [_dp(940, note="HHI")]),
        "risk_news": _m("لا مخاطر حادة", []),
    }
    analyst = {
        "report": {"agent_name": "market_analyst",
                   "summary": "هولندا WATCH — سوق مفتّت بأسعار رفّ جيدة.",
                   "findings": [], "failed": False},
        "missing_categories": [],
        "by_category": {
            "demand": [_dp(42_000_000, note="واردات تنمو 8%")],
            "price_competitiveness": [_dp(7.49, "Google Maps", note="سعر رفّ")],
        },
    }
    verdict = {"verdict": "WATCH", "confidence": 0.6,
               "ai": {"verdict": "WATCH",
                      "reasoning": "سوق واعد لكن يحتاج تحقّق المستوردين."}}
    report_out = {"report": _REPORT_TEXT, "review_cycles": 2,
                  "unresolved_notes": [], "failure_reason": ""}
    return {
        "product": "تمور", "hs_code": "080410", "year": None, "preliminary": True,
        "market": {"iso3": "NLD", "m49": 528, "iso2": "NL",
                   "name_en": "Netherlands", "name_ar": "هولندا"},
        "markets": [],
        "deep_research": {"missions": missions, "analyst": analyst,
                          "verdict": verdict, "report": report_out,
                          "trace_id": "nld-real",
                          "budget_status": {"tail_degraded": False}},
        "data_economics": {"llm_calls": 30, "note": "30 نداء كلود"},
    }


# ═══ القفل ١ — report.md يُصيَّر من deep_research لا من قالب /analyze ═══════

def test_report_md_renders_deep_research_not_analyze_template():
    import silk_render
    from silk_reports import render_markdown
    view = silk_render.build_view(_netherlands_research_blob())
    md = render_markdown(view)
    # السرد الغنيّ الحقيقي موجود.
    assert "HHI" in md and "940" in md              # المشهد التنافسي
    assert "EU 2017/625" in md                       # لوائح الوصول
    assert "6.20" in md or "7.49" in md              # أسعار الرفّ
    assert "دورة تنقيح" in md                        # المراجعة (دورتان)
    # قالب /analyze الفارغ اختفى تماماً.
    assert "with_research" not in md
    assert "0 أسواق مرشّحة" not in md
    assert "حزمة وكلاء البحث غير مفعّلة" not in md


# ═══ القفل ٢ — لا نصّ "None" حرفي في الترويسة (صدق الفجوات) ════════════════

def test_report_md_never_prints_none_literal():
    import silk_render
    from silk_reports import render_markdown, _data_year_label
    view = silk_render.build_view(_netherlands_research_blob())
    md = render_markdown(view)
    assert "None" not in md                          # لا سنة/ثقة "None"
    assert "ثقة التصنيف —" in md                     # فجوة معلنة صريحة
    # وحدةً: سنة غائبة => «—» لا "None".
    assert _data_year_label({"year": None}) == "—"
    assert _data_year_label({"year": 2023}) == "2023"


# ═══ القفل ٣ — report.docx (تقرير العميل) لا يفشل 501 على لغة الحكم ════════

def test_report_docx_client_does_not_501_on_judgment_language():
    import silk_render
    from silk_reports import render_client_docx, _client_forbidden_hits
    view = silk_render.build_view(_netherlands_research_blob())
    # كان يرفع RuntimeError→501 على «درجة الثقة» (algorithm_language).
    path = render_client_docx(view, os.path.join(tempfile.mkdtemp(), "c.docx"))
    assert os.path.exists(path)
    # والمستند نظيف فعلاً (لغة الحكم حُوّلت تجارياً لا سُرِّبت).
    from docx import Document
    doc = Document(path)
    blob = "\n".join(p.text for p in doc.paragraphs)
    for t in doc.tables:
        for row in t.rows:
            for c in row.cells:
                blob += "\n" + c.text
    assert not _client_forbidden_hits(blob), _client_forbidden_hits(blob)


# ═══ القفل ٤ — نقطة النهاية GET /report.md تقدّم السرد فعلاً ═══════════════

def test_report_md_endpoint_serves_deep_research_narrative():
    from fastapi.testclient import TestClient
    import importlib
    import api
    with _env(SILK_API_KEY="x", SILK_RATE_LIMIT="0",
              SILK_USAGE_DB=os.path.join(tempfile.mkdtemp(), "u.db")):
        importlib.reload(api)
        client = TestClient(api.create_app())
        with mock.patch("silk_storage.get_analysis",
                        return_value=_netherlands_research_blob()):
            r = client.get("/analyses/5/report.md", headers={"X-API-Key": "x"})
        assert r.status_code == 200, r.text
        body = r.text
        assert "HHI" in body and "EU 2017/625" in body
        assert "with_research" not in body and "None" not in body
