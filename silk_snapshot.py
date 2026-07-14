"""لقطة سريعة لمنتج جديد — «هل يستحق دراسة كاملة؟» (R4).

يعيد استخدام بعثة pricing_scout (R1، القطعة المركزية) في **وضع مقيَّد
الميزانية** + مورّدي كومتريد مباشرة (بلا كلود) — نداء كلود واحد رخيص لا
تشغيلة الاثنتي عشرة بعثة كاملة. المخرَج: منتجات منافِسة، نطاق سعر، أبرز
مورّدين، وحكم أولي عمّا إذا كان المنتج يستحق دراسة كاملة.

المبدأ المؤسِّس: بلا شبكة/مفتاح => كل حقل فجوة معلنة، لا اختلاق. اللقطة
تُخزَّن لكل (منتج، سوق) فتكرار السؤال يُخدَم من المخزن بلا حرق أرصدة
(silk_storage.get/save_product_snapshot).
"""
from __future__ import annotations

import datetime
import logging

from silk_data_layer import _today

log = logging.getLogger(__name__)

# ميزانية مقيَّدة — لقطة رخيصة لا بحث كامل (بعثة pricing_scout العميقة = 9).
_QUICK_TOOL_CALLS = 3
_QUICK_MAX_TOKENS = 1500
# سوق مرجعي افتراضي للقطة حين لا يحدّد المستخدم سوقاً — الدراسة الكاملة
# وحدها ترتّب كل الأسواق؛ اللقطة تفحص إشارة تنافسية ضد سوق واحد شفافاً.
_DEFAULT_PROBE_MARKET = "ARE"


def _competing_from_report(report) -> list[dict]:
    """استخرج المنتجات المنافِسة من تقرير pricing_scout — كل بند بمصدره
    وشارة دليله (✓/◐). قيمة غير نصية (dict/list) تُتخطّى؛ لا اختلاق."""
    out: list[dict] = []
    for f in getattr(report, "findings", None) or []:
        val = getattr(f, "value", None)
        if val is None or isinstance(val, (list, dict)):
            continue
        note = str(getattr(f, "note", "") or "")
        evidence = "◐" if ("غير موثَّق" in note or "◐" in note) else "✓"
        out.append({"item": str(val), "source": getattr(f, "source", "") or "",
                    "evidence": evidence,
                    "date": getattr(f, "retrieved_at", "") or ""})
    return out


def _top_suppliers(hs_code: str | None, market, top_n: int = 5) -> list[dict]:
    """أبرز الدول المورّدة للسوق (كومتريد ثنائي، بلا كلود) — فجوة معلنة عند
    غياب رمز HS أو تعذّر الجلب (لا اختلاق)."""
    if not hs_code:
        return []
    try:
        from silk_data_layer_v2 import market_competitors
        this_year = datetime.date.today().year
        for y in (this_year - 1, this_year - 2, this_year - 3):
            comps = market_competitors(hs_code, market.m49, y)
            if comps:
                return [{"partner": c.get("partner"), "share": c.get("share"),
                         "year": y}
                        for c in comps[:top_n] if c.get("partner")]
    except Exception as e:  # noqa: BLE001 — تعذّر الجلب فجوة لا عطل
        log.warning("quick snapshot suppliers failed (HS%s): %s", hs_code, e)
    return []


def _worth_full_study(competing: list, suppliers: list, note: str) -> dict:
    """حكم أولي حتمي — يستحق دراسة كاملة متى وُجدت إشارة تنافسية فعلية
    (منتجات منافِسة أو مورّدون مرصودون). لا إشارة => لا حسم (قد لا يستحق،
    أو تعذّر الرصد فجوةً) — لا نقول 'لا يستحق' بيقين على غياب بيانات."""
    signals = []
    if competing:
        signals.append(f"{len(competing)} منتج منافِس مرصود")
    if suppliers:
        signals.append(f"{len(suppliers)} مورّد فعلي في كومتريد")
    if signals:
        return {"worth": True,
                "why": "إشارة تنافسية فعلية: " + "، ".join(signals)
                       + " — يستحق دراسة كاملة لترتيب الأسواق والهامش."}
    return {"worth": None,
            "why": "لم تُرصد إشارة تنافسية في هذه اللقطة السريعة "
                   f"({note or 'لا نتائج'}) — قد لا يستحق، أو تعذّر الرصد "
                   "(فجوة). الدراسة الكاملة تحسم عبر مصادر أوسع."}


def quick_snapshot(product: str, hs_code: str | None, market,
                   tool_calls: int = _QUICK_TOOL_CALLS) -> dict:
    """لقطة سريعة لمنتج × سوق — تعيد بنية جاهزة للتخزين/العرض.

    نداء كلود واحد (بعثة pricing_scout بميزانية مقيَّدة) + مورّدو كومتريد.
    بلا شبكة/مفتاح => بعثة تعيد تقريراً فاشلاً/فارغاً بفجوات معلنة (حارس
    BaseAgent) فتخرج competing=[]، والحكم «لا حسم» — لا اختلاق.
    """
    from silk_missions import MISSIONS
    from silk_llm_runtime import LLMMissionAgent

    budget = {"tool_calls": int(tool_calls), "max_output_tokens": _QUICK_MAX_TOKENS}
    report = LLMMissionAgent(MISSIONS["pricing_scout"]).run(
        {"market": market, "product": product, "hs_code": hs_code,
         "budget": budget})
    competing = _competing_from_report(report)
    suppliers = _top_suppliers(hs_code, market)
    summary = getattr(report, "summary", "") or ""
    return {
        "product": product,
        "hs_code": hs_code,
        "market": {"iso3": market.iso3, "m49": market.m49,
                   "name_ar": market.name_ar, "name_en": market.name_en},
        "competing_products": competing,
        "top_suppliers": suppliers,
        "worth_full_study": _worth_full_study(competing, suppliers, summary),
        "note": ("لقطة أولية ضد سوق مرجعي واحد — الدراسة الكاملة ترتّب كل "
                 "الأسواق. " + summary).strip(),
        "generated_at": _today(),
        "from_store": False,
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("United Arab Emirates")
    snap = quick_snapshot("تمر", "080410", ref)
    print("worth:", snap["worth_full_study"])
    print("competing:", len(snap["competing_products"]),
          "suppliers:", len(snap["top_suppliers"]))
