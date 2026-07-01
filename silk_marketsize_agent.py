"""وكيل حجم السوق لسِلك — Silk market-size agent (المجموعة أ · Group A, V3).

يقدّر حجم السوق عبر «الاستهلاك الظاهري»: الإنتاج + الاستيراد − التصدير (بالأطنان،
كميات Comtrade عبر netWgt + إنتاج FAOSTAT). عند غياب الإنتاج أو الكميات يرجع إلى
«قيمة الاستيراد» (دولار) كمؤشّر جزئي موسوم بوضوح — لا كحجم سوق كامل. عند غياب كل
شيء يعيد None موسومًا. بيانات حقيقية فقط، لا اختلاق.

Estimates market size via APPARENT CONSUMPTION = production + imports − exports
(tonnes; trade quantities from Comtrade netWgt, production from FAOSTAT). When
production or trade quantities are missing it degrades to an import-VALUE (USD)
proxy, clearly labeled as a partial measure (imports only, NOT full apparent
consumption). When nothing is available it returns a provenance-tagged None.
Never fabricates.
"""
from __future__ import annotations

import logging

from silk_data_layer import DataPoint, comtrade_trade, _today
from silk_agents import Agent, AgentReport
from silk_production_agent import production_estimate

log = logging.getLogger(__name__)


def _trade_tonnes(hs_code: str, m49: object, year: int, flow: str) -> float | None:
    """كمية تجارة بالأطنان — total World trade quantity (tonnes) from Comtrade netWgt.

    Sums netWgt (kg) over the World-partner record(s) and converts to tonnes.
    Returns None when there's no data or no usable weight (never fabricated).
    """
    recs = comtrade_trade(hs_code, m49, year, flow=flow, partner=0)
    if not recs:
        return None
    total_kg = 0.0
    for r in recs:
        w = r.get("netWgt")
        if w in (None, ""):
            continue
        try:
            total_kg += float(w)
        except (TypeError, ValueError):
            continue
    return round(total_kg / 1000.0, 3) if total_kg > 0 else None


def apparent_consumption(hs_code: str, iso3: str, m49: object, product: str,
                         year: int) -> DataPoint:
    """الاستهلاك الظاهري — apparent consumption (tonnes) or a labeled proxy.

    production + imports − exports (tonnes) when all three are available; else an
    import-value (USD) proxy labeled as partial; else None. Real data only.
    """
    prod_findings = production_estimate(iso3, product, year, allow_websearch=False)
    prod = next((f for f in prod_findings
                 if f.source == "FAOSTAT" and f.value is not None), None)
    imports_t = _trade_tonnes(hs_code, m49, year, "M")
    exports_t = _trade_tonnes(hs_code, m49, year, "X")

    if prod is not None and imports_t is not None and exports_t is not None:
        ac = round(prod.value + imports_t - exports_t, 1)
        return DataPoint(
            {"method": "apparent_consumption_tonnes", "value_tonnes": ac,
             "production_tonnes": prod.value, "imports_tonnes": imports_t,
             "exports_tonnes": exports_t},
            "Silk (FAOSTAT + UN Comtrade)", 0.8,
            f"apparent consumption = production + imports − exports (tonnes), {year}",
            _today())

    # مؤشّر جزئي: قيمة الاستيراد فقط — import-value proxy, clearly partial.
    from silk_data_layer_v2 import market_imports
    mi = market_imports(hs_code, m49, year)
    if mi.get("total_usd") is not None:
        missing = []
        if prod is None:
            missing.append("production")
        if imports_t is None or exports_t is None:
            missing.append("trade quantities")
        return DataPoint(
            {"method": "import_value_proxy_usd", "value_usd": mi["total_usd"],
             "missing": missing},
            "UN Comtrade", 0.5,
            f"market-size PROXY: import value only (USD) — {', '.join(missing)} "
            f"unavailable, so this is NOT full apparent consumption, {year}",
            _today())

    return DataPoint(
        None, "Silk", 0.0,
        f"market size unavailable for {iso3}/{product} {year} "
        "(no production, no trade)", _today())


class MarketSizeAgent(Agent):
    """وكيل حجم السوق — apparent consumption (tonnes) or a labeled import proxy."""

    def __init__(self) -> None:
        super().__init__("MarketSizeAgent")

    def run(self, task: dict) -> AgentReport:
        """قدّر حجم السوق — estimate market size for the task's product/market.

        task keys: hs_code, iso3/country, market_m49/m49, product/item, year.
        Missing essentials -> failed report; never a fabricated size.
        """
        hs_code = task.get("hs_code")
        iso3 = task.get("iso3") or task.get("country")
        m49 = task.get("market_m49") or task.get("m49")
        product = task.get("product") or task.get("item")
        year = task.get("year")
        if not hs_code or not iso3 or m49 is None or not product or not year:
            return AgentReport(
                self.name, [], True,
                "بيانات ناقصة — missing hs_code/iso3/m49/product/year, cannot size market")
        dp = apparent_consumption(str(hs_code), str(iso3), m49, str(product), int(year))
        failed = dp.value is None
        if failed:
            summary = f"market size unavailable for {iso3}/{product} (best-effort)"
        else:
            method = dp.value.get("method")
            summary = (f"market size ({method}) for {iso3}/{product}")
        return AgentReport(self.name, [dp], failed, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk MarketSizeAgent — apparent consumption or labeled import proxy "
          "(degrades gracefully offline; no fabricated size)")
    report = MarketSizeAgent().run(
        {"hs_code": "080410", "iso3": "ARE", "market_m49": "784",
         "product": "Dates", "year": 2022})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} conf={f.confidence} note={f.note}")
