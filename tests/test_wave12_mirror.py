"""اختبارات الموجة ١٢ — التثليث بالمرآة (§2 من RESEARCH_METHODOLOGY).

يقفل:
1. رياضيات الاتفاق نقيّة: تقارب/تباعد/طرف واحد/فجوة بنِسَب صحيحة.
2. mirror_triangulation يتدهور بأمان بلا شبكة (one_sided/gap، لا اختلاق).
3. build_view يمرّر علَم المرآة لكل سوق.
Run:  python3 -m pytest tests/test_wave12_mirror.py -q
"""
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_market_ranker import _mirror_agreement, mirror_triangulation
from silk_render import build_view


def test_agreement_converge():
    r = _mirror_agreement(100.0, 92.0)
    assert r["flag"] == "converge" and r["agreement_pct"] == 92.0


def test_agreement_diverge():
    r = _mirror_agreement(100.0, 40.0)
    assert r["flag"] == "diverge" and r["agreement_pct"] == 40.0


def test_agreement_one_sided_and_gap():
    assert _mirror_agreement(100.0, None)["flag"] == "one_sided"
    assert _mirror_agreement(None, 50.0)["flag"] == "one_sided"
    g = _mirror_agreement(None, None)
    assert g["flag"] == "gap" and g["agreement_pct"] is None


def test_agreement_boundary_70pct_is_converge():
    r = _mirror_agreement(100.0, 70.0)
    assert r["flag"] == "converge" and r["agreement_pct"] == 70.0


def test_mirror_triangulation_offline_is_one_sided_or_gap():
    # بلا شبكة: الطرف المُصدَّر None. مع importer=قيمة => one_sided؛ بلا شيء => gap.
    saved = socket.socket
    try:
        socket.socket = lambda *a, **k: (_ for _ in ()).throw(OSError("blocked"))
        one = mirror_triangulation("080410", 784, 5_000_000.0, 2022)
        assert one["flag"] == "one_sided" and one["exporter_reported"] is None
        gap = mirror_triangulation("080410", 784, None, 2022)
        assert gap["flag"] == "gap"
        assert "mirror" in one["source"]
    finally:
        socket.socket = saved


def test_build_view_passes_mirror_flag():
    result = {"product": "x", "hs_code": "1", "year": 2022, "classified": True,
              "markets": [{"country": "c", "iso3": "ARE", "m49": "784",
                           "total_score": 0.5, "confidence": 0.5,
                           "components": {},
                           "mirror": {"flag": "converge", "agreement_pct": 88.0,
                                      "note": "n", "source": "UN Comtrade (mirror)"}}]}
    view = build_view(result)
    assert view["markets"][0]["mirror"]["flag"] == "converge"
