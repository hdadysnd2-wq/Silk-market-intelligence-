"""وكيل اتجاهات جوجل لسِلك — Silk Google Trends research agent (README step 4).

Pulls real public interest-over-time from Google Trends via pytrends (an OPTIONAL
dep, imported lazily). If pytrends is missing OR the network fails, returns a
provenance-tagged None — it never fabricates interest values (founding principle).

Optional dependency: pytrends  (pip install pytrends). Not imported at module top.
"""
from __future__ import annotations

import calendar
import logging

from silk_data_layer import DataPoint, _today
from silk_agents import BaseAgent, AgentReport

log = logging.getLogger(__name__)


def trends_interest(
    keyword: str,
    geo: str | None = None,
    timeframe: str = "today 12-m",
) -> DataPoint:
    """اهتمام جوجل تريندز — mean search interest 0-100 for a keyword.

    Standalone helper. Returns DataPoint(value=mean interest) on success, or
    DataPoint(value=None, confidence=0.0) if pytrends missing / network fails.
    The raw monthly series is stashed in DataPoint.note for the seasonality step.
    """
    try:
        from pytrends.request import TrendReq  # lazy: optional dep
    except ImportError:
        log.warning("pytrends not installed — trends interest unavailable")
        return DataPoint(None, "Google Trends", 0.0,
                         "pytrends unavailable / no network", _today())
    try:
        kw = (keyword or "").strip()
        if not kw:
            return DataPoint(None, "Google Trends", 0.0,
                             "empty keyword — no query", _today())
        py = TrendReq(timeout=(10, 30))
        py.build_payload([kw], timeframe=timeframe,
                         geo=(geo or ""))
        df = py.interest_over_time()
        if df is None or df.empty or kw not in df.columns:
            return DataPoint(None, "Google Trends", 0.0,
                             f"no interest data for '{kw}' (geo={geo or 'WW'})", _today())
        series = df[kw]
        mean = round(float(series.mean()), 1)
        return DataPoint(mean, "Google Trends", 0.7,
                         f"mean interest 0-100 for '{kw}' geo={geo or 'WW'} "
                         f"tf='{timeframe}' n={len(series)}", _today())
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("Google Trends fetch failed ('%s', geo=%s): %s", keyword, geo, e)
        return DataPoint(None, "Google Trends", 0.0,
                         f"pytrends unavailable / no network: {e}", _today())


def trends_series(keyword: str, geo: str | None = None,
                  timeframe: str = "today 12-m") -> dict:
    """سلسلة اهتمام + نمو من نداء pytrends واحد — Stage 3 المرحلة ٢ (§7).

    نداء واحد فقط (حارس ميزانية: لا يُضاعف استهلاك pytrends المحدود أصلاً —
    لاحظنا 429 حياً)؛ يُستخرَج منه المتوسط (كما `trends_interest`) **و**نسبة
    نمو الاتجاه (الربع الأول مقابل الربع الأخير من السلسلة نفسها، بنفس منطق
    `silk_trend.growth_pct` لكن على إشارة بحث لا تجارة). أقل من 4 نقاط
    مرصودة => `growth_pct=None` بصدق، لا تخمين. فشل/غياب pytrends =>
    القيم كلها None بملاحظة السبب — لا اختلاق.
    """
    try:
        from pytrends.request import TrendReq  # lazy: optional dep
    except ImportError:
        return {"mean": None, "growth_pct": None, "n": 0, "confidence": 0.0,
                "note": "pytrends unavailable / no network"}
    kw = (keyword or "").strip()
    if not kw:
        return {"mean": None, "growth_pct": None, "n": 0, "confidence": 0.0,
                "note": "empty keyword — no query"}
    try:
        py = TrendReq(timeout=(10, 30))
        py.build_payload([kw], timeframe=timeframe, geo=(geo or ""))
        df = py.interest_over_time()
        if df is None or df.empty or kw not in df.columns:
            return {"mean": None, "growth_pct": None, "n": 0, "confidence": 0.0,
                    "note": f"no interest data for '{kw}' (geo={geo or 'WW'})"}
        series = df[kw]
        n = len(series)
        mean = round(float(series.mean()), 1)
        growth = None
        if n >= 4:
            q = max(1, n // 4)
            first_q, last_q = float(series.iloc[:q].mean()), float(series.iloc[-q:].mean())
            if first_q > 0:
                growth = round(100.0 * (last_q - first_q) / first_q, 1)
        return {"mean": mean, "growth_pct": growth, "n": n, "confidence": 0.7,
                "note": f"متوسط اهتمام 0-100 لـ'{kw}' geo={geo or 'WW'} "
                        f"tf='{timeframe}' n={n}"
                        + (f"؛ نمو الربع الأول↔الأخير {growth}%" if growth is not None
                           else "؛ سلسلة أقصر من 4 نقاط — لا نمو محسوب")}
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("Google Trends series fetch failed ('%s', geo=%s): %s",
                    keyword, geo, e)
        return {"mean": None, "growth_pct": None, "n": 0, "confidence": 0.0,
                "note": f"pytrends unavailable / no network: {e}"}


def _seasonality(keyword: str, geo: str | None, timeframe: str) -> DataPoint:
    """موسمية بسيطة — peak month of search interest over the timeframe."""
    try:
        from pytrends.request import TrendReq  # lazy: optional dep
    except ImportError:
        return DataPoint(None, "Google Trends", 0.0,
                         "pytrends unavailable / no network", _today())
    try:
        kw = (keyword or "").strip()
        py = TrendReq(timeout=(10, 30))
        py.build_payload([kw], timeframe=timeframe, geo=(geo or ""))
        df = py.interest_over_time()
        if df is None or df.empty or kw not in df.columns:
            return DataPoint(None, "Google Trends", 0.0,
                             f"no series for seasonality of '{kw}'", _today())
        monthly = df[kw].groupby(df.index.month).mean()
        peak_month = int(monthly.idxmax())
        return DataPoint(peak_month, "Google Trends", 0.6,
                         f"peak interest month = {calendar.month_name[peak_month]} "
                         f"for '{kw}' geo={geo or 'WW'}", _today())
    except Exception as e:  # noqa: BLE001
        log.warning("Google Trends seasonality failed ('%s'): %s", keyword, e)
        return DataPoint(None, "Google Trends", 0.0,
                         f"pytrends unavailable / no network: {e}", _today())


class TrendsAgent(BaseAgent):
    """وكيل الاتجاهات — Google Trends demand signal for a product keyword."""

    PAID = False

    def __init__(self) -> None:
        super().__init__("TrendsAgent")

    def _execute(self, task: dict) -> AgentReport:
        """إشارة الطلب من بحث جوجل — mean interest + seasonality, real data only.

        task keys: keyword(str), geo(ISO2 like 'AE'/'SA', optional),
                   timeframe(default 'today 12-m').
        """
        keyword = task.get("keyword", "")
        geo = task.get("geo")
        timeframe = task.get("timeframe", "today 12-m")

        interest = trends_interest(keyword, geo, timeframe)
        if interest.value is None:
            return AgentReport(self.name, [interest], True,
                               "لا توجد بيانات اتجاهات — no Google Trends data available")
        season = _seasonality(keyword, geo, timeframe)
        findings = [interest, season] if season.value is not None else [interest]
        return AgentReport(self.name, findings, False,
                           f"interest={interest.value}/100 for '{keyword}' (geo={geo or 'WW'})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk TrendsAgent — degrades gracefully offline / without pytrends (no fabricated data)")
    report = TrendsAgent().run({"keyword": "تمور", "geo": "AE"})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} conf={f.confidence} note={f.note}")
