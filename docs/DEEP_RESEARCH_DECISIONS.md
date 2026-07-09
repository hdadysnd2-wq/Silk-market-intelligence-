# قرارات البحث العميق — سجل الموجات ١-٦ (V5)

> يوثّق هذا الملف كل قرار تصميم/تكليف اتُّخذ أثناء بناء مبادرة "التكليف
> الختامي" (Silk Deep Market Research: 12 Claude Agents + Comprehensive
> Analyst + Professional Report). القاعدة: أي فجوة أو انحراف عن التكليف
> الحرفي **مُعلَن هنا صراحة**، لا صامت. راجع أيضاً `docs/TUNING.md`
> (بروتوكول التنقيح) و`CLAUDE.md` (الهيكل العام والمبدأ التأسيسي).

## نطاق هذه المبادرة مقابل خطة التنفيذ القائمة

`docs/EXECUTION_PLAN.md`/`docs/VISION.md` لا يذكران هذه المبادرة إطلاقاً
(تصفان محرّك التقاطع/الاكتشاف المعكوس/الامتثال — موجات ٠-٥ منتهية
ومدموجة). التكليف الختامي طبقة **إضافية** جديدة كلياً (١٢ وكيل كلود
بالأدوات + محلل شامل + كاتب/مراجع) لم تكن مخطَّطة في تلك الوثائق. قرار
المالك الصريح: المضي قدماً حرفياً بالتكليف رغم ذلك — موثَّق هنا لأن أي
تدقيق لاحق سيسأل "من أين جاء هذا؟".

**الأثر على استهلاك كلود**: `/analyze` (المسار القديم) يستهلك نداء كلود
واحداً إضافياً على الأكثر (بوابة H2). `/research` (المسار الجديد) يستهلك
حتى ١٥ نداء كلود لكل تشغيلة (١٢ بعثة + محلل + توليف مرحلة ٢ + كاتب/مراجع
حتى دورتين) — محكوم بنفس حجز `SILK_PAID_DAILY_CAP` (تفعيلة واحدة لكل
طلب، كـ`/analyze` تماماً) + سقف حجم منفصل (`SILK_RESEARCH_MAX_LLM_CALLS`/
`_MAX_TOOL_CALLS`، انظر أدناه).

## قرارات معمارية

### ١. التسجيل الإضافي لا الاستبدال (AGENT_CATALOG)
الـ١٤ وكيلاً القائمون (trade/economic/competition/...) بقوا كما هم
حرفياً. البعثات الـ١٢ الجديدة + reviewer + report_writer سُجِّلت بمفاتيح
مختلفة عبر `silk_agents.register_agents()` (تسجيل إضافي، ١٤→٢٨ صفاً، لا
تصادم). `/analyze` الحالي **لا يتأثر إطلاقاً** — مسار `/research` وحده
يستدعي البعثات الجديدة. (قرار مالك صريح أثناء البناء، بديل "الاستبدال"
المرفوض لأنه كان سيغيّر سلوك `/analyze` القائم بلا داعٍ.)

### ٢. مُحلِّل السوق العالمي — إصلاح ثغرة حقيقية
`silk_market_resolver.resolve_market()` كان يفشل بصمت في مطابقة "U.A.E."/
"U.K."/"U.S.A." (نقاط الاختصار) و"Turkey" (تركيا تبنّت "Türkiye" رسمياً
في مlédoze/countries بعد تبنّي الأمم المتحدة الاسم ٢٠٢٢، فحُذف "Turkey"
من الأسماء المعتمدة) — أربعة من أسواق سِلك الـ٣٨ ذات الأولوية كانت
ستُفقَد بصمت. أُصلح بتطبيع النقاط في `_norm()` + إضافة "Turkey" كاسم
شائع بديل (`ALIAS_OVERRIDES` في `tools/fetch_countries.py`). عتبة
المطابقة الضعيفة ضُبطت ٠٫٩٣ (لا ٠٫٧٥) بعد ملاحظة أن "Nigera" (خطأ إملائي)
تطابق "Nigeria" و"Niger" معاً بنسب متقاربة — الغموض بين دولتين حقيقيتين
يستحق سؤال المستخدم لا تخميناً صامتاً.

