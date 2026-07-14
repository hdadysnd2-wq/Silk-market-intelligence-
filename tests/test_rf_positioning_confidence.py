"""اختبارات PR-F (توصياتي): S2 موقع سعر المصدّر ضمن أسعار المنافسين (سطر
كاتب)، وS3 مؤشّر ثقة الدراسة (عدّ شارات ✓/◐/○ في تقرير العميل).

كلاهما يمرّ عبر build_view → render_client_docx وحارس المصطلحات المحظورة.
Run:  python3 -m pytest tests/test_rf_positioning_confidence.py -q
"""
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import docx_all_text  # noqa: E402


# ── S3: مؤشّر ثقة الدراسة ──────────────────────────────────────────────────

def test_confidence_section_tallies_badges_correctly():
    """✓≥0.8 / ◐≥0.5 / ○<0.5 — البعثة الفاشلة تُتخطّى، والمحلل يُحتسب."""
    from docx import Document
    import silk_reports as R
    dr = {
        "missions": {
            "m1": {"failed": False, "findings": [
                {"confidence": 0.9}, {"confidence": 0.6}, {"confidence": 0.2}]},
            "m2": {"failed": True, "findings": [{"confidence": 0.95}]}},
        "analyst": {"by_category": {"demand": [{"confidence": 0.95}]}},
    }
    doc = Document()
    R._client_confidence_section(doc, dr)
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "مؤشّر ثقة الدراسة" in text
    assert "إجمالي 4 مؤشراً" in text        # 3 من m1 + 1 محلل (m2 فاشلة مُتخطّاة)
    assert "2 موثّق" in text                 # 0.9 + 0.95
    # الجدول يحمل العدّات الثلاث
    tbl = doc.tables[0]
    cells = [c.text for row in tbl.rows for c in row.cells]
    assert "✓ موثّق (مصدر رسمي)" in cells


def test_confidence_section_absent_when_no_findings():
    from docx import Document
    import silk_reports as R
    doc = Document()
    R._client_confidence_section(doc, {"missions": {}, "analyst": {}})
    assert all("ثقة الدراسة" not in p.text for p in doc.paragraphs)


# ── S2: سطر عقد برومبت الكاتب ─────────────────────────────────────────────

def test_writer_prompt_requires_price_positioning_line():
    import silk_ai_judge as J
    src = inspect.getsource(J.deep_report)
    assert "موقع سعرك ضمن أسعار المنافسين" in src
    assert "مئين" in src                     # تموضع مئيني إن أمكن


# ── العيّنة المحفوظة تُظهر الاثنين وتبقى نظيفة ─────────────────────────────

def test_committed_sample_shows_positioning_and_confidence_index():
    import silk_reports as R
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    text = docx_all_text(os.path.join(root, "samples", "client_report_latest.docx"))
    assert "مؤشّر ثقة الدراسة" in text                    # S3
    assert "موثّق (مصدر رسمي)" in text
    # S2: التموضع السعري مقروء من داخل قسم المنافسة (صياغة الكاتب التوضيحية)
    assert "الموقع السعري" in text
    assert "ضمن أسعار المنافسين المرصودة" in text
    assert R._client_forbidden_hits(text) == []          # يبقى خالياً من التِلِمِتري
