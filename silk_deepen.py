"""تعميق التحليل لسِلك — Silk paid "deepen" layer (المجموعة و · Group F, V3).

طبقة متقدّمة مدفوعة **لا تُستدعى تلقائياً** في كل تحليل، بل يدوياً عبر زر «تعميق
التحليل» للأسواق الثلاثة الأعلى فقط (توفيراً للتكلفة): Google Maps (مصانع/موزّعون
بالاسم) + Volza (مستوردون من بوالص الشحن) + explee (مشترون B2B) + D&B (التحقق من
شرعية الموردين المكتشفين). كل مصدر مقيّد بمفتاحه ويتدهور بأمان إلى None بلا اختلاق.

يعيد استخدام الوكلاء الموجودين؛ يجمع أسماء الموردين المكتشفة ويمرّرها لـ D&B
للتحقق. لا أسماء ولا أرقام تُختلق (المبدأ التأسيسي).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_DEEPEN_TOP = 3  # الأسواق الأعلى فقط — only the top markets get paid deepening.

# ISO3 -> ISO2 لأهم الأسواق (لـ Maps region و D&B country) — best-effort, else None.
_ISO3_TO_ISO2 = {
    "SAU": "SA", "ARE": "AE", "QAT": "QA", "KWT": "KW", "BHR": "BH", "OMN": "OM",
    "JOR": "JO", "LBN": "LB", "EGY": "EG", "MAR": "MA", "TUN": "TN", "DZA": "DZ",
    "IRQ": "IQ", "TUR": "TR", "YEM": "YE", "ZAF": "ZA", "NGA": "NG", "KEN": "KE",
    "ETH": "ET", "GHA": "GH", "IND": "IN", "PAK": "PK", "BGD": "BD", "IDN": "ID",
    "MYS": "MY", "SGP": "SG", "THA": "TH", "VNM": "VN", "CHN": "CN", "JPN": "JP",
    "KOR": "KR", "GBR": "GB", "DEU": "DE", "FRA": "FR", "ITA": "IT", "ESP": "ES",
    "NLD": "NL", "USA": "US", "CAN": "CA",
}


def _names_from(findings: list) -> list[str]:
    """استخرج أسماء الموردين المكتشفة — supplier names from maps/volza/explee findings."""
    out: list[str] = []
    for f in findings or []:
        v = getattr(f, "value", None) if not isinstance(f, dict) else f.get("value")
        if v is None:
            continue
        if isinstance(v, str):
            name = v
        elif isinstance(v, dict):
            name = v.get("name") or v.get("importer") or v.get("company") or ""
        else:
            name = ""
        name = str(name).strip()
        if name and name not in out:
            out.append(name)
    return out


def deepen(result: dict, top: int = _DEEPEN_TOP) -> dict:
    """عمّق أعلى الأسواق — run the PAID deepen agents on the top markets only.

    Returns {product, hs_code, markets:[{iso3, country, maps, volza, explee,
    dnb}], note}. Every source is key-gated and degrades to [] / None offline
    (never fabricated). Reuses the existing agents; D&B verifies the union of
    supplier names discovered by Maps/Volza/explee.
    """
    if not result or not result.get("classified"):
        return {"product": result.get("product") if result else None,
                "hs_code": None, "markets": [],
                "note": "لا تحليل مصنّف للتعميق — nothing classified to deepen."}

    from silk_maps_agent import MapsAgent            # lazy: optional paid layers
    from silk_volza_agent import VolzaAgent
    from silk_explee_agent import ExpleeAgent
    from silk_dnb_agent import DnbAgent
    from silk_bestsellers_agent import BestsellersAgent   # PAID Apify — deepen-only
    from silk_localprice_agent import LocalPriceAgent     # PAID SerpApi — deepen-only

    product = result.get("product") or ""
    hs_code = result.get("hs_code")
    maps_a, volza_a, explee_a, dnb_a = (MapsAgent(), VolzaAgent(),
                                        ExpleeAgent(), DnbAgent())
    best_a, price_a = BestsellersAgent(), LocalPriceAgent()
    out_markets = []
    for row in (result.get("markets") or [])[: max(1, top)]:
        iso3 = row.get("iso3")
        country = row.get("country") or iso3 or ""
        iso2 = _ISO3_TO_ISO2.get(iso3)
        entry = {"iso3": iso3, "country": country}
        try:
            entry["maps"] = maps_a.run({"query": f"{product} {country}".strip(),
                                        "region": iso2}).findings
        except Exception as e:  # noqa: BLE001 — deepen must not crash
            log.warning("deepen maps failed for %s: %s", iso3, e)
            entry["maps"] = []
        try:
            entry["volza"] = volza_a.run({"hs_code": hs_code, "market": row.get("m49"),
                                          "partner": "SAU"}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("deepen volza failed for %s: %s", iso3, e)
            entry["volza"] = []
        try:
            entry["explee"] = explee_a.run({"query": product, "market": iso3 or ""}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("deepen explee failed for %s: %s", iso3, e)
            entry["explee"] = []
        try:  # الأكثر مبيعاً (Apify مدفوع) — deepen-only best-sellers
            entry["bestsellers"] = best_a.run({"product": product, "market": iso2 or iso3 or ""}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("deepen bestsellers failed for %s: %s", iso3, e)
            entry["bestsellers"] = []
        try:  # أسعار التجزئة المُهيكلة (SerpApi مدفوع) — deepen-only structured prices
            entry["retail_prices"] = price_a.run(
                {"query": f"{product} {country}".strip(), "market": iso2}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("deepen retail_prices failed for %s: %s", iso3, e)
            entry["retail_prices"] = []
        # D&B: تحقّق من اتحاد الأسماء المكتشفة — verify the union of discovered names.
        names = _names_from(entry["maps"]) + _names_from(entry["volza"]) + _names_from(entry["explee"])
        try:
            entry["dnb"] = dnb_a.run({"names": names, "country": iso2}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("deepen dnb failed for %s: %s", iso3, e)
            entry["dnb"] = []
        out_markets.append(entry)

    return {
        "product": product, "hs_code": hs_code, "markets": out_markets,
        "note": ("طبقة تعميق مدفوعة على أعلى الأسواق؛ كل مصدر مقيّد بمفتاحه ويتدهور "
                 "بأمان بلا اختلاق. PAID deepen on top markets; key-gated, no fabrication."),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk deepen — PAID Group-F layer; degrades gracefully without keys "
          "(no fabricated companies/DUNS)")
    demo = {"classified": True, "product": "تمور", "hs_code": "080410",
            "markets": [{"iso3": "MAR", "m49": "504", "country": "المغرب"}]}
    out = deepen(demo, top=1)
    m = out["markets"][0]
    print("  market:", m["country"],
          "| maps:", len(m["maps"]), "volza:", len(m["volza"]),
          "explee:", len(m["explee"]), "dnb:", len(m["dnb"]))
