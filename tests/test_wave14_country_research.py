"""اختبارات الموجة ١٤ — وكيل البحث القُطري الشامل (تقرير كامل مُسنَد).

يقفل:
1. بلا مفتاح بحث => available=False، الفجوة معلنة، صفر اختلاق.
2. ببحث محقون + كلود محقون => تقرير مؤلَّف بأقسام، مصادر مرقّمة، مُسنَد.
3. ببحث محقون بلا كلود => ملفّ مصادر (available=True, synthesized=False).
4. المصادر مُزالة التكرار ومرقّمة، والبحث يغطّي كل الزوايا السبع.
Run:  python3 -m pytest tests/test_wave14_country_research.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_data_layer import DataPoint
import silk_websearch_agent as ws
import silk_ai_judge as aij
import silk_country_research as cr


def _fake_results(n_per):
    """محاكاة web_search: نتائج حقيقية الشكل مرتبطة بالاستعلام."""
    def _search(query, num=5):
        out = []
        for i in range(min(num, n_per)):
            out.append(DataPoint(
                {"title": f"{query[:20]} result {i}",
                 "snippet": "snippet " + query[:15],
                 "link": f"https://ex.com/{abs(hash(query)) % 9999}/{i}"},
                "Web Search (Serper)", 0.5, "organic", "2026-07-07"))
        return out
    return _search


def test_no_search_key_declares_gap(monkeypatch):
    # web_search بلا مفتاح يعيد DataPoint(None) => لا مصادر => فجوة معلنة.
    monkeypatch.setattr(ws, "web_search",
                        lambda q, num=5: [DataPoint(None, "Web Search", 0.0,
                                                    "requires SEARCH_API_KEY")])
    r = cr.research_country("تمور", "080410", "ARE", "الإمارات")
    assert r["available"] is False and r["sections"] == []
    assert "SEARCH_API_KEY" in r["note"]


def test_full_synthesis_path(monkeypatch):
    monkeypatch.setattr(ws, "web_search", _fake_results(3))
    monkeypatch.setattr(aij, "available", lambda: True)
    captured = {}

    def fake_call(system, user, max_tokens=1600):
        captured["user"] = user
        return ('{"sections":[{"title":"حجم السوق والطلب","text":"سوق نامٍ [1][2]."},'
                '{"title":"سلوك المستهلك والثقافة","text":"إقبال موسمي [3]."}]}')
    monkeypatch.setattr(aij, "_call", fake_call)

    r = cr.research_country("تمور", "080410", "ARE", "الإمارات")
    assert r["available"] and r["synthesized"]
    assert len(r["sections"]) == 2
    assert r["sections"][0]["title"] == "حجم السوق والطلب" and "[1]" in r["sections"][0]["text"]
    # المصادر مرقّمة ومزالة التكرار، وكل الزوايا السبع بُحثت.
    assert r["sources"] and r["sources"][0]["n"] == 1
    assert len(r["queries_run"]) == len(cr.RESEARCH_ANGLES) == 7
    # المصادر عُزلت لكلود (تنبيه الحقن).
    assert "[RAW_FINDINGS_START]" in captured["user"]


def test_search_only_dossier_without_claude(monkeypatch):
    monkeypatch.setattr(ws, "web_search", _fake_results(2))
    monkeypatch.setattr(aij, "available", lambda: False)  # لا كلود
    r = cr.research_country("تمور", "080410", "ARE", "الإمارات")
    assert r["available"] is True and r["synthesized"] is False
    assert r["sections"] == [] and r["sources"]           # ملفّ مصادر لا تأليف
    assert "ANTHROPIC_API_KEY" in r["note"]


def test_bad_claude_json_falls_back_to_dossier(monkeypatch):
    monkeypatch.setattr(ws, "web_search", _fake_results(2))
    monkeypatch.setattr(aij, "available", lambda: True)
    monkeypatch.setattr(aij, "_call", lambda s, u, max_tokens=1600: "not json at all")
    r = cr.research_country("تمور", "080410", "ARE", "الإمارات")
    assert r["available"] is True and r["synthesized"] is False and r["sources"]
