"""المحلل الشامل للسوق — Silk Comprehensive Market Analyst (الموجة ٣، V5).

الطبقة ٣: وكيل كلود مركزي **بلا أدوات خارجية** — مدخلاته حصراً تقارير
البعثات الاثنتي عشرة المعزولة (الموجة ٢) + خيوط `correlation.py` إن
وُجدت (بطاقة منتج). يبني خمس تقاطعات إلزامية (كل تقاطع يستشهد بمعرّفات
نقاط بيانات من التقارير) ثم SWOT، وينتهي بمسوّدة تقييم تُسلَّم لـ
`silk_synthesis.synthesize()` (المرحلة ٢) — لا مسار حكم مستقل (٩.٣ محفوظة:
نقطة الحكم الوحيدة تبقى synthesize).

**قرار تصميم موثَّق**: `correlation.py` مبني على شكل صف `/analyze` القديم
(`components_detail`، `retail_price`، إلخ) لا شكل تقارير البعثات الجديدة
— لا محوّل شكل جديد يُبنى هنا (تجنّب ازدواجية منطق مطابقة). خيوط
`correlation.py` الجاهزة (إن حسبها المستدعي من مسار `/analyze` ببطاقة
منتج) تُمرَّر كسياق سردي إضافي (`extra_context`) غير قابل للاستشهاد
المباشر — نفس نمط `silk_synthesis._stage2` (خيوط كسياق JSON معزول).
"""
from __future__ import annotations

import json
import logging

from silk_agents import AgentReport
from silk_llm_runtime import run_llm_agent
from silk_market_resolver import MarketRef

log = logging.getLogger(__name__)

# التقاطعات الخمسة الإلزامية — the 5 required intersections (+ SWOT).
REQUIRED_CATEGORIES: tuple[str, ...] = (
    "demand", "entry_cost", "price_competitiveness", "entry_door", "swot")

_CATEGORY_LABELS = {
    "demand": "الطلب الفعلي القابل للتوجيه",
    "entry_cost": "تكلفة وصعوبة الدخول",
    "price_competitiveness": "التنافسية السعرية",
    "entry_door": "أبواب الدخول الأكثر أماناً",
    "swot": "SWOT من منظور المصدّر السعودي",
}

_ANALYST_MISSION = {
    "key": "market_analyst", "name": "المحلل الشامل للسوق",
    "allowed_tools": [],
    "instructions": (
        "أنت المحلل الشامل (الطبقة ٣) — لا أدوات لك، اقرأ فقط نتائج "
        "البعثات الاثنتي عشرة المرفقة (وأي خيوط تقاطع إن أُرفقت كسياق "
        "سردي). ابنِ **خمسة تقاطعات إلزامية بالضبط**، كل واحد بند "
        "'category' من هذه القيم **حرفياً بالضبط بأحرف صغيرة إنجليزية، لا "
        "ترجمة ولا تكبير حرف ولا مسافات إضافية**: demand, entry_cost, "
        "price_competitiveness, entry_door, swot — وبند واحد على الأقل "
        "لكل قيمة:\n"
        "1. demand = ثقافة الاستهلاك × حجم الاستيراد × السكان × نسبة "
        "المسلمين (عند صلة الحلال) — تقدير **استدلالي من مصادر موثّقة**، "
        "صرّح أنه استدلال لا حقيقة، مع إظهار المعادلة.\n"
        "2. entry_cost = الاشتراطات الجمركية × التعريفة والاتفاقيات × "
        "اللوجستيات.\n"
        "3. price_competitiveness = أسعار المنافسين × التعريفة × مؤشر "
        "اللوجستيات (تكلفة الشحن الفعلية تبقى فجوة معلنة إن لم تُرصد). "
        "إن وُجدت بطاقة منتج (تكلفة/سعر مستهدف) بين الحقائق، احسب الهامش "
        "عند المضاهاة صراحة.\n"
        "4. entry_door = قنوات التوزيع × المخاطر والأخبار — أي باب أكثر "
        "أماناً وواقعية.\n"
        "5. swot = نقاط قوة/ضعف السوق من منظور مصدّر سعودي تحديداً.\n"
        "كل رقم تذكره يجب أن يستشهد بمعرّف نقطة بيانات من نتائج البعثات "
        "المرفقة — لا اختلاق، والفجوة الحرجة تُذكر صراحة في gaps.\n\n"
        "قاعدة صارمة (بلاغ حي: خمس تقاطعات ظهرت 'دليل غير كافٍ' رغم توفر "
        "أدلة حقيقية في نفس التقرير — أرقام قطاع مسلم × واردات، سلّم أسعار "
        "Albert Heijn/Jumbo كاملاً، اشتراطات الاتحاد الأوروبي): "
        "**إن وُجد بندان مترابطان أو أكثر بين الحقائق المرفقة قابلان "
        "للربط بهذا التقاطع، فيُمنَع كتابة 'دليل غير كافٍ' — اجمعهما "
        "واكتب الحساب الحسابي صراحة** (مثال: حجم شريحة × تكرار استهلاك × "
        "نطاق سعري = مدى إمكانية إيراد؛ أظهر المعادلة والأرقام المستشهَد "
        "بها حرفياً)، ثم صرّح ما البيانات الإضافية التي كانت ستُضيّق هذا "
        "المدى. 'دليل غير كافٍ' مسموح فقط حين توجد حقيقة واحدة أو صفر "
        "متعلّقة بهذا التقاطع تحديداً — لا حين توجد بيانات لم تُستغَلّ."),
}


