"""وكيل البحث على الويب لسِلك — Silk web-search research agent (docx layer 7).

Pulls real public web results (consumer-behaviour reports, market news) via a
configurable search API. Default provider is Serper.dev (Google Search API).
Requires SEARCH_API_KEY in the environment / .env. On missing key, network
failure, or empty results it returns a provenance-tagged None — it never
fabricates titles, snippets, or links (founding principle).

Env:
  SEARCH_API_KEY   — required API key (e.g. a Serper.dev key).
  SEARCH_PROVIDER  — optional; 'serper' (default) is the only implemented
                     provider. Others are documented TODO and degrade to failed.
"""
from __future__ import annotations

import logging
import os

from silk_data_layer import DataPoint, _today
from silk_agents import BaseAgent, AgentReport

log = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"
_TIMEOUT = 30


def search_key() -> str:
    """مفتاح بحث الويب — SEARCH_API_KEY أو الاسم الشائع SERPER_API_KEY.

    P5: مفتاح مضبوط تحت الاسم الشائع (SERPER_API_KEY) كان يُهمَل بصمت
    فتظلم طبقة قوقل كلها رغم وجود المفتاح — القبول بالاسمين يغلق الفخ.
    SEARCH_API_KEY يبقى الأعلى سلطة عند وجود الاثنين.
    """
    return (os.environ.get("SEARCH_API_KEY", "").strip()
            or os.environ.get("SERPER_API_KEY", "").strip())


