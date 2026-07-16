"""معاينة فورية لمنتج جديد — «هل يستحق دراسة كاملة؟» (R4، أُعيد تصميمها ITEM ٢).

**قرار حي (تدقيق تكلفة، راجع docs/DEEP_RESEARCH_DECISIONS.md)**: النسخة
الأصلية كانت تعيد استخدام بعثة pricing_scout بميزانية مقيَّدة — نداء كلود
حقيقي واحد على كل زوج (منتج × سوق) جديد. أُزيل هذا النداء نهائياً: المعاينة
الآن **مجانية دوماً** — مورّدو كومتريد فقط (بلا كلود إطلاقاً)، وأي لقطة أسعار
منافِسة كانت خُزِّنت قبل هذا القرار تبقى تُعرَض من المخزن (بيانات مدفوعة
الثمن سلفاً، إعادة عرضها مجانية بحق). على زوج جديد لم يُلقَط قط: لا سعر
منافِس، فجوة معلنة صريحة — لا اختلاق، ولا نداء يسدّها تلقائياً.

المبدأ المؤسِّس: بلا شبكة/مفتاح => كل حقل فجوة معلنة، لا اختلاق. اللقطة
تُخزَّن لكل (منتج، سوق) فتكرار السؤال يُخدَم من المخزن بلا حرق أرصدة
(silk_storage.get/save_product_snapshot).
"""
from __future__ import annotations

import datetime
import logging

from silk_data_layer import _today

log = logging.getLogger(__name__)

# سوق مرجعي افتراضي للقطة حين لا يحدّد المستخدم سوقاً — الدراسة الكاملة
# وحدها ترتّب كل الأسواق؛ اللقطة تفحص إشارة تنافسية ضد سوق واحد شفافاً.
_DEFAULT_PROBE_MARKET = "ARE"


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


def quick_snapshot(product: str, hs_code: str | None, market) -> dict:
    """معاينة فورية مجانية لمنتج × سوق — تعيد بنية جاهزة للتخزين/العرض.

    مورّدو كومتريد فقط — **بلا أي نداء كلود** (ITEM ٢، بلاغ حي التكلفة).
    لا سعر منافِس على زوج جديد لم يُلقَط قط: فجوة معلنة صريحة توجّه إلى
    البحث العميق، لا اختلاق ولا نداء يسدّها تلقائياً.
    """
    suppliers = _top_suppliers(hs_code, market)
    return {
        "product": product,
        "hs_code": hs_code,
        "market": {"iso3": market.iso3, "m49": market.m49,
                   "name_ar": market.name_ar, "name_en": market.name_en},
        "competing_products": [],
        "top_suppliers": suppliers,
        "worth_full_study": _worth_full_study([], suppliers, ""),
        "note": ("معاينة مجانية من بيانات محفوظة (كومتريد) — الأسعار "
                 "التنافسية غير مرصودة هنا؛ البحث العميق يرصدها ببحث حقيقي "
                 "مسعَّر بشفافية."),
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
