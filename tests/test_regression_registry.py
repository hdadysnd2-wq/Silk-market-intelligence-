"""سجلّ الانحدار الموحّد — one guard per real incident, one meta-test for coverage.

> **الغرض (أمر المُشرِف).** لكل حادثة إنتاجية حقيقية في هذا المستودع — صفوف
> `docs/LESSONS.md` **وفخاخ** `silk-operations` §2 (THE TRAPS) — حارسٌ واحد
> يُفشِل على عودة نفس العائلة، و**اختبار تغطية شامل** (meta) يثبت أنّ كل حادثة
> مُسجَّلة هنا فعلاً — فلا تسقط حادثة من الشبكة بصمت. يشمل ذلك **الحوادث الثلاث
> لعطل 501 في تصدير docx** (صفوف LESSONS ٣/١١/١٣) بحُرّاس سلوكيين فعليين.
>
> **Why a registry (not just per-file lock-tests).** Lock-tests live scattered
> across `tests/`; this file is the single index that maps EVERY known incident
> to a live guard and then proves — mechanically — that the index is complete
> against both incident ledgers. A new incident that lands in either ledger
> without a registry entry fails `test_meta_registry_covers_every_known_incident`.

هرمتي بالكامل (قراءة مصدر + سلوك محلي، بلا شبكة). الحُرّاس السلوكية (٣/١١/١٣)
تبني/تنقّي فعلياً من المدوّنة القانونية الحقيقية الشكل — لا نماذج مثالية.

Run: python3 -m pytest tests/test_regression_registry.py -q
"""
from __future__ import annotations

import os
import re
import sys
import tempfile

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))


