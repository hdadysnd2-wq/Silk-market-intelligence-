"""وكيل الاشتراطات لسِلك — Silk requirements/compliance agent (wave 3, #4).

القسم الخامس من الرؤية مبدوءاً بالخليج (كما قررت الخطة): **الطبقة ١** مرجع
ثابت في `data/requirements_l1.csv` (بنود دخول خليجية + بنود **الخروج
السعودي** — الاتجاهان معاً، §12.6) يُقرأ من القرص بلا أي شبكة. كل بند
موسوم بجهته ورابط بوابته الرسمية وثقته وملاحظة "تحقق قبل الشحن".

حدود صريحة (لا اختلاق):
- سوق غير مغطى بالمرجع = `DataPoint(None, note="تحقق محلياً")` — لا تُخترع
  اشتراطات؛ بنود الخروج السعودية تُعاد دوماً (مستقلة عن سوق الوجهة).
- هذا مرجع طبقة ١ يُزامَن ربع سنوياً؛ **ليس** استشارة قانونية — كل بند
  يحمل ملاحظته. البحث الحي المستهدف (الطبقة ٢) وأوروبا يأتيان لاحقاً
  حسب الخطة (الموجة ٥).

يرث `BaseAgent` (PAID=False) — أول وكيل معرفي يولد على الفئة الفارضة.
"""
from __future__ import annotations

import csv
import functools
import logging
import os

from silk_data_layer import DataPoint, _today
from silk_agents import BaseAgent, AgentReport

log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_CSV = os.path.join(_HERE, "data", "requirements_l1.csv")
_SOURCE = "Silk L1 requirements reference (official portals)"

# أسواق الخليج التي يغطيها وسم GCC في المرجع — GCC wildcard expansion.
_GCC = {"ARE", "QAT", "KWT", "OMN", "BHR", "SAU"}

# فصول HS الغذائية (01-24) — food HS chapters for category matching.
_FOOD_CHAPTERS = {f"{n:02d}" for n in range(1, 25)}


def hs_category(hs_code: str | None) -> str:
    """صنّف فئة المرجع من رمز HS — 'food' for chapters 01-24, else 'all'."""
    digits = "".join(ch for ch in str(hs_code or "") if ch.isdigit())
    return "food" if digits[:2] in _FOOD_CHAPTERS else "all"


@functools.lru_cache(maxsize=1)
def _load_reference() -> tuple[dict, ...]:
    """حمّل مرجع الطبقة ١ — read the L1 CSV once (offline, no network)."""
    try:
        with open(_CSV, newline="", encoding="utf-8") as f:
            return tuple(csv.DictReader(f))
    except Exception as exc:  # noqa: BLE001 — missing reference degrades, never crashes
        log.warning("L1 requirements reference unavailable (%s): %s", _CSV, exc)
        return ()


def _matches(row: dict, market: str, category: str, direction: str) -> bool:
    """هل ينطبق البند؟ — row applies to market×category×direction?"""
    row_market = (row.get("market") or "").strip().upper()
    market_ok = (row_market == market
                 or (row_market == "GCC" and market in _GCC))
    row_cat = (row.get("category") or "all").strip().lower()
    cat_ok = row_cat == "all" or row_cat == category
    dir_ok = (row.get("direction") or "").strip().lower() == direction
    return market_ok and cat_ok and dir_ok


def _row_dp(row: dict, direction: str) -> DataPoint:
    """بند مرجع كنقطة موسومة — one checklist item as a provenance DataPoint."""
    try:
        conf = float(row.get("confidence") or 0.5)
    except ValueError:
        conf = 0.5
    return DataPoint(
        value={"item": row.get("item_ar"), "authority": row.get("authority"),
               "direction": direction, "source_url": row.get("source_url")},
        source=_SOURCE, confidence=conf,
        note=row.get("note") or "مرجع طبقة ١ — تحقق قبل الشحن",
        retrieved_at=_today())


class RequirementsAgent(BaseAgent):
    """وكيل الاشتراطات — dual-direction compliance checklist (L1 reference)."""

    PAID = False
    SOURCE = _SOURCE

    def __init__(self) -> None:
        super().__init__("RequirementsAgent")

    def _execute(self, task: dict) -> AgentReport:
        """قائمة تحقق الدخول+الخروج — entry (market) + Saudi-exit checklist.

        task keys: market_iso3 (destination), hs_code (category matching),
        category (optional override: 'food'/'all'). Fully offline.
        """
        market = (task.get("market_iso3") or task.get("iso3") or "").strip().upper()
        if not market:
            return AgentReport(self.name, [], True,
                               "لا سوق — missing market_iso3")
        category = (task.get("category") or hs_category(task.get("hs_code"))).lower()
        rows = _load_reference()
        if not rows:
            return AgentReport(
                self.name,
                [DataPoint(None, _SOURCE, 0.0,
                           "مرجع الطبقة ١ غير متاح — L1 reference unavailable",
                           _today())],
                True, "لا مرجع اشتراطات — L1 reference unavailable")

        entry = [_row_dp(r, "entry") for r in rows
                 if _matches(r, market, category, "entry")]
        exit_items = [_row_dp(r, "exit") for r in rows
                      if _matches(r, "SAU", category, "exit")]

        findings: list[DataPoint] = []
        if entry:
            findings.extend(entry)
        else:
            # سوق غير مغطى: فجوة معلنة لا اشتراطات مخترعة — the honest gap.
            findings.append(DataPoint(
                None, _SOURCE, 0.0,
                f"سوق {market} غير مغطى بالمرجع الثابت بعد — تحقق محلياً "
                "(verify locally; L1 reference does not cover this market yet)",
                _today()))
        findings.extend(exit_items)  # اتجاه الخروج السعودي يُعاد دوماً (§12.6)

        n_entry = len(entry)
        summary = (f"{n_entry} entry item(s) for {market} ({category}) + "
                   f"{len(exit_items)} Saudi-exit item(s)"
                   if n_entry else
                   f"سوق {market} بلا مرجع دخول (تحقق محلياً) + "
                   f"{len(exit_items)} بند خروج سعودي")
        return AgentReport(self.name, findings, False, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk RequirementsAgent — offline L1 reference, dual direction")
    for market in ("ARE", "DEU"):
        rep = RequirementsAgent().run({"market_iso3": market,
                                       "hs_code": "080410"})
        print(f"  [{market}] {rep.summary}")
        for dp in rep.findings[:3]:
            label = dp.value["item"] if dp.value else dp.note
            print(f"    - conf={dp.confidence} {label[:60]}")
