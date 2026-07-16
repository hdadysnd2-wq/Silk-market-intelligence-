# LESSONS.md — سجلّ الأخطاء الدائم · the permanent mistake ledger

> **الغرض.** ذاكرة دائمة تُحمَّل كل جلسة. كل صفّ خطأ حقيقي كلّف وقتاً أو مالاً،
> يُقابله **قانون دائم** و**أداة إنفاذ ميكانيكية** (اختبار/حارس شيفرة/علامة
> منهج موثَّقة). قانون بلا إنفاذ = أمنية؛ لذا لكل صفّ مرساة يثبت
> `tests/test_lessons_enforcement.py` بقاءها — حذف أي حارس يُحمِّر CI.
>
> **Purpose.** Permanent memory loaded every session. Each row is a real
> mistake that cost time or money, paired with a permanent rule and a
> mechanical enforcement artifact. A rule without enforcement is a wish, so
> every row is anchored by `tests/test_lessons_enforcement.py`, which fails
> CI if a named guard disappears.

**أول فعل في كل جلسة:** اقرأ هذا الملف + `docs/LIVE_PROOF_RUNBOOK.md` قبل كتابة
أي شيفرة. **First action every session:** read this file + the live-proof
runbook before writing any code.

**قراءة عمود الإنفاذ:** «test» = اختبار سلوكي يُفشِل على الانحدار؛ «guard» =
رمز مصدر (دالة/ثابت/فرع) يجب أن يبقى؛ «doc» = علامة منهج في وثيقة/مهارة (لا
اختبار سلوكي ممكن — قاعدة عملية/حيّة). البنود ١ و١٠ موثَّقتان بطبيعتهما (لا
يمكن قفل تحقّق حيّ هرمتياً)، لكن وجود وثائقها وعلاماتها مُنفَّذ ميكانيكياً.

---

## السجلّ · the ledger

