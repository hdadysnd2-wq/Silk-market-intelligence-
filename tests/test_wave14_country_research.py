"""اختبارات الموجة ١٤ — وكلاء المجالات + طبقة القرار (استخراج منظّم، لا روابط).

يقفل:
1. بلا مفتاح بحث => available=False، فجوة معلنة، صفر اختلاق.
2. بحث+قراءة+كلود محقونين => لكل مجال ملخّص/نقاط/جدول، وطبقة قرار تحكم.
3. الاستخراج ينقل المعلومة نفسها (نقاط + جدول)، لا مجرّد روابط.
4. بلا كلود => قرأ الصفحات لكن لا استخراج (synthesized=False) — يُعلن.
Run:  python3 -m pytest tests/test_wave14_country_research.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_data_layer import DataPoint
import silk_websearch_agent as ws
import silk_ai_judge as aij
import silk_country_research as cr


def _fake_search(n=4):
    def _s(query, num=5):
        return [DataPoint({"title": f"{query[:16]} {i}", "snippet": "snip",
                           "link": f"https://ex.com/{abs(hash(query))%999}/{i}"},
                          "Web Search (Serper)", 0.5, "organic", "2026") for i in range(min(num, n))]
    return _s


def test_no_search_key_declares_gap(monkeypatch):
    monkeypatch.setattr(ws, "web_search",
                        lambda q, num=5: [DataPoint(None, "Web Search", 0.0, "requires SEARCH_API_KEY")])
    r = cr.research_country("تمور", "080410", "ARE", "الإمارات")
    assert r["available"] is False and not r["synthesized"]
    assert "SEARCH_API_KEY" in r["note"]


def test_per_field_extraction_and_decision(monkeypatch):
    monkeypatch.setattr(ws, "web_search", _fake_search(3))
    monkeypatch.setattr(cr, "_fetch_page_text", lambda url: "محتوى صفحة فيه سعر 118 درهم لعلامة Bateel")
    monkeypatch.setattr(aij, "available", lambda: True)

    def fake_call(system, user, max_tokens=1600):
        if "طبقة القرار" in system:      # decision layer
            return ('{"verdict":"GO","why":"طلب متنامٍ وأسعار فاخرة [1]",'
                    '"recommendations":["ابدأ بقناة الفخامة","سعّر عند 110-120 درهم"],'
                    '"risks":["تذبذب الأسعار","إعادة التصدير"]}')
        # field extraction: نقاط + جدول
        return ('{"summary":"أسعار الفخامة 90-130 درهم [1][2].","facts":'
                '["Bateel 400غ = 118 درهم في نون [1]","Al Foah 500غ = 74 درهم [2]"],'
                '"table":{"columns":["المنتج","السعر","المتجر"],'
                '"rows":[["Bateel 400غ","118 درهم","نون [1]"],["Al Foah","74 درهم","أمازون [2]"]]}}')
    monkeypatch.setattr(aij, "_call", fake_call)

    r = cr.research_country("تمور", "080410", "ARE", "الإمارات")
    assert r["available"] and r["synthesized"]
    assert len(r["fields"]) == 7
    f0 = r["fields"][0]
    assert f0["facts"] and "[1]" in f0["facts"][0]            # نقطة مُسنَدة
    assert f0["table"] and f0["table"]["rows"][0][0] == "Bateel 400غ"  # جدول بيانات
    # طبقة القرار قرّرت من مخرجات الوكلاء
    assert r["decision"]["verdict"] == "GO"
    assert r["decision"]["recommendations"] and r["decision"]["risks"]


def test_pages_read_but_no_claude_is_declared(monkeypatch):
    monkeypatch.setattr(ws, "web_search", _fake_search(2))
    monkeypatch.setattr(cr, "_fetch_page_text", lambda url: "some content")
    monkeypatch.setattr(aij, "available", lambda: False)   # لا استخراج
    r = cr.research_country("تمور", "080410", "ARE", "الإمارات")
    assert r["available"] is True and r["synthesized"] is False
    assert r["decision"] is None and "ANTHROPIC_API_KEY" in r["note"]
    assert all(f["sources"] for f in r["fields"])          # الصفحات جُمعت فعلاً


def test_fetch_page_text_graceful_offline(monkeypatch):
    import silk_country_research as m
    # فشل الجلب => None لا استثناء (لا اختلاق محتوى).
    monkeypatch.setattr("requests.get", lambda *a, **k: (_ for _ in ()).throw(OSError("blocked")))
    assert m._fetch_page_text("https://x.com") is None