### ٣. `correlation.py` لم يُوسَّع لشكل تقارير البعثات الجديد
`correlation.py` (محرّك التقاطع القائم، الموجة ٤ من `EXECUTION_PLAN.md`)
مبني على شكل صف `/analyze` القديم (`components_detail`، `retail_price`،
`distribution_channels`...) لا شكل `AgentReport` الجديد. **قرار موثَّق**:
لا محوّل شكل جديد يُبنى — بدل ذلك، خيوط `correlation.py` الجاهزة (إن
حُسبت من مسار قديم ببطاقة منتج) تُمرَّر لـ`silk_market_analyst.py`
كسياق سردي (`extra_context`) **غير قابل للاستشهاد المباشر** — تجنّب
ازدواجية منطق مطابقة يُصان في موضعين. (`silk_market_analyst.py`، تعليق
أعلى الملف.)

### ٤. تسمية `view["deep_research"]` — تفادي تصادم صامت
اكتُشف أثناء بناء الموجة ٤ أن `row["research"]` **موجود أصلاً** — حزمة
وكلاء البحث الثمانية الحتمية (Stage 3، `silk_research.py`، غير مذكورة في
CLAUDE.md رغم كونها كوداً فعلياً يعمل). القسم الجديد سُمِّي `deep_research`
تحديداً لتفادي الخلط الدلالي — راجع تعليق التصميم في `silk_render.py`
أعلى `_deep_research_view()`.

### ٥. ثغرتان حقيقيتان في التزامن — اكتُشفتا وأُصلحتا (لا افتراضيتان)
- **`contextvars` لا تُورَث في خيوط `ThreadPoolExecutor`**: توجيهات لوحة
  إعدادات الوكلاء (`agent_prefs_context`) وحجب إضافات كلود
  (`block_ai_extras`) كانا سيُتجاهَلان بصمت داخل البعثات الإحدى عشرة
  الموازية رغم ضبطهما في الخيط المستدعي. الإصلاح:
  `contextvars.copy_context()` **مستقلة لكل مهمة** قبل `pool.submit`
  (كائن `Context` واحد لا يقبل `.run()` من أكثر من خيط في آن — خطأ ثانٍ
  اكتُشف أثناء إصلاح الأول). `silk_missions.run_all_missions`، اختبار
  انحدار مخصّص في `tests/test_wave6_missions.py`.
- **عدّاد `silk_context._data_counter` يُسرِّب حالة بين اختبارات pytest**:
  contextvar بلا حدود عملية مستقلة (pytest يُشغّل كل الاختبارات على نفس
  الخيط)، فاختبار سابق ترك عدّاداً بأرقام عالية كان يُفعِّل سقف
  `silk_llm_runtime` الكلي زوراً في اختبار لاحق غير مترابط. الإصلاح:
  reset صريح في autouse fixture (`tests/conftest.py`). الإنتاج غير
  متأثر أصلاً — كل طلب `/research` يستدعي `begin_data_counter()` صراحة
  في بداية معالجته.

### ٦. السقف الكلي لحجم البحث — كان موصوفاً بلا تنفيذ فعلي
قسم "الميزانية والأمان" بالتكليف يذكر `SILK_RESEARCH_MAX_LLM_CALLS`
(افتراضي ٤٠) و`SILK_RESEARCH_MAX_TOOL_CALLS` (افتراضي ١٠٠) — لم يكن أي
كود يطبّقهما فعلياً. الآن: `silk_llm_runtime._run_loop` يفحص عدّاد
`data_economics` المشترك (يعمل بفضل إصلاح القرار ٥) عند بداية كل جولة،
ويفرض إنهاءً رشيقاً (جولة أخيرة بلا أدوات، فجوة مُعلَنة) عند التجاوز —
لا كسر، ونفس آلية استنفاد الميزانية المحلية للوكيل الواحد.

