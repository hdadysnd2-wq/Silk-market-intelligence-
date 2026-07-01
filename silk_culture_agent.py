"""وكلاء الثقافة والسلوك التجاري لسِلك — Silk culture & business agents (المجموعة هـ · Group E, V3).

ثلاثة وكلاء يعتمدون على بحث ويب ديناميكي (لا قوائم ثابتة):
  • CulturalAgent        — عادات الاستهلاك وأسلوب الحياة المرتبط بالمنتج في السوق.
  • BusinessCultureAgent — أعراف التفاوض التجاري وشروط الدفع وآداب العمل في السوق.
  • ExhibitionsAgent     — أبرز المعارض التجارية لفئة المنتج في السوق المستهدف.

المجموعة هـ تشمل أيضاً trends_agent الموجود مسبقاً (Google Trends عبر with_trends).

بيانات حقيقية فقط: نتائج بحث حقيقية أو None موسوم عند غياب SEARCH_API_KEY/النتائج
— لا تُختلق رؤى ثقافية أو أعراف أو معارض (المبدأ التأسيسي). أغلفة رفيعة ديناميكية
فوق silk_websearch_agent.web_search.
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
        log.warning("culture/business search failed for %r: %s", query, e)
        return [DataPoint(None, "Web Search", 0.0,
                          f"search unavailable: {e}", _today())]


def consumer_culture(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """عادات الاستهلاك — consumption habits / lifestyle around the product (dynamic search)."""
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no cultural search", _today())]
    query = (f"{product} consumer habits preferences lifestyle culture {country}").strip()
    return _search(query, num)


def business_culture(country: str = "", product: str = "", num: int = 5) -> list[DataPoint]:
    """السلوك التجاري — negotiation norms, payment terms, business etiquette (dynamic search)."""
    country = (country or "").strip()
    if not country:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty market — no business-culture search", _today())]
    query = (f"business culture negotiation payment terms trade etiquette "
             f"importers {product} {country}").strip()
    return _search(query, num)


def exhibitions(product: str, country: str = "", num: int = 5) -> list[DataPoint]:
    """المعارض التجارية — major trade fairs/exhibitions for the category (dynamic search)."""
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Web Search", 0.0,
                          "empty product — no exhibitions search", _today())]
    query = (f"{product} trade fair exhibition expo {country}").strip()
    return _search(query, num)


class CulturalAgent(Agent):
    """وكيل الثقافة الاستهلاكية — consumption habits / lifestyle (dynamic web search)."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("CulturalAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot research culture")
        findings = consumer_culture(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا رؤى ثقافية — no cultural data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} cultural lead(s) for '{product}' {country}".strip())


class BusinessCultureAgent(Agent):
    """وكيل السلوك التجاري — negotiation/payment/etiquette norms (dynamic web search)."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("BusinessCultureAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        country = task.get("country") or ""
        product = task.get("product") or task.get("item") or ""
        num = int(task.get("num", self.num))
        if not country:
            return AgentReport(self.name, [], True,
                               "لا يوجد سوق — missing country, cannot research business culture")
        findings = business_culture(str(country), str(product), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا أعراف تجارية — no business-culture data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} business-culture lead(s) for {country}")


class ExhibitionsAgent(Agent):
    """وكيل المعارض — major trade fairs/exhibitions for the category (dynamic web search)."""

    def __init__(self, num: int = 5) -> None:
        super().__init__("ExhibitionsAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        product = task.get("product") or task.get("item")
        country = task.get("country") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot find exhibitions")
        findings = exhibitions(str(product), str(country), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا معارض — no exhibitions data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} exhibition lead(s) for '{product}' {country}".strip())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk culture/business agents — dynamic web search; graceful None keyless")
    print("  cultural:", CulturalAgent().run({"product": "dates", "country": "UAE"}).summary)
    print("  business:", BusinessCultureAgent().run({"country": "UAE", "product": "dates"}).summary)
    print("  exhibitions:", ExhibitionsAgent().run({"product": "dates", "country": "UAE"}).summary)
