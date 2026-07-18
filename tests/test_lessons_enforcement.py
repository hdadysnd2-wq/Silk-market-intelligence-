"""العمود الميكانيكي لِـ docs/LESSONS.md — كل صفّ في السجلّ يسمّي أداة إنفاذ،
وهذا الملف يثبت أن كل أداة مسمّاة **لا تزال موجودة** في الشجرة. حذف حارس أو
وثيقة يكسر هذا الاختبار فيُحمرّ CI — فلا يمكن لأداة إنفاذ أن تختفي بصمت.

هذا اختبار **وجود/مرساة** لا إعادة تنفيذ للسلوك (الاختبارات السلوكية نفسها
تُفشِل على الانحدار). قيمته العظمى للبنود الموثَّقة فقط (١ و١٠) التي لا حارس
آخر لها: بدونه يبقى CI أخضر لو حُذِفت وثيقة التدقيق أو أُفرِغت.

قراءة الوجود فقط (Path.exists + تفتيش نصّي للمصدر) — هرمتي، بلا شبكة،
دون ثانية. لا يكرّر تأكيداً سلوكياً (ذلك يُضاعِف الصيانة).

Run: python3 -m pytest tests/test_lessons_enforcement.py -q
"""
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel: str) -> str:
    with open(os.path.join(_ROOT, rel), encoding="utf-8") as f:
        return f.read()


def _exists(rel: str) -> bool:
    return os.path.exists(os.path.join(_ROOT, rel))


# كل مدخلة: (رقم الدرس، مسار المصدر، سلاسل يجب أن تكون كلها حاضرة).
# المصادر المسمّاة هنا هي بالضبط عمود «الإنفاذ» في docs/LESSONS.md.
_SYMBOL_ANCHORS = [
    # البند ٢ — المُصدِّرات تقرأ فرع deep_research لا قالب /analyze
    (2, "silk_render.py", ["_deep_research_view"]),
    (2, "silk_reports.py", ["_md_deep_research", "render_client_docx"]),
    # البند ٤ — مصيدة إقلاع التخزين الفاني + تحذير /health
    (4, "api.py", ["SILK_REQUIRE_PERSISTENT_DATA_DIR",
                   "SILK_DATA_DIR غير مضبوط"]),
    # البند ٥ — نقاط تفتيش/استئناف البعثات
    (5, "silk_storage.py", ["def create_research_run", "def save_mission_checkpoint",
                            "def load_mission_checkpoints", "def mark_research_failed"]),
    # البند ٦ — مستخلِصات JSON المتينة (الاسم الصحيح: لا _extract_json في
    # silk_llm_runtime — بل _json_candidates/_parse_output؛ _extract_json في
    # silk_ai_judge وحدها)
    (6, "silk_llm_runtime.py", ["_json_candidates", "_parse_output",
                                "_JSON_PARSE_FAILURE_GAP"]),
    (6, "silk_ai_judge.py", ["_extract_json"]),
    # البند ٧ — معامل source للبنك الدولي + تدهور البعثة لفجوة معلنة
    (7, "silk_data_layer.py", ["_WB_INDICATOR_SOURCE", "_wb_shape_error"]),
    (7, "silk_agents.py", ["class BaseAgent"]),
    # البند ٨ — عقد DataPoint (لا اختلاق)
    (8, "silk_data_layer.py", ["class DataPoint"]),
]

# كل مدخلة: (رقم الدرس، مسار الوثيقة، علامات المنهج التي يجب أن تبقى).
_DOC_ANCHORS = [
    # البند ١ — merged ≠ works؛ الدليل الحيّ بأثر
    (1, "docs/LIVE_PROOF_RUNBOOK.md", ["لا يُشغَّل هيرمتياً"]),
    (1, ".claude/skills/pr-and-wave-discipline/SKILL.md",
     ["direct reproduction", "static code review",
      "no sufficient evidence — pending"]),
    # البند ١٠ — التدقيق قراءة فقط، بالدليل، وBLOCKED جواب صادق
    (10, "docs/AUDIT_STATUS.md", ["قراءة فقط", "غير موجود"]),
    (10, ".claude/skills/pr-and-wave-discipline/SKILL.md",
     ["no sufficient evidence — pending"]),
    # البند ١٥ — دلاء الصدق المنقسمة (hermetic only مقابل real-server+browser)
    (15, ".claude/skills/pr-and-wave-discipline/SKILL.md",
     ["hermetic only", "passed real-server + browser e2e", "e2e-live-shape"]),
]

