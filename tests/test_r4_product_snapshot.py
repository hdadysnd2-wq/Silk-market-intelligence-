"""اختبارات PR-E (R4 لقطة المنتج الجديد السريعة): «هل يستحق دراسة كاملة؟»
تعيد استخدام بعثة pricing_scout مقيَّدةً + تخزين لكل (منتج × سوق) فتكرار
السؤال يُخدَم من المخزن بلا حرق أرصدة، والتكلفة تُعرَض قبل التشغيل.

المبدأ المؤسِّس: بلا شبكة/مفتاح => فجوات معلنة لا اختلاق.
Run:  python3 -m pytest tests/test_r4_product_snapshot.py -q
"""
import importlib
import os
import sys
import tempfile
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conftest import block_network  # noqa: E402


def _market(name="United Arab Emirates"):
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market(name)
    return ref


# ── التخزين لكل (منتج × سوق) ──────────────────────────────────────────────

def test_product_snapshot_store_roundtrip_and_upsert():
    import silk_storage as S
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    snap = {"product": "تمر", "hs_code": "080410",
            "competing_products": [{"item": "تمر تونسي 6$/كجم"}],
            "worth_full_study": {"worth": True, "why": "إشارة"}}
    S.save_product_snapshot("080410", "ARE", snap, path=db)
    got = S.get_product_snapshot("080410", "ARE", path=db)
    assert got is not None
    assert got["from_store"] is True and got["stored_at"]     # عقد المخزن
    assert got["product"] == "تمر"
    # تحديث يستبدل الصفّ (لا صفّ ثانٍ)
    S.save_product_snapshot("080410", "ARE", {**snap, "product": "تمر محدّث"},
                            path=db)
    again = S.get_product_snapshot("080410", "ARE", path=db)
    assert again["product"] == "تمر محدّث"


def test_get_missing_snapshot_is_none():
    import silk_storage as S
    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    S.init_db(db)
    assert S.get_product_snapshot("999999", "ZZZ", path=db) is None


# ── محرّك اللقطة السريعة ──────────────────────────────────────────────────

def test_quick_snapshot_offline_declares_gaps_not_fabricate():
    import silk_snapshot as SN
    with block_network():
        snap = SN.quick_snapshot("تمر", "080410", _market())
    assert snap["competing_products"] == []       # لا اختلاق منتجات
    assert snap["top_suppliers"] == []            # لا اختلاق مورّدين
    assert snap["worth_full_study"]["worth"] is None   # لا حسم على فجوة
    assert snap["market"]["iso3"] == "ARE"
    assert snap["from_store"] is False


def test_worth_full_study_signal_vs_gap():
    import silk_snapshot as SN
    worth = SN._worth_full_study([{"item": "x"}], [{"partner": "تونس"}], "s")
    assert worth["worth"] is True
    gap = SN._worth_full_study([], [], "لا نتائج")
    assert gap["worth"] is None                   # غياب إشارة ≠ 'لا يستحق' يقيناً


# ── نقطة النهاية: التكلفة قبل التشغيل + المخزن أولاً ───────────────────────

import contextlib  # noqa: E402


@contextlib.contextmanager
def _client():
    """TestClient بقواعد مؤقتة معزولة — يُرجِع البيئة ويعيد تحميل api عند
    الخروج كي لا تتسرّب متغيّرات SILK_DB إلى اختبارات لاحقة."""
    import api
    from fastapi.testclient import TestClient
    keys = ("SILK_API_KEY", "ANTHROPIC_API_KEY", "SILK_RATE_LIMIT",
            "SILK_DB", "SILK_STORE_DB", "SILK_USAGE_DB")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.pop("SILK_API_KEY", None)
    os.environ.pop("ANTHROPIC_API_KEY", None)
    os.environ["SILK_RATE_LIMIT"] = "0"
    tmp = tempfile.mkdtemp()
    os.environ["SILK_DB"] = os.path.join(tmp, "silk.db")
    os.environ["SILK_STORE_DB"] = os.path.join(tmp, "store.db")
    os.environ["SILK_USAGE_DB"] = os.path.join(tmp, "usage.db")
    importlib.reload(api)
    try:
        yield TestClient(api.create_app())
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(api)


def test_snapshot_precheck_shows_cost_without_running():
    """بلا confirm: تُعاد التكلفة المقدَّرة ولا تشغيل ولا تخزين."""
    ran = {"n": 0}

    def spy(*a, **k):
        ran["n"] += 1
        return {}

    with _client() as client, mock.patch("silk_snapshot.quick_snapshot", spy):
        r = client.post("/products/snapshot",
                        json={"product": "تمر", "market": "United Arab Emirates"})
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot"] is None
    assert body["cost"]["claude_activations"] == 1     # التكلفة معروضة
    assert body["cached"] is False
    assert ran["n"] == 0                               # لم يُشغَّل شيء


def test_snapshot_confirm_runs_stores_and_repeat_is_cached():
    """confirm يشغّل ويخزّن؛ تكرار السؤال (بلا refresh) يُخدَم من المخزن
    بتكلفة صفر — لا حرق أرصدة."""
    canned = {"product": "تمر", "hs_code": "080410",
              "market": {"iso3": "ARE"}, "competing_products": [{"item": "x"}],
              "top_suppliers": [], "worth_full_study": {"worth": True, "why": "y"},
              "from_store": False}
    calls = {"n": 0}

    def fake(product, hs, ref, **k):
        calls["n"] += 1
        return dict(canned)

    with _client() as client, mock.patch("silk_snapshot.quick_snapshot", fake):
        r1 = client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates", "confirm": True})
        assert r1.status_code == 200 and r1.json()["snapshot"] is not None
        assert r1.json()["cached"] is False and calls["n"] == 1
        # تكرار بلا refresh => من المخزن، صفر تشغيل
        r2 = client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates"})
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert r2.json()["cost"]["claude_activations"] == 0
        assert calls["n"] == 1                         # لم يُعَد التشغيل


def test_snapshot_refresh_reruns_even_if_cached():
    calls = {"n": 0}

    def fake(product, hs, ref, **k):
        calls["n"] += 1
        return {"product": product, "hs_code": hs, "market": {"iso3": "ARE"},
                "competing_products": [], "top_suppliers": [],
                "worth_full_study": {"worth": None, "why": "y"},
                "from_store": False}

    with _client() as client, mock.patch("silk_snapshot.quick_snapshot", fake):
        client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates", "confirm": True})
        client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates", "refresh": True, "confirm": True})
    assert calls["n"] == 2                             # التحديث أعاد التشغيل


def test_snapshot_ui_wired():
    """الواجهة: زرّ «لقطة سريعة» + تدفق التكلفة-قبل-التشغيل موصولان."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "web", "index.html"), encoding="utf-8").read()
    assert 'id="snapBtn"' in html
    assert "function quickSnapshot" in html
    assert "/products/snapshot" in html
    assert "confirm:true" in html                      # مسار التأكيد
    assert "من المخزن" in html                          # وسم الخدمة من المخزن
