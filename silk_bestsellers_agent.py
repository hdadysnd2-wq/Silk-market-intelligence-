"""وكيل الأكثر مبيعاً لسِلك — Silk best-sellers agent (المجموعة ج · Group C, V3).

يجلب ترتيب المنتجات الأكثر مبيعاً في متاجر التجزئة المحلية (أمازون، نون، جوميا…)
للفئة بالسوق المستهدف — ترتيب فعلي لا نطاق سعر فقط.

⚠️ تنبيه قانوني (docx): السكرابينغ المباشر لصفحات أمازون/نون قد يخالف شروط الخدمة.
لذلك هذا الوكيل **لا يسكرَب مباشرةً بكودنا إطلاقاً**؛ بل يستدعي **مُشغّل Apify
مرخّصاً** (actor جاهز لهذي المنصّات) عبر APIFY_API_TOKEN + APIFY_BESTSELLERS_ACTOR.
بلا التوكن لا تُجرى أي محاولة شبكة، ويُعاد None موسوم يوضّح المتطلّب والقيد القانوني.
الترتيب/الأسماء تُقرأ فقط من ردّ المُشغّل الحقيقي ولا تُختلق أبداً (المبدأ التأسيسي).

Fetches the actual best-seller RANKING of competing products on local retail
platforms for the category+market. Legal note (from the spec): direct scraping
of Amazon/Noon likely violates their ToS, so this agent NEVER scrapes in our own
code — it calls a LICENSED Apify actor (APIFY_API_TOKEN + APIFY_BESTSELLERS_ACTOR)
built for those platforms. Without the token no network call is made and a
provenance-tagged None explains the requirement + legal constraint. Ranks/names
are read only from the real actor response, never fabricated.
"""
from __future__ import annotations

import logging
import os

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)

_APIFY_BASE = "https://api.apify.com/v2/acts"
_TIMEOUT = 90
_NO_TOKEN_NOTE = (
    "best-sellers require APIFY_API_TOKEN + a LICENSED marketplace scraper "
    "(APIFY_BESTSELLERS_ACTOR); direct scraping of Amazon/Noon/Jumia may violate "
    "their ToS and is never performed in-code")


def best_sellers(product: str, market: str, platform: str = "",
                 num: int = 10) -> list[DataPoint]:
    """الأكثر مبيعاً — ranked best-selling competing products via a licensed Apify actor.

    No APIFY_API_TOKEN / no configured actor -> a single provenance-tagged None
    (no network call). With both, runs the actor defensively and parses ranked
    items; on any error / empty / format change -> provenance-tagged None.
    Product names and ranks come only from the real response — never fabricated.
    """
    token = os.environ.get("APIFY_API_TOKEN", "").strip()
    actor = os.environ.get("APIFY_BESTSELLERS_ACTOR", "").strip()
    if not token or not actor:
        log.warning("APIFY not configured — best-sellers unavailable (licensed scraper required)")
        return [DataPoint(None, "Best-sellers (Apify)", 0.0, _NO_TOKEN_NOTE, _today())]
    product = (product or "").strip()
    if not product:
        return [DataPoint(None, "Best-sellers (Apify)", 0.0,
                          "empty product — no best-seller lookup", _today())]
    try:
        import requests  # lazy: only needed when a token is present
    except ImportError as e:  # pragma: no cover — requests is a core dep
        return [DataPoint(None, "Best-sellers (Apify)", 0.0,
                          f"requests unavailable: {e}", _today())]

    # نقطة تشغيل متزامنة تُعيد عناصر مجموعة البيانات مباشرةً — run-sync dataset items.
    url = f"{_APIFY_BASE}/{actor}/run-sync-get-dataset-items"
    payload = {"product": product, "market": market, "platform": platform,
               "maxItems": int(num)}
    try:
        r = requests.post(url, params={"token": token}, json=payload, timeout=_TIMEOUT)
        r.raise_for_status()
        items = r.json()
    except Exception as e:  # noqa: BLE001 — opaque paid API; never raise
        note = f"best-sellers fetch failed for '{product}' in {market}: {type(e).__name__}: {e}"
        log.warning(note)
        return [DataPoint(None, "Best-sellers (Apify)", 0.0, note, _today())]

    parsed = _parse_items(items, num)
    if not parsed:
        return [DataPoint(None, "Best-sellers (Apify)", 0.0,
                          f"best-sellers: no ranked items parsed for '{product}' in {market}",
                          _today())]
    return [
        DataPoint(it, "Best-sellers (Apify)", 0.7,
                  f"#{it.get('rank')} {it.get('title')}"
                  + (f" @ {it['price']}" if it.get("price") is not None else "")
                  + (f" ({it['platform']})" if it.get("platform") else ""),
                  _today())
        for it in parsed
    ]


def _parse_items(items: object, num: int) -> list[dict]:
    """استخراج العناصر المرتّبة — pull ranked best-seller items from an actor reply.

    Actor output shapes vary; probe common fields defensively. Rank falls back to
    list order (1-based) ONLY when the item carries no explicit rank — order is a
    real signal from the source, not an invented figure. Returns [] if nothing
    parseable. Never invents a title.
    """
    if isinstance(items, dict):
        rows = items.get("items") or items.get("data") or items.get("results") or []
    elif isinstance(items, list):
        rows = items
    else:
        rows = []

    out: list[dict] = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        title = (row.get("title") or row.get("name") or row.get("productName") or "")
        title = str(title).strip()
        if not title:
            continue
        rank = row.get("rank") or row.get("bestSellerRank") or row.get("position") or i
        try:
            rank = int(rank)
        except (TypeError, ValueError):
            rank = i
        out.append({
            "rank": rank,
            "title": title,
            "price": row.get("price") if row.get("price") not in ("", None) else None,
            "currency": row.get("currency"),
            "platform": row.get("platform") or row.get("source") or row.get("store"),
            "link": row.get("url") or row.get("link"),
        })
        if len(out) >= max(1, num):
            break
    out.sort(key=lambda d: d["rank"])
    return out


class BestsellersAgent(Agent):
    """وكيل الأكثر مبيعاً — ranked best-sellers via a LICENSED Apify actor (no raw scraping)."""

    def __init__(self, num: int = 10) -> None:
        super().__init__("BestsellersAgent")
        self.num = num

    def run(self, task: dict) -> AgentReport:
        """رتّب الأكثر مبيعاً — real best-seller ranking for product+market.

        task keys: product/item, market (ccTLD/country), platform (optional),
        num (optional). No token / no actor -> failed report with a clear
        requirement+legal note; never a fabricated ranking.
        """
        product = task.get("product") or task.get("item")
        market = task.get("market") or task.get("iso2") or task.get("country") or ""
        platform = task.get("platform") or ""
        num = int(task.get("num", self.num))
        if not product:
            return AgentReport(self.name, [], True,
                               "لا يوجد منتج — missing product, cannot rank best-sellers")
        findings = best_sellers(str(product), str(market), str(platform), num)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "unavailable"
            return AgentReport(self.name, findings, True,
                               f"لا بيانات الأكثر مبيعاً — no best-seller data ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} best-seller(s) for '{product}' in {market}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk BestsellersAgent — LICENSED Apify actor only (no raw scraping); "
          "degrades gracefully without APIFY_API_TOKEN (no fabricated ranks)")
    report = BestsellersAgent().run({"product": "dates", "market": "ae"})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} note={f.note}")
