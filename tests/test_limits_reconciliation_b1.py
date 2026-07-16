"""PART B1 (أمر العمل الرئيس) — «حدود هذا البحث» كانت تناقض المتن: تعلن أن
حصص المورّدين غير متاحة بينما التقرير مبنيّ على 3.39%/55.28%/HHI. السبب
البنيوي: البعثات تُعلن فجواتها معزولةً وقت تشغيلها المتوازي، ولا شيء
يصالحها مع الحقائق النهائية قبل العرض. كذلك «…» وسط الجملة في سطر الحدّ.

اللقفل (LESSONS البند ١٢ — «التجميع يثق بالملاحظات الخام فوق الحقائق
المصالَحة»): سطر حدٍّ مشتقٍّ من بعثة يُعاد وسمه «حُسمت لاحقاً» فقط إذا وُجد
له دليل رقمي فعلي (نفس الموضوع + رقم في بند واحد)؛ وإلا يبقى حرفياً (عقد
عدم الاختلاق — لا إخفاء فجوة حقيقية). كلا الاتجاهين مقفولان.

Run: python3 -m pytest tests/test_limits_reconciliation_b1.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_resolved_supplier_share_gap_is_retagged_not_contradiction():
    """فجوة «حصص الموردين غير متاحة» + بند حقيقة يحمل حصة رقمية => تُعاد
    وسماً «حُسمت لاحقاً»، لا تبقى تناقضاً صريحاً في الحدود."""
    import silk_render as R
    facts = ["الصين: حصة 55.28% من واردات السوق (UN Comtrade 2023)",
             "مؤشر تركّز المورّدين HHI=2350"]
    out = R._reconcile_mission_limits(
        ["المنافسون: حصص الموردين غير متاحة"], facts)
    assert out[0].startswith("حُسمت لاحقاً")
    assert "حصص الموردين غير متاحة" in out[0]  # النص الأصلي محفوظ للشفافية


def test_genuinely_unresolved_gap_stays_verbatim():
    """فجوة بلا أيّ دليل رقمي مطابق الموضوع => تبقى حرفياً (لا اختلاق حسم)."""
    import silk_render as R
    facts = ["عدد السكان 17 مليون نسمة (World Bank 2023)"]  # لا علاقة بالحصص
    out = R._reconcile_mission_limits(
        ["المنافسون: حصص الموردين غير متاحة"], facts)
    assert out == ["المنافسون: حصص الموردين غير متاحة"]


def test_topic_keyword_without_number_does_not_resolve():
    """بند يذكر الموضوع بلا رقم => لا يحسم (تحفّظ صارم ضد إخفاء فجوة)."""
    import silk_render as R
    facts = ["حصص الموردين قيد الدراسة ولم تُرصد بعد"]  # كلمة موضوع، صفر رقم
    out = R._reconcile_mission_limits(
        ["المنافسون: حصص الموردين غير متاحة"], facts)
    assert out == ["المنافسون: حصص الموردين غير متاحة"]


def test_number_in_unrelated_topic_does_not_false_resolve():
    """رقم في بند موضوعه مختلف (سعر) لا يحسم فجوة الحصص — الاشتراط أن
    يجتمع الموضوع والرقم في نفس البند."""
    import silk_render as R
    facts = ["سعر التجزئة للمنافس 9.96 يورو/كجم"]
    out = R._reconcile_mission_limits(
        ["المنافسون: حصص الموردين غير متاحة"], facts)
    assert out == ["المنافسون: حصص الموردين غير متاحة"]  # لا حسم كاذب


def test_price_gap_resolved_by_priced_finding():
    import silk_render as R
    facts = ["Albert Heijn: تمر مجدول 9.96 €/كجم (رصد مباشر)"]
    out = R._reconcile_mission_limits(["الأسعار: تسعير المنافسين غير مرصود"],
                                      facts)
    assert out[0].startswith("حُسمت لاحقاً")


def test_first_clause_prevents_midsentence_ellipsis():
    """سطر البعثة الفاشلة يحمل الجملة الأولى فقط لا الملخّص الطويل — فلا
    تعيد طبقة docx (٣٠٠) قصّه منتصفَ جملة بـ«…»."""
    import silk_render as R
    long_summary = ("تعذّر جمع بيانات كافية لهذه البعثة. " + "تفصيل إضافي طويل "
                    * 40)
    clause = R._first_clause(long_summary)
    assert clause == "تعذّر جمع بيانات كافية لهذه البعثة."
    assert "…" not in clause and len(clause) < 300


def test_first_clause_word_safe_when_no_punctuation():
    import silk_render as R
    s = "كلمة " * 100  # بلا علامة وقف
    out = R._first_clause(s)
    assert "…" not in out and len(out) <= 200 and not out.endswith("كلم")


def test_final_fact_texts_pulls_from_missions_and_by_category():
    import silk_render as R
    missions = {"competitors": {"findings": [
        {"value": "الصين 55.28%", "note": "حصة السوق"}]}}
    by_cat = {"price_competitiveness": [
        {"value": "9.96 يورو/كجم", "note": "سعر مرصود"}]}
    texts = R._final_fact_texts(missions, by_cat)
    assert any("55.28%" in t for t in texts)
    assert any("9.96" in t for t in texts)


def test_reconciliation_wired_into_deep_research_view_end_to_end():
    """تكامل: نتيجة بحث فيها بعثة منافسين تحمل حصصاً + بعثة فاشلة تعلن فجوة
    حصص => الحدّ يظهر «حُسمت لاحقاً» لا تناقضاً. من build_view الكامل."""
    from silk_render import build_view
    from silk_agents import AgentReport
    from silk_data_layer import DataPoint
    comp = AgentReport(
        "LLMAgent:competitors",
        [DataPoint("الصين 55.28%", "UN Comtrade", 0.9, "حصة المورّد من الواردات")],
        False, "حصص المورّدين مرصودة")
    failed = AgentReport(
        "LLMAgent:trade_flow", [], True,
        "تعذّر: حصص الموردين غير متاحة لهذه البعثة")
    result = {
        "product": "تمور", "hs_code": "080410", "markets": [],
        "deep_research": {
            "missions": {"competitors": comp, "trade_flow": failed},
            "analyst": {"report": comp, "by_category": {}, "missing_categories": []},
            "verdict": {"verdict": "WATCH", "ai": {"verdict": "WATCH"}},
            "report": {"report": "## 1. الخلاصة\nنص.", "review_cycles": 1,
                      "unresolved_notes": []},
        },
    }
    limits = build_view(result)["deep_research"]["limits"]
    joined = "\n".join(limits)
    # فجوة الحصص المشتقّة من البعثة الفاشلة أُعيد وسمها، لا تناقض صريح.
    resolved = [l for l in limits if l.startswith("حُسمت لاحقاً")]
    assert resolved, f"لم يُصالَح حدّ الحصص رغم رصدها 55.28%: {limits}"
    assert "حصص الموردين غير متاحة" in joined  # النص الأصلي محفوظ شفافياً
