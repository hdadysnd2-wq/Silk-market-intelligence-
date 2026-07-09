"""بعثات وكلاء كلود الاثني عشر لسِلك — Silk's 12 Claude tool-use missions
(الموجة ٢ من التكليف الختامي — V5).

كل مهمة: مفتاح + اسم + وصف مهمة + تعليمات مخصّصة (تُلحَق بـ`_PRINCIPLE` في
نظام `silk_llm_runtime._run_loop`) + قائمة أدوات مسموحة حصراً (من
`silk_llm_runtime.TOOLS`). المهمة ١٢ (`opportunity_gaps`) بلا أدوات
خاصة بها — تقرأ نتائج الوكلاء ١-١١ فقط (`extra_findings`، تُسجَّل كنقاط
بيانات قابلة للاستشهاد بها — silk_llm_runtime._run_loop).

التسجيل في `AGENT_CATALOG` **إضافي لا استبدال** (قرار المالك أثناء هذه
الموجة): الصفوف الـ١٤ القائمة تبقى كما هي، وهذه الصفوف الـ١٢ تُضاف
بمفاتيح مختلفة — `/analyze` الحالي لا يتأثر؛ مسار البحث العميق الجديد
(`POST /research`، الموجة ٤) هو من يستدعي `run_all_missions` أدناه.
"""
from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutureTimeout

import silk_agents
from silk_agents import AgentReport
from silk_llm_runtime import LLMMissionAgent
from silk_market_resolver import MarketRef

log = logging.getLogger(__name__)

# لغة السوق المستهدف (§ملاحظة التكليف): pricing_scout/consumer_culture/
# channels_importers يُطلَب منها البحث بلغة السوق صراحةً — سطر مشترك يُلحَق
# بتعليماتها الثلاث فلا يتكرر نصاً بحرفه.
_SEARCH_IN_MARKET_LANGUAGE = (
    " ابحث بلغة (لغات) السوق المستهدف، لا الإنجليزية فقط، حين يكون ذلك "
    "متاحاً — نتائج محلية اللغة أدق من ترجمة استعلام إنجليزي.")

