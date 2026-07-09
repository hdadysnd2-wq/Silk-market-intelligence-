"""أداة تقييم جودة البحث العميق — Silk deep-research quality eval harness
(الموجة ٥، V5).

قاعدة القبول ذاتها المطبَّقة على المنصة بأكملها: **لا اختلاق**. المحور
الأول (استشهاد الأرقام) برمجي حتمي — يفحص هل كل رقم ورد في نص التقرير
المكتوب موجود فعلاً في نتائج البعثات الخام، بلا أي نداء كلود؛ فشله = صفر
فوري لهذا المحور (لا تقدير جزئي — رقم مختلَق واحد يكفي لإسقاطه). الأربعة
الباقية (اكتمال الأقسام، إعلان الفجوات، توصية بلا ادّعاءات غير مسندة،
جودة التقاطعات الخمسة) حَكَمٌ كلود (`_FAST_MODEL`) — تحتاج مفتاح.

**قرار تصميم موثَّق**: نتيجة `run_llm_agent` (`silk_llm_runtime.py`)
تحوّل كل بند مُستشهَد إلى AgentReport.findings حيث `.value` هو **نص
الادّعاء** الذي كتبه كلود (وليس الرقم الخام من الأداة) — سجل نقاط
البيانات الخام (dp1, dp2...) لجولة تشغيل واحدة لا يُخزَّن مستقلاً. لذا
"الأرقام المعروفة" هنا تُستخرَج من نص ادّعاءات/ملاحظات البعثات المخزَّنة
(`finding.value` + `finding.note`) — وهي عملياً نفس الأرقام التي استشهد
بها الوكيل من الأداة (التعليمات تُلزمه بذكرها كما وردت). تحسين لاحق طبيعي:
حفظ السجل الخام نفسه لكل بعثة لفحصٍ أدق — غير مطبَّق هنا (نطاق الموجة ٥).

الحالات الذهبية (`evals/golden_cases.json`) تبدأ **فارغة عمداً**: بناء
حالة ذهبية حقيقية يتطلب أرقاماً مُتحقَّقة يدوياً من مصدر رسمي حيّ
(مثال: Comtrade مباشرة) — هذه البيئة بلا مفتاح Anthropic وبلا وصول شبكي
لمصادر البيانات (Comtrade/WorldBank/GDELT/WITS)، فإضافة حالة الآن تعني
إما اختلاق أرقام أو ترك الحقول فارغة زوراً بمظهر التحقق. البنية والمخطط
(`golden_cases.schema.json`) جاهزان بالكامل ومُختبَران؛ أول حالة حقيقية
مؤجَّلة صراحةً لبيئة بمفتاح حيّ (راجع docs/DEEP_RESEARCH_DECISIONS.md).
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import re
import sys

log = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLDEN_PATH = os.path.join(_HERE, "evals", "golden_cases.json")
_SCORES_PATH = os.path.join(_HERE, "evals", "scores.json")

# أوزان المحاور الخمسة (تجمع ١٫٠) — المحور الأول وحده برمجي، البقية حَكَم كلود.
AXIS_WEIGHTS = {
    "citation_correctness": 0.35,
    "section_completeness": 0.15,
    "gaps_declared": 0.15,
    "recommendation_grounded": 0.20,
    "intersections_quality": 0.15,
}
_REGRESSION_DROP_THRESHOLD = 10  # نقطة — انخفاض أكبر منها = فشل معلن

_NUM_RE = re.compile(r"-?\d[\d,]*\.?\d*")


def _extract_numbers(text: str) -> list[float]:
    """أرقام مرشَّحة من نص — parses "950,000"/"5.2"/"12" into floats.

    يستثني علامات ترقيم العناوين (أسطر تبدأ بـ"## ") — رقم القسم ليس
    ادّعاءً يحتاج استشهاداً. Header-numbering lines are excluded first.
    """
    body = "\n".join(ln for ln in (text or "").splitlines()
                     if not ln.strip().startswith("## "))
    out: list[float] = []
    for m in _NUM_RE.finditer(body):
        raw = m.group().replace(",", "")
        try:
            out.append(float(raw))
        except ValueError:
            continue
    return out


def _report_fields(rep: object) -> dict:
    """AgentReport حيّة أو dict مُعاد تحميله — نفس نمط silk_render._report_fields."""
    if isinstance(rep, dict):
        return {"findings": rep.get("findings") or []}
    return {"findings": getattr(rep, "findings", None) or []}


def _finding_text(f: object) -> str:
    if isinstance(f, dict):
        return f"{f.get('value')} {f.get('note') or ''}"
    return f"{getattr(f, 'value', '')} {getattr(f, 'note', '') or ''}"


def _known_numbers(mission_reports: dict) -> set[float]:
    """الأرقام المعروفة عبر كل البعثات — من نص الادّعاء/الملاحظة (راجع تعليق
    التصميم أعلى الملف)."""
    known: set[float] = set()
    for rep in (mission_reports or {}).values():
        for f in _report_fields(rep)["findings"]:
            known.update(_extract_numbers(_finding_text(f)))
    return known


def citation_correctness_score(report_text: str,
                               mission_reports: dict) -> dict:
    """المحور البرمجي — كل رقم في التقرير يجب أن يرد حرفياً في بعثة ما.

    يعيد {"score": 0|100, "violations": [أرقام غير مسندة]} — لا نداء كلود،
    لا تقدير جزئي (رقم واحد مختلَق = صفر الفور، نفس مبدأ لا اختلاق).
    """
    known = _known_numbers(mission_reports)
    report_numbers = _extract_numbers(report_text)
    violations = sorted({n for n in report_numbers if n not in known})
    return {"score": 0 if violations else 100, "violations": violations,
           "checked": len(report_numbers), "known_pool": len(known)}


def _judge_prompt(result: dict) -> str:
    from silk_ai_judge import _isolate
    dr = result.get("deep_research") or {}
    report_text = (dr.get("report") or {}).get("report") or ""
    missions = dr.get("missions") or {}
    mission_summaries = "\n".join(
        f"- [{k}] فشل={_report_fields(v).get('failed', False)}"
        for k, v in missions.items())
    return (
        "قيّم تقرير بحث عميق على أربعة محاور (٠-١٠٠ لكل محور)، بعيداً عن "
        "استشهاد الأرقام (يُفحص برمجياً بمعزل عنك):\n"
        "1. section_completeness: هل الأقسام الخمسة عشر المطلوبة حاضرة "
        "بمحتوى فعلي لا عناوين فارغة؟\n"
        "2. gaps_declared: هل الفجوات (بيانات غائبة/بعثات فاشلة) مُعلَنة "
        "صراحة بدل تجاهلها؟\n"
        "3. recommendation_grounded: هل التوصية النهائية خالية من ادّعاءات "
        "غير مسندة لحقائق البعثات؟\n"
        "4. intersections_quality: هل التقاطعات الخمسة (الطلب/تكلفة الدخول/"
        "التنافسية السعرية/أبواب الدخول/SWOT) مبنية منطقياً من الأدلة؟\n\n"
        f"ملخص البعثات:\n{_isolate(mission_summaries)}\n\n"
        f"نص التقرير:\n{_isolate(report_text[:8000])}\n\n"
        'أعد JSON فقط: {"section_completeness":N,"gaps_declared":N,'
        '"recommendation_grounded":N,"intersections_quality":N,'
        '"reasoning":"سبب موجز"}')


def evaluate_report(result: dict) -> dict | None:
    """قيّم تقريراً كاملاً — المحور البرمجي أولاً (لا كلود)، ثم أربعة محاور
    حَكَم كلود إن توفّر مفتاح. None فقط إن تعذّر النداء ولم يوجد نص تقرير
    أصلاً؛ استشهاد الأرقام يُحسب دوماً بلا حاجة لمفتاح."""
    dr = result.get("deep_research") or {}
    report_text = (dr.get("report") or {}).get("report") or ""
    mission_reports = dr.get("missions") or {}
    citation = citation_correctness_score(report_text, mission_reports)

    axes = {"citation_correctness": citation["score"]}
    from silk_ai_judge import _call, _FAST_MODEL, _PRINCIPLE, available
    llm_axes: dict | None = None
    if report_text and available():
        raw = _call(_PRINCIPLE, _judge_prompt(result), max_tokens=700,
                    model=_FAST_MODEL, timeout=30)
        if raw:
            try:
                start, end = raw.find("{"), raw.rfind("}")
                llm_axes = json.loads(raw[start:end + 1]) if start >= 0 else None
            except Exception:  # noqa: BLE001 — رد غير-JSON = محاور كلود غائبة
                llm_axes = None
    for axis in ("section_completeness", "gaps_declared",
                "recommendation_grounded", "intersections_quality"):
        val = (llm_axes or {}).get(axis)
        try:
            axes[axis] = max(0.0, min(100.0, float(val)))
        except (TypeError, ValueError):
            axes[axis] = None  # محور غير محسوب (لا مفتاح/فشل) — فجوة معلنة

    scored = {k: v for k, v in axes.items() if v is not None}
    total_weight = sum(AXIS_WEIGHTS[k] for k in scored)
    overall = (round(sum(axes[k] * AXIS_WEIGHTS[k] for k in scored)
                     / total_weight, 1) if total_weight else None)
    return {
        "overall": overall, "axes": axes,
        "citation_violations": citation["violations"],
        "reasoning": (llm_axes or {}).get("reasoning", ""),
        "grounded_axes": sorted(scored),
        "note": ("محاور كلود غير محسوبة — بلا مفتاح ANTHROPIC_API_KEY"
                 if llm_axes is None else ""),
    }


# ── الحالات الذهبية · golden cases ───────────────────────────────────────────

_REQUIRED_CASE_FIELDS = ("key", "product", "market", "hs_code", "expected",
                         "verified_at", "verified_by")


def validate_case(case: dict) -> list[str]:
    """تحقّق خفيف من مخطط الحالة — لا مكتبة jsonschema (stdlib-first)؛
    يعيد قائمة الأخطاء (فارغة = صالحة)."""
    errors = []
    for field in _REQUIRED_CASE_FIELDS:
        if field not in case:
            errors.append(f"missing field: {field}")
    hs = case.get("hs_code", "")
    if hs and not re.fullmatch(r"\d{6}", str(hs)):
        errors.append(f"hs_code must be 6 digits: {hs!r}")
    expected = case.get("expected")
    if isinstance(expected, dict):
        for k, v in expected.items():
            if not isinstance(v, dict) or "value" not in v or "source_url" not in v:
                errors.append(f"expected.{k} missing value/source_url")
    elif "expected" in case:
        errors.append("expected must be an object")
    return errors


def load_golden_cases(path: str = _GOLDEN_PATH) -> list[dict]:
    """حمّل الحالات الذهبية — صفوف صالحة فقط؛ صفّ فاسد يُسجَّل ويُستبعد لا يُسقط التحميل."""
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:  # noqa: BLE001 — ملف غائب/فاسد = قائمة فارغة، لا اختلاق
        log.warning("golden cases unavailable (%s): %s", path, e)
        return []
    if not isinstance(raw, list):
        return []
    out = []
    for case in raw:
        errs = validate_case(case) if isinstance(case, dict) else ["not an object"]
        if errs:
            log.warning("golden case rejected (%s): %s", case.get("key", "?"), errs)
            continue
        out.append(case)
    return out


def load_scores(path: str = _SCORES_PATH) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — لا سجل سابق = قاموس فارغ
        return {}


def save_scores(scores: dict, path: str = _SCORES_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scores, f, ensure_ascii=False, indent=2, sort_keys=True)


def compare_to_last_score(case_key: str, new_score: float | None,
                          scores: dict | None = None,
                          path: str = _SCORES_PATH) -> dict:
    """قارن بالنتيجة المحفوظة — انخفاض > 10 نقطة = فشل معلن (لا يُسقط شيئاً،
    يُعلَن). أول تشغيلة لحالة (لا سجل سابق) = نجاح دوماً (لا أساس للمقارنة)."""
    scores = scores if scores is not None else load_scores(path)
    prev = scores.get(case_key)
    if prev is None or new_score is None:
        return {"regression": False, "previous": prev, "new": new_score,
               "note": "لا نتيجة سابقة للمقارنة" if prev is None
                       else "لا نتيجة جديدة محسوبة"}
    drop = prev - new_score
    return {"regression": drop > _REGRESSION_DROP_THRESHOLD,
           "previous": prev, "new": new_score, "drop": round(drop, 1)}


def run_case(case: dict) -> dict:
    """أعد تشغيل حالة ذهبية حياً — ١٢ بعثة + محلل + توليف + كاتب، يتطلب
    شبكة ومفتاح Anthropic فعليين (لا يعمل في هذه البيئة/CI). غير مُختبَر
    هيرمتياً بتصميم — الاختبارات تموّه هذه الدالة عند فحص منطق الـCLI."""
    from silk_market_resolver import resolve_market
    from silk_missions import run_all_missions
    from silk_market_analyst import analyze_market, to_synthesis_input
    from silk_synthesis import synthesize
    from silk_ai_judge import write_reviewed_report

    ref, suggestions = resolve_market(case["market"])
    if ref is None:
        raise ValueError(f"cannot resolve market {case['market']!r}: "
                         f"suggestions={suggestions}")
    mission_reports = run_all_missions(ref, product=case["product"],
                                       hs_code=case["hs_code"])
    analyst_out = analyze_market(ref, case["product"], mission_reports,
                                 hs_code=case["hs_code"])
    analyst_input = to_synthesis_input(analyst_out)
    verdict = synthesize(list(mission_reports.values()), product=case["product"],
                         market=ref.name_en, with_ai=True,
                         analyst_assessment=analyst_input)
    report_out = write_reviewed_report(mission_reports, analyst_input["summary"],
                                       verdict, case["product"], ref.name_en)
    return {"product": case["product"], "hs_code": case["hs_code"],
           "market": {"iso3": ref.iso3, "m49": ref.m49, "name_en": ref.name_en,
                     "name_ar": ref.name_ar},
           "markets": [],
           "deep_research": {"missions": mission_reports, "analyst": analyst_out,
                            "verdict": verdict, "report": report_out}}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser(
        description="أعد تشغيل حالة ذهبية وقارن النتيجة بالسجل السابق — "
                    "يتطلب شبكة ومفتاح Anthropic؛ لا يعمل في CI.")
    ap.add_argument("--case", required=True, help="مفتاح الحالة (key)")
    args = ap.parse_args(argv)

    cases = {c["key"]: c for c in load_golden_cases()}
    case = cases.get(args.case)
    if case is None:
        log.error("unknown golden case %r (available: %s)", args.case,
                  sorted(cases) or "none — evals/golden_cases.json فارغ حالياً")
        return 1

    result = run_case(case)
    evaluation = evaluate_report(result)
    overall = (evaluation or {}).get("overall")
    scores = load_scores()
    cmp = compare_to_last_score(args.case, overall, scores)
    print(json.dumps({"case": args.case, "evaluation": evaluation,
                      "comparison": cmp}, ensure_ascii=False, indent=2))
    if overall is not None:
        scores[args.case] = overall
        save_scores(scores)
    if cmp["regression"]:
        log.error("quality regression on %s: %s -> %s (drop %.1f)",
                 args.case, cmp["previous"], cmp["new"], cmp["drop"])
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
