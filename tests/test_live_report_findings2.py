"""اختبارات من مراجعة ثانية لتقرير حي (عصائر → اليمن، Railway) — إصلاحان
حقيقيان وُجدا وأُصلحا:

1) محلات عصير/مطاعم كانت تُعرَض كأنها «مستوردون/موزّعون» بلا تمييز — بلاغ
   مالك حرفي: "يستخدم محلات العصير العادية ويقول انهم مستوردين". تصنيف
   Google Places الفعلي (types) كان يُهمَل تماماً؛ الآن يُستخرَج ويُستهلَك
   لإعلان «يبدو محل تجزئة/مطعماً» بدل الادّعاء الضمني بأنه موزّع بالجملة.
2) سنة البيانات كانت تعلق على أرقام ثابتة تتقادم (2022 في المحرك، 2023
   افتراضي الواجهة رغم توفّر 2024 في القائمة نفسها) — بلاغ مالك: "البيانات
   قديمة يمديك الى 2024". الافتراضات الآن محسوبة من تاريخ اليوم.
"""
import datetime
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from silk_data_layer import DataPoint, _today  # noqa: E402


# ── ١) تصنيف نوع العمل من Google Places ──────────────────────────────────────

def test_find_places_extracts_google_types_field():
    import silk_maps_agent as M
    payload = {"status": "OK", "results": [
        {"name": "City Juice Restaurant", "rating": 4.1,
         "formatted_address": "Sanaa", "types": ["restaurant", "food",
                                                  "point_of_interest"]},
        {"name": "Yemen Trading Co", "rating": 4.5,
         "formatted_address": "Sanaa", "types": ["point_of_interest",
                                                  "establishment"]}]}
    resp = mock.MagicMock(status_code=200)
    resp.raise_for_status.return_value = None
    resp.json.return_value = payload
    with mock.patch.dict(os.environ, {"GOOGLE_MAPS_API_KEY": "k"}), \
         mock.patch("requests.get", return_value=resp):
        found = M.find_places("juice Yemen")
    by_name = {f.value["name"]: f.value["types"] for f in found}
    assert by_name["City Juice Restaurant"] == ["restaurant", "food",
                                                "point_of_interest"]
    assert by_name["Yemen Trading Co"] == ["point_of_interest", "establishment"]


def test_business_hint_flags_restaurant_not_wholesale_distributor():
    import silk_research as R
    assert R._business_hint(["restaurant", "food"]) == "retail_or_food_service"
    assert R._business_hint(["cafe"]) == "retail_or_food_service"
    assert R._business_hint(["point_of_interest", "establishment"]) is None
    assert R._business_hint([]) is None
    assert R._business_hint(None) is None


def test_entities_and_references_excludes_retail_food_service():
    """بلاغ المالك «كل البيانات محلات تجزئة»: محل التجزئة/المطعم يُستبعَد كلياً
    من قائمة المرشّحين (لا يُعرض كموزّع/مستورد)، ويُعاد عدد المُستبعَد ليُعلَن؛
    ويبقى الكيان الحقيقي فقط. Retail is excluded, not merely flagged."""
    import silk_research as R
    juice_shop = DataPoint({"name": "City Juice Restaurant", "rating": 4.1,
                            "address": "Sanaa", "types": ["restaurant"]},
                           "Google Maps", 0.7, "place", _today())
    trading_co = DataPoint({"name": "Yemen Trading Co", "rating": 4.5,
                           "address": "Sanaa", "types": ["establishment"]},
                          "Google Maps", 0.7, "place", _today())
    with mock.patch("silk_maps_agent.find_places",
                    return_value=[juice_shop, trading_co]), \
         mock.patch("silk_websearch_agent.web_search", return_value=[]):
        out, _refs, dropped = R._entities_and_references(["q"], "mq")
    names = [e["name"] for e in out]
    assert "City Juice Restaurant" not in names   # محل تجزئة مُستبعَد
    assert names == ["Yemen Trading Co"]           # الكيان الحقيقي فقط باقٍ
    assert dropped == 1                            # وعددُ المُستبعَد مُعلَن
    assert out[0]["business_hint"] is None


def test_report_text_warns_on_retail_hint_never_asserts_wholesale_silently():
    from silk_reports import _entry_text
    shop = {"kind": "entity", "name": "City Juice Restaurant",
           "business_hint": "retail_or_food_service", "via": "Google Maps",
           "retrieved_at": _today()}
    trader = {"kind": "entity", "name": "Yemen Trading Co",
             "business_hint": None, "via": "Google Maps",
             "retrieved_at": _today()}
    shop_line, trader_line = _entry_text(shop), _entry_text(trader)
    assert "⚠" in shop_line and "محل تجزئة" in shop_line
    assert "⚠" not in trader_line


def test_ui_renders_retail_hint_warning():
    html = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "web", "index.html"),
        encoding="utf-8").read()
    assert "business_hint" in html and "retail_or_food_service" in html
    assert "retailHint" in html


# ── ٢) سنة البيانات الافتراضية محسوبة لا ثابتة ───────────────────────────────

def test_engine_default_year_tracks_current_date_not_hardcoded():
    import silk_engine
    expected = datetime.date.today().year - 1
    assert silk_engine._default_year() == expected
    assert silk_engine._default_year() != 2022   # لم يعد الرقم القديم العالق


def test_tariffs_agent_default_year_computed_not_hardcoded():
    import silk_tariffs_agent as T
    expected = datetime.date.today().year - 3
    assert T._default_year() == expected
    assert T._default_year() != 2021


def test_ui_year_dropdown_defaults_computed_from_today():
    html = open(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "web", "index.html"),
        encoding="utf-8").read()
    assert "new Date().getFullYear()" in html
    assert "yearTo:CUR_Y-1" in html or "yearTo: CUR_Y - 1" in html
    # لا قائمة سنوات ثابتة عالقة على 2024 كأقصى قيمة بعد الآن.
    assert "[2024,2023,2022,2021,2020,2019,2018,2017]" not in html
