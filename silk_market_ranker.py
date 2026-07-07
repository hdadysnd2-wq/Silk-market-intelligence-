"""محرّك ترتيب الأسواق لسِلك — Silk market ranking engine.

Compares several target markets for ONE HS code and ranks them by a transparent,
weighted score. Every component carries its DataPoint provenance so a human can
audit the ranking. Real public data only (Comtrade + World Bank via the data
layer). Missing component => skipped + lowered row confidence; never fabricated.
"""
from __future__ import annotations

import datetime
import logging
from concurrent.futures import ThreadPoolExecutor

from silk_data_layer import (
    DataPoint,
    gdp_per_capita,
    population,
    _today,
)
from silk_data_layer_v2 import market_imports_cached, ppp_per_capita, market_imports

log = logging.getLogger(__name__)

_SAUDI_M49 = "682"

# أسواق سِلك المستهدفة — Silk target markets (iso3 + M49). Real codes; GCC,
# wider MENA, key African, Asian and European import markets.
COUNTRIES: list[dict] = [
    # GCC
    {"iso3": "ARE", "m49": "784"}, {"iso3": "QAT", "m49": "634"},
    {"iso3": "KWT", "m49": "414"}, {"iso3": "OMN", "m49": "512"},
    {"iso3": "BHR", "m49": "048"},
    # wider MENA
    {"iso3": "JOR", "m49": "400"}, {"iso3": "LBN", "m49": "422"},
    {"iso3": "EGY", "m49": "818"}, {"iso3": "MAR", "m49": "504"},
    {"iso3": "TUN", "m49": "788"}, {"iso3": "DZA", "m49": "012"},
    {"iso3": "IRQ", "m49": "368"}, {"iso3": "TUR", "m49": "792"},
    {"iso3": "YEM", "m49": "887"},
    # Africa
    {"iso3": "ZAF", "m49": "710"}, {"iso3": "NGA", "m49": "566"},
    {"iso3": "KEN", "m49": "404"}, {"iso3": "ETH", "m49": "231"},
    {"iso3": "GHA", "m49": "288"},
    # Asia
    {"iso3": "IND", "m49": "356"}, {"iso3": "PAK", "m49": "586"},
    {"iso3": "BGD", "m49": "050"}, {"iso3": "IDN", "m49": "360"},
    {"iso3": "MYS", "m49": "458"}, {"iso3": "SGP", "m49": "702"},
    {"iso3": "THA", "m49": "764"}, {"iso3": "VNM", "m49": "704"},
    {"iso3": "CHN", "m49": "156"}, {"iso3": "JPN", "m49": "392"},
    {"iso3": "KOR", "m49": "410"},
    # Europe / North America
    {"iso3": "GBR", "m49": "826"}, {"iso3": "DEU", "m49": "276"},
    {"iso3": "FRA", "m49": "250"}, {"iso3": "ITA", "m49": "380"},
    {"iso3": "ESP", "m49": "724"}, {"iso3": "NLD", "m49": "528"},
    {"iso3": "USA", "m49": "840"}, {"iso3": "CAN", "m49": "124"},
]

# أوزان المكوّنات — tunable component weights (sum ~1.0). Audit/tune here.
WEIGHTS: dict[str, float] = {
    "market_size": 0.40,      # how much the market imports of this HS
    "saudi_position": 0.20,   # Saudi already a supplier? higher = warmer entry
    "demand_capacity": 0.25,  # income (PPP) x population
    "competition": 0.15,      # fragmented suppliers => easier => higher
}


def _market_size_component(total_usd: object, hs_code: str, m49: str,
                           year: int, xval: str = "") -> DataPoint:
    """حجم السوق — total imports of this HS by the market, derived from the SAME
    Comtrade call as the competitors (no extra request). None => no data."""
    if total_usd is None:
        return DataPoint(None, "UN Comtrade", 0.0,
                         note=f"no import total HS{hs_code} -> {m49} {year}",
                         retrieved_at=_today())
    conf = 0.7 if xval else 0.9      # تباين مصادر >20% => ثقة أدنى (Stage 2A)
    return DataPoint(float(total_usd), "UN Comtrade", conf,
                     note=f"total imports HS{hs_code} {year} (USD){xval}",
                     retrieved_at=_today())


