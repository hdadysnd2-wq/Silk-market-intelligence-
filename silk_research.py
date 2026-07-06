"""وكلاء البحث السبعة والمنسّق — Silk research agents & orchestrator (Stage 3, §4b).

الطبقة بين خط البيانات (§4) ومحرك القرار (§8): الجامعون يملؤون مخزن الحقائق →
الوكلاء يقرؤون الحقائق (+ نداءات حية مستهدفة ضمن الميزانية) → المنسّق يتحقق من
المخطط ويجمّع → محرك القرار (Stage 4) يستهلك مدخلات الأعمدة → التقرير يستهلك
مخرجات الأقسام.

السبعة (خطة §4b الخمسة + وكيلا توجيه المالك):
  market_size · competitor (طبقتان: دول + شركات) · regulatory ·
  pricing (طبقتان: حدودية + تجزئة) · risk · consumer_demand · supplier

عقيدة المخطط تُفرَض بالتحقق (pydantic) لا بالمراجعة:
  * كل اكتشاف بقيمة يتطلب sources[] غير فارغة — لا رقم بلا مصدر.
  * modeled=True يتطلب formula صريحة — لا نموذج بلا معادلة معلنة.
  * قيمة غائبة = بند في gaps[] — الفجوة تُعلَن ولا تُخفى.
  * اكتشاف يخالف المخطط يُرفض عند التحقق ويُخفَّض إلى فجوة مسجَّلة — لا يصل
    التقرير ولا محرك القرار غير موثَّق.

كل الوكلاء السبعة PAID=False (بروتوكول النقاط الأربع): المسار المدفوع الوحيد
هو طبقة التجزئة المهيكلة في pricing، وهي تفوّض LocalPriceAgent القائم الذي
يستحيل تنفيذه خارج /deepen بحارس BaseAgent البنيوي — خارج السياق تظهر فجوة
معلنة تشرح ذلك، بلا أي نداء.
"""
from __future__ import annotations

import concurrent.futures as _cf
import csv
import datetime
import logging
import os
import time as _time

from pydantic import BaseModel, Field, field_validator, model_validator

from silk_agents import AgentReport, BaseAgent
from silk_data_layer import DataPoint, _today

log = logging.getLogger(__name__)

SCHEMA = "silk.research/v1"
DEFAULT_TIMEOUT = float(os.environ.get("SILK_AGENT_TIMEOUT", "90"))
_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


# ── مخطط المخرجات · output schema (§4b, validated) ──────────────────────────

class SourceRef(BaseModel):
    """مرجع مصدر واحد لاكتشاف — one provenance reference for a finding."""

    source: str = Field(min_length=1)
    retrieved_at: str = ""
    confidence: float = 0.0
    url: str | None = None


class Finding(BaseModel):
    """اكتشاف واحد — metric + value + provenance; the doctrine is validated here."""

    metric: str = Field(min_length=1)
    value: object = None
    unit: str | None = None
    modeled: bool = False
    formula: str | None = None
    sources: list[SourceRef] = Field(default_factory=list)
    note: str = ""

    @model_validator(mode="after")
    def _doctrine(self):
        if self.value is not None and not self.sources:
            raise ValueError(
                "finding with a value requires non-empty sources[] — لا رقم بلا مصدر")
        if self.modeled and not (self.formula or "").strip():
            raise ValueError(
                "modeled finding requires an explicit formula — لا نموذج بلا معادلة")
        return self


class AgentOutput(BaseModel):
    """مخرجات وكيل واحد — the §4b envelope; invalid findings never enter it."""

    agent: str
    hs6: str = ""
    iso3: str = ""
    status: str = "failed"
    findings: list[Finding] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)
    coverage: float = 0.0
    started_at: str = ""
    finished_at: str = ""

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v not in ("complete", "partial", "failed"):
            raise ValueError("status must be complete|partial|failed")
        return v


def _src(source: str, conf: float = 0.9, url: str | None = None,
         retrieved_at: str | None = None) -> dict:
    return {"source": source, "confidence": conf, "url": url,
            "retrieved_at": retrieved_at or _today()}


def _dp_src(dp: DataPoint) -> dict:
    return {"source": dp.source, "confidence": dp.confidence,
            "retrieved_at": dp.retrieved_at or _today()}


def _f(metric: str, value, sources: list[dict], unit: str | None = None,
       modeled: bool = False, formula: str | None = None, note: str = "") -> dict:
    return {"metric": metric, "value": value, "unit": unit, "modeled": modeled,
            "formula": formula, "sources": sources, "note": note}


def _failed_output(agent: str, task: dict, reason: str) -> dict:
    """مغلّف فشل صريح — a failed envelope whose reason is visible, never silent."""
    now = _now_iso()
    return AgentOutput(
        agent=agent, hs6=str(task.get("hs6") or ""), iso3=str(task.get("iso3") or ""),
        status="failed", findings=[], gaps=[reason], coverage=0.0,
        started_at=now, finished_at=now).model_dump()


# ── الأساس المشترك · shared research-agent base ─────────────────────────────

