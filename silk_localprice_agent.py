"""وكيل أسعار السوق المحلي لسِلك — Silk local retail-price agent (docx layer 10).

يغطّي صف «المتاجر المحلية» في دليل المصادر: الأسعار الفعلية والأكثر مبيعاً في
متاجر التجزئة (أمازون، نون، جوميا…). يعطيك سعر بيع المنتج الفعلي في السوق
المستهدف — عنصر حاسم لتقدير هامش الربح بعد الاستيراد والرسوم.

Returns the product's REAL local retail price points by querying a configured
price/shopping API (LOCALPRICE_API_KEY + LOCALPRICE_API_URL — e.g. a SerpApi
Google-Shopping endpoint or any JSON service returning priced listings). With no
key OR a network/format failure it returns a provenance-tagged None and never
invents a price (founding principle). 'requests' is lazy-imported so the module
imports offline and keyless with no side effects.
"""
from __future__ import annotations

import logging
import os

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)

# نقطة نهاية أسعار التجزئة — overridable so a provider change needs no code edit.
# الافتراضي SerpApi (Google Shopping) لأنه يرجّع listings بأسعار وعملة ومتجر.
_PRICE_URL = os.environ.get(
    "LOCALPRICE_API_URL", "https://serpapi.com/search.json").strip()
_TIMEOUT = 30


def _extract(payload: dict) -> list[dict]:
    """التقط القوائم المسعّرة من ردّ المزوّد — pull priced listings from the payload.

    Supports SerpApi's `shopping_results` and a generic `results`/`items` list.
    Each item -> {title, price, currency, store, link} using only present fields;
    items with no usable price are skipped (never fabricated).
    """
    items = (payload.get("shopping_results")
             or payload.get("results") or payload.get("items") or [])
    out: list[dict] = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        price = (it.get("extracted_price") if it.get("extracted_price") is not None
                 else it.get("price"))
        if price in (None, ""):
            continue
        out.append({
            "title": it.get("title") or it.get("name"),
            "price": price,
            "currency": it.get("currency"),
            "store": it.get("source") or it.get("store") or it.get("seller"),
            "link": it.get("link") or it.get("product_link"),
        })
    return out


def retail_prices(query: str, market: str | None = None) -> list[DataPoint]:
    """أسعار التجزئة المحلية — real local retail price points for a product.

    Each priced listing -> DataPoint(value={title, price, currency, store, link}).
    No key -> a single DataPoint(None, 0.0, "<requires key>"). On network/API
    failure or empty result -> [DataPoint(None, ...)] (caller flags it). The agent
    NEVER invents a price: a missing source means value=None, confidence=0.0.
    """
    key = os.environ.get("LOCALPRICE_API_KEY", "").strip()
    if not key:
        log.warning("LOCALPRICE_API_KEY not set — local retail prices unavailable")
        return [DataPoint(None, "Local retail", 0.0,
                          "local prices require LOCALPRICE_API_KEY "
                          "(e.g. a SerpApi Google-Shopping key)", _today())]
    q = (query or "").strip()
    if not q:
        return [DataPoint(None, "Local retail", 0.0,
                          "empty query — no price lookup", _today())]
    try:
        import requests  # lazy: keeps import offline-safe and keyless
    except ImportError:
        log.warning("requests not installed — local retail prices unavailable")
        return [DataPoint(None, "Local retail", 0.0,
                          "requests unavailable", _today())]
    # معاملات SerpApi (افتراضي) — engine=google_shopping; gl يحيّز السوق المستهدف.
    params = {"engine": "google_shopping", "q": q, "api_key": key}
    if market:
        params["gl"] = market.lower()  # ccTLD/country bias, e.g. 'ma' for Morocco
    try:
        r = requests.get(_PRICE_URL, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("local price fetch failed (q=%r, market=%s): %s", q, market, e)
        return [DataPoint(None, "Local retail", 0.0,
                          f"local price fetch failed: {e}", _today())]
    listings = _extract(payload)
    if not listings:
        return [DataPoint(None, "Local retail", 0.0,
                          f"no priced listings for '{q}'", _today())]
    findings: list[DataPoint] = []
    for it in listings:
        cur = f" {it['currency']}" if it.get("currency") else ""
        findings.append(DataPoint(
            it, "Local retail", 0.6,
            f"{it.get('title') or 'listing'} @ {it['price']}{cur}"
            + (f" ({it['store']})" if it.get("store") else ""),
            _today()))
    return findings


class LocalPriceAgent(Agent):
    """وكيل أسعار السوق المحلي — actual retail prices/best-sellers in-market."""

    def __init__(self) -> None:
        super().__init__("LocalPriceAgent")

    def run(self, task: dict) -> AgentReport:
        """اجلب الأسعار الفعلية في السوق — fetch real in-market retail prices.

        task keys: query (product, optionally + market words), market (ccTLD
        bias like 'ma', optional). Missing key / network fail -> failed report,
        never a fabricated price.
        """
        query = task.get("query", "")
        market = task.get("market")
        findings = retail_prices(query, market)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no query"
            return AgentReport(self.name, findings, True,
                               f"لا أسعار محلية — no local price data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} local price listing(s) for '{query}'")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk LocalPriceAgent — degrades gracefully offline / without key "
          "(no fabricated prices)")
    report = LocalPriceAgent().run({"query": "تمور", "market": "ma"})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} conf={f.confidence} note={f.note}")