def _competitor_list(comps: list[DataPoint], top: int = 5) -> list[dict]:
    """قائمة المنافسين للوحة — top suppliers (name + share + value) for the UI.

    `comps` is ranked desc; returns plain dicts (never fabricated; [] if none)."""
    out: list[dict] = []
    for c in comps[:top]:
        if c.value:
            out.append({"partner": c.value.get("partner"),
                        "code": c.value.get("code"),
                        "value_usd": c.value.get("value_usd"),
                        "share": c.value.get("share")})
    return out


def _saudi_position_component(comps: list[DataPoint]) -> DataPoint:
    """موقع السعودية — Saudi supplier share of this market (0 if absent)."""
    if not comps:
        return DataPoint(None, "UN Comtrade", 0.0,
                         note="no competitor data", retrieved_at=_today())
    sa = next((c for c in comps if c.value and c.value.get("code") == _SAUDI_M49),
              None)
    share = sa.value["share"] if sa else 0.0
    note = (f"Saudi share {share}%" if sa
            else "Saudi not yet a supplier (share 0%)")
    return DataPoint(share, "UN Comtrade", 0.9, note=note, retrieved_at=_today())


def _income_dp(iso3: str, year: int) -> DataPoint:
    """الدخل مرّة واحدة — fetch income ONCE (PPP, GDP fallback).

    يُعاد استعماله لمكوّن طاقة الطلب ولحقل income_ppp باللوحة معاً — كان يُجلب
    مرّتين (Q4)، فيُهدر نداءً/قراءة ذاكرة لكل سوق. Fetched once, reused for both.
    """
    inc = ppp_per_capita(iso3, year)
    if inc.value is None:
        inc = gdp_per_capita(iso3, year)
    return inc


def _demand_capacity_component(inc: DataPoint, iso3: str, year: int) -> DataPoint:
    """طاقة الطلب — القوة الشرائية للفرد من دخل مُجلَب مسبقاً (ثراء السوق، لا حجمه).

    purchasing power PER CAPITA (PPP, GDP/cap fallback), computed from the income
    DataPoint already fetched by _income_dp (no second fetch). NOT multiplied by
    population — that made the largest economies dominate every product.
    """
    if inc.value is None:
        return DataPoint(None, "World Bank", 0.0,
                         note=f"no income data for {iso3} {year}",
                         retrieved_at=_today())
    return DataPoint(float(inc.value), "World Bank", 0.9,
                     note=inc.note, retrieved_at=_today())


# تراجُع سنويّ معلن — بيانات التجارة السنوية تتأخّر سنة–سنتين، فالسنةُ المطلوبة قد
# تكون غير منشورة بعد. نبدأ من min(المطلوبة، السنة الحالية−1) ونتراجع حتى نجد أحدث
# سنةٍ فيها بيانات فعلية (بدل انهيار التحليل إلى 0% لسنةٍ لم تُنشر). لا اختلاق:
# السنة الفعلية تُعلَن في ملاحظة كل مكوّن؛ الفشل الكامل يبقى فجوةً معلنة كالمعتاد.
_MAX_YEAR_FALLBACK = 4


def _imports_with_fallback(hs_code: str, m49: str, iso3: str,
                           year: int) -> tuple[dict, int, bool]:
    """استيراد السوق مع تراجعٍ سنويٍّ معلن — most-recent-year-with-data resolver.

    يعيد (mi، السنة_الفعلية، هل_تراجَعنا). يبدأ من min(المطلوبة، الحالية−1) لتفادي
    استعلام سنةٍ لم تُنشر بعد، ثم يتراجع حتى _MAX_YEAR_FALLBACK. آخرُ محاولةٍ فارغة
    تُعاد بالسنة المطلوبة (فجوة معلنة). Never fabricates — just picks the newest
    published year within the window.
    """
    start = min(year, datetime.date.today().year - 1)
    mi = {"total_usd": None, "competitors": []}
    for back in range(_MAX_YEAR_FALLBACK + 1):
        y = start - back
        mi = market_imports_cached(hs_code, m49, iso3, y, live=market_imports)
        if mi.get("total_usd") is not None or mi.get("competitors"):
            return mi, y, (y != year)
    return mi, year, False


