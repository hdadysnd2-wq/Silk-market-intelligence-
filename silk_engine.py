"""المحرّك الكامل لمنصّة سِلك لذكاء الأسواق — Silk Market Intelligence engine.

End-to-end pipeline, real public data only (founding principle: never fabricate):
    product name -> HS6 code (silk_hs_resolver)
                 -> ranked target markets (silk_market_ranker)
                 -> top markets enriched with agents + jury (silk_agents).

Every output is PRELIMINARY and carries provenance. Network failures degrade
gracefully (no data / fetch failed), never crash, never invent numbers.
"""
from __future__ import annotations

import logging

from silk_hs_resolver import resolve
from silk_market_ranker import rank_markets, COUNTRIES, WEIGHTS
from silk_agents import ResearchManager, JuryCommittee

log = logging.getLogger(__name__)

_DEFAULT_YEAR = 2022      # آخر سنة كاملة موثوقة في Comtrade — stable full year
_ENRICH_TOP = 3           # كم سوقًا نُثريه بالوكلاء — top markets to deep-enrich


def analyze(product_name: str, countries: list[dict] | None = None,
            year: int | None = None, *, with_trends: bool = False,
            with_tariffs: bool = False, with_faostat: bool = False,
            with_maps: bool = False, with_websearch: bool = False,
            with_localprice: bool = False, own_price: float | None = None,
            with_market_size: bool = False, with_demographics: bool = False,
            with_competition: bool = False, with_compliance: bool = False,
            with_culture: bool = False,
            with_volza: bool = False, with_explee: bool = False,
            with_ai: bool = False, with_synthesis: bool = False,
            persist: bool = False, db_path: str = "data/silk.db",
            check_quality: bool = True) -> dict:
    """حلّل منتجًا عبر الأسواق — full preliminary market analysis for one product.

    Returns an EngineResult dict:
        {product, hs_code, hs_confidence, hs_note, year, preliminary,
         classified (bool), markets: [...], note}
    Each market row adds a one-line `recommendation`; the top markets also carry
    an agents `jury` verdict. If the product cannot be classified, returns
    classified=False with markets=[] — it never guesses an HS code.

    Optional, default-OFF enrichments (old behavior is unchanged with defaults):
      with_trends   — attach a Google Trends finding per top market (row['trends']).
      with_tariffs  — attach a WITS applied-tariff finding per top market (row['tariff']).
      with_faostat  — attach a FAOSTAT per-capita supply finding per top market (row['faostat']).
      with_market_size — attach Group-A production + market-size (apparent
                      consumption, tonnes; import-value proxy fallback) per top
                      market (row['production'], row['market_size']). Additive.
      with_demographics — attach Group-B context per top market: row['cities']
                      (largest cities lat/lng+pop), row['religion'] (majority
                      religion, approx/dated), row['currency_risk'] (World Bank
                      inflation + FX-rate signals). Additive; no score change.
      with_competition — attach Group-C context per top market:
                      row['competitors_web'], row['importers'] (FREE web search;
                      the PAID Volza importers stay deepen-only),
                      row['distribution_channels'], row['ecommerce'] (dynamic web
                      search), and row['bestsellers']
                      (LICENSED Apify actor; None without APIFY_API_TOKEN — no raw
                      scraping). Additive; no score change.
      with_compliance — attach Group-D NEW context per top market:
                      row['regulatory'] (packaging/labeling/cert requirements —
                      halal/health/ISO) and row['customs_web'] (official customs
                      authority page), both dynamic web search. Retail price
                      (with_localprice) and applied tariff % (with_tariffs) are
                      the pre-existing Group-D members. Additive; no score change.
      with_culture  — attach Group-E context per top market: row['cultural']
                      (consumption habits/lifestyle), row['business_culture']
                      (negotiation/payment/etiquette), row['exhibitions'] (trade
                      fairs), all dynamic web search. Google Trends (with_trends)
                      is the pre-existing Group-E member. Additive; no score change.
      with_synthesis— run the two-stage Claude synthesis (silk_synthesis) over
                      ALL attached group findings per top market, attaching
                      row['synthesis'] (verdict/opportunities/risks/
                      recommendations/gaps). Runs LAST so it sees every group.
                      Keyless -> nothing attached (deterministic jury stands);
                      raw findings are quarantined (prompt-injection guard) and
                      never fabricated. Additive; no score change.
      with_maps     — attach Google Maps named businesses per top market (row['maps']).
      with_localprice— attach actual in-market retail prices per top market (row['localprice']).
      own_price     — YOUR product's price; with with_localprice, attaches a
                      price-positioning comparison per top market
                      (row['price_comparison']: percentile vs. observed local
                      listings). No effect without with_localprice. Ignored
                      (never fabricated) when there are no local listings.
      with_websearch— attach web-search results for the product (result['websearch']).
      with_volza    — attach Volza named importers (PAID) per top market (row['volza']).
      with_explee   — attach Explee buyers/contacts (PAID) per top market (row['explee']).
                      All of these are ADDITIVE context — they never change total_score.
      persist       — init_db + save_analysis(db_path); attaches result['analysis_id'].
      check_quality — annotate each market with quality_flags (flags only, no number edits).
      db_path       — SQLite path for persist.
    All optional layers degrade gracefully offline (provenance-tagged None, no fabrication).
    """
    year = year or _DEFAULT_YEAR
    countries = countries or COUNTRIES

    # 1) صنّف المنتج إلى رمز HS — resolve product -> HS6 (carry its confidence).
    hs = resolve(product_name)
    if hs.value is None:
        result = {
            "product": product_name, "hs_code": None, "hs_confidence": 0.0,
            "hs_note": hs.note, "year": year, "preliminary": True,
            "classified": False, "markets": [],
            "note": "تعذّر تصنيف المنتج إلى رمز HS — could not classify product; "
                    "no HS code guessed.",
        }
        if check_quality:
            _annotate_quality(result)
        if persist:
            _persist(result, db_path)
        return result

    # 2) رتّب الأسواق المرشّحة لهذا الرمز — rank candidate markets.
    ranked = rank_markets(hs.value, countries=countries, year=year)

    # 3) أثرِ الأسواق الأعلى بالوكلاء واللجنة — enrich the top markets.
    manager = ResearchManager()
    for row in ranked[:_ENRICH_TOP]:
        task = {"hs_code": hs.value, "market_m49": row["m49"],
                "iso3": row["iso3"], "year": year}
        reports = manager.distribute(task)
        row["jury"] = JuryCommittee.evaluate(reports)
        if with_ai:  # الطبقة 3: كلود يَحكم على مخرجات الوكلاء — Claude judges the findings
            _ai_verdict(row, product_name, reports)

    # 3b) طبقات سياق إضافية (لا تغيّر النقاط) — additive context layers (no score change).
    if with_trends:
        _enrich_trends(ranked[:_ENRICH_TOP], product_name)
    if with_tariffs:
        _enrich_tariffs(ranked[:_ENRICH_TOP], hs.value, year)
    if with_faostat:
        _enrich_faostat(ranked[:_ENRICH_TOP], product_name, year)
    if with_market_size:
        _enrich_market_size(ranked[:_ENRICH_TOP], hs.value, product_name, year)
    if with_demographics:
        _enrich_demographics(ranked[:_ENRICH_TOP], year)
    if with_competition:
        _enrich_competition(ranked[:_ENRICH_TOP], product_name)
    if with_compliance:
        _enrich_compliance(ranked[:_ENRICH_TOP], product_name)
    if with_culture:
        _enrich_culture(ranked[:_ENRICH_TOP], product_name)
    if with_maps:
        _enrich_maps(ranked[:_ENRICH_TOP], product_name)
    if with_localprice:
        _enrich_localprice(ranked[:_ENRICH_TOP], product_name, own_price)
    if with_volza:
        _enrich_volza(ranked[:_ENRICH_TOP], hs.value)
    if with_explee:
        _enrich_explee(ranked[:_ENRICH_TOP], product_name)

    # 3c) التركيب النهائي عبر كلود (بعد كل الإثراء) — two-stage synthesis LAST so it
    # sees every group's findings. Keyless -> None, deterministic jury stands.
    if with_synthesis:
        _enrich_synthesis(ranked[:_ENRICH_TOP], product_name)

    # 4) سطر توصية لكل سوق — one-line recommendation per market.
    for row in ranked:
        row["recommendation"] = _recommend(row)

    result = {
        "product": product_name, "hs_code": hs.value,
        "hs_confidence": hs.confidence, "hs_note": hs.note,
        "year": year, "preliminary": True, "classified": True,
        "markets": ranked,
        "note": "نتيجة مبدئية مبنية على بيانات عامة حقيقية؛ النواقص معلّمة لا مُخمّنة. "
                "Preliminary, real public data only; gaps flagged, not estimated.",
    }
    if with_websearch:
        result["websearch"] = _websearch(product_name)
    if with_ai:  # الطبقة 3: كلود يكتب التقرير المبدئي — Claude writes the report
        rep = _ai_report(result)
        if rep:
            result["report"] = rep
    if check_quality:
        _annotate_quality(result)
    if persist:
        _persist(result, db_path)
    return result


