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


def test_storage_round_trip(tmp_path=None):
    # خزّن نتيجة وهمية ثم استرجعها — save a fake result, then get it back unchanged.
    import os
    import tempfile
    import silk_storage as storage

    db = os.path.join(tempfile.mkdtemp(), "smoke.db")
    fake = {"product": "demo", "hs_code": "000000", "year": 2022,
            "preliminary": True,
            "markets": [{"country": "Demo-Land", "iso3": "XXX",
                         "total_score": 0.0, "confidence": 0.0}]}
    aid = storage.save_analysis(fake, db)
    got = storage.get_analysis(aid, db)
    assert got is not None and got["product"] == "demo"
    assert any(r["id"] == aid for r in storage.list_analyses(db))


def test_quality_flags_near_zero():
    # صف بحجم سوق شبه صفري => تنبيه عدم تطابق — near-zero size flags a mismatch.
    import silk_quality as quality

    row = {"country": "X", "iso3": "XXX",
           "components": {"market_size": {"value": 12.0},
                          "saudi_position": {"value": 3.0},
                          "demand_capacity": {"value": 1.0e9},
                          "competition": {"value": 0.4}}}
    flags = quality.validate_market_row(row)
    assert any("near-zero" in f for f in flags)


def test_engine_optional_layers_offline():
    # كل الطبقات الاختيارية مفعّلة بلا شبكة: لا تعطّل، يبقى التصنيف سليمًا.
    import os
    import tempfile

    db = os.path.join(tempfile.mkdtemp(), "engine.db")
    res = engine.analyze("تمور", countries=[{"iso3": "ARE", "m49": "784"}],
                         year=2022, with_trends=True, with_tariffs=True,
                         persist=True, db_path=db)
    assert res["classified"] is True and res["hs_code"] == "080410"
    assert "quality_flags" in res["markets"][0]      # quality on by default
    assert "analysis_id" in res                       # persisted
    # طبقات السياق مرفقة (قيم None بلا شبكة، لا اختلاق) — context attached, None offline.
    assert "trends" in res["markets"][0] and "tariff" in res["markets"][0]
    assert res["markets"][0]["total_score"] == 0.0    # additive context, score unchanged


if __name__ == "__main__":
    import logging

    logging.disable(logging.WARNING)
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL TESTS PASSED")