class ResearchAgent(BaseAgent):
    """وكيل بحث §4b — يبني حول حرّاس BaseAgent البنيويين تحققَ المخطط والتغطية.

    الفئات الفرعية تكتب `_research(task) -> (raw_findings, gaps)` فقط؛ هنا:
    التحقق (اكتشاف مخالف => يُرفض ويُخفَّض إلى فجوة)، فرض «قيمة غائبة = فجوة
    معلنة»، حساب التغطية من EXPECTED، وتعليب المغلف الموحّد.
    """

    PAID = False               # السبعة مجانية — المدفوع محصور في /deepen بنيوياً
    AGENT = ""                 # الاسم المخططي (market_size, competitor, …)
    EXPECTED: tuple[str, ...] = ()

    def __init__(self) -> None:
        super().__init__(self.__class__.__name__)

    def _research(self, task: dict) -> tuple[list[dict], list[str]]:
        raise NotImplementedError

    def _execute(self, task: dict) -> AgentReport:
        started = _now_iso()
        raw, gaps = self._research(task)
        findings: list[Finding] = []
        rejected: list[str] = []
        for rf in raw:
            try:
                findings.append(Finding(**rf))
            except Exception as e:  # noqa: BLE001 — رفض المخطط يُسجَّل لا يُبتلع
                msg = (f"{rf.get('metric', '?')}: rejected at schema validation — "
                       f"{e}")
                rejected.append(msg)
                gaps.append(msg)
                log.warning("%s: %s", self.AGENT, msg)
        for f in findings:  # قيمة غائبة بلا فجوة مقابلة => الفجوة تُضاف تلقائياً
            if f.value is None and not any(f.metric in g for g in gaps):
                gaps.append(f"{f.metric}: {f.note or 'غير مرصود — unobserved'}")
        observed = {f.metric for f in findings if f.value is not None}
        if self.EXPECTED:
            coverage = round(len(observed & set(self.EXPECTED))
                             / len(self.EXPECTED), 2)
        else:
            coverage = 1.0 if observed else 0.0
        status = ("failed" if not observed else
                  "complete" if coverage >= 0.999 and not gaps else "partial")
        out = AgentOutput(
            agent=self.AGENT, hs6=str(task.get("hs6") or ""),
            iso3=str(task.get("iso3") or ""), status=status, findings=findings,
            gaps=gaps, rejected=rejected, coverage=coverage,
            started_at=started, finished_at=_now_iso())
        return AgentReport(self.name, [out.model_dump()], failed=(status == "failed"),
                           summary=f"{self.AGENT}: {status} coverage={coverage}")


# ── ١) وكيل حجم السوق · market size (TAM/SAM/SOM + نمو) ─────────────────────

_TIER_FACTORS = {"premium": 0.2, "mid": 0.5, "standard": 0.5,
                 "mass": 0.8, "economy": 0.8}


class MarketSizeAgent(ResearchAgent):
    """TAM مرصود (كومتريد) · SAM/SOM نموذجان معلنا الافتراضات · نمو من المخزن."""

    AGENT = "market_size"
    EXPECTED = ("tam_usd", "import_growth_pct", "import_cagr_pct",
                "sam_usd", "som_usd")

    def _research(self, task):
        F: list[dict] = []
        gaps: list[str] = []
        hs, iso3, year = task["hs6"], task["iso3"], int(task["year"])
        from silk_data_layer_v2 import market_imports_cached
        mi = market_imports_cached(hs, task.get("m49"), iso3, year)
        tam = mi.get("total_usd")
        if tam is not None:
            F.append(_f("tam_usd", tam, [_src("UN Comtrade")], unit="USD",
                        note=f"TAM = إجمالي واردات السوق المرصودة HS{hs} سنة "
                             f"{year}{mi.get('xval_note') or ''}"))
        else:
            gaps.append(f"tam_usd: لا واردات مرصودة HS{hs} {iso3} {year} — "
                        "كومتريد غير متاح والمخزن بارد")

        # النمو من مخزن الحقائق حصراً (لا توسيع نداءات حية هنا — الميزانية للجامع).
        import silk_store
        from silk_trend import cagr_pct, growth_pct
        pairs: list[tuple[int, float | None]] = []
        for y in range(year - 4, year + 1):
            try:
                pairs.append((y, silk_store.market_imports_from_store(
                    hs, iso3, y)["total_usd"]))
            except Exception:  # noqa: BLE001 — المخزن تحسين لا شرط
                pairs.append((y, None))
        g, c = growth_pct(pairs), cagr_pct(pairs)
        obs_years = [y for y, v in pairs if v is not None]
        store_src = _src("UN Comtrade (مخزن الحقائق)")
        if g is not None:
            F.append(_f("import_growth_pct", g, [store_src], unit="%",
                        note=f"نمو الواردات {obs_years[0]}→{obs_years[-1]} — "
                             f"{len(obs_years)}/5 سنوات مرصودة، الفجوات معلنة"))
        else:
            gaps.append("import_growth_pct: يتطلب سنتين مرصودتين على الأقل في "
                        "مخزن الحقائق — شغّل جامع كومتريد (tools/refresh.py)")
        if c is not None:
            F.append(_f("import_cagr_pct", c, [store_src], unit="%",
                        note=f"CAGR عبر السنوات المرصودة {obs_years[0]}–{obs_years[-1]}"))
        else:
            gaps.append("import_cagr_pct: يتطلب سلسلة سنوات في مخزن الحقائق")

        # SAM/SOM — نموذجان بافتراضات معلنة (§7-2): لا يُحسبان بلا مدخلاتهما.
        card = task.get("product_card") or {}
        tier = str(card.get("tier") or "").strip().lower()
        if tam is not None and tier in _TIER_FACTORS:
            factor = _TIER_FACTORS[tier]
            F.append(_f("sam_usd", round(tam * factor), [_src("UN Comtrade")],
                        unit="USD", modeled=True,
                        formula=f"SAM = TAM × {factor} (عامل شريحة '{tier}' — "
                                "افتراض معلن قابل للتعديل)",
                        note="مُقدَّر — نموذج بافتراضات معلنة، ليس رصداً"))
        else:
            gaps.append("sam_usd: يتطلب TAM مرصوداً + شريحة tier في بطاقة المنتج "
                        "(premium/mid/mass)")
        cap = card.get("monthly_capacity")
        uv = _border_unit_value(hs, iso3, year)
        if cap and uv and tam is not None:
            som = round(min(tam * _TIER_FACTORS.get(tier, 1.0),
                            float(cap) * 12 * uv))
            F.append(_f("som_usd", som, [_src("UN Comtrade")], unit="USD",
                        modeled=True,
                        formula="SOM = min(SAM أو TAM، الطاقة الشهرية × 12 × "
                                f"قيمة الوحدة الحدودية {uv:.2f}$/kg)",
                        note="مُقدَّر — سقف إيراد الطاقة الإنتاجية بأسعار الحدود "
                             "المرصودة"))
        else:
            gaps.append("som_usd: يتطلب طاقة شهرية في بطاقة المنتج + قيمة وحدة "
                        "حدودية مرصودة (قيمة/وزن كومتريد)")
        return F, gaps


