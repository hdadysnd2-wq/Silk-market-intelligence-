"""وكيل التركيبة الدينية لسِلك — Silk religion-composition agent (المجموعة ب · Group B).

يعطي الديانة الغالبة وحصتها التقريبية في السوق المستهدف من جدول مرجعي محلي مبني
مرة واحدة من Pew Global Religious Landscape. مهمّ لملاءمة المنتج (حلال، مناسبات
دينية، محرّمات غذائية) وتوقيت الطلب الموسمي الديني.

Returns the target market's majority religion + approximate share from a local
reference table built once from Pew's Global Religious Landscape
(data/religion_reference.csv). Real curated reference data (like the M49 map),
NOT per-request fabrication. Shares are APPROXIMATE and dated (see the CSV's
source/year columns) — surfaced with that caveat, never presented as live/exact.
Unknown country / missing file -> provenance-tagged None. Pure stdlib, offline.
"""
from __future__ import annotations

import csv
import functools
import logging
import os

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_SOURCE = "Pew Global Religious Landscape (curated reference)"


def _abspath(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_HERE, path)


@functools.lru_cache(maxsize=1)
def load_religion(path: str = "data/religion_reference.csv") -> dict:
    """حمّل الجدول المرجعي — load the religion reference, keyed by ISO3 (cached)."""
    fp = _abspath(path)
    try:
        with open(fp, newline="", encoding="utf-8") as f:
            return {(_r.get("iso3") or "").strip().upper(): _r
                    for _r in csv.DictReader(f)}
    except Exception as exc:  # missing/unreadable file degrades to empty
        log.warning("failed to load religion reference %s: %s", fp, exc)
        return {}


def _pct(raw: object) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def religion_profile(iso3: str,
                     path: str = "data/religion_reference.csv") -> DataPoint:
    """التركيبة الدينية لدولة — majority religion + approx share for one market.

    value = {majority_religion, majority_religion_ar, majority_share_pct,
    second_religion, second_share_pct, source, year}. Unknown country / empty
    file -> DataPoint(value=None). Never fabricates a religion or a number.
    """
    want = (iso3 or "").strip().upper()
    if not want:
        return DataPoint(None, _SOURCE, 0.0, "empty ISO3 — no religion lookup", _today())
    table = load_religion(path)
    if not table:
        return DataPoint(None, _SOURCE, 0.0,
                         "religion reference empty/unavailable", _today())
    row = table.get(want)
    if row is None:
        return DataPoint(None, _SOURCE, 0.0,
                         f"no religion reference for ISO3 '{want}' "
                         "(seed is partial; extend from Pew)", _today())
    value = {
        "majority_religion": row.get("majority_religion"),
        "majority_religion_ar": row.get("majority_religion_ar"),
        "majority_share_pct": _pct(row.get("approx_share_pct")),
        "second_religion": row.get("second_religion") or None,
        "second_share_pct": _pct(row.get("second_share_pct")),
        "source": row.get("source"),
        "year": row.get("year"),
    }
    note = (f"{value['majority_religion']} ≈{value['majority_share_pct']}% "
            f"({row.get('source')}, {row.get('year')}; approximate)")
    return DataPoint(value, _SOURCE, 0.7, note, _today())


class ReligionAgent(Agent):
    """وكيل التركيبة الدينية — majority religion + share for product-fit/timing."""

    def __init__(self) -> None:
        super().__init__("ReligionAgent")

    def run(self, task: dict) -> AgentReport:
        """التركيبة الدينية للسوق — the market's majority religion (approx, dated).

        task keys: iso3/country. Unknown/missing -> failed report, never guessed.
        """
        iso3 = task.get("iso3") or task.get("country")
        if not iso3:
            return AgentReport(self.name, [], True,
                               "لا يوجد ISO3 — missing iso3/country, cannot profile religion")
        dp = religion_profile(str(iso3))
        failed = dp.value is None
        summary = (f"no religion reference for {iso3}" if failed
                   else f"{dp.value['majority_religion']} majority in {iso3} (approx)")
        return AgentReport(self.name, [dp], failed, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk ReligionAgent — curated Pew reference (approximate, dated); "
          "graceful None for uncovered countries (no fabrication)")
    for iso3 in ("SAU", "IND", "XXX"):
        report = ReligionAgent().run({"iso3": iso3})
        flag = "FAILED" if report.failed else "ok"
        print(f"  [{flag}] {iso3}: {report.summary}")
