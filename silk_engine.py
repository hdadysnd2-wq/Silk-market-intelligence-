"""المحرّك الكامل لمنصّة سِلك لذكاء الأسواق — Silk Market Intelligence engine.

End-to-end pipeline, real public data only (founding principle: never fabricate):
    product name -> HS6 code (silk_hs_resolver)
                 -> ranked target markets (silk_market_ranker)
                 -> top markets enriched with agents + jury (silk_agents).

Every output is PRELIMINARY and carries provenance. Network failures degrade
gracefully (no data / fetch failed), never crash, never invent numbers.
"""
from __future__ import annotations

import datetime
import logging

from silk_hs_resolver import resolve
from silk_market_ranker import rank_markets, COUNTRIES, WEIGHTS
from silk_agents import ResearchManager, JuryCommittee

log = logging.getLogger(__name__)

_DEFAULT_YEAR = 2022      # آخر سنة كاملة موثوقة في Comtrade — stable full year
_ENRICH_TOP = 3           # كم سوقًا نُثريه بالوكلاء — top markets to deep-enrich


def _today() -> str:
    """تاريخ اليوم — ISO date string."""
    return datetime.date.today().isoformat()


def analyze(product_name: str, countries: list[dict] | None = None,
            year: int | None = None) -> dict:
    """حلّل منتجًا عبر الأسواق — full preliminary market analysis for one product.

    Returns an EngineResult dict:
        {product, hs_code, hs_confidence, hs_note, year, preliminary,
         classified (bool), markets: [...], note}
    Each market row adds a one-line `recommendation`; the top markets also carry
    an agents `jury` verdict. If the product cannot be classified, returns
    classified=False with markets=[] — it never guesses an HS code.
    """
    year = year or _DEFAULT_YEAR
    countries = countries or COUNTRIES

    # 1) صنّف المنتج إلى رمز HS — resolve product -> HS6 (carry its confidence).
    hs = resolve(product_name)
    if hs.value is None:
        return {
            "product": product_name, "hs_code": None, "hs_confidence": 0.0,
            "hs_note": hs.note, "year": year, "preliminary": True,
            "classified": False, "markets": [],
            "note": "تعذّر تصنيف المنتج إلى رمز HS — could not classify product; "
                    "no HS code guessed.",
        }

    # 2) رتّب الأسواق المرشّحة لهذا الرمز — rank candidate markets.
    ranked = rank_markets(hs.value, countries=countries, year=year)

    # 3) أثرِ الأسواق الأعلى بالوكلاء واللجنة — enrich the top markets.
    manager = ResearchManager()
    for row in ranked[:_ENRICH_TOP]:
        task = {"hs_code": hs.value, "market_m49": row["m49"],
                "iso3": row["iso3"], "year": year}
        reports = manager.distribute(task)
        row["jury"] = JuryCommittee.evaluate(reports)

    # 4) سطر توصية لكل سوق — one-line recommendation per market.
    for row in ranked:
        row["recommendation"] = _recommend(row)

    return {
        "product": product_name, "hs_code": hs.value,
        "hs_confidence": hs.confidence, "hs_note": hs.note,
        "year": year, "preliminary": True, "classified": True,
        "markets": ranked,
        "note": "نتيجة مبدئية مبنية على بيانات عامة حقيقية؛ النواقص معلّمة لا مُخمّنة. "
                "Preliminary, real public data only; gaps flagged, not estimated.",
    }


def _recommend(row: dict) -> str:
    """سطر توصية مبدئي — one-line preliminary recommendation for a market row."""
    country = row["country"]
    score = row.get("total_score", 0.0)
    conf = row.get("confidence", 0.0)
    present = sum(1 for dp in row["components"].values() if dp.value is not None)
    if present == 0:
        return f"{country}: لا بيانات كافية — insufficient data (preliminary)."
    jury = row.get("jury", {})
    tag = jury.get("verdict", "").split(" —")[0].strip() if jury else ""
    verdict = f" [{tag}]" if tag else ""
    return (f"{country}: score={score:.3f} conf={conf} "
            f"({present}/{len(WEIGHTS)} comps){verdict} — preliminary.")


def format_result(result: dict) -> str:
    """نسّق النتيجة للطرفية — readable terminal summary (Arabic labels ok)."""
    L = [
        "═" * 60,
        f"المنتج / Product : {result['product']}",
    ]
    if not result.get("classified"):
        L += [f"الحالة / Status  : تعذّر التصنيف — could not classify product",
              f"السبب / Reason   : {result.get('hs_note', '')}",
              "═" * 60]
        return "\n".join(L)

    L += [
        f"رمز HS / HS code : {result['hs_code']}  (ثقة/conf={result['hs_confidence']})",
        f"السنة / Year     : {result['year']}   |   مبدئي / PRELIMINARY",
        f"التصنيف / Note   : {result['hs_note']}",
        "─" * 60,
        "الأسواق مرتّبة (الأفضل أولاً) — markets ranked best-first:",
    ]
    for i, row in enumerate(result["markets"], 1):
        present = sum(1 for dp in row["components"].values() if dp.value is not None)
        L.append(f"  {i:>2}. {row['country']:<22} score={row['total_score']:.3f} "
                 f"conf={row['confidence']} ({present}/{len(WEIGHTS)} comps)")
        if "jury" in row:
            j = row["jury"]
            L.append(f"      الحكم/Jury: {j['verdict']}  "
                     f"(conf={j['confidence']}, gaps={j['data_gaps']})")
        L.append(f"      → {row['recommendation']}")
    L += [f"\nملاحظة / Note: {result['note']}", "═" * 60]
    return "\n".join(L)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk Market Intelligence — engine demo "
          "(offline: shows 'no data / fetch failed', never fake numbers)\n")
    # عيّنة صغيرة من الأسواق لإبقاء العرض سريعًا — small market sample for a fast demo.
    sample = [{"iso3": "ARE", "m49": "784"}, {"iso3": "USA", "m49": "840"},
              {"iso3": "IND", "m49": "356"}]
    for product in ("تمور", "saffron", "spaceship-xyz"):
        res = analyze(product, countries=sample)
        print(format_result(res))
        print()
