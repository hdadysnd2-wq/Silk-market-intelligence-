"""وكيل D&B لسِلك — Silk Dun & Bradstreet agent (المجموعة و · Group F, PAID/advanced).

يتحقق من **الشرعية القانونية** للموردين المكتشفين (من Maps/Volza/explee) عبر رقم
D-U-N-S وبيانات D&B Direct+. مدفوع ومتقدّم، لا يُستدعى إلا في «تعميق التحليل»
للأسواق الناجحة. بلا DNB_API_KEY لا تُجرى أي محاولة شبكة ويُعاد DataPoint(None,
0.0) موسوم بأنه يتطلب اشتراكاً. الأسماء/الأرقام تُقرأ فقط من الردّ الحقيقي ولا
تُختلق أبداً (المبدأ التأسيسي).

'requests' يُستورد بكسل داخل الدالة فيبقى الاستيراد يعمل بلا مفتاح/شبكة.
"""
from __future__ import annotations

import logging
import os

from silk_data_layer import DataPoint, _today
from silk_agents import Agent, AgentReport

log = logging.getLogger(__name__)

# نقطة نهاية D&B (قابلة للتهيئة) — D&B Direct+ endpoint; overridable per plan.
_DNB_URL = os.environ.get(
    "DNB_API_URL", "https://plus.dnb.com/v1/match/cleanseMatch").strip()
_TIMEOUT = 30
_NO_KEY_NOTE = ("D&B requires a paid subscription (DNB_API_KEY) — supplier "
                "legitimacy verification not attempted")


def verify_supplier(name: str, country: str = "") -> DataPoint:
    """تحقّق من مورّد — D&B legitimacy match for a company name (PAID, advanced).

    No DNB_API_KEY -> a single failed DataPoint (no network call). With a key,
    a defensive best-effort match; on any error / empty / format change ->
    provenance-tagged None. D-U-N-S and confidence come only from the real
    response — never fabricated.
    """
    name = (name or "").strip()
    if not name:
        return DataPoint(None, "D&B", 0.0, "empty company name — no lookup", _today())
    key = os.environ.get("DNB_API_KEY", "").strip()
    if not key:
        log.warning("DNB_API_KEY not set — D&B is a paid subscription")
        return DataPoint(None, "D&B", 0.0, _NO_KEY_NOTE, _today())
    try:
        import requests  # lazy: only needed when a key is present
    except ImportError as e:  # pragma: no cover — requests is a core dep
        return DataPoint(None, "D&B", 0.0, f"requests unavailable: {e}", _today())

    params = {"name": name}
    if country:
        params["countryISOAlpha2Code"] = country
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    try:
        r = requests.get(_DNB_URL, params=params, headers=headers, timeout=_TIMEOUT)
        r.raise_for_status()
        payload = r.json()
    except Exception as e:  # noqa: BLE001 — paid API is opaque; never raise
        note = f"D&B lookup failed for {name!r}: {type(e).__name__}: {e}"
        log.warning(note)
        return DataPoint(None, "D&B", 0.0, note, _today())

    match = _parse_match(payload)
    if not match:
        return DataPoint(None, "D&B", 0.0,
                         f"D&B: no verified match for {name!r}", _today())
    return DataPoint(match, "D&B", 0.85,
                     f"verified {match.get('name') or name} "
                     f"(DUNS {match.get('duns')})", _today())


def _parse_match(payload: object) -> dict | None:
    """استخراج أفضل مطابقة — pull the top D&B match (name, DUNS, country) defensively.

    D&B Direct+ shapes vary; probe matchCandidates -> organization. Returns a
    compact dict or None. Never invents a DUNS or a name.
    """
    if not isinstance(payload, dict):
        return None
    candidates = payload.get("matchCandidates") or payload.get("matchcandidates") or []
    if not isinstance(candidates, list) or not candidates:
        return None
    top = candidates[0]
    if not isinstance(top, dict):
        return None
    org = top.get("organization") if isinstance(top.get("organization"), dict) else top
    duns = org.get("duns") or top.get("duns")
    name = org.get("primaryName") or org.get("name")
    if not duns and not name:
        return None
    country = None
    addr = org.get("primaryAddress") if isinstance(org.get("primaryAddress"), dict) else {}
    if isinstance(addr, dict):
        cc = addr.get("addressCountry")
        country = cc.get("isoAlpha2Code") if isinstance(cc, dict) else None
    return {"name": name, "duns": duns, "country": country,
            "confidence_code": top.get("matchQualityInformation", {}).get("confidenceCode")
            if isinstance(top.get("matchQualityInformation"), dict) else None}


class DnbAgent(Agent):
    """وكيل D&B — supplier legal-legitimacy verification (PAID, advanced/deepen)."""

    def __init__(self) -> None:
        super().__init__("DnbAgent")

    def run(self, task: dict) -> AgentReport:
        """تحقّق من قائمة موردين — verify discovered supplier names via D&B.

        task keys: names (list[str]) or name (str); country (ISO2, optional).
        No paid key -> failed report with a clear note; never fabricates a DUNS.
        """
        names = task.get("names")
        if not names and task.get("name"):
            names = [task["name"]]
        names = [n for n in (names or []) if n and str(n).strip()][:8]
        country = task.get("country") or task.get("iso2") or ""
        if not names:
            return AgentReport(self.name, [], True,
                               "لا أسماء موردين للتحقق — no supplier names to verify")
        findings = [verify_supplier(str(n), str(country)) for n in names]
        real = [f for f in findings if f.value is not None]
        failed = not real
        if failed:
            note = findings[0].note if findings else _NO_KEY_NOTE
            summary = f"لا تحقق D&B — no D&B verification ({note})"
        else:
            summary = f"{len(real)}/{len(names)} supplier(s) verified via D&B"
        return AgentReport(self.name, findings, failed, summary)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk DnbAgent — PAID/advanced; degrades gracefully without DNB_API_KEY "
          "(no fabricated DUNS/verification)")
    report = DnbAgent().run({"names": ["Maroc Dattes SARL"], "country": "MA"})
    flag = "FAILED" if report.failed else "ok"
    print(f"  [{flag}] {report.agent_name}: {report.summary}")
    for f in report.findings:
        print(f"    value={f.value} conf={f.confidence} note={f.note}")
