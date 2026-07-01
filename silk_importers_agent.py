"""وكيل المستوردين لسِلك — Silk importers agent (المجموعة ج · Group C, V3).

يكتشف مستوردين/موزّعين محتملين للفئة في السوق المستهدف عبر **بحث ويب مجاني**
(استعلاء ديناميكي من المنتج والدولة) — best-effort مجاني كما نصّت مواصفة V3
لمجموعة ج، لا أداة مدفوعة. النسخة المدفوعة الأدقّ (Volza، بوالص الشحن) تبقى
حصراً في طبقة «تعميق التحليل» (/deepen).

بيانات حقيقية فقط: نتائج بحث حقيقية أو None موسوم عند غياب SEARCH_API_KEY/النتائج
— لا يخترع أسماء شركات (المبدأ التأسيسي). غلاف رفيع فوق silk_websearch_agent.
"""
from __future__ import annotations

import logging

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)


def find_importers(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """المستوردون في السوق — likely importers/distributors via FREE web search.

    Dynamic query delegated to web_search (degrades to a provenance-tagged None
    keyless / on failure). Never fabricates a company name.
    """
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no importer search", _today())]
    query = f"{product} importers distributors wholesale buyers {country}".strip()
    try:
        from silk_websearch_agent import web_search  # lazy: optional layer
        return web_search(query, num=num)
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("importer search failed for %r: %s", query, e)
        return [DataPoint(None, "Web Search", 0.0,
                          f"importer search unavailable: {e}", _today())]


class ImportersAgent(Agent):
    """وكيل المستوردين — likely importers/distributors via FREE dynamic web search.

    The free Group-C counterpart to the PAID Volza layer (which stays deepen-only).
    """

    def __init__(self, num: int = 5) -> None:
        super().__init__("ImportersAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        """اكتشف المستوردين — real importer/distributor leads for product+market.

        task keys: product/item, country (name, optional), num (optional).
        Missing product -> failed; keyless/no-results -> failed with None
        (never fabricated company names).
        """
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot find importers")
        findings = find_importers(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا مستوردون — no importer data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} importer lead(s) for '{product}' {country}".strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk ImportersAgent — FREE web search; graceful None keyless "
          "(paid Volza stays deepen-only; no fabricated companies)")
    report = ImportersAgent().run({"product": "dates", "country": "Morocco", "num": 3})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