### ٧. الفئة (`category`) والسياق الإضافي (`extra_context`) — امتداد صغير متوافق خلفياً
`silk_llm_runtime` يدعم بندَي بيانات وصفية اختياريَّين لكل استشهاد
(`category` لتصنيف تقاطعات المحلل الشامل، `extra_context` لسياق سردي
غير قابل للاستشهاد) — كلاهما اختياري بقيمة افتراضية فارغة؛ البعثات الـ١٢
الأخرى لا تستعملهما فتبقى بلا تغيير سلوكي.

## قرارات نطاق البيانات (لا اختلاق)

### ٨. مراجع L1 الجديدة (ديموغرافيا/موانئ/اتفاقيات) — تغطية حقيقية بفجوات معلنة
- `data/demographics_l1.csv`: **يمدّد** `data/muslim_share.csv` (بذرة
  سِلك المنسَّقة، ٤٩ سوقاً) + `data/worldbank_seed.csv` بدل تكرارهما —
  نسبة المسلمين الإضافية من **نفس مصدر Pew** المُستشهَد به أصلاً
  (`datasets/world-religion-projections`, CC BY 4.0): ٢٢٥/٢٥٠ دولة
  بمصدر حقيقي، البقية فجوة معلنة صراحة (`muslim_pct=""` + ملاحظة).
- `data/ports_l1.csv`: دليل الموانئ العالمي الرسمي (NGA World Port
  Index، عام المجال) عبر `github.com/tayljordan/ports`. الاختيار الآلي
  (أعلى تصنيف حجم NGA) أخطأ لموانئ بارزة (اختار أمستردام لا روتردام،
  داليان لا شنغهاي، بالتيمور لا لوس أنجلوس/لونغ بيتش) — صُحِّح يدوياً
  لأسواق سِلك الـ٣٨ ذات الأولوية فقط (`PRIORITY_PORT_OVERRIDES` في
  `tools/fetch_ports.py`)، بمعرفة عامة موثّقة عن الأهمية التجارية
  النسبية، موسوم صراحة كتصحيح يدوي.
- `data/agreements_l1.csv`: عضوية GCC/GAFTA/OIC/AfCFTA/WTO **لأسواق
  سِلك الـ٣٨ فقط** — لا ٢٥٠ دولة (تعداد دقيق لـ١٦٤+ عضو WTO عالمياً
  يتجاوز ما يمكن تثبيته بثقة دون شبكة موثوقة لكل صف). يميّز `member` عن
  `in_accession` صراحة — لبنان والجزائر وإثيوبيا **ليست** أعضاء WTO
  كاملين (اختبار انحدار مخصّص يحرس افتراض عضوية خاطئ).

### ٩. الحالات الذهبية — فارغة عمداً بصدق (لا مُختلَقة)
`evals/golden_cases.json` = `[]` حرفياً. بناء حالة ذهبية حقيقية (الموجة
٥) يتطلب رقماً مُتحقَّقاً يدوياً من مصدر رسمي حيّ (Comtrade مباشرة) —
هذه البيئة بلا مفتاح Anthropic وبلا وصول شبكي لأي مصدر بيانات حقيقي
(Comtrade/WorldBank/GDELT/WITS محجوبة كلها بسياسة الشبكة). إضافة حالة
الآن تعني إما اختلاق رقم أو تزوير مظهر التحقق — كلاهما ينتهك المبدأ
التأسيسي حرفياً. البنية والمخطط (`evals/golden_cases.schema.json`)
جاهزان بالكامل ومُختبَران؛ التنفيذ الفعلي مؤجَّل — راجع "خطوات أول جلسة
حية" أدناه.

## فجوات معلنة صراحة (الحالة عند تسليم هذا المستند)