def _enrich_synthesis(rows: list[dict], product_name: str) -> None:
    """التركيب النهائي — attach row['synthesis'] via the two-stage Claude synthesis
    over every attached group finding. Keyless/offline -> nothing attached
    (deterministic jury stands); never fabricates."""
    try:
        import silk_synthesis  # lazy: optional, key-gated
    except Exception as e:  # noqa: BLE001
        log.warning("synthesis unavailable: %s", e)
        return
    for row in rows:
        try:
            s = silk_synthesis.synthesize_market(row, product_name)
            if s:
                row["synthesis"] = s
        except Exception as e:  # noqa: BLE001 — synthesis must not crash analysis
            log.warning("synthesis failed for %s: %s", row.get("iso3"), e)


def _ai_verdict(row: dict, product: str, reports: list) -> None:
    """الطبقة 3 — حكم كلود على صفّ السوق — attach Claude's verdict (graceful None)."""
    try:
        import silk_ai_judge  # lazy: optional layer, key-gated
        v = silk_ai_judge.ai_verdict(product, row.get("country") or row.get("iso3"), reports)
        if v:
            row.setdefault("jury", {})["ai"] = v
    except Exception as e:  # noqa: BLE001 — never crash analysis
        log.warning("AI verdict failed for %s: %s", row.get("iso3"), e)


