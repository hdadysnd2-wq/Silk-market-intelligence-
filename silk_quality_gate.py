"""بوابة الجودة قبل التسليم لسِلك — Silk pre-delivery quality gate (الموجة ١٠).

تشغَّل تلقائياً في نهاية كل `/research`، **قبل** أن يُعرَض DOCX — فحوصات
حتمية (لا كلود) على `view["deep_research"]` النهائي: لا رموز شركاء خامة،
لا تقطيع منتصف كلمة، لا تسريب Markdown/JSON خام، لا أرقام ثقة خامة في
المتن، تغطية الملحق التقني، عدم إعلان "دليل غير كافٍ" حين توجد أدلة كافية،
ترتيب/اكتمال الأقسام الأحد عشر (§10.3)، وصحة البعثات (بعثة بلا نتائج
مستشهَد بها). حكم PASS / PASS-WITH-WARNINGS / FAIL؛ النتائج القابلة
للإصلاح (Markdown/ثقة خام/تقطيع) تُصلَح آلياً بالفعل في طبقة العرض
(`silk_reports._strip_inline_markdown`/`_evidence_badge`/`_truncate_at_word`)
— هذه البوابة حارس انحدار يتأكد أنها فعلاً أُصلحت، لا مصلح مستقل. النتائج
غير القابلة للإصلاح (بنيوية/بيانات) تُبنى كملاحظات تُعرَض داخل قسم
"منهجية البحث ونطاقه" (٢) — لا لافتة تحذير على الغلاف، ولا صمت.

منطق فحص صرف: صفر شبكة، صفر تعديل على الأرقام — قراءة وتشكيل فقط، مثل
`silk_render.py` تماماً.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

PASS, WARN, FAIL = "PASS", "PASS-WITH-WARNINGS", "FAIL"

_MARKDOWN_RE = re.compile(r"(^#{1,6}\s)|(```)|(\*\*)", re.M)
_RAW_JSON_RE = re.compile(r'[{]\s*"[a-zA-Z_]+"\s*:', re.M)
_RAW_CONFIDENCE_RE = re.compile(r"\(?ثقة\s*0")
_TERMINAL_PUNCT = ".!?:؛،؟…\"'”)"


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


def _check_bare_partner_codes(dr: dict) -> list[dict]:
    """رمز شريك خام بدل اسم — حارس انحدار دائم لإصلاح ١٠.٢أ
    (`silk_data_layer.partner_name`) لا فحصاً أولياً؛ يُتوقَّع نظافته دوماً
    الآن لكنه يبقى يرصد أي تسرّب مستقبلي (مصدر بيانات جديد لا يمرّ عبر
    partner_name)."""
    findings = []
    for key, m in (dr.get("missions") or {}).items():
        for f in (m.get("findings") or []):
            v = f.get("value")
            if isinstance(v, dict) and "partner" in v:
                p = str(v.get("partner") or "")
                if p.isdigit():
                    findings.append({
                        "check": "bare_partner_code", "repairable": False,
                        "note": f"[{key}] رمز شريك خام بلا اسم: {p!r}"})
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


def _check_agent_health(dr: dict) -> list[dict]:
    """بعثات بلا أي نتيجة مستشهَد بها — تُسرَد صراحة، لا تُخفى داخل ملخّص.

    بعثة **فشلت فعلياً** (`failed=True`) أشد من بعثة نجحت لكن لم تجد
    جديداً (مثل `opportunity_gaps` حين تكون كل الفرص مغطّاة أصلاً في
    البعثات الأخرى) — الأولى بند `agent_failed` (تُفشِل الحكم)، الثانية
    `agent_empty` (ملاحظة منهجية فقط، لا تُفشِل الحكم وحدها)."""
    findings = []
    for key, m in (dr.get("missions") or {}).items():
        if m.get("failed"):
            findings.append({
                "check": "agent_failed", "repairable": False,
                "note": f"البعثة '{key}' فشلت بلا نتائج مستشهَد بها — "
                       f"{m.get('summary') or 'بلا ملخّص'}"})
        elif not (m.get("findings") or []):
            findings.append({
                "check": "agent_empty", "repairable": False,
                "note": f"البعثة '{key}' نجحت لكن بلا نتائج مستشهَد بها — "
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
    findings += _check_bare_partner_codes(dr)
    findings += _check_intersection_insufficiency(dr)
    findings += _check_section_structure(dr)
    findings += _check_agent_health(dr)
    findings += _check_audit_coverage(dr)
    findings += _check_analyst_layer_failure(dr)

    non_repairable = [f for f in findings if not f["repairable"]]
    if not findings:
        verdict = PASS
    elif any(f["check"] in ("section_structure", "agent_failed",
                            "analyst_layer_failed") for f in non_repairable):
        verdict = FAIL
    else:
        verdict = WARN

    methodology_notes = [f["note"] for f in non_repairable]
    return {"verdict": verdict, "findings": findings,
           "methodology_notes": methodology_notes}
