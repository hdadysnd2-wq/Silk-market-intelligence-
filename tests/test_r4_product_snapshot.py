"""اختبارات R4/ITEM٢ (معاينة المنتج الفورية): «هل يستحق دراسة كاملة؟»

قرار حي (بلاغ تدقيق التكلفة): كانت تعيد استخدام بعثة pricing_scout (كلود)
بميزانية مقيَّدة خلف تأكيد صريح؛ أُزيل نداء كلود هذا نهائياً — المعاينة
الآن **مجانية دوماً** (مورّدو كومتريد فقط)، مع تخزين لكل (منتج × سوق) يخدم
التكرار من المخزن. لا سعر منافِس على زوج جديد لم يُلقَط — فجوة معلنة صريحة
توجّه إلى البحث العميق، لا اختلاق.

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


def test_snapshot_runs_immediately_free_no_confirm_needed():
    """لا خطوة تأكيد بعد الآن — المعاينة تُشغَّل وتُخزَّن فوراً، مجاناً."""
    canned = {"product": "تمر", "hs_code": "080410",
              "market": {"iso3": "ARE"}, "competing_products": [],
              "top_suppliers": [], "worth_full_study": {"worth": None, "why": "y"},
              "from_store": False}
    calls = {"n": 0}

    def fake(product, hs, ref):
        calls["n"] += 1
        return dict(canned)

    with _client() as client, mock.patch("silk_snapshot.quick_snapshot", fake):
        r = client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates"})
    assert r.status_code == 200
    body = r.json()
    assert body["snapshot"] is not None
    assert body["cached"] is False and calls["n"] == 1
    assert body["cost"]["claude_activations"] == 0     # مجانية دوماً الآن


def test_snapshot_repeat_without_refresh_is_cached_no_rerun():
    canned = {"product": "تمر", "hs_code": "080410",
              "market": {"iso3": "ARE"}, "competing_products": [{"item": "x"}],
              "top_suppliers": [], "worth_full_study": {"worth": True, "why": "y"},
              "from_store": False}
    calls = {"n": 0}

    def fake(product, hs, ref):
        calls["n"] += 1
        return dict(canned)

    with _client() as client, mock.patch("silk_snapshot.quick_snapshot", fake):
        r1 = client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates"})
        assert r1.json()["cached"] is False and calls["n"] == 1
        r2 = client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates"})
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert r2.json()["cost"]["claude_activations"] == 0
        assert calls["n"] == 1                         # لم يُعَد التشغيل


def test_snapshot_refresh_reruns_even_if_cached():
    calls = {"n": 0}

    def fake(product, hs, ref):
        calls["n"] += 1
        return {"product": product, "hs_code": hs, "market": {"iso3": "ARE"},
                "competing_products": [], "top_suppliers": [],
                "worth_full_study": {"worth": None, "why": "y"},
                "from_store": False}

    with _client() as client, mock.patch("silk_snapshot.quick_snapshot", fake):
        client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates"})
        client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates", "refresh": True})
    assert calls["n"] == 2                             # التحديث أعاد التشغيل


def test_snapshot_never_calls_claude():
    """إثبات بنيوي — لا نداء كلود إطلاقاً من هذا المسار بعد الآن (ITEM ٢).

    (لا block_network هنا — يقطع socket.socket عالمياً فيكسر نقل TestClient
    الداخلي؛ نفس القيد الموثَّق في CLAUDE.md، الحجب هنا عبر requests فقط.)
    """
    def _boom(*a, **k):
        raise AssertionError("quick snapshot must never call Claude")

    with _client() as client, \
         mock.patch("silk_llm_provider.AnthropicProvider.complete", side_effect=_boom), \
         mock.patch("silk_llm_provider.AnthropicProvider.complete_tools", side_effect=_boom), \
         mock.patch("requests.sessions.Session.request",
                    side_effect=OSError("network disabled for hermetic test")):
        r = client.post("/products/snapshot", json={
            "product": "تمر", "hs_code": "080410",
            "market": "United Arab Emirates"})
    assert r.status_code == 200
    assert r.json()["snapshot"]["competing_products"] == []   # فجوة معلنة لا اختلاق


def test_snapshot_ui_wired():
    """الواجهة: زرّ «معاينة فورية» + مسار مجاني مباشر بلا تأكيد."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "web", "index.html"), encoding="utf-8").read()
    assert 'id="snapBtn"' in html
    assert "function quickSnapshot" in html
    assert "/products/snapshot" in html
    assert "confirm:true" not in html                  # مسار التأكيد أُزيل
    assert "من المخزن" in html                          # وسم الخدمة من المخزن
    assert "بلا أي نداء كلود" in html or "مجانية" in html