MISSIONS: dict[str, dict] = {
    "pricing_scout": {
        "key": "pricing_scout", "name": "وكيل استكشاف الأسعار",
        "mission": "أسعار المنتجات المنافسة الفعلية في السوق المستهدف",
        "allowed_tools": ["web_search", "trends_interest"],
        "instructions": (
            "ابحث عن أسعار تجزئة/جملة فعلية لمنتجات تنافس منتج المستخدم في "
            "السوق المستهدف: المنتج، العلامة، السعر، العملة، المتجر/الرابط، "
            "التاريخ. حوّل لدولار أمريكي بسعر صرف مُعلَن المصدر. أي سعر بلا "
            "رابط = 'غير موثَّق'. لا تُقدّر سعراً لم تجده فعلاً."
            + _SEARCH_IN_MARKET_LANGUAGE),
    },
    "consumer_culture": {
        "key": "consumer_culture", "name": "وكيل ثقافة المستهلك",
        "mission": "ثقافة الاستهلاك للفئة في السوق المستهدف",
        "allowed_tools": ["web_search", "trends_interest", "lookup_reference"],
        "instructions": (
            "حلّل: عادات استهلاك الفئة، البُعد الديني (الحلال — استخدم نسبة "
            "المسلمين من lookup_reference جدول demographics)، المواسم "
            "(رمضان/الأعياد)، تفضيلات التغليف واللغة، حساسية بلد المنشأ "
            "(كيف ينظر السوق للمنتجات السعودية). افصل الحقيقة الموثّقة عن "
            "الانطباع صراحةً." + _SEARCH_IN_MARKET_LANGUAGE),
    },
    "trade_flow": {
        "key": "trade_flow", "name": "وكيل تدفق التجارة",
        "mission": "حجم استيراد السوق ومساراته لرمز HS هذه المهمة",
        "allowed_tools": ["comtrade_imports"],
        "instructions": (
            "احسب من comtrade_imports: حجم الاستيراد، النمو خلال ٥ سنوات إن "
            "توفرت، وأشر لأي موسمية ظاهرة في الأرقام. أعداد فقط مما عاد من "
            "الأداة — لا تقدير لسنة غير مجلوبة."),
    },
    "demographics_economy": {
        "key": "demographics_economy", "name": "وكيل الديموغرافيا والاقتصاد",
        "mission": "سكان واقتصاد السوق المستهدف وربطهما بحجم الشريحة المستهدَفة",
        "allowed_tools": ["worldbank_indicator", "lookup_reference"],
        "instructions": (
            "اجمع: السكان ونموهم، الدخل للفرد وPPP، نسبة الشباب إن أمكن، "
            "ونسبة المسلمين (lookup_reference جدول demographics). اربطها "
            "بحجم الشريحة المستهدَفة للمنتج — احسب لا تُقدّر."),
    },
    "competitors": {
        "key": "competitors", "name": "وكيل المنافسين",
        "mission": "الدول والشركات المنافسة في السوق المستهدف",
        "allowed_tools": ["comtrade_imports", "web_search"],
        "instructions": (
            "الدول المنافسة وحصصها من comtrade_imports (بيانات فعلية)، "
            "والشركات/العلامات بالاسم من بحث الويب (موسومة 'غير موثَّقة') "
            "مع نقاط قوتها المُعلَنة. لا تكرّر بحث الأسعار — ذاك عمل "
            "pricing_scout ويُقاطَع لاحقاً في التحليل الشامل."),
    },
    "customs_requirements": {
        "key": "customs_requirements", "name": "وكيل الاشتراطات الجمركية",
        "mission": "قائمة تحقق دخول السوق ومتطلبات المنشأ السعودي",
        "allowed_tools": ["lookup_reference", "web_search"],
        "instructions": (
            "المرجع الثابت (lookup_reference جدول requirements) هو المصدر "
            "الأساس — اعرضه كما هو أولاً. استخدم بحث الويب فقط للتحقق "
            "المستهدَف من تحديثات حديثة، لا لاكتشاف اشتراطات من الصفر. "
            "اذكر شهادات الحلال/SONCAP/CIQ/SFDA متى انطبقت."),
    },
    "tariffs_agreements": {
        "key": "tariffs_agreements", "name": "وكيل التعريفات والاتفاقيات",
        "mission": "التعريفة الجمركية المطبَّقة وأثر اتفاقيات التجارة",
        "allowed_tools": ["wits_tariff", "lookup_reference"],
        "instructions": (
            "التعريفة المطبَّقة من wits_tariff، وعضوية الاتفاقيات من "
            "lookup_reference جدول agreements (GAFTA/OIC/AfCFTA/GCC/WTO). "
            "إن كانت التعريفة المطبَّقة أدنى من المتوقع MFN، سمِّها "
            "'تفضيل محتمل — تحقق' لا حقيقة مؤكدة."),
    },
    "logistics": {
        "key": "logistics", "name": "وكيل اللوجستيات",
        "mission": "جاهزية اللوجستيات وأفضل ميناء ملائم",
        "allowed_tools": ["worldbank_indicator", "lookup_reference", "web_search"],
        "instructions": (
            "مؤشر أداء اللوجستيات (worldbank_indicator indicator="
            "logistics_lpi) وأفضل ميناء ملائم من jeddah/dammam "
            "(lookup_reference جدول ports للسوق المستهدف). خطوط شحن منشورة "
            "إن وُجدت عبر بحث الويب. زمن/تكلفة الشحن غير المرصودين = فجوة "
            "معلنة، لا تقدير."),
    },
    "channels_importers": {
        "key": "channels_importers", "name": "وكيل قنوات التوزيع والمستوردين",
        "mission": "أبواب الدخول الفعلية للسوق المستهدف",
        "allowed_tools": ["channels_importers", "web_search"],
        "instructions": (
            "أبواب الدخول: مستورد/موزّع/تجزئة/تجارة إلكترونية/معارض "
            "تجارية. المرشّحون بالاسم من channels_importers يُوسَمون "
            "'غير موثَّقين — التحقق عبر التعميق'." + _SEARCH_IN_MARKET_LANGUAGE),
    },
    "demand_trends": {
        "key": "demand_trends", "name": "وكيل اتجاهات الطلب",
        "mission": "اتجاه الطلب والموسمية للمنتج في السوق المستهدف",
        "allowed_tools": ["trends_interest", "faostat_supply"],
        "instructions": (
            "اهتمام البحث (trends_interest) خلال ٥ سنوات وموسميته، ونصيب "
            "الفرد من السلعة (faostat_supply) إن كان المنتج غذائياً فقط."),
    },
    "risk_news": {
        "key": "risk_news", "name": "وكيل المخاطر والأخبار",
        "mission": "الاستقرار السياسي ومخاطر العملة وآخر الأخبار القطاعية",
        "allowed_tools": ["worldbank_indicator", "gdelt_news"],
        "instructions": (
            "الاستقرار السياسي وسيادة القانون (worldbank_indicator "
            "political_stability/rule_of_law)، وأهم ١٠ عناوين قطاعية من "
            "GDELT آخر ١٢ شهراً (عنوان/تاريخ/رابط). تقلّب سعر الصرف من "
            "البيانات المتاحة فقط، لا تخمين."),
    },
    "opportunity_gaps": {
        "key": "opportunity_gaps", "name": "وكيل الفرص والفجوات",
        "mission": "تركيب الفرص والفجوات من تقارير الوكلاء ١-١١ (يعمل أخيراً)",
        "allowed_tools": [],
        "instructions": (
            "لا أدوات لك — اقرأ فقط نتائج الوكلاء الأحد عشر السابقين "
            "(مُرفَقة). استخرج: طلباً غير ملبّى، مورّدين يفقدون حصتهم، "
            "مزايا سعودية (قرب، اتفاقية، حلال)، وفجوات بيانات تستحق "
            "التعميق. كل استنتاج يستشهد بمعرّف نقطة بيانات من التقارير "
            "المرفقة — لا استنتاج بلا سند."),
    },
}

