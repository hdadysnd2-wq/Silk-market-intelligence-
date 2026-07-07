"""اختبارات الموجة ١١ — نموذج ITC: العرض + الفرصة القابلة للاقتناص.

يقفل (وفق docs/RESEARCH_METHODOLOGY.md §1):
1. addressable = market_imports × (1 − saudi_share/100) — مرصوب بالكامل من
   رقمين، ويُعلن None لو غاب أحدهما (لا اختلاق، لا صفر وهمي).
2. addressable لا يدخل total_score (سرد فرصة إضافي، لا وزن).
3. saudi_world_supply يتدهور بأمان بلا شبكة (None، ثقة 0).
4. build_view يحمل addressable لكل سوق و supply على الأعلى، ويعلن الغياب.
Run:  python3 -m pytest tests/test_wave11_itc_potential.py -q
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_market_ranker as R
from silk_market_ranker import _addressable_component, saudi_world_supply
from silk_render import build_view


def _block_network():
    def guard(*a, **k):
        raise OSError("network blocked in test")
    socket.socket = guard


def test_addressable_is_imports_times_uncaptured_share():
    # سوق يستورد 100M$، حصة السعودية 30% => القابل للاقتناص 70M$.
    dp = _addressable_component(100_000_000.0, 30.0, "080410", "784", 2022)
    assert dp.value == 70_000_000.0
    assert dp.confidence > 0
    assert "headroom" in dp.note


def test_addressable_declares_gap_when_inputs_missing():
    # غياب أي مدخل => None (لا صفر مختلق).
    assert _addressable_component(None, 30.0, "1", "1", 2022).value is None
    assert _addressable_component(100.0, None, "1", "1", 2022).value is None
    assert _addressable_component(None, None, "1", "1", 2022).confidence == 0.0


def test_addressable_full_share_leaves_zero_headroom():
    # حصة سعودية 100% => لا فرصة إضافية (صفرٌ مرصوب لا مُختلق: كلا الرقمين حقيقي).
    dp = _addressable_component(50_000_000.0, 100.0, "1", "1", 2022)
    assert dp.value == 0.0 and dp.confidence > 0


def test_supply_degrades_gracefully_offline():
    saved = socket.socket
    try:
        _block_network()
        dp = saudi_world_supply("080410", 2022)
        assert dp.value is None and dp.confidence == 0.0
    finally:
        socket.socket = saved


def test_addressable_not_in_weighted_score():
    # القابل للاقتناص ليس من مكوّنات الوزن — لا يحرّك النقاط.
    assert "addressable" not in R.WEIGHTS


def _fake_ranked_row():
    from silk_data_layer import DataPoint
    def dp(v):
        return DataPoint(v, "UN Comtrade", 0.9 if v is not None else 0.0, "n")
    return {
        "country": "الإمارات", "iso3": "ARE", "m49": "784",
        "total_score": 0.7, "confidence": 0.75,
        "components": {"market_size": dp(400_000_000.0),
                       "saudi_position": dp(25.0),
                       "demand_capacity": dp(78000.0), "competition": dp(0.2)},
        "addressable": dp(300_000_000.0),
        "competitors": [], "recommendation": "",
    }


def test_build_view_carries_addressable_and_supply():
    from silk_data_layer import DataPoint
    result = {"product": "تمور", "hs_code": "080410", "year": 2022,
              "classified": True, "markets": [_fake_ranked_row()],
              "supply": DataPoint(1_200_000_000.0, "UN Comtrade", 0.9, "n")}
    view = build_view(result)
    m0 = view["markets"][0]
    assert m0["addressable"] == 300_000_000.0
    assert m0["addressable_detail"]["source"] == "UN Comtrade"
    assert view["supply"]["value"] == 1_200_000_000.0


def test_build_view_declares_missing_supply_and_addressable():
    result = {"product": "x", "hs_code": "1", "year": 2022, "classified": True,
              "markets": [{"country": "c", "iso3": "ARE", "total_score": 0.1,
                           "confidence": 0.1, "components": {}}]}
    view = build_view(result)
    assert view["markets"][0]["addressable"] is None
    assert view["supply"]["value"] is None
