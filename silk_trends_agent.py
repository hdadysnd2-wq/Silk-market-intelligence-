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
        try:  # عائلة C (Wave 1.5): إعلان الفشل للمشغّل.
            import silk_ops_log
            silk_ops_log.record_service_failure(
                "trends", f"pytrends fetch failed ('{keyword}', geo={geo}): {e}")
        except Exception:  # noqa: BLE001
            pass
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


def _coerce_trend_value(v: object) -> object:
    """قيمة صف تريندز كما هي — رقم يبقى رقماً، و'Breakout' الصاعدة تبقى نصاً
    (لا تحويلها لرقم مختلَق). None يبقى None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    s = str(v).strip()
    return s or None


def trends_context(keyword: str, geo: str | None = None,
                   timeframe: str = "today 12-m") -> dict:
    """سياق طلب أغنى من بناء حمولة pytrends واحد — R3 (ثقافة المستهلك الأعمق):
    الاستعلامات المرتبطة (الشائعة والصاعدة)، المواضيع الصاعدة، والتوزيع
    الإقليمي للاهتمام.

    كلها من `build_payload` واحد ثم ثلاث قراءات (related_queries/
    related_topics/interest_by_region) — كل قسم مُغلَّف باستثنائه فيتدهور
    **مستقلاً** إلى قائمة فارغة بملاحظة السبب عند غيابه؛ لا اختلاق قط
    (المبدأ المؤسِّس). فشل/غياب pytrends => كل الأقسام فارغة بملاحظة السبب.
    يعيد {"related_top", "related_rising", "topics_rising", "regions",
          "confidence", "note"} — كل بند {"label", "value"}.
    """
    empty = {"related_top": [], "related_rising": [], "topics_rising": [],
             "regions": [], "confidence": 0.0, "note": ""}
    try:
        from pytrends.request import TrendReq  # lazy: optional dep
    except ImportError:
        return {**empty, "note": "pytrends unavailable / no network"}
    kw = (keyword or "").strip()
    if not kw:
        return {**empty, "note": "empty keyword — no query"}
    try:
        py = TrendReq(timeout=(10, 30))
        py.build_payload([kw], timeframe=timeframe, geo=(geo or ""))
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("Trends context payload failed ('%s', geo=%s): %s",
                    keyword, geo, e)
        return {**empty, "note": f"pytrends unavailable / no network: {e}"}

    def _rows(df, label_col: str, n: int = 6) -> list[dict]:
        rows: list[dict] = []
        try:
            if df is None or df.empty:
                return rows
            for _, r in df.head(n).iterrows():
                label = r.get(label_col)
                if label is None:
                    continue
                rows.append({"label": str(label),
                             "value": _coerce_trend_value(r.get("value"))})
        except Exception:  # noqa: BLE001 — قسم واحد يفشل لا يُسقِط البقية
            return []
        return rows

    out = {**empty, "confidence": 0.6}
    found = False
    try:
        rq = (py.related_queries() or {}).get(kw) or {}
        out["related_top"] = _rows(rq.get("top"), "query")
        out["related_rising"] = _rows(rq.get("rising"), "query")
        found = found or bool(out["related_top"] or out["related_rising"])
    except Exception as e:  # noqa: BLE001
        log.warning("related_queries failed ('%s'): %s", kw, e)
    try:
        rt = (py.related_topics() or {}).get(kw) or {}
        out["topics_rising"] = _rows(rt.get("rising"), "topic_title")
        found = found or bool(out["topics_rising"])
    except Exception as e:  # noqa: BLE001
        log.warning("related_topics failed ('%s'): %s", kw, e)
    try:
        reg = py.interest_by_region(resolution="REGION")
        if reg is not None and not reg.empty and kw in reg.columns:
            top = reg.sort_values(kw, ascending=False).head(6)
            out["regions"] = [{"label": str(idx),
                               "value": _coerce_trend_value(row[kw])}
                              for idx, row in top.iterrows()
                              if row[kw]]
            found = found or bool(out["regions"])
    except Exception as e:  # noqa: BLE001
        log.warning("interest_by_region failed ('%s'): %s", kw, e)

    if not found:
        return {**empty, "note":
                f"لا سياق اتجاهات مرتبط لـ'{kw}' (geo={geo or 'WW'})"}
    out["note"] = (f"سياق اتجاهات لـ'{kw}' geo={geo or 'WW'}: "
                   f"{len(out['related_top'])} استعلام شائع، "
                   f"{len(out['related_rising'])} صاعد، "
                   f"{len(out['topics_rising'])} موضوع صاعد، "
                   f"{len(out['regions'])} إقليم")
    return out


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
    PREF_KEY = "trends"

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