def _border_unit_value(hs: str, iso3: str, year: int) -> float | None:
    """قيمة الوحدة الحدودية $/kg من المخزن — value/qty of the WLD row, or None."""
    try:
        import silk_store
        row = silk_store.get_trade_flow(hs, iso3, "WLD", year)
        if row and row.get("value_usd") and row.get("qty_kg"):
            return row["value_usd"] / row["qty_kg"]
    except Exception:  # noqa: BLE001 — المخزن تحسين لا شرط
        pass
    return None


# ── ٢) وكيل المنافسة · competitor (طبقتان: دول ثم شركات) ────────────────────

class CompetitorAgent(ResearchAgent):
    """الطبقة ١: دول مورّدة بحصص وHHI (كومتريد). الطبقة ٢: شركات بالاسم
    (Serper/Maps) — مرشّحون غير موثَّقين برابط وتاريخ، ثقة 0.4، لا اختلاق."""

    AGENT = "competitor"
    EXPECTED = ("hhi", "top_supplier_share_pct", "saudi_share_pct",
                "supplier_countries", "named_companies")

    def _research(self, task):
        F: list[dict] = []
        gaps: list[str] = []
        hs, iso3, year = task["hs6"], task["iso3"], int(task["year"])
        from silk_data_layer_v2 import market_imports_cached
        mi = market_imports_cached(hs, task.get("m49"), iso3, year)
        comps = mi.get("competitors") or []
        if comps:
            rows = [c.value for c in comps if c.value]
            shares = [r["share"] for r in rows]
            hhi = round(sum((s / 100.0) ** 2 for s in shares), 3)
            ct = _src("UN Comtrade")
            F.append(_f("hhi", hhi, [ct],
                        note=f"مؤشر هيرفنداهل لتركّز المورّدين ({len(rows)} دولة) — "
                             ">0.25 سوق مركّز"))
            F.append(_f("top_supplier_share_pct", shares[0], [ct], unit="%",
                        note=f"حصة المورّد الأكبر: {rows[0]['partner']}"))
            sau = next((r for r in rows if str(r.get("code")) == "682"), None)
            F.append(_f("saudi_share_pct", (sau or {}).get("share", 0.0), [ct],
                        unit="%",
                        note="حصة السعودية بين المورّدين المبلَّغ عنهم"
                             + ("" if sau else " — غير ظاهرة بينهم (رصد غياب، "
                                                "ليس تقديراً)")))
            F.append(_f("supplier_countries", rows[:8], [ct],
                        note=f"أكبر {min(8, len(rows))} دول مورّدة بالقيمة والحصة"))
        else:
            gaps.append(f"الطبقة الدولية: لا صفوف شركاء HS{hs} {iso3} {year} — "
                        "كومتريد غير متاح والمخزن بارد")

        # الطبقة ٢ — كيانات ومراجع (إصلاح مراجعة Stage 5، ثغرة ٢): أسماء الأعمال
        # الحقيقية تأتي من Google Places حصراً (kind=entity)؛ نتائج بحث الويب
        # عناوين صفحات لا أسماء كيانات فتُدرج «مرجعاً للمراجعة اليدوية»
        # (kind=reference) — لا يُعرض عنوان بحث كاسم منافس أبداً.
        product, market = task.get("product", ""), task.get("market_name", iso3)
        named, refs = _entities_and_references(
            web_queries=[f"top {product} brands importers distributors "
                         f"companies in {market}"],
            maps_query=f"{product} distributor importer {market}")
        if named:
            F.append(_f("named_companies", named, refs,
                        note="كيانات Google Maps بالاسم (غير موثَّقة، ثقة 0.4) "
                             "+ مراجع ويب للمراجعة اليدوية — أكّدها قبل "
                             "الاعتماد؛ الترقية الموثّقة عبر /deepen (Volza/Explee)"))
        else:
            gaps.append("الطبقة الاسمية (شركات): تتطلب SEARCH_API_KEY و/أو "
                        "GOOGLE_MAPS_API_KEY في بيئة الخادم — لا أسماء مخترعة")
        return F, gaps


