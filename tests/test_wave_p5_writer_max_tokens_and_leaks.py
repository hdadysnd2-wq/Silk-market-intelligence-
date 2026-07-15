"""بلاغ حي إنتاجي (تمور/هولندا HS080410) — إصلاح ثلاث قضايا بدليل مُلتقَط:

القضية ١ — فشل الكاتب بـstop_reason="max_tokens" (سلسلة PRs #69/#70/#71):
  رد HTTP 200 بلا كتل نصية كان يعيد None فيصير report=None. الآن يصعّد
  مزوّد كلود سقف الإخراج ويعيد المحاولة، ويعيد أوفى نص — max_tokens لا
  يسبّب report=None بعد اليوم (silk_llm_provider.complete).

القضية ٢ — تسريب JSON خام للواجهة: أشكال (سياج ```json، JSON مضمَّن،
  لاحقة "| tool calls: N") فاتت المُطهِّر المُرسَّى القديم. الآن تُطهَّر
  (silk_render._strip_raw_json_leak) وحارس الجودة يلتقط مفاتيح JSON العربية.

القضية ٣ — تصدير docx حين report=None: يُصدَّر مستند بالحكم + الأدلة +
  الفجوات + ملاحظة متدهورة صريحة بدل فشل صامت (silk_reports.render_client_docx).

هيرمتي بالكامل — لا شبكة، لا مفتاح حقيقي. Run:
  python3 -m pytest tests/test_wave_p5_writer_max_tokens_and_leaks.py -q
"""
from __future__ import annotations

import contextlib
import os
import sys
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


def _resp(payload: dict):
    class _R:
        def raise_for_status(self):
            return None

        def json(self):
            return payload
    return _R()


# ═══ القضية ١ — استرداد الكاتب من نفاد رموز الإخراج ═══════════════════════

def test_max_tokens_with_no_text_blocks_recovers_via_ceiling_escalation():
    """المسار الإنتاجي بالضبط: أول رد stop_reason='max_tokens' وبلا أي كتلة
    نصية (كان يعيد None → report=None). يجب أن يرفع المزوّد السقف ويعيد
    المحاولة، فيسترد نصاً حقيقياً — لا None."""
    import silk_llm_provider as lp
    maxes: list[int] = []

    def fake_post(url, **kw):
        maxes.append(kw["json"]["max_tokens"])
        if len(maxes) == 1:  # أول محاولة: نفاد السقف بلا نص إطلاقاً
            return _resp({"stop_reason": "max_tokens", "content": [],
                          "usage": {"input_tokens": 10, "output_tokens": 10}})
        return _resp({"stop_reason": "end_turn",  # بعد رفع السقف: نص كامل
                      "content": [{"type": "text", "text": "التقرير الكامل."}],
                      "usage": {"input_tokens": 10, "output_tokens": 40}})

    with _env(ANTHROPIC_API_KEY="k"), \
         mock.patch("requests.post", side_effect=fake_post):
        out = lp.AnthropicProvider().complete("sys", "user", 8000,
                                              "claude-opus-4-8", 5)
    assert out == "التقرير الكامل."          # استُرِدّ، لا None
    assert lp.last_error() is None            # نجاح نظيف
    assert len(maxes) == 2 and maxes[1] > maxes[0]   # صُعِّد السقف فعلاً


def test_max_tokens_with_partial_text_returns_best_partial_never_none():
    """نفاد السقف مع نص جزئي حتى بعد التصعيد → يُعاد الجزئي (تقرير مقتطع
    مفيد أفضل من report=None) — لا None، لا اختلاق."""
    import silk_llm_provider as lp

    def fake_post(url, **kw):
        return _resp({"stop_reason": "max_tokens",
                      "content": [{"type": "text", "text": "جزء من التقرير"}],
                      "usage": {"input_tokens": 10, "output_tokens": 30}})

    with _env(ANTHROPIC_API_KEY="k"), \
         mock.patch("requests.post", side_effect=fake_post):
        out = lp.AnthropicProvider().complete("s", "u", 8000, "m", 5)
    assert out == "جزء من التقرير"
    assert lp.last_error() is None