def _read(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _exists(rel: str) -> bool:
    return os.path.exists(os.path.join(_ROOT, rel))


def _needles(rel: str, *needles: str):
    """حارس وجود: كل إبرة حاضرة في الملف — يعيد callable للتسجيل."""
    def check():
        assert _exists(rel), f"ملف الإنفاذ مفقود: {rel}"
        src = _read(rel)
        missing = [n for n in needles if n not in src]
        assert not missing, f"{rel}: رموز/علامات إنفاذ مفقودة {missing}"
    return check


def _absent(rel: str, *forbidden: str):
    def check():
        src = _read(rel)
        present = [n for n in forbidden if n in src]
        assert not present, f"{rel}: رموز يجب أن تكون قد أُزيلت لا تزال {present}"
    return check


# ── حُرّاس سلوكية للحوادث الثلاث لعطل docx-501 (LESSONS ٣/١١/١٣) ──────────────

def _guard_docx501_row3():
    """LESSONS ٣ — 501 شُحن لأن الاختبارات نماذج مموّهة. الحارس: تصدير docx
    العميل يُنتِج ملفاً حقيقياً قابلاً للفتح من **المدوّنة القانونية الحقيقية
    الشكل** (لا نموذج)، بلا 501."""
    import silk_render
    from silk_reports import render_client_docx
    from canonical_netherlands import netherlands_research_blob
    view = silk_render.build_view(netherlands_research_blob())
    path = render_client_docx(view, os.path.join(tempfile.mkdtemp(), "c.docx"))
    assert os.path.exists(path)
    from docx import Document
    doc = Document(path)
    assert any(p.text.strip() for p in doc.paragraphs), "docx فارغ"


def _guard_docx501_row11():
    """LESSONS ١١ — 501 تكرّر لأن محفّزات الحارس العربية بلا استبدال مقابل.
    الحارس: مصطلح حكم عربي ممنوع («درجة الثقة») يُحيَّد فعلياً بمُطهِّر/منقِّي
    العميل فلا يبقى في مخرَج التصدير."""
    from silk_reports import _client_redact_text, _client_forbidden_hits
    leaked = "التقييم يعتمد درجة الثقة العالية على مصدر البيانات"
    cleaned = _client_redact_text(leaked)
    assert not _client_forbidden_hits(cleaned), (
        f"محفّز حارس عربي بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")


def _guard_docx501_row13():
    """LESSONS ١٣ — docx يفشل حياً (501) بينما الهرمتي أخضر؛ الحارس كان يرفض
    على تسرّب واحد. القاعدة «نقِّ لا ترفض»: مصطلح إنجليزي عارٍ متسرّب يُستبدَل
    بمحايد ويُسلَّم المستند — لا 501. الحارس: `_client_redact_text` ينقّي
    مصطلحاً إنجليزياً تشغيلياً بدل رفعه."""
    from silk_reports import _client_redact_text, _client_forbidden_hits
    leaked = "mission status: successful run"
    assert _client_forbidden_hits(leaked), "التهيئة خاطئة — النص يجب أن يتسرّب أولاً"
    cleaned = _client_redact_text(leaked)
    assert not _client_forbidden_hits(cleaned), (
        f"مصطلح إنجليزي تشغيلي بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")


# ── حُرّاس سلوكية لفخّي المسار (markets:[] + view بعد التخزين) ────────────────

def _guard_trap_markets_empty():
    """TRAP «markets:[] misroutes exporters» — نتيجة /research دوماً markets:[]؛
    أي مسار عرض يثق بـ`markets[0]` يحصل على {} فيُنتِج صفحة /analyze فارغة.
    الحارس: build_view للمدوّنة القانونية يُنتِج فرع deep_research (لا قالب
    فارغ) رغم markets:[]."""
    import silk_render
    from canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    assert blob["markets"] == [], "المدوّنة القانونية يجب أن تحمل markets:[]"
    view = silk_render.build_view(blob)
    assert view.get("deep_research"), "build_view لم يُنتِج فرع deep_research"


def _guard_trap_view_after_persist():
    """TRAP «view attached AFTER persist on one path» — البلوب المخزَّن قد لا
    يحمل view مشتقّاً؛ مسار القراءة يجب أن يعيد بناءه. الحارس: `GET /analyses/{id}`
    يبني view عند غيابه (`found["view"] = _view(found)`)."""
    src = _read("api.py")
    assert 'found["view"] = _view(found)' in src or 'found["view"]=_view(found)' in src, (
        "مسار /analyses/{id} لا يعيد بناء view الغائب")
    assert 'found.setdefault("analysis_id"' in src, (
        "مسار /analyses/{id} لا يضمن analysis_id للبلوبات الأقدم")


# ── حُرّاس تراب باقية (وجود رمز الإصلاح، file:line-anchored) ──────────────────

def _guard_trap_two_sanitizers():
    _needles("silk_reports.py", "_client_assert_clean", "_client_sanitize")()
    _needles("silk_render.py", "_strip_internal_plumbing")()


def _guard_trap_redaction_mangling():
    # الإصلاح الالتفافي: مرحلة التصعيد سُمّيت `..._escalate{attempt}` لتفادي
    # الجزء القصير الذي كان يُشوَّه؛ والمنقِّح `_redact` باقٍ. (بنيوياً مفتوح
    # — لا حارس طول أدنى بعد؛ مُتتبَّع في silk-operations §2.)
    _needles("silk_ai_judge.py", "_escalate{attempt}")()
    _absent("silk_ai_judge.py", "maxtok_retry")()
    _needles("silk_diagnostics.py", "def _redact")()


def _guard_trap_strip_plumbing_three_leaks():
    """TRAP «_strip_internal_plumbing leaked three raw forms» — الحارس يبني
    السلاسل الإنتاجية الحرفية الثلاث ويؤكّد تحييد كلٍّ منها (silk-operations §4:
    القفل بالسلسلة الحرفية). الثلاث: ريبر DataPoint(...) يُحيَّد كاملاً بلا
    نصف-ترجمة؛ JSON مضمَّن بمفاتيح score/summary يُحيَّد؛ رمز حكم بأي حالة أحرف."""
    from silk_render import _strip_internal_plumbing
    # (١) ريبر DataPoint(...) — كامل التحييد، لا نصف-ترجمة، تُستخرَج القيمة
    dp = ("مبنيّ على DataPoint(value='واردات 120 مليون دولار', source='UN "
          "Comtrade', confidence=0.9, note='n', retrieved_at='2026-07-01', "
          "status='')")
    o1 = _strip_internal_plumbing(dp)
    assert "DataPoint(" not in o1 and "confidence=" not in o1, o1
    assert "درجة الثقة=" not in o1, f"نصف-ترجمة: {o1}"
    assert "واردات 120 مليون دولار" in o1, o1
    # (٢) JSON مضمَّن بمفاتيح score/summary
    o2 = _strip_internal_plumbing('التوصية: {"score": 0.72, "summary": "سوق واعد"}')
    assert "{" not in o2 and '"summary"' not in o2, o2
    assert "سوق واعد" in o2, o2
    # (٣) رمز حكم بأي حالة أحرف
    o3 = _strip_internal_plumbing("الحكم go — مراقبة قبل الدخول")
    assert not re.search(r"\bgo\b", o3, re.I), f"رمز حكم خام بقي: {o3}"


def _guard_trap_parallel_cache_window():
    # فخّ معروف غير مُصلَح بعد (نافذة الذاكرة المؤقتة عبر ١٢ بعثة متوازية).
    # الحارس يُبقيه مُتتبَّعاً: آلية التوازي (ThreadPoolExecutor) لا تزال في
    # مُشغّل البعثات، والفخّ موسوم صراحةً «Known, not yet fixed» في المهارة.
    _needles("silk_missions.py", "ThreadPoolExecutor")()
    _needles(".claude/skills/silk-operations/SKILL.md", "not yet fixed")()


# كل مدخلة: Incident(key, source, match, check)
#   source: "LESSONS" (key=رقم الصفّ int) أو "trap" (key=slug، match=جزء من
#   اسم الفخّ العريض في §2). check: callable يُفشِل على عودة الانحدار.


def _guard_datapoint_repr_flexible():
    """LESSONS ١٧ — ريبر DataPoint المختصر/الشاذ كان يمرّ نصف مترجم (هجوم
    المشرف الحي). الحارس: النمط المرن + شبكة الأمان يمسكان كل العائلة."""
    import silk_render as _r
    cases = [
        "DataPoint(value=None, confidence=0.0)",
        "DataPoint(value='12.5', source='comtrade', confidence=0.9, "
        "note='ok (x)', retrieved_at='2026', status='ok')",
        "DataPoint(confidence=0.5, value=None)",
        "قبل DataPoint(value=None, confidence=0.0) بعد",
    ]
    for c in cases:
        out = _r._strip_internal_plumbing(c)
        assert "DataPoint" not in out and "confidence" not in out and \
               "درجة الثقة=" not in out, f"leak: {c!r} -> {out!r}"
    assert _r._strip_internal_plumbing(cases[1]).strip().startswith("12.5")


def _guard_vendor_name_leak():
    """LESSONS ١٨ — اسم مزوّد داخلي (Volza/Explee/…) تسرّب لسطح العميل (بلاغ
    UK الحي). الحارس السلوكي: الأسطر الحرفية المسرّبة (سطر «الخطوة التالية»
    القديم + ترجمة `silk_narrative` التي تُسمّي المزوّد) تُحيَّد فعلياً بمنقِّي
    العميل فلا يبقى اسم مزوّد في مخرَج التصدير؛ وسطر next_step المُولَّد لم
    يعُد يحمل اسم مزوّد أصلاً."""
    from silk_reports import (_client_redact_text, _client_forbidden_hits,
                              _client_sanitize)
    # (١) الأسطر الحرفية المسرّبة من البلاغ الحي — كلٌّ يتسرّب أولاً ثم يُحيَّد.
    leaked = [
        "فعّل خدمة التعميق المدفوعة للتحقق من المستوردين وجهات الاتصال (Volza/Explee)",
        "إكسبلي غير متاح حالياً",
        "فولزا: لا مستوردون بالاسم مرصودون لرمز 0804 في GBR",
        "buyers via Serper and SerpApi, priced by LocalPrice",
        "seasonality from pytrends; risk news from GDELT",
    ]
    for line in leaked:
        assert _client_forbidden_hits(line), (
            f"التهيئة خاطئة — يجب أن يتسرّب أولاً: {line!r}")
        cleaned = _client_redact_text(_client_sanitize(line))
        assert not _client_forbidden_hits(cleaned), (
            f"اسم مزوّد بقي بعد التنقية: {_client_forbidden_hits(cleaned)}")
    # (٢) الحارس الصارم يملك أسماء المزوّدين لاتينيةً وعربيةً معاً — لا يعتمد
    # على المُطهِّر وحده (متغيّر مستقبلي يفلت المُطهِّر يبقى يُرفَع بصوت عالٍ).
    for v in ("Volza", "Explee", "إكسبلي", "فولزا", "LocalPrice", "Serper",
              "SerpApi", "pytrends", "GDELT"):
        hits = _client_forbidden_hits(f"مبنيّ على {v} التجارية")
        assert any(h.startswith("vendor_name") for h in hits), (
            f"اسم مزوّد ليس في قائمة الرفض الصارم (_client_assert_clean): {v}")
    # (٣) سطر next_step المُولَّد لا يحمل اسم مزوّد إطلاقاً.
    import silk_render
    from canonical_netherlands import netherlands_research_blob
    blob = netherlands_research_blob()
    blob["deep_research"]["verdict"] = {"verdict": "GO", "confidence": 0.7,
                                        "ai": {"verdict": "GO"}}
    view = silk_render.build_view(blob)
    nxt = (view.get("deep_research") or {}).get("next_step") or ""
    assert nxt and not _client_forbidden_hits(nxt), (
        f"سطر الخطوة التالية يحمل اسم مزوّد: {nxt!r}")


def _guard_export_format_contract():
    """LESSONS ١٩ — عائلة export-format-contract (بلاغ المُشرِف عند السطر): زرّ
    «تصدير التقرير» الأساسي كان موصولاً بـ`dlReport("docx")` فينزّل Word بينما
    المُسلَّم النهائي للعميل PDF غير قابل للتحرير (§3، اتفاق المالك). الحارس:
    (١) زرّ PDF موصول بـ`dlReport("pdf")` لا docx؛ (٢) `dlReport` يملك فرع pdf
    بامتداد `.pdf` ورسالة 503 عربية صريحة؛ (٣) بطاقة الدردشة المصغّرة تُصدِّر
    PDF؛ (٤) الخادم يخدم report.pdf بنوع application/pdf؛ (٥) صورة النشر
    (Dockerfile) + وظيفة e2e تُثبّتان محرّك التحويل فلا يموت الزرّ حياً."""
    html = _read("web/index.html")
    # (١) الوصلة الأساسية: PDF لا docx (السطر المعطوب الأصلي غائب).
    assert '$("#pdfBtn").addEventListener("click",function(){dlReport("pdf")})' \
        in html, "زرّ PDF غير موصول بـdlReport(\"pdf\")"
    assert '$("#pdfBtn").addEventListener("click",function(){dlReport("docx")})' \
        not in html, "زرّ PDF لا يزال موصولاً بتنزيل docx (البلاغ الأصلي)"
    # زرّ Word ثانوي حاضر (النسخة القابلة للتحرير للمشغّل، لا العميل).
    assert 'id="wordBtn"' in html and \
        '$("#wordBtn").addEventListener("click",function(){dlReport("docx")})' \
        in html, "زرّ Word الثانوي غائب أو غير موصول"
    # (٢) فرع pdf في dlReport: امتداد .pdf + رسالة 503 العربية الصريحة.
    assert 'kind==="pdf"' in html, "dlReport بلا فرع pdf"
    assert '"سِلك_تقرير_"+id+".pdf"' in html, "اسم/امتداد ملف الـPDF خاطئ"
    assert "محرّك التحويل غير متاح — جرّب Word مؤقتاً" in html, \
        "رسالة 503 العربية الصريحة غائبة"
    assert "r.status===503" in html, "فرع pdf لا يعالج 503 صراحةً"
    # (٣) بطاقة الدردشة المصغّرة تُصدِّر PDF لا docx.
    assert 'data-act="pdf"' in html, "بطاقة الدردشة المصغّرة لا تُصدِّر PDF"
    assert 'this.dataset.act==="board"?nav("board"):dlReport("pdf")' in html, \
        "معالج بطاقة الدردشة لا يستدعي dlReport(\"pdf\")"
    # (٤) الخادم يخدم report.pdf بنوع application/pdf.
    api = _read("api.py")
    assert "/analyses/{analysis_id}/report.pdf" in api and \
        'media_type="application/pdf"' in api, "نقطة نهاية report.pdf غائبة/خاطئة"
    # (٥) محرّك التحويل مثبَّت على النشر (Dockerfile) وفي وظيفة e2e — كي يعمل
    # الزرّ حيّاً لا في CI فقط (البند ٦ من أمر العمل).
    dockerfile = _read("Dockerfile")
    assert "libreoffice-writer" in dockerfile, \
        "محرّك تحويل PDF غير مثبَّت في صورة النشر — الزرّ سيموت حياً بـ503"
    e2e = _read(".github/workflows/e2e-live-shape.yml")
    assert "libreoffice-writer" in e2e, \
        "وظيفة e2e لا تثبّت محرّك التحويل — تأكيد %PDF سيفشل"
    # التدفّق يؤكّد توقيع %PDF على المسار الأساسي.
    flow = _read("tests/e2e/live_shape_flow.cjs")
    assert 'pdfBuf[0] === 0x25 && pdfBuf[1] === 0x50' in flow, \
        "تدفّق e2e لا يؤكّد توقيع %PDF لزرّ PDF"


def _guard_world_tier2_no_fabrication():
    """LESSONS ٢٠ — عائلة tier2-fabrication (تصميم الميزة أ، قفل استباقي): توسيع
    الترتيب لكل دول العالم يجب ألّا يختلق قيمة فئة-٢ ولا يفجّر ميزانية كومتريد.
    الحارس (قراءة مصدر + سلوك حيّ): (١) وحدة الترتيب لا تقرأ أيّ CSV محلّي؛
    (٢) الفئة-٢ تحمل الوسم التعاقدي + فجوتَي موقع السعودية/المنافسة معلنتين؛
    (٣) نداء العالم الواحد + التدهور عند نفاد الميزانية موجودان؛ (٤) ملف القفل
    قائم."""
    src = _read("silk_market_ranker.py")
    # (١) لا CSV محلّي في وحدة الترتيب إطلاقاً.
    for forbidden in ("agreements_l1", "demographics_l1", "market_locale",
                      "muslim_share", "requirements_l1"):
        assert forbidden not in src, f"الترتيب يقرأ CSV محلّياً: {forbidden}"
    # (٢) الوسم التعاقدي + الفجوة المعلنة + المسجّل + الصمّام.
    for needle in ('TIER2_LABEL = "تغطية أساسية — بيانات محلية محدودة"',
                   'def _tier2_gather_row', 'status="tier2_gap"',
                   'def _world_markets_enabled', 'def world_import_totals',
                   'def _comtrade_budget_left'):
        assert needle in src, f"علامة إنفاذ الفئة-٢ مفقودة: {needle}"
    # (٣) نداء العالم الواحد (partner=0) مشترك للفئتين + تدهور الميزانية.
    assert 'flow="M", partner=0' in src, "نداء العالم الواحد (partner=0) غائب"
    assert '_comtrade_budget_left()' in src and '_WORLD_BUDGET_RESERVE' in src, \
        "فرع التدهور عند نفاد الميزانية غائب"
    # (٤) ملف القفل قائم بأقفاله السبعة.
    assert _exists("tests/test_world_coverage_tierA.py"), "ملف قفل الميزة أ مفقود"
    lock = _read("tests/test_world_coverage_tierA.py")
    for fn in ("test_tier_separation_and_labels",
               "test_tier2_never_carries_a_local_csv_value",
               "test_tier2_gather_makes_zero_comtrade_calls",
               "test_budget_exhausted_degrades_to_tier1_only",
               "test_ranking_is_deterministic_on_fixture"):
        assert f"def {fn}" in lock, f"قفل الميزة أ مفقود: {fn}"


def _guard_out_of_coverage_thin_study():
    """LESSONS ٢٢ — عائلة out-of-coverage-thin-study (مواصفة المالك، الميزة أ):
    سوقٌ خارج التغطية يجب ألّا يشغّل دراسةً هزيلة بل يُعاد برسالةٍ صادقة ويُسجَّل
    إشارةَ طلب. الحارس (قراءة مصدر): البوّابة + الرسالة الحرفية + التسجيل +
    تسطيح الواجهة + ملف القفل."""
    api = _read("api.py")
    assert "def _market_in_coverage" in api, "دالّة فحص التغطية غائبة"
    assert '"error": "out_of_coverage"' in api, "بوّابة خارج التغطية غائبة"
    assert "هذه السوق خارج التغطية الحالية" in api and \
        "تواصل معنا لإضافتها" in api, "الرسالة الصادقة الحرفية غائبة"
    assert '"out_of_coverage_demand"' in api, "تسجيل إشارة الطلب غائب"
    assert "_world_markets_enabled()" in api, "البوّابة غير مقيّدة بالصمّام"
    html = _read("web/index.html")
    assert "x.message||x.reason||x.error" in html, \
        "الواجهة لا تُسطّح رسالة detail (لن تظهر رسالة خارج التغطية)"
    assert _exists("tests/test_out_of_coverage_guard.py"), "ملف قفل البوّابة مفقود"
    lock = _read("tests/test_out_of_coverage_guard.py")
    for fn in ("test_out_of_coverage_market_returns_honest_message_and_logs_demand",
               "test_tier1_curated_market_is_always_covered",
               "test_flag_off_no_coverage_guard_any_country_works_todays_way"):
        assert f"def {fn}" in lock, f"قفل البوّابة مفقود: {fn}"


def _guard_intake_no_silent_guess():
    """LESSONS ٢١ — عائلة intake-silent-guess (تصميم الميزة ب، قفل استباقي):
    استقبال المنتج من صورة يجب ألّا يختلق اسماً ولا يبدأ تحليلاً قبل تأكيد
    المستخدم، والمحوّل أماميّ معزول عن طبقات التحليل. الحارس (قراءة مصدر):
    (١) عقد عدم الاختلاق (فرع readable/العتبة => تعذّر قراءة صادق)؛ (٢) حدود
    الصورة + التقييس + العزل؛ (٣) القياس (حجز واحد) في نقطة النهاية؛ (٤) المحوّل
    لا يستورد/يستدعي طبقات التحليل؛ (٥) ملف القفل قائم."""
    import ast as _ast
    src = _read("silk_product_intake.py")
    # (١) عقد عدم الاختلاق + الرسالة الموحّدة + العتبة.
    for needle in ('READ_FAILED_MSG = "تعذّرت القراءة — اكتب الاسم يدوياً"',
                   'def _read_failed', 'def intake_image', 'readable',
                   '_MIN_CONFIDENCE', 'def enabled'):
        assert needle in src, f"علامة إنفاذ الاستقبال مفقودة: {needle}"
    # (٢) حدود الصورة + التقييس + العزل.
    for needle in ('MAX_IMAGE_BYTES', 'ALLOWED_MEDIA_TYPES', 'def _decode_and_check',
                   'def _sanitize', 'def _isolate', '_MAGIC'):
        assert needle in src, f"علامة سلامة الصورة مفقودة: {needle}"
    # (٣) القياس — نقطة النهاية تحجز تفعيلة واحدة كأيّ نداء مدفوع.
    api = _read("api.py")
    assert 'def _intake_vision_allowed' in api and \
        'try_reserve_paid_calls(1)' in api, "قياس نداء الرؤية غائب"
    assert '@app.post("/products/intake")' in api, "نقطة نهاية الاستقبال غائبة"
    assert 'intake.enabled()' in api, "صمّام SILK_IMAGE_INTAKE غير مفحوص"
    # (٤) المحوّل أماميّ معزول — لا يستورد أيّ طبقة تحليل، ولا يستدعيها نصّاً.
    tree = _ast.parse(src)
    imported = {n.names[0].name.split(".")[0] for n in _ast.walk(tree)
                if isinstance(n, _ast.Import)}
    imported |= {(n.module or "").split(".")[0] for n in _ast.walk(tree)
                 if isinstance(n, _ast.ImportFrom)}
    forbidden = {"silk_engine", "silk_missions", "silk_market_analyst",
                 "silk_ai_judge", "silk_market_ranker", "correlation",
                 "silk_synthesis", "silk_llm_runtime"}
    assert imported.isdisjoint(forbidden), imported & forbidden
    for banned in ("analyze(", "deep_research(", "write_reviewed_report",
                   "ResearchManager", "rank_markets("):
        assert banned not in src, f"الاستقبال يمسّ مسار التحليل: {banned}"
    # (٥) ملف القفل قائم بأقفاله المركزية.
    assert _exists("tests/test_product_intake_featureB.py"), "ملف قفل الميزة ب مفقود"
    lock = _read("tests/test_product_intake_featureB.py")
    for fn in ("test_low_confidence_or_unreadable_never_fabricates",
               "test_intake_module_imports_no_pipeline_code",
               "test_endpoint_image_call_is_metered_from_the_cap",
               "test_image_validation_rejects_bad_inputs"):
        assert f"def {fn}" in lock, f"قفل الميزة ب مفقود: {fn}"


def _guard_coverage_gate_year_fallback():
    """LESSON ٢٣ — بوّابة «خارج التغطية» كانت تفشل مفتوحةً دوماً (استطلاع سنة
    اليوم-١ بلا سُلَّم fallback، وكومتريد متأخّر). الحارس (قراءة مصدر + سلوك):
    السُّلَّم + المُحلِّل + السنة المشتركة موجودة، والبوّابة تستعملها، والأقفال قائمة."""
    src = _read("silk_market_ranker.py")
    for n in ("DEFAULT_STUDY_YEAR", "def coverage_year_ladder",
              "def world_import_totals_resolved"):
        assert n in src, f"علامة إنفاذ سُلَّم التغطية مفقودة: {n}"
    api = _read("api.py")
    assert "world_import_totals_resolved" in api, "البوّابة لا تستعمل السُّلَّم"
    # سلوك: السُّلَّم يبدأ من سنة اليوم-١ ويضمن سنة الدراسة في الذيل.
    import datetime as _dt
    import silk_market_ranker as _R
    ladder = _R.coverage_year_ladder()
    assert ladder[0] == _dt.date.today().year - 1, ladder
    assert _R.DEFAULT_STUDY_YEAR in ladder, ladder
    lock = _read("tests/test_out_of_coverage_guard.py")
    for fn in ("test_coverage_gate_closes_when_current_year_empty_but_study_year_full",
               "test_world_import_totals_resolved_ladders_to_first_nonempty_year"):
        assert f"def {fn}" in lock, f"قفل سُلَّم التغطية مفقود: {fn}"


def _guard_sanitizer_obfuscation_variants():
    """LESSON ٢٤ — سبع صيغ تشويش أكّد المشرف نفاذها بالتنفيذ المباشر. الحارس
    السلوكي يبني السلاسل السبع الحرفية ويؤكّد تحييد كلٍّ (المسار العام أو
    مسار العميل) — القفل بالسلسلة الحرفية (silk-operations §4)."""
    import silk_render as _SR
    from silk_reports import (_client_forbidden_hits, _client_redact_text,
                              _client_sanitize)

    def _gen(s):
        return _SR._strip_internal_plumbing(s)

    def _client_clean(s):
        return not _client_forbidden_hits(_client_redact_text(_client_sanitize(s)))

    # (١) stop_reason مباعَد/عارٍ بلا قيمة — المسار العام.
    assert "stop_reason" not in _gen("التوليد stop_reason =  انتهى")
    # (٢) اسم مزوّد لاتيني مباعَد «S e r p A p i» — مسار العميل.
    assert _client_clean("مبنيّ على S e r p A p i التجارية")
    # (٣) درجة ثقة بأرقام عربية-هندية «ثقة=٠٫٦٤» — المسار العام.
    o3 = _gen("التقييم ثقة=٠٫٦٤ للمصدر")
    assert "٠٫٦٤" not in o3 and "ثقة=" not in o3, o3
    # (٤) اسم مزوّد عربي مُشكَّل «إكْسبِلي» — مسار العميل.
    assert _client_clean("المصدر إكْسبِلي غير متاح")
    # (٥) «سجلات الخادم» بلا شدّة — المسار العام.
    assert "سجلات الخادم" not in _gen("خطأ داخلي راجع سجلات الخادم الآن")
    # (٦) بادئة مفتاح بعثة مرقّمة «m3_» — المسار العام.
    assert "m3_" not in _gen("أنتجت m3_pricing_scout النتيجة")
    # (٧) عدّ نداءات أدوات بأرقام عربية «نداءات أدوات: ٢» — المسار العام.
    assert "نداءات أدوات" not in _gen("الملخّص | نداءات أدوات: ٢")


_LESSONS = {
    1: _needles("docs/LIVE_PROOF_RUNBOOK.md", "لا يُشغَّل هيرمتياً"),
    2: _needles("silk_render.py", "_deep_research_view"),
    3: _guard_docx501_row3,          # docx-501 (١)
    4: _needles("api.py", "SILK_REQUIRE_PERSISTENT_DATA_DIR",
                "SILK_DATA_DIR غير مضبوط"),
    5: _needles("silk_storage.py", "def create_research_run",
                "def load_mission_checkpoints"),
    6: _needles("silk_llm_runtime.py", "_JSON_PARSE_FAILURE_GAP"),
    7: _needles("silk_data_layer.py", "_WB_INDICATOR_SOURCE"),
    8: _needles("silk_data_layer.py", "class DataPoint"),
    9: _absent("web/index.html", 'id="snapBtn"'),
    10: _needles("docs/AUDIT_STATUS.md", "قراءة فقط", "غير موجود"),
    11: _guard_docx501_row11,         # docx-501 (٣)
    12: _needles("silk_render.py", "_reconcile_mission_limits", "_first_clause"),
    13: _guard_docx501_row13,         # docx-501 (٢، الفشل الحيّ)
    14: _needles("silk_quality_gate.py", "_check_confidentiality_leaks",
                 "_check_style"),
    15: _needles("tools/live_shape_server.py", "class LiveShapeServer",
                 "def seed_db"),
    16: _needles("silk_ai_judge.py", "_WRITER_MAX_TOKENS", "_MAX_TOKENS_CEILING",
                 "max_tokens=_MAX_TOKENS_CEILING"),
    17: _guard_datapoint_repr_flexible,  # هجوم المشرف — ريبر DataPoint المرن
    18: _guard_vendor_name_leak,         # بلاغ UK — تسريب اسم مزوّد للعميل
    19: _guard_export_format_contract,   # بلاغ المُشرِف — زرّ PDF كان ينزّل docx
    20: _guard_world_tier2_no_fabrication,  # الميزة أ — لا تلفيق فئة-٢/تفجّر ميزانية
    21: _guard_intake_no_silent_guess,      # الميزة ب — لا اختلاق منتج من صورة
    22: _guard_out_of_coverage_thin_study,  # الميزة أ — سوق خارج التغطية لا دراسة هزيلة
    23: _guard_coverage_gate_year_fallback,  # الموجة ١ — بوّابة التغطية كانت تفشل مفتوحة
    24: _guard_sanitizer_obfuscation_variants,  # الموجة ١ — سبع صيغ تشويش المشرف
}

_TRAPS = [
    ("mock_passes_real_fails", "Mock-passes / real-fails",
     _needles("silk_render.py", "_deep_research_view")),
    ("markets_empty_misroute", "misroutes exporters",
     _guard_trap_markets_empty),
    ("two_sanitizers", "Two different sanitizers",
     _guard_trap_two_sanitizers),
    ("redaction_mangling", "Redaction mangling",
     _guard_trap_redaction_mangling),
    ("parallel_cache_window", "Parallel missions and the cache window",
     _guard_trap_parallel_cache_window),
    ("cap_counts_not_dollars", "Cap counted operations, not dollars",
     _needles("silk_usage.py", "def try_reserve_usd")),
    ("styled_not_wired", "Styled-but-never-wired UI affordance",
     _needles("web/index.html", 'data-id="',
              '$("#histList").addEventListener("click"')),
    ("silent_noop_family", "silent no-op has three forms",
     _needles("web/index.html", "function openStoredAnalysis",
              # حزمة الإغلاق، البند ٤: سلسلة /markets في بناء نيّة الدردشة
              # اكتسبت .catch عربياً (كانت ترفض صامتةً فتُعلّق مؤشّر الانتظار).
              "تعذّر تحميل قائمة الأسواق")),
    ("view_after_persist", "view attached AFTER persist",
     _guard_trap_view_after_persist),
    ("strip_plumbing_three_leaks", "leaked three raw forms",
     _guard_trap_strip_plumbing_three_leaks),
    ("orphan_reservation_leak", "Orphaned runs leak their USD reservation",
     lambda: (
         _needles("silk_storage.py", "def reap_orphan_research_runs",
                  "reconcile_usd", "SILK_ORPHAN_STALE_MINUTES")(),
         _needles("api.py", "reap_orphan_research_runs")(),
         _needles("silk_collectors.py", "reap_orphan_research_runs")())),
]


# ── حارس واحد لكل حادثة (تُوسَّع برمجياً لتقارير pytest واضحة) ────────────────

@pytest.mark.parametrize("row", sorted(_LESSONS), ids=[f"lessons-{n}" for n in sorted(_LESSONS)])
def test_lessons_incident_guard_holds(row):
    """كل صفّ في docs/LESSONS.md له حارس حيّ يُفشِل على عودة عائلته."""
    _LESSONS[row]()


@pytest.mark.parametrize("slug,match,check", _TRAPS,
                         ids=[t[0] for t in _TRAPS])
def test_operations_trap_guard_holds(slug, match, check):
    """كل فخّ في silk-operations §2 (THE TRAPS) له حارس حيّ."""
    check()


# ── الاختبار الشامل: التغطية كاملة ضدّ كلا السِّجلّين ─────────────────────────

def _lessons_rows_in_ledger() -> set[int]:
    ledger = _read("docs/LESSONS.md")
    return {int(m.group(1))
            for m in re.finditer(r"^\|\s*(\d+)\s*\|", ledger, re.M)}


def _trap_rows_in_skill() -> list[str]:
    """صفوف بيانات جدول §2 (THE TRAPS) — الخلية الأولى (اسم الفخّ العريض)."""
    skill = _read(".claude/skills/silk-operations/SKILL.md")
    m = re.search(r"## 2\. THE TRAPS(.*?)\n## 3\.", skill, re.S)
    assert m, "قسم §2 THE TRAPS غير موجود في مهارة silk-operations"
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("| **"):        # صفوف البيانات فقط
            continue
        first_cell = line.split("|")[1].strip()
        rows.append(first_cell)
    return rows


def test_meta_registry_covers_every_known_incident():
    """التغطية الشاملة: كل صفّ LESSONS وكل فخّ §2 مُسجَّل هنا بحارس، ولا مدخلة
    يتيمة بلا صفّ مقابل. حادثة جديدة تسقط في أي سِجلّ بلا حارس تُحمِّر هنا."""
    # (أ) LESSONS: مفاتيح السجلّ = أرقام الصفوف بالضبط، متتابعة ١..N.
    ledger_rows = _lessons_rows_in_ledger()
    assert ledger_rows == set(range(1, max(ledger_rows) + 1)), (
        f"أرقام صفوف LESSONS غير متتابعة: {sorted(ledger_rows)}")
    registry_rows = set(_LESSONS)
    assert registry_rows == ledger_rows, (
        f"صفوف LESSONS بلا حارس في السجلّ: {sorted(ledger_rows - registry_rows)}؛ "
        f"حُرّاس بلا صفّ: {sorted(registry_rows - ledger_rows)}")

    # (ب) TRAPS: كل صفّ فخّ في §2 يطابقه حارس واحد بالضبط عبر إبرة `match`،
    # وكل حارس فخّ يطابق صفّاً واحداً على الأقل (لا يتيم).
    trap_rows = _trap_rows_in_skill()
    assert trap_rows, "لم تُقرَأ صفوف فخاخ من المهارة"
    for row in trap_rows:
        matched = [slug for slug, match, _ in _TRAPS if match in row]
        assert len(matched) == 1, (
            f"صفّ الفخّ «{row[:60]}…» يطابقه {len(matched)} حُرّاس (المتوقّع ١): "
            f"{matched}")
    for slug, match, _ in _TRAPS:
        assert any(match in row for row in trap_rows), (
            f"حارس الفخّ «{slug}» (match={match!r}) لا يطابق أيّ صفّ في §2 — "
            "يتيم؛ حدِّث السجلّ أو المهارة")


def test_meta_docx501_trio_all_have_behavioral_guards():
    """الحوادث الثلاث لعطل docx-501 (LESSONS ٣/١١/١٣) لها حُرّاس **سلوكية**
    (تبني/تنقّي فعلياً)، لا مجرّد وجود رمز — أمر المُشرِف الصريح."""
    behavioral = {3: _guard_docx501_row3, 11: _guard_docx501_row11,
                  13: _guard_docx501_row13}
    for row, guard in behavioral.items():
        assert _LESSONS[row] is guard, (
            f"صفّ docx-501 رقم {row} ليس مربوطاً بحارسه السلوكي")
        guard()  # يجب أن يمرّ فعلياً الآن
