"""وكيل التعريفات الجمركية لسِلك — Silk customs-tariff research agent.

Best-effort applied import tariff (%) for an HS code into a market from World
Bank WITS (SDMX REST, TRN datasource). WITS is volatile, so every fetch is
defensive: on failure / format change / empty -> DataPoint(value=None,
confidence=0.0) + warning. Never guesses a rate (founding principle).
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

import requests

from silk_data_layer import DataPoint, ISO3_TO_M49, M49_TO_ISO3, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)

# WITS SDMX REST — applied (AHS) tariff, simple average, by product/year.
# Path: .../TRN/reporter_partner_product_year_indicator/...
_WITS_BASE = "https://wits.worldbank.org/API/V1/SDMX/V21/datasource/TRN/reporter"
_TIMEOUT = 30
_DEFAULT_YEAR = 2021  # WITS tariff data lags; recent years are often empty.


def _hs6(hs_code: str) -> str:
    """رمز HS بست خانات — WITS keys on 6-digit HS (zero-padded, trimmed)."""
    digits = "".join(ch for ch in str(hs_code) if ch.isdigit())
    return (digits + "000000")[:6] if digits else ""  # "" signals invalid HS


def applied_tariff(
    hs_code: str,
    market_iso3: str,
    partner_iso3: str = "SAU",
    year: int = _DEFAULT_YEAR,
) -> DataPoint:
    """التعريفة المطبّقة (%) — applied import tariff for HS into market from partner.

    Queries WITS TRN (AHS simple-average). Returns DataPoint(value=percent) on a
    parsed rate, else DataPoint(None, confidence=0.0, note=reason) on any error.
    """
    hs6 = _hs6(hs_code)
    if not hs6:
        return DataPoint(None, "World Bank WITS", 0.0,
                         f"invalid HS code {hs_code!r}", _today())
    # SDMX key: reporter/partner/product/year/AHS (applied, simple average).
    url = (f"{_WITS_BASE}/{market_iso3}/partner/{partner_iso3}"
           f"/product/{hs6}/year/{year}/datatype/AHS")
    params = {"format": "JSON"}
    try:
        r = requests.get(url, params=params, timeout=_TIMEOUT)
        r.raise_for_status()
        rate = _parse_rate(r)
    except Exception as e:  # noqa: BLE001 — WITS is volatile; never raise
        note = (f"WITS unavailable: {type(e).__name__} for HS{hs6} "
                f"{partner_iso3}->{market_iso3} {year}: {e}")
        log.warning(note)
        return DataPoint(None, "World Bank WITS", 0.0, note, _today())
    if rate is None:
        note = (f"WITS unavailable: no applied rate parsed for HS{hs6} "
                f"{partner_iso3}->{market_iso3} {year}")
        log.warning(note)
        return DataPoint(None, "World Bank WITS", 0.0, note, _today())
    return DataPoint(
        round(rate, 2), "World Bank WITS", 0.9,
        f"applied import tariff % (AHS simple avg) HS{hs6} "
        f"{partner_iso3}->{market_iso3} {year}", _today())


def _parse_rate(resp: requests.Response) -> float | None:
    """استخراج النسبة — pull the first tariff value from a WITS JSON or SDMX-XML reply.

    WITS may return SDMX-JSON or SDMX-ML depending on the endpoint/mood; try
    both. Returns the float rate or None if nothing parseable is found.
    """
    # المحاولة الأولى: SDMX-JSON.
    try:
        data = resp.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        for obs in _iter_json_obs(data):
            try:
                return float(obs)
            except (TypeError, ValueError):
                continue
        return None
    # المحاولة الثانية: SDMX-ML (XML) — Obs/@OBS_VALUE or generic ObsValue.
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return None
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        val = el.attrib.get("OBS_VALUE") or (
            el.attrib.get("value") if tag == "ObsValue" else None)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _iter_json_obs(data: dict):
    """تكرار قيم الرصد — yield observation values from SDMX-JSON dataSets."""
    for ds in data.get("dataSets", []) or []:
        series = ds.get("series") or {}
        for s in series.values():
            for obs in (s.get("observations") or {}).values():
                if isinstance(obs, list) and obs:
                    yield obs[0]
        for obs in (ds.get("observations") or {}).values():
            if isinstance(obs, list) and obs:
                yield obs[0]


class TariffsAgent(Agent):
    """وكيل التعريفات — applied customs tariff (%) into a market for an HS code."""

    def __init__(self) -> None:
        super().__init__("TariffsAgent")

    def run(self, task: dict) -> AgentReport:
        """جلب التعريفة المطبّقة — fetch the applied import tariff into the market.

        task keys: hs_code, reporter_m49 or iso3 (market), partner_iso3
        (default 'SAU'), year. Failure -> failed report, never a guessed rate.
        """
        hs = task.get("hs_code")
        year = task.get("year") or _DEFAULT_YEAR
        partner = task.get("partner_iso3", "SAU")
        iso3 = task.get("iso3") or M49_TO_ISO3.get(str(task.get("reporter_m49")))
        if not hs or not iso3:
            return AgentReport(
                self.name, [], True,
                "لا يوجد HS أو سوق صالح — missing hs_code or resolvable market ISO3")
        dp = applied_tariff(hs, iso3, partner, year)
        failed = dp.value is None
        if failed:
            summary = "لا توجد بيانات تعريفة — no tariff data (WITS unavailable)"
        else:
            summary = f"applied tariff {dp.value}% into {iso3} from {partner} ({year})"
        return AgentReport(self.name, [dp], failed, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk tariffs agent — best-effort WITS (degrades gracefully offline)")
    # قطن HS 5201 إلى الصين من السعودية — cotton into China from Saudi Arabia.
    report = TariffsAgent().run(
        {"hs_code": "5201", "iso3": "CHN", "partner_iso3": "SAU", "year": 2021})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    dp = report.findings[0]
    if dp.value is None:
        print(f"  tariff: no data / fetch failed — {dp.note}")
    else:
        print(f"  applied tariff = {dp.value}% [{dp.source}, {dp.note}]")
    _ = ISO3_TO_M49  # imported for downstream callers / symmetry.
