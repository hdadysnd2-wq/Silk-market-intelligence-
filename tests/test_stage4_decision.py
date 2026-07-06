"""اختبارات Stage 4 — محرك القرار الموزون (§8) والاختبار الرجعي (GATE 3).

يقفل: العتبات المعلنة (GO/CONDITIONAL/NO-GO)، بوابة الخطر الحرج، إعادة تسوية
الأوزان عند عمود غائب (فجوة تصير شرطاً لا تخميناً)، سقف بوابة الأهلية، حساب
كلا خياري الأوزان دائماً، قاعدة اتفاق الاختبار الرجعي، وربط المحرّك.
"""
import copy
import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from conftest import block_network  # noqa: E402

import silk_decision as D  # noqa: E402

# حزمة أساس قوية الأعمدة — تُنسخ وتُضعف عمداً في كل اختبار.
BUNDLE = {
    "coverage": 0.85,
    "pillar_inputs": {
        "market_attractiveness": {"tam_usd": 2.9e8, "import_cagr_pct": 20.0,
                                  "gdp_per_capita_usd": 48_000,
                                  "saudi_share_pct": 8.0},
        "competition_intensity": {"hhi": 0.12, "top_supplier_share_pct": 21.0,
                                  "named_company_count": 7},
        "regulatory_fit": {"tariff_applied_pct": 0.0,
                           "entry_requirements_count": 9,
                           "eligibility_gate": False},
        "profitability": {"border_unit_value_usd_kg": 3.4,
                          "saudi_border_unit_value_usd_kg": 3.1,
                          "margin_at_border_pct": 18.0},
        "risk": {"political_stability_wgi": 0.8, "fx_volatility_pct": 0.9,
                 "supplier_concentration_hhi": 0.12, "critical_risk": False},
    },
}


def _b(**overrides):
    b = copy.deepcopy(BUNDLE)
    for pillar, vals in overrides.items():
        b["pillar_inputs"][pillar].update(vals)
    return b


def test_go_when_score_and_confidence_clear_thresholds():
    d = D.decide(BUNDLE)
    assert d["verdict"] == "GO" and d["score"] >= 0.65
    assert d["confidence"] == 0.85          # تغطية × 4/4 أعمدة
    assert "×" in d["confidence_basis"]     # الأساس معلن لا رقم حدسي
    for p in d["pillars"].values():
        assert p["basis"]                   # كل عمود يطبع معادلته


def test_nogo_below_threshold_and_critical_risk_gate():
    weak = _b(market_attractiveness={"tam_usd": 1e5, "import_cagr_pct": -8.0,
                                     "gdp_per_capita_usd": 2_000,
                                     "saudi_share_pct": 0.0},
              competition_intensity={"hhi": 0.45,
                                     "top_supplier_share_pct": 85.0},
              regulatory_fit={"tariff_applied_pct": 28.0,
                              "entry_requirements_count": 1},
              profitability={"margin_at_border_pct": -5.0,
                             "saudi_border_unit_value_usd_kg": 5.5})
    d = D.decide(weak)
    assert d["verdict"] == "NO-GO" and d["score"] < 0.45
    # بوابة الخطر الحرج تقلب GO إلى NO-GO حتى مع score مرتفع — قاعدة §8.
    crit = _b(risk={"critical_risk": True})
    d2 = D.decide(crit)
    assert d2["verdict"] == "NO-GO" and d2["critical_risk"] is True
    assert "حرجة" in d2["why"]


def test_missing_pillar_renormalizes_and_becomes_condition():
    b = copy.deepcopy(BUNDLE)
    b["pillar_inputs"]["profitability"] = {}          # لا مدخلات ربحية إطلاقاً
    d = D.decide(b)
    assert d["missing_pillars"] == ["profit"]
    assert d["pillars"]["profit"]["value"] is None    # لا تخمين
    assert d["confidence"] == round(0.85 * 0.75, 2)   # 3/4 أعمدة
    assert any("هامش الربحية" in c for c in d["conditions"])
    assert d["verdict"] == "CONDITIONAL-GO"           # الفجوة شرط لا مانع
    # الدرجة أعيدت تسويتها على 0.75 من الأوزان — لا صفر مختلق عن العمود الغائب.
    assert d["score"] is not None


def test_eligibility_gate_caps_regulatory_and_leads_steps():
    d = D.decide(_b(regulatory_fit={"eligibility_gate": True}))
    assert d["pillars"]["regulatory"]["value"] <= 0.3
    assert "أهلية" in d["conditions"][0]
    assert d["verdict"] == "CONDITIONAL-GO"
    assert "2017/625" in d["first_steps"][0]


def test_both_weight_options_always_reported_and_selectable():
    d = D.decide(BUNDLE)
    assert set(d["scores_by_option"]) == {"A", "B"}
    assert "GATE 3" in d["weights_note"]
    # حالة تنظيمية قوية وسوق ضعيف: B (تنظيمي مثقّل) أعلى من A — اتجاه منطقي.
    reg_strong = _b(market_attractiveness={"tam_usd": 5e5,
                                           "import_cagr_pct": -5.0,
                                           "gdp_per_capita_usd": 5_000,
                                           "saudi_share_pct": 0.5})
    d2 = D.decide(reg_strong)
    assert d2["scores_by_option"]["B"] > d2["scores_by_option"]["A"]
    # الاختيار الصريح يعمل، والبيئة تُحترم افتراضياً (A).
    assert D.decide(BUNDLE, weights_option="B")["weights_option"] == "B"
    assert d["weights_option"] == "A"


def test_backtest_agreement_rule_and_cases_reference():
    spec = importlib.util.spec_from_file_location(
        "backtest", os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "tools", "backtest.py"))
    bt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bt)
    # قاعدة الاتفاق المعلنة: نجاح ⇒ ليس NO-GO؛ تعثر ⇒ ليس GO.
    assert bt.agrees("success", "GO") and bt.agrees("success", "CONDITIONAL-GO")
    assert not bt.agrees("success", "NO-GO")
    assert bt.agrees("stalled", "NO-GO") and bt.agrees("stalled",
                                                       "CONDITIONAL-GO")
    assert not bt.agrees("stalled", "GO")
    cases = bt.load_cases()
    assert len(cases) == 5
    assert all(c["outcome"] in ("success", "stalled") for c in cases)
    assert all(c["evidence"].strip() for c in cases)   # كل حالة بدليلها الموثّق


def test_engine_attaches_decision_with_research():
    import silk_store
    silk_store.migrate()
    silk_store.upsert_trade_flows([
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "WLD",
         "year": 2023, "flow": "M", "value_usd": 6.0e7, "qty_kg": 2.0e7},
        {"hs6": "080410", "reporter_iso3": "CHN", "partner_iso3": "SAU",
         "year": 2023, "flow": "M", "value_usd": 1.8e7, "qty_kg": 8.0e6}])
    import silk_engine
    with block_network():
        res = silk_engine.analyze("تمور",
                                  countries=[{"iso3": "CHN", "m49": "156"}],
                                  year=2023, with_research=True)
    dec = res["markets"][0]["decision"]
    assert dec["schema"] == "silk.decision/v1"
    assert dec["verdict"] in ("GO", "CONDITIONAL-GO", "NO-GO")
    assert dec["weights_option"] == "A"
    assert dec["confidence_basis"]
