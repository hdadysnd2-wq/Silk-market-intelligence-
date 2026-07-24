"""حارس المعقولية عبر المصادر (HF3) — يقارن كلَّ مقدارٍ مُبتلَعٍ (حجم سوقٍ
مكشوطٍ مثلاً) بمرتكزات التشغيلة **المُتحقَّقة** (إجمالي الواردات، السكان، الناتج
للفرد) **قبل** التصيير، فلا يصل العميلَ رقمٌ متعارضٌ مع بيانات المنصّة نفسها بلا
مصالحة.

الباعث (تقرير قطر × HS 200811، ٢٠٢٦-٠٧-٢٣): «حجم سوق الفول السوداني الكامل في
قطر قُدِّر بـ 497 مليون دولار» بينما إجمالي واردات قطر لنفس البند ≈ ٧ ملايين
دولار وسكانها ٢٫٨٦ مليون — أي ≈١٧٤ دولاراً للفرد سنوياً من صنفٍ واحد. رقمٌ على
بُعد رتبتين من مرتكزات المنصّة، يهدم ثقة العميل لحظةَ يدقّقه أحد.

عقيدة التصميم (مرآةُ استشارة A2، `docs/DESIGN_A2_SUPPLIER_PLAUSIBILITY.md`):
- **إشارةٌ مصاحِبة لا بوّابةٌ وحيدة**: لا تحذف رقماً ولا تُبقيه صامتاً — إمّا
  إسقاطٌ بسببٍ مُسجَّل أو تصييرٌ بتحفّظِ نطاقٍ صريح. لا يُختلَق رقمٌ ولا يُصحَّح.
- **عتباتٌ من البيئة، صفرُ رقمٍ مكتوبٍ صلباً في المنطق**؛ فشلٌ آمنٌ مفتوح: بلا
  مرتكزٍ مُتحقَّقٍ لا حكم (لا اتهامَ رقمٍ بلا مرجعٍ نقارنه به).
- **كلُّ علامةٍ تُسجَّل في مانيفست التشغيلة** (`view["deep_research"]
  ["plausibility_flags"]` + حدث تتبّعٍ أفضلَ جهدٍ) — قابليةُ تدقيقٍ كاملة.

هرمتيّ بالكامل: صفرُ شبكةٍ وصفرُ مفتاح — يقرأ حقائقَ البعثات المُجمَّعة فقط.
"""
from __future__ import annotations

import logging
import os
import re

log = logging.getLogger("silk.plausibility")

# ── العتبات (config-driven، لا رقم مكتوب صلباً في المنطق) ────────────────────
_DEF_MAX_IMPORT_MULT = 20.0      # حجمُ سوقٍ يفوق واردات البند بأكثر من هذا = علامة
_DEF_MAX_PER_CAPITA = 500.0      # دولارٌ للفرد سنوياً من صنفٍ واحد فوقه = علامة


def enabled() -> bool:
    """صمّام الحارس — `SILK_PLAUSIBILITY` (افتراضيّ مُفعَّل: حارسُ نزاهةٍ لا
    يُختلِق ولا يُنفِق، يكتفي بالتحفّظ/الإسقاط المُعلَن). ضعه «0» لإطفائه."""
    return os.environ.get("SILK_PLAUSIBILITY", "1").strip() != "0"


def _f_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "").strip() or default)
    except (TypeError, ValueError):
        return default


def action() -> str:
    """الأثرُ عند العلامة: «caveat» (تحفّظُ نطاقٍ يبقى الرقمُ بجانبه) الافتراضيّ،
    أو «drop» (إسقاطُ البند بسببٍ مُسجَّل). كلاهما مُعلَن، لا حذفٌ صامت."""
    a = os.environ.get("SILK_PLAUSIBILITY_ACTION", "caveat").strip().lower()
    return "drop" if a == "drop" else "caveat"


# مضاعِفاتُ المقياس اللفظيّة (عربيّ/إنجليزيّ) — «497 مليون» → 497e6. **حرجٌ
# (مراجعةٌ ذاتية):** الكلمةُ تُطابَق **حدَّ كلمةٍ تالياً للرقم مباشرةً** لا كأيّ
# سلسلةٍ في النصّ — وإلّا «الف» (جزءُ «الفول»/«الفواكه»/«الفلفل») يُضاعِف ×1000
# زوراً في مجال المنصّة نفسه، فيُفسِد الأرقامَ المشتقّة في تحفّظ العميل.
_SCALE_MULT = {
    "مليار": 1e9, "بليون": 1e9, "billion": 1e9, "bn": 1e9,
    "مليون": 1e6, "million": 1e6, "mn": 1e6, "م$": 1e6,
    "ألف": 1e3, "الف": 1e3, "thousand": 1e3, "k$": 1e3,
}
# رقمٌ متبوعٌ **اختيارياً** بكلمة مقياسٍ محدودةٍ بحدٍّ (لا حرفَ عربيٍّ/لاتينيٍّ
# بعدها) — فـ«3 الفئات» لا يُضاعَف (بعد «الف» حرفٌ عربيّ)، و«497 مليون دولار»
# يُضاعَف (بعد «مليون» فراغ).
_MAGNITUDE_RE = re.compile(
    r"([-+]?\d[\d,،٬]*(?:[.٫]\d+)?)"
    r"\s*(?:(مليار|بليون|billion|bn|مليون|million|mn|م\$|ألف|الف|thousand|k\$)"
    r"(?![A-Za-z؀-ۿ]))?",
    re.I)


