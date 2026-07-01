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
| `silk_faostat_agent.py` | وكيل اختياري: نصيب الفرد من العرض الغذائي (FAOSTAT). يتدهور بأمان عند المصادقة/الفشل (لا يخمّن رقمًا). |
| `silk_production_agent.py` | **المجموعة أ · Group A**: الإنتاج المحلي — FAOSTAT (QCL، أطنان) مع رجوع لبحث الويب كسياق للسلع غير الزراعية (لا يُستخرج رقم من نص حر). |
| `silk_marketsize_agent.py` | **المجموعة أ · Group A**: حجم السوق بالاستهلاك الظاهري (إنتاج + استيراد − تصدير، أطنان)؛ رجوع لمؤشّر قيمة الاستيراد (دولار) موسوم كجزئي؛ لا اختلاق. |
| `silk_cities_agent.py` · `data/world_cities.csv` | **المجموعة ب · Group B**: أكبر مدن السوق (إحداثيات + سكان) من مرجع بصيغة simplemaps (بذرة منسّقة؛ أسقِط ملف simplemaps الكامل للتغطية الكاملة). لطبقة الخريطة ومراكز الطلب. |
| `silk_religion_agent.py` · `data/religion_reference.csv` | **المجموعة ب · Group B**: الديانة الغالبة وحصتها التقريبية (مرجع Pew، مؤرّخ/تقريبي) لملاءمة المنتج والتوقيت. |
| `silk_currency_agent.py` | **المجموعة ب · Group B**: إشارات مخاطر العملة — التضخم وسعر الصرف الرسمي (البنك الدولي، حيّ)؛ التصنيف الائتماني غير مُختلق (يحتاج مصدراً خارجياً). |
| `silk_competitors_agent.py` | **المجموعة ج · Group C**: العلامات/المنتجات المنافسة عبر بحث ويب ديناميكي؛ بلا مفتاح => None، لا أسماء مُختلقة. |
| `silk_distribution_agent.py` | **المجموعة ج · Group C**: أكبر سلاسل التجزئة/الموزّعين + منصّات التجارة الإلكترونية المهيمنة (بحث ويب ديناميكي). |
| `silk_bestsellers_agent.py` | **المجموعة ج · Group C**: ترتيب الأكثر مبيعاً عبر **مُشغّل Apify مرخّص** (لا سكرابينغ مباشر بكودنا — قد يخالف ToS)؛ بلا `APIFY_API_TOKEN` => None موسوم بالقيد. |
| `silk_cache.py` | ذاكرة تخزين مؤقت على القرص لطلبات GET (stdlib؛ `requests` بكسل). يُستخدم شفّافًا في طبقة البيانات. |
| `api.py` | واجهة REST عبر FastAPI فوق المحرّك (تُستورد FastAPI بكسل؛ `app=None` بدونها). |
| `app.py` | واجهة Streamlit اختيارية فوق المحرّك (تُستورد Streamlit بكسل داخليًا). |
| `tools/fetch_hs_codes.py` | أداة تشغيل: تجلب مرجع HS من Comtrade وتوسّع `data/hs_codes.csv` برموز حقيقية. |
| `Dockerfile` · `.github/workflows/ci.yml` | تعبئة الخدمة (Docker) + تكامل مستمر (CI) يشغّل اختبارات الدخان. |
| `data/hs_codes.csv` | جدول التصنيف للمُصنّف: **5,627 صفاً** = بذرة منسّقة (عربي/إنجليزي + كلمات مفتاحية) + كامل رموز HS6 المدموجة. |
| `data/hs_reference.csv` | المرجع الكامل الخام من Comtrade (6,940 رمزاً، كل المستويات 2/4/6) للتدقيق والتوسيع. |

كل قرار من المنصة **أوّلي لا نهائي**: تصفّي الأسواق وترتّبها، ثم تُستثمر الدراسة العميقة على المرشّحين فقط.

---

## المصادر · Data sources — الطبقات التسع · the 9 layers

كل المصادر **موصولة** (`wired`). المجانية تعمل بلا مفتاح (أو بمفتاح اختياري يرفع الحد)؛
المدفوعة تتطلب مفتاحًا وإلا تتدهور بأمان إلى `value=None` بلا اختلاق. خريطة الحالة الحيّة عبر `GET /sources`.

All layers are wired. Free layers work keyless (or with an optional key that raises limits);
paid layers require a key and otherwise degrade gracefully to `value=None` (no fabrication).
Live status map: `GET /sources`.

