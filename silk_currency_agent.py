"""وكيل مخاطر العملة لسِلك — Silk currency-risk agent (المجموعة ب · Group B, V3).

إشارات استقرار العملة/الأسعار في السوق المستهدف من البنك الدولي (بيانات حيّة
حقيقية): التضخم السنوي (أسعار المستهلك) وسعر الصرف الرسمي مقابل الدولار. هذه
مؤشّرات لمخاطر التسعير والتحويل عند التصدير. التصنيف الائتماني السيادي غير متاح
مجاناً عبر البنك الدولي، فلا يُختلق — يُعاد None موسوماً يوضّح أنه يحتاج مصدراً
خارجياً (وكالة تصنيف/بحث).

Currency/price-stability signals for the target market from the World Bank
(real live data): annual inflation (consumer prices) and the official exchange
rate vs. USD — both proxies for export pricing/FX risk. A sovereign credit
rating is NOT available free via the World Bank, so it is never fabricated: a
provenance-tagged None explains it needs an external source. Degrades gracefully
offline (all findings None), never invents a number.
"""
from __future__ import annotations

import logging

from silk_data_layer import DataPoint, world_bank, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)

# مؤشرات البنك الدولي — World Bank indicator codes.
_INFLATION = "FP.CPI.TOTL.ZG"      # Inflation, consumer prices (annual %)
_FX_RATE = "PA.NUS.FCRF"           # Official exchange rate (LCU per US$, avg)


def currency_signals(iso3: str, year: int | None = None) -> list[DataPoint]:
    """إشارات مخاطر العملة — inflation + official FX rate + (unavailable) rating.

    Returns a list of DataPoints: inflation (%, World Bank), official exchange
    rate (LCU/US$, World Bank), and a credit-rating placeholder that is always
    value=None (not free via World Bank; never fabricated). Offline -> the two
    World Bank findings degrade to None too, each provenance-tagged.
    """
    inflation = world_bank(iso3, _INFLATION, year)
    if inflation.value is not None:
        inflation.note = f"inflation, consumer prices annual % ({inflation.note})"
    fx = world_bank(iso3, _FX_RATE, year)
    if fx.value is not None:
        fx.note = f"official exchange rate LCU/US$ ({fx.note})"
    rating = DataPoint(
        None, "Credit rating agency (not wired)", 0.0,
        "sovereign credit rating unavailable via World Bank free API — "
        "requires an external source (rating agency / paid search); not fabricated",
        _today())
    return [inflation, fx, rating]


class CurrencyRiskAgent(Agent):
    """وكيل مخاطر العملة — inflation + FX-rate stability signals (World Bank)."""

    def __init__(self) -> None:
        super().__init__("CurrencyRiskAgent")

    def run(self, task: dict) -> AgentReport:
        """إشارات مخاطر العملة للسوق — real currency/price-stability signals.

        task keys: iso3/country, year (optional). Missing iso3 -> failed report;
        credit rating is always reported as unavailable (never fabricated).
        """
        iso3 = task.get("iso3") or task.get("country")
        year = task.get("year")
        if not iso3:
            return AgentReport(self.name, [], True,
                               "لا يوجد ISO3 — missing iso3/country, cannot assess currency risk")
        findings = currency_signals(str(iso3), year)
        real = [f for f in findings if f.value is not None]
        failed = not real
        summary = ("لا بيانات عملة — no currency signals available (best-effort)"
                   if failed else f"{len(real)} currency signal(s) from World Bank for {iso3}")
        return AgentReport(self.name, findings, failed, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk CurrencyRiskAgent — live World Bank signals; degrades gracefully "
          "offline; credit rating never fabricated")
    report = CurrencyRiskAgent().run({"iso3": "EGY", "year": 2022})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} conf={f.confidence} note={f.note}")
