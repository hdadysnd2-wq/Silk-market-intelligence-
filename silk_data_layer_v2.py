"""طبقة بيانات سِلك (v2) — derived indicators & competitor analysis.

Builds on silk_data_layer with PPP income and market-competitor ranking.
Same rule: never fabricate; failures degrade to provenance-tagged None / [].
"""
from __future__ import annotations

import logging

from silk_data_layer import (
    DataPoint,
    comtrade_trade,
    partner_name,
    primary_value,
    world_bank,
    _today,
)

log = logging.getLogger(__name__)

_SAUDI_M49 = "682"


def mirror_saudi_export(hs_code: str, target_m49: object, target_iso3: str,
                        year: int) -> DataPoint:
    """صادرات سعودية مباشرة (مرآة) — Saudi Arabia's OWN reported exports to a
    target market (Comtrade reporter=SAU, flow=X).

    تقنية «إحصاءات المرآة» في اقتصاد التجارة: يقارَن هذا بتقرير السوق الهدف
    عن وارداته من السعودية (reporter=target, partner=SAU) — تقريران مستقلان
    لنفس التدفق التجاري من جهتين جمركيتين مختلفتين، يُستخدمان للتثليث
    (`silk_research._triangulate`) حين يغيب أحدهما أو يتباعدان. لا مصدر
    جديد — Comtrade نفسه، منظور إبلاغ مختلف فقط؛ فشل/غياب => DataPoint(None)
    موسوم (المبدأ التأسيسي: لا اختلاق).
    """
    recs = comtrade_trade(hs_code, _SAUDI_M49, year, flow="X", partner=target_m49)
    pairs = [(primary_value(r), r.get("netWgt")) for r in recs]
    pairs = [(v, q) for v, q in pairs if v is not None]
    src = "UN Comtrade (تقرير سعودي مباشر — مرآة)"
    if not pairs:
        return DataPoint(
            None, src, 0.0,
            f"لا تقرير سعودي مباشر (reporter=SAU) لـ HS{hs_code}→{target_iso3} "
            f"{year} — مرآة غير متاحة", _today())
    total_usd = sum(v for v, _ in pairs)
    qtys = [float(q) for _, q in pairs if q]
    return DataPoint(
        {"value_usd": total_usd, "qty_kg": sum(qtys) if qtys else None}, src, 0.9,
        f"صادرات سعودية مُعلنة مباشرة (reporter=SAU) HS{hs_code}→{target_iso3} "
        f"{year}", _today())


def ppp_per_capita(iso3: str, year: int | None = None) -> DataPoint:
    """نصيب الفرد (تعادل القوة الشرائية) — GDP per capita, PPP (current int'l $)."""
    return world_bank(iso3, "NY.GDP.PCAP.PP.CD", year)


def market_imports(hs_code: str, market_m49: object, year: int) -> dict:
    """واردات سوق ومنافسوه من نداء Comtrade واحد — ONE call: total imports + suppliers.

    يجمع الكفاءة: الردّ نفسه يحوي صفّ «العالم» (إجمالي الواردات = حجم السوق) وصفوف
    الشركاء (المنافسون). فتغني هذه الدالة عن نداءٍ ثانٍ لحجم السوق، وتقلّ نداءات
    Comtrade للنصف — أهمّ سبب لغياب النتائج بلا مفتاح (سقف المعاينة منخفض).

    Returns {"total_usd": float|None, "competitors": [DataPoint{partner,code,
    value_usd,share}]} — competitors ranked desc by value, share = % of suppliers
    total. Empty/failed -> {"total_usd": None, "competitors": []}. Never fabricates.
    """
    recs = comtrade_trade(hs_code, market_m49, year, flow="M", partner="all")
    if not recs:
        log.warning("market_imports: no data (%s -> market %s, %s)",
                    hs_code, market_m49, year)
        return {"total_usd": None, "competitors": []}
    # جمع حسب الشريك مع التقاط صفّ العالم — aggregate per partner; capture World row.
    world: float | None = None
    totals: dict[str, float] = {}
    for rec in recs:
        code = str(rec.get("partnerCode"))
        val = primary_value(rec)
        if val is None:  # سجل بلا قيمة رقمية لا يُعدّ صفراً — لا اختلاق منافس بـ0$
            continue
        if code == "0":  # World aggregate = total market imports (market size)
            world = val
            continue
        totals[code] = totals.get(code, 0.0) + val
    grand = sum(totals.values())
    # حجم السوق: صفّ العالم إن وُجد، وإلا مجموع الشركاء (لا اختلاق) — market size.
    total_usd = world if (world and world > 0) else (grand if grand > 0 else None)
    # تحقق تقاطعي (Stage 2A): مشتقّتان لنفس الحقيقة — صف العالم ومجموع الشركاء.
    # تباين >20% يُعلَّم (سوء تبويب/نقص شركاء محتمل) ولا يُخفى ولا يُسوّى.
    xval_note = ""
    if world and world > 0 and grand > 0:
        div = abs(world - grand) / world
        if div > 0.20:
            xval_note = (f" | تباين مصادر {round(100 * div)}%: صف العالم "
                         f"{round(world):,}$ مقابل مجموع الشركاء {round(grand):,}$")
    competitors: list[DataPoint] = []
    if grand > 0:
        for code, val in sorted(totals.items(), key=lambda kv: kv[1], reverse=True):
            share = round(100 * val / grand, 2)
            competitors.append(DataPoint(
                value={"partner": partner_name(code), "code": code,
                       "value_usd": val, "share": share},
                source="UN Comtrade", confidence=0.9,
                note=f"HS{hs_code} imports to {market_m49} {year}; share {share}%",
                retrieved_at=_today(),
            ))
    return {"total_usd": total_usd, "competitors": competitors,
            "xval_note": xval_note}