# ترتيب التشغيل الثابت — the fixed run order (12 runs last, reads 1-11).
MISSION_ORDER: tuple[str, ...] = (
    "pricing_scout", "consumer_culture", "trade_flow", "demographics_economy",
    "competitors", "customs_requirements", "tariffs_agreements", "logistics",
    "channels_importers", "demand_trends", "risk_news", "opportunity_gaps",
)

# صفوف الكتالوج الإضافية — additive AGENT_CATALOG rows (لوحة «إعدادات
# الوكلاء»)، مسجَّلة عند استيراد هذا الملف. مفاتيح مختلفة عن الـ١٤ القائمة
# فلا تصادم؛ paid=False (تستهلك عدّاد SILK_PAID_DAILY_CAP لإضافات الذكاء
# الاصطناعي عبر silk_ai_judge.ai_extras_blocked — نفس بوابة consumer/dynamics
# القائمة، لا بوابة PAID الجديدة).
_CATALOG_ROWS = [
    {"key": m["key"], "name": m["name"], "role": f"{m['mission']} · Claude+أدوات",
     "paid": False}
    for m in MISSIONS.values()
]
silk_agents.register_agents(_CATALOG_ROWS)

# ميزانية وكيل واحد ضمن تشغيلة الاثني عشر — أخفض من ميزانية silk_llm_runtime
# الافتراضية (٨) لأن ١١ وكيلاً يعملون معاً؛ يبقى قابلاً للضبط بيئياً.
_MISSION_BUDGET = {
    "tool_calls": int(os.environ.get("SILK_MISSION_TOOL_CALLS", "5")),
    "max_output_tokens": int(os.environ.get("SILK_MISSION_MAX_TOKENS", "4000")),
}
_MISSION_TIMEOUT_S = int(os.environ.get("SILK_MISSION_TIMEOUT_S", "90"))


def _timed_out_report(key: str) -> AgentReport:
    return AgentReport(
        f"LLMMissionAgent:{key}", [], True,
        f"{key}: تجاوز المهلة الزمنية ({_MISSION_TIMEOUT_S}s) — استثناء "
        "لا يوقف بقية الوكلاء (ThreadPoolExecutor)")


def run_all_missions(market: MarketRef, product: str = "",
                     hs_code: str | None = None) -> dict[str, AgentReport]:
    """شغّل البعثات الاثنتي عشرة — missions 1-11 in parallel (ThreadPoolExecutor,
    المستودع متزامن — لا asyncio)، ثم opportunity_gaps (12) قارئاً نتائجها.

    فشل/مهلة وكيل واحد = تقرير فاشل موسوم لا يوقف البقية (نفس مبدأ
    `ResearchManager.distribute`). Returns {mission_key: AgentReport}.
    """
    reports: dict[str, AgentReport] = {}
    parallel_keys = [k for k in MISSION_ORDER if k != "opportunity_gaps"]

    def _run_one(key: str) -> AgentReport:
        agent = LLMMissionAgent(MISSIONS[key])
        return agent.run({"market": market, "product": product,
                          "hs_code": hs_code, "budget": _MISSION_BUDGET})

    with ThreadPoolExecutor(max_workers=len(parallel_keys) or 1) as pool:
        futures = {pool.submit(_run_one, k): k for k in parallel_keys}
        for fut, key in futures.items():
            try:
                reports[key] = fut.result(timeout=_MISSION_TIMEOUT_S)
            except _FutureTimeout:
                log.warning("mission %s timed out after %ss", key, _MISSION_TIMEOUT_S)
                reports[key] = _timed_out_report(key)
            except Exception as e:  # noqa: BLE001 — عزل الأعطال، لا سقوط جماعي
                log.warning("mission %s raised: %s", key, e)
                reports[key] = AgentReport(
                    f"LLMMissionAgent:{key}", [], True,
                    f"{key}: خطأ غير متوقع: {type(e).__name__}: {e}")

    prior_findings = [dp for k in parallel_keys for dp in reports[k].findings]
    gaps_agent = LLMMissionAgent(MISSIONS["opportunity_gaps"])
    reports["opportunity_gaps"] = gaps_agent.run({
        "market": market, "product": product, "hs_code": hs_code,
        "budget": _MISSION_BUDGET, "extra_findings": prior_findings})
    return reports


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from silk_market_resolver import resolve_market
    ref, _ = resolve_market("Nigeria")
    all_reports = run_all_missions(ref, product="تمور", hs_code="080410")
    for key, report in all_reports.items():
        flag = "FAILED" if report.failed else "ok"
        print(f"  [{flag}] {key}: {report.summary}")
