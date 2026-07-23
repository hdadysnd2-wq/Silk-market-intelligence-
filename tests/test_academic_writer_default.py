"""قفل: مسار /research الرئيسي يكتب أكاديمياً افتراضياً — generation default.

طلب المالك (2026-07-23): «تأكّد أن الكاتب يكتب التقرير أكاديمياً». الاكتشاف:
البنية الأكاديمية كانت متاحةً فقط عبر تصدير/إعادة توليد بـ`?style=academic`؛
أمّا **التوليد الرئيسي** (`_run_research_pipeline` → `write_reviewed_report`)
فكان يستدعي الكاتب **بلا `style`**، فيستعمل العقد التجاري دوماً. النتيجة:
حتى التصدير الأكاديمي كان يعيد تشكيل نثرٍ كُتب بسجلٍّ تجاري.

الإصلاح (api.py): التوليد الرئيسي يمرّر النمط للكاتب، والافتراضي «academic»
عبر `SILK_REPORT_STYLE`. قيمة صريحة في الطلب (`report_style`) تتقدّم. هذه
الأقفال تثبت التوصيل نصّياً (لا نداء شبكة/كلود).
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_API = os.path.join(_ROOT, "api.py")


def _api_src() -> str:
    return open(_API, encoding="utf-8").read()


def test_research_request_has_report_style_field():
    """نموذج طلب البحث يحمل حقل نمط اختيارياً (تجاوز صريح للبيئة)."""
    src = _api_src()
    assert "report_style: str | None = None" in src


def test_default_report_style_helper_defaults_to_academic():
    """الافتراضي المضبوط «academic» (طلب المالك) عبر SILK_REPORT_STYLE."""
    src = _api_src()
    assert "def _default_report_style()" in src
    assert 'os.environ.get("SILK_REPORT_STYLE", "academic")' in src


def test_generation_passes_style_to_the_writer():
    """التوليد الرئيسي يمرّر النمط الفعّال للكاتب (لا استدعاء بلا style)."""
    src = _api_src()
    pipeline = src.split("def _run_research_pipeline(")[1].split(
        "\n    def ")[0]
    assert "eff_report_style = (report_style or _default_report_style())" in pipeline
    assert "style=eff_report_style," in pipeline
    # يُخزَّن النمط المستعمَل فعلاً كي تتّسق طبقة العرض/التصدير.
    assert '"report_style": eff_report_style,' in pipeline


def test_both_call_sites_thread_the_request_style():
    """المساران المتزامن والخلفي يمرّران req.report_style (لا فقدان صامت)."""
    src = _api_src()
    # المتزامن + وسائط الخيط الخلفي كلاهما يمرّر req.report_style.
    assert src.count("resume_reports, req.report_style") == 2
    # جسم الخيط الخلفي يمرّر المعامل الذي استلمه للأنبوب.
    assert src.count("resume_reports, report_style)") == 1
    assert "resume_reports, req.report_style)," in src             # وسائط الخيط الخلفي


def test_pipeline_and_background_accept_report_style_param():
    """توقيعا الدالتين يستقبلان النمط (تفادي TypeError عند التمرير)."""
    src = _api_src()
    assert "resume_reports: dict | None,\n                               report_style: str | None = None) -> dict:" in src
    assert "resume_reports, report_style=None) -> None:" in src
