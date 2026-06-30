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
    world_bank,
    _today,
)

log = logging.getLogger(__name__)


def ppp_per_capita(iso3: str, year: int | None = None) -> DataPoint:
    """نصيب الفرد (تعادل القوة الشرائية) — GDP per capita, PPP (current int'l $)."""
    return world_bank(iso3, "NY.GDP.PCAP.PP.CD", year)


def market_competitors(hs_code: str, market_m49: object, year: int) -> list[DataPoint]:
    """المنافسون في السوق — suppliers of an HS code to a market, ranked by value.

    Each DataPoint.value is a dict {partner, code, value_usd, share}; ranked
    descending by value_usd, share = % of total imports. [] on failure.
    """
    recs = comtrade_trade(hs_code, market_m49, year, flow="M", partner="all")
    if not recs:
        log.warning("market_competitors: no data (%s -> market %s, %s)",
                    hs_code, market_m49, year)
        return []
    # جمع حسب الشريك — aggregate per partner, drop the World total row.
    totals: dict[str, float] = {}
    for rec in recs:
        code = str(rec.get("partnerCode"))
        if code == "0":  # World aggregate, not a competitor
            continue
        val = rec.get("primaryValue") or 0
        totals[code] = totals.get(code, 0.0) + float(val)
    grand = sum(totals.values())
    if grand <= 0:
        log.warning("market_competitors: zero total imports (%s, market %s, %s)",
                    hs_code, market_m49, year)
        return []
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    out: list[DataPoint] = []
    for code, val in ranked:
        share = round(100 * val / grand, 2)
        out.append(DataPoint(
            value={"partner": partner_name(code), "code": code,
                   "value_usd": val, "share": share},
            source="UN Comtrade", confidence=0.9,
            note=f"HS{hs_code} imports to {market_m49} {year}; share {share}%",
            retrieved_at=_today(),
        ))
    return out


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
