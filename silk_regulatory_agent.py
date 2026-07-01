"""وكيلا الاشتراطات والجمارك لسِلك — Silk regulatory & customs agents (المجموعة د · Group D, V3).

وكيلان يعتمدان على بحث ويب ديناميكي (لا قوائم ثابتة):
  • RegulatoryStandardsAgent — اشتراطات التغليف/الملصقات/الشهادات (حلال، صحية، ISO،
    استيراد غذائي…) للمنتج في السوق المستهدف.
  • CustomsInfoAgent — صفحة هيئة الجمارك الرسمية وإجراءات الاستيراد/الرسوم، تكمّل
    نسبة التعريفة المطبّقة من WITS (silk_tariffs_agent) بمرجع رسمي.

المجموعة د تشمل أيضاً وكيلين موجودين مسبقاً: سعر التجزئة (silk_localprice_agent،
عبر with_localprice) والتعريفة المطبّقة % (silk_tariffs_agent، عبر with_tariffs).

بيانات حقيقية فقط: نتائج بحث حقيقية أو None موسوم عند غياب SEARCH_API_KEY/النتائج
— لا تُختلق اشتراطات أو نِسب أو مصادر (المبدأ التأسيسي). أغلفة رفيعة فوق web_search.
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
        log.warning("regulatory/customs search failed for %r: %s", query, e)
        return [DataPoint(None, "Web Search", 0.0,
                          f"search unavailable: {e}", _today())]


def regulatory_standards(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """اشتراطات تنظيمية — packaging/labeling/certification requirements (dynamic search)."""
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no regulatory search", _today())]
    query = (f"{product} import requirements packaging labeling certification "
             f"halal health standards {country}").strip()
    return _search(query, num)


def customs_info(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """معلومات جمركية رسمية — official customs authority / import-duty page (dynamic search)."""
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no customs search", _today())]
    query = (f"official customs authority import duty procedure {product} "
             f"{country}").strip()
    return _search(query, num)


class RegulatoryStandardsAgent(Agent):
    """وكيل الاشتراطات — packaging/labeling/certification requirements (halal/health/ISO)."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("RegulatoryStandardsAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot find standards")
        findings = regulatory_standards(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا اشتراطات — no regulatory data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} regulatory lead(s) for '{product}' {country}".strip())


class CustomsInfoAgent(Agent):
    """وكيل معلومات الجمارك — official customs-authority page (complements WITS tariffs)."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("CustomsInfoAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot find customs info")
        findings = customs_info(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا معلومات جمركية — no customs data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} customs lead(s) for '{product}' {country}".strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk regulatory/customs agents — dynamic web search; graceful None keyless "
          "(no fabricated requirements)")
    for agent in (RegulatoryStandardsAgent(), CustomsInfoAgent()):
        report = agent.run({"product": "dates", "country": "UAE", "num": 3})
        flag = "FAILED" if report.failed else "ok"
        print(f"  [{flag}] {report.agent_name}: {report.summary}")
