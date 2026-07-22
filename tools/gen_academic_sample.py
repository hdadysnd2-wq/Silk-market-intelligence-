#!/usr/bin/env python3
"""عيّنة القالب الأكاديمي الملتزَمة (§10.6) — samples/academic_report_latest.docx.

يبني من مدوّنة الكويت القانونية نفسها (`tools/canonical_kuwait_peanut_butter`)
مضافاً إليها بعثات الشواهد الثلاث التي طلب المالك إظهارها دائماً
(الديموغرافيا/حجم السكان، ثقافة المستهلك، الاشتراطات الجمركية) ببيانات
موسومة برهانية — عبر مسار العرض الإنتاجي الفعلي (`build_view` ثم
`render_academic_docx`)، لا مستند مدوَّر يدوياً. لافتة «نموذج توضيحي
ببيانات موسومة» تُطبع على الغلاف (test_run).
"""
from __future__ import annotations

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

os.environ["SILK_HERMETIC"] = "1"

from tools.canonical_kuwait_peanut_butter import kuwait_research_blob  # noqa: E402
from silk_render import build_view  # noqa: E402
from silk_reports import render_academic_docx  # noqa: E402


def _f(value, source, conf, note):
    return {"value": value, "source": source, "confidence": conf,
            "note": note, "retrieved_at": "2026-07-20", "status": ""}


def academic_sample_blob() -> dict:
    """مدوّنة الكويت + بعثات الشواهد الثلاث ببيانات موسومة برهانية."""
    blob = kuwait_research_blob()
    blob["deep_research"]["missions"].update({
        "demographics_economy": {
            "agent_name": "LLMAgent:demographics_economy", "failed": False,
            "summary": "سياق ديموغرافي واقتصادي مرصود",
            "findings": [
                _f("عدد السكان نحو 4.3 مليون نسمة (2023).",
                   "World Bank", 0.9, "بيانات سكانية رسمية"),
                _f("نصيب الفرد من الناتج المحلي مرتفع خليجياً.",
                   "World Bank", 0.85, "مؤشر دخل"),
            ]},
        "consumer_culture": {
            "agent_name": "LLMAgent:consumer_culture", "failed": False,
            "summary": "أنماط استهلاك مرصودة",
            "findings": [
                _f("نمط استهلاك أسري لمنتجات الدهن القابل للدهن مع إقبال "
                   "على العلامات المستوردة.", "رصد ميداني عام", 0.6,
                   "شاهد ثقافة مستهلك"),
            ]},
        "customs_requirements": {
            "agent_name": "LLMAgent:customs_requirements", "failed": False,
            "summary": "اشتراطات دخول مرصودة",
            "findings": [
                _f("شهادة مطابقة خليجية (GSO) وبطاقة بيانات عربية إلزامية "
                   "للأغذية المعبأة.", "GSO", 0.85, "اشتراط دخول"),
                _f("شهادة حلال لمكوّنات المنشأ الحيواني حيث انطبق.",
                   "بلدية الكويت — اشتراطات الأغذية", 0.7, "اشتراط دخول"),
            ]},
    })
    return blob


def main() -> int:
    view = build_view(academic_sample_blob())
    view["test_run"] = True
    out = os.path.join(_ROOT, "samples", "academic_report_latest.docx")
    render_academic_docx(view, out)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