def _entities_and_references(web_queries: list[str], maps_query: str,
                             region: str | None = None,
                             num: int = 4) -> tuple[list[dict], list[dict]]:
    """مرشّحون مفصولون بالنوع — entities (Google Places names) vs references
    (web-result titles for manual review). عنوان بحث ليس اسم كيان (ثغرة ٢)."""
    out, refs = [], []
    from silk_maps_agent import find_places
    from silk_websearch_agent import web_search
    for dp in find_places(maps_query, region=region):
        if dp.value:
            out.append({"kind": "entity", "name": dp.value.get("name", ""),
                        "address": dp.value.get("address"),
                        "rating": dp.value.get("rating"),
                        "via": "Google Maps", "retrieved_at": dp.retrieved_at})
            refs.append(_src("Google Maps", 0.4, retrieved_at=dp.retrieved_at))
    for q in web_queries:
        for dp in web_search(q, num):
            if dp.value:
                out.append({"kind": "reference",
                            "title": dp.value.get("title", ""),
                            "url": dp.value.get("link", ""),
                            "via": "Serper", "retrieved_at": dp.retrieved_at,
                            "note": "مرجع للمراجعة اليدوية — ليس اسم كيان"})
                refs.append(_src("Web Search (Serper)", 0.3,
                                 url=dp.value.get("link"),
                                 retrieved_at=dp.retrieved_at))
    return out, refs


# ── ٣) الوكيل التنظيمي · regulatory ──────────────────────────────────────────

class RegulatoryAgent(ResearchAgent):
    """قائمة الاشتراطات L1 (مرجع ساكن مُستشهَد) + التعريفة المطبّقة (WITS)."""

    AGENT = "regulatory"
    EXPECTED = ("requirements_checklist", "entry_requirements_count",
                "eligibility_gate", "tariff_applied_pct")

    def _research(self, task):
        F: list[dict] = []
        gaps: list[str] = []
        hs, iso3, year = task["hs6"], task["iso3"], int(task["year"])
        from silk_requirements_agent import RequirementsAgent
        rep = RequirementsAgent().run({"market_iso3": iso3, "hs_code": hs})
        items = [f.value for f in rep.findings if f.value is not None]
        if items:
            l1 = _dp_src(next(f for f in rep.findings if f.value is not None))
            F.append(_f("requirements_checklist", items, [l1],
                        note=f"{len(items)} بند اشتراطات (دخول السوق + خروج سعودي) "
                             "— كل بند بلائحته ورابطه الرسمي"))
            F.append(_f("entry_requirements_count", len(items), [l1],
                        note="عدد بنود قائمة التحقق"))
            gate = any("2017/625" in str(i) for i in items)
            F.append(_f("eligibility_gate", gate, [l1],
                        note=("بوابة أهلية أمامية: منشأة معتمدة (EU 2017/625) قبل "
                              "أي بند لاحق" if gate else
                              "لا بوابة أهلية أمامية مسجّلة لهذا السوق/الفصل")))
        else:
            gaps.append("requirements_checklist: "
                        + (rep.summary or "مرجع L1 بلا بنود لهذا السوق"))
        from silk_tariffs_agent import TariffsAgent
        trep = TariffsAgent().run({"hs_code": hs, "iso3": iso3, "year": year})
        tdp = next((f for f in trep.findings if f.value is not None), None)
        if tdp:
            F.append(_f("tariff_applied_pct", tdp.value, [_dp_src(tdp)], unit="%",
                        note=tdp.note))
        else:
            why = trep.findings[0].note if trep.findings else trep.summary
            gaps.append(f"tariff_applied_pct: {why}")
        return F, gaps


# ── ٤) وكيل التسعير · pricing (طبقتان: حدودية + تجزئة) ──────────────────────

