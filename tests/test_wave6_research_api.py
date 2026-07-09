"""اختبارات الموجة ٤ب (V5): POST /research — البحث العميق كنقطة نهاية.

يغطي: سوق غامض => 422 + اقتراحات (لا تخمين)، مسار كيليسي يعمل بلا 500
(كل شيء يتدهور لفجوات معلنة)، مسار كامل مموّه ينتج حكم مرحلة ٢ وتقريراً
مراجَعاً ويُخزَّن، ونموذج الطلب لا يحمل حقولاً مدفوعة (فحص بنيوي).
Run:  python3 -m pytest tests/ -q
"""
import json
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _client():
    from fastapi.testclient import TestClient
    import api
    return TestClient(api.app)


def test_ambiguous_market_returns_422_with_suggestions_no_guessing():
    r = _client().post("/research", json={"product": "تمور", "market": "Nigera"})
    assert r.status_code == 422
    body = r.json()["detail"]
    assert "Nigeria" in body["suggestions"]


def test_no_key_degrades_to_declared_gaps_never_500():
    # TestClient يحتاج مقابس حقيقية داخلياً (نقل anyio) — block_network()
    # يقطع socket.socket عالمياً فيكسر النقل نفسه؛ المطابق هنا (نفس نمط
    # اختبارات FastAPI الأخرى في الحزمة) هو قطع requests.get تحديداً.
    with patch("requests.get", side_effect=OSError("network disabled")):
        r = _client().post("/research", json={
            "product": "تمور", "market": "Nigeria", "hs_code": "080410",
            "persist": False})
    assert r.status_code == 200
    data = r.json()
    dr = data["deep_research"]
    assert len(dr["missions"]) == 12
    assert dr["verdict"]["verdict"]  # المرحلة ١ الحتمية تعمل دوماً
    assert dr["report"]["report"] is None  # بلا مفتاح => لا تقرير مختلَق


def test_full_mocked_run_reaches_stage2_and_writes_report():
    def fake_call_tools(system, messages, tools=None, max_tokens=1600,
                        model=None, timeout=None):
        return {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": json.dumps(
                {"findings": [], "gaps": [], "summary": "ok"})}]}

    def fake_call(system, user, max_tokens=1600, model=None, timeout=None):
        return json.dumps({"verdict": "WATCH", "confidence": 0.5,
                           "reasoning": "ok"})

    db = os.path.join(tempfile.mkdtemp(), "silk.db")
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test",
                                 "SILK_API_KEY": "secret"}), \
         patch("silk_llm_runtime._call_tools", side_effect=fake_call_tools), \
         patch("silk_synthesis._call", side_effect=fake_call), \
         patch("silk_ai_judge._call", side_effect=fake_call), \
         patch("silk_storage._db_path", return_value=db):
        r = _client().post(
            "/research", headers={"X-API-Key": "secret"},
            json={"product": "تمور", "market": "Nigeria", "hs_code": "080410",
                 "persist": True})

    assert r.status_code == 200
    data = r.json()
    dr = data["deep_research"]
    assert dr["verdict"]["ai"]["verdict"] == "WATCH"
    assert dr["report"]["report"]
    assert data.get("analysis_id") is not None
    assert data["view"]  # القالب الموحّد يُبنى بلا استثناء


def test_request_model_has_no_paid_fields():
    import inspect
    import api

    src = inspect.getsource(api.create_app)
    # فحص خفيف: نموذج ResearchRequest لا يذكر أياً من حقول التعميق المدفوعة.
    idx = src.find("class ResearchRequest")
    assert idx != -1
    body = src[idx:idx + 800]
    for paid_field in ("with_volza", "with_explee", "with_localprice",
                       "own_price"):
        assert paid_field not in body


def test_hs_resolved_automatically_when_omitted():
    with patch("requests.get", side_effect=OSError("network disabled")):
        r = _client().post("/research", json={
            "product": "تمور", "market": "Nigeria", "persist": False})
    assert r.status_code == 200
    data = r.json()
    # التمور رمزها الحقيقي 080410 في بذرة سِلك — يُحلّ تلقائياً بلا hs_code صريح.
    assert data["hs_code"] == "080410"