def _ai_report(result: dict):
    """الطبقة 3 — تقرير كلود المبدئي — Claude's written report (None if unavailable)."""
    try:
        import silk_ai_judge  # lazy
        return silk_ai_judge.ai_report(result)
    except Exception as e:  # noqa: BLE001
        log.warning("AI report failed: %s", e)
        return None


def _enrich_trends(rows: list[dict], product_name: str) -> None:
    """أضف إشارة جوجل تريندز لكل سوق — attach Trends findings (graceful None offline)."""
    from silk_trends_agent import TrendsAgent  # lazy: optional layer
    agent = TrendsAgent()
    for row in rows:
        try:
            rep = agent.run({"keyword": product_name, "geo": row.get("iso2")})
            row["trends"] = rep.findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("trends enrichment failed for %s: %s", row.get("iso3"), e)
            row["trends"] = []


def _enrich_tariffs(rows: list[dict], hs_code: str, year: int) -> None:
    """أضف التعريفة المطبّقة لكل سوق — attach tariff finding (graceful None offline)."""
    from silk_tariffs_agent import TariffsAgent  # lazy: optional layer
    agent = TariffsAgent()
    for row in rows:
        try:
            rep = agent.run({"hs_code": hs_code, "iso3": row.get("iso3"),
                             "year": year})
            row["tariff"] = rep.findings[0] if rep.findings else None
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("tariff enrichment failed for %s: %s", row.get("iso3"), e)
            row["tariff"] = None


def _enrich_faostat(rows: list[dict], product_name: str, year: int) -> None:
    """أضف نصيب الفرد من فاوستات لكل سوق — attach FAOSTAT finding (graceful None offline)."""
    from silk_faostat_agent import FaostatAgent  # lazy: optional layer
    agent = FaostatAgent()
    for row in rows:
        try:
            rep = agent.run({"iso3": row.get("iso3"), "item": product_name,
                             "year": year})
            row["faostat"] = rep.findings[0] if rep.findings else None
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("faostat enrichment failed for %s: %s", row.get("iso3"), e)
            row["faostat"] = None


def _enrich_market_size(rows: list[dict], hs_code: str, product_name: str,
                        year: int) -> None:
    """أضف الإنتاج وحجم السوق (المجموعة أ) — attach Group-A production +
    market-size (apparent consumption) per market. Graceful None offline; both
    are additive context and never change total_score."""
    from silk_production_agent import ProductionAgent  # lazy: optional layer
    from silk_marketsize_agent import MarketSizeAgent  # lazy: optional layer
    prod_agent = ProductionAgent()
    size_agent = MarketSizeAgent()
    for row in rows:
        iso3 = row.get("iso3")
        try:
            prep = prod_agent.run({"iso3": iso3, "product": product_name,
                                   "year": year})
            row["production"] = prep.findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("production enrichment failed for %s: %s", iso3, e)
            row["production"] = []
        try:
            srep = size_agent.run({"hs_code": hs_code, "iso3": iso3,
                                   "market_m49": row.get("m49"),
                                   "product": product_name, "year": year})
            row["market_size"] = srep.findings[0] if srep.findings else None
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("market_size enrichment failed for %s: %s", iso3, e)
            row["market_size"] = None


