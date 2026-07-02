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

from silk_data_layer import DataPoint, _today
from silk_hs_resolver import resolve
from silk_market_ranker import rank_markets, COUNTRIES, WEIGHTS
from silk_agents import ResearchManager
from silk_synthesis import synthesize

log = logging.getLogger(__name__)

_DEFAULT_YEAR = 2022      # آخر سنة كاملة موثوقة في Comtrade — stable full year
_ENRICH_TOP = 3           # كم سوقًا نُثريه بالوكلاء — top markets to deep-enrich


def analyze(product_name: str, countries: list[dict] | None = None,
            year: int | None = None, *, with_trends: bool = False,
            with_tariffs: bool = False, with_faostat: bool = False,
            with_maps: bool = False, with_websearch: bool = False,
            with_localprice: bool = False, own_price: float | None = None,
            with_volza: bool = False, with_explee: bool = False,
            with_ai: bool = False,
            with_competitors: bool = False, with_channels: bool = False,
            with_importers: bool = False, with_requirements: bool = False,
            product_card: dict | None = None,
            hs_code: str | None = None,
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
      with_competitors — attach named-competitor candidates (row['competitors_named']).
      with_channels — attach distribution-channel candidates (row['channels']).
      with_importers— attach importer candidates, free web layer (row['importers']).
      with_requirements — attach the dual-direction compliance checklist
                      (row['requirements']: entry items for the market +
                      Saudi-exit items, L1 reference, fully offline).
      product_card  — بطاقة المنتج الاختيارية (الموجة ٤): {cost_per_unit,
                      unit, tier, monthly_capacity, shipping_per_unit}.
                      عند وجودها يعمل محرّك التقاطع (correlation.py) على
                      نتائج الوكلاء بالذاكرة ويضيف row['competitive_position'];
                      غيابها = السلوك الحالي بالضبط (لا انحدار).
                      All of these are ADDITIVE context — they never change total_score.
      persist       — init_db + save_analysis(db_path); attaches result['analysis_id'].
      check_quality — annotate each market with quality_flags (flags only, no number edits).
      db_path       — SQLite path for persist.
    All optional layers degrade gracefully offline (provenance-tagged None, no fabrication).
    """
    year = year or _DEFAULT_YEAR
    countries = countries or COUNTRIES

    # 1) صنّف المنتج إلى رمز HS — resolve product -> HS6 (carry its confidence).
    #    hs_code ممرَّر (من زر "حلّل هذه الفرصة" بالاكتشاف، §11.5-3) يتجاوز
    #    المصنّف — رمز معلوم المصدر لا يحتاج إعادة تخمين.
    if hs_code:
        hs = DataPoint(str(hs_code), "Silk discovery hand-off", 1.0,
                       "HS ممرَّر مباشرة من اكتشاف الفرص — لا إعادة تصنيف",
                       _today())
    else:
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

    # 3) شغّل الوكلاء الأساسيين واحتفظ بتقاريرهم — run core agents, keep reports
    #    (الحكم يتأخر لما بعد الإثراء والتقاطع كي تصل الخيوط للمرحلة ٢ — الموجة ٤).
    manager = ResearchManager()
    reports_by_iso: dict[str, list] = {}
    for row in ranked[:_ENRICH_TOP]:
        task = {"hs_code": hs.value, "market_m49": row["m49"],
                "iso3": row["iso3"], "year": year}
        reports_by_iso[row["iso3"]] = manager.distribute(task)

    # 3b) طبقات سياق إضافية (لا تغيّر النقاط) — additive context layers (no score change).
    if with_trends:
        _enrich_trends(ranked[:_ENRICH_TOP], product_name)
    if with_tariffs:
        _enrich_tariffs(ranked[:_ENRICH_TOP], hs.value, year)
    if with_faostat:
        _enrich_faostat(ranked[:_ENRICH_TOP], product_name, year)
    if with_maps:
        _enrich_maps(ranked[:_ENRICH_TOP], product_name)
    if with_localprice:
        _enrich_localprice(ranked[:_ENRICH_TOP], product_name, own_price)
    if with_volza:
        _enrich_volza(ranked[:_ENRICH_TOP], hs.value)
    if with_explee:
        _enrich_explee(ranked[:_ENRICH_TOP], product_name)
    if with_competitors:
        _enrich_named(ranked[:_ENRICH_TOP], product_name,
                      "competitors_named", "silk_competitors_agent",
                      "NamedCompetitorsAgent")
    if with_channels:
        _enrich_named(ranked[:_ENRICH_TOP], product_name,
                      "channels", "silk_channels_agent",
                      "DistributionChannelsAgent")
    if with_importers:
        _enrich_named(ranked[:_ENRICH_TOP], product_name,
                      "importers", "silk_importers_agent", "ImportersAgent")
    if with_requirements:
        _enrich_requirements(ranked[:_ENRICH_TOP], hs.value)

    # 3c) محرّك التقاطع (الموجة ٤) — يعمل فقط عند وجود بطاقة المنتج.
    if product_card:
        import correlation  # صفر استدعاءات خارجية — يعمل على الذاكرة حصراً
        for row in ranked[:_ENRICH_TOP]:
            try:
                row["competitive_position"] = correlation.correlate(
                    row, product_card, product_name)
            except Exception as e:  # noqa: BLE001 — لا يُسقط التحليل
                log.warning("correlation failed for %s: %s", row.get("iso3"), e)
                row["competitive_position"] = {
                    "error": f"correlation error: {type(e).__name__}: {e}"}

    # 3d) التوليف الموحّد (مرحلتان) — the single verdict entry point (§9.3).
    for row in ranked[:_ENRICH_TOP]:
        reports = reports_by_iso.get(row["iso3"], [])
        row["jury"] = synthesize(
            reports, product=product_name,
            market=row.get("country") or row["iso3"],
            threads=row.get("competitive_position"), with_ai=with_ai)

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
    if not product_card:
        result["product_card_hint"] = ("أضف بطاقة منتجك (product_card) للحصول "
                                       "على تحليل تنافسي مخصص — موقعك ضد "
                                       "منافسين مرصودين بالاسم")
    if with_websearch:
        result["websearch"] = _websearch(product_name)
    if with_ai:  # الطبقة 3: كلود يكتب التقرير المبدئي — Claude writes the report
        rep = _ai_report(result)
        result["report"] = rep  # None = فشل/غياب المفتاح، ظاهرٌ لا محذوف (الموجة ١)
        if rep is None:
            result["report_note"] = ("تعذّر توليد تقرير كلود (مفتاح غائب أو فشل "
                                     "النداء) — AI report unavailable, not hidden.")
    if check_quality:
        _annotate_quality(result)
    if persist:
        _persist(result, db_path)
    return result


def _ai_report(result: dict):
    """الطبقة 3 — تقرير كلود المبدئي — Claude's written report (None if unavailable)."""
    try:
        import silk_ai_judge  # lazy
        return silk_ai_judge.ai_report(result)
    except Exception as e:  # noqa: BLE001
        log.warning("AI report failed: %s", e)
        return None



def _enrich_error_dp(source: str, e: Exception) -> "DataPoint":
    """فشل غلاف الإثراء بملاحظة — provenance-tagged enrichment failure (wave 1).

    كان الاستثناء غير المتوقع يتدهور إلى []/None صامتين لا يميّزهما المستهلك عن
    "لا نتائج"؛ الآن يظهر DataPoint(None, note=السبب) — نفس صرامة الوكلاء.
    """
    return DataPoint(None, source, 0.0,
                     f"enrichment error: {type(e).__name__}: {e}", _today())

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
            row["trends"] = [_enrich_error_dp("Google Trends", e)]


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
            row["tariff"] = _enrich_error_dp("World Bank WITS", e)


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
            row["faostat"] = _enrich_error_dp("FAOSTAT", e)


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
            row["maps"] = [_enrich_error_dp("Google Maps", e)]


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
            row["localprice"] = [_enrich_error_dp("Local retail", e)]
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
            row["volza"] = [_enrich_error_dp("Volza", e)]


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
            row["explee"] = [_enrich_error_dp("Explee", e)]


def _enrich_named(rows: list[dict], product_name: str, key: str,
                  module: str, cls: str) -> None:
    """أضف وكيل ترشيح ويب لكل سوق — attach a wave-3 web-candidate agent.

    غلاف واحد للوكلاء الثلاثة (منافسون مُسمّون/قنوات/مستوردون) — نفس نمط
    الإثراء القائم ونفس انضباط الموجة ١ (استثناء => DataPoint موسوم).
    """
    import importlib
    agent = getattr(importlib.import_module(module), cls)()
    for row in rows:
        try:
            rep = agent.run({"product": product_name,
                             "market": row.get("country") or row.get("iso3")})
            row[key] = rep.findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("%s enrichment failed for %s: %s", key, row.get("iso3"), e)
            row[key] = [_enrich_error_dp(cls, e)]


def _enrich_requirements(rows: list[dict], hs_code: str) -> None:
    """أضف قائمة تحقق الاشتراطات — attach the dual-direction L1 checklist."""
    from silk_requirements_agent import RequirementsAgent  # lazy: optional layer
    agent = RequirementsAgent()
    for row in rows:
        try:
            rep = agent.run({"market_iso3": row.get("iso3"), "hs_code": hs_code})
            row["requirements"] = rep.findings
        except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
            log.warning("requirements enrichment failed for %s: %s",
                        row.get("iso3"), e)
            row["requirements"] = [_enrich_error_dp("Silk L1 reference", e)]


def _websearch(product_name: str) -> list:
    """نتائج بحث الويب للمنتج — top-level web-search findings (graceful None offline)."""
    from silk_websearch_agent import WebSearchAgent  # lazy: optional layer
    try:
        rep = WebSearchAgent().run({"query": product_name, "num": 5})
        return rep.findings
    except Exception as e:  # noqa: BLE001 — context layer must not crash analysis
        log.warning("websearch enrichment failed: %s", e)
        return [_enrich_error_dp("Web Search", e)]


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
    """نسّق النتيجة للطرفية — terminal summary derived from the ONE view template.

    الموجة ٤ (§10.1): كان هذا مسار عرض مستقلاً ثالثاً؛ صار مشتقاً من
    silk_render.build_view — القالب الموحّد الذي تشتق منه كل المخرجات.
    """
    from silk_render import build_view, render_text
    return render_text(build_view(result))


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
