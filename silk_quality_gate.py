"""بوابة الجودة قبل التسليم لسِلك — Silk pre-delivery quality gate (الموجة ١٠).

تشغَّل تلقائياً في نهاية كل `/research`، **قبل** أن يُعرَض DOCX — فحوصات
حتمية (لا كلود) على `view["deep_research"]` النهائي: لا رموز شركاء خامة،
لا تقطيع منتصف كلمة، لا تسريب Markdown/JSON خام، لا أرقام ثقة خامة في
المتن، لا تسريب سباكة داخلية (LLMAgent:*/وسوم dp)، تغطية الملحق التقني،
عدم إعلان "دليل غير كافٍ" حين توجد أدلة كافية، ترتيب/اكتمال الأقسام
الأحد عشر (§10.3)، وصحة البعثات (بعثة بلا نتائج مستشهَد بها). حكم PASS /
PASS-WITH-WARNINGS / FAIL؛ النتائج القابلة للإصلاح (Markdown/ثقة خام/
تقطيع/سباكة داخلية) تُصلَح آلياً بالفعل في طبقة العرض
(`silk_reports._strip_inline_markdown`/`_evidence_badge`/`_truncate_at_word`،
`silk_render._strip_internal_plumbing`) — هذه البوابة حارس انحدار يتأكد
أنها فعلاً أُصلحت، لا مصلح مستقل. النتائج غير القابلة للإصلاح (بنيوية/
بيانات) تُبنى كملاحظات تُعرَض داخل قسم "منهجية البحث ونطاقه" (٢) — لا
لافتة تحذير على الغلاف، ولا صمت.

منطق فحص صرف: صفر شبكة، صفر تعديل على الأرقام — قراءة وتشكيل فقط، مثل
`silk_render.py` تماماً.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

PASS, WARN, FAIL = "PASS", "PASS-WITH-WARNINGS", "FAIL"

_MARKDOWN_RE = re.compile(r"(^#{1,6}\s)|(```)|(\*\*)", re.M)
# مفتاح JSON بأي حروف (لا اللاتينية فقط) — بلاغ حي: حكم مسرَّب عُرِّبت
# مفاتيحه ("{\"الحكم\":...}") فأفلت من [a-zA-Z_]+؛ [^"\s]+ يلتقط الصيغتين.
_RAW_JSON_RE = re.compile(r'[{]\s*"[^"\s]+"\s*:', re.M)
_RAW_CONFIDENCE_RE = re.compile(r"\(?ثقة\s*0")
_TERMINAL_PUNCT = ".!?:؛،؟…\"'”)"
# بلاغ منتج من المالك: التقرير المعروض للعميل كشف السباكة الداخلية
# ("LLMAgent:tariffs_agreements"، وسوم استشهاد خام "dp7") — كلود يستشهد
# أحياناً حرفياً بوسوم رآها في مدخلاته. طبقة العرض تُصلح هذا فعلاً
# (silk_render._strip_internal_plumbing)؛ هذا الفحص حارس انحدار.
_INTERNAL_PLUMBING_RE = re.compile(r"LLM(?:Mission)?Agent:[A-Za-z_]+|\[?dp\d+\]?")
# بلاغ مالك (تسريب سباكة ٢): أسماء حقول داخلية إنجليزية ("verdict"،
# "confidence 0.64") ومفاتيح بعثات snake_case خام ("pricing_scout") ظهرت في
# نص معروض للعميل. طبقة العرض تُصلح فعلاً (_strip_internal_plumbing يعرّب
# الحقول، وlabel العربي يحل محل المفتاح) — هذان حارسا انحدار حتميان.
_EN_FIELD_LEAK_RE = re.compile(r"\b(?:verdict|confidence)\b")


def _check_markdown_and_raw_json(text: str) -> list[dict]:
    findings = []
    if not text:
        return findings
    if _MARKDOWN_RE.search(text):
        findings.append({"check": "markdown_artifacts", "repairable": True,
                         "note": "تسريب رموز Markdown (#/```/**) في النص المصدَر"})
    if _RAW_JSON_RE.search(text):
        findings.append({"check": "raw_json", "repairable": True,
                         "note": "كتلة JSON خام مسرَّبة في النص المصدَر"})
    return findings


def _check_raw_confidence(text: str) -> list[dict]:
    if text and _RAW_CONFIDENCE_RE.search(text):
        return [{"check": "raw_confidence", "repairable": True,
                 "note": "رقم ثقة خام '(ثقة 0.x)' مسرَّب في النص المصدَر"}]
    return []


def _check_mid_word_truncation(text: str) -> list[dict]:
    """تقطيع منتصف كلمة — آخر سطر في كل **فقرة** (كتلة أسطر متتالية بين
    سطرين فارغين) ينتهي بحرف/رقم بلا علامة ترقيم ختامية، مع طول كافٍ
    يستبعد عناوين/فواصل قصيرة عادية (بلاغ حي: "لا تتوفر من أد"). يفحص
    آخر سطر في الفقرة فقط لا كل سطر — نثر مُلفوف يدوياً عبر أسطر متعددة
    (تنسيق شائع للمصدر) لا يجب أن يُبلَّغ سطراً سطراً كتقطيع مزيَّف؛
    التقطيع الحقيقي يظهر في نهاية الوحدة المولَّدة لا وسطها."""
    if not text:
        return []
    findings = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        s = lines[-1]
        if s.startswith(("#", "|", "-", "*")):
            continue
        if len(s) < 25:
            continue
        if s[-1] not in _TERMINAL_PUNCT and not s.endswith("**"):
            findings.append({"check": "mid_word_truncation", "repairable": True,
                             "note": f"فقرة تنتهي بلا علامة ترقيم ختامية: "
                                     f"'...{s[-40:]}'"})
    return findings


def _check_trailing_ellipsis(text: str) -> list[dict]:
    """§5/§6 (أمر العمل الرئيس) — لا فقرة/حقيقة تنتهي بنقاط حذف «…»/«...»
    (بتر غير نظيف). حارس انحدار: القصّ النظيف (silk_reports._trim_sentence)
    يقطع عند حدّ جملة بلا نقاط حذف؛ ظهورها يعني بتراً وصل المُسلَّم."""
    if not text:
        return []
    findings = []
    for block in re.split(r"\n\s*\n", text):
        s = block.strip()
        if s.endswith("…") or s.endswith("..."):
            findings.append({"check": "trailing_ellipsis", "repairable": True,
                             "note": "نصّ ينتهي بنقاط حذف «…» — بتر غير نظيف "
                                     "(§5): يجب القصّ عند حدّ جملة أو العرض كاملاً"})
    return findings


def _check_internal_plumbing_leak(text: str) -> list[dict]:
    """تسريب سباكة داخلية (اسم وكيل خام/وسم استشهاد dp) في نص التقرير
    المصدَر — بلاغ منتج من المالك. حارس انحدار: طبقة العرض
    (`silk_render._strip_internal_plumbing`) تُصلح هذا فعلاً قبل وصول
    النص هنا؛ ظهوره يعني ثغرة في التطبيع لا حالة طبيعية."""
    if not text:
        return []
    if _INTERNAL_PLUMBING_RE.search(text):
        return [{"check": "internal_plumbing_leak", "repairable": True,
                 "note": "تسريب سباكة داخلية (اسم وكيل/وسم استشهاد خام) "
                        "في نص التقرير المصدَر"}]
    return []


def _check_english_field_and_mission_key_leak(text: str) -> list[dict]:
    """حقول داخلية إنجليزية (verdict/confidence) أو مفاتيح بعثات snake_case
    خام (pricing_scout وأخواتها) في نص معروض للعميل — حارس انحدار: طبقة
    العرض تعرّب الحقول (`_strip_internal_plumbing`) وتستبدل المفتاح بالاسم
    العربي (`label` في النموذج القانوني)؛ ظهور أيٍّ منها يعني ثغرة تطبيع.
    مفاتيح البعثات تُستورد كسولاً من السجل الواحد (silk_missions.MISSIONS)
    — لا قائمة يدوية تتقادم؛ فشل الاستيراد يمرّر فحص الحقول وحده."""
    findings = []
    if not text:
        return findings
    if _EN_FIELD_LEAK_RE.search(text):
        findings.append({"check": "english_field_leak", "repairable": True,
                         "note": "اسم حقل داخلي إنجليزي (verdict/confidence) "
                                "مسرَّب في النص المصدَر"})
    try:
        from silk_missions import MISSIONS
        keys_re = re.compile(
            r"\b(?:" + "|".join(re.escape(k) for k in MISSIONS) + r")\b")
        if keys_re.search(text):
            findings.append({"check": "mission_key_leak", "repairable": True,
                             "note": "مفتاح بعثة داخلي خام (snake_case) "
                                    "مسرَّب في النص المصدَر"})
    except Exception:  # noqa: BLE001 — حارس ثانوي، لا يعطّل البوابة
        pass
    return findings


# §2 (أمر العمل الرئيس — سرّية: صفر سباكة داخلية في المُسلَّم): محفّزات
# تُفشِل البوابة حتمياً إن ظهرت في نصّ التقرير أو ملخّصات المصادر. طبقة
# العرض (silk_render._strip_internal_plumbing) تُحيّدها فعلاً قبل وصول النص
# هنا — ظهور أيٍّ منها = ثغرة تطبيع، لا حالة طبيعية (حارس انحدار حتمي).
#   لا تُطبَع القيمة المطابَقة في الملاحظة كي لا تُعيد البوابة تسريبها بنفسها.
_CONFIDENTIALITY_LEAK_PATTERNS = [
    ("tool_use_leak", re.compile(r"tool[-\s]?use", re.I), "وسم استخدام أداة"),
    ("claude_mention", re.compile(r"\bClaude\b|كلود"), "ذكر صريح للأداة (كلود)"),
    ("env_var_leak", re.compile(r"SILK_[A-Z_]+"), "اسم متغيّر بيئة داخلي"),
    ("research_track_leak", re.compile(r"مسار(?:ات)?\s+(?:ال)?بحث"),
     "نسبة الحقائق لمسار بحث داخلي"),
    ("facts_list_leak", re.compile(r"بين\s+الحقائق"),
     "تلميح لقائمة حقائق داخلية"),
    ("ops_warning_leak", re.compile(r"⚠"), "رمز تحذير تشغيلي"),
]


# §8 (أمر العمل الرئيس — بوابة الأسلوب الحتمية): جودة العربية التجارية.
#   FAIL: «م$» (اختزال عملة)، «(1)» ترقيم إنجليزي داخل فقرة، «بين الحقائق».
#   WARN: «من ناحية» > مرّتين (سقف رابط)، رقم مفتاحي مميَّز مكرَّر > مرّتين.
_MSHORT_STYLE_RE = re.compile(r"\d\s*م\$")
_INLINE_ENUM_RE = re.compile(r"(?<![\n(])\s\(\d\)")   # «(1)» وسط سطر لا بدايته
_CONNECTOR_RE = re.compile(r"من ناحية")
# رقم مفتاحي مميَّز: نسبة بكسر عشري («55.28%») أو رقم بفواصل آلاف («61,000,000»)
# أو قيمة HHI مجاورة للفظها — عادةً لا يتكرّر طبيعياً، فتكراره >مرّتين حشو.
_KEYFIG_RES = [
    re.compile(r"\d{1,3}\.\d+\s*%"),
    re.compile(r"\d{1,3}(?:,\d{3}){2,}"),
    re.compile(r"HHI[^0-9]{0,8}\d{3,5}"),
]


def _check_style(text: str) -> list[dict]:
    """§8 — جودة الأسلوب الحتمية (بلا كلود). FAIL على اختزال العملة/الترقيم
    الإنجليزي داخل الفقرة؛ WARN على تجاوز سقف الروابط أو تكرار رقم مفتاحي."""
    findings = []
    if not text:
        return findings
    if _MSHORT_STYLE_RE.search(text):
        findings.append({"check": "style_currency_shorthand", "repairable": True,
                         "note": "اختزال العملة «م$» — اكتب «مليون دولار» كاملةً"})
    if _INLINE_ENUM_RE.search(text):
        findings.append({"check": "style_inline_enumeration", "repairable": False,
                         "note": "ترقيم إنجليزي «(1)…(2)» داخل فقرة — استعمل "
                                 "أولاً/ثانياً أو قائمة مرقّمة"})
    conn = len(_CONNECTOR_RE.findall(text))
    if conn > 2:
        findings.append({"check": "style_connector_overuse", "repairable": False,
                         "note": f"عبارة «من ناحية» تكرّرت {conn} مرّات "
                                 "(الحدّ مرّتان) — نوّع أدوات الربط"})
    for rex in _KEYFIG_RES:
        counts: dict = {}
        for m in rex.finditer(text):
            tok = re.sub(r"\s+", "", m.group(0))
            counts[tok] = counts.get(tok, 0) + 1
        for tok, n in counts.items():
            if n > 2:
                findings.append({
                    "check": "style_repeated_key_figure", "repairable": False,
                    "note": f"رقم مفتاحي «{tok}» تكرّر {n} مرّات في المتن "
                            "(الحدّ مرّتان) — اذكره كاملاً مرّة ثم أحِل إليه"})
    return findings


def _check_confidentiality_leaks(text: str) -> list[dict]:
    """§2 — تسريب سرّية في المُسلَّم (اسم أداة/متغيّر بيئة/مسار بحث/…). حارس
    انحدار: يُفشِل البوابة إن أفلت أيّ محفّز من طبقة التطهير."""
    findings = []
    for check, pat, human in _CONFIDENTIALITY_LEAK_PATTERNS:
        if pat.search(text or ""):
            findings.append({
                "check": check, "repairable": True,
                "note": f"تسريب سرّية داخلي في نصّ التقرير ({human}) — "
                        "يجب تحييده قبل التسليم"})
    return findings


def _check_bare_partner_codes(dr: dict) -> list[dict]:
    """رمز شريك خام بدل اسم — حارس انحدار دائم لإصلاح ١٠.٢أ
    (`silk_data_layer.partner_name`) لا فحصاً أولياً؛ يُتوقَّع نظافته دوماً
    الآن لكنه يبقى يرصد أي تسرّب مستقبلي (مصدر بيانات جديد لا يمرّ عبر
    partner_name).

    سدّ تسريب (الطبقة ٧ — مفارقة البوابة): كانت ملاحظة هذا الفحص نفسها
    تحمل مفتاح البعثة الخام (snake_case) وتنسيق repr بايثون الخام
    (`{p!r}` → `'042'` بعلامات اقتباس بايثونية) — وهذه الملاحظة
    (`repairable: False`) تُحقَن مباشرة في قسم "منهجية البحث ونطاقه"
    المعروض للعميل عبر `methodology_notes`؛ أي بوابة الجودة كانت تكتشف
    تسريباً ثم تُصدر تسريباً موازياً بنفسها. الاسم التجاري + بلا تنسيق
    بايثون الآن، بنفس `_mission_label` المستعمَل في بقية هذا الملف."""
    findings = []
    for key, m in (dr.get("missions") or {}).items():
        label = _mission_label(key)
        for f in (m.get("findings") or []):
            v = f.get("value")
            if isinstance(v, dict) and "partner" in v:
                p = str(v.get("partner") or "")
                if p.isdigit():
                    findings.append({
                        "check": "bare_partner_code", "repairable": False,
                        "note": f"[{label}] رمز شريك خام بلا اسم: «{p}»"})
    return findings


def _check_intersection_insufficiency(dr: dict) -> list[dict]:
    """"دليل غير كافٍ" رغم وجود ≥٢ بند ذي صلة — بلاغ حي (الموجة ٩-١٠)."""
    from silk_market_analyst import _CATEGORY_LABELS
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    by_cat = (dr.get("analyst") or {}).get("by_category") or {}
    findings = []
    for cat, label in _CATEGORY_LABELS.items():
        items = by_cat.get(cat) or []
        if len(items) < 2:
            continue
        idx = text.find(label)
        window = text[idx:idx + 400] if idx >= 0 else text
        if "دليل غير كافٍ" in window or "لا تتوفر بيانات كافية" in window:
            findings.append({
                "check": "intersection_insufficiency", "repairable": False,
                "note": f"تقاطع '{label}' يحوي {len(items)} بند(اً) ذا صلة "
                       "لكن النص يعلن 'دليل غير كافٍ' بدل الحساب الحسابي"})
    return findings


def _check_section_structure(dr: dict) -> list[dict]:
    """ترتيب/اكتمال الأقسام الأحد عشر (§10.3) — يعيد استعمال الفحص الحتمي
    الموجود أصلاً في silk_ai_judge (مصدر حقيقة واحد لا تكرار منطق)."""
    from silk_ai_judge import _section_order_issues
    text = ((dr.get("report") or {}).get("text") or "")
    if not text:
        return []
    return [{"check": "section_structure", "repairable": False, "note": issue}
           for issue in _section_order_issues(text)]


def _mission_label(key: str) -> str:
    """اسم البعثة التجاري بالعربية — بلاغ منتج من المالك: ملاحظات هذه
    البوابة تصل قسم "حدود المنهجية وجودة البيانات" في التقرير المعروض
    للعميل مباشرة؛ المفتاح snake_case الخام (مثل "tariffs_agreements")
    سباكة داخلية لا لغة تجارية."""
    try:
        from silk_missions import MISSIONS
        row = MISSIONS.get(key)
        if row and row.get("name"):
            return row["name"]
    except Exception:  # noqa: BLE001 — تسمية تجميلية لا شرط فحص
        pass
    return key.replace("_", " ")


def _check_agent_health(dr: dict) -> list[dict]:
    """بعثات بلا أي نتيجة مستشهَد بها — تُسرَد صراحة، لا تُخفى داخل ملخّص.

    بعثة **فشلت فعلياً** (`failed=True`) أشد من بعثة نجحت لكن لم تجد
    جديداً (مثل `opportunity_gaps` حين تكون كل الفرص مغطّاة أصلاً في
    البعثات الأخرى) — الأولى بند `agent_failed` (تُفشِل الحكم)، الثانية
    `agent_empty` (ملاحظة منهجية فقط، لا تُفشِل الحكم وحدها)."""
    findings = []
    for key, m in (dr.get("missions") or {}).items():
        label = _mission_label(key)
        if m.get("failed"):
            findings.append({
                "check": "agent_failed", "repairable": False,
                "note": f"بعثة '{label}' فشلت بلا نتائج مستشهَد بها — "
                       f"{m.get('summary') or 'بلا ملخّص'}"})
        elif not (m.get("findings") or []):
            findings.append({
                "check": "agent_empty", "repairable": False,
                "note": f"بعثة '{label}' نجحت لكن بلا نتائج مستشهَد بها — "
                       f"{m.get('summary') or 'بلا ملخّص'}"})
    return findings


def _check_analyst_layer_failure(dr: dict) -> list[dict]:
    """فشل طبقة المحلل الشامل كاملة — بلاغ حي إنتاجي (تمور/هولندا): نداءا
    المحلل الشامل وكاتب التقرير تجاوزا مهلة ثابتة فأعادا None، فظهرت
    التقاطعات الخمسة كلها "دليل غير كافٍ" مع غياب التقرير الكامل — ومرّت
    البوابة رغم ذلك لأن كل الفحوصات أعلاه تشترط نص تقرير غير فارغ.

    هذا فحص مستقل لا يشترط وجود نص: تشغيلة بلا تقرير كامل **و** بخمس
    تقاطعات معلنة كلها ناقصة الأدلة معاً = فشل الطبقة كلها، لا نتيجة
    تحليل حقيقية — لا يجوز أن تمر بحكم PASS/PASS-WITH-WARNINGS."""
    from silk_market_analyst import REQUIRED_CATEGORIES

    text = ((dr.get("report") or {}).get("text") or "")
    if text:
        return []
    missing = set((dr.get("analyst") or {}).get("missing_categories") or [])
    if missing >= set(REQUIRED_CATEGORIES):
        return [{"check": "analyst_layer_failed", "repairable": False,
                 "note": "طبقة المحلل الشامل فشلت كاملة: التقاطعات الخمسة "
                        "كلها بلا أدلة كافية والتقرير الكامل غائب — نداء "
                        "المحلل الشامل و/أو كاتب التقرير فشل (مهلة أو خطأ "
                        "شبكة)، لا نتيجة تحليل حقيقية لهذه التشغيلة"}]
    return []


_AUDIT_APPENDIX_CAP = 80


def _check_audit_coverage(dr: dict) -> list[dict]:
    """سقف ملحق ٨٠ صفاً — إن تجاوزه إجمالي الاستشهادات، أعلن القطع صراحة
    بدل حذف صامت (نفس مبدأ "لا سقف صامت" المتّبع في هذا المشروع)."""
    total = sum(len(m.get("findings") or [])
               for m in (dr.get("missions") or {}).values())
    if total > _AUDIT_APPENDIX_CAP:
        return [{"check": "audit_coverage", "repairable": False,
                 "note": f"{total} استشهاداً إجمالياً يتجاوز سقف الملحق "
                        f"التقني ({_AUDIT_APPENDIX_CAP}) — يُعرَض أول "
                        f"{_AUDIT_APPENDIX_CAP} فقط، معلَناً هنا لا صامتاً"}]
    return []


# Q2 (تدقيق CAGR غير متسق، تمور/هولندا): معدّل نمو سنوي مركّب واحد قد يظهر
# برقمين مختلفين على نافذتَي سنوات مختلفتين (الملخّص «13.3% (2020-2024)»
# مقابل الحكم «16.3% (2019-2023)») بلا مصالحة. نلتقط «معدّل نمو مؤطَّر بنافذة»
# = نسبة مئوية تجاور لفظَ نموٍّ ونافذةَ سنوات ضمن الجملة نفسها.
_GROWTH_KW_RE = re.compile(r"نمو|مركّب|مركب|سنوي|CAGR|معدّل النمو|compound", re.I)
_PCT_RE = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%")
_YEAR_WINDOW_RE = re.compile(r"(?:19|20)\d{2}\s*[-–—]\s*(?:19|20)\d{2}")


def _check_cagr_consistency(dr: dict) -> list[dict]:
    """اكشف أكثر من معدّل نمو سنوي مركّب بنوافذ سنوات مختلفة بلا مصالحة —
    نفس المقياس، سنوات أساس مختلفة، رقمان متعارضان. يمسح سرد الكاتب + تعليل
    الحكم + ملخّص المحلل (المصادر التي أظهرت التعارض فعلاً في البلاغ الحيّ)."""
    report_text = (dr.get("report") or {}).get("text") or ""
    verdict = dr.get("verdict") or {}
    reasoning = " ".join(str(x) for x in [
        (verdict.get("ai") or {}).get("reasoning"), verdict.get("note"),
        ((dr.get("analyst") or {}).get("report") or {}).get("summary")] if x)
    blob = report_text + "\n" + reasoning
    all_windows = [(m.start(), re.sub(r"\s+", "", m.group(0)))
                   for m in _YEAR_WINDOW_RE.finditer(blob)]
    # قُرب (لا تقسيم جُمَل — «.» يكسر العشري «13.3%»): لكل نسبة يجاورها لفظُ
    # نموٍّ ضمن ±45 محرفاً، نربطها بأقربِ نافذةِ سنوات إليها (أقلّ مسافة، ≤45)
    # — فلا تختطف نسبةٌ نافذةَ جملةٍ أخرى في نصٍّ قصير.
    windowed: list[tuple[str, str]] = []
    for pm in _PCT_RE.finditer(blob):
        ctx = blob[max(0, pm.start() - 45):pm.end() + 45]
        if not _GROWTH_KW_RE.search(ctx):
            continue
        near = [(abs(wp - pm.start()), w) for wp, w in all_windows
                if abs(wp - pm.start()) <= 45]
        if not near:
            continue
        windowed.append((pm.group(1), min(near)[1]))
    distinct_vals = {v for v, _ in windowed}
    distinct_wins = {w for _, w in windowed}
    if len(distinct_vals) >= 2 and len(distinct_wins) >= 2:
        pairs = "، ".join(f"{v}% ({w})" for v, w in dict.fromkeys(windowed))
        return [{
            "check": "cagr_inconsistency", "repairable": False,
            "note": ("معدّلات نمو سنوي مركّب متعارضة على نوافذ سنوات مختلفة "
                     f"بلا مصالحة: {pairs} — يجب اعتماد معدّل واحد قانوني مع "
                     "ذكر نافذته، وأيّ بديل يُذكر بنافذته صراحة")}]
    return []


# Q3 (تدقيق عملة العمود المضلِّل، تمور/هولندا): عمود «السعر/كجم بالدولار»
# يحمل قيماً باليورو مع اعتذار داخل الخليّة — وعدٌ بتحويلٍ لم يُجرَ. نكشف عمود
# عملةٍ يَعِد بعملةٍ بينما النصّ يحمل رموز عملةٍ أخرى.
_CURRENCY_LABELS = {
    "USD": re.compile(r"بالدولار|\bUSD\b|دولار"),
    "EUR": re.compile(r"باليورو|\bEUR\b|€|يورو"),
    "GBP": re.compile(r"بالجنيه|\bGBP\b|£|جنيه إسترليني"),
}


def _check_currency_label_mismatch(dr: dict) -> list[dict]:
    """اكشف عمودَ سعرٍ يَعِد بعملةٍ بينما القيم بعملةٍ أخرى (تحويل غير مُنجَز).

    البلاغ الحيّ: عنوان العمود «السعر/كجم بالدولار» بينما الخلايا يورو. نكتفي
    بإشارةٍ نصّية حتمية: ذكرُ «بالدولار» (وعدُ عمودٍ بالدولار) مع وجود رموز
    يورو/جنيه في التقرير نفسه (أو العكس) = وعدُ تحويلٍ لم يُجرَ."""
    text = (dr.get("report") or {}).get("text") or ""
    # عنوان عمود يَعِد بعملة صراحةً (صيغة «بالـ…» داخل ترويسة السعر).
    promised = [cur for cur, pat in _CURRENCY_LABELS.items()
                if re.search(r"السعر[^|]{0,20}" + {"USD": "بالدولار",
                             "EUR": "باليورو", "GBP": "بالجنيه"}[cur], text)]
    for cur in promised:
        others = [c for c in _CURRENCY_LABELS
                  if c != cur and _CURRENCY_LABELS[c].search(text)]
        if others:
            return [{
                "check": "currency_label_mismatch", "repairable": False,
                "note": (f"عمود السعر مُعنوَن بـ{cur} بينما التقرير يحمل قيماً "
                         f"بعملة أخرى ({'، '.join(others)}) — عنوِن العمود "
                         "بالعملة المرصودة فعلاً، ولا تَعِد بتحويلٍ لم يُجرَ")}]
    return []


def run_quality_gate(view: dict) -> dict:
    """شغّل بوابة الجودة على `view["deep_research"]` — يعيد
    {"verdict": PASS|WARN|FAIL, "findings": [...], "methodology_notes": [...]}.

    `findings`: كل بنود الفحص (قابل للإصلاح أو لا). `methodology_notes`:
    نصوص عربية جاهزة للعرض داخل قسم "منهجية البحث ونطاقه" — البنود غير
    القابلة للإصلاح فقط (القابلة للإصلاح مُصلَحة فعلاً في طبقة العرض،
    عرضها كملاحظة منهجية يكرر معلومة صحيحة الآن بلا داعٍ)."""
    dr = view.get("deep_research") if isinstance(view, dict) else None
    if not dr:
        return {"verdict": PASS, "findings": [], "methodology_notes": []}

    text = ((dr.get("report") or {}).get("text") or "")
    summaries = " ".join(str((m or {}).get("summary") or "")
                         for m in (dr.get("missions") or {}).values())
    combined_text = text + "\n" + summaries

    findings: list[dict] = []
    findings += _check_markdown_and_raw_json(combined_text)
    findings += _check_raw_confidence(combined_text)
    # ملخّصات البعثات عبارات قصيرة عمداً بلا علامة ترقيم ختامية بالاصطلاح
    # (راجع أي AgentReport.summary في المشروع) — فحص التقطيع يقتصر على نص
    # التقرير السردي الكامل (كاتب التقرير) حيث التقطيع الحقيقي مرصود فعلاً.
    findings += _check_mid_word_truncation(text)
    findings += _check_trailing_ellipsis(text)
    findings += _check_internal_plumbing_leak(text)
    findings += _check_english_field_and_mission_key_leak(text)
    findings += _check_confidentiality_leaks(combined_text)
    findings += _check_style(text)
    findings += _check_bare_partner_codes(dr)
    findings += _check_intersection_insufficiency(dr)
    findings += _check_section_structure(dr)
    findings += _check_cagr_consistency(dr)
    findings += _check_currency_label_mismatch(dr)
    findings += _check_agent_health(dr)
    findings += _check_audit_coverage(dr)
    findings += _check_analyst_layer_failure(dr)

    non_repairable = [f for f in findings if not f["repairable"]]
    # سدّ تسريب (الطبقة ٧ — مفارقة البوابة): هذه الفحوصات مُعلَّمة
    # repairable=True لأن *صنف* النتيجة يُصلَح عادة في طبقة العرض قبل أن
    # يصل النص هنا (راجع تعليق الوحدة) — لكن حين تُطلِق أحدها فعلياً، فهذا
    # يعني أن الإصلاح **فشل تحديداً في هذه التشغيلة**، والنص الخام وصل
    # بالفعل إلى DOCX المُسلَّم قبل أن تُشغَّل هذه البوابة (راجع
    # api.py._attach_quality_gate — تُشغَّل بعد بناء العرض لا قبله).
    # تخفيضها بصمت إلى WARN كان يعني أن البوابة تكتشف تسريباً فعلياً
    # ثم تكتمه هي نفسها بدل أن تُصعِّده — لا يجوز أن يمرّ هذا بحكم أهدأ من
    # فشل بنيوي حقيقي (section_structure/agent_failed).
    _REGRESSION_GUARD_FIRED = {"internal_plumbing_leak", "english_field_leak",
                               "mission_key_leak", "raw_confidence",
                               "trailing_ellipsis", "tool_use_leak",
                               "claude_mention", "env_var_leak",
                               "research_track_leak", "facts_list_leak",
                               "ops_warning_leak",
                               # §8: اختزال العملة والترقيم الإنجليزي داخل
                               # الفقرة يُفشِلان (FAIL)؛ سقف الروابط وتكرار
                               # الرقم المفتاحي يبقيان WARN (تحذير أسلوبي).
                               "style_currency_shorthand",
                               "style_inline_enumeration"}
    guard_fired = [f for f in findings if f["check"] in _REGRESSION_GUARD_FIRED]
    severe = non_repairable + guard_fired
    if not findings:
        verdict = PASS
    elif any(f["check"] in ("section_structure", "agent_failed",
                            "analyst_layer_failed") for f in non_repairable) \
            or guard_fired:
        verdict = FAIL
    else:
        verdict = WARN

    methodology_notes = [f["note"] for f in severe]
    return {"verdict": verdict, "findings": findings,
           "methodology_notes": methodology_notes}