def test_max_tokens_zero_text_forever_declares_gap_not_fabrication():
    """الحالة المرضية القصوى: نفاد السقف بلا أي نص أبداً حتى السقف الصلب →
    يُعلَن فجوة صريحة (empty_response + None)، لا يُختلَق نص. المبدأ المؤسِّس."""
    import silk_llm_provider as lp

    def fake_post(url, **kw):
        return _resp({"stop_reason": "max_tokens", "content": [],
                      "usage": {"input_tokens": 10, "output_tokens": 5}})

    with _env(ANTHROPIC_API_KEY="k"), \
         mock.patch("requests.post", side_effect=fake_post):
        out = lp.AnthropicProvider().complete("s", "u", 8000, "m", 5)
    assert out is None                         # لا اختلاق
    err = lp.last_error()
    assert err and err["type"] == "empty_response"
    assert "max_tokens" in err["message"]


def test_normal_response_makes_exactly_one_call_no_escalation():
    """رد طبيعي (stop_reason='end_turn') لا يُصعِّد ولا يعيد المحاولة —
    مسارات النجاح العادية غير متأثّرة بالإصلاح (نداء واحد فقط)."""
    import silk_llm_provider as lp
    n = {"c": 0}

    def fake_post(url, **kw):
        n["c"] += 1
        return _resp({"stop_reason": "end_turn",
                      "content": [{"type": "text", "text": "رد."}],
                      "usage": {"input_tokens": 5, "output_tokens": 5}})

    with _env(ANTHROPIC_API_KEY="k"), \
         mock.patch("requests.post", side_effect=fake_post):
        out = lp.AnthropicProvider().complete("s", "u", 900, "m", 5)
    assert out == "رد." and n["c"] == 1


def test_deep_report_recovers_end_to_end_from_writer_max_tokens():
    """المسار الكامل: الكاتب (deep_report → _call → complete) يواجه
    max_tokens-بلا-نص ثم يسترد، فيعيد نصّ تقرير لا None."""
    import silk_ai_judge as aj
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    posts = {"n": 0}

    def fake_post(url, **kw):
        posts["n"] += 1
        if posts["n"] == 1:  # المحاولة الأولى للكاتب: نفاد السقف بلا نص
            return _resp({"stop_reason": "max_tokens", "content": [],
                          "usage": {"input_tokens": 20, "output_tokens": 20}})
        return _resp({"stop_reason": "end_turn",
                      "content": [{"type": "text",
                                   "text": "## 1. الخلاصة\nتقرير مسترَدّ."}],
                      "usage": {"input_tokens": 20, "output_tokens": 60}})

    reports = {"trade_flow": AgentReport(
        "LLMAgent:trade_flow",
        [DataPoint("واردات هولندا 33 مليون دولار", "UN Comtrade", 0.9, "note")],
        False, "ok")}
    with _env(ANTHROPIC_API_KEY="k", SILK_API_KEY="x"), \
         mock.patch("requests.post", side_effect=fake_post):
        out = aj.deep_report(reports, "مسوّدة المحلل", {"verdict": "WATCH"},
                             "تمور", "هولندا")
    assert out and "تقرير مسترَدّ" in out       # لا None بسبب max_tokens


# ═══ القضية ٢ — تسريب JSON خام للواجهة (سلاسل إنتاجية حرفية) ══════════════

# السلاسل بالضبط كما ظهرت في الإنتاج (بلاغ المالك، القضية ٢).
_LEAK_VERDICT_EMBEDDED = (
    'التوصية: {"verdict":"مراقبة السوق","confidence":0.55,'
    '"reasoning":"مبني على الحقائق والخيوط."}')
_LEAK_VERDICT_ARABIC_KEYS = (
    '{"الحكم":"مراقبة السوق","درجة الثقة":0.55,'
    '"reasoning":"مبني على الحقائق."}')
_LEAK_FENCED_FINDINGS = (
    'json { "findings": [ { "claim": "ادّعاء", '
    '"datapoint_ids": ["",""] } ] } | tool calls: 2')
_LEAK_UNPARSEABLE_SUFFIX = "رد كلود غير قابل للتفسير كـ JSON | tool calls: 2"


def _assert_no_raw_plumbing(out: str):
    assert "{" not in out and "}" not in out, out
    assert '"findings"' not in out and '"datapoint_ids"' not in out, out
    assert '"verdict"' not in out and '"confidence"' not in out, out
    assert '"الحكم"' not in out and '"درجة الثقة"' not in out, out
    assert "tool calls" not in out and "نداءات أدوات" not in out, out