# كل مدخلة: (رقم الدرس، ملف الاختبار، دوال اختبار يجب أن تبقى).
_TEST_ANCHORS = [
    (2, "tests/test_research_export_from_view.py",
     ["def test_report_md_renders_deep_research_not_analyze_template"]),
    (3, "tests/test_research_export_from_view.py",
     ["def test_report_docx_client_does_not_501_on_judgment_language"]),
    (3, "tests/conftest.py", ["def docx_all_text"]),
    (4, "tests/test_analysis_history_storage.py",
     ["def test_health_warns_when_silk_data_dir_unset"]),
    (4, "tests/test_persistent_volume.py",
     ["def test_create_app_refuses_ephemeral_storage_when_require_flag_set"]),
    (5, "tests/test_wave13_resilience.py",
     ["def test_mid_run_crash_then_resume_skips_completed_missions"]),
    (5, "tests/test_persistent_volume.py",
     ["def test_redeploy_preserves_research_checkpoints_and_resume_reads_them"]),
    (6, "tests/test_technical_mission_failures_item2.py",
     ["def test_json_repair_retry_stays_declared_gap_when_repair_also_fails"]),
    (7, "tests/test_wave_p4_source_outages.py",
     ["def test_every_mission_governance_indicator_is_source3_registered"]),
    (8, "tests/test_smoke.py",
     ["def test_tradeflow_all_records_missing_value_is_declared_gap"]),
    (9, "tests/test_item3_analyze_screen_button.py",
     ["def test_all_action_buttons_have_honest_tooltips_and_distinct_labels"]),
    (9, "tests/test_ui_action_buttons_have_purpose.py",
     ["def test_every_runbar_action_button_has_a_tooltip"]),
    (11, "tests/test_client_sanitizer_covers_guard.py",
     ["def test_every_arabic_guard_trigger_is_neutralized_by_the_sanitizer",
      "def test_dlreport_surfaces_the_501_detail_not_bare_status"]),
    (12, "tests/test_limits_reconciliation_b1.py",
     ["def test_resolved_supplier_share_gap_is_retagged_not_contradiction",
      "def test_genuinely_unresolved_gap_stays_verbatim"]),
    (13, "tests/test_client_export_redact_not_refuse.py",
     ["def test_render_client_docx_does_not_501_on_english_source_title"]),
    (14, "tests/test_report_output_overhaul.py",
     ["def test_quality_gate_fails_on_confidentiality_leak_tokens",
      "def test_docx_is_rtl_document_wide",
      "def test_finding_assembly_uses_public_source_not_tool_use"]),
    (15, "tests/test_rung2_real_server.py",
     ["def test_report_md_serves_real_narrative_not_the_empty_analyze_template",
      "def test_report_docx_downloads_a_real_openable_document_no_501"]),
    (15, "tests/test_rung3_playwright_e2e.py",
     ["def test_rung3_full_browser_flow_word_and_md_export_and_sidebar"]),
    (16, "tests/test_command6_regression_budget_and_pricing.py",
     ["def test_full_report_with_all_blocks_completes_end_to_end_not_skeleton",
      "def test_writer_continuation_call_uses_the_ceiling_not_the_base_budget",
      "def test_every_default_routed_model_is_priced",
      "def test_maxtokens_truncated_call_still_meters_its_burned_tokens"]),
    # البند ١٧ — ريبر DataPoint المختصر/الشاذ مرّ نصف مترجم (هجوم المشرف الحي)؛
    # الحارس: النمط المرن + شبكة الأمان، وسلاسل المشرف الحرفية في السجل.
    (17, "tests/test_regression_registry.py",
     ["def _guard_datapoint_repr_flexible"]),
    # البند ١٨ — تسريب اسم مزوّد داخلي للعميل (بلاغ UK الحي): كنس المدوّنة
    # القانونية + شكل UK بزيرو تطابق، والحارس السلوكي في السجل.
    (18, "tests/test_vendor_name_leak_item1.py",
     ["def test_client_export_names_no_vendor_across_canonical_and_uk_shapes",
      "def test_client_vendor_guard_fails_loud_on_injected_vendor_name"]),
    (18, "tests/test_regression_registry.py",
     ["def _guard_vendor_name_leak"]),
    # البند ١٩ — عقد صيغة التصدير (زرّ PDF كان ينزّل docx): الحارس السلوكي في
    # السجل + تدفّق المتصفّح الحقيقي يؤكّد توقيع %PDF.
    (19, "tests/test_regression_registry.py",
     ["def _guard_export_format_contract"]),
    # البند ٢٠ — تغطية العالم (الميزة أ): لا تلفيق فئة-٢ ولا تفجّر ميزانية؛
    # الأقفال السلوكية + الحارس السلوكي في السجل.
    (20, "tests/test_world_coverage_tierA.py",
     ["def test_tier_separation_and_labels",
      "def test_tier2_never_carries_a_local_csv_value",
      "def test_tier2_gather_makes_zero_comtrade_calls",
      "def test_budget_exhausted_degrades_to_tier1_only"]),
    (20, "tests/test_regression_registry.py",
     ["def _guard_world_tier2_no_fabrication"]),
    # البند ٢١ — استقبال المنتج من صورة (الميزة ب): لا اختلاق منتج، والمحوّل
    # أماميّ معزول؛ الأقفال السلوكية + الحارس السلوكي في السجل.
    (21, "tests/test_product_intake_featureB.py",
     ["def test_low_confidence_or_unreadable_never_fabricates",
      "def test_intake_module_imports_no_pipeline_code",
      "def test_endpoint_image_call_is_metered_from_the_cap"]),
    (21, "tests/test_regression_registry.py",
     ["def _guard_intake_no_silent_guess"]),
    # البند ٢٢ — بوّابة «خارج التغطية» (الميزة أ): سوق خارج التغطية لا دراسة
    # هزيلة بل رسالة صادقة + إشارة طلب؛ الأقفال + الحارس السلوكي في السجل.
    (22, "tests/test_out_of_coverage_guard.py",
     ["def test_out_of_coverage_market_returns_honest_message_and_logs_demand",
      "def test_flag_off_no_coverage_guard_any_country_works_todays_way"]),
    (22, "tests/test_regression_registry.py",
     ["def _guard_out_of_coverage_thin_study"]),
    # البند ٢٣ — الفيتوتشيني: لا حجز/إنفاق برمز HS غير محسوم؛ البوّابة الصلبة
    # + المُصنِّف المقيس + الحارس السلوكي في السجل.
    (23, "tests/test_wave1_hs_classifier.py",
     ["def test_research_hard_gate_422_on_empty_hs6_no_reservation",
      "def test_endpoint_low_confidence_is_metered_count_from_the_cap"]),
    (23, "tests/test_regression_registry.py",
     ["def _guard_unresolved_hs_silent_spend"]),
    # البند ٢٤ — الحارسان قاعدتان مبنيّتان على البيانات لا حالتا منتج؛ قفل
    # التعميم (≥٤ عيّنات) + غياب الترميز الصلب + الحارس السلوكي في السجل.
    (24, "tests/test_wave1_hs_classifier.py",
     ["def test_classifier_and_advisory_paths_have_no_hardcoded_product_or_iso_or_hs",
      "def test_producer_advisory_generalizes_from_data_not_names"]),
    (24, "tests/test_regression_registry.py",
     ["def _guard_hardcoded_product_rule"]),
]

