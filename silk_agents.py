"""بنية الوكلاء المتعددة لسِلك — Silk multi-agent structure.

Manager + three research agents + a jury committee. Each agent pulls ONLY real
public data via the data layer; an agent with no real data sets failed=True and
reports it — it never invents findings (founding principle).
"""
from __future__ import annotations

import datetime
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from silk_data_layer import (
    DataPoint,
    comtrade_trade,
    gdp_per_capita,
    population,
    partner_name,
)
from silk_data_layer_v2 import ppp_per_capita, market_competitors

log = logging.getLogger(__name__)


@dataclass
class AgentReport:
    """تقرير وكيل — one agent's findings plus its success flag."""

    agent_name: str
    findings: list[DataPoint] = field(default_factory=list)
    failed: bool = False
    summary: str = ""


class Agent(ABC):
    """وكيل أساس — base research agent; name + abstract run()."""

    def __init__(self, name: str) -> None:
        self.name = name

    @abstractmethod
    def run(self, task: dict) -> AgentReport:
        """نفّذ المهمة — execute the task, returning an AgentReport."""
        raise NotImplementedError


def _real(findings: list[DataPoint]) -> list[DataPoint]:
    """نقاط حقيقية — findings carrying an actual value (value is not None)."""
    return [f for f in findings if f.value is not None]


class BaseAgent(Agent):
    """الفئة الأساس الفارضة — enforces the protocol structurally (wave 2).

    البروتوكول الرباعي كان قواعد تُراجَع؛ هنا يصير بنيةً تُورَث:
      - `PAID = True` خارج سياق `/deepen` = **يستحيل التنفيذ** (تقرير متخطى
        موسوم، بلا أي نداء) — لا يعتمد على حارس يدوي في api.py.
      - استثناء غير متوقع من `_execute` = تقرير فاشل بـ `DataPoint(None,
        note=السبب)` تلقائياً — الفشل الصامت مستحيل بنيوياً.
    الوكلاء الجدد يرثونها ويكتبون `_execute()` فقط؛ القائمون يهاجرون تدريجياً
    (الموجة ٢ تهجّر المدفوعين الثلاثة، والبقية وكيلٌ مع كل PR لاحق).
    """

    PAID: bool = False   # تصنيف إلزامي عند التعريف — مدفوع أم مجاني
    SOURCE: str = ""     # وسم المصدر لنقاط الفشل البنيوية (افتراضه اسم الوكيل)

    def run(self, task: dict) -> AgentReport:
        """نفّذ محروساً — guarded execution; subclasses implement _execute()."""
        import silk_context  # lazy: keeps import graph flat

        src = self.SOURCE or self.name
        if self.PAID and not silk_context.deepen_active():
            note = (f"{self.name}: paid agent outside /deepen — skipped "
                    "(structural guard, no call attempted)")
            log.warning(note)
            return AgentReport(
                self.name,
                [DataPoint(None, src, 0.0, note,
                           datetime.date.today().isoformat())],
                True, note)
        try:
            return self._execute(task)
        except Exception as e:  # noqa: BLE001 — silent failure impossible
            note = f"{self.name} error: {type(e).__name__}: {e}"
            log.warning(note)
            return AgentReport(
                self.name,
                [DataPoint(None, src, 0.0, note,
                           datetime.date.today().isoformat())],
                True, note)

    def _execute(self, task: dict) -> AgentReport:
        """منطق الوكيل الفعلي — the agent's actual logic (subclass hook)."""
        raise NotImplementedError


class TradeFlowAgent(BaseAgent):
    """وكيل تدفّق التجارة — Comtrade import/export size of an HS code in a market."""

    PAID = False

    def __init__(self) -> None:
        super().__init__("TradeFlowAgent")

    def _execute(self, task: dict) -> AgentReport:
        """حجم استيراد/تصدير سلعة في سوق — total trade value from World partner."""
        hs, market, year = task["hs_code"], task["market_m49"], task["year"]
        findings: list[DataPoint] = []
        for flow, label in (("M", "imports"), ("X", "exports")):
            recs = comtrade_trade(hs, market, year, flow=flow, partner=0)
            total = sum(float(r.get("primaryValue") or 0) for r in recs) if recs else None
            if total is None:
                findings.append(DataPoint(
                    None, "UN Comtrade", 0.0,
                    f"HS{hs} {label} for market {market} {year}: no data / fetch failed"))
            else:
                findings.append(DataPoint(
                    total, "UN Comtrade", 0.9,
                    f"HS{hs} total {label} (World) to market {market} {year}, USD"))
        real = _real(findings)
        failed = not real
        summary = ("لا توجد بيانات تجارة — no trade data available"
                   if failed else f"{len(real)} trade flow datum(s) from Comtrade")
        return AgentReport(self.name, findings, failed, summary)


