"""وكيلا التوزيع لسِلك — Silk distribution agents (المجموعة ج · Group C, V3).

وكيلان يعتمدان على بحث ويب ديناميكي (لا قوائم ثابتة):
  • DistributionChannelsAgent — أكبر سلاسل التجزئة/الموزّعين للفئة بالسوق المستهدف.
  • EcommerceLandscapeAgent   — منصّات التجارة الإلكترونية المهيمنة على الفئة بالسوق
    (تُغذّي لاحقاً وكيل الأكثر مبيعاً بتحديد المنصّات الصحيحة).

بيانات حقيقية فقط: نتائج بحث حقيقية أو None موسوم عند غياب المفتاح/النتائج — لا
اختلاق لأسماء متاجر أو منصّات. أغلفة رفيعة ديناميكية فوق web_search.

Two dynamic web-search agents (no hardcoded lists): the biggest retail
chains/distributors for the category in the target market, and the dominant
e-commerce platforms there (the latter feeds bestsellers_agent by naming the
right platforms). Real data only; never fabricates a store/platform name.
"""
from __future__ import annotations

import logging

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)


def _search(query: str, num: int) -> list[DataPoint]:
    """بحث آمن — delegate to web_search, degrade to a tagged None on any failure."""
    try:
        from silk_websearch_agent import web_search  # lazy: optional layer
        return web_search(query, num=num)
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("distribution search failed for %r: %s", query, e)
        return [DataPoint(None, "Web Search", 0.0,
                          f"distribution search unavailable: {e}", _today())]


def distribution_channels(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """قنوات التوزيع — biggest retail chains / distributors for the category+market."""
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no distribution search", _today())]
    return _search(f"largest retail chains distributors {product} {country}".strip(), num)


def ecommerce_platforms(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """منصّات التجارة الإلكترونية — dominant e-commerce platforms for the category+market."""
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no e-commerce search", _today())]
    return _search(f"top e-commerce platforms to buy {product} online {country}".strip(), num)


class DistributionChannelsAgent(Agent):
    """وكيل قنوات التوزيع — biggest retail chains / distributors (dynamic web search)."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("DistributionChannelsAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot find channels")
        findings = distribution_channels(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا قنوات توزيع — no distribution data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} distribution lead(s) for '{product}' {country}".strip())


class EcommerceLandscapeAgent(Agent):
    """وكيل مشهد التجارة الإلكترونية — dominant online platforms (dynamic web search)."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("EcommerceLandscapeAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot map e-commerce")
        findings = ecommerce_platforms(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا منصّات — no e-commerce data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} e-commerce lead(s) for '{product}' {country}".strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk distribution agents — dynamic web search; graceful None keyless")
    for agent in (DistributionChannelsAgent(), EcommerceLandscapeAgent()):
        report = agent.run({"product": "dates", "country": "UAE", "num": 3})
        flag = "FAILED" if report.failed else "ok"
        print(f"  [{flag}] {report.agent_name}: {report.summary}")
