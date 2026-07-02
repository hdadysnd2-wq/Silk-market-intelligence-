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

**ملاحظة صدق:** النموذج الحالي وُلّد في بيئة **بلا وصول لمصادر البيانات**
(سياسة شبكة تحجب Comtrade)، فقيم المكوّنات فيه `value=null` موسومة بسبب
الفشل — وهذا عرضٌ حقيقي لمبدأ «لا اختلاق»: الفجوة معلنة لا مُخمّنة.
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