class PricingAgent(ResearchAgent):
    """الطبقة ١: قيم وحدة حدودية = قيمة÷وزن كومتريد (مشتق معلن من رصدين).
    الطبقة ٢: تجزئة مهيكلة عبر /deepen فقط (SerpApi — حارس بنيوي) + مراجع
    أسعار حرة بروابط بلا استخراج أرقام آلي — لا سعر مخترع أبداً."""

    AGENT = "pricing"
    EXPECTED = ("border_unit_value_usd_kg", "saudi_border_unit_value_usd_kg",
                "retail_prices", "margin_at_border_pct", "retail_references")

    def _research(self, task):
        F: list[dict] = []
        gaps: list[str] = []
        hs, iso3, year = task["hs6"], task["iso3"], int(task["year"])
        product, market = task.get("product", ""), task.get("market_name", iso3)

        # الطبقة ١ — حدودية: من المخزن أولاً، وإلا نداء كومتريد واحد (partner=0).
        uv = _border_unit_value(hs, iso3, year)
        uv_src = _src("UN Comtrade (مخزن الحقائق)")
        if uv is None:
            from silk_data_layer import comtrade_trade, primary_value
            recs = comtrade_trade(hs, task.get("m49"), year, flow="M", partner=0)
            rec = next((r for r in recs
                        if primary_value(r) and (r.get("netWgt") or 0) > 0), None)
            if rec:
                uv = primary_value(rec) / float(rec["netWgt"])
                uv_src = _src("UN Comtrade")
        if uv is not None:
            F.append(_f("border_unit_value_usd_kg", round(uv, 2), [uv_src],
                        unit="USD/kg", modeled=True,
                        formula="قيمة الوحدة = قيمة الواردات ÷ الوزن الصافي "
                                "(كلاهما مرصود من كومتريد)",
                        note=f"متوسط سعر الحدود لواردات HS{hs} إلى {iso3} {year}"))
        else:
            gaps.append("border_unit_value_usd_kg: يتطلب قيمة ووزناً صافياً معاً "
                        "من كومتريد — غير متوافرَين لهذه السنة/السوق")
        sau_uv = None
        try:
            import silk_store
            row = silk_store.get_trade_flow(hs, iso3, "SAU", year)
            if row and row.get("value_usd") and row.get("qty_kg"):
                sau_uv = row["value_usd"] / row["qty_kg"]
        except Exception:  # noqa: BLE001
            pass
        if sau_uv is not None:
            F.append(_f("saudi_border_unit_value_usd_kg", round(sau_uv, 2),
                        [_src("UN Comtrade (مخزن الحقائق)")], unit="USD/kg",
                        modeled=True,
                        formula="قيمة وحدة الصادر السعودي = قيمة ÷ وزن صافٍ "
                                "(صف الشريك SAU)",
                        note="موقعك السعري عند الحدود مقابل متوسط السوق"))
        else:
            gaps.append("saudi_border_unit_value_usd_kg: لا صف سعودي بوزن صافٍ "
                        "في المخزن لهذه السنة")

        # الطبقة ٢ — تجزئة مهيكلة: مدفوعة، /deepen حصراً (الحارس البنيوي يقرر).
        from silk_localprice_agent import LocalPriceAgent
        lrep = LocalPriceAgent().run({"query": f"{product} {market}".strip(),
                                      "market": task.get("iso2")})
        listings = [f for f in lrep.findings if f.value is not None]
        if listings:
            F.append(_f("retail_prices",
                        [f.value for f in listings],
                        [_dp_src(f) for f in listings],
                        note=f"{len(listings)} سعر تجزئة مهيكل مؤرّخ (طبقة /deepen)"))
        else:
            why = lrep.findings[0].note if lrep.findings else lrep.summary
            gaps.append(f"retail_prices: {why}")

        # مراجع أسعار حرة — روابط مؤرّخة فقط؛ الأرقام لا تُستخرج آلياً من مقتطفات.
        from silk_websearch_agent import web_search
        refs = [dp for dp in web_search(f"{product} retail price in {market}", 3)
                if dp.value]
        if refs:
            F.append(_f("retail_references",
                        [{"title": d.value.get("title", ""),
                          "url": d.value.get("link", ""),
                          "retrieved_at": d.retrieved_at} for d in refs],
                        [_src("Web Search (Serper)", 0.3,
                              url=d.value.get("link"),
                              retrieved_at=d.retrieved_at) for d in refs],
                        note="مراجع سعرية للمراجعة اليدوية — لا استخراج أرقام آلي "
                             "من المقتطفات (لا اختلاق)"))
        else:
            gaps.append("retail_references: بحث الويب غير متاح "
                        "(SEARCH_API_KEY / الشبكة)")

        # هامش عند الحدود — نموذج معلن، يتطلب بطاقة منتج بوحدة kg + قيمة حدودية.
        card = task.get("product_card") or {}
        cost, ship = card.get("cost_per_unit"), card.get("shipping_per_unit") or 0
        if uv is not None and cost and str(card.get("unit", "")).lower() == "kg":
            margin = round(100 * (uv - float(cost) - float(ship)) / uv, 1)
            F.append(_f("margin_at_border_pct", margin, [uv_src], unit="%",
                        modeled=True,
                        formula=f"الهامش = (قيمة الوحدة الحدودية {uv:.2f} − "
                                f"تكلفتك {cost} − شحن {ship}) ÷ قيمة الوحدة",
                        note="مُقدَّر عند متوسط سعر الحدود — ليس سعر بيع تجزئة"))
        else:
            gaps.append("margin_at_border_pct: يتطلب بطاقة منتج بوحدة kg "
                        "(cost_per_unit) + قيمة وحدة حدودية مرصودة")
        return F, gaps


# ── ٥) وكيل المخاطر · risk ───────────────────────────────────────────────────