def _gather_row(hs_code: str, c: dict, year: int) -> dict:
    """اجمع مكوّنات سوق واحد — all fetches for ONE market (runs in a worker thread).

    مستقل تماماً عن بقية الأسواق (لا حالة مشتركة قابلة للتحوّر)، فيُوزَّع على
    الخيوط بأمان. الدخل يُجلب مرّة واحدة (Q4) ويُعاد استعماله. السنةُ الفعلية
    تُحلّ بتراجعٍ معلن عند غياب بيانات السنة المطلوبة (التجارة تتأخّر سنة–سنتين).
    """
    iso3, m49 = c["iso3"], c["m49"]
    # نداء واحد لكل سوق عبر مخزن الحقائق أولاً (M2) + تراجُع سنويّ معلن عند الغياب.
    mi, eff_year, fell_back = _imports_with_fallback(hs_code, m49, iso3, year)
    comps = mi["competitors"]
    inc = _income_dp(iso3, eff_year)             # الدخل مرّة واحدة (Q4)
    pop = population(iso3, eff_year)
    fb = (f" | بيانات {eff_year} — أحدث سنة منشورة ({year} لم تُنشر بعد)"
          if fell_back else "")
    comp_dps = {
        "market_size": _market_size_component(mi["total_usd"], hs_code, m49,
                                              eff_year,
                                              xval=mi.get("xval_note", "") + fb),
        "saudi_position": _saudi_position_component(comps),
        "demand_capacity": _demand_capacity_component(inc, iso3, eff_year),
        "competition": _competition_component(comps),
    }
    return {
        "iso3": iso3, "m49": m49, "components": comp_dps,
        "income_ppp": inc.value,                 # يُعاد استعمال نفس الجلب
        "population": pop.value,
        "year_used": eff_year, "year_fell_back": fell_back,
        "competitors": _competitor_list(comps),
        "top_competitor": _top_competitor(comps),
    }


def _top_competitor(comps: list[DataPoint]) -> str | None:
    """أكبر مورّد غير سعودي — name of the largest NON-Saudi supplier, else None.

    `comps` is already ranked descending by value_usd, so the first competitor
    whose code != Saudi M49 is the largest non-Saudi supplier. Never fabricates.
    """
    for c in comps:
        if c.value and c.value.get("code") != _SAUDI_M49:
            return c.value.get("partner")
    return None


def _competition_component(comps: list[DataPoint]) -> DataPoint:
    """المنافسة — Herfindahl concentration of suppliers (lower share top = easier)."""
    if not comps:
        return DataPoint(None, "UN Comtrade", 0.0,
                         note="no competitor data", retrieved_at=_today())
    # HHI من الحصص (0..1) — sum of squared shares; 1 = monopoly, ~0 = fragmented.
    hhi = sum((c.value["share"] / 100.0) ** 2 for c in comps if c.value)
    return DataPoint(round(hhi, 4), "UN Comtrade", 0.9,
                     note=f"supplier HHI over {len(comps)} suppliers",
                     retrieved_at=_today())


def _normalize(raw: dict[str, float], value: float) -> float:
    """طبّع 0..1 — min-max normalize one component across all rows."""
    vals = [v for v in raw.values() if v is not None]
    if not vals:
        return 0.0
    lo, hi = min(vals), max(vals)
    if hi == lo:
        return 1.0
    return (value - lo) / (hi - lo)