| # | الطبقة · Layer | النوع · Type | الوحدة · Module | مفتاح البيئة · Key env |
|---|---|---|---|---|
| 1 | UN Comtrade | مجاني · free | `silk_data_layer.py` | — (اختياري `COMTRADE_API_KEY`) |
| 2 | World Bank | مجاني · free | `silk_data_layer.py` | — (لا مفتاح) |
| 3 | FAOSTAT | مجاني · free | `silk_faostat_agent.py` | — (اختياري) |
| 4 | WITS (الرسوم · tariffs) | مجاني · free | `silk_tariffs_agent.py` | — (لا مفتاح) |
| 5 | Google Trends | مجاني · free | `silk_trends_agent.py` | — (`pip install pytrends`) |
| 6 | Google Maps | مجاني · free | `silk_maps_agent.py` | `GOOGLE_MAPS_API_KEY` |
| 7 | Web Search (Serper) | مجاني · free | `silk_websearch_agent.py` | `SEARCH_API_KEY` |
| 8 | Volza | مدفوع · paid | `silk_volza_agent.py` | `VOLZA_API_KEY` |
| 9 | explee | مدفوع · paid | `silk_explee_agent.py` | `EXPLEE_API_KEY` |

> النهايات المرجعية · reference endpoints:
> **UN Comtrade** `https://comtradeapi.un.org/public/v1/preview/C/A/HS` ·
> **World Bank** `https://api.worldbank.org/v2/country/{iso3}/indicator/{code}`.

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

- `with_trends` / `with_tariffs` / `with_faostat` **سياق إضافي فقط** — يُرفقون `row['trends']` / `row['tariff']` / `row['faostat']` ولا يغيّرون `total_score`.
- `with_maps` / `with_volza` / `with_explee` يُرفقون `row['maps']` / `row['volza']` / `row['explee']` لأعلى الأسواق؛ و`with_websearch` يُرفق `result['websearch']` على المستوى الأعلى. كلّها **إضافية** لا تغيّر `total_score`.
- `with_localprice` يُرفق `row['localprice']` (قوائم مسعّرة فعلية، مع `is_best_seller` عند توفّر شارة حقيقية من المزوّد — لا يوجد رقم "عدد المبيعات" علني من أي منصة). مع `own_price` يُرفق أيضاً `row['price_comparison']`: مقارنة سعرك بالقوائم المرصودة (نسبة كونك أرخص من السوق) — مقارنة سعرية لا مقارنة مبيعات.
- `with_market_size` (**المجموعة أ · Group A**) يُرفق `row['production']` (إنتاج FAOSTAT بالأطنان، أو أدلة بحث بلا رقم مُختلق) و`row['market_size']` (الاستهلاك الظاهري = إنتاج + استيراد − تصدير بالأطنان؛ وإلا مؤشّر قيمة الاستيراد بالدولار موسوم كجزئي). **إضافي** لا يغيّر `total_score`.
- `with_demographics` (**المجموعة ب · Group B**) يُرفق `row['cities']` (أكبر المدن بإحداثياتها وسكانها)، `row['religion']` (الديانة الغالبة، تقريبي/مؤرّخ من Pew)، و`row['currency_risk']` (تضخم وسعر صرف من البنك الدولي؛ التصنيف الائتماني غير مُختلق). المدن والديانة مرجع محلي فيعملان بلا شبكة؛ إشارات العملة حيّة وتتدهور بأمان. **إضافي** لا يغيّر `total_score`.
- `with_competition` (**المجموعة ج · Group C**) يُرفق `row['competitors_web']` و`row['distribution_channels']` و`row['ecommerce']` (بحث ويب ديناميكي، يتطلب `SEARCH_API_KEY`) و`row['bestsellers']` (ترتيب الأكثر مبيعاً عبر مُشغّل Apify مرخّص، يتطلب `APIFY_API_TOKEN` + `APIFY_BESTSELLERS_ACTOR` — لا سكرابينغ مباشر). الكل **إضافي** لا يغيّر `total_score`، ويتدهور بأمان بلا مفاتيح/شبكة.
- المدفوعان (Volza, explee) يتطلبان مفتاحًا؛ بدونه يُرجعان `value=None, confidence=0.0` بلا اختلاق.
- جميع الطبقات تتدهور بأمان بلا شبكة (قيمة `None` موسومة بمصدرها، بلا اختلاق رقم).

### تشغيل الواجهة · Run the UI

```bash
pip install streamlit            # حزمة اختيارية
streamlit run app.py
```

