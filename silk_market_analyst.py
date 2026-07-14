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
from silk_ai_judge import _LONG_TIMEOUT
from silk_llm_runtime import _truncate_at_word, run_llm_agent
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
        # ترقية المرحلة ١ (حلّل كل شيء): القاعدة الجوهرية الوحيدة قبل أي
        # تعليمة أخرى — لا تقتصر على الصيغ الأربع المذكورة أدناه، فهي
        # أرضية توضيحية لا سقف. امسح كل نقطة بيانات من كل بعثة وقارنها
        # بكل نقطة أخرى ذات صلة محتملة عبر البعثات الأخرى.
        "أنت المحلل الشامل (الطبقة ٣) — لا أدوات لك، اقرأ فقط نتائج "
        "البعثات الاثنتي عشرة المرفقة (وأي خيوط تقاطع إن أُرفقت كسياق "
        "سردي). مهمتك الجوهرية: **حلّل كل شيء**. لا تكتفِ بربط زوج ثابت "
        "من العوامل لكل تقاطع — امسح كل حقيقة وردت من أي بعثة وابحث عن "
        "كل علاقة حقيقية تربطها بأي حقيقة أخرى عبر البعثات الاثنتي عشرة: "
        "الديموغرافيا والدين والثقافة والدخل والأسعار والاستيراد "
        "والمورّدين والمنافسين والتنظيم واللوجستيات والمخاطر والموسمية، "
        "وأي مزيج آخر بينها تدعمه الحقائق المرفقة فعلياً. لا توجد قائمة "
        "مغلقة من العلاقات المسموحة. أمثلة لمستوى التحليل المطلوب "
        "(أرضية لا سقف): نسبة السكان المسلمين × واردات المنتج تكشف حجم "
        "الطلب الحقيقي وموسمية رمضان؛ الدخل للفرد × أسعار الرفّ يحدّد "
        "الشريحة المستهدَفة فعلياً؛ ثقافة الاستهلاك × حجم واردات المنتجات "
        "القريبة يكشف انفتاحاً على المنتج المستورَد أو مقاومته؛ تركّز "
        "المورّدين (HHI) × مستوى الأسعار السائد يكشف فرصة تسعير حقيقية "
        "للدخول.\n\n"
        "نظّم كل هذا الفحص الشامل ضمن **خمسة تقاطعات إلزامية بالضبط**، "
        "كل واحد بند 'category' من هذه القيم **حرفياً بالضبط بأحرف "
        "صغيرة إنجليزية، لا ترجمة ولا تكبير حرف ولا مسافات إضافية**: "
        "demand, entry_cost, price_competitiveness, entry_door, swot — "
        "وبند واحد على الأقل لكل قيمة، دون التقيّد بصيغة حسابية واحدة "
        "جامدة لكل تقاطع — استعمل كل إشارة ذات صلة توفّرت فعلاً، لا "
        "إشارة واحدة فقط لأن المثال التوضيحي ذكرها:\n"
        "1. demand = اجمع كل ما يخصّ حجم الطلب الفعلي القابل للتوجيه — "
        "ثقافة الاستهلاك، حجم الاستيراد ونموه، السكان ونسبة المسلمين عند "
        "صلة الحلال، الموسمية، أي اتجاه بحث ذي صلة — تقدير **استدلالي "
        "من مصادر موثّقة**، صرّح أنه استدلال لا حقيقة، مع إظهار المعادلة.\n"
        "2. entry_cost = الاشتراطات الجمركية × التعريفة والاتفاقيات × "
        "اللوجستيات × أي عامل تنظيمي آخر يرفع أو يخفّض تكلفة الدخول "
        "الفعلية.\n"
        "3. price_competitiveness = أسعار المنافسين × التعريفة × مؤشر "
        "اللوجستيات × تركّز المورّدين × الدخل للفرد (يحدّد ما يتحمّله "
        "المستهلك فعلياً — تكلفة الشحن الفعلية تبقى فجوة معلنة إن لم "
        "تُرصد). إن وُجدت بطاقة منتج (تكلفة/سعر مستهدف) بين الحقائق، "
        "احسب الهامش عند المضاهاة صراحة.\n"
        "4. entry_door = قنوات التوزيع × المخاطر والأخبار × نتائج بعثة "
        "الفجوات (opportunity_gaps) — أي باب أكثر أماناً وواقعية، ولماذا "
        "بالتحديد بناءً على أكثر من إشارة واحدة.\n"
        "5. swot = التوليف الختامي من منظور مصدّر سعودي تحديداً — ليس "
        "قائمة نقاط منعزلة عن بقية التقاطعات، بل الحلقة التي تربط "
        "الأربعة أعلاه بسلسلة استدلال منطقية واحدة متماسكة تنتهي بخلاصة "
        "قابلة للتنفيذ: دخول أم لا، عبر من تحديداً، بأي سعر تقريبي، "
        "وبأي تسلسل خطوات.\n\n"
        "التزامات إضافية إلزامية تسري على التقاطعات الخمسة كلها معاً، "
        "لا تقاطعاً واحداً فقط:\n"
        "- **التثليث والتناقض**: إن ورد رقم متعارض أو متطابق من مصدرين "
        "مختلفين بين الحقائق المرفقة، صرّح بالتناقض صراحة — لا تختر "
        "أحدهما بصمت.\n"
        "- **المقارنة المرجعية**: أي رقم تذكره، إن وُجد رقم مقارن (سوق "
        "بديل، متوسط إقليمي، منافس آخر) بين الحقائق المرفقة، اذكر "
        "المقارنة صراحة بدل عرض الرقم منعزلاً بلا مرجع.\n"
        "- **'إذن ماذا؟' للمصدّر السعودي**: كل بند تكتبه ينتهي بأثره "
        "المباشر على قرار المصدّر — لا استعادة للحقيقة الخام دون تفسير "
        "لدلالتها.\n"
        "- **وزن الدليل**: ميّز صراحة بين رقم مرصود مباشرة من مصدر "
        "(أقوى)، ورقم مقدَّر استدلالاً (أضعف)، وفجوة معلنة (الأضعف) — لا "
        "تُصغ القيمة المقدَّرة بنفس يقين القيمة المرصودة.\n"
        "- **الفجوات الحرجة**: ضمن تقاطع swot تحديداً، اذكر أهم فجوة "
        "بيانات كانت ستُغيّر القرار لو رُصدت، وأي مصدر/بعثة كان يُفترض "
        "أن يوفّرها.\n\n"
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


