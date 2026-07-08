"""اختبارات القرص الدائم — persistent-volume wiring (Railway /data).

يثبت أن متغير `SILK_DATA_DIR` الواحد يوجّه المخازن الأربعة (قاعدة التحليلات،
مخزن الحقائق، عدّاد الاستهلاك، ذاكرة الطلبات) لمسار القرص، وأن «إعادة نشر»
(عملية جديدة تمامًا على نفس مسار القرص) تجد الحقيقة المخزّنة وتخدمها **بلا
أي نداء شبكة** — هذا هو عقد «لا ندفع مرتين». المبدأ التأسيسي محفوظ: القيم
تُقرأ كما خُزّنت بمصدرها، والغياب يبقى غيابًا.
Proves one env var routes all four stores to the volume, and a fresh process
on the same volume path serves the stored fact with zero network calls.
"""
import json
import os
import subprocess
import sys

import silk_cache
import silk_storage
import silk_store
import silk_usage

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ── اشتقاق المسارات · path derivation ───────────────────────────────────────

def test_data_dir_derives_all_store_paths(monkeypatch, tmp_path):
    """SILK_DATA_DIR وحده يوجّه المخازن الأربعة — one var, four stores."""
    for var in ("SILK_DB", "SILK_STORE_DB", "SILK_USAGE_DB", "SILK_CACHE_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SILK_DATA_DIR", str(tmp_path))
    assert silk_storage._db_path() == os.path.join(str(tmp_path), "silk.db")
    assert silk_store._db_path() == os.path.join(str(tmp_path), "silk_store.db")
    assert silk_usage._db_path() == os.path.join(str(tmp_path), "usage.db")
    assert silk_cache._cache_dir() == os.path.join(str(tmp_path), "cache")


def test_explicit_vars_win_over_data_dir(monkeypatch, tmp_path):
    """المتغير الصريح يفوز على SILK_DATA_DIR — explicit per-store override wins."""
    monkeypatch.setenv("SILK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SILK_DB", "/elsewhere/a.db")
    monkeypatch.setenv("SILK_STORE_DB", "/elsewhere/b.db")
    monkeypatch.setenv("SILK_USAGE_DB", "/elsewhere/c.db")
    monkeypatch.setenv("SILK_CACHE_DIR", "/elsewhere/cache")
    assert silk_storage._db_path() == "/elsewhere/a.db"
    assert silk_store._db_path() == "/elsewhere/b.db"
    assert silk_usage._db_path() == "/elsewhere/c.db"
    assert silk_cache._cache_dir() == "/elsewhere/cache"


def test_defaults_unchanged_without_env(monkeypatch):
    """بلا متغيرات: الافتراضيات المحلية كما كانت — local defaults untouched."""
    for var in ("SILK_DATA_DIR", "SILK_DB", "SILK_STORE_DB",
                "SILK_USAGE_DB", "SILK_CACHE_DIR"):
        monkeypatch.delenv(var, raising=False)
    assert silk_storage._db_path() == os.path.join("data", "silk.db")
    assert silk_store._db_path() == os.path.join("data", "silk_store.db")
    assert silk_usage._db_path() == os.path.join("data", "usage.db")
    assert silk_cache._cache_dir() == os.path.join("data", "cache")


def test_cache_dir_env_honored_end_to_end(monkeypatch, tmp_path):
    """cached_get يكتب ويقرأ من SILK_CACHE_DIR — الملف ينجو لعملية أخرى."""
    monkeypatch.setenv("SILK_CACHE_DIR", str(tmp_path / "cache"))

    class _Resp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"real": True}]}

    calls = {"n": 0}

    def fetcher(url, params):
        calls["n"] += 1
        return _Resp()

    out1 = silk_cache.cached_get("https://x.example/api", {"q": 1},
                                 fetcher=fetcher)
    assert out1 == {"data": [{"real": True}]}
    assert calls["n"] == 1
    assert os.listdir(str(tmp_path / "cache"))  # كُتب على «القرص»
    # القراءة الثانية من القرص — صفر جلب حي. Second read: zero live fetches.
    out2 = silk_cache.cached_get("https://x.example/api", {"q": 1},
                                 fetcher=fetcher)
    assert out2 == out1
    assert calls["n"] == 1


# ── محاكاة إعادة النشر · redeploy simulation (fresh process, same volume) ────

_WRITER = """
import os, sys
sys.path.insert(0, {repo!r})
import silk_store
silk_store.migrate()
silk_store.upsert_trade_flows([
    {{"hs6": "090111", "reporter_iso3": "DEU", "partner_iso3": "WLD",
      "year": 2023, "flow": "M", "value_usd": 1234567.0}},
    {{"hs6": "090111", "reporter_iso3": "DEU", "partner_iso3": "BRA",
      "year": 2023, "flow": "M", "value_usd": 700000.0}},
])
print("written")
"""

_READER = """
import json, os, socket, sys
sys.path.insert(0, {repo!r})

from silk_data_layer_v2 import market_imports_cached

def _no_net(*a, **k):
    raise AssertionError("network attempted — store should have served this")

socket.socket = _no_net  # الاستيراد تم؛ الآن أي نداء شبكة فعلي = فشل صريح

mi = market_imports_cached("090111", "276", "DEU", 2023)
comp = [c.value for c in mi["competitors"]]
print(json.dumps({{"total_usd": mi["total_usd"], "competitors": comp,
                   "sources": [c.source for c in mi["competitors"]]}}))
"""


def _run(code: str, env: dict) -> str:
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True,
                          text=True, env=env, cwd=_REPO, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_redeploy_preserves_fact_store_and_serves_without_network(tmp_path):
    """اكتب حقيقة، «أعد النشر» (عملية جديدة، نفس القرص)، اقرأها بلا شبكة.

    Write a fact; simulate a redeploy (fresh process, same volume path);
    assert the value is served from the store with the network hard-blocked.
    """
    env = {k: v for k, v in os.environ.items()
           if k not in ("SILK_DB", "SILK_STORE_DB", "SILK_USAGE_DB",
                        "SILK_CACHE_DIR")}
    env["SILK_DATA_DIR"] = str(tmp_path)

    assert _run(_WRITER.format(repo=_REPO), env) == "written"
    # القرص «نجا» من إعادة النشر — the volume file survived the "redeploy".
    assert os.path.exists(tmp_path / "silk_store.db")

    out = json.loads(_run(_READER.format(repo=_REPO), env))
    assert out["total_usd"] == 1234567.0
    assert out["competitors"] and out["competitors"][0]["value_usd"] == 700000.0
    # الإسناد يعلن أن القيمة من المخزن — provenance declares the store origin.
    assert any("مخزن" in s for s in out["sources"])
