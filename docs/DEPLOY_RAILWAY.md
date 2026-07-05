# النشر على Railway — Deploying Silk on Railway

خدمة Railway واحدة تشغّل كل شيء: `api.py` يقدّم الـ API **والواجهة معًا** (`web/` تُقدَّم على `/`)، فلا حاجة لخدمة واجهة منفصلة.
*A single Railway service runs everything: `api.py` serves both the API and the dashboard (`web/` mounted at `/`).*

المستودع مهيأ بالكامل — Railway يكتشف `Dockerfile` تلقائيًا ويقرأ `railway.json` (فحص صحة على `/health`، إعادة تشغيل عند الفشل).
*The repo is fully pre-configured: Railway auto-detects the `Dockerfile` and reads `railway.json` (healthcheck on `/health`, restart on failure).*

---

## ١ · إنشاء الخدمة — Create the service

1. افتح [railway.com](https://railway.com) → **New Project** → **Deploy from GitHub repo** → اختر هذا المستودع، فرع `main`.
2. Railway يبني الصورة من `Dockerfile` ويشغّل `uvicorn api:app --host 0.0.0.0 --port $PORT` (متغير `PORT` يُمرَّر تلقائيًا).
3. **Settings → Networking → Generate Domain** للحصول على رابط عام (`https://….up.railway.app`).

## ٢ · القرص الدائم — Persistent volume (مهم · important)

نظام ملفات Railway **زائل**: بدون قرص دائم تضيع قواعد SQLite (`silk.db` سجل التحليلات التراكمي، و`usage.db` عدّاد السقف المدفوع) مع كل نشر جديد.
*Railway's filesystem is ephemeral — without a volume, both SQLite databases are wiped on every redeploy.*

1. على الخدمة: **Right-click → Attach Volume** (أو ⌘K → Volume)، واضبط **Mount Path** إلى `/data`.
2. أضف متغيّري البيئة:

| المتغير | القيمة |
|---|---|
| `SILK_DB` | `/data/silk.db` |
| `SILK_USAGE_DB` | `/data/usage.db` |

> ⚠️ **لا** تركّب القرص على `/app/data` — المجلد `data/` في المستودع يحوي ملفات CSV مرجعية (بذرة HS، `requirements_l1.csv`) سيحجبها القرص الفارغ ويكسر المحلّل والامتثال. القرص على `/data` والمسارات تُوجَّه بالمتغيرين أعلاه.
> *Never mount the volume over `/app/data` — that directory ships seed CSVs the resolver and compliance agent read; an empty volume would shadow them. Mount at `/data` and redirect via the two env vars.*

## ٣ · متغيّرات البيئة — Environment variables (Variables tab)

القائمة الكاملة مع الشرح في `.env.example`. الأساسية للإنتاج:
*Full annotated list in `.env.example`. Production essentials:*

| المتغير | إلزامي؟ | الغرض |
|---|---|---|
| `SILK_API_KEY` | **نعم في الإنتاج** | مصادقة `X-API-Key`؛ بدونه مع أي مفتاح مدفوع → 503 (حارس الموجة ٠) |
| `SILK_PAID_DAILY_CAP` | ينصح به | سقف تفعيلات الطبقات المدفوعة يوميًا (429 عند التجاوز) |
| `SILK_DB` / `SILK_USAGE_DB` | نعم (مع القرص) | توجيه قواعد SQLite للقرص الدائم (§٢ أعلاه) |
| `COMTRADE_API_KEY` | اختياري | يرفع حد Comtrade إلى ~500 طلب/يوم |
| `GOOGLE_MAPS_API_KEY`, `SEARCH_API_KEY` | اختياري | طبقات الإثراء المجانية بحصة |
| `VOLZA_API_KEY`, `EXPLEE_API_KEY`, `ANTHROPIC_API_KEY` | اختياري (مدفوع) | طبقات `/deepen` والحكم الذكي — **لا تضبطها دون `SILK_API_KEY`** |
| `CORS_ORIGINS` | اختياري | فقط إن نُشرت الواجهة على دومين منفصل (Netlify) |

## ٤ · التحقق — Verify

```
https://<domain>/health   → {"status":"ok"}   (+ تحذير إن وُجد مفتاح مدفوع بلا SILK_API_KEY)
https://<domain>/          → الواجهة (اترك حقل «رابط الباك-إند» فارغًا — نفس الخدمة)
```

جرّب تحليلًا من الواجهة ثم أعد النشر (Redeploy) وتأكد أن التحليل ما زال في القائمة — هذا يثبت أن القرص الدائم يعمل.
*Run one analysis, redeploy, and confirm it still appears in the list — that proves the volume works.*

## ملاحظات — Notes

- كل push إلى `main` ينشر تلقائيًا (افتراضي Railway؛ يمكن تقييده بـ **Check Suites** ليننتظر نجاح CI).
- ترحيل من Render: هذا الدليل يحلّ محل `render.yaml` (حُذف). لا ترحيل بيانات تلقائي — إن كانت لديك `silk.db` قديمة على قرص Render انسخها إلى قرص Railway عبر `railway ssh` / `scp` قبل إيقاف الخدمة القديمة، فسجل التحليلات تراكمي ولا يُحذف (قاعدة المستودع).
- *Migrating from Render: this guide replaces the deleted `render.yaml`. No automatic data migration — copy any existing `silk.db` from the old Render disk onto the Railway volume before decommissioning; the analyses track record is cumulative and must never be lost.*
