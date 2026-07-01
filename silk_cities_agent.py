"""وكيل المدن لسِلك — Silk cities agent (المجموعة ب · Group B, V3).

يعطي أكبر مدن السوق المستهدف بإحداثياتها وسكانها من جدول مرجعي محلي بصيغة
simplemaps (data/world_cities.csv). يُستخدم لطبقة الخريطة التفاعلية (نقاط المدن
بحجم يعكس السكان) ولفهم مراكز الطلب داخل السوق.

Returns the target market's largest cities (lat/lng + population) from a local
simplemaps-format reference (data/world_cities.csv). Real curated reference data
only — like data/hs_codes.csv and the M49 map, NOT per-request fabrication. The
shipped file is a CURATED SEED of major/capital cities for Silk's target
markets; drop in the full simplemaps World Cities CSV (same columns) for
complete coverage. Unknown country / missing file -> provenance-tagged None, no
guessing. Pure stdlib (csv), fully offline.
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
_SOURCE = "Silk curated world-cities seed (simplemaps schema)"


def _abspath(path: str) -> str:
    return path if os.path.isabs(path) else os.path.join(_HERE, path)


@functools.lru_cache(maxsize=1)
def load_cities(path: str = "data/world_cities.csv") -> list[dict]:
    """حمّل جدول المدن — load the world-cities reference (cached; parsed once)."""
    fp = _abspath(path)
    try:
        with open(fp, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as exc:  # missing/unreadable file degrades to empty (no crash)
        log.warning("failed to load world-cities seed %s: %s", fp, exc)
        return []


def _pop(row: dict) -> float:
    """سكان كرقم للترتيب — population as a sortable float (missing -> -1)."""
    raw = (row.get("population") or "").strip()
    try:
        return float(raw)
    except (TypeError, ValueError):
        return -1.0


def top_cities(iso3: str, top_n: int = 5,
               path: str = "data/world_cities.csv") -> list[DataPoint]:
    """أكبر مدن دولة — the country's largest cities as DataPoints, ranked by pop.

    Each value = {city, lat, lng, population, capital}. Unknown country / empty
    file -> a single provenance-tagged None. Never fabricates a city or a number.
    """
    want = (iso3 or "").strip().upper()
    if not want:
        return [DataPoint(None, _SOURCE, 0.0, "empty ISO3 — no city lookup", _today())]
    rows = load_cities(path)
    if not rows:
        return [DataPoint(None, _SOURCE, 0.0,
                          "world-cities reference empty/unavailable "
                          "(drop in the simplemaps CSV at data/world_cities.csv)",
                          _today())]
    matched = [r for r in rows if (r.get("iso3") or "").strip().upper() == want]
    if not matched:
        return [DataPoint(None, _SOURCE, 0.0,
                          f"no cities in the reference for ISO3 '{want}' "
                          "(seed is partial; extend from simplemaps)", _today())]
    matched.sort(key=_pop, reverse=True)
    out: list[DataPoint] = []
    for r in matched[: max(1, top_n)]:
        pop = _pop(r)
        try:
            lat, lng = float(r.get("lat")), float(r.get("lng"))
        except (TypeError, ValueError):
            continue  # a row without real coordinates is skipped, never guessed
        out.append(DataPoint(
            {"city": r.get("city"), "lat": lat, "lng": lng,
             "population": int(pop) if pop >= 0 else None,
             "capital": (r.get("capital") or "").strip() or None},
            _SOURCE, 0.8,
            f"{r.get('city')} ({want})"
            + (f", pop≈{int(pop):,}" if pop >= 0 else ", population n/a"),
            _today()))
    if not out:
        return [DataPoint(None, _SOURCE, 0.0,
                          f"no usable city coordinates for '{want}'", _today())]
    return out


class CitiesAgent(Agent):
    """وكيل المدن — largest cities (lat/lng + population) of the target market."""

    def __init__(self, top_n: int = 5) -> None:
        super().__init__("CitiesAgent")
        self.top_n = top_n

    def run(self, task: dict) -> AgentReport:
        """أكبر مدن السوق — the market's largest cities for the map/demand layer.

        task keys: iso3/country, top_n (optional). Unknown/missing -> failed
        report, never a fabricated city.
        """
        iso3 = task.get("iso3") or task.get("country")
        top_n = int(task.get("top_n", self.top_n))
        if not iso3:
            return AgentReport(self.name, [], True,
                               "لا يوجد ISO3 — missing iso3/country, cannot list cities")
        findings = top_cities(str(iso3), top_n)
        real = [f for f in findings if f.value is not None]
        if not real:
            note = findings[0].note if findings else "no data"
            return AgentReport(self.name, findings, True,
                               f"لا مدن مرجعية — no reference cities ({note})")
        return AgentReport(self.name, real, False,
                           f"{len(real)} city/cities for {iso3}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk CitiesAgent — curated real reference; graceful None for uncovered "
          "countries (no fabricated cities)")
    for iso3 in ("EGY", "ARE", "XXX"):
        report = CitiesAgent().run({"iso3": iso3, "top_n": 3})
        flag = "FAILED" if report.failed else "ok"
        print(f"  [{flag}] {iso3}: {report.summary}")
        for f in report.findings:
            print(f"    value={f.value} note={f.note}")
