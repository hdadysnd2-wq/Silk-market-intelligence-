"""وكيل الإنتاج لسِلك — Silk production agent (المجموعة أ · Group A, V3).

يقدّر الإنتاج المحلي لسلعة في سوق: FAOSTAT للسلع الزراعية (نطاق QCL، كمية
الإنتاج بالأطنان) مع رجوع لبحث الويب للسلع غير الزراعية. بيانات حقيقية فقط: عند
أي فشل يعيد DataPoint(value=None, confidence=0.0) موسومًا — لا يخترع رقمًا.

Estimates a market's domestic PRODUCTION of a product: FAOSTAT (agricultural
items, QCL domain, production quantity in tonnes) with a web-search evidence
fallback for non-agricultural products. Real data only: on any failure it
returns a provenance-tagged DataPoint(value=None, confidence=0.0).

FAOSTAT auth caveat applies (see silk_faostat_agent): anonymous requests may be
401/403; we degrade gracefully. The web-search fallback needs SEARCH_API_KEY;
even with results we DO NOT parse a production number out of free text (that
would risk fabrication) — we attach the evidence with value=None so a later
synthesis step can reason over it. 'requests' is imported lazily-safe (module
imports offline).
"""
from __future__ import annotations

import logging

import requests

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport
from silk_faostat_agent import ISO3_TO_FAOSTAT_AREA

log = logging.getLogger(__name__)

# قاعدة فاوستات — FAOSTAT data endpoint (domain filled per call).
_FAOSTAT_BASE = "https://faostatservices.fao.org/api/v1/en/data"
_TIMEOUT = 30
# النطاق: المحاصيل والثروة الحيوانية — QCL (Crops and livestock products).
_PROD_DOMAIN = "QCL"
# العنصر 5510 = كمية الإنتاج (طن) — Production quantity (tonnes).
_PROD_ELEMENT = "5510"


def faostat_production(iso3: str, product: str, year: int | None = None) -> DataPoint:
    """إنتاج فاوستات — FAOSTAT production quantity (tonnes) for one crop/livestock item.

    Best-effort; returns DataPoint(value=None, confidence=0.0, note=...) on any
    failure (unknown area / auth / empty / format / network / non-numeric) —
    never fabricates.
    """
    area = ISO3_TO_FAOSTAT_AREA.get(iso3.upper())
    if area is None:
        note = f"FAOSTAT production unavailable: unknown area for ISO3 '{iso3}' (no mapping)"
        log.warning(note)
        return DataPoint(None, "FAOSTAT", 0.0, note, _today())

    params = {
        "area": str(area),
        "element": _PROD_ELEMENT,
        "show_unit": "true",
        "output_type": "objects",
    }
    if year is not None:
        params["year"] = str(year)

    url = f"{_FAOSTAT_BASE}/{_PROD_DOMAIN}"
    try:
        r = requests.get(url, params=params, timeout=_TIMEOUT)
        if r.status_code in (401, 403):
            note = (f"FAOSTAT production unavailable: HTTP {r.status_code} for "
                    f"{iso3}/{product} (may require auth)")
            log.warning(note)
            return DataPoint(None, "FAOSTAT", 0.0, note, _today())
        r.raise_for_status()
        payload = r.json()
    except ValueError as e:  # non-JSON body -> likely auth/format change
        note = (f"FAOSTAT production unavailable: non-JSON response for "
                f"{iso3}/{product}: {e} (may require auth)")
        log.warning(note)
        return DataPoint(None, "FAOSTAT", 0.0, note, _today())
    except Exception as e:  # noqa: BLE001 — network/HTTP; never raise to caller
        note = (f"FAOSTAT production unavailable: fetch failed for "
                f"{iso3}/{product}: {e} (may require auth)")
        log.warning(note)
        return DataPoint(None, "FAOSTAT", 0.0, note, _today())

    rows = payload.get("data") if isinstance(payload, dict) else None
    if not rows:
        note = (f"FAOSTAT production unavailable: empty data for "
                f"{iso3}/{product} {year or ''} (may require auth)")
        log.warning(note)
        return DataPoint(None, "FAOSTAT", 0.0, note, _today())

    want = product.strip().lower()
    chosen = None
    for row in rows:
        ritem = str(row.get("Item", "")).strip().lower()
        if ritem == want or want in ritem or (ritem and ritem in want):
            chosen = row
            break
    if chosen is None:
        note = f"FAOSTAT production unavailable: item '{product}' not found for {iso3}"
        log.warning(note)
        return DataPoint(None, "FAOSTAT", 0.0, note, _today())

    raw = chosen.get("Value")
    try:
        value = float(raw)
    except (TypeError, ValueError):
        note = (f"FAOSTAT production unavailable: non-numeric value for "
                f"{iso3}/{product}: {raw!r}")
        log.warning(note)
        return DataPoint(None, "FAOSTAT", 0.0, note, _today())

    unit = chosen.get("Unit", "tonnes")
    yr = chosen.get("Year", year)
    note = f"{chosen.get('Item', product)} production year={yr} unit={unit}"
    return DataPoint(value, "FAOSTAT", 0.85, note, _today())