def rank_markets(hs_code: str, countries: list[dict] | None = None,
                 year: int = 2022, max_workers: int = 16) -> list[dict]:
    """رتّب الأسواق لرمز HS — rank markets best-first by a weighted, audited score.

    Each result: {country, iso3, m49, total_score, confidence, components}
    where components[name] = the component DataPoint (provenance + raw value).
    Missing components are skipped and lower that row's confidence; weights are
    renormalized over present components so rows stay comparable. Never fabricates.

    P1: الأسواق تُجمَع **بالتوازي** عبر ThreadPoolExecutor (I/O شبكي حاجب)، وكل
    سوق مستقل فالتطبيع يقع بعد اكتمال الجمع؛ `ex.map` يحفظ الترتيب فالنتيجة
    مطابقة للتسلسلي. الجلسة المجمّعة (silk_data_layer._session) تعيد استعمال
    الاتصالات عبر الخيوط. Markets are gathered concurrently; identical output.
    """
    countries = countries or COUNTRIES

    # 1) اجمع المكوّنات الخام لكل دولة بالتوازي — gather raw components concurrently.
    workers = max(1, min(max_workers, len(countries)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        rows: list[dict] = list(
            ex.map(lambda c: _gather_row(hs_code, c, year), countries))

    # 2) جداول القيم الخام لكل مكوّن عبر الدول — per-component raw value tables.
    raw_tables: dict[str, dict[str, float]] = {k: {} for k in WEIGHTS}
    for row in rows:
        for name, dp in row["components"].items():
            if dp.value is not None:
                raw_tables[name][row["iso3"]] = float(dp.value)

    # 3) طبّع، اقلب المنافسة (أقل تركّز = أفضل)، ثم وزّن — normalize + weight.
    out: list[dict] = []
    for row in rows:
        iso3 = row["iso3"]
        wsum, score, present = 0.0, 0.0, 0
        for name, w in WEIGHTS.items():
            dp = row["components"][name]
            if dp.value is None:
                continue  # مفقود => يُتخطى، لا قيمة وهمية — skip, no fake value
            norm = _normalize(raw_tables[name], float(dp.value))
            if name == "competition":
                norm = 1.0 - norm  # تركّز أعلى = أصعب — invert: less concentrated better
            score += w * norm
            wsum += w
            present += 1
        # وزّن على المكوّنات الموجودة فقط — renormalize over present weights.
        total = round(score / wsum, 4) if wsum else 0.0
        # ثقة الصف تنخفض بنقص المكوّنات — confidence drops with missing components.
        confidence = round(present / len(WEIGHTS), 2)
        out.append({
            "country": _name(iso3, row["m49"]),
            "iso3": iso3, "m49": row["m49"],
            "total_score": total, "confidence": confidence,
            "components": row["components"],
            "income_ppp": row["income_ppp"],
            "population": row["population"],
            "year_used": row.get("year_used"),
            "year_fell_back": row.get("year_fell_back", False),
            "competitors": row["competitors"],
            "top_competitor": row["top_competitor"],
        })

    out.sort(key=lambda r: (r["total_score"], r["confidence"]), reverse=True)
    return out


def _name(iso3: str, m49: str) -> str:
    """اسم الدولة — friendly name via the data layer's partner map."""
    from silk_data_layer import partner_name
    n = partner_name(m49)
    return n if n != str(m49) else iso3


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk market ranker — demo (degrades gracefully offline)")
    sample = [{"iso3": "ARE", "m49": "784"}, {"iso3": "USA", "m49": "840"}]
    ranked = rank_markets("100630", countries=sample, year=2022)  # rice
    for i, r in enumerate(ranked, 1):
        present = sum(1 for dp in r["components"].values() if dp.value is not None)
        print(f"  {i}. {r['country']:<22} score={r['total_score']:.3f} "
              f"conf={r['confidence']} ({present}/{len(WEIGHTS)} components present)")
    if all(c.value is None for r in ranked for c in r["components"].values()):
        print("  (offline: all components missing -> scores 0, rank still ran)")