def web_search(query: str, num: int = 5) -> list[DataPoint]:
    """بحث ويب — organic web results as DataPoints (consumer/market signals).

    Standalone helper. Provider chosen by SEARCH_PROVIDER (default 'serper').
    Returns a list of DataPoint(value={"title","snippet","link"}) on success, or
    a single DataPoint(value=None, confidence=0.0) when the key is missing /
    provider unsupported / network fails / no results. Never raises, never invents.
    """
    q = (query or "").strip()
    if not q:
        return [DataPoint(None, "Web Search", 0.0, "empty query — no search", _today())]

    provider = os.environ.get("SEARCH_PROVIDER", "serper").strip().lower() or "serper"
    if provider != "serper":
        # TODO: implement other providers (e.g. serpapi, bing). Only 'serper' works.
        log.warning("SEARCH_PROVIDER '%s' not implemented — only 'serper' supported", provider)
        return [DataPoint(None, f"Web Search ({provider})", 0.0,
                          f"provider '{provider}' not implemented (TODO); set SEARCH_PROVIDER=serper",
                          _today())]

    key = search_key()
    if not key:
        log.warning("SEARCH_API_KEY not set — web search unavailable")
        return [DataPoint(None, "Web Search (Serper)", 0.0,
                          "requires SEARCH_API_KEY (or SERPER_API_KEY)", _today())]

    try:
        import requests  # lazy: import works offline/keyless
        resp = requests.post(
            _SERPER_URL,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json={"q": q, "num": int(num)},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        organic = (resp.json() or {}).get("organic") or []
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("Web search fetch failed ('%s'): %s", q, e)
        return [DataPoint(None, "Web Search (Serper)", 0.0,
                          f"serper unavailable / no network: {e}", _today())]

    if not organic:
        return [DataPoint(None, "Web Search (Serper)", 0.0,
                          f"no results for '{q}'", _today())]

    findings: list[DataPoint] = []
    for item in organic[: int(num)]:
        findings.append(DataPoint(
            {"title": item.get("title", ""),
             "snippet": item.get("snippet", ""),
             "link": item.get("link", "")},
            "Web Search (Serper)", 0.5,
            f"organic result for '{q}'", _today()))
    return findings


_CURRENCY_SYMBOLS = {
    "$": "USD", "€": "EUR", "£": "GBP", "﷼": "SAR", "USD": "USD",
    "SAR": "SAR", "AED": "AED", "EUR": "EUR", "GBP": "GBP", "KWD": "KWD",
    "QAR": "QAR", "OMR": "OMR", "BHD": "BHD", "JOD": "JOD", "EGP": "EGP",
    "YER": "YER", "درهم": "AED", "ريال": "SAR", "جنيه": "EGP",
}


def _parse_price(raw: str) -> tuple[float | None, str | None]:
    """حلّل نص سعر Serper Shopping المنظَّم — رقم واضح + عملة إن ظهرت.

    لا تخمين: سلسلة بلا رقم واضح => (None, None) فيُسقِطها المستدعي؛ الخام
    (raw) يبقى محفوظاً دوماً بجانب أي قيمة مُحلَّلة للتحقق اليدوي.
    """
    import re
    if not raw:
        return None, None
    m = re.search(r"[\d,]+\.?\d*", raw)
    if not m:
        return None, None
    try:
        amount = float(m.group(0).replace(",", ""))
    except ValueError:
        return None, None
    currency = next((code for sym, code in _CURRENCY_SYMBOLS.items()
                     if sym in raw), None)
    return amount, currency


def web_search_shopping(query: str, gl: str | None = None,
                        num: int = 5) -> list[DataPoint]:
    """أسعار تجزئة منظّمة من فهرس Google Shopping (عبر Serper) — أي منصة
    تفهرسها Google لكل دولة (`gl`، رمز ISO 3166-1 alpha-2)، لا منصة مفروضة
    واحدة (طلب مالك: "اي سعر في اي منصة حسب كل دولة").

    السعر يأتي من حقل `price` المنظَّم في نتيجة التسوق نفسها — لا استخراج
    آلي من عنوان صفحة حرّ (الفرق عن `web_search`/`retail_references`). سلسلة
    بلا رقم واضح تُسقَط لا تُخمَّن؛ الخام (`price_raw`) يبقى محفوظاً دوماً.
    نفس مفتاح SEARCH_API_KEY ونفس نداء `/search` — صفر تكامل جديد.
    """
    q = (query or "").strip()
    if not q:
        return [DataPoint(None, "Web Search (Serper Shopping)", 0.0,
                          "empty query — no search", _today())]
    key = search_key()
    if not key:
        return [DataPoint(None, "Web Search (Serper Shopping)", 0.0,
                          "requires SEARCH_API_KEY (or SERPER_API_KEY)", _today())]
    try:
        import requests  # lazy: import works offline/keyless
        body = {"q": q, "num": int(num)}
        if gl:
            body["gl"] = str(gl).lower()
        resp = requests.post(
            _SERPER_URL,
            headers={"X-API-KEY": key, "Content-Type": "application/json"},
            json=body, timeout=_TIMEOUT)
        resp.raise_for_status()
        shopping = (resp.json() or {}).get("shopping") or []
    except Exception as e:  # noqa: BLE001 — never raise to caller
        log.warning("Serper shopping fetch failed ('%s'): %s", q, e)
        return [DataPoint(None, "Web Search (Serper Shopping)", 0.0,
                          f"serper shopping unavailable / no network: {e}",
                          _today())]
    if not shopping:
        return [DataPoint(None, "Web Search (Serper Shopping)", 0.0,
                          f"no shopping results for '{q}'"
                          + (f" gl={gl}" if gl else ""), _today())]
    findings: list[DataPoint] = []
    for item in shopping[: int(num)]:
        raw_price = item.get("price", "")
        amount, currency = _parse_price(raw_price)
        if amount is None:
            continue  # لا رقم رسمي واضح في هذه القائمة — تُسقَط لا تُخمَّن
        findings.append(DataPoint(
            {"title": item.get("title", ""), "price": amount,
             "currency": currency, "price_raw": raw_price,
             "store": item.get("source", ""), "link": item.get("link", "")},
            "Web Search (Serper Shopping)", 0.6,
            f"listing for '{q}'" + (f" gl={gl}" if gl else ""), _today()))
    if not findings:
        return [DataPoint(None, "Web Search (Serper Shopping)", 0.0,
                          f"shopping results found but no parseable price "
                          f"for '{q}'" + (f" gl={gl}" if gl else ""), _today())]
    return findings


class WebSearchAgent(BaseAgent):
    """وكيل البحث على الويب — consumer-behaviour / reports / news signals.

    هاجر إلى BaseAgent (قاعدة "وكيل مع كل PR" — الموجة ٣): PAID=False،
    والفشل الصامت مستحيل بنيوياً.
    """

    PAID = False
    PREF_KEY = "consumer"
    SOURCE = "Web Search (Serper)"

    def __init__(self) -> None:
        super().__init__("WebSearchAgent")

    def _execute(self, task: dict) -> AgentReport:
        """نتائج بحث حقيقية للمنتج والسوق — real web results, real data only.

        task keys: query(str, product+market+intent), num(int, default 5).
        """
        query = task.get("query", "")
        num = task.get("num", 5)
        findings = web_search(query, num)
        real = [f for f in findings if f.value is not None]
        if not real:
            reason = findings[0].note if findings else "no results"
            return AgentReport(self.name, findings, True,
                               f"لا توجد نتائج بحث — no web search results ({reason})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} web result(s) for '{query}'")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk WebSearchAgent — degrades gracefully offline / without SEARCH_API_KEY (no fabricated data)")
    report = WebSearchAgent().run(
        {"query": "Saudi Arabia dates consumer demand 2024", "num": 3})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} conf={f.confidence} note={f.note}")