# حراس رمزية للبندين ١٢/١٣ (المصالحة + نقِّ-لا-ترفض) — وجود الدوال في المصدر.
_SYMBOL_ANCHORS_EXTRA = [
    (12, "silk_render.py", ["_reconcile_mission_limits", "_first_clause"]),
    (13, "silk_reports.py", ["_client_redact_residual"]),
    (13, "tools/post_deploy_smoke.py", ["report.docx"]),
    # البند ١٤ — تحديث مخرجات تقرير البحث (سرّية/عملة/RTL/اكتمال/PDF/أسلوب)
    (14, "silk_quality_gate.py", ["_check_confidentiality_leaks",
                                  "_check_style", "_check_trailing_ellipsis"]),
    (14, "silk_reports.py", ["def _apply_rtl", "def docx_to_pdf",
                            "def _clean_source_label", "def _trim_sentence"]),
    (14, "silk_render.py", ["_map_mission_keys", "_CLAUDE_WORD_RE"]),
    # البند ١٥ — المالك آخِر تأكيد لا أوّل مكتشف؛ رُتب الاختبار ٢–٣ + الوظيفة
    # المطلوبة e2e-live-shape + المُنشئ القانوني للمدوّنة الحقيقية الشكل.
    (15, "tools/live_shape_server.py",
     ["class LiveShapeServer", "def seed_db", "netherlands_research_blob"]),
    (15, "tools/canonical_netherlands.py", ["def netherlands_research_blob"]),
    (15, ".github/workflows/e2e-live-shape.yml", ["e2e-live-shape"]),
    # البند ١٥ — ميزانية الكاتب/المحلل أُعيد قياسها؛ نداء الإكمال يأخذ السقف.
    (16, "silk_ai_judge.py", ["_WRITER_MAX_TOKENS", "_MAX_TOKENS_CEILING",
                              "max_tokens=_MAX_TOKENS_CEILING"]),
    (16, "silk_market_analyst.py", ["_ANALYST_MAX_TOKENS"]),
    # البند ١٧ — النمط المرن + شبكة أمان DataPoint في المعقِّم نفسه.
    (17, "silk_render.py", ["_DATAPOINT_REPR_RE", "_DATAPOINT_ANY_RE"]),
    # البند ١٨ — قائمة أسماء المزوّدين الممنوعة على سطح العميل (بلاغ UK الحي):
    # المُطهِّر + المنقِّي + الحارس، وسطر next_step بلا اسم مزوّد.
    (18, "silk_reports.py", ["_CLIENT_VENDOR_RE", "_CLIENT_VENDOR_GENERIC",
                             "vendor_name"]),
    # البند ١٩ — عقد صيغة التصدير: الزرّ الأساسي يُسلّم PDF، والخادم يخدمه،
    # ومحرّك التحويل مثبَّت على صورة النشر (لا CI فقط).
    (19, "web/index.html", ['dlReport("pdf")', 'kind==="pdf"',
                            'data-act="pdf"']),
    (19, "api.py", ["report.pdf", 'media_type="application/pdf"']),
    (19, "Dockerfile", ["libreoffice-writer"]),
]