الحزم الاختيارية: `streamlit` (للواجهة) و `pytrends` (لوكيل الاتجاهات). النواة تعمل وتُستورد بدونهما.

### تشغيل الخدمة (API) · Run the backend (API)

واجهة REST عبر FastAPI فوق المحرّك. تُستورد `api.py` بلا الحزمة (`app=None`)؛ التشغيل يحتاج `fastapi`+`uvicorn`.

```bash
pip install fastapi uvicorn      # حزم اختيارية
uvicorn api:app --host 0.0.0.0 --port 8000
# أو مباشرة:  python3 api.py
```

عبر Docker · with Docker:

```bash
docker build -t silk-api .
docker run -p 8000:8000 silk-api
```

النهايات · Endpoints:

| Method · Path | الوظيفة · Role |
|---|---|
| `GET /health` | حالة الخدمة + توفّر الحزم الاختيارية. |
| `GET /sources` | خريطة حالة الطبقات التسع (`name, type, wired, key_env, key_present`). |
| `GET /resolve/{name}` | يصنّف اسم منتج إلى HS6 (مع المصدر/الثقة). |
| `POST /analyze` | يشغّل `analyze` كاملًا (`{product, year, with_trends, with_tariffs, with_faostat, with_maps, with_websearch, with_localprice, own_price, with_volza, with_explee, persist}`). |
| `GET /analyses` | يسرد التحليلات المحفوظة. |
| `GET /analyses/{id}` | يعيد تحليلًا محفوظًا، أو 404. |

**CI** (`.github/workflows/ci.yml`): يثبّت `requirements.txt` (بما فيها `fastapi`/`uvicorn`) + `pytest` ويشغّل `python -m pytest tests/ -q` عند كل push / PR.

### النشر · Deployment (Railway)

النشر على **Railway** (بدّل Render — `railway.toml` يحل محل `render.yaml`). خدمتان من نفس المستودع:

1. Railway → **New Project** → **Deploy from GitHub repo** (يقرأ `railway.toml` تلقائيًا) → فرع `main`.
   - خدمة **web**: Start command من `railway.toml`/`Procfile` (`uvicorn api:app`)، تقدّم الواجهة + الـ API معًا (`api.py` يضيف `web/` على `/`).
   - خدمة **worker** (أضِفها كخدمة ثانية بنفس المستودع، Start command = سطر `worker:` في `Procfile`): تُنفّذ التحليلات بالخلفية (طابور RQ عبر Redis).
2. أضف من لوحة Railway: قالب **Postgres** (يُعبّئ `DATABASE_URL` تلقائيًا لكلتا الخدمتين) وقالب **Redis** (يُعبّئ `REDIS_URL`).
   ⚠️ هذي القوالب **"غير مُدارة"** رسميًا حسب توثيق Railway — النسخ الاحتياطي والمراقبة مسؤوليتك؛ فعّل **Backups** اليدوية من اليوم الأول.
3. متغيرات بيئة إضافية على كلتا الخدمتين: `ANTHROPIC_API_KEY`، وأي مفاتيح مصادر اختيارية (`.env.example`). بلا `DATABASE_URL`/`REDIS_URL` يعمل النظام محليًا بـ SQLite + كاش قرص (نفس سلوك dev القديم، بلا تعطّل).
4. تحقّق من `/<الرابط>/health` → `{"status":"ok", "deps": {...}}`.
5. راقب لوحة استهلاك Railway أسبوعيًا أول شهر — الفوترة حسب الاستهلاك الفعلي لا سعر ثابت.

> Docker: `Dockerfile` الموجود يعمل أيضًا لو فضّلت نشرًا آخر يقرأ صورة حاويات مباشرة.

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

**مُنجَز:** النواة (طبقة بيانات + مُصنّف HS + وكلاء + مُرتّب + محرّك) + طبقات Google Trends،
الرسوم الجمركية (WITS)، FAOSTAT، فحوص الجودة، تخزين SQLite، وذاكرة تخزين مؤقت + واجهتا Streamlit
و**FastAPI** + تعبئة Docker وتكامل مستمر (CI). اختبارات الدخان: 10/10.

**خطوات لاحقة مقترحة:** اختبار حيّ شامل ببيانات الإنترنت، توسيع `hs_codes.csv` للقائمة الكاملة عبر
`tools/fetch_hs_codes.py`، لفّ الوكلاء بـ CrewAI، ودمج المصادر المدفوعة (Volza/explee) للأسواق الناجية
من التصفية الأولية فقط.
