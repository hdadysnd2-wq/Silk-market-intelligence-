"""اختبارات دخان بلا شبكة — تتحقق من الاستيراد، التصنيف، والمبدأ التأسيسي (لا اختلاق بيانات).
Offline smoke tests: imports, HS classification, and the no-fabrication principle.
Run:  python3 -m pytest tests/ -q   (or)  python3 tests/test_smoke.py
"""
import contextlib
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_hs_resolver as resolver
import silk_engine as engine


@contextlib.contextmanager
def _block_network():
    """اقطع الشبكة مؤقتًا — force outbound sockets to fail so 'no data => 0.0'
    holds even where the CI has internet. Restores socket.socket on exit."""
    real = socket.socket

    def _no_net(*a, **k):  # noqa: ANN002, ANN003
        raise OSError("network disabled for hermetic test")

    socket.socket = _no_net
    try:
        yield
    finally:
        socket.socket = real


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
    with _block_network():
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
    with _block_network():
        res = engine.analyze("تمور", countries=[{"iso3": "ARE", "m49": "784"}],
                             year=2022, with_trends=True, with_tariffs=True,
                             persist=True, db_path=db)
    assert res["classified"] is True and res["hs_code"] == "080410"
    assert "quality_flags" in res["markets"][0]      # quality on by default
    assert "analysis_id" in res                       # persisted
    # طبقات السياق مرفقة (قيم None بلا شبكة، لا اختلاق) — context attached, None offline.
    assert "trends" in res["markets"][0] and "tariff" in res["markets"][0]
    assert res["markets"][0]["total_score"] == 0.0    # additive context, score unchanged


def test_api_imports_without_fastapi():
    # api.py يُستورد بلا fastapi — import works offline; app may be None.
    import api
    assert hasattr(api, "create_app") and hasattr(api, "app")


def test_faostat_agent_imports():
    # وكيل فاوستات يُستورد بلا شبكة — offline import + graceful None on unknown area.
    import silk_faostat_agent as fao
    dp = fao.per_capita_supply("XXX", "Dates")
    assert dp.value is None and dp.confidence == 0.0  # no fabrication


def test_cache_returns_none_offline():
    # ذاكرة التخزين تُعيد None بلا شبكة — cached_get degrades to None offline.
    import silk_cache
    with _block_network():
        out = silk_cache.cached_get("https://example.invalid/none", {"a": "1"})
    assert out is None


def test_new_agents_import_and_no_fabrication_keyless():
    # الوكلاء الأربعة الجدد يُستوردون بلا شبكة/مفتاح، وكل نداء بلا مفتاح => value=None.
    import silk_maps_agent, silk_websearch_agent, silk_volza_agent, silk_explee_agent

    with _block_network():
        for key in ("GOOGLE_MAPS_API_KEY", "SEARCH_API_KEY",
                    "VOLZA_API_KEY", "EXPLEE_API_KEY"):
            os.environ.pop(key, None)  # ensure keyless
        dps = [
            silk_maps_agent.find_places("dates morocco")[0],
            silk_websearch_agent.web_search("dates demand")[0],
            silk_volza_agent.importers_by_name("080410", "156")[0],
            silk_explee_agent.discover_buyers("dates packaging", "DEU")[0],
        ]
    for dp in dps:
        assert dp.value is None and dp.confidence == 0.0  # no fabrication keyless


def test_engine_paid_layers_offline():
    # الطبقات الأربع الجديدة مفعّلة بلا شبكة/مفتاح: لا تعطّل، يبقى التصنيف سليمًا.
    with _block_network():
        for key in ("GOOGLE_MAPS_API_KEY", "SEARCH_API_KEY",
                    "VOLZA_API_KEY", "EXPLEE_API_KEY"):
            os.environ.pop(key, None)
        res = engine.analyze("تمور", countries=[{"iso3": "ARE", "m49": "784"}],
                             year=2022, with_maps=True, with_websearch=True,
                             with_volza=True, with_explee=True)
    assert res["classified"] is True and res["hs_code"] == "080410"
    row = res["markets"][0]
    # طبقات السياق مرفقة (None بلا مفتاح/شبكة، لا اختلاق) — attached, None offline.
    assert "maps" in row and "volza" in row and "explee" in row
    assert "websearch" in res                            # top-level web search
    assert row["total_score"] == 0.0                     # additive, score unchanged


def test_hs_codes_grew_and_resolve_dates():
    # نمت رموز HS وما زال التمر يُصنّف صحيحًا — table grew; dates still resolve.
    assert len(resolver.load_hs_codes()) >= 157
    assert resolver.resolve("تمور").value == "080410"


if __name__ == "__main__":
    import logging

    logging.disable(logging.WARNING)
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL TESTS PASSED")