def test_lessons_ledger_and_its_wiring_exist():
    """السجلّ نفسه + وصلاته في CLAUDE.md حاضرة."""
    assert _exists("docs/LESSONS.md"), "docs/LESSONS.md غائب — سجلّ الدروس"
    claude = _read("CLAUDE.md")
    assert "docs/LESSONS.md" in claude, "CLAUDE.md لا يشير إلى LESSONS.md"
    assert "قوانين غير قابلة للكسر" in claude, (
        "قسم القوانين غير القابلة للكسر غائب من CLAUDE.md")


def test_every_symbol_anchor_still_present():
    """كل رمز مصدر مسمّى في عمود الإنفاذ لا يزال موجوداً."""
    missing = []
    for rule, path, needles in _SYMBOL_ANCHORS + _SYMBOL_ANCHORS_EXTRA:
        if not _exists(path):
            missing.append(f"[rule {rule}] ملف مفقود: {path}")
            continue
        src = _read(path)
        for needle in needles:
            if needle not in src:
                missing.append(f"[rule {rule}] {path}: رمز مفقود «{needle}»")
    assert not missing, "أدوات إنفاذ رمزية اختفت:\n" + "\n".join(missing)


def test_every_doc_anchor_still_carries_its_method_markers():
    """البنود الموثَّقة فقط (١، ١٠) — الوثائق موجودة وتحمل علامات منهجها."""
    missing = []
    for rule, path, needles in _DOC_ANCHORS:
        if not _exists(path):
            missing.append(f"[rule {rule}] وثيقة مفقودة: {path}")
            continue
        doc = _read(path)
        for needle in needles:
            if needle not in doc:
                missing.append(f"[rule {rule}] {path}: علامة منهج مفقودة «{needle}»")
    assert not missing, "علامات منهج التدقيق/الدليل اختفت:\n" + "\n".join(missing)


def test_every_named_behavioral_test_still_present():
    """كل اختبار سلوكي مسمّى في السجلّ لا يزال موجوداً (يحمي من الحذف الصامت)."""
    missing = []
    for rule, path, needles in _TEST_ANCHORS:
        if not _exists(path):
            missing.append(f"[rule {rule}] ملف اختبار مفقود: {path}")
            continue
        src = _read(path)
        for needle in needles:
            if needle not in src:
                missing.append(f"[rule {rule}] {path}: اختبار مفقود «{needle}»")
    assert not missing, "اختبارات إنفاذ مسمّاة اختفت:\n" + "\n".join(missing)


def test_all_ledger_rules_are_covered_by_at_least_one_anchor():
    """كل درس في السجلّ له مرساة إنفاذ واحدة على الأقل — لا صفّ بلا حارس.
    عدد الصفوف يُقرأ من docs/LESSONS.md نفسه (أسطر `| N |`) فلا يتخلّف هذا
    الاختبار عن السجلّ عند إضافة درس جديد (بروتوكول التحديث الذاتي)."""
    import re as _re
    ledger = _read("docs/LESSONS.md")
    rows = {int(m.group(1))
            for m in _re.finditer(r"^\|\s*(\d+)\s*\|", ledger, _re.M)}
    assert rows and rows == set(range(1, max(rows) + 1)), (
        f"أرقام صفوف السجلّ غير متتابعة: {sorted(rows)}")
    covered = {r for r, _, _ in _SYMBOL_ANCHORS + _SYMBOL_ANCHORS_EXTRA}
    covered |= {r for r, _, _ in _DOC_ANCHORS}
    covered |= {r for r, _, _ in _TEST_ANCHORS}
    assert covered == rows, (
        f"دروس بلا أي مرساة إنفاذ: {sorted(rows - covered)}؛ "
        f"مراسٍ بلا صفّ في السجلّ: {sorted(covered - rows)}")