class EconomicAgent(BaseAgent):
    """وكيل اقتصادي — World Bank income (GDP & PPP per capita) + population."""

    PAID = False

    def __init__(self) -> None:
        super().__init__("EconomicAgent")

    def _execute(self, task: dict) -> AgentReport:
        """قياس قوة السوق الاقتصادية — economic profile of the market."""
        iso3, year = task.get("iso3"), task.get("year")
        if not iso3:
            return AgentReport(self.name, [], True,
                               "لا يوجد ISO3 للسوق — no ISO3 for market, cannot query World Bank")
        findings = [gdp_per_capita(iso3, year), ppp_per_capita(iso3, year),
                    population(iso3, year)]
        real = _real(findings)
        failed = not real
        summary = ("لا توجد بيانات اقتصادية — no economic data available"
                   if failed else f"{len(real)}/3 World Bank indicator(s) returned")
        return AgentReport(self.name, findings, failed, summary)


class CompetitionAgent(BaseAgent):
    """وكيل المنافسة — named competitors & shares in the target market."""

    PAID = False
    SOURCE = "UN Comtrade"

    def __init__(self, top_n: int = 5) -> None:
        super().__init__("CompetitionAgent")
        self.top_n = top_n

    def _execute(self, task: dict) -> AgentReport:
        """من يورّد للسوق وبأي حصة — ranked suppliers of the HS code to the market."""
        hs, market, year = task["hs_code"], task["market_m49"], task["year"]
        comps = market_competitors(hs, market, year)
        if not comps:
            return AgentReport(
                self.name,
                [DataPoint(None, "UN Comtrade", 0.0,
                           f"HS{hs} competitors in market {market} {year}: no data / fetch failed")],
                True, "لا توجد بيانات منافسين — no competitor data available")
        findings = comps[: self.top_n]
        return AgentReport(self.name, findings, False,
                           f"top {len(findings)} supplier(s) by import value")


class ResearchManager:
    """مدير البحث — holds the agents and distributes a task to each."""

    def __init__(self, agents: list[Agent] | None = None) -> None:
        self.agents = agents or [TradeFlowAgent(), EconomicAgent(), CompetitionAgent()]

    def distribute(self, task: dict) -> list[AgentReport]:
        """وزّع المهمة — run every agent, collecting their reports (never crashes)."""
        reports: list[AgentReport] = []
        for agent in self.agents:
            try:
                reports.append(agent.run(task))
            except Exception as e:  # noqa: BLE001 — an agent must not crash the run
                log.warning("agent %s raised: %s", agent.name, e)
                reports.append(AgentReport(agent.name, [], True, f"agent error: {e}"))
        return reports


class JuryCommittee:
    """لجنة التحكيم — aggregates reports into a PRELIMINARY entry verdict."""

    @staticmethod
    def evaluate(reports: list[AgentReport]) -> dict:
        """قرار أولي بدخول السوق — explainable, confidence-weighted, flags thin data.

        Returns a dict with verdict, confidence, data_gaps (failed agents),
        and the contributing real findings. Never guesses past missing data.
        """
        contributing = [f for r in reports for f in r.findings if f.value is not None]
        data_gaps = [r.agent_name for r in reports if r.failed]
        n_ok = len(reports) - len(data_gaps)
        # ثقة كلية = متوسط ثقة الأدلة الحقيقية مرجّحًا بتغطية الوكلاء.
        avg_conf = sum(f.confidence for f in contributing) / len(contributing) if contributing else 0.0
        coverage = n_ok / len(reports) if reports else 0.0
        confidence = round(avg_conf * coverage, 2)

        if not contributing:
            verdict = "NO-GO (insufficient data) — قرار مؤجّل لانعدام البيانات"
        elif data_gaps:
            verdict = "PRELIMINARY / INCONCLUSIVE — مبدئي وناقص البيانات"
        else:
            verdict = "PRELIMINARY GO — مبدئي إيجابي"

        return {
            "verdict": verdict,
            "preliminary": True,
            "confidence": confidence,
            "agents_with_data": n_ok,
            "agents_total": len(reports),
            "data_gaps": data_gaps,
            "contributing_findings": contributing,
            "note": ("Preliminary only; missing sources flagged, not estimated. "
                     "تنبيه: قرار مبدئي والنواقص معلّمة لا مُخمّنة."),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk multi-agent run — degrades gracefully offline (no fabricated data)")
    # مهمة واحدة: قطن (HS 5201) إلى الصين 2022 — one product/market.
    task = {"hs_code": "5201", "market_m49": 156, "iso3": "CHN", "year": 2022}
    manager = ResearchManager()
    reports = manager.distribute(task)
    for r in reports:
        flag = "FAILED" if r.failed else "ok"
        print(f"  [{flag}] {r.agent_name}: {r.summary}")
    decision = JuryCommittee.evaluate(reports)
    print(f"  JURY verdict: {decision['verdict']}")
    print(f"        confidence={decision['confidence']} "
          f"coverage={decision['agents_with_data']}/{decision['agents_total']} "
          f"gaps={decision['data_gaps']}")