def _comprehensive_digest(by_category: dict[str, list]) -> str:
    """ابنِ ملخّصاً شاملاً حتمياً (بلا نداء كلود إضافي) من نتائج التقاطعات
    الخمسة معاً — ترقية المرحلة ١: كاتب التقرير ومُوَلِّف الحكم (المرحلة ٢)
    كانا يستقبلان فقط سطر حالة آلي مقتضب من `run_llm_agent` (سقف ٧٠٠ حرف
    — عبارة تذييل عامة مثل 'نداءات أدوات: N'، لا تحليلاً)، بينما التحليل
    الشامل الفعلي (تقاطعات demand/entry_cost/... التي ينتجها المحلل) كان
    يصل الملحق التقني فقط ولا يصل متن التقرير المكتوب ولا حكم كلود مطلقاً.
    الآن: نبني نص القراءة الفعلي من نفس البنود المصنَّفة (by_category)
    فيصل الكاتب والحكم كلاهما التحليل الحقيقي لا سطر حالة فارغاً تقريباً."""
    parts = []
    for cat in REQUIRED_CATEGORIES:
        items = by_category.get(cat) or []
        if not items:
            continue
        label = _CATEGORY_LABELS[cat]
        claims = "؛ ".join(str(dp.value)[:320] for dp in items[:5])
        parts.append(f"{label}: {claims}")
    return _truncate_at_word(" | ".join(parts), 3000)


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
        budget=budget, extra_findings=tagged, extra_context=extra_context,
        timeout=_LONG_TIMEOUT)

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

    # ترقية المرحلة ١: استبدل سطر الحالة المقتضب (راجع تعليق
    # _comprehensive_digest) بالتحليل الشامل الفعلي — هذا ما يصل الكاتب
    # (analyst_summary) وحكم كلود (المرحلة ٢) الآن، لا مجرد عدّاد نداءات.
    digest = _comprehensive_digest(by_category)
    if digest:
        report.summary = digest
    if missing:
        labels = "، ".join(_CATEGORY_LABELS[c] for c in missing)
        report.summary = _truncate_at_word(
            f"{report.summary} | تقاطعات ناقصة الأدلة: {labels}", 3000)

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
