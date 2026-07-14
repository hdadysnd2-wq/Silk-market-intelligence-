"""اختبارات تصدير تقرير العميل (القالب الثاني، فصل الجمهور).

البصيرة الجوهرية (بلاغ المالك): التصدير القديم يعرض تِلِمِتري النظام لقارئ
نهائي — خطأ جمهور. تقرير العميل (render_client_docx) يجب أن يكون خالياً
تماماً من المصطلحات الممنوعة (mission/status/successful/run/call/declared
gap/tool names + لغة الخوارزمية)، وأن يرفض التصدير إن تسرّب أيّ منها.
Run:  python3 -m pytest tests/ -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import block_network, docx_all_text  # noqa: E402


def _mock_view(missing_categories=None, report_text=None):
    """نتيجة بحث عميق مموّهة → build_view. تحوي عمداً تسريبات تشغيلية في سرد
    الكاتب (اسم أداة، "بعثة"، جدول درجات) ليتأكّد أن المُطهِّر/الحارس يزيلها."""
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    from silk_market_resolver import resolve_market
    from silk_render import build_view

    ref, _ = resolve_market("Netherlands")

    def f(v, s, c, n):
        return DataPoint(v, s, c, n, "2026-07-02")

    demand = [f("واردات هولندا من تمور 38 مليون دولار (2023)", "UN Comtrade",
               0.9, "[demand] تدفق مباشر")]
    price = [f("Albert Heijn: تمور 5.50€/كغم", "Albert Heijn (رصد ويب)", 0.6,
              "[price_competitiveness] سعر مرصود")]
    by_cat = {"demand": demand, "entry_cost": [], "price_competitiveness": price,
              "entry_door": [], "swot": []}
    # التقاطعات الغائبة تُصرَّح صراحةً (لا حذف صامت).
    missing = (missing_categories if missing_categories is not None
              else [c for c, v in by_cat.items() if not v])

    default_report = (
        "## 1. الخلاصة التنفيذية\n"
        "التوصية دخول مشروط لأن الشريحة كبيرة والسوق مجزَّأ.\n"
        "**ماذا يعني هذا لقرارك:** ابدأ ملف الأهلية الآن.\n\n"
        "## 2. منهجية البحث ونطاقه\n"
        "11 من 12 بعثة أنتجت أدلة. المصدر: Comtrade عبر comtrade_imports.\n\n"
        "## 3. نظرة عامة على السوق وحجمه\n"
        "واردات 38 مليون دولار (UN Comtrade)، نمو 7%.\n"
        "**ماذا يعني هذا لقرارك:** حجم كافٍ لشحنة تجارية.\n\n"
        "## 6. المشهد التنافسي\n"
        "HHI≈2100 من comtrade_competitors.\n"
        "| الدولة | الحصة |\n| --- | --- |\n| تونس | 31% |\n\n"
        "## 9. تقييم المخاطر\n"
        "استقرار مرتفع (World Bank WGI).\n"
        "**ماذا يعني هذا لقرارك:** لا مخاطر كلية.\n\n"
        "## 10. التوصيات الاستراتيجية\n"
        "الحكم دخول مشروط. \n"
        "| العمود | القيمة |\n| --- | --- |\n| verdict | دخول مشروط |"
        "\n| confidence | 0.66 |\n\n"
        "### خارطة طريق الدخول (٩٠ يوماً)\n"
        "الباب الأول: موزّع حلال في أمستردام (○ يحتاج تحققاً).\n")

    result = {
        "product": "تمور", "hs_code": "080410", "year": 2023,
        "market": {"iso3": ref.iso3, "m49": ref.m49, "iso2": ref.iso2,
                  "name_en": ref.name_en, "name_ar": ref.name_ar},
        "markets": [],
        "deep_research": {
            "trace_id": "test-client-nld",
            "missions": {
                "trade_flow": AgentReport("LLMAgent:trade_flow", demand, False,
                                          "تدفقات مؤكَّدة"),
                "pricing_scout": AgentReport("LLMAgent:pricing_scout", price,
                                             False, "أسعار مرصودة"),
                "competitors": AgentReport("LLMAgent:competitors", [
                    f({"year": 2023, "hhi": 2100.0}, "UN Comtrade", 0.9,
                      "HHI معتدل")], False, "تركّز معتدل"),
            },
            "analyst": {
                "report": AgentReport("LLMAgent:market_analyst",
                                      demand + price, False, "تحليل مكتمل"),
                "by_category": by_cat, "missing_categories": missing},
            "verdict": {"verdict": "PRELIMINARY GO",
                       "ai": {"verdict": "دخول مشروط", "confidence": 0.66,
                             "reasoning": "دخول مشروط بتأمين الأهلية أولاً."}},
            "report": {"report": report_text or default_report,
                      "review_cycles": 2, "unresolved_notes": []},
        },
    }
    os.environ["SILK_HERMETIC"] = "1"
    view = build_view(result)
    view["test_run"] = True
    return view


def _render(view, tmp_path):
    import silk_reports as R
    out = os.path.join(str(tmp_path), "client.docx")
    return R.render_client_docx(view, out)


# ── الحارس الأساسي: صفر مصطلح ممنوع في المخرَج ────────────────────────────

def test_client_export_has_zero_forbidden_terms(tmp_path):
    import silk_reports as R
    with block_network():
        out = _render(_mock_view(), tmp_path)
    text = docx_all_text(out)
    hits = R._client_forbidden_hits(text)
    assert hits == [], f"forbidden telemetry leaked into client export: {hits}"


def test_each_forbidden_category_absent_explicitly(tmp_path):
    """تحقّق صريح من كل بند في قائمة المالك: mission/status/successful/run/
    call/declared gap/tool names + لغة الخوارزمية."""
    with block_network():
        out = _render(_mock_view(), tmp_path)
    text = docx_all_text(out)
    # عربية تشغيلية
    for term in ("بعثة", "بعثات", "ناجحة", "نجحت", "فشلت", "فجوة معلنة",
                 "تشغيلة", "المحلل الشامل", "كاتب التقرير"):
        assert term not in text, f"forbidden Arabic term present: {term}"
    # أسماء أدوات snake_case
    for tool in ("comtrade_imports", "comtrade_competitors", "web_search",
                 "worldbank_indicator", "eurostat_eu_signals",
                 "trends_interest"):
        assert tool not in text, f"tool name leaked: {tool}"
    # لغة الخوارزمية الإنجليزية (جدول الدرجات)
    for algo in ("verdict", "confidence", "score"):
        assert algo not in text.lower(), f"algorithm language leaked: {algo}"
    # المصادر البشرية المشروعة تبقى (استشهاد لا أداة)
    assert "UN Comtrade" in text  # اسم مصدر بشري — مسموح


# ── سلوك الرفض: الحارس يرمي إن تسرّب مصطلح ─────────────────────────────────

def test_guard_rejects_export_when_forbidden_term_leaks(tmp_path):
    """قلب المتطلب (بلاغ المالك النقطة ١): الحارس يرفض التصدير إن ظهر مصطلح
    ممنوع لا يلتقطه المُطهِّر. نُدرج مصطلحاً إنجليزياً تشغيلياً لا يطهّره
    المُطهِّر (mission بالإنجليزية) في سرد الكاتب."""
    import silk_reports as R
    leaky = ("## 1. الخلاصة التنفيذية\n"
             "This mission was successful.\n"
             "**ماذا يعني هذا لقرارك:** ابدأ.\n")
    view = _mock_view(report_text=leaky)
    with block_network():
        import pytest
        with pytest.raises(RuntimeError) as exc:
            _render(view, tmp_path)
    assert "مصطلحات ممنوعة" in str(exc.value)


def test_forbidden_hits_helper_detects_each_pattern():
    import silk_reports as R
    assert R._client_forbidden_hits("هذه بعثة بحث")
    assert R._client_forbidden_hits("النتيجة ناجحة")
    assert R._client_forbidden_hits("فجوة معلنة في البيانات")
    assert R._client_forbidden_hits("عبر comtrade_competitors")
    assert R._client_forbidden_hits("the mission ran")
    assert R._client_forbidden_hits("confidence 0.6")
    # نص تجاري نظيف — لا مطابقة
    assert R._client_forbidden_hits(
        "واردات هولندا 38 مليون دولار وفق UN Comtrade، نمو 7%.") == []


# ── البنية: أقسام العميل السبعة بالترتيب ─────────────────────────────────

def test_client_structure_headings_in_order(tmp_path):
    with block_network():
        out = _render(_mock_view(), tmp_path)
    text = docx_all_text(out)
    order = ["القرار وأساسه", "السوق بالأرقام", "المنافسة والتسعير والهامش",
             "مسار الدخول والمتطلبات", "المخاطر",
             "ما لم يكتمل للقرار", "المنهجية وسجل الأدلة للمدققين"]
    positions = [text.find(h) for h in order]
    for h, pos in zip(order, positions):
        assert pos >= 0, f"client section missing: {h}"
    assert positions == sorted(positions), "client sections out of order"


def test_missions_table_replaced_by_methodology_paragraph(tmp_path):
    """النقطة ٤: جدول البعثات التشغيلي يُستبدَل بفقرة منهجية (٣ أسطر) تذكر
    عدد مسارات البحث والمصادر — لا جدول حالات بعثات."""
    with block_network():
        out = _render(_mock_view(), tmp_path)
    text = docx_all_text(out)
    assert "مسار بحث" in text          # مفردة تجارية بدل «بعثة»
    assert "سجل الأدلة للمدققين" in text  # الملحق المُعاد تسميته
    # لا عمود «الحالة» التشغيلي (كان في جدول ملخّص مصادر البحث القديم)
    assert "الحالة" not in text or "ناجحة" not in text


# ── الفجوات → صياغة تجارية، لا عناوين فارغة متتالية ───────────────────────

def test_empty_intersections_become_commercial_phrasing(tmp_path):
    """النقطة ٣: كل تقاطع بلا أدلة يتحوّل لصياغة تجارية موحّدة القالب، لا
    عنوان فارغ. المموّه يترك entry_cost/entry_door/swot فارغة."""
    with block_network():
        out = _render(_mock_view(
            missing_categories=["entry_cost", "entry_door", "swot"]), tmp_path)
    text = docx_all_text(out)
    assert "لم نتمكّن من توثيق" in text
    assert "إغلاق هذه الفجوة يتطلّب" in text
    # صياغة تجارية للأبواب الغائبة تحديداً
    assert "موزّعين" in text or "جهات اتصال" in text


def test_no_missing_categories_gives_positive_line_not_empty(tmp_path):
    with block_network():
        out = _render(_mock_view(missing_categories=[]), tmp_path)
    text = docx_all_text(out)
    assert "لا فجوة جوهرية" in text
    assert "لم نتمكّن من توثيق" not in text


# ── لا اختلاق: تقرير بلا سرد كاتب يتدهور تجارياً بلا تِلِمِتري ──────────────

def test_missing_writer_report_degrades_cleanly(tmp_path):
    import silk_reports as R
    with block_network():
        out = _render(_mock_view(report_text=""), tmp_path)
    text = docx_all_text(out)
    assert R._client_forbidden_hits(text) == []       # نظيف رغم غياب السرد
    assert "التوصية:" in text                         # الحكم حاضر دوماً
    assert "المنهجية وسجل الأدلة للمدققين" in text     # الملحق حاضر


# ── نقطة النهاية: /research → تقرير العميل النظيف؛ ?internal=1 → الكامل ────

def _store_deep_research(db):
    """خزّن نتيجة بحث عميق بشكل JSON-safe (بعثات كقواميس) — كما يصل من
    التخزين فعلاً؛ build_view يطبّعها عبر _report_fields."""
    import silk_storage as storage
    dp = {"value": "واردات هولندا 38 مليون دولار (2023)", "source": "UN Comtrade",
          "confidence": 0.9, "note": "[demand] تدفق مباشر",
          "retrieved_at": "2026-07-02"}
    result = {
        "product": "تمور", "hs_code": "080410", "year": 2023,
        "market": {"iso3": "NLD", "m49": "528", "iso2": "NL",
                  "name_en": "Netherlands", "name_ar": "هولندا"},
        "markets": [],
        "deep_research": {
            "missions": {"trade_flow": {"agent_name": "LLMAgent:trade_flow",
                                        "failed": False, "summary": "ok",
                                        "findings": [dp]}},
            "analyst": {"report": {"agent_name": "LLMAgent:market_analyst",
                                  "failed": False, "summary": "تحليل",
                                  "findings": [dp]},
                       "by_category": {"demand": [dp], "entry_cost": [],
                                      "price_competitiveness": [],
                                      "entry_door": [], "swot": []},
                       "missing_categories": ["entry_cost",
                                             "price_competitiveness",
                                             "entry_door", "swot"]},
            "verdict": {"verdict": "PRELIMINARY GO",
                       "ai": {"verdict": "دخول مشروط", "confidence": 0.6,
                             "reasoning": "دخول مشروط بالأهلية."}},
            "report": {"report": "## 1. الخلاصة التنفيذية\nنص تجريبي نظيف.\n",
                      "review_cycles": 1, "unresolved_notes": []},
        },
    }
    return storage.save_analysis(result, db)


def test_conditional_go_badge_agrees_with_body_label(tmp_path):
    """بلاغ مراجعة المالك (تناقض الحكم صفحة ١): شارة الغلاف كانت «مراقبة
    السوق» بينما المتن «دخول مشروط». الآن CONDITIONAL-GO له tone وتسمية
    مستقلّان، فتتّفق الشارة مع المتن."""
    from silk_render import _VERDICT_LABELS_AR, _verdict_tone
    assert _verdict_tone("CONDITIONAL-GO") == "conditional"
    assert _VERDICT_LABELS_AR["conditional"] == "دخول مشروط"
    view = _mock_view()
    view["deep_research"]["verdict"]["ai"]["verdict"] = "CONDITIONAL-GO"
    view["deep_research"]["verdict"]["verdict"] = "CONDITIONAL-GO"
    with block_network():
        out = _render(view, tmp_path)
    text = docx_all_text(out)
    assert "دخول مشروط" in text          # المتن + الشارة متطابقان
    assert "مراقبة السوق" not in text     # لا تسمية watch مخالفة


def test_committed_client_sample_is_clean_and_structured():
    """قاعدة ١٠.٦: نموذج تقرير العميل محفوظ بالمستودع، ويجب أن يظل خالياً
    من أيّ مصطلح ممنوع وكامل البنية (يُعاد توليده عبر
    tools/gen_client_report_sample.py مع كل تعديل على طبقة العرض)."""
    import silk_reports as R
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "samples", "client_report_latest.docx")
    assert os.path.exists(path), "شغّل tools/gen_client_report_sample.py"
    text = docx_all_text(path)
    assert R._client_forbidden_hits(text) == [], "النموذج المحفوظ يحوي تِلِمِتري"
    for h in ("القرار وأساسه", "السوق بالأرقام", "المنافسة والتسعير والهامش",
              "مسار الدخول والمتطلبات", "المخاطر", "ما لم يكتمل للقرار",
              "سجل الأدلة للمدققين"):
        assert h in text, f"قسم مفقود من النموذج المحفوظ: {h}"


def test_research_docx_endpoint_serves_clean_client_report(tmp_path):
    import pytest
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import api
    import silk_storage as storage
    import silk_reports as R

    db = os.path.join(str(tmp_path), "research.db")
    os.environ["SILK_HERMETIC"] = "1"
    aid = _store_deep_research(db)
    saved = storage._DEFAULT_PATH
    storage._DEFAULT_PATH = db
    try:
        client = TestClient(api.create_app())
        with patch("requests.sessions.Session.request",
                   side_effect=OSError("network disabled for offline test")):
            # الافتراضي: تقرير العميل النظيف
            r = client.get(f"/analyses/{aid}/report.docx")
            assert r.status_code in (200, 501)
            if r.status_code == 501:
                return  # لا python-docx في هذه البيئة
            assert "client_report" in r.headers.get("content-disposition", "")
            path = os.path.join(str(tmp_path), "got_client.docx")
            with open(path, "wb") as fh:
                fh.write(r.content)
            text = docx_all_text(path)
            assert R._client_forbidden_hits(text) == []
            assert "المنهجية وسجل الأدلة للمدققين" in text
            assert "قسم البحث العميق" not in text  # لا عنوان تشغيلي

            # ?internal=1: التصدير التشغيلي الكامل (للمدقّق) — يحوي التِلِمِتري
            r2 = client.get(f"/analyses/{aid}/report.docx?internal=1")
            assert r2.status_code == 200
            path2 = os.path.join(str(tmp_path), "got_internal.docx")
            with open(path2, "wb") as fh:
                fh.write(r2.content)
            text2 = docx_all_text(path2)
            assert "قسم البحث العميق" in text2  # التصدير الكامل يحتفظ به
    finally:
        storage._DEFAULT_PATH = saved