def _tag_source_reports(mission_reports: dict[str, AgentReport]) -> list:
    """أضف اسم البعثة المصدر لكل نتيجة — traceability: أي بعثة قالت ماذا."""
    from silk_data_layer import DataPoint

    tagged: list[DataPoint] = []
    for key, report in (mission_reports or {}).items():
        for dp in report.findings:
            tagged.append(DataPoint(dp.value, dp.source, dp.confidence,
                                    f"[{key}] {dp.note}", dp.retrieved_at,
                                    getattr(dp, "status", "")))
    return tagged


def analyze_market(market: MarketRef, product: str,
                   mission_reports: dict[str, AgentReport],
                   hs_code: str | None = None,
                   correlation_threads: dict | None = None,
                   budget: dict | None = None,
                   product_card: dict | None = None) -> dict:
    """حلّل السوق تحليلاً شاملاً — the 5 intersections + SWOT as one AgentReport.

    `mission_reports`: خرْج `silk_missions.run_all_missions()` (١٢ تقريراً).
    `correlation_threads`: خيوط `correlation.py` الجاهزة إن حُسبت مسبقاً من
    مسار ببطاقة منتج (اختياري، تُمرَّر كسياق سردي — راجع تعليق التصميم أعلى
    الملف). `product_card`: بطاقة منتج مسار /research (الموجة ٩، بلاغ حي:
    كانت لا تصل هنا إطلاقاً — "الموقع التنافسي" غائب من كل تقرير بحث عميق)
    — تصل كسياق سردي أيضاً، يستعملها المحلل لحساب الهامش عند المضاهاة
    داخل تقاطع price_competitiveness صراحة (تعليمات _ANALYST_MISSION).
    يعيد {"report": AgentReport, "by_category": {فئة: [DataPoint]},
    "missing_categories": [...]} — الفجوة معلنة لا مخفيّة.
    """
    from silk_missions import _product_card_context

    tagged = _tag_source_reports(mission_reports)
    ctx_parts = []
    if correlation_threads:
        ctx_parts.append(json.dumps(correlation_threads, ensure_ascii=False,
                                    default=str))
    card_ctx = _product_card_context(product_card)
    if card_ctx:
        ctx_parts.append(card_ctx)
    extra_context = "\n".join(ctx_parts)

    report = run_llm_agent(
        _ANALYST_MISSION, market, product=product, hs_code=hs_code,
        budget=budget, extra_findings=tagged, extra_context=extra_context)

    by_category: dict[str, list] = {c: [] for c in REQUIRED_CATEGORIES}
    # بلاغ حي (الموجة ٩): مطابقة حرفية صارمة (cat in by_category) كانت
    # تُسقِط أي بند صمتاً إن كتب كلود القيمة بحرف كبير أو مسافة زائدة
    # ("Demand" لا "demand") — فتظهر كل التقاطعات الخمسة "دليل غير كافٍ"
    # رغم أن كلود حلّل فعلاً وأنتج بنوداً حقيقية، لمجرد فشل التصنيف لاحقاً.
    # الآن: تطبيع (خفض الأحرف + قصّ المسافات) قبل المطابقة.
    _norm_map = {c.lower(): c for c in REQUIRED_CATEGORIES}
    for dp in report.findings:
        note = str(dp.note or "")
        if note.startswith("["):
            raw_cat = note[1:note.find("]")].strip()
            cat = _norm_map.get(raw_cat.lower())
            if cat:
                by_category[cat].append(dp)
    missing = [c for c in REQUIRED_CATEGORIES if not by_category[c]]
    if missing:
        labels = "، ".join(_CATEGORY_LABELS[c] for c in missing)
        report.summary = (f"{report.summary} | تقاطعات ناقصة الأدلة: "
                          f"{labels}")[:600]

    return {"report": report, "by_category": by_category,
           "missing_categories": missing}


def to_synthesis_input(result: dict) -> dict:
    """حوّل خرْج analyze_market إلى مُدخَل قابل للتسلسل — plain-value dict for
    `silk_synthesis.synthesize(analyst_assessment=...)` (AgentReport/DataPoint
    ليسا JSON-serializable مباشرة)."""
    return {
        "summary": result["report"].summary,
        "by_category": {
            cat: [{"claim": dp.value, "confidence": dp.confidence,
                  "note": dp.note} for dp in dps]
            for cat, dps in result["by_category"].items()},
        "missing_categories": result["missing_categories"],
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from silk_market_resolver import resolve_market
    from silk_missions import run_all_missions

    ref, _ = resolve_market("Nigeria")
    reports = run_all_missions(ref, product="تمور", hs_code="080410")
    out = analyze_market(ref, "تمور", reports, hs_code="080410")
    r = out["report"]
    print(f"[{'FAILED' if r.failed else 'ok'}] {r.agent_name}: {r.summary}")
    for cat, dps in out["by_category"].items():
        print(f"  {cat}: {len(dps)} finding(s)")