def production_estimate(iso3: str, product: str, year: int | None = None,
                        *, allow_websearch: bool = True) -> list[DataPoint]:
    """أفضل تقدير إنتاج — FAOSTAT أولاً، ثم بحث الويب كسياق (بلا اختلاق رقم).

    Returns a list of DataPoints. On a FAOSTAT hit it's a single valued
    DataPoint. Otherwise it's the FAOSTAT failure DataPoint plus any web-search
    evidence (each value being a {title,snippet,link} dict, NOT a parsed number —
    production figures are never inferred from free text). Empty/offline -> just
    the provenance-tagged None. Never fabricates.
    """
    dp = faostat_production(iso3, product, year)
    if dp.value is not None:
        return [dp]
    if not allow_websearch:
        return [dp]
    # رجوع سياقي: أدلة بحث بلا رقم مُستخرج — evidence only, no number parsed.
    try:
        from silk_websearch_agent import web_search
        q = f"{product} production {iso3} {year or ''} tonnes annual".strip()
        results = web_search(q, num=3)
        evidence = [r for r in results if r.value is not None]
        if evidence:
            return [dp] + evidence
    except Exception as e:  # noqa: BLE001 — fallback must not crash the agent
        log.warning("production web fallback failed for %s/%s: %s", iso3, product, e)
    return [dp]


class ProductionAgent(Agent):
    """وكيل الإنتاج — domestic production (FAOSTAT tonnes; web evidence fallback)."""

    def __init__(self) -> None:
        super().__init__("ProductionAgent")

    def run(self, task: dict) -> AgentReport:
        """قدّر الإنتاج المحلي — estimate the market's domestic production.

        task keys: iso3/country, product/item, year (optional),
                   allow_websearch (optional, default True).
        Missing iso3/product -> failed report; never a fabricated figure.
        """
        iso3 = task.get("iso3") or task.get("country")
        product = task.get("product") or task.get("item")
        year = task.get("year")
        allow_websearch = task.get("allow_websearch", True)
        if not iso3 or not product:
            return AgentReport(
                self.name, [], True,
                "لا يوجد ISO3/سلعة — missing iso3/country or product, cannot estimate production")
        findings = production_estimate(str(iso3), str(product), year,
                                       allow_websearch=bool(allow_websearch))
        valued = [f for f in findings if f.value is not None]
        # وكيل ناجح فقط لو عنده رقم إنتاج حقيقي — success needs a real number,
        # not merely web evidence (which carries no verified production figure).
        has_number = any(f.source == "FAOSTAT" and f.value is not None for f in valued)
        if has_number:
            dp = next(f for f in valued if f.source == "FAOSTAT")
            return AgentReport(self.name, findings, False,
                               f"production {dp.value} tonnes for {iso3}/{product} (FAOSTAT)")
        summary = (f"production unavailable for {iso3}/{product} — "
                   f"{len(valued)} web evidence item(s), no verified number"
                   if valued else
                   f"production unavailable for {iso3}/{product} (best-effort)")
        return AgentReport(self.name, findings, True, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk ProductionAgent — best-effort, degrades gracefully offline / under auth "
          "(no fabricated production numbers)")
    report = ProductionAgent().run({"iso3": "SAU", "product": "Dates", "year": 2021})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} conf={f.confidence} note={f.note}")