| الفجوة | السبب | المتابعة |
|---|---|---|
| `samples/` لم تُعَد توليدها لطبعة البحث العميق (قاعدة §10.6) | لا `ANTHROPIC_API_KEY` حيّ ولا وصول شبكي لمصادر البيانات في هذه البيئة | شغّل "الخطوة ١" في القسم التالي على بيئة بمفتاح حيّ |
| `evals/golden_cases.json` فارغ (صفر حالات) | نفس السبب — لا أرقام يمكن التحقق منها يدوياً هنا | شغّل "الخطوة ٣" أدناه؛ استهدف ٥ حالات كما يطلب التكليف الأصلي |
| تنبيهات مراقبة ما بعد الدخول (`silk_collectors.check_post_entry`) تُسجَّل وتُعاد من `refresh()` فقط — لا تخزين قابل للاستعلام ولا بطاقة لوحة مخصّصة | نطاق واعٍ (الموجة ٤هـ) — الكشف حقيقي ومُختبَر بالكامل؛ السطح الكامل للوحة توسيع طبيعي لاحق | أضف جدولاً في `silk_store`/`silk_storage` + بطاقة في `web/index.html` عند الحاجة الفعلية |
| `silk_evals.run_case()`/`main()` (تشغيل حي لحالة ذهبية) غير مُختبَرين هيرمتياً | يتطلبان شبكة+مفتاح فعليين بتصميم — غير هيرمتيين عمداً، لا يعملان في CI | تُمارَس فعلياً في "الخطوة ٣" أدناه |
| استراتيجية الفرع/الـPR | الموجات ١-٦ كلها على PR/فرع واحد بدل "فرع واحد لكل موجة" (قاعدة CLAUDE.md) | قيد بيئة الجلسة (فرع مُعيَّن واحد)، مُعلَن في وصف كل PR بدل تجاهله |

## خطوات أول جلسة حية — نسخ ولصق

### المتطلبات البيئية

```bash
export ANTHROPIC_API_KEY=sk-ant-...           # إلزامي — بلا هذا يتدهور كل شيء لفجوات معلنة
export SILK_API_KEY=...                       # موصى به بقوة قبل أي نشر عام (بوابة 401 + حارس 503 لمفاتيح غير محمية)
export SEARCH_API_KEY=...                     # اختياري — Serper.dev؛ بلا هذا تتدهور pricing_scout/consumer_culture/channels_importers لفجوات
export COMTRADE_API_KEY=...                   # اختياري — يرفع سقف Comtrade من 4 إلى ~500 نداء/يوم
export GOOGLE_MAPS_API_KEY=...                # اختياري — وكيل الأعمال بالاسم (المسار القديم فقط)
# اختياري: عدّل السقف الكلي لتشغيلة بحث عميق واحدة إن لزم
export SILK_RESEARCH_MAX_LLM_CALLS=40
export SILK_RESEARCH_MAX_TOOL_CALLS=100
```

### الخطوة ١ — أول تشغيلة بحث حقيقية (السوق: نيجيريا)

```bash
pip install -r requirements.txt pytest httpx
python3 -m pytest tests/ -q                     # تأكيد أن الحزمة الحالية خضراء أولاً

python3 -c "
import json
from silk_market_resolver import resolve_market
from silk_missions import deep_research
from silk_market_analyst import analyze_market, to_synthesis_input
from silk_synthesis import synthesize
from silk_ai_judge import write_reviewed_report

ref, _ = resolve_market('Nigeria')
run = deep_research(ref, product='تمور', hs_code='080410')
reports = run['reports']
analyst = analyze_market(ref, 'تمور', reports, hs_code='080410')
analyst_input = to_synthesis_input(analyst)
verdict = synthesize(list(reports.values()), product='تمور', market=ref.name_en,
                      with_ai=True, analyst_assessment=analyst_input)
report = write_reviewed_report(reports, analyst_input['summary'], verdict, 'تمور', ref.name_en)
print('trace:', run['trace_id'])
print('verdict:', (verdict.get('ai') or {}).get('verdict') or verdict.get('verdict'))
print(report['report'][:500] if report['report'] else 'NO REPORT — check ANTHROPIC_API_KEY')
"
```

