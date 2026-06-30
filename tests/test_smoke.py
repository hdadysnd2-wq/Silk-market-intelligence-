"""اختبارات دخان بلا شبكة — تتحقق من الاستيراد، التصنيف، والمبدأ التأسيسي (لا اختلاق بيانات).
Offline smoke tests: imports, HS classification, and the no-fabrication principle.
Run:  python3 -m pytest tests/ -q   (or)  python3 tests/test_smoke.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_hs_resolver as resolver
import silk_engine as engine


def test_all_modules_import():
    import silk_data_layer, silk_data_layer_v2, silk_agents, silk_market_ranker  # noqa: F401


def test_resolver_real_hs_codes():
    assert resolver.resolve("تمور").value == "080410"
    assert resolver.resolve("saffron").value == "091020"
    # كلمة بلا معنى => لا تصنيف ولا اختلاق رمز
    miss = resolver.resolve("xqzwv nonsense 123")
    assert miss.value is None and miss.confidence == 0.0


def test_engine_pipeline_offline_no_fabrication():
    # بلا شبكة: المحرّك يصنّف المنتج لكن لا يخترع أرقام أسواق
    res = engine.analyze("تمور", countries=[{"iso3": "ARE", "m49": "784"}], year=2022)
    assert res["classified"] is True
    assert res["hs_code"] == "080410"
    assert res["preliminary"] is True
    row = res["markets"][0]
    assert row["total_score"] == 0.0 and row["confidence"] == 0.0  # no data => no invented score


if __name__ == "__main__":
    import logging

    logging.disable(logging.WARNING)
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL TESTS PASSED")