class RiskAgent(ResearchAgent):
    """WGI (استقرار/تنظيم) + LPI لوجستي + تقلب صرف من السلسلة + تركّز مورّدين."""

    AGENT = "risk"
    EXPECTED = ("political_stability_wgi", "regulatory_quality_wgi",
                "logistics_lpi", "fx_volatility_pct", "supplier_concentration_hhi")

    _INDICATORS = (("PV.EST", "political_stability_wgi", "الاستقرار السياسي (WGI)"),
                   ("RQ.EST", "regulatory_quality_wgi", "جودة التنظيم (WGI)"),
                   ("LP.LPI.OVRL.XQ", "logistics_lpi", "الأداء اللوجستي (LPI)"))

    def _research(self, task):
        F: list[dict] = []
        gaps: list[str] = []
        iso3, year = task["iso3"], int(task["year"])
        import silk_store
        for ind, metric, label in self._INDICATORS:
            got = None
            try:
                got = silk_store.get_indicator(iso3, ind)
            except Exception:  # noqa: BLE001 — المخزن تحسين لا شرط
                got = None
            if got and got.get("value") is not None:
                F.append(_f(metric, round(float(got["value"]), 3),
                            [_src(got.get("source", "World Bank"),
                                  float(got.get("confidence") or 0.9))],
                            note=f"{label} — {ind} سنة {got.get('year')} "
                                 "(مخزن الحقائق)"))
            else:
                from silk_data_layer import world_bank
                dp = world_bank(iso3, ind)
                if dp.value is not None:
                    F.append(_f(metric, dp.value, [_dp_src(dp)],
                                note=f"{label} — {dp.note}"))
                else:
                    gaps.append(f"{metric}: {label} غير متاح (مخزن بارد + "
                                f"{dp.note})")
        try:
            series = silk_store.get_indicator_series(iso3, "PA.NUS.FCRF")
        except Exception:  # noqa: BLE001
            series = []
        vals = [r["value"] for r in series if r.get("value")]
        if len(vals) >= 3:
            mean = sum(vals) / len(vals)
            cov = round(100 * (sum((v - mean) ** 2 for v in vals)
                               / len(vals)) ** 0.5 / mean, 2) if mean else None
            F.append(_f("fx_volatility_pct", cov,
                        [_src(series[-1].get("source", "World Bank"), 0.85)],
                        unit="%", modeled=True,
                        formula=f"معامل الاختلاف = انحراف معياري ÷ متوسط × 100 "
                                f"على {len(vals)} سنوات PA.NUS.FCRF",
                        note="تقلب سعر الصرف من السلسلة المخزّنة"))
        else:
            gaps.append("fx_volatility_pct: يتطلب سلسلة PA.NUS.FCRF (٣+ سنوات) — "
                        "شغّل جامع worldbank (tools/refresh.py)")
        # تركّز المورّدين — نفس HHI من صفوف المخزن (رخيص، محلي).
        try:
            got = silk_store.market_imports_from_store(task["hs6"], iso3, year)
            partners = got["partners"]
        except Exception:  # noqa: BLE001
            partners = []
        if partners:
            grand = sum(p["value_usd"] for p in partners)
            hhi = round(sum((p["value_usd"] / grand) ** 2 for p in partners), 3)
            F.append(_f("supplier_concentration_hhi", hhi, [_src("UN Comtrade")],
                        note="تركّز مصادر التوريد للسوق — >0.25 اعتماد مركّز "
                             "(خطر انقطاع/حرب أسعار)"))
        else:
            gaps.append("supplier_concentration_hhi: لا صفوف شركاء في المخزن")
        # بوابة الخطر الحرج — قاعدة معلنة على رصد WGI.
        pv = next((f["value"] for f in F
                   if f["metric"] == "political_stability_wgi"), None)
        if pv is not None:
            F.append(_f("critical_risk", bool(pv < -1.5),
                        [_src("World Bank", 0.9)], modeled=True,
                        formula="قاعدة: PV.EST < −1.5 ⇒ خطر سياسي حرج "
                                "(بوابة محرك القرار)",
                        note="علم بوابة الخطر الحرج — مشتق بقاعدة معلنة"))
        return F, gaps


# ── ٦) وكيل المستهلك والطلب · consumer & demand ─────────────────────────────

_muslim_cache: dict | None = None


def muslim_share(iso3: str) -> dict | None:
    """حصة مسلمة من المرجع الساكن المُستشهَد — cited static snapshot or None."""
    global _muslim_cache
    if _muslim_cache is None:
        _muslim_cache = {}
        try:
            with open(os.path.join(_DATA_DIR, "muslim_share.csv"),
                      encoding="utf-8") as fh:
                rows = [r for r in fh if not r.startswith("#")]
            for r in csv.DictReader(rows):
                _muslim_cache[r["iso3"].strip().upper()] = {
                    "pct": float(r["muslim_share_pct"]),
                    "ref_year": r["ref_year"], "note": r.get("note", "")}
        except Exception as e:  # noqa: BLE001 — مرجع غائب = فجوة، لا انهيار
            log.warning("muslim_share reference unavailable: %s", e)
    return _muslim_cache.get((iso3 or "").upper())


_PEW_SRC = dict(source="Pew Research Center (لقطة ساكنة مقرّبة)", confidence=0.7,
                url="https://www.pewresearch.org/religion/feature/"
                    "religious-composition-by-country-2010-2050/")