def _enrich_demographics(rows: list[dict], year: int) -> None:
    """أضف سياق المجموعة ب — attach Group-B demographics per market: cities,
    religion, currency-risk. Graceful None offline; all additive (no score change)."""
    from silk_cities_agent import CitiesAgent      # lazy: optional layer
    from silk_religion_agent import ReligionAgent  # lazy: optional layer
    from silk_currency_agent import CurrencyRiskAgent  # lazy: optional layer
    cities_agent = CitiesAgent()
    religion_agent = ReligionAgent()
    currency_agent = CurrencyRiskAgent()
    for row in rows:
        iso3 = row.get("iso3")
        try:
            row["cities"] = cities_agent.run({"iso3": iso3}).findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("cities enrichment failed for %s: %s", iso3, e)
            row["cities"] = []
        try:
            crep = religion_agent.run({"iso3": iso3})
            row["religion"] = crep.findings[0] if crep.findings else None
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("religion enrichment failed for %s: %s", iso3, e)
            row["religion"] = None
        try:
            row["currency_risk"] = currency_agent.run({"iso3": iso3, "year": year}).findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("currency_risk enrichment failed for %s: %s", iso3, e)
            row["currency_risk"] = []


def _enrich_competition(rows: list[dict], product_name: str) -> None:
    """أضف سياق المجموعة ج — attach Group-C competition/distribution per market:
    competitors (web), importers (FREE web), distribution channels (web),
    e-commerce landscape (web), best-sellers (licensed Apify). Graceful None
    offline/keyless; all additive. The PAID Volza importers stay deepen-only."""
    from silk_competitors_agent import CompetitorsAgent      # lazy: optional layer
    from silk_importers_agent import ImportersAgent          # lazy: FREE web search
    from silk_distribution_agent import (DistributionChannelsAgent,
                                         EcommerceLandscapeAgent)  # lazy
    from silk_bestsellers_agent import BestsellersAgent      # lazy: Apify-gated
    comp_agent = CompetitorsAgent()
    imp_agent = ImportersAgent()
    dist_agent = DistributionChannelsAgent()
    ecom_agent = EcommerceLandscapeAgent()
    best_agent = BestsellersAgent()
    for row in rows:
        country = row.get("country", "")
        market = row.get("iso2") or row.get("iso3") or ""
        try:
            row["competitors_web"] = comp_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("competitors enrichment failed for %s: %s", row.get("iso3"), e)
            row["competitors_web"] = []
        try:
            row["importers"] = imp_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("importers enrichment failed for %s: %s", row.get("iso3"), e)
            row["importers"] = []
        try:
            row["distribution_channels"] = dist_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("distribution enrichment failed for %s: %s", row.get("iso3"), e)
            row["distribution_channels"] = []
        try:
            row["ecommerce"] = ecom_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("ecommerce enrichment failed for %s: %s", row.get("iso3"), e)
            row["ecommerce"] = []
        try:
            row["bestsellers"] = best_agent.run(
                {"product": product_name, "market": market}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("bestsellers enrichment failed for %s: %s", row.get("iso3"), e)
            row["bestsellers"] = []


def _enrich_compliance(rows: list[dict], product_name: str) -> None:
    """أضف سياق المجموعة د الجديد — attach Group-D NEW context per market:
    regulatory standards + official customs-authority page (both web search).
    Graceful None offline/keyless; additive (no score change)."""
    from silk_regulatory_agent import (RegulatoryStandardsAgent,
                                       CustomsInfoAgent)  # lazy: optional layer
    reg_agent = RegulatoryStandardsAgent()
    cust_agent = CustomsInfoAgent()
    for row in rows:
        country = row.get("country", "")
        try:
            row["regulatory"] = reg_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("regulatory enrichment failed for %s: %s", row.get("iso3"), e)
            row["regulatory"] = []
        try:
            row["customs_web"] = cust_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("customs enrichment failed for %s: %s", row.get("iso3"), e)
            row["customs_web"] = []


def _enrich_culture(rows: list[dict], product_name: str) -> None:
    """أضف سياق المجموعة هـ — attach Group-E context per market: consumer culture,
    business culture, exhibitions (all web search). Graceful None offline/keyless;
    additive (no score change)."""
    from silk_culture_agent import (CulturalAgent, BusinessCultureAgent,
                                    ExhibitionsAgent)  # lazy: optional layer
    cult_agent = CulturalAgent()
    biz_agent = BusinessCultureAgent()
    exh_agent = ExhibitionsAgent()
    for row in rows:
        country = row.get("country", "")
        try:
            row["cultural"] = cult_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("cultural enrichment failed for %s: %s", row.get("iso3"), e)
            row["cultural"] = []
        try:
            row["business_culture"] = biz_agent.run(
                {"country": country, "product": product_name}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("business_culture enrichment failed for %s: %s", row.get("iso3"), e)
            row["business_culture"] = []
        try:
            row["exhibitions"] = exh_agent.run(
                {"product": product_name, "country": country}).findings
        except Exception as e:  # noqa: BLE001
            log.warning("exhibitions enrichment failed for %s: %s", row.get("iso3"), e)
            row["exhibitions"] = []


def _enrich_maps(rows: list[dict], product_name: str) -> None:
    """أضف لاعبي السوق بالاسم — attach Google Maps businesses (graceful None offline)."""
    from silk_maps_agent import MapsAgent  # lazy: optional layer
    agent = MapsAgent()
    for row in rows:
        try:
            query = f"{product_name} {row.get('country', '')}".strip()
            rep = agent.run({"query": query})
            row["maps"] = rep.findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("maps enrichment failed for %s: %s", row.get("iso3"), e)
            row["maps"] = []


def _enrich_localprice(rows: list[dict], product_name: str,
                       own_price: float | None = None) -> None:
    """أضف أسعار التجزئة المحلية لكل سوق — attach actual in-market retail prices
    (الأسعار الفعلية، docx 'المتاجر المحلية') + مقارنة سعرك إن أُعطي. Graceful
    None offline; own_price comparison reuses the same fetch, no 2nd call."""
    from silk_localprice_agent import LocalPriceAgent, compare_own_price  # lazy: optional layer
    agent = LocalPriceAgent()
    for row in rows:
        try:
            query = f"{product_name} {row.get('country', '')}".strip()
            rep = agent.run({"query": query, "market": row.get("iso2")})
            row["localprice"] = rep.findings
            if own_price is not None:
                row["price_comparison"] = compare_own_price(own_price, rep.findings)
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("localprice enrichment failed for %s: %s", row.get("iso3"), e)
            row["localprice"] = []
            if own_price is not None:
                row["price_comparison"] = compare_own_price(own_price, [])


def _enrich_volza(rows: list[dict], hs_code: str) -> None:
    """أضف المستوردين بالاسم (فولزا، مدفوع) — attach Volza importers (graceful None)."""
    from silk_volza_agent import VolzaAgent  # lazy: optional paid layer
    agent = VolzaAgent()
    for row in rows:
        try:
            rep = agent.run({"hs_code": hs_code, "market": row.get("m49"),
                             "partner": "SAU"})
            row["volza"] = rep.findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("volza enrichment failed for %s: %s", row.get("iso3"), e)
            row["volza"] = []


def _enrich_explee(rows: list[dict], product_name: str) -> None:
    """أضف المشترين وجهات الاتصال (Explee، مدفوع) — attach Explee buyers (graceful None)."""
    from silk_explee_agent import ExpleeAgent  # lazy: optional paid layer
    agent = ExpleeAgent()
    for row in rows:
        try:
            rep = agent.run({"query": product_name, "market": row.get("iso3", "")})
            row["explee"] = rep.findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("explee enrichment failed for %s: %s", row.get("iso3"), e)
            row["explee"] = []


def _websearch(product_name: str) -> list:
    """نتائج بحث الويب للمنتج — top-level web-search findings (graceful None offline)."""
    from silk_websearch_agent import WebSearchAgent  # lazy: optional layer
    try:
        rep = WebSearchAgent().run({"query": product_name, "num": 5})
        return rep.findings
    except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
        log.warning("websearch enrichment failed: %s", e)
        return []


def _annotate_quality(result: dict) -> None:
    """علّم تنبيهات الجودة — attach quality flags (flags only, never edits numbers)."""
    try:
        from silk_quality import annotate_result
        annotate_result(result)
    except Exception as e:  # noqa: BLE001 — quality is non-essential context
        log.warning("quality annotation skipped: %s", e)


def _persist(result: dict, db_path: str) -> None:
    """خزّن النتيجة — init_db + save_analysis; attaches result['analysis_id']."""
    try:
        from silk_storage import init_db, save_analysis
        init_db(db_path)
        result["analysis_id"] = save_analysis(result, db_path)
    except Exception as e:  # noqa: BLE001 — persistence must not crash analysis
        log.warning("persist skipped: %s", e)


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