أو عبر الخادم مباشرة (يطبّق نفس بوابات التوثيق/السقف اليومي):

```bash
uvicorn api:app --host 0.0.0.0 --port 8000 &
curl -X POST http://localhost:8000/research \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $SILK_API_KEY" \
  -d '{"product": "تمور", "market": "Nigeria", "hs_code": "080410", "persist": true}' \
  | python3 -m json.tool > /tmp/nigeria_research.json
```

### الخطوة ٢ — أعِد توليد `samples/`

```bash
python3 -c "
import json
from silk_render import build_view

result = json.load(open('/tmp/nigeria_research.json'))
view = result['view']

from silk_reports import render_docx, render_brief
render_docx(view, 'samples/report_deep_research_latest.docx')
open('samples/brief_deep_research_latest.txt', 'w', encoding='utf-8').write(render_brief(view))
open('samples/analysis_deep_research_latest.json', 'w', encoding='utf-8').write(
    json.dumps(result, ensure_ascii=False, indent=2, default=str))
print('samples/ regenerated — راجع rule §10.6: التزم الملفات مع الـPR')
"
git add samples/
git commit -m "samples: طبعة البحث العميق — بيانات حقيقية (نيجيريا/تمور)"
```

### الخطوة ٣ — أول حالة ذهبية حقيقية

1. اسحب رقماً حقيقياً واحداً مباشرة من Comtrade (لا من نتيجة كلود):
   ```bash
   python3 -c "
   from silk_data_layer import comtrade_trade, primary_value
   recs = comtrade_trade('080410', 566, 2023, flow='M', partner=0)  # 566 = M49 نيجيريا
   total = sum(v for v in (primary_value(r) for r in (recs or [])) if v)
   print('نيجيريا، استيراد التمور HS080410، 2023:', total, 'USD')
   "
   ```
2. أضِف الحالة إلى `evals/golden_cases.json` (مصفوفة فارغة حالياً) وفق
   `evals/golden_cases.schema.json` — كل رقم في `expected` يحمل
   `source_url` حقيقياً (رابط Comtrade نفسه الذي استعلمت منه، لا رابط
   عام):
   ```json
   [{
     "key": "nigeria_dates", "product": "تمور", "market": "نيجيريا",
     "hs_code": "080410",
     "expected": {"trade_import_usd": {"value": <الرقم من الخطوة 1>, "year": 2023,
                  "source_url": "https://comtradeplus.un.org/..."}},
     "verified_at": "<تاريخ اليوم>", "verified_by": "<اسمك>"
   }]
   ```
3. شغّل التقييم وسجّل خط الأساس الأول:
   ```bash
   python3 -m silk_evals --case nigeria_dates
   ```
   (أول تشغيلة: `compare_to_last_score` تعيد `regression: false` دوماً —
   لا أساس سابق للمقارنة؛ `evals/scores.json` يُحدَّث تلقائياً.)
4. التزم `evals/golden_cases.json` و`evals/scores.json` معاً.

### الخطوة ٤ — أول جلسة تنقيح

اتبع `docs/TUNING.md` حرفياً على `pricing_scout` أولاً (الأكثر حساسية
للغة السوق):

```bash
python3 -c "
from silk_market_resolver import resolve_market
from silk_missions import deep_research
ref, _ = resolve_market('Nigeria')
out = deep_research(ref, product='تمور', hs_code='080410',
                     dry_run=True, only_agent='pricing_scout')
print(out['report'].summary)
"
```

اقرأ `data/traces/dryrun-pricing_scout-NGA.jsonl`، صنّف أي فشل عبر جدول
الأعراض/الأسباب في `docs/TUNING.md`، عدّل `silk_missions.MISSIONS
["pricing_scout"]["instructions"]`، أعد الخطوة ٣ (`silk_evals`) لقياس
الأثر على الدرجة قبل الالتزام.

جلستا التنقيح التاليتان المقترحتان أصلاً بالتكليف: **الصين** ثم **مصر**
(تختبر تعليمات "ابحث بلغة السوق" بالعربية فعلياً).