def market_competitors(hs_code: str, market_m49: object, year: int) -> list[DataPoint]:
    """المنافسون في السوق — suppliers of an HS code to a market, ranked by value.

    Thin wrapper over market_imports() (kept for the agents). Each DataPoint.value
    is {partner, code, value_usd, share}, ranked desc; [] on failure.
    """
    return market_imports(hs_code, market_m49, year)["competitors"]


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk data layer v2 — demo (degrades gracefully offline)")
    dp = ppp_per_capita("SAU")
    if dp.value is None:
        print(f"  PPP/capita SAU: no data / fetch failed — {dp.note}")
    else:
        print(f"  PPP/capita SAU = {dp.value} int'l$ [{dp.source}, {dp.note}]")
    comps = market_competitors("100630", 840, 2022)  # rice into USA
    if not comps:
        print("  Competitors: no data / fetch failed")
    else:
        print(f"  Top supplier: {comps[0].value['partner']} "
              f"({comps[0].value['share']}%)")


# ── M2: قراءة من مخزن الحقائق أولاً + كتابة عابرة — store-first + write-through ──

def market_imports_cached(hs_code: str, market_m49: object, market_iso3: str,
                          year: int, live=None) -> dict:
    """واردات سوق عبر مخزن الحقائق أولاً — fact-store first, live+write-through miss.

    نفس عقد market_imports تماماً. وجود صفوف للسنة/الرمز في المخزن = إصابة (صفر
    نداء خارجي)؛ الغياب = المسار الحي القائم، وعند نجاحه تُكتب الصفوف للمخزن
    فيستفيد كل تحليل لاحق. أي فشل في طبقة المخزن يسقط بأمان للمسار الحي — المخزن
    تحسين، ليس شرطاً. لا اختلاق: مخزن فارغ لا يُنتج صفوفاً.
    """
    from silk_data_layer import M49_TO_ISO3, ISO3_TO_M49, partner_name, _today
    try:  # 1) المخزن أولاً — the warm store
        import silk_store
        got = silk_store.market_imports_from_store(hs_code, market_iso3, int(year))
        if got["total_usd"] is not None or got["partners"]:
            grand = sum(p["value_usd"] for p in got["partners"]) or None
            competitors = []
            if grand:
                for p in got["partners"]:
                    m49 = ISO3_TO_M49.get(p["iso3"], p["iso3"])
                    share = round(100 * p["value_usd"] / grand, 2)
                    competitors.append(DataPoint(
                        value={"partner": partner_name(m49), "code": str(m49),
                               "value_usd": p["value_usd"], "share": share},
                        source="UN Comtrade (مخزن الحقائق)", confidence=0.9,
                        note=f"HS{hs_code} imports to {market_iso3} {year} "
                             f"(fact store); share {share}%",
                        retrieved_at=_today()))
            return {"total_usd": got["total_usd"], "competitors": competitors,
                    "xval_note": ""}
    except Exception as e:  # noqa: BLE001 — المخزن تحسين لا شرط (هدوء: debug)
        log.debug("fact-store read unavailable (%s %s %s): %s",
                  hs_code, market_iso3, year, e)

    # 2) المسار الحي القائم — the existing live path. `live` يُمرَّر من المُرتِّب
    # ليبقى قابلاً للترقيع في اختباراته (wave8 seam) — default: هذا الملف.
    mi = (live or market_imports)(hs_code, market_m49, year)

    # 3) كتابة عابرة عند النجاح — write-through so the NEXT run is store-warm.
    try:
        if mi["total_usd"] is not None or mi["competitors"]:
            import silk_store
            rows = []
            if mi["total_usd"] is not None:
                rows.append({"hs6": hs_code, "reporter_iso3": market_iso3,
                             "partner_iso3": "WLD", "year": int(year), "flow": "M",
                             "value_usd": mi["total_usd"]})
            for c in mi["competitors"]:
                v = c.value or {}
                piso = M49_TO_ISO3.get(str(v.get("code")), str(v.get("code")))
                rows.append({"hs6": hs_code, "reporter_iso3": market_iso3,
                             "partner_iso3": piso, "year": int(year), "flow": "M",
                             "value_usd": v.get("value_usd")})
            if rows:
                silk_store.migrate()
                silk_store.upsert_trade_flows(rows)
    except Exception as e:  # noqa: BLE001 — never break the live path
        log.warning("fact-store write-through failed (%s %s %s): %s",
                    hs_code, market_iso3, year, e)
    return mi