class ConsumerDemandAgent(ResearchAgent):
    """دخل وسكان (مخزن→حي) + استهلاك فردي (FAOSTAT) + اهتمام بحث (Trends) +
    حصة مسلمة (مرجع Pew ساكن) وموسمية رمضان كقاعدة معلنة عليها."""

    AGENT = "consumer_demand"
    EXPECTED = ("gdp_per_capita_usd", "population", "percapita_supply_kg",
                "search_interest", "muslim_share_pct", "ramadan_seasonality")

    def _research(self, task):
        F: list[dict] = []
        gaps: list[str] = []
        iso3 = task["iso3"]
        import silk_store
        for ind, metric, label in (("NY.GDP.PCAP.CD", "gdp_per_capita_usd",
                                    "نصيب الفرد من الناتج ($)"),
                                   ("SP.POP.TOTL", "population", "السكان")):
            got = None
            try:
                got = silk_store.get_indicator(iso3, ind)
            except Exception:  # noqa: BLE001
                got = None
            if got and got.get("value") is not None:
                F.append(_f(metric, got["value"],
                            [_src(got.get("source", "World Bank"),
                                  float(got.get("confidence") or 0.9))],
                            note=f"{label} — سنة {got.get('year')} (مخزن الحقائق)"))
            else:
                from silk_data_layer import world_bank
                dp = world_bank(iso3, ind)
                if dp.value is not None:
                    F.append(_f(metric, dp.value, [_dp_src(dp)], note=dp.note))
                else:
                    gaps.append(f"{metric}: {dp.note}")
        from silk_faostat_agent import FaostatAgent
        frep = FaostatAgent().run({"iso3": iso3, "item": task.get("product"),
                                   "year": task.get("year")})
        fdp = next((f for f in frep.findings if f.value is not None), None)
        if fdp:
            F.append(_f("percapita_supply_kg", fdp.value, [_dp_src(fdp)],
                        unit="kg/capita/yr", note=fdp.note))
        else:
            why = frep.findings[0].note if frep.findings else frep.summary
            gaps.append(f"percapita_supply_kg: {why}")
        from silk_trends_agent import TrendsAgent
        trep = TrendsAgent().run({"keyword": task.get("product"),
                                  "geo": task.get("iso2")})
        tdp = next((f for f in trep.findings if f.value is not None), None)
        if tdp:
            F.append(_f("search_interest", tdp.value, [_dp_src(tdp)],
                        note=tdp.note))
        else:
            why = trep.findings[0].note if trep.findings else trep.summary
            gaps.append(f"search_interest: {why}")
        ms = muslim_share(iso3)
        if ms:
            F.append(_f("muslim_share_pct", ms["pct"], [dict(_PEW_SRC)], unit="%",
                        note=f"لقطة ساكنة مقرّبة (إسقاطات {ms['ref_year']}) — "
                             f"{ms['note']}؛ للقراءة التجارية لا الإحصاء الرسمي"))
            likely = ms["pct"] >= 25
            F.append(_f("ramadan_seasonality",
                        "موسمية رمضان/العيدين مرجّحة تجارياً" if likely
                        else "أثر موسمية رمضان محدود متوقّعاً",
                        [dict(_PEW_SRC)], modeled=True,
                        formula="قاعدة معلنة: حصة مسلمة ≥ 25% ⇒ موسمية رمضان/"
                                "العيدين ذات أثر تجاري",
                        note="استنتاج قاعدي من الحصة المرصودة أعلاه — ليس رصد "
                             "مبيعات موسمية"))
        else:
            gaps.append(f"muslim_share_pct: {iso3} خارج المرجع الساكن — "
                        "أضف صفاً مُستشهَداً في data/muslim_share.csv")
            gaps.append("ramadan_seasonality: يتطلب حصة مسلمة مرصودة")
        return F, gaps


# ── ٧) وكيل المورّدين والمصنّعين · supplier & manufacturer ───────────────────

class SupplierAgent(ResearchAgent):
    """دليل مورّدين: سعوديون (جانب المنشأ) + موزّعون في السوق المستهدف —
    مرشّحون بالاسم برابط وتاريخ، غير موثَّقين (0.4)، لا أسماء مخترعة أبداً."""

    AGENT = "supplier"
    EXPECTED = ("saudi_suppliers", "target_distributors")

    def _research(self, task):
        F: list[dict] = []
        gaps: list[str] = []
        product = task.get("product", "")
        market = task.get("market_name", task.get("iso3", ""))
        sa, sa_refs = _entities_and_references(
            [f"{product} manufacturers suppliers Saudi Arabia",
             f"مصانع موردي {product} السعودية"],
            f"{product} مصنع مورد السعودية", region="sa")
        if sa:
            F.append(_f("saudi_suppliers", sa, sa_refs,
                        note="مرشّحو توريد سعوديون (جانب المنشأ) — غير موثَّقين، "
                             "أكّدهم قبل التعاقد"))
        else:
            gaps.append("saudi_suppliers: يتطلب SEARCH_API_KEY / "
                        "GOOGLE_MAPS_API_KEY — لا أسماء مخترعة")
        tg, tg_refs = _entities_and_references(
            [f"{product} importers wholesale distributors in {market}"],
            f"{product} wholesale distributor {market}")
        if tg:
            F.append(_f("target_distributors", tg, tg_refs,
                        note=f"مرشّحو توزيع في {market} — غير موثَّقين؛ الترقية "
                             "الموثّقة عبر /deepen"))
        else:
            gaps.append("target_distributors: يتطلب SEARCH_API_KEY / "
                        "GOOGLE_MAPS_API_KEY — لا أسماء مخترعة")
        return F, gaps


# ── المنسّق · orchestrator ───────────────────────────────────────────────────

ALL_AGENTS: tuple[type[ResearchAgent], ...] = (
    MarketSizeAgent, CompetitorAgent, RegulatoryAgent, PricingAgent,
    RiskAgent, ConsumerDemandAgent, SupplierAgent)


