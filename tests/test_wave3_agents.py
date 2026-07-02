"""اختبارات الموجة ٣ — hermetic wave-3 tests: the four selective agents.

كل وكيل جديد يولد على BaseAgent وباختبار هيرمتيكي من يومه الأول (قاعدة
الخطة). لا شبكة، لا مفاتيح — value=None موسوم أو مرجع ثابت من القرص.
Run:  python3 -m pytest tests/ -q
"""
import contextlib
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@contextlib.contextmanager
def _block_network():
    """اقطع الشبكة — hermetic guard (same pattern as test_smoke)."""
    real = socket.socket

    def _no_net(*a, **k):  # noqa: ANN002, ANN003
        raise OSError("network disabled for hermetic test")

    socket.socket = _no_net
    try:
        yield
    finally:
        socket.socket = real


def test_web_candidate_agents_keyless_no_fabrication():
    # الوكلاء الثلاثة (منافسون/قنوات/مستوردون): keyless => فشل موسوم، لا اختلاق.
    from silk_competitors_agent import NamedCompetitorsAgent
    from silk_channels_agent import DistributionChannelsAgent
    from silk_importers_agent import ImportersAgent

    os.environ.pop("SEARCH_API_KEY", None)
    with _block_network():
        for agent in (NamedCompetitorsAgent(), DistributionChannelsAgent(),
                      ImportersAgent()):
            rep = agent.run({"product": "dates", "market": "Germany"})
            assert rep.failed is True
            dp = rep.findings[0]
            assert dp.value is None and dp.confidence == 0.0
            assert agent.PAID is False        # مجاني — لا يتطلب /deepen


def test_web_candidate_agents_tag_results_as_unverified():
    # عند وجود نتائج: تُوسم صراحةً كمرشحات غير مُتحقَّق منها بثقة 0.4.
    from unittest.mock import patch
    from silk_data_layer import DataPoint
    import silk_competitors_agent as comp

    fake = [DataPoint({"title": "Top 10 date brands", "snippet": "…",
                       "link": "https://example.com"}, "Web Search (Serper)",
                      0.5, "organic result")]
    with patch.object(comp, "web_search", return_value=fake):
        rep = comp.NamedCompetitorsAgent().run({"product": "dates",
                                                "market": "Germany"})
    assert rep.failed is False
    dp = rep.findings[0]
    assert dp.confidence == 0.4                      # ثقة مرشح، لا حقيقة
    assert "غير مُتحقَّق" in dp.note                  # الصدق في الوسم


def test_channels_agent_two_lenses():
    # وكيل القنوات يسأل بقناتين (فعلي/رقمي) ويسم كل نتيجة بعدستها.
    from unittest.mock import patch
    from silk_data_layer import DataPoint
    import silk_channels_agent as ch

    fake = [DataPoint({"title": "Carrefour UAE", "snippet": "…", "link": "x"},
                      "Web Search (Serper)", 0.5, "organic result")]
    with patch.object(ch, "web_search", return_value=list(fake)) as ws:
        rep = ch.DistributionChannelsAgent().run({"product": "dates",
                                                  "market": "UAE"})
    assert ws.call_count == 2                        # عدستان = استعلامان
    lenses = {dp.value["channel_type"] for dp in rep.findings}
    assert lenses == {"physical", "digital"}


def test_requirements_agent_gcc_dual_direction_offline():
    # سوق خليجي (ARE) × منتج غذائي: بنود دخول موسومة + بنود خروج سعودية — بلا شبكة.
    from silk_requirements_agent import RequirementsAgent

    with _block_network():                            # يثبت أنه مرجع قرص صرف
        rep = RequirementsAgent().run({"market_iso3": "ARE",
                                       "hs_code": "080410"})
    assert rep.failed is False
    entry = [dp for dp in rep.findings
             if dp.value and dp.value["direction"] == "entry"]
    exit_items = [dp for dp in rep.findings
                  if dp.value and dp.value["direction"] == "exit"]
    assert entry and exit_items                       # الاتجاهان معاً (§12.6)
    for dp in entry + exit_items:
        assert dp.value["source_url"].startswith("https://")  # كل بند بمرجعه
        assert dp.value["authority"]
        assert 0.0 < dp.confidence <= 1.0
        assert dp.note                                # ملاحظة "تحقق" حاضرة
    # حلال للحوم ضمن دخول الغذائي الخليجي، وسابر ضمن دخول السعودية فقط.
    items = " ".join(dp.value["item"] for dp in entry)
    assert "حلال" in items and "سابر" not in items


def test_requirements_agent_unknown_market_honest_gap():
    # سوق غير مغطى (DEU): فجوة دخول معلنة "تحقق محلياً" + بنود الخروج تبقى.
    from silk_requirements_agent import RequirementsAgent

    rep = RequirementsAgent().run({"market_iso3": "DEU", "hs_code": "080410"})
    assert rep.failed is False
    gaps = [dp for dp in rep.findings if dp.value is None]
    assert len(gaps) == 1 and "تحقق محلياً" in gaps[0].note   # لا اختلاق اشتراطات
    exit_items = [dp for dp in rep.findings
                  if dp.value and dp.value["direction"] == "exit"]
    assert exit_items                                 # الخروج السعودي مستقل


def test_requirements_category_from_hs():
    # فصول HS الغذائية (01-24) => food، وغيرها => all.
    from silk_requirements_agent import hs_category

    assert hs_category("080410") == "food"
    assert hs_category("520100") == "all"
    assert hs_category(None) == "all"


def test_engine_wave3_layers_offline():
    # الأعلام الأربعة مفعّلة بلا شبكة/مفاتيح: مرفقة، موسومة، والنقاط لا تتغير.
    import silk_engine as engine

    os.environ.pop("SEARCH_API_KEY", None)
    with _block_network():
        res = engine.analyze("تمور", countries=[{"iso3": "ARE", "m49": "784"}],
                             year=2022, with_competitors=True,
                             with_channels=True, with_importers=True,
                             with_requirements=True)
    row = res["markets"][0]
    for key in ("competitors_named", "channels", "importers", "requirements"):
        assert key in row and row[key]                # مرفقة دوماً
    assert row["total_score"] == 0.0                  # إضافية، لا تغيّر النقاط
    # المرجع الثابت يعمل حتى بلا شبكة — بنود ARE الغذائية حاضرة بقيم حقيقية.
    assert any(dp.value for dp in row["requirements"])


def test_api_analyze_accepts_wave3_flags():
    # الأعلام الأربعة مجانية => متاحة على المسار العادي /analyze.
    import pytest
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.create_app())
    with patch("requests.get",
               side_effect=OSError("network disabled for hermetic test")), \
         patch("requests.post",
               side_effect=OSError("network disabled for hermetic test")):
        r = client.post("/analyze", json={"product": "تمور", "year": 2022,
                                          "with_requirements": True,
                                          "with_competitors": True})
    assert r.status_code == 200
    row = r.json()["markets"][0]
    assert "requirements" in row and "competitors_named" in row
