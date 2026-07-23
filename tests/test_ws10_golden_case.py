"""WS10 — الحالة الذهبية القياسية (قطر × HS 200811) + البوّابة البنيوية.

يُغلق الفجوة النظامية: كان `evals/golden_cases.json` فارغاً فلا يُقاس أيّ تغيير
برومبت. هذه الاختبارات هرمتية بالكامل (صفر مفتاح، صفر اعتماد) وتُشغَّل في CI:
تحميل/تحقّق الحالة، والبوّابة البنيوية (أقسام/نظافة متن/سلامة مراجع/سقف فجوات)
على نتيجةٍ نظيفة (تنجح) وأخرى ملوّثة (تُمسَك)، وتخطّي `main` بسببٍ معلن بلا مفتاح.

الجزء الحيّ (بعثات+محلل+كاتب+حَكَم كلود) لا يُشغَّل هنا — يتطلّب مفتاحاً وشبكة.

Run:  python3 -m pytest tests/test_ws10_golden_case.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_CASE = {
    "structural": {
        "required_sections": ["القرار وأساسه", "السوق بالأرقام",
                              "المنافسة والتسعير", "مسار الدخول",
                              "المخاطر", "المراجع"],
        "clean_body": True, "references_integrity": True, "gap_rate_max": 0.3,
    }
}


def test_golden_case_file_loads_and_validates():
    import silk_evals as E
    cases = E.load_golden_cases()
    keys = [c["key"] for c in cases]
    assert "qatar_peanut_butter" in keys      # الفجوة النظامية مُغلقة (لا ملف فارغ)
    case = next(c for c in cases if c["key"] == "qatar_peanut_butter")
    assert E.validate_case(case) == []
    assert case["hs_code"] == "200811" and case["origin"] == "SAU"
    assert case["structural"]["clean_body"] is True


def test_validate_case_requires_expected_or_structural():
    import silk_evals as E
    bad = {"key": "x", "product": "p", "market": "قطر", "hs_code": "200811",
           "verified_at": "2026-07-23", "verified_by": "t"}
    errs = E.validate_case(bad)
    assert any("expected" in e and "structural" in e for e in errs)
    # سقف فجوات خارج [0,1] مرفوض.
    bad2 = {**bad, "structural": {"gap_rate_max": 1.5}}
    assert any("gap_rate_max" in e for e in E.validate_case(bad2))


def test_structural_gate_passes_on_clean_result():
    import silk_evals as E
    import tools.gen_client_report_sample as gcs   # استيرادٌ بلا أثر جانبي (تحت __main__)
    out = E.structural_checks(gcs.result, _CASE)
    assert out["passed"], out["failures"]
    assert out["checks"]["clean_body"]["passed"]
    assert out["checks"]["required_sections"]["passed"]
    assert out["checks"]["references_integrity"]["passed"]
    assert out["checks"]["gap_rate"]["passed"]


def test_structural_gate_catches_dirty_body():
    # نتيجةٌ سابقة لـWS10 (جدول تسعير بعمود «مستوى التوثيق» وشارة ✓) تُمسَك.
    import silk_evals as E
    from tools.canonical_dza_peanut_butter import dza_research_blob
    out = E.structural_checks(dza_research_blob(), _CASE)
    assert not out["passed"]
    hits = out["checks"]["clean_body"]["hits"]
    assert "مستوى التوثيق" in hits and "✓" in hits


def test_required_sections_detects_a_missing_section():
    import silk_evals as E
    import tools.gen_client_report_sample as gcs
    case = {"structural": {"required_sections": ["قسمٌ غير موجود إطلاقاً ٱ"]}}
    out = E.structural_checks(gcs.result, case)
    assert not out["passed"]
    assert "قسمٌ غير موجود إطلاقاً ٱ" in out["checks"]["required_sections"]["missing"]


def test_gap_rate_counts_declared_gaps():
    import silk_evals as E
    result = {"deep_research": {"missions": {
        "m1": {"findings": [{"value": 5}, {"value": None},
                            {"value": 3, "status": "fetch_failed"}]}}}}
    rate, gaps, total = E.gap_rate(result)
    assert (gaps, total) == (2, 3) and round(rate, 3) == 0.667


def test_main_skips_with_reason_without_key(monkeypatch, capsys):
    import silk_evals as E
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rc = E.main(["--case", "qatar_peanut_butter"])
    assert rc == 0                       # تخطٍّ لا فشل — إشارة CI نظيفة
    import json
    out = json.loads(capsys.readouterr().out)
    assert out["skipped"] is True and "ANTHROPIC_API_KEY" in out["reason"]
    assert "silk_evals.py --case qatar_peanut_butter" in out["how_to_run_live"]
