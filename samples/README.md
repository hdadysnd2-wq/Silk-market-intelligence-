# نماذج المخرجات — Output samples

> قاعدة الموجة ١ (من `docs/EXECUTION_PLAN.md`، درس أزمة الإرفاق في
> `docs/VISION.md` §١٠.٦): كل مخرج يُولَّد منه نموذج فعلي يُحفَظ في
> المستودع نفسه مع كل تعديل على طبقة العرض — المراجع يفتح الملف من
> هنا مباشرة، لا قنوات إرفاق.

| الملف | ما هو | كيف وُلّد |
|---|---|---|
| `report_full_latest.docx` | التقرير الكامل Word (§10.3) من نفس النتيجة — خلاصة أولاً + سطر مصدر تحت كل رقم + «حدود هذا التقرير» | `silk_reports.render_docx(build_view(...))` |
| `brief_latest.txt` | المختصر (§10.4) — صفحة «رسالة جوال» | `silk_reports.render_brief(build_view(...))` |
| `analysis_latest.json` | ردّ `POST /analyze` الكامل (تمور × 38 سوقاً، ببطاقة منتج) شاملاً `view` (القالب الموحّد) و`competitive_position` (محرّك التقاطع) — نفس ما ينزّله زر «حمّل JSON» | عبر `TestClient` فوق مسار الـ API الحقيقي |
| `report_full_latest.md` | التقرير الكامل Markdown (Stage 5، §7): قرار الدخول §8 + TAM/SAM/SOM + المنافسة بطبقتيها + التسعير بطبقتيه + SWOT + الشرائح + دليل المورّدين + الاشتراطات + سجل المخاطر + ملحق الأثر | `GET /analyses/{id}/report.md` عبر `TestClient` |
| `research_report_latest.docx` | تقرير `POST /research` (البحث العميق، الموجة ٩ — التنسيق الاحترافي): غلاف بشارة حكم ملوّنة + خلاصة تنفيذية بأطروحة + التقاطعات الخمسة بحساب حسابي صريح + جداول حقيقية (لا قوائم شرطات) + شارات أدلة (✓/◐/○) بدل أرقام ثقة خام + خارطة طريق دخول ٩٠ يوماً + ملحق تقني بكامل أرقام الثقة | `python3 tools/gen_research_sample.py` (نتيجة هولندا×تمور مموّهة، بنفس بنية تشغيلة الحادثة الحية) |

**ملاحظة صدق (تحديث Stage 5):** العينات الحالية وُلّدت في بيئة تحجب مضيفي
البيانات، عبر **مخزن حقائق مبذور + بدائل HTTP موسومة** (نفس عاذف
`tools/stage2c_proof.py` — مؤشرات البنك الدولي من اللقطة الحقيقية المضمّنة،
وتدفقات كومتريد وروابط Serper بدائل موسومة `example.org`/«مخزن الحقائق»).
كل رقم في العينة يحمل مصدره الموسوم — لا اختلاق؛ ولتوليدها ببيانات حية
أعد التشغيل من بيئة متصلة (النشر) بنفس المسار.
لتوليد نموذج ببيانات حية أعد التشغيل من بيئة متصلة:

```bash
python3 - <<'EOF'
import json, dataclasses, silk_engine
res = silk_engine.analyze("تمور", countries=[
    {"iso3": "ARE", "m49": "784"}, {"iso3": "IND", "m49": "356"},
    {"iso3": "GBR", "m49": "826"}], year=2022)
d = lambda o: dataclasses.asdict(o) if dataclasses.is_dataclass(o) else str(o)
open("samples/analysis_latest.json", "w", encoding="utf-8").write(
    json.dumps(res, ensure_ascii=False, indent=2, default=d))
EOF
```