| # | الخطأ (mistake) | كيف اكتُشف (how we caught it) | القانون الدائم (permanent rule) | الإنفاذ (enforcement) |
|---|---|---|---|---|
| 1 | ادُّعي «مُصلَح/تمّ» بينما العمل مدموج محلياً فقط؛ نتيجة خضراء محلياً عوملت كأنها تعمل حيّاً. | مراجعات حيّة متكرّرة كشفت أن تقارير «مكتملة» لم تعمل على النشر الفعلي (البلاغات في `DEEP_RESEARCH_DECISIONS.md`). | **مدموج ≠ يعمل؛ أخضر محلياً ≠ تمّ.** لا يُعَدّ العمل منجَزاً إلا بتحقّق **حيّ بأثر** (مخرَج curl، ملف مُنزَّل، سطر سجلّ/تتبّع). العيّنة المموّهة تُوسَم مموّهة صراحةً، لا تُقدَّم كحيّة. | `doc`: `docs/LIVE_PROOF_RUNBOOK.md` (إجراء الالتقاط، «لا يُشغَّل هيرمتياً»)؛ مهارة `pr-and-wave-discipline` §5 (تصنيف الدليل: direct reproduction / static code review / no sufficient evidence — pending). لا اختبار سلوكي ممكن — قاعدة حيّة؛ وجود الوثائق/العلامات مُنفَّذ في `test_lessons_enforcement.py`. |
| 2 | المُصدِّرات قرأت فرع `/analyze` القديم بدل `dr["report"]` — تقرير بحث عميق خرج بقالب فارغ (تغطية 0.0%، «سنة None»). | بلاغ حيّ (تمور/هولندا): اللوحة تعرض التقرير الغنيّ لكن `report.md` قالب فارغ و`report.docx` يفشل 501. | **كل مُصدِّر/عارض لنتيجة `/research` يقرأ من عرض `deep_research` حصراً**، لا قالب `/analyze`؛ واختبارات القفل تعمل على شكل مدوّنة هولندا الحقيقية المُعاد بناؤها، لا نماذج مثالية. | `guard`: `silk_render._deep_research_view`؛ `silk_reports._md_deep_research`/`_render_research_docx`/`render_client_docx` (فرع `if view.get("deep_research")`). `test`: `test_research_export_from_view.py::test_report_md_renders_deep_research_not_analyze_template` (+ يؤكّد غياب علامات قالب /analyze). |
| 3 | فشل تصدير docx (501) شُحن لأن الاختبارات استعملت نماذج مموّهة. | التصدير الحيّ فشل رغم خضرة الاختبارات المموّهة. | **اختبارات التصدير تُنتِج وتفتح ملف .docx فعلياً** من مدوّنة تحليل حقيقية الشكل (لا نموذج) وتفتّش فقراته وخلايا جداوله. | `test`: `test_research_export_from_view.py::test_report_docx_client_does_not_501_on_judgment_language` (يبني docx ويعيد فتحه عبر `Document(path)`)؛ `conftest.docx_all_text`؛ `test_client_report_export.py`. |
| 4 | قرص Railway الفاني (`data_dir=null`) يفقد التحليلات المدفوعة بصمت عند إعادة النشر. | `/health` الحيّ أظهر `storage.data_dir: null`؛ التتبّع أكّد لا وحدة تخزين مركَّبة. | **قواعد البيانات على وحدة تخزين مركَّبة**؛ الإقلاع يفشل بصوت عالٍ إن لم يُوجَّه تخزين دائم (لا فقدان صامت)، وتحذير `/health` دائم في كل الأحوال. | `guard`: مصيدة إقلاع `SILK_REQUIRE_PERSISTENT_DATA_DIR` في `api.create_app()` (RuntimeError) + تحذير `/health` («SILK_DATA_DIR غير مضبوط»). `test`: `test_persistent_volume.py::test_create_app_refuses_ephemeral_storage_when_require_flag_set`؛ `test_analysis_history_storage.py::test_health_warns_when_silk_data_dir_unset`. |
| 5 | إعادة النشر قتلت تشغيلات خلفية منتصف الطريق — بعثات مكتملة ضاعت، فأُعيد التشغيل من الصفر (إنفاق مضاعف). | بلاغ حيّ (حادثة نفاد الاعتمادات، PR #65). | **كل تشغيلة طويلة قابلة للاستئناف لكل بعثة**؛ «الاستئناف بالقروش، إعادة التشغيل بالدولارات» ثابتٌ باختبار، والبعثات المكتملة تنجو من إعادة النشر على القرص. | `guard`: `silk_storage.{create_research_run,save_mission_checkpoint,load_mission_checkpoints,mark_research_failed}` + فرع استئناف `/research`. `test`: `test_wave13_resilience.py::test_mid_run_crash_then_resume_skips_completed_missions`؛ `test_persistent_volume.py::test_redeploy_preserves_research_checkpoints_and_resume_reads_them`. |
| 6 | مخرَج JSON من النموذج فُسِّر بسذاجة — بعثات ماتت على أسوار ```json ونصّ زائد. | بلاغ حيّ (اختفاء سعر Albert Heijn الحقيقي، الموجة ٨). | **كل JSON من نموذج يمرّ عبر المستخلِص المتين** (نزع الأسوار، محاولة إصلاح واحدة، تحقّق شكل)؛ الفشل = فجوة معلنة، **لا اختلاق أبداً**. | `guard`: `silk_llm_runtime._json_candidates`/`_parse_output`/`_JSON_PARSE_FAILURE_GAP` (الاسم الصحيح — لا `_extract_json` في هذه الوحدة)؛ `silk_ai_judge._extract_json`. `test`: `test_technical_mission_failures_item2.py::test_json_repair_retry_stays_declared_gap_when_repair_also_fails` (+ ~14 عبر wave8/9). |
| 7 | معامل خاطئ للبنك الدولي أفرغ بعثة كاملة بصمت (WGI هولندا/إسبانيا). | بلاغ حيّ (الموجة ١٠): WGI فارغ يتدهور لملاحظة عامة بدل تشخيص. | **معاملات كل API خارجي تُثبَّت على شكل نقطة نهاية حقيقية مُسجَّلة**؛ وفشل البعثة يتدهور لفجوة معلنة، لا يكسر التشغيلة ولا يختفي صامتاً. | `guard`: `silk_data_layer._WB_INDICATOR_SOURCE` (WGI→source=3) + `_wb_shape_error`؛ `silk_agents.BaseAgent` (استثناء `_execute` → تقرير فاشل بـDataPoint معلَّم). `test`: `test_wave_p4_source_outages.py::test_every_mission_governance_indicator_is_source3_registered` (حارس تناسق عبر-وحدات جديد). |
| 8 | فجوات بيانات صادقة (تعريفة WITS، صرف، SAM/SOM) كادت تُعامَل كأخطاء تحتاج «إصلاحاً». | مراجعة: محاولة سدّ الفجوة برقم بدل إعلانها. | **عقد عدم الاختلاق لا يُمَسّ**؛ صنِّف نوع الفجوة **قبل** لمس الشيفرة. القيمة عند الفشل = `None` بثقة `0.0`، لا صفر مختلَق. | `guard`: `silk_data_layer.DataPoint` (مسارات الفشل تعيد `None`/`0.0`). `test`: `test_smoke.py::test_tradeflow_all_records_missing_value_is_declared_gap` + `test_engine_pipeline_offline_no_fabrication` (تحت `_block_network`، تؤكّد `None` لا صفراً)؛ المبدأ المؤسِّس في `CLAUDE.md`. |
| 9 | أزرار واجهة ميتة/غامضة («لقطة سريعة»/«حلّل السوق») تآكلت بها الثقة. | بلاغ المالك + تدقيق الواجهة الوظيفي. | **لا زرّ فعل يُشحَن بلا غرض مُصرَّح + تكلفة مرئية**؛ ما لا يستطيع المالك شرحه يُحذَف أو يُعاد وسمه بصدق. | `test`: `test_item3_analyze_screen_button.py::test_all_three_action_buttons_have_honest_tooltips_and_distinct_labels`؛ `test_ui_action_buttons_have_purpose.py::test_every_runbar_action_button_has_a_tooltip` (حارس عام يعمّم القاعدة على أي زرّ فعل جديد)؛ `test_r4_product_snapshot.py::test_snapshot_never_calls_claude`. |
| 10 | تدقيقات تحقّق تُتخطّى أو تُبلَّغ ذاتياً بلا دليل. | بلاغات سابقة: ادعاء PASS/FAIL بلا أثر حيّ. | **التدقيقات قراءة-فقط، بالدليل، تُشغَّل على الحيّ، وBLOCKED جواب صادق صحيح.** كل ادعاء مُسنَد إلى file:line؛ «غير موجود» يُذكَر صراحةً؛ لا ادعاء بقراءة سجلّات لم تُقرأ. | `doc`: `docs/AUDIT_STATUS.md` (قراءة فقط، file:line، «غير موجود»)؛ `docs/LIVE_PROOF_RUNBOOK.md`؛ مهارات `pr-and-wave-discipline` §5 / `silk-operations` §4 / `change-rules` (تصنيف الدليل + «no sufficient evidence — pending»). وجود الوثائق/العلامات مُنفَّذ في `test_lessons_enforcement.py`. |
| 11 | 501 تصدير العميل تكرّر ثالث مرة (بعد #90 و#103): حارس التصدير يملك محفّزات عربية بلا أي استبدال مقابل في المُطهِّر، وكل فكس سابق طارد المصطلح الواحد بعد وقوعه؛ والواجهة كانت تبتلع جسم الـ501 الذي يسمّي المصطلح بالضبط. | بلاغ حي ثالث («فشل التنزيل: HTTP 501 وما زال») + إعادة إنتاج محلية آلية عدّدت ٣ محفّزات غير مغطّاة («استدعاء أداة»، «بوابة الجودة»، «بلا استشهاد»). | **تغطية المُطهِّر تشمل ميكانيكياً كل محفّز عربي في حارس تصدير العميل** — نمط حارس جديد بلا استبدال مقابل يفشل البناء فوراً، لا عند البلاغ الحي التالي. وكل خطأ تنزيل يعرض تفصيل الجسم لا الحالة العارية. | `test`: `test_client_sanitizer_covers_guard.py::test_every_arabic_guard_trigger_is_neutralized_by_the_sanitizer` (استخراج آلي من أنماط الحارس نفسها + صيغ يدوية للأنماط المعقّدة/dpN) + `::test_dlreport_surfaces_the_501_detail_not_bare_status`. |

---

## بروتوكول التحديث الذاتي · self-update protocol

عند اكتشاف أي خطأ جديد من نفس العائلة (أو عائلة جديدة كلّياً):

1. **أضف صفّاً إلى هذا الجدول في نفس الجلسة** — الخطأ، كيف اكتُشف، القانون،
   الإنفاذ.
2. **أنشئ اختبار قفل قبل الفكس نفسه** (test-first lock) — الاختبار يُفشِل على
   السلوك الخاطئ أولاً، ثم يمرّ بعد الإصلاح.
3. **اربط الصفّ بمرساة في `tests/test_lessons_enforcement.py`** (رمز/وثيقة/
   اختبار) كي لا يختفي الحارس بصمت لاحقاً.

هذه القاعدة نفسها مكتوبة في `CLAUDE.md` (قسم القوانين غير القابلة للكسر) فتُحمَّل
كل جلسة. When you find a new mistake of the same (or a new) family: add a row
here **the same session**, write the lock-test **before** the fix itself
(test-first), and anchor the row in `test_lessons_enforcement.py`.
