"""طبقة بيانات سِلك (v2) — derived indicators & competitor analysis.

Builds on silk_data_layer with PPP income and market-competitor ranking.
Same rule: never fabricate; failures degrade to provenance-tagged None / [].
"""
from __future__ import annotations

import logging

from silk_data_layer import (
    DataPoint,
    comtrade_trade,
    partner_name,
    primary_value,
    world_bank,
    _today,
)

log = logging.getLogger(__name__)


def ppp_per_capita(iso3: str, year: int | None = None) -> DataPoint:
    """نصيب الفرد (تعادل القوة الشرائية) — GDP per capita, PPP (current int'l $)."""
    return world_bank(iso3, "NY.GDP.PCAP.PP.CD", year)


def market_imports(hs_code: str, market_m49: object, year: int) -> dict:
    """واردات سوق ومنافسوه من نداء Comtrade واحد — ONE call: total imports + suppliers.

    يجمع الكفاءة: الردّ نفسه يحوي صفّ «العالم» (إجمالي الواردات = حجم السوق) وصفوف
    الشركاء (المنافسون). فتغني هذه الدالة عن نداءٍ ثانٍ لحجم السوق، وتقلّ نداءات
    Comtrade للنصف — أهمّ سبب لغياب النتائج بلا مفتاح (سقف المعاينة منخفض).

    Returns {"total_usd": float|None, "competitors": [DataPoint{partner,code,
    value_usd,share}]} — competitors ranked desc by value, share = % of suppliers
    total. Empty/failed -> {"total_usd": None, "competitors": []}. Never fabricates.
    """
    recs = comtrade_trade(hs_code, market_m49, year, flow="M", partner="all")
    if not recs:
        log.warning("market_imports: no data (%s -> market %s, %s)",
                    hs_code, market_m49, year)
        return {"total_usd": None, "competitors": []}
    # جمع حسب الشريك مع التقاط صفّ العالم — aggregate per partner; capture World row.
    world: float | None = None
    totals: dict[str, float] = {}
    for rec in recs:
        code = str(rec.get("partnerCode"))
        val = primary_value(rec)
        if val is None:  # سجل بلا قيمة رقمية لا يُعدّ صفراً — لا اختلاق منافس بـ0$
            continue
        if code == "0":  # World aggregate = total market imports (market size)
            world = val
            continue
        totals[code] = totals.get(code, 0.0) + val
    grand = sum(totals.values())
    # حجم السوق: صفّ العالم إن وُجد، وإلا مجموع الشركاء (لا اختلاق) — market size.
    total_usd = world if (world and world > 0) else (grand if grand > 0 else None)
    competitors: list[DataPoint] = []
    if grand > 0:
        for code, val in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
            share = round(100 * val / grand, 2)
            competitors.append(DataPoint(
                value={"partner": partner_name(code), "code": code,
                       "value_usd": val, "share": share},
                source="UN Comtrade", confidence=0.9,
                note=f"HS{hs_code} imports to {market_m49} {year}; share {share}%",
                retrieved_at=_today(),
            ))
    return {"total_usd": total_usd, "competitors": competitors}


def market_competitors(hs_code: str, market_m49: object, year: int) -> list[DataPoint]:
    """المنافسون في السوق — suppliers of an HS code to a market, ranked by value.

    Thin wrapper over market_imports() (kept for the agents). Each DataPoint.value
    is {partner, code, value_usd, share}, ranked desc; [] on failure.
    """
    return market_imports(hs_code, market_m49, year)["competitors"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk data layer v2 — demo (degrades gracefully offline)")
    dp = ppp_per_capita("SAU")
    if dp.value is None:
        print(f"  PPP/capita SAU: no data / fetch failed — {dp.note}")
    else:
        print(f"  PPP/capita SAU = {dp.value} int'l$ [{dp.source}, {dp.note}]")
    comps = market_competitors("100630", 840, 2022)  # rice into USA
    if not comps:
        print("  Competitors: no data / fetch failed")
    else:
        print(f"  Top supplier: {comps[0].value['partner']} "
              f"({comps[0].value['share']}%)")
