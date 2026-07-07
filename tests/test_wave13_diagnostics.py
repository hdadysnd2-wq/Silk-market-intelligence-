"""اختبارات الموجة ١٣ — تشخيص المصادر الحيّ.

يقفل:
1. بلا شبكة => كل المصدر unreachable، agents_can_work=False، وتلميح لكل مصدر.
2. عند وصول بيانات (محقونة) => ok و agents_can_work=True.
3. متصل بلا صفوف => reachable_empty مع تلميح المفتاح.
4. نقطة /diagnostics لا ترمي أبداً (تتدهور بأمان).
Run:  python3 -m pytest tests/test_wave13_diagnostics.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import silk_data_layer as dl
import silk_diagnostics as diag


class _Resp:
    def __init__(self, payload):
        self._p = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._p


def test_offline_all_unreachable(monkeypatch):
    def boom(url, params=None):
        raise OSError("network blocked")
    monkeypatch.setattr(dl, "_http_get", boom)
    out = diag.run_diagnostics(2022)
    assert out["overall"] == "unreachable"
    assert out["agents_can_work"] is False
    assert all(s["state"] == "unreachable" and s["hint"] for s in out["sources"])


def test_injected_data_makes_agents_workable(monkeypatch):
    def ok(url, params=None):
        if "worldbank" in url or "indicator" in url:
            return _Resp([{"page": 1}, [{"date": "2022", "value": 78000}]])
        return _Resp({"data": [{"partnerCode": 0, "primaryValue": 4.1e8}]})
    monkeypatch.setattr(dl, "_http_get", ok)
    out = diag.run_diagnostics(2022)
    assert out["overall"] == "ok"
    assert out["agents_can_work"] is True
    assert all(s["state"] == "ok" for s in out["sources"])


def test_reachable_but_empty_hints_key(monkeypatch):
    monkeypatch.delenv("COMTRADE_API_KEY", raising=False)

    def empty(url, params=None):
        if "worldbank" in url or "indicator" in url:
            return _Resp([{"page": 1}, [{"date": "2022", "value": 78000}]])
        return _Resp({"data": []})  # reachable, zero rows
    monkeypatch.setattr(dl, "_http_get", empty)
    out = diag.run_diagnostics(2022)
    ct = [s for s in out["sources"] if s["name"] == "UN Comtrade"][0]
    assert ct["state"] == "reachable_empty"
    assert "COMTRADE_API_KEY" in ct["hint"]
    assert out["overall"] == "reachable_empty"


def test_endpoint_never_500(monkeypatch):
    from fastapi.testclient import TestClient
    import api

    def boom(url, params=None):
        raise OSError("blocked")
    monkeypatch.setattr(dl, "_http_get", boom)
    r = TestClient(api.app).get("/diagnostics")
    assert r.status_code == 200
    assert r.json()["agents_can_work"] is False