def _num_usd(value: object, note: object = "") -> "float | None":
    """قيمةٌ رقميةٌ بالدولار من قيمةٍ عدديةٍ أو نصٍّ («497 مليون دولار»)، أو None.

    لا اختلاق: يعيد None إن لم يُرصَد رقمٌ حقيقيّ — المتّصلُ يتجاوز البند بدل
    افتراضِ صفرٍ أو تخمين. المقياسُ يُقرأ من الكلمة التالية للرقم مباشرةً فقط."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = _MAGNITUDE_RE.search(str(value or ""))
    if not m or not m.group(1):
        # القيمةُ نصٌّ بلا رقم — قد تحمل الملاحظةُ الرقمَ (نادر).
        m = _MAGNITUDE_RE.search(str(note or ""))
        if not m or not m.group(1):
            return None
    try:
        base = float(re.sub(r"[,،٬]", "", m.group(1)).replace("٫", "."))
    except ValueError:
        return None
    scale = (m.group(2) or "").lower()
    return base * _SCALE_MULT.get(scale, 1.0)


# ── كشفُ المرتكزات والمرشّحين من حقائق البعثات ───────────────────────────────
_IMPORT_KW = ("واردات", "استيراد", "import", "إجمالي واردات")
_POP_KW = ("سكان", "نسمة", "population")
_GDP_PC_KW = ("للفرد", "per capita", "gdp per capita", "دخل الفرد")
# مقاديرُ «حجم سوق» المكشوطة — الفئةُ الأوسع التي تتجاوز خطَّ الواردات الجمركيّ.
_MARKET_SIZE_KW = ("حجم السوق", "حجم سوق", "قيمة السوق", "السوق الكامل",
                   "السوق الكلي", "إجمالي السوق", "حجم الصناعة", "market size",
                   "market value", "market worth", "industry size", "tam")


def _iter_findings(dr: dict):
    """يمرّ على حقائق البعثات مهما كان شكلها — البعثةُ dict أو `AgentReport`،
    والحقيقةُ dict أو `DataPoint`. يُطبَّع كلٌّ لِـdict-وصولٍ موحّد كي يعمل
    الحارسُ على النتيجة الخام (كائنات) وعلى النموذج المُصيَّر (dicts) سواءً."""
    for key, m in (dr.get("missions") or {}).items():
        findings = (m.get("findings") if isinstance(m, dict)
                    else getattr(m, "findings", None))
        for f in (findings or []):
            if isinstance(f, dict):
                yield key, f
            else:
                yield key, {"value": getattr(f, "value", None),
                            "source": getattr(f, "source", ""),
                            "note": getattr(f, "note", ""),
                            "claim": getattr(f, "claim", "")}


def _kw_hit(text: str, kws) -> bool:
    t = (text or "").lower()
    return any(k in t for k in kws)


def _anchors(dr: dict) -> dict:
    """مرتكزاتُ التشغيلة المُتحقَّقة — إجمالي الواردات (كومتريد)، السكان، الناتج
    للفرد (البنك الدولي). أعلى قيمةٍ مرصودةٍ لكلٍّ (البند الأساسيّ)."""
    imports = population = gdp_pc = None
    for _key, f in _iter_findings(dr):
        blob = f"{f.get('note') or ''} {f.get('value') or ''}"
        val = _num_usd(f.get("value"), f.get("note"))
        if val is None or val <= 0:
            continue
        if _kw_hit(blob, _IMPORT_KW) and not _kw_hit(blob, _MARKET_SIZE_KW):
            imports = max(imports or 0.0, val)
        elif _kw_hit(blob, _GDP_PC_KW):
            gdp_pc = max(gdp_pc or 0.0, val)
        elif _kw_hit(blob, _POP_KW):
            population = max(population or 0.0, val)
    return {"imports_usd": imports, "population": population,
            "gdp_per_capita_usd": gdp_pc}


def check_magnitudes(result: dict) -> list:
    """علاماتُ المعقولية — قائمةُ dicts، أو [] إن لا تعارض/لا مرتكز/معطَّل.

    لكلِّ مقدارِ «حجم سوق» مرشّح: يُقارَن بإجمالي الواردات (مضاعِفٌ مفرطٌ لسوقٍ
    قليلةِ الإنتاج المحليّ) وبالسكان (نصيبٌ للفرد خارج نطاقٍ سليمٍ لصنفٍ واحد).
    """
    if not enabled():
        return []
    dr = (result or {}).get("deep_research") or {}
    if not dr:
        return []
    anchors = _anchors(dr)
    imports = anchors.get("imports_usd")
    population = anchors.get("population")
    max_mult = _f_env("SILK_PLAUSIBILITY_MAX_IMPORT_MULT", _DEF_MAX_IMPORT_MULT)
    max_pc = _f_env("SILK_PLAUSIBILITY_MAX_PER_CAPITA_USD", _DEF_MAX_PER_CAPITA)
    act = action()
    flags: list = []
    for key, f in _iter_findings(dr):
        blob = f"{f.get('note') or ''} {f.get('value') or ''} {f.get('claim') or ''}"
        if not _kw_hit(blob, _MARKET_SIZE_KW):
            continue
        val = _num_usd(f.get("value"), f.get("note"))
        if val is None or val <= 0:
            continue
        reasons: list = []
        detail: dict = {}
        # (١) مضاعِفُ الواردات — فشلٌ آمنٌ مفتوح: بلا مرتكزِ وارداتٍ لا حكم.
        if imports and imports > 0:
            ratio = val / imports
            if ratio > max_mult:
                reasons.append(
                    f"يفوق إجمالي واردات البند المرصود ({imports:,.0f}$) "
                    f"بمقدار {ratio:.0f}× (السقف {max_mult:.0f}×)")
                detail["import_ratio"] = round(ratio, 1)
                detail["imports_usd"] = imports
        # (٢) نصيبُ الفرد — صنفٌ واحدٌ فوق النطاق السليم.
        if population and population > 0:
            per_capita = val / population
            if per_capita > max_pc:
                reasons.append(
                    f"يعني ≈{per_capita:,.0f}$ للفرد سنوياً من صنفٍ واحد "
                    f"(النطاق السليم ≤{max_pc:,.0f}$)")
                detail["per_capita_usd"] = round(per_capita, 1)
                detail["population"] = population
        if not reasons:
            continue
        flags.append({
            "kind": "market_size_magnitude",
            "mission": key,
            "source": f.get("source"),
            "claimed_usd": val,
            "reason": "؛ ".join(reasons),
            "detail": detail,
            "action": act,
            "severity": "high",
        })
    return flags


def annotate(result: dict) -> list:
    """افحصْ ثمّ سجّلِ العلاماتِ في مانيفست التشغيلة (`deep_research
    ["plausibility_flags"]`) + حدثَ تتبّعٍ أفضلَ جهد. يعيد العلامات.

    عند `action="drop"`: يُعلَّم البندُ المُسبِّب `plausibility_dropped=True`
    فيُسقطه المُصدِّرون (لا حذفٌ صامت — سببُه في المانيفست)."""
    flags = check_magnitudes(result)
    if not flags:
        return flags
    dr = (result or {}).get("deep_research")
    if isinstance(dr, dict):
        dr["plausibility_flags"] = flags
        if action() == "drop":
            _mark_dropped(dr, flags)
    for fl in flags:
        log.warning("plausibility flag [%s] %s: %s",
                    fl.get("mission"), fl.get("claimed_usd"), fl.get("reason"))
        try:  # حدثُ تتبّعٍ أفضلَ جهد — no-op بهدوء خارج سياق التتبّع.
            import silk_trace
            silk_trace.record_event(event="plausibility_flag", **fl)
        except Exception:  # noqa: BLE001
            pass
    return flags


def _mark_dropped(dr: dict, flags: list) -> None:
    # يعمل على النموذج المُصيَّر (حقائقُ dict قابلةٌ للتعليم). حقائقُ الكائنات
    # (`DataPoint`) في النتيجة الخام لا تُعلَّم — العلامةُ مُسجَّلةٌ في المانيفست
    # والتتبّع أصلاً، والمُصدِّرون يقرؤون النموذج المُصيَّر.
    keyed = {fl.get("mission") for fl in flags}
    for key, m in (dr.get("missions") or {}).items():
        if key not in keyed or not isinstance(m, dict):
            continue
        for f in (m.get("findings") or []):
            if not isinstance(f, dict):
                continue
            blob = f"{f.get('note') or ''} {f.get('value') or ''} {f.get('claim') or ''}"
            if _kw_hit(blob, _MARKET_SIZE_KW) and _num_usd(
                    f.get("value"), f.get("note")):
                f["plausibility_dropped"] = True


def caveat_lines(flags: list) -> list:
    """أسطرُ تحفّظِ النطاق للعميل — جملةٌ تجاريةٌ لكلِّ علامة (لا لغةَ نظامٍ
    داخلية). فارغة إن لا علامات أو إن كان الأثرُ «drop» (البندُ مُسقَط أصلاً)."""
    if action() == "drop":
        return []
    out: list = []
    for fl in flags:
        out.append(
            "تنبيه تحقّقٍ: رقمُ «حجم السوق» المُدرَج أعلاه يتعذّر التوفيقُ بينه "
            "وبين بيانات التجارة الرسمية المرصودة في هذه الدراسة (" +
            str(fl.get("reason") or "") + ")؛ يُرجَّح أنه يقيس فئةً أوسع أو "
            "نطاقاً جغرافياً مختلفاً — يُقرأ مؤشراً سياقياً لا قياساً مباشراً "
            "لهذا البند حتى التحقّق المستقلّ.")
    return out