class ResearchOrchestrator:
    """يوزّع الوكلاء السبعة بالتوازي بمهلة، يتحقق، يجمّع، ويسجّل التشغيلات.

    فشل وكيل (خطأ/مهلة/مخطط) = مغلف failed بسببه الظاهر — لا يحجب البقية ولا
    التقرير (§4b «فشل غير محاجز وصادق»). التغطية الكلية = متوسط تغطيات الوكلاء
    (أوزان محرك القرار تأتي في Stage 4).
    """

    def __init__(self, timeout: float | None = None,
                 agent_classes=None) -> None:
        self.timeout = timeout or DEFAULT_TIMEOUT
        self.agents = [c() for c in (agent_classes or ALL_AGENTS)]

    def run_market(self, task: dict) -> dict:
        outputs: dict[str, dict] = {}
        with _cf.ThreadPoolExecutor(max_workers=len(self.agents)) as ex:
            futs = {ex.submit(a.run, dict(task)): a for a in self.agents}
            deadline = _time.monotonic() + self.timeout
            for fut, a in futs.items():
                try:
                    rep = fut.result(
                        timeout=max(0.05, deadline - _time.monotonic()))
                    outputs[a.AGENT] = self._envelope(rep, a, task)
                except _cf.TimeoutError:
                    fut.cancel()
                    outputs[a.AGENT] = _failed_output(
                        a.AGENT, task,
                        f"timeout: تجاوز الوكيل مهلة {self.timeout}s — فشل "
                        "معلن غير محاجز، بقية الوكلاء لم تتأثر")
                except Exception as e:  # noqa: BLE001 — لا يسقط سوق كامل بوكيل
                    outputs[a.AGENT] = _failed_output(
                        a.AGENT, task, f"{type(e).__name__}: {e}")
        coverage = round(sum(o["coverage"] for o in outputs.values())
                         / max(1, len(outputs)), 2)
        self._record_runs(outputs)
        return {"schema": SCHEMA, "agents": outputs, "coverage": coverage,
                "pillar_inputs": _pillar_inputs(outputs),
                "note": "حزمة وكلاء البحث السبعة — كل رقم بمصدره؛ فشل وكيل "
                        "يظهر بسببه ولا يحجب البقية"}

    @staticmethod
    def _envelope(rep: AgentReport, agent: ResearchAgent, task: dict) -> dict:
        if (rep.findings and isinstance(rep.findings[0], dict)
                and rep.findings[0].get("agent")):
            return rep.findings[0]
        # مسار حارس BaseAgent (استثناء غير متوقع): DataPoint واحد بملاحظة السبب.
        note = rep.summary or (getattr(rep.findings[0], "note", "")
                               if rep.findings else "فشل غير مفسَّر")
        return _failed_output(agent.AGENT, task, note)

    @staticmethod
    def _record_runs(outputs: dict[str, dict]) -> None:
        try:
            import silk_store
            silk_store.migrate()
            for o in outputs.values():
                silk_store.record_agent_run(
                    o["agent"], o.get("hs6", ""), o.get("iso3", ""),
                    o["status"], o["coverage"], o.get("started_at", ""),
                    o.get("finished_at", ""),
                    note="; ".join(o.get("gaps", [])[:3]))
        except Exception as e:  # noqa: BLE001 — السجل تحسين لا شرط
            log.warning("agent_runs recording skipped: %s", e)


def _metric_value(outputs: dict, agent: str, metric: str):
    for f in (outputs.get(agent) or {}).get("findings", []):
        if f.get("metric") == metric and f.get("value") is not None:
            return f["value"]
    return None


def _pillar_inputs(outputs: dict) -> dict:
    """مدخلات الأعمدة الخام لمحرك القرار (Stage 4) — قيم مرصودة أو None، لا تعويض."""
    mv = lambda a, m: _metric_value(outputs, a, m)  # noqa: E731 — اختصار موضعي
    named = mv("competitor", "named_companies") or []
    return {
        "market_attractiveness": {
            "tam_usd": mv("market_size", "tam_usd"),
            "import_cagr_pct": mv("market_size", "import_cagr_pct"),
            "gdp_per_capita_usd": mv("consumer_demand", "gdp_per_capita_usd"),
            "saudi_share_pct": mv("competitor", "saudi_share_pct")},
        "competition_intensity": {
            "hhi": mv("competitor", "hhi"),
            "top_supplier_share_pct": mv("competitor", "top_supplier_share_pct"),
            "named_company_count": len(named) if named else None},
        "regulatory_fit": {
            "tariff_applied_pct": mv("regulatory", "tariff_applied_pct"),
            "entry_requirements_count": mv("regulatory",
                                           "entry_requirements_count"),
            "eligibility_gate": mv("regulatory", "eligibility_gate")},
        "profitability": {
            "border_unit_value_usd_kg": mv("pricing", "border_unit_value_usd_kg"),
            "saudi_border_unit_value_usd_kg":
                mv("pricing", "saudi_border_unit_value_usd_kg"),
            "margin_at_border_pct": mv("pricing", "margin_at_border_pct")},
        "risk": {
            "political_stability_wgi": mv("risk", "political_stability_wgi"),
            "fx_volatility_pct": mv("risk", "fx_volatility_pct"),
            "supplier_concentration_hhi": mv("risk",
                                             "supplier_concentration_hhi"),
            "critical_risk": mv("risk", "critical_risk")},
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk research orchestrator — سبعة وكلاء، فشل معلن لا صامت "
          "(offline => فجوات موسومة، لا اختلاق)\n")
    bundle = ResearchOrchestrator(timeout=30).run_market(
        {"product": "تمور", "hs6": "080410", "iso3": "CHN", "m49": "156",
         "iso2": "CN", "market_name": "China", "year": 2023})
    for name, out in bundle["agents"].items():
        print(f"  [{out['status']:^8}] {name}: coverage={out['coverage']} "
              f"findings={sum(1 for f in out['findings'] if f['value'] is not None)} "
              f"gaps={len(out['gaps'])}")
    print(f"\n  التغطية الكلية: {bundle['coverage']}")
