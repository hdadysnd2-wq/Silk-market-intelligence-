"""تسريب السباكة الداخلية للتقارير (بلاغ مالك، الجولة الثالثة) — يقفل:

المسح المرجعي لعينات `samples/` أظهر أربع فئات سباكة داخلية تصل نص العميل:
1) مفاتيح بعثات snake_case خام ("pricing_scout"، "risk_news") في جدول ملخّص
   البعثات والملحق التقني بدل الاسم التجاري العربي؛
2) حقول داخلية إنجليزية من جدول الكاتب ("verdict"، "confidence 0.64")
   تُحوَّل حرفياً لجدول Word في متن التقرير؛
3) سطر «لماذا» لمحرك القرار الموزون §8 برطانة كود إنجليزية ("score 0.636")
   وكسر ثقة عشري خام ("الثقة 0.31 دون 0.6")؛
4) اسم مسار API داخلي ("/deepen") واسم متغيّر البيئة (SILK_HERMETIC) في
   ملاحظات ولافتات معروضة للعميل.

الإصلاح في طبقة العرض مرة واحدة (label عربي في النموذج القانوني +
تعريب الحقول في _strip_internal_plumbing) وفي مصدر سطر القرار
(silk_decision)، مع حارسي انحدار جديدين في بوابة الجودة.

Run: python3 -m pytest tests/test_report_plumbing_leaks.py -q
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402


# ── 1) تعريب الحقول الداخلية الإنجليزية في النص المعروض ──────────────────

def test_strip_internal_plumbing_humanizes_english_fields():
    from silk_render import _strip_internal_plumbing
    raw = "| verdict | WATCH→GO مشروط |\n| confidence | 0.64 |"
    out = _strip_internal_plumbing(raw)
    assert "verdict" not in out and "confidence" not in out
    assert "الحكم" in out and "درجة الثقة" in out
    assert "0.64" not in out                      # الكسر الخام صيغ بشرياً
    assert "متوسطة (64%)" in out                  # confidence_phrase


def test_strip_internal_plumbing_leaves_arabic_prose_untouched():
    from silk_render import _strip_internal_plumbing
    prose = "الطلب موسمي حول رمضان وينمو بثبات — تحليل مبني على أدلة مرصودة."
    assert _strip_internal_plumbing(prose) == prose


def test_strip_internal_plumbing_translates_bare_verdict_token_in_prose():
    # سدّ تسريب لاحق: الكاتب أحياناً يكتب رمز الحكم الخام داخل نثر حرّ
    # ("الحكم النهائي WATCH — ...") بدل حقل مُهيكَل — لا مصدر عرض آخر
    # يلتقط هذا الشكل، فالالتقاط النصّي المباشر هنا هو خط الدفاع الوحيد.
    from silk_render import _strip_internal_plumbing
    prose = "الحكم النهائي WATCH — الطلب موسمي حول رمضان بثقة عالية."
    out = _strip_internal_plumbing(prose)
    assert "مراقبة السوق" in out
    assert "WATCH" not in out


# ── 2) الاسم العربي للبعثة في النموذج القانوني وكل المشتقات ──────────────

def _mock_research_result():
    return {
        "product": "تمور", "hs_code": "080410", "markets": [],
        "deep_research": {
            "market": {"iso3": "ESP", "name_ar": "إسبانيا"},
            "missions": {
                "pricing_scout": {"agent_name": "LLMAgent:pricing_scout",
                                  "failed": False,
                                  "findings": [{"value": "سعر مرصود 5.8€",
                                                "source": "Mercadona",
                                                "confidence": 0.6,
                                                "note": "",
                                                "retrieved_at": "2026-07-01"}],
                                  "summary": "سلّم أسعار مرصود"},
            },
            "analyst": {"report": {"summary": ""}, "by_category": {},
                        "missing_categories": []},
            "verdict": {"verdict": "PRELIMINARY GO"},
            "report": {"report": "## ملخص\nنص التقرير.", "review_cycles": 1,
                       "unresolved_notes": []},
            "trace_id": "t-1",
        },
    }


def test_mission_label_is_arabic_in_view_and_falls_back_on_unknown_key():
    from silk_missions import MISSIONS
    from silk_render import _mission_label, build_view
    view = build_view(_mock_research_result())
    m = view["deep_research"]["missions"]["pricing_scout"]
    assert m["label"] == MISSIONS["pricing_scout"]["name"]   # عربي تجاري
    assert "_" not in m["label"]
    assert _mission_label("no_such_mission") == "no such mission"


def test_next_step_and_supplier_note_carry_no_internal_endpoint_or_raw_conf():
    from silk_render import _supplier_directory, build_view
    view = build_view(_mock_research_result())
    nxt = view["deep_research"]["next_step"] or ""
    assert "/deepen" not in nxt and "خدمة التعميق المدفوعة" in nxt
    note = _supplier_directory(None)["note"]
    assert "/deepen" not in note
    assert not re.search(r"ثقة\s*0\.\d", note)     # لا كسر ثقة خام
    assert "○ غير متحقق" in note                   # الشارة الثلاثية بدله


def test_research_docx_shows_arabic_mission_name_not_snake_key():
    pytest.importorskip("docx")
    import tempfile

    from silk_missions import MISSIONS
    from silk_render import build_view
    from silk_reports import render_docx
    old = os.environ.get("SILK_HERMETIC")
    os.environ["SILK_HERMETIC"] = "1"      # قبل build_view — لافتة test_run
    try:
        view = build_view(_mock_research_result())
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "r.docx")
            render_docx(view, path)
            from conftest import docx_all_text
            joined = docx_all_text(path)
    finally:
        if old is None:
            os.environ.pop("SILK_HERMETIC", None)
        else:
            os.environ["SILK_HERMETIC"] = old
    assert "pricing_scout" not in joined
    assert MISSIONS["pricing_scout"]["name"] in joined
    # لافتة TEST RUN تبقى ظاهرة لكن بلا اسم متغيّر البيئة الداخلي
    assert "TEST RUN" in joined and "SILK_HERMETIC" not in joined


# ── 3) سطر «لماذا» للقرار الموزون — عربية بشرية بلا رطانة كود ─────────────

def test_decision_why_lines_are_human_arabic_not_code_speak():
    import copy

    import silk_decision as D
    from test_stage4_decision import BUNDLE
    d_go = D.decide(BUNDLE)
    assert d_go["verdict"] == "GO"
    assert "score" not in d_go["why"]              # لا رطانة إنجليزية
    assert "الدرجة الموزونة" in d_go["why"]
    assert "عالية (85%)" in d_go["why"]            # confidence_phrase

    low_conf = copy.deepcopy(BUNDLE)
    low_conf["coverage"] = 0.5                     # ثقة 0.5 دون الحد 0.6
    d_cond = D.decide(low_conf)
    assert d_cond["verdict"] == "CONDITIONAL-GO"
    assert "score" not in d_cond["why"]
    # لا كسر ثقة عشري خام على وجه التقرير («الثقة 0.5 دون 0.6» القديمة)
    assert not re.search(r"الثقة\s*0\.\d", d_cond["why"])
    assert "الحد الأدنى (60%)" in d_cond["why"]


def test_limits_lines_humanize_known_english_guard_notes():
    """سطر حدّ يحمل ملاحظة الحارس المدفوع الإنجليزية واسم متغيّر مفتاح —
    يُعرَّب في النموذج القانوني؛ ملاحظة الوكيل نفسها (عقد مختبَر في طبقة
    البيانات) لا تُمسّ."""
    from silk_render import _humanize_gap_note, build_view
    raw = ("retail_prices: LocalPriceAgent: paid agent outside /deepen — "
           "skipped (structural guard, no call attempted)؛ ولا نتائج "
           "مرصودة (requires SEARCH_API_KEY (or SERPER_API_KEY))")
    out = _humanize_gap_note(raw)
    assert "/deepen" not in out and "SEARCH_API_KEY" not in out
    assert "خدمة التعميق المدفوعة" in out
    assert "مفتاح خدمة البحث (Serper)" in out
    view = build_view({"markets": [{"country": "الصين", "iso3": "CHN",
                                    "total_score": 0.5, "confidence": 0.5,
                                    "components": {},
                                    "quality_flags": [raw]}],
                       "classified": True, "product": "تمور"})
    assert all("/deepen" not in x and "SEARCH_API_KEY" not in x
               for x in view["limits"])


# ── 4) لافتة TEST RUN في ماركداون بلا اسم متغيّر البيئة ──────────────────

def test_markdown_banner_lacks_env_var_name():
    from silk_render import build_view
    from silk_reports import render_markdown
    old = os.environ.get("SILK_HERMETIC")
    os.environ["SILK_HERMETIC"] = "1"
    try:
        view = build_view({"markets": [], "product": "تمور"})
        md = render_markdown(view)
    finally:
        if old is None:
            os.environ.pop("SILK_HERMETIC", None)
        else:
            os.environ["SILK_HERMETIC"] = old
    assert "TEST RUN" in md.splitlines()[0]
    assert "SILK_HERMETIC" not in md


# ── 5) حارسا الانحدار الجديدان في بوابة الجودة ────────────────────────────

def _gate_view(report_text: str) -> dict:
    return {"deep_research": {"report": {"text": report_text},
                              "missions": {}, "analyst": {}}}


def test_quality_gate_flags_english_fields_and_mission_keys():
    from silk_quality_gate import run_quality_gate
    out = run_quality_gate(_gate_view("verdict: WATCH — confidence 0.6"))
    checks = {f["check"] for f in out["findings"]}
    assert "english_field_leak" in checks

    out2 = run_quality_gate(_gate_view("نتائج pricing_scout تشير للنمو"))
    checks2 = {f["check"] for f in out2["findings"]}
    assert "mission_key_leak" in checks2


def test_quality_gate_silent_on_clean_arabic_report():
    from silk_quality_gate import run_quality_gate
    out = run_quality_gate(_gate_view(
        "الحكم WATCH — درجة الثقة متوسطة (64%). وكيل استكشاف الأسعار رصد "
        "سلّماً سعرياً ثلاثي الطبقات."))
    checks = {f["check"] for f in out["findings"]}
    assert "english_field_leak" not in checks
    assert "mission_key_leak" not in checks
