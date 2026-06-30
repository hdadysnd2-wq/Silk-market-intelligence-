# منصة سِلك لذكاء الأسواق — Silk Market Intelligence

> نظام **متعدد الوكلاء** لتحليل أسواق التصدير/الاستيراد لشركة سِلك (منتجات سعودية)،
> يجمّع ويحلّل **بيانات حقيقية فقط** ويوسم كل معلومة بمصدرها ودرجة ثقتها.

A multi-agent system that ranks export markets for Saudi products using **real public data only**
(UN Comtrade + World Bank). Every value is tagged with its source and a confidence score.

---

## المبدأ التأسيسي · Founding principle

النظام **لا يخلق بيانات** — بل يجمّع ويحلّل المتاح آلياً. الوكيل بلا مصدر حقيقي = خيال مقنع.
عند فشل المصدر، تُعاد قيمة فارغة موسومة (`value=None, confidence=0.0`) مع تحذير — **ولا يُخترع رقم**.

The system never fabricates data. On a source failure it returns a provenance-tagged empty value
(`DataPoint(value=None, confidence=0.0, note=...)`) and logs a warning — it never invents a number.

---

## البنية · Architecture

| الملف · File | الوظيفة · Role |
|---|---|
| `silk_data_layer.py` | الطبقة الأساس: ربط UN Comtrade + World Bank، وتعريف `DataPoint` (المصدر/الثقة). |
| `silk_data_layer_v2.py` | + القوة الشرائية (PPP) + المنافسون بالاسم وحصصهم. |
| `silk_hs_resolver.py` | تصنيف HS تلقائي من اسم المنتج (عربي/إنجليزي) عبر `difflib` + الكلمات المفتاحية. |
| `silk_agents.py` | بنية الوكلاء: مدير + 3 وكلاء باحثين (تجارة/اقتصاد/منافسة) + لجنة تحكيم. |
| `silk_market_ranker.py` | محرّك الترتيب: يقارن عدة دول لرمز HS ويرتّبها بنقاط شفّافة قابلة للتدقيق. |
| `silk_engine.py` | **المحرّك الكامل**: يقبل أي منتج بالاسم → يصنّفه → يرتّب أسواقه. ابدأ من هنا. |
| `silk_trends_agent.py` | وكيل اختياري: إشارة الطلب من Google Trends (`pytrends`) مع موسمية. يتدهور بأمان بلا الحزمة/الشبكة. |
| `silk_tariffs_agent.py` | وكيل اختياري: التعريفة الجمركية المطبّقة (%) من World Bank WITS. لا يخمّن نسبة عند الفشل. |
| `silk_quality.py` | فحوص جودة (stdlib): يوسم الصفوف بتنبيهات (حجم شبه صفري، نواقص، قيم خارج المدى) — **لا يغيّر أرقامًا**. |
| `silk_storage.py` | تخزين النتائج في SQLite (stdlib): `save_analysis`/`get_analysis`/`list_analyses`. ملف `.db` متجاهَل في git. |
| `app.py` | واجهة Streamlit اختيارية فوق المحرّك (تُستورد Streamlit بكسل داخليًا). |
| `data/hs_codes.csv` | بذرة رموز HS6 الحقيقية لمنتجات سِلك (عربي/إنجليزي + كلمات مفتاحية). |

كل قرار من المنصة **أوّلي لا نهائي**: تصفّي الأسواق وترتّبها، ثم تُستثمر الدراسة العميقة على المرشّحين فقط.

---

## المصادر · Data sources (no API key)

- **UN Comtrade** — `https://comtradeapi.un.org/public/v1/preview/C/A/HS` — الاستيراد/التصدير بالـ HS Code.
- **World Bank** — `https://api.worldbank.org/v2/country/{iso3}/indicator/{code}` — الدخل، PPP، السكان.

---

## التشغيل · Quick start

```bash
pip install -r requirements.txt
python3 silk_engine.py        # عرض توضيحي: يصنّف منتجاً ويرتّب أسواقه
```

> ملاحظة: التشغيل يتطلب وصولاً للإنترنت ليجلب البيانات الحقيقية. بلا إنترنت يعمل الكود لكن يُظهر
> "لا بيانات / فشل الجلب" بدل أرقام مُختلَقة (إثباتاً لسلامة المبدأ).

---

## طبقات إضافية · Extra layers

طبقات اختيارية فوق المحرّك، **مطفأة افتراضيًا** حتى لا تتغيّر السلوك القديم ولا الاختبارات:

```python
from silk_engine import analyze
analyze("تمور",
        with_trends=True,    # Google Trends (يتطلب pytrends؛ بدونه None موسوم)
        with_tariffs=True,   # WITS applied tariff %
        persist=True,        # يحفظ في SQLite ويضيف analysis_id
        db_path="data/silk.db",
        check_quality=True)  # يضيف quality_flags (تنبيهات فقط، لا يغيّر أرقامًا)
```

- `with_trends` / `with_tariffs` **سياق إضافي فقط** — يُرفقان `row['trends']` و `row['tariff']` ولا يغيّران `total_score`.
- جميع الطبقات تتدهور بأمان بلا شبكة (قيمة `None` موسومة بمصدرها، بلا اختلاق رقم).

### تشغيل الواجهة · Run the UI

```bash
pip install streamlit            # حزمة اختيارية
streamlit run app.py
```

الحزم الاختيارية: `streamlit` (للواجهة) و `pytrends` (لوكيل الاتجاهات). النواة تعمل وتُستورد بدونهما.

---

## مهارة ponytail المثبّتة · Installed skill

المشروع مهيّأ لتفعيل إضافة **[ponytail](https://github.com/DietrichGebert/ponytail)** تلقائياً
عبر `.claude/settings.json` (تُسجّل السوق وتفعّل `ponytail@ponytail`). تشجّع على أقل كود ممكن
(YAGNI، المكتبة القياسية أولاً). عند فتح المشروع في Claude Code قد يُطلب منك الموافقة على تثبيتها،
أو ثبّتها يدوياً:

```
/plugin marketplace add DietrichGebert/ponytail
/plugin install ponytail@ponytail
```

أوامرها: `/ponytail-review` · `/ponytail-audit` · `/ponytail-debt` · `/ponytail-gain` · `/ponytail-help`.

---

## الحالة · Status

**مُنجَز:** النواة (طبقة بيانات + مُصنّف HS + وكلاء + مُرتّب + محرّك) + طبقات: Google Trends،
الرسوم الجمركية (WITS)، تخزين SQLite، فحوص الجودة، وواجهة Streamlit.

**خطوات لاحقة مقترحة:** حل FAOSTAT (الاستهلاك للفرد)، لفّ الوكلاء بـ CrewAI، واجهة FastAPI،
ودمج المصادر المدفوعة (Volza/explee) للأسواق الناجية من التصفية الأولية فقط.
