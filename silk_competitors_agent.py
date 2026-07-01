"""وكيل المنافسين لسِلك — Silk competitors agent (المجموعة ج · Group C, V3).

يكتشف العلامات/المنتجات المنافسة الفعلية في السوق المستهدف عبر بحث ويب ديناميكي
(استعلاء يُبنى من المنتج والدولة، لا قاموس منتجات ثابت). بيانات حقيقية فقط: يعيد
نتائج بحث حقيقية (عنوان/مقتطف/رابط) أو None موسوماً عند غياب المفتاح/النتائج —
لا يخترع أسماء علامات (المبدأ التأسيسي).

Discovers real competing brands/products in the target market via a DYNAMIC web
search (query built from the product + country — no hardcoded product list).
Real data only: returns actual search results or a provenance-tagged None when
SEARCH_API_KEY is missing / no results. Never fabricates brand names. Thin,
dynamic wrapper over silk_websearch_agent.web_search.
"""
from __future__ import annotations

import logging

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)


def find_competitors(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """المنافسون في السوق — real competing brands/products via web search.

    Builds a dynamic query and delegates to web_search (which degrades to a
    single provenance-tagged None keyless / on failure). Never fabricates.
    """
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no competitor search", _today())]
    query = f"{product} brands competitors market {country}".strip()
    try:
        from silk_websearch_agent import web_search  # lazy: optional layer
        return web_search(query, num=num)
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("competitor search failed for %r: %s", query, e)
        return [DataPoint(None, "Web Search", 0.0,
                          f"competitor search unavailable: {e}", _today())]


class CompetitorsAgent(Agent):
    """وكيل المنافسين — competing brands/products discovered by dynamic web search."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("CompetitorsAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        """اكتشف المنافسين — real competing brands/products for product+market.

        task keys: product/item, country (name, optional), num (optional).
        Missing product -> failed; keyless/no-results -> failed with None
        (never fabricated brand names).
        """
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot find competitors")
        findings = find_competitors(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا منافسون — no competitor data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} competitor lead(s) for '{product}' {country}".strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk CompetitorsAgent — dynamic web search; graceful None keyless "
          "(no fabricated brands)")
    report = CompetitorsAgent().run({"product": "dates", "country": "Morocco", "num": 3})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} note={f.note}")