def test_embedded_verdict_json_is_neutralized_to_reasoning():
    from silk_render import _strip_internal_plumbing
    out = _strip_internal_plumbing(_LEAK_VERDICT_EMBEDDED)
    _assert_no_raw_plumbing(out)
    assert "مبني على الحقائق والخيوط" in out   # استُخرج التعليل المقروء


def test_arabic_keyed_verdict_json_is_neutralized():
    from silk_render import _strip_internal_plumbing
    out = _strip_internal_plumbing(_LEAK_VERDICT_ARABIC_KEYS)
    _assert_no_raw_plumbing(out)
    assert "مبني على الحقائق" in out


def test_fenced_findings_json_with_tool_calls_suffix_becomes_declared_gap():
    from silk_render import _strip_internal_plumbing
    out = _strip_internal_plumbing(_LEAK_FENCED_FINDINGS)
    _assert_no_raw_plumbing(out)
    assert "json" not in out.lower()
    assert "تعذّر تفسير" in out                 # فجوة معلنة بدل JSON خام


def test_unparseable_gap_line_keeps_message_but_drops_tool_calls_suffix():
    from silk_render import _strip_internal_plumbing
    out = _strip_internal_plumbing(_LEAK_UNPARSEABLE_SUFFIX)
    assert "tool calls" not in out and "|" not in out
    assert "غير قابل للتفسير" in out            # جملة الفجوة تبقى، بلا سباكة


def test_quality_gate_flags_arabic_keyed_raw_json():
    """حارس الانحدار: مفتاح JSON عربي مسرَّب كان يفلت من [a-zA-Z_]+ —
    الآن يلتقطه _RAW_JSON_RE الموسَّع."""
    from silk_quality_gate import _check_markdown_and_raw_json
    findings = _check_markdown_and_raw_json(_LEAK_VERDICT_ARABIC_KEYS)
    assert any(f["check"] == "raw_json" for f in findings)


# ═══ القضية ٣ — تصدير docx متدهور حين report=None ════════════════════════

def _research_view_report_none():
    import silk_render
    result = {
        "product": "تمور", "hs_code": "080410",
        "market": {"name_ar": "هولندا", "name_en": "Netherlands", "iso3": "NLD"},
        "header": {"product": "تمور", "hs_code": "080410",
                   "target_market": "هولندا", "date": "2026-07-15"},
        "deep_research": {
            "verdict": {"verdict": "WATCH", "confidence": 0.55,
                        "ai": {"verdict": "WATCH", "reasoning": "مبني على الحقائق."}},
            "report": {"report": None, "unresolved_notes": [],
                       "failure_reason": "فشل نداء كلود (empty_response: "
                                         "HTTP 200 بلا كتل نصية — "
                                         "stop_reason='max_tokens')"},
            "analyst": {"summary": "x", "missing_categories": ["price_competitiveness"],
                        "by_category": {}},
            "missions": {}, "limits": [], "trace_id": "t"},
    }
    return silk_render.build_view(result)


def test_client_docx_with_report_none_exports_degraded_not_failure():
    pytest.importorskip("docx")
    import tempfile
    import silk_reports
    from conftest import docx_all_text
    with _env(SILK_HERMETIC="1"):
        view = _research_view_report_none()
        path = silk_reports.render_client_docx(
            view, os.path.join(tempfile.mkdtemp(), "r.docx"))
    txt = docx_all_text(path)
    assert "مراقبة السوق" in txt                # الحكم حاضر
    assert "لأسباب تقنية مؤقتة" in txt          # ملاحظة التدهور الصريحة
    assert "إعادة توليد" in txt                 # طريق الخروج معلن
    # لا يتسرّب تفصيل تشغيلي خام للعميل (حارس _client_assert_clean لم يُكسَر).
    assert "max_tokens" not in txt and "stop_reason" not in txt


def test_operator_docx_with_report_none_surfaces_failure_reason():
    pytest.importorskip("docx")
    import tempfile
    import silk_reports
    from conftest import docx_all_text
    with _env(SILK_HERMETIC="1"):
        view = _research_view_report_none()
        path = silk_reports.render_docx(
            view, os.path.join(tempfile.mkdtemp(), "op.docx"))
    txt = docx_all_text(path)
    # التصدير التشغيلي (للمدقّق) يُظهر سبب الفشل عبر «حدود هذا التقرير».
    assert "التقرير الكامل غائب" in txt
