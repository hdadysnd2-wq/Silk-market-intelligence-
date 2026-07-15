"""واجهة REST لمنصّة سِلك — FastAPI service exposing the Silk engine.

Lazy-imports FastAPI/pydantic inside create_app() so that `import api` works
offline and even when fastapi is absent (founding principle: graceful degrade,
never crash, never fabricate). Module-level `app` is None when fastapi is missing.

Run:  python3 api.py   (needs `pip install fastapi uvicorn`).
"""
import dataclasses
import hmac
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

_PIP_HINT = "FastAPI/uvicorn not installed — run: pip install fastapi uvicorn"


def _to_jsonable(obj: object) -> object:
    """حوّل DataPoint وغيره إلى JSON — make DataPoints/dataclasses JSON-safe."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def _index_search(q: str = "", limit: int = 20) -> list[dict]:
    """فهرس بحث المنتجات للوحة المعلومات — product search index for the dashboard
    combobox. Returns [{"name", "hs", "analyzed"}]; empty q -> a small default
    list. Pure/offline (the HS CSV load is lru_cached). Never fabricates.
    """
    import silk_hs_resolver as resolver

    def _row(r: dict) -> dict:
        return {"name": r.get("name_ar") or r.get("name_en"),
                "hs": r.get("hs_code"), "analyzed": False}

    rows = resolver.load_hs_codes()
    q = (q or "").strip().lower()
    if not q:
        return [_row(r) for r in rows[:12]]

    out: list[dict] = []
    for r in rows:
        hay = " ".join([
            (r.get("name_ar") or ""), (r.get("name_en") or ""),
            (r.get("keywords") or ""),
        ]).lower()
        if q in hay:
            out.append(_row(r))
        if len(out) >= max(1, limit):
            break
    return out


def _cors_origins() -> list[str]:
    """أصول CORS المسموحة — allowed origins from CORS_ORIGINS; [] = same-origin only.

    الموجة ٠: الافتراضي لم يعد "*" — بلا ضبط صريح لا يُركَّب CORS إطلاقاً
    (الواجهة تُقدَّم من نفس الأصل). Wildcard requires an explicit opt-in.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if not raw:
        return []
    if raw == "*":
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


def _api_key_expected() -> str:
    """مفتاح الخدمة المتوقع — the API key required by /analyze ('' = auth off).

    الموجة ٠: يُضبط SILK_API_KEY في الإنتاج فيصير كل طلب /analyze بلا ترويسة
    X-API-Key مطابقة = 401 **قبل تشغيل أي وكيل**. غير مضبوط => وضع تطوير مفتوح.
    """
    return os.environ.get("SILK_API_KEY", "").strip()


# الطبقات المدفوعة الخاضعة للسقف — paid layers counted against the daily cap.
_PAID_FLAGS = ("with_localprice", "with_volza", "with_explee", "with_ai")

# مفاتيح البيئة المدفوعة — the paid-provider key env vars (503 guard below).
_PAID_KEY_ENVS = ("LOCALPRICE_API_KEY", "VOLZA_API_KEY",
                  "EXPLEE_API_KEY", "ANTHROPIC_API_KEY")


def _unprotected_paid_keys() -> list[str]:
    """مفاتيح مدفوعة بلا مصادقة — paid keys present while SILK_API_KEY is unset.

    الإغلاق المسبق قبل الموجة ٤: مفتاح مدفوع في البيئة + مصادقة معطّلة =
    خدمة عامة تصرف رصيداً مدفوعاً لأي مجهول. القاعدة: وضع التطوير المفتوح
    مشروع فقط عند غياب المفاتيح المدفوعة **كلها**؛ وجود أي منها يوجب ضبط
    SILK_API_KEY وإلا رُفض تشغيل الطبقات المدفوعة بـ503 وسبب واضح.
    """
    if _api_key_expected():
        return []
    return [k for k in _PAID_KEY_ENVS if os.environ.get(k, "").strip()]


def create_app():
    """أنشئ تطبيق FastAPI — build the FastAPI app, or raise if fastapi is absent."""
    try:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(_PIP_HINT) from exc

    import silk_engine
    import silk_hs_resolver
    import silk_storage
    import silk_usage

    app = FastAPI(title="Silk Market Intelligence API",
                  description="Real public-data export-market analysis "
                              "(UN Comtrade + World Bank). Preliminary, never fabricated.")

    # Stage 2A: حمّل مفاتيح المصادر المحفوظة إلى بيئة العملية عند الإقلاع —
    # متغير بيئة النشر يفوز (overwrite=False). Best-effort: فشلها لا يمنع الإقلاع.
    try:
        import silk_store as _store
        _store.migrate()
        _store.load_settings_into_env()
    except Exception as _e:  # noqa: BLE001
        log.debug("settings bootstrap skipped: %s", _e)

    # القرص الدائم: هيّئ قاعدة التحليلات ومجلد ذاكرة الطلبات على مساراتهما
    # الموجَّهة (SILK_DB/SILK_CACHE_DIR أو SILK_DATA_DIR على Railway volume)
    # عند الإقلاع — إنشاء المجلدات إن غابت، فلا يفاجأ أول طلب بكتابة فاشلة.
    # Persistent volume: init the analyses DB and cache dir at startup so the
    # first request never trips over a missing directory. Best-effort.
    try:
        silk_storage.init_db()
        import silk_cache as _cache
        os.makedirs(_cache._cache_dir(), exist_ok=True)
    except Exception as _e:  # noqa: BLE001
        log.warning("storage bootstrap failed (continuing): %s", _e)

    # التحديث الدوري داخل العملية (SILK_REFRESH_HOURS) — قرص Railway يُركَّب
    # على خدمة واحدة، فالمُجدول خيط خلفي هنا لا خدمة cron منفصلة. معطّل بلا
    # المتغير — الاختبارات والتطوير لا تتأثر. In-process scheduled refresh.
    try:
        import silk_collectors
        silk_collectors.start_scheduler()
    except Exception as _e:  # noqa: BLE001
        log.warning("refresh scheduler not started: %s", _e)

    # CORS (الموجة ٠): الافتراضي صار **نفس الأصل فقط** (الواجهة تُقدَّم من نفس
    # الخدمة فلا تحتاج CORS). للواجهات المنفصلة (Netlify) اضبط CORS_ORIGINS
    # بقائمة أصول مفصولة بفواصل؛ "*" لم يعد افتراضياً ويتطلب ضبطاً صريحاً.
    allow = _cors_origins()
    if allow:
        app.add_middleware(CORSMiddleware, allow_origins=allow,
                           allow_methods=["*"], allow_headers=["*"])

    # ترويسات أمان على كل ردّ (L-2) — security headers on every response.
    # CSP خطّ أساس يسمح بأنماط/سكربتات الصفحة المضمّنة وخطوط Google (الواجهة
    # ملف واحد بأنماط وسكربت مضمّنين)؛ التشديد (nonces / خط ذاتي الاستضافة =
    # L-3) لاحقاً. nosniff يمنع تخمين نوع المحتوى؛ Referrer-Policy يحدّ التسريب.
    # الخطوط صارت مستضافة ذاتياً (task 12) — لا مضيف خطوط خارجي في السياسة.
    _CSP = ("default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self'; "
            "base-uri 'self'; frame-ancestors 'none'")

    @app.middleware("http")
    async def _security_headers(request, call_next):  # noqa: ANN001, ANN201
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers.setdefault("Content-Security-Policy", _CSP)
        return resp

    class ProductCard(BaseModel):
        """بطاقة المنتج (الموجة ٤، vision §2) — اختيارية، تفعّل محرّك التقاطع."""
        cost_per_unit: float
        unit: str | None = None
        tier: str | None = None            # premium|standard|economy
        monthly_capacity: float | None = None
        shipping_per_unit: float | None = None  # افتراض شحن معلَن قابل للتعديل
        certifications: list[str] | None = None  # مثال: HALAL, ISO22000, SFDA

    class AnalyzeRequest(BaseModel):
        """طلب تحليل منتج (المسار العادي) — analyze request body.

        الموجة ٢: حقول الطبقات المدفوعة أُزيلت نهائياً من هذا النموذج —
        إرسالها يُتجاهَل بنيوياً (pydantic يسقط الحقول الزائدة)، فالمسار
        العادي **يستحيل** أن يشغّل طبقة مدفوعة. التعميق عبر POST /deepen.
        """
        product: str
        year: int | None = None
        with_trends: bool = False
        with_tariffs: bool = False
        with_faostat: bool = False
        with_maps: bool = False
        with_websearch: bool = False
        with_competitors: bool = False
        with_channels: bool = False
        with_importers: bool = False
        with_requirements: bool = False
        with_trend: bool = False          # مدى السنوات — multi-year import trend
        trend_span: int = 5
        product_card: ProductCard | None = None
        hs_code: str | None = None
        markets: list[str] | None = None  # ISO3s لتضييق المرشّحين؛ فارغ = كل الأسواق
        # P3: توجيهات درج «إعدادات الوكلاء» — {agent_key: {on: bool, cmd: str}}.
        # تُطبَّع شكلياً في _clean_agent_prefs؛ الأمر يوجّه تركيز برومبتات
        # كلود حصراً داخل العزل — لا يغيّر رقماً ولا يصل وكيل بيانات.
        agent_prefs: dict | None = None
        persist: bool = False

    class DeepenRequest(BaseModel):
        """طلب تعميق (المسار المدفوع) — the /deepen request body (wave 2).

        المسار الوحيد القادر على تفعيل الطبقات المدفوعة، ويعمل داخل
        silk_context.deepen_context() فيسمح حارس BaseAgent البنيوي بالتنفيذ.
        """
        product: str
        year: int | None = None
        with_trends: bool = False
        with_tariffs: bool = False
        with_faostat: bool = False
        with_maps: bool = False
        with_websearch: bool = False
        with_localprice: bool = False
        own_price: float | None = None
        with_volza: bool = False
        with_explee: bool = False
        with_ai: bool = False
        with_competitors: bool = False
        with_channels: bool = False
        with_importers: bool = False
        with_requirements: bool = False
        with_trend: bool = False          # مدى السنوات — multi-year import trend
        trend_span: int = 5
        product_card: ProductCard | None = None
        hs_code: str | None = None
        persist: bool = False

    def _json(payload: object):
        """رد JSON آمن للـ DataPoint — JSONResponse with DataPoint-safe payload."""
        return JSONResponse(content=_to_jsonable(payload))

    def _view(result: dict) -> dict:
        """القالب الموحّد (§10.1) — attach the canonical view (never crashes)."""
        try:
            from silk_render import build_view
            return build_view(result)
        except Exception as e:  # noqa: BLE001 — العرض لا يُسقط التحليل
            log.warning("view build failed: %s", e)
            return {"error": f"view error: {type(e).__name__}: {e}"}

    @app.get("/health")
    def health():
        """فحص الصحّة — liveness plus optional-dep availability flags."""
        deps = {}
        for name in ("fastapi", "uvicorn", "pytrends", "streamlit", "requests"):
            try:
                __import__(name)
                deps[name] = True
            except Exception:  # noqa: BLE001
                deps[name] = False
        health = {"status": "ok", "deps": deps}
        # P5: شفافية المصادر — أي طبقة قوقل/كلود فعّالة الآن ولماذا لا.
        # وجود/غياب فقط، لا قيم مفاتيح ولا نداءات حية (التحقيق العميق في
        # /diagnostics المحروس).
        from silk_websearch_agent import search_key as _sk
        _claude_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
        if not _claude_key:
            _claude = "off — ANTHROPIC_API_KEY غير مضبوط"
        elif _unprotected_paid_keys():
            _claude = ("blocked — ANTHROPIC_API_KEY بلا SILK_API_KEY؛ "
                       "اضبط SILK_API_KEY لتفعيل حكم كلود وطبقاته")
        else:
            _claude = "on"
        health["sources"] = {
            "comtrade": ("key" if os.environ.get("COMTRADE_API_KEY", "").strip()
                         else "preview — بلا COMTRADE_API_KEY (حدّ معدل منخفض؛ "
                              "أضِف المفتاح المجاني)"),
            "world_bank": "on — بلا مفتاح",
            "google_trends": "on — pytrends بلا مفتاح (حصة قوقل محدودة)",
            "google_search_serper": ("on" if _sk() else
                                     "off — SEARCH_API_KEY/SERPER_API_KEY غائب"),
            "google_maps": ("on" if os.environ.get(
                "GOOGLE_MAPS_API_KEY", "").strip()
                else "off — GOOGLE_MAPS_API_KEY غائب"),
            "claude": _claude,
        }
        # جهوزية البحث العميق (/research) — بلاغ حي: كلود شرط تشغيل هناك لا
        # تحسين اختياري؛ حقل صريح هنا كي يتحقق المشغّل قبل أي طلب حي، لا
        # بعد تسليم هيكل فارغ (نفس فحص _research_readiness دون حجز ميزانية).
        _rr_ready, _rr_reason = _research_readiness()
        health["research_ready"] = _rr_ready
        if not _rr_ready:
            health["research_ready_reason"] = _rr_reason
        # القرص الدائم: المسارات المحلولة فعلاً لكل مخزن — للتحقق بعد النشر أن
        # كل شيء يكتب للقرص (persistent=true عندما يقع المسار تحت SILK_DATA_DIR
        # أو وُجّه بمتغير صريح). Resolved storage paths for volume verification.
        try:
            import silk_cache as _cache
            import silk_store as _fact_store
            import silk_usage as _usage
            _base = os.environ.get("SILK_DATA_DIR", "").strip()
            health["storage"] = {
                "data_dir": _base or None,
                "analyses_db": silk_storage._db_path(),
                "fact_store_db": _fact_store._db_path(),
                "usage_db": _usage._db_path(),
                "cache_dir": _cache._cache_dir(),
            }
        except Exception as _e:  # noqa: BLE001 — تشخيص لا شرط
            log.debug("storage health section skipped: %s", _e)
        unprotected = _unprotected_paid_keys()
        if unprotected:
            health["warnings"] = [
                "paid keys present without SILK_API_KEY ("
                + ", ".join(unprotected)
                + ") — paid layers will refuse with 503 until SILK_API_KEY "
                  "is set (or the paid keys are removed)"]
        return health

    @app.get("/resolve/{name}")
    def resolve(name: str, request: Request):
        """صنّف اسم منتج إلى HS6 — resolve a product name to an HS6 DataPoint."""
        _rate_limit(request)   # قراءة رخيصة لكنها ليست مجانية بلا حدود
        dp = silk_hs_resolver.resolve(name)
        return _json({"hs_code": dp.value, "confidence": dp.confidence,
                      "note": dp.note, "source": dp.source,
                      "retrieved_at": dp.retrieved_at})

    @app.get("/index")
    def index(request: Request, q: str = "", limit: int = 20):
        """فهرس المنتجات للبحث — product search index for the dashboard combobox.

        limit مُقيَّد إلى [1..100] (M0): قيمة ضخمة/سالبة لا تُمرَّر للبحث كما هي.
        """
        _rate_limit(request)
        return _json(_index_search(q, max(1, min(int(limit), 100))))

    @app.get("/markets")
    def markets_reference(request: Request):
        """مرجع الأسواق المرشَّحة — the candidate-market list for the target
        picker: {iso3, m49, name}. Same reference `rank_markets()` scores
        against — يُبنى مرة واحدة، لا نداء شبكة، ثابت لكل التشغيلات.
        """
        _rate_limit(request)
        from silk_market_ranker import COUNTRIES
        from silk_data_layer import partner_name
        from silk_narrative import COUNTRY_AR
        # P3 (بلاغ المالك): الاسم العربي إلى جانب الإنجليزي — الواجهة تعرض
        # العربية في وضعها العربي بدل أسماء إنجليزية خام.
        return _json([{"iso3": c["iso3"], "m49": c["m49"],
                      "name": partner_name(c["m49"]),
                      "name_ar": COUNTRY_AR.get(c["iso3"],
                                                partner_name(c["m49"]))}
                      for c in COUNTRIES])

    def _require_key(request: Request) -> None:
        """حارس المصادقة — 401 when the key mismatches, constant-time (L-1).

        يُطبَّق على مسارات القراءة الحسّاسة أيضاً (C-1): التحليلات المحفوظة
        تحمل بطاقة المنتج الاقتصادية، ومعرّفاتها متسلسلة — بلا هذا الحارس
        يقرؤها أي مجهول بالتعداد. المقارنة عبر hmac.compare_digest لتفادي
        تسريب التوقيت. غير مضبوط SILK_API_KEY => وضع تطوير مفتوح (لا انحدار).
        """
        expected = _api_key_expected()
        if not expected:
            return
        got = request.headers.get("x-api-key", "")
        if not hmac.compare_digest(got, expected):   # constant-time (L-1)
            raise HTTPException(status_code=401,
                                detail="missing or invalid API key "
                                       "(send X-API-Key header)")

    # تحديد معدّل بسيط بالذاكرة (M-1) — in-memory fixed-window rate limit.
    # نافذة ثابتة لكل هوية (X-API-Key إن وُجد وإلا IP)؛ التجاوز = 429.
    # يكفي أداةً داخلية (لا Redis)؛ الحالة لكل نسخة تطبيق (تُعاد تهيئتها في
    # الاختبارات). SILK_RATE_LIMIT=0 يعطّله؛ الافتراضي 120 طلباً/60 ثانية.
    _rl_max = int(os.environ.get("SILK_RATE_LIMIT", "120") or "120")
    _rl_window = max(1, int(os.environ.get("SILK_RATE_WINDOW", "60") or "60"))
    _rl_lock = threading.Lock()
    _rl_hits: dict[str, tuple[int, int]] = {}

    def _rate_limit(request: Request) -> None:
        """حدّ المعدّل — raise 429 when a client exceeds the window budget."""
        if _rl_max <= 0:
            return
        ident = (request.headers.get("x-api-key")
                 or (request.client.host if request.client else "anon"))
        win = int(time.time()) // _rl_window
        with _rl_lock:
            w, c = _rl_hits.get(ident, (win, 0))
            if w != win:
                w, c = win, 0
            c += 1
            _rl_hits[ident] = (w, c)
            if len(_rl_hits) > 4096:
                # سدّ النمو بلا تصفير شامل (مراجعة المشروع): .clear() كان
                # يمحو نوافذ كل العملاء، فيستطيع مهاجم إرسال 4096 هوية
                # زائفة ليصفّر عدّاده هو. الآن: تُقلَّم النوافذ المنتهية
                # فقط؛ وإن بقي الفيض (هجوم هويات في نافذة واحدة) تُطرد
                # هويات أخرى — عدّاد الهوية الحالية لا يُمسّ أبداً.
                stale = [k for k, (w0, _c0) in _rl_hits.items() if w0 != win]
                for k in stale:
                    del _rl_hits[k]
                if len(_rl_hits) > 4096:
                    for k in list(_rl_hits):
                        if k != ident:
                            del _rl_hits[k]
                        if len(_rl_hits) <= 4096:
                            break
        if c > _rl_max:
            raise HTTPException(
                status_code=429,
                detail=f"rate limit exceeded ({_rl_max}/{_rl_window}s) — "
                       "slow down or raise SILK_RATE_LIMIT")

    def _guard_paid(req) -> None:
        """حارسا المدفوع — 503 لمفاتيح غير محمية، ثم 429 للسقف، ثم التسجيل."""
        paid_requested = sum(1 for f in _PAID_FLAGS if getattr(req, f, False))
        if paid_requested:
            unprotected = _unprotected_paid_keys()
            if unprotected:
                raise HTTPException(
                    status_code=503,
                    detail="paid provider keys are set ("
                           + ", ".join(unprotected)
                           + ") but SILK_API_KEY is not — refusing to run "
                             "paid layers unauthenticated. Set SILK_API_KEY "
                             "(and send X-API-Key) or unset the paid keys.")
        # فحص السقف والتسجيل في معاملة ذرّية واحدة — لا نافذة سباق بين
        # القراءة والكتابة (طلبان متزامنان لا يتجاوزان السقف معًا).
        # Atomic check-and-reserve: no TOCTOU window between read and write.
        if paid_requested and not silk_usage.try_reserve_paid_calls(
                paid_requested):
            # ITEM 5ب: رفض حجز بحالة السقف — نص خادمي بحت، لا محتوى كلود.
            import silk_ops_log
            silk_ops_log.record_error(
                "reservation_refused",
                "بلغ سقف التفعيلات المدفوعة اليومي (SILK_PAID_DAILY_CAP)",
                context={"requested": paid_requested,
                        "today_activations": silk_usage.paid_calls_today()})
            raise HTTPException(
                status_code=429,
                detail="daily paid-layer cap reached (SILK_PAID_DAILY_CAP) — "
                       "retry tomorrow or raise the cap")

    def _source_policy() -> dict:
        """سياسة المصادر الخادمية (Stage 2A) — server decides, never UI flags.

        القاعدة الصلبة: كل مصدر مجاني بلا مفتاح يُحاول دائماً؛ والمفتاحيّ المجاني
        يُحاول متى وُجد مفتاحه في بيئة الخادم. أعلام العميل لا تُعطّل مصدراً —
        كانت البوابة المشتقة من لوحة مفاتيح المتصفح سببَ إظلام 8/12 مصدراً
        (docs/SOURCE_AUDIT.md). المدفوع يبقى بنيوياً في /deepen فقط.

        قرار المالك (مراجعة التشغيل الحي، 2026-07-06): with_competitors/
        with_channels/with_importers (الموجة ٣) عُطِّلت هنا نهائياً — صارت
        زائدة عن حاجتها بعد `with_research` (المرحلة ٣، §4b): CompetitorAgent
        وSupplierAgent يبحثان نفس السؤال (منافسون/موزّعون بالاسم) عبر
        Serper/Maps، فتضاعف الاستهلاك بلا فائدة وتكرّر نفس المحتوى في قسمين
        مختلفين من التقرير الواحد (وquotas Serper/Trends محدودة — لاحظنا
        429 من Google Trends في التشغيل الحي). الوكيلان القائمان (silk_
        competitors_agent.py، silk_channels_agent.py، silk_importers_agent.py)
        يبقيان دون حذف — silk_engine.analyze لا يزال يقبل هذه الأعلام
        مباشرة (اختبارات test_wave3_agents.py)، فقط سياسة الخادم توقفت عن
        تفعيلها تلقائياً.
        """
        return {
            "with_trends": True, "with_tariffs": True, "with_faostat": True,
            "with_requirements": True, "with_trend": True,
            "with_competitors": False, "with_channels": False,
            "with_importers": False, "with_risk": True, "with_research": True,
            "with_dynamics": True,
            "with_websearch": bool(__import__("silk_websearch_agent")
                                   .search_key()),
            "with_maps": bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()),
        }

    def _free_ai_extras_allowed() -> tuple[bool, str]:
        """هل تُسمح إضافات كلود على المسار المجاني؟ — (allowed, reason).

        مراجعة المشروع (H2): استخلاص الثقافة وفلترة الكيانات نداءاتُ كلود
        تجري داخل /analyze خارج وكلاء PAID الثلاثة، فكانت (١) تُصرف لمجهولين
        حين يوجد ANTHROPIC_API_KEY بلا SILK_API_KEY — خرقاً لقاعدة حارس 503،
        و(٢) لا تُحتسب على SILK_PAID_DAILY_CAP. الآن: النشر غير المحمي يحجبها،
        والمحمي يحجز تفعيلة واحدة ذرّياً من نفس عدّاد السقف قبل السماح.
        الرفض يتدهور (تحليل بلا إضافات كلود + ملاحظة معلنة) — لا 429 لمسارٍ
        مجاني في أصله.
        """
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return True, ""            # لا مفتاح => لا إنفاق ممكن أصلاً
        if _unprotected_paid_keys():
            return False, ("ANTHROPIC_API_KEY مضبوط بلا SILK_API_KEY — "
                           "إضافات كلود (ثقافة المستهلك، فلترة الكيانات) "
                           "حُجبت على المسار المجاني حتى تُضبط المصادقة.")
        if not silk_usage.try_reserve_paid_calls(1):
            return False, ("سقف الاستهلاك اليومي (SILK_PAID_DAILY_CAP) "
                           "مستنفد — إضافات كلود حُجبت لهذا الطلب؛ "
                           "التحليل المجاني اكتمل بدونها.")
        return True, ""

    def _research_readiness() -> tuple[bool, str]:
        """جهوزية البحث العميق — (ready, reason). فحص قراءة بلا حجز (M-2 نمط
        would_exceed_cap، لا try_reserve_paid_calls) — الحجز الذرّي الفعلي
        يبقى في _free_ai_extras_allowed أثناء التنفيذ؛ هذا فحص مسبق رخيص.

        بلاغ حي (أول تشغيلة إنتاجية): /research بلا كلود ينتج هيكلاً فارغاً
        لا تقريراً — الاثنتا عشرة بعثة + المحلل + التوليف مرحلة ٢ + الكاتب/
        المراجع كلها نداءات كلود، خلافاً لـ/analyze حيث كلود تحسين اختياري.
        الفرق: هنا كلود **شرط تشغيل**، فيُرفض غيابه صراحة (409) قبل تشغيل
        أي بعثة — لا يُسلَّم هيكل فارغ كأنه المنتج. `allow_degraded=true`
        فتحة هروب صريحة تطلبها الجهة المستهلكة، لا تدهوراً افتراضياً.
        """
        import silk_ai_judge
        if not os.environ.get("ANTHROPIC_API_KEY", "").strip():
            return False, ("ANTHROPIC_API_KEY غير مضبوط — البحث العميق "
                           "يتطلب كلود لكل الاثنتي عشرة بعثة والمحلل "
                           "والكاتب؛ بلا مفتاح لا تقرير حقيقي ممكن.")
        unprotected = _unprotected_paid_keys()
        if unprotected:
            return False, ("ANTHROPIC_API_KEY مضبوط بلا SILK_API_KEY — "
                           "طبقة كلود محجوبة (حارس 503) حتى تُضبط "
                           "SILK_API_KEY في بيئة النشر.")
        if not silk_ai_judge.available():
            return False, ("طبقة كلود محجوبة سياقياً (block_ai_extras) في "
                           "هذا الطلب — راجع سياق التشغيل الحالي.")
        if silk_usage.would_exceed_cap(1):
            return False, ("سقف الاستهلاك اليومي (SILK_PAID_DAILY_CAP) "
                           "مستنفد — أعد المحاولة غداً أو ارفع السقف.")
        return True, ""

    @app.post("/analyze")
    def analyze(req: AnalyzeRequest, request: Request):
        """حلّل منتجًا عبر الأسواق (المسار العادي، مجاني حصراً) — free-only path.

        الموجة ٢: لا حقول مدفوعة في النموذج أصلاً — الحصر بنيوي. التعميق عبر
        POST /deepen. Stage 2A: طبقات المصادر تُقرَّر بسياسة الخادم حصراً
        (_source_policy) — علم العميل لا يستطيع إطفاء مصدر مجاني.
        """
        _require_key(request)
        _rate_limit(request)
        policy = _source_policy()
        ai_ok, ai_note = _free_ai_extras_allowed()
        # P5 (بلاغ المالك: «كلود العادي يتفوق على المنصة»): حكم كلود
        # (المرحلة ٢ من التوليف) وتقريره يعملان على المسار الرئيسي متى كان
        # المفتاح مضبوطاً ومحمياً — نفس بوابة H2 ونفس الحجز من السقف؛ لا
        # مسار حكم موازٍ (التوليف يبقى نقطة الدخول الوحيدة، §9.3).
        policy["with_ai"] = ai_ok and bool(
            os.environ.get("ANTHROPIC_API_KEY", "").strip())
        import contextlib
        import silk_context
        ctx = (contextlib.nullcontext() if ai_ok
               else silk_context.block_ai_extras())
        # لوحة إعدادات الوكلاء: طلبٌ بلا agent_prefs يرث الإعدادات المحفوظة
        # خادمياً — فتسري على الإدخال والدردشة معاً حتى من عميل لا يرسلها.
        prefs = _clean_agent_prefs(req.agent_prefs)
        if prefs is None:
            prefs = _saved_agent_settings()
        with ctx, silk_context.agent_prefs_context(prefs):
            result = silk_engine.analyze(
                req.product, year=req.year,
                countries=_target_countries(req.markets),
                trend_span=req.trend_span,
                product_card=(req.product_card.model_dump()
                              if req.product_card else None),
                hs_code=req.hs_code,
                persist=req.persist, **policy)
        if not ai_ok:
            result["ai_extras_note"] = ai_note   # الغياب مُعلَن لا صامت
        result["view"] = _view(result)
        return _json(result)

    def _clean_agent_prefs(raw: dict | None) -> dict | None:
        """طبّع توجيهات الوكلاء شكلياً (P3) — {key: {on: bool, cmd: str<=500}}.

        أي شكل آخر يُتجاهل بصمت (إعداد عميل لا بيانات)؛ الأمر نص حر يذهب
        حصراً إلى برومبتات كلود داخل عزل _isolate — لا يمسّ وكلاء الأرقام.
        """
        if not isinstance(raw, dict):
            return None
        out = {}
        for k, v in list(raw.items())[:24]:
            if not isinstance(v, dict):
                continue
            out[str(k)[:40]] = {"on": bool(v.get("on", True)),
                                "cmd": str(v.get("cmd") or "")[:500]}
        return out or None

    def _target_countries(iso3s: list[str] | None):
        """ضيّق قائمة الأسواق المرشّحة — an explicit ISO3 subset of COUNTRIES,
        أو None (الافتراضي: كل الأسواق ‎— سلوك الاكتشاف القائم بلا تغيير).

        رموز غير معروفة تُتجاهَل بصمت (لا اختلاق سوق غير موجود في المرجع)؛
        قائمة فارغة بعد الترشيح => None (لا نُسقط التحليل إلى صفر أسواق).
        """
        if not iso3s:
            return None
        from silk_market_ranker import COUNTRIES
        wanted = {s.strip().upper() for s in iso3s if s and s.strip()}
        filtered = [c for c in COUNTRIES if c["iso3"] in wanted]
        return filtered or None

    def _saved_agent_settings() -> dict | None:
        """إعدادات الوكلاء المحفوظة خادمياً — sanitized, or None (لا حفظ)."""
        try:
            import silk_store
            return _clean_agent_prefs(silk_store.load_agent_settings())
        except Exception as e:  # noqa: BLE001 — الإعدادات تحسين لا شرط
            log.debug("saved agent settings unavailable: %s", e)
            return None

    class AgentSettingsBody(BaseModel):
        """جسم إعدادات الوكلاء — {agent_key: {on: bool, cmd: str}} فقط.

        **لا مفاتيح مصادر هنا** — pydantic يسقط أي حقل آخر، والقاموس يمرّ
        على _clean_agent_prefs (on/cmd حصراً) فلا يمكن تهريب مفتاح عبر
        هذه اللوحة؛ مفاتيح المصادر تُضبط في بيئة النشر (Railway env).
        """
        settings: dict | None = None

    @app.get("/settings/agents")
    def get_agent_settings(request: Request):
        """سجل الوكلاء + الإعدادات السارية — the catalog and effective settings.

        الواجهة تبني اللوحة من هذا الرد (سجل واحد قانوني في silk_agents —
        لا قائمة موازية في الواجهة تنحرف عنه).
        """
        _require_key(request)
        _rate_limit(request)
        import silk_missions  # noqa: F401 — يسجّل صفوف البعثات الاثنتي عشر
        from silk_agents import AGENT_CATALOG, default_agent_settings
        merged = default_agent_settings()
        saved = _saved_agent_settings() or {}
        for k, v in saved.items():
            if k in merged:
                merged[k] = v
        return {"agents": AGENT_CATALOG, "settings": merged,
                "saved": bool(saved)}

    @app.post("/settings/agents")
    def set_agent_settings(body: AgentSettingsBody, request: Request):
        """احفظ إعدادات الوكلاء خادمياً — persist per-agent {on, cmd}.

        جسم فارغ = استعادة الافتراضي (يمحو المحفوظ فتسري الافتراضيات).
        """
        _require_key(request)
        _rate_limit(request)
        clean = _clean_agent_prefs(body.settings) or {}
        import silk_store
        silk_store.migrate()
        silk_store.save_agent_settings(clean)
        return {"saved": True, "count": len(clean)}

    class KeysBody(BaseModel):
        """جسم حفظ مفاتيح المصادر — allow-listed server-side key settings."""
        keys: dict[str, str]

    @app.post("/settings/keys")
    def set_keys(body: KeysBody, request: Request):
        """احفظ مفاتيح المصادر في الخادم (Stage 2A) — the settings panel finally
        persists somewhere real: allow-listed keys go to the unified store AND the
        process env (agents pick them up immediately). القيم لا تُعاد أبداً —
        الاستجابة وجود/رفض فقط. متغير بيئة النشر يبقى الأعلى سلطة عند الإقلاع.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_store
        silk_store.migrate()
        saved, rejected = [], []
        for k, v in (body.keys or {}).items():
            v = (v or "").strip()
            if v and silk_store.set_setting(k, v):
                os.environ[k] = v
                saved.append(k)
            elif v:
                rejected.append(k)
        return {"saved": saved, "rejected": rejected}

    @app.post("/deepen")
    def deepen(req: DeepenRequest, request: Request):
        """عمّق التحليل (المسار المدفوع الوحيد) — the only paid-layer path.

        يعمل داخل silk_context.deepen_context() فيسمح حارس BaseAgent البنيوي
        بتشغيل الوكلاء المدفوعين (localprice/volza/explee) — خارجه يستحيل
        تنفيذهم حتى مع مفاتيح مضبوطة. حارسا الموجة ٠ (401 المصادقة، 429
        السقف) يعملان قبل أي وكيل.
        """
        _require_key(request)
        _rate_limit(request)
        _guard_paid(req)
        import silk_context
        with silk_context.deepen_context():
            result = silk_engine.analyze(
                req.product, year=req.year, with_trends=req.with_trends,
                with_tariffs=req.with_tariffs, with_faostat=req.with_faostat,
                with_maps=req.with_maps, with_websearch=req.with_websearch,
                with_localprice=req.with_localprice, own_price=req.own_price,
                with_volza=req.with_volza, with_explee=req.with_explee,
                with_ai=req.with_ai,
                with_competitors=req.with_competitors,
                with_channels=req.with_channels,
                with_importers=req.with_importers,
                with_requirements=req.with_requirements,
                with_trend=req.with_trend, trend_span=req.trend_span,
                product_card=(req.product_card.model_dump()
                              if req.product_card else None),
                hs_code=req.hs_code,
                persist=req.persist)
        result["view"] = _view(result)
        return _json(result)

    class ResearchRequest(BaseModel):
        """طلب بحث عميق (الموجة ٤، V5) — ١٢ بعثة كلود + محلل شامل + تقرير.

        لا حقول مدفوعة (كـ AnalyzeRequest تماماً) — مسار مجاني حصراً. `market`
        نص حر (اسم عربي/إنجليزي أو ISO3) يُحلّ عبر silk_market_resolver؛
        مطابقة ضعيفة/غامضة = 422 مع اقتراحات، لا تخمين سوق.

        حادثة نقطة تفتيش/استئناف + تشغيل خلفي (P0): `resume` يستأنف تشغيلة
        سابقة بمعرّفها — `product`/`market` يصيران اختياريَين عندها (تُقرَآن
        من الطلب المخزَّن وقت الإنشاء)، وإلا إلزاميان كالسابق. `async_run`
        يُعيد `analysis_id` فوراً (202) ويكمل المعالجة في خيط خلفي — تجاوز
        مهلة بوّابة/وكيل عكسي لا يقتل التشغيلة أو يُيتّمها بعد اليوم.
        """
        product: str | None = None
        market: str | None = None
        hs_code: str | None = None
        product_card: ProductCard | None = None
        own_price: float | None = None  # سعرك المستهدف — كـAnalyzeRequest
        persist: bool = True
        agent_prefs: dict | None = None
        # بلاغ حي — بوابة ما قبل التشغيل (409) ترفض تشغيلة بلا كلود صراحة؛
        # هذا الحقل فتحة هروب صريحة تطلبها الجهة المستهلكة (لا تدهور
        # افتراضي): تسليم تقرير موسوم بوضوح "متدهور" بدل رفضه كلياً.
        allow_degraded: bool = False
        resume: int | None = None
        async_run: bool = False

    def _research_budget_status(economics: dict) -> dict:
        """حالة الميزانية على مستوى التشغيلة كاملة — P1، حادثة نفاد
        الاعتمادات: يسمّي **أي** سقف بلغ حدّه صراحة، لا يكتفي بملاحظة
        مدفونة داخل فجوات بعثة واحدة (كانت موجودة أصلاً — هذا تجميع
        علوي إضافي يجعلها مرئية فوراً للوحة/المستهلك)."""
        llm_cap = int(os.environ.get("SILK_RESEARCH_MAX_LLM_CALLS", "40"))
        tool_cap = int(os.environ.get("SILK_RESEARCH_MAX_TOOL_CALLS", "100"))
        llm_calls = economics.get("llm_calls", 0)
        tool_calls = economics.get("tool_calls", 0)
        hit = []
        if llm_calls >= llm_cap:
            hit.append(f"SILK_RESEARCH_MAX_LLM_CALLS={llm_cap}")
        if tool_calls >= tool_cap:
            hit.append(f"SILK_RESEARCH_MAX_TOOL_CALLS={tool_cap}")
        return {"exhausted": bool(hit), "caps_hit": hit,
               "llm_calls": llm_calls, "llm_cap": llm_cap,
               "tool_calls": tool_calls, "tool_cap": tool_cap,
               # H5: هل تدهور الذيل (تخطّى حَكَم التوليف + مراجعة الكاتب) لأن
               # البعثات استنفدت السقف؟ مُعلَن صراحةً، لا مدفون.
               "tail_degraded": bool(economics.get("tail_degraded"))}

    def _attach_quality_gate(result: dict, trace_id: str | None) -> None:
        """شغّل بوابة الجودة على القالب الموحّد وألحِق نتيجتها — الموجة ١٠،
        مستخرَجة كي يستدعيها كل من مسار /research الكامل ونقطة إعادة توليد
        التقرير وحدها (POST /analyses/{id}/report) بلا ازدواج منطق."""
        try:
            import silk_quality_gate
            gate_out = silk_quality_gate.run_quality_gate(result["view"])
            result["view"]["deep_research"]["quality_gate"] = gate_out
            if trace_id:
                import silk_trace
                silk_trace.append_event(
                    trace_id, event="quality_gate", verdict=gate_out["verdict"],
                    finding_count=len(gate_out["findings"]))
        except Exception as e:  # noqa: BLE001 — البوابة تحسين لا شرط تسليم
            log.warning("quality gate skipped: %s", e)

    def _run_research_pipeline(market_ref, product: str, hs_code: str | None,
                               hs_note: str | None, product_card_dict: dict | None,
                               ai_ok: bool, ai_note: str, prefs: dict | None,
                               ready: bool, ready_reason: str,
                               analysis_id: int | None,
                               resume_reports: dict | None) -> dict:
        """جسم التشغيلة الثقيل — بعثات + محلل + توليف + كاتب/مراجع + بوابة
        جودة. مستخرَج من مسار /research المتزامن السابق **بلا تغيير سلوكي**
        كي يُستدعى إما مباشرة (وضع متزامن) أو من خيط خلفي (async_run=true)
        بلا ازدواج منطق. لا حفظ هنا — المستدعي يقرّر متى/كيف يُخزَّن."""
        import contextlib
        import silk_context
        ctx = (contextlib.nullcontext() if ai_ok
               else silk_context.block_ai_extras())
        with ctx, silk_context.agent_prefs_context(prefs):
            silk_context.begin_data_counter()
            from silk_missions import deep_research
            from silk_market_analyst import analyze_market, to_synthesis_input
            from silk_synthesis import synthesize
            from silk_ai_judge import write_reviewed_report

            # تقدّم حيّ (GET /research/{id}/status): لقطة أولى تضبط started_at
            # مرّة واحدة — كل لقطة لاحقة (لكل بعثة، ولكل مرحلة كاتب/مراجع)
            # تعيد استعمال نفس القناة (silk_context.snapshot_research_progress)
            # بلا عدّاد جديد، تُقرأ من نفس data_counter المستعمَل للتقرير النهائي.
            import datetime as _dt
            _started_at = _dt.datetime.now().isoformat(timespec="seconds")
            silk_context.snapshot_research_progress(
                analysis_id, "missions", started_at=_started_at)

            # deep_research() (لا run_all_missions مباشرة) — يفعّل التتبّع
            # الكامل دوماً (data/traces/{trace_id}.jsonl، الموجة ٦) فيبقى كل
            # تشغيل /research إنتاجي قابلاً للتدقيق، لا التشغيلات التجريبية فقط.
            research_run = deep_research(market_ref, product=product,
                                         hs_code=hs_code,
                                         product_card=product_card_dict,
                                         analysis_id=analysis_id,
                                         resume_reports=resume_reports)
            mission_reports = research_run["reports"]
            trace_id = research_run.get("trace_id")
            silk_context.snapshot_research_progress(analysis_id, "analyst")
            # H5 (تدقيق): حارس إنفاق على مستوى التشغيلة للذيل. السقف الكلي
            # (SILK_RESEARCH_MAX_LLM_CALLS) كان يُستشار داخل حلقة البعثات
            # فقط؛ الذيل (محلل+توليف+كاتب+مراجع) يجري بلا حكم حتى لو استُنفد.
            # الآن: إن بلغت البعثاتُ السقف، يُنتِج الذيل التقرير الأساسي
            # (المحلل + مسوّدة الكاتب — لا يُلغى الكاتب فلا فقدان) لكن يتخطّى
            # المكلّف الاختياري: حَكَم التوليف مرحلة-٢ (تبقى جورية المرحلة ١)
            # ودورة مراجعة الكاتب (مسوّدة بلا تنقيح). تدهور رشيق مُعلَن.
            _llm_cap = int(os.environ.get("SILK_RESEARCH_MAX_LLM_CALLS", "40"))
            _ctr = silk_context.data_counter() or {}
            tail_over_budget = ai_ok and _ctr.get("llm_calls", 0) >= _llm_cap
            tail_with_ai = ai_ok and not tail_over_budget
            tail_max_cycles = 1 if tail_over_budget else 2
            # بلاغ حي (تمور/هولندا، تشغيلة ثانية): trace_context البعثات
            # الاثنتي عشرة يُغلَق فور عودة deep_research() أعلاه — نداءا
            # المحلل الشامل والكاتب/المراجع كانا يجريان **بلا أي تتبّع**،
            # فحين فشل الكاتب لم يكن هناك أثر يوضّح هل بلغ مهلته الموسّعة
            # فعلاً أم فشل أسرع بخطأ آخر. إعادة فتح نفس ملف التتبّع (معرّف
            # واحد، إلحاق فقط — لا تصادم) للمحلل صراحة؛ الكاتب يُمرَّر
            # trace_id مباشرة (راجع silk_ai_judge._traced_call).
            import silk_trace
            with silk_trace.trace_context(trace_id):
                analyst_out = analyze_market(
                    market_ref, product, mission_reports, hs_code=hs_code,
                    product_card=product_card_dict)
            analyst_input = to_synthesis_input(analyst_out)
            verdict = synthesize(
                list(mission_reports.values()), product=product,
                market=market_ref.name_en, with_ai=tail_with_ai,
                analyst_assessment=analyst_input)
            report_out = (write_reviewed_report(
                mission_reports, analyst_input.get("summary", ""), verdict,
                product, market_ref.name_en, max_cycles=tail_max_cycles,
                trace_id=trace_id, hs_code=hs_code,
                on_stage=lambda s: silk_context.snapshot_research_progress(
                    analysis_id, s)) if ai_ok else
                {"report": None, "review_cycles": 0, "unresolved_notes": []})
            economics = dict(silk_context.data_counter() or {})
            economics["tail_degraded"] = tail_over_budget
            if not report_out.get("report"):
                # ITEM 5ب: فشل الكاتب في التشغيلة الرئيسية (لا مسار regen) —
                # السبب مُطهَّر قبل التخزين (نفس مُطهِّر H1/H4 القائم).
                from silk_render import _strip_internal_plumbing
                import silk_ops_log
                silk_ops_log.record_error(
                    "writer_failure",
                    _strip_internal_plumbing(report_out.get("failure_reason") or "")
                    or "فشل الكاتب بلا سبب مسجَّل",
                    context={"analysis_id": analysis_id, "trace_id": trace_id})

        served = economics.get("store_hits", 0) + economics.get("cache_hits", 0)
        economics["note"] = (
            f"{economics.get('llm_calls', 0)} نداء كلود، "
            f"{economics.get('tool_calls', 0)} نداء أداة، {served} قراءة "
            "خُدمت من المخزن/ذاكرة الطلبات")
        from silk_pricing import estimate_cost_usd
        cost = estimate_cost_usd(economics.get("llm_usage"))
        economics["cost_usd_estimate"] = cost["total_usd"]
        economics["cost_usd_by_model"] = cost["by_model"]
        economics["cost_unpriced_models"] = cost["unpriced_models"]
        # إسناد التكلفة لكل بعثة (Part C، تحضير قياس حقيقي لتخفيض الكلفة):
        # mission_usage يُملأ فقط داخل silk_context.mission_context (وسم كل
        # نداء بمفتاح بعثته) — يُعاد استعمال estimate_cost_usd نفسه لكل بعثة
        # لا حساب تسعير موازٍ. تشغيلات سابقة لهذه الإضافة تعرض {} — فجوة
        # معلنة صريحة (تشغيلة قديمة بلا هذا الوسم)، لا اختلاق رقم.
        economics["cost_usd_by_mission"] = {
            mkey: estimate_cost_usd(mu)["total_usd"]
            for mkey, mu in (economics.get("mission_usage") or {}).items()}
        silk_context.snapshot_research_progress(analysis_id, "done")
        # H6: صالِح الحجز المسبق بالتكلفة الفعلية المُقدَّرة — المعالج حجز
        # التقدير (_expected) ذرّيًا قبل البدء؛ هنا نبدّله بالمُنفَق الحقيقي
        # المحسوب من رموز *كل* نداءات كلود في التشغيلة: بعثات + محلل + توليف +
        # كاتب بما فيه **كل محاولات تصعيد السقف** + **دورات المراجع** — العدّاد
        # يُقرأ بعد اكتمال الذيل كله (economics أعلاه)، وكل ردّ HTTP يسجّل رموزه
        # حتى المقتطع (silk_llm_provider._record_usage قبل فحص الاقتطاع). لكل
        # تشغيلة (متزامنة أو خلفية، كلاهما يمرّ من هنا).
        _reserved_usd = float(os.environ.get("SILK_RESEARCH_EXPECTED_USD", "3.0"))
        silk_usage.reconcile_usd(reserved=_reserved_usd, actual=cost["total_usd"])
        budget_status = _research_budget_status(economics)

        result: dict = {
            "product": product, "hs_code": hs_code, "year": None,
            "preliminary": True,
            "market": {"iso3": market_ref.iso3, "m49": market_ref.m49,
                      "iso2": market_ref.iso2, "name_en": market_ref.name_en,
                      "name_ar": market_ref.name_ar},
            "markets": [],  # لا ترتيب أسواق هنا — سوق واحد مُحلَّل بعمق
            "deep_research": {
                "missions": mission_reports, "analyst": analyst_out,
                "verdict": verdict, "report": report_out,
                "trace_id": research_run.get("trace_id"),
                # P1 (حادثة نفاد الاعتمادات): سقف بلغ حدّه = إنهاء رشيق
                # بفجوات معلنة، لا خطأ صلب — لكن يُذكَر صراحةً أيّ سقف.
                "budget_status": budget_status,
            },
            "data_economics": economics,
        }
        if hs_note:
            result["hs_resolution_note"] = hs_note
        if not ai_ok:
            result["ai_extras_note"] = ai_note
        # التدهور الفعلي = عدم الجهوزية (ready=False، بلاغ حي: _free_ai_
        # extras_allowed تعيد (True, "") حين لا مفتاح إطلاقاً — "لا قيد على
        # إضافات كلود" لأن /analyze لا يحتاجها أصلاً؛ ذلك المنطق يُخفي هنا
        # حقيقة أن /research **لا يعمل بلا مفتاح** رغم ai_ok=True ظاهرياً)
        # أو فشل الحجز الذرّي المتأخر رغم اجتياز البوابة (سباق نادر).
        if not ready or not ai_ok:
            result["degraded"] = True
            result["degraded_reason"] = (ai_note if not ai_ok else "") or ready_reason
        result["view"] = _view(result)

        # بوابة الجودة قبل التسليم (الموجة ١٠) — تعمل على القالب الموحّد
        # النهائي **قبل** أي عرض docx، فتلحَق نتيجتها بالتتبّع وبقسم
        # "منهجية البحث ونطاقه" داخل التقرير (طبقة العرض، silk_reports.py).
        _attach_quality_gate(result, research_run.get("trace_id"))
        return result

    def _finish_research_run(analysis_id: int | None, result: dict) -> None:
        """خزّن النتيجة النهائية وحدّث حالة التشغيلة — نفس معرّف الإنشاء
        (P0: نتيجة الاستئناف تنتهي بنفس analysis_id الذي بدأت به).

        `analysis_id` يُضاف لِـ`result` **قبل** التخزين لا بعده — بلاغ حي
        (اختبار استئناف تشغيلة مكتملة): إضافته بعد `save_analysis` تعني
        أن النسخة المخزَّنة لا تحمله أبداً، فقراءتها لاحقاً عبر استئناف أو
        `GET /analyses/{id}` تفتقد الحقل رغم ظهوره في الرد الأصلي المباشر.
        """
        if analysis_id is None:
            return
        result["analysis_id"] = analysis_id
        from silk_storage import save_analysis
        save_analysis(result, analysis_id=analysis_id)

    def _research_background(market_ref, product, hs_code, hs_note,
                             product_card_dict, ai_ok, ai_note, prefs,
                             ready, ready_reason, analysis_id,
                             resume_reports) -> None:
        """جسم الخيط الخلفي (async_run=true) — يُغلَّف باستثناء شامل عمداً:
        خيط بايثون غير المُمسوك يفشل صامتاً (لا كسر عملية، لا تحديث حالة)
        فتبقى التشغيلة عالقة على 'running' للأبد — بلاغ التحقيق (P0) يمنع
        هذا صراحة. نقاط تفتيش البعثات المكتملة فعلاً تبقى مخزَّنة بصرف
        النظر عن نتيجة هذه المحاولة — استئناف لاحق يقرأها."""
        try:
            result = _run_research_pipeline(
                market_ref, product, hs_code, hs_note, product_card_dict,
                ai_ok, ai_note, prefs, ready, ready_reason, analysis_id,
                resume_reports)
            _finish_research_run(analysis_id, result)
        except Exception as e:  # noqa: BLE001 — خيط خلفي: هذا آخر حزام أمان
            log.error("background /research run %s failed: %s", analysis_id, e)
            from silk_storage import mark_research_failed
            mark_research_failed(analysis_id, f"{type(e).__name__}: {e}")

    @app.post("/research")
    def research(req: ResearchRequest, request: Request):
        """بحث عميق — ١٢ بعثة كلود بالأدوات + محلل شامل + حكم + تقرير مراجَع.

        مسار مجاني حصراً (نموذج بلا حقول مدفوعة، كـ/analyze) — إضافات كلود
        (البعثات + المحلل + توليف المرحلة ٢ + الكاتب/المراجع) تمرّ عبر نفس
        بوابة H2 (`_free_ai_extras_allowed`) وحجزها الذرّي الواحد من
        SILK_PAID_DAILY_CAP (كنداء AI إضافي واحد على /analyz تماماً) — لا
        مسار كلود موازٍ. الحجم الفعلي لعدد النداءات عبر التحليل بأكمله
        محكوم بسقف منفصل (`SILK_RESEARCH_MAX_LLM_CALLS`/`_MAX_TOOL_CALLS`،
        افتراضياً ٤٠/١٠٠) يُطبَّق حياً داخل `silk_llm_runtime._run_loop` —
        إنهاء رشيق لا كسر عند تجاوزه، ومُلخَّص علوياً في
        `deep_research.budget_status` (P1، حادثة نفاد الاعتمادات).

        بوابة ما قبل التشغيل (بلاغ حي): كلود هنا **شرط تشغيل** لا تحسين
        اختياري — بلا مفتاح فعّال كل الاثنتي عشرة بعثة تفشل بصفر نتائج
        والتقرير هيكل فارغ. `_research_readiness()` يرفض هذا صراحة بـ409
        قبل تشغيل أي بعثة، إلا أن يمرّر الطالب `allow_degraded=true` —
        عندها تُشغَّل التشغيلة وتُوسَم النتيجة `degraded=true` مع سبب واضح
        (`degraded_reason`)، فتحمل كل مشتقات التقرير (docx/مختصر/لوحة)
        لافتة تحذير حمراء بدل تسليم هيكل فارغ بصمت كأنه المنتج.

        نقطة تفتيش/استئناف + تشغيل خلفي (P0، حادثة نفاد الاعتمادات —
        `docs/DEEP_RESEARCH_DECISIONS.md`): `persist=true` (الافتراضي)
        يخصّص `analysis_id` **قبل** تشغيل أي بعثة، وكل بعثة تُخزَّن فور
        اكتمالها — عطل/إعادة نشر منتصف الطريق لا يخسر البعثات المكتملة.
        `resume=<analysis_id>` يعيد فتح تشغيلة سابقة (مكتملة/فاشلة/عالقة)
        ويُشغّل فقط البعثات الناقصة + المحلل/الكاتب من جديد؛ إن كانت
        مكتملة أصلاً يعيدها كما هي بلا أي نداء كلود جديد (لا حرق اعتمادات
        مضاعف). `async_run=true` يعيد `{analysis_id, status:"running"}`
        فوراً (202) ويكمل المعالجة في خيط خلفي — تجاوز مهلة بوّابة/وكيل
        عكسي يعود يقطع اتصال العميل فقط، لا التشغيلة نفسها، ولا يُيتّمها:
        استطلع `GET /research/{analysis_id}/status` حتى `status=="completed"`
        ثم `GET /analyses/{analysis_id}` للنتيجة الكاملة.
        """
        _require_key(request)
        _rate_limit(request)

        resume_reports: dict | None = None
        analysis_id: int | None = None
        stored_request: dict = {}

        if req.resume is not None:
            from silk_storage import get_analysis, get_research_run, \
                load_mission_checkpoints
            run_row = get_research_run(req.resume)
            if run_row is None:
                raise HTTPException(status_code=404, detail={
                    "error": "resume_not_found",
                    "reason": f"research run {req.resume} not found"})
            if run_row.get("kind") != "research":
                raise HTTPException(status_code=400, detail={
                    "error": "not_a_research_run",
                    "reason": f"analysis {req.resume} is not a /research "
                              "run — resume only applies to /research"})
            if run_row.get("status") == "completed":
                # مكتملة فعلاً — أعِدها كما هي، لا إعادة تشغيل ولا حرق
                # اعتمادات إضافي (استئناف مكتمل يجب أن يكون آمناً للتكرار).
                existing = get_analysis(req.resume)
                if existing is not None:
                    return _json(existing)
            stored_request = run_row.get("request") or {}
            analysis_id = req.resume
            resume_reports = load_mission_checkpoints(req.resume)

        product = req.product or stored_request.get("product")
        market_name = req.market or stored_request.get("market")
        if not product or not market_name:
            raise HTTPException(status_code=422, detail={
                "error": "product_and_market_required",
                "reason": "product/market are required unless resuming an "
                         "existing analysis_id that already has them"})

        from silk_market_resolver import resolve_market
        market_ref, suggestions = resolve_market(market_name)
        if market_ref is None:
            raise HTTPException(status_code=422, detail={
                "error": f"unknown or ambiguous market {market_name!r}",
                "suggestions": suggestions})

        # بوابة ما قبل التشغيل بعد التحقق من صحة الإدخال (422 على خطأ
        # الطالب يسبق 409 على جهوزية الخادم — خطأ العميل يستحق أن يُشرَح
        # حتى لو كان الخادم متدهوراً الآن) وقبل تشغيل أي بعثة أو حجز ميزانية.
        ready, ready_reason = _research_readiness()
        if not ready and not req.allow_degraded:
            raise HTTPException(status_code=409, detail={
                "error": "research_not_ready", "reason": ready_reason,
                "hint": "اضبط ANTHROPIC_API_KEY (وSILK_API_KEY إن لزم) ثم "
                        "أعد المحاولة، أو مرّر allow_degraded=true لتسليم "
                        "تقرير موسوم صراحة كمتدهور (غير مُنصَح به تسليمياً)."})

        # H6 (تدقيق): بوابة الميزانية الدولارية اليومية — تحجز تكلفة التشغيلة
        # المتوقَّعة ذرّيًا قبل بدئها (try_reserve_usd، لا فحص قراءة فقط)، فلا
        # يمكن لتشغيلتين متزامنتين قرب السقف أن تمرّا معًا وتتجاوزا الحدّ (سباق
        # TOCTOU مسدود — نفس نمط عدّاد التفعيلات الذرّي). السقف غير مضبوط => لا
        # حجب. الإنفاق الفعلي يُصالَح بعد التشغيلة في _run_research_pipeline
        # (reconcile_usd) فيحمل الدفتر المُنفَق الحقيقي لا التقدير. تسبق حجز
        # عدّاد التفعيلات كي لا تُستهلك تفعيلة على طلب مرفوض. الاستئناف المكتمل
        # رجع مبكراً قبل هنا.
        _expected_usd = float(os.environ.get("SILK_RESEARCH_EXPECTED_USD", "3.0"))
        if not silk_usage.try_reserve_usd(_expected_usd):
            # ITEM 5ب: رفض حجز بحالة السقف — نص خادمي بحت، لا محتوى كلود.
            import silk_ops_log
            silk_ops_log.record_error(
                "reservation_refused",
                f"الميزانية اليومية بالدولار أوشكت على النفاد — "
                f"أُنفِق {round(silk_usage.usd_spent_today(), 2)}$ اليوم",
                context={"expected_usd": _expected_usd,
                        "spent_today_usd": round(silk_usage.usd_spent_today(), 2)})
            raise HTTPException(status_code=429, detail={
                "error": "daily_usd_budget_exhausted",
                "reason": f"الميزانية اليومية بالدولار أوشكت على النفاد — "
                          f"أُنفِق {round(silk_usage.usd_spent_today(), 2)}$ اليوم؛ "
                          f"تشغيلة /research متوقَّعة بنحو {_expected_usd}$."})

        hs_code = req.hs_code or stored_request.get("hs_code")
        hs_note = None
        if not hs_code:
            from silk_hs_resolver import resolve as resolve_hs
            dp = resolve_hs(product)
            hs_code = dp.value
            if hs_code is None:
                hs_note = dp.note  # فجوة معلنة — لا اختلاق رمز HS

        ai_ok, ai_note = _free_ai_extras_allowed()
        prefs = _clean_agent_prefs(req.agent_prefs)
        if prefs is None:
            prefs = stored_request.get("agent_prefs") or _saved_agent_settings()

        # بطاقة المنتج — بلاغ حي (الموجة ٩): كانت تُقبَل في النموذج ولا تصل
        # أي بعثة أو المحلل إطلاقاً، فيغيب "الموقع التنافسي"/هامش المضاهاة
        # من كل تقرير بحث عميق رغم إرسال المستخدم للبطاقة فعلياً.
        product_card_dict = (req.product_card.model_dump() if req.product_card
                             else stored_request.get("product_card"))
        own_price = (req.own_price if req.own_price is not None
                    else stored_request.get("own_price"))
        if product_card_dict is not None and own_price is not None:
            product_card_dict = dict(product_card_dict)
            product_card_dict["own_price"] = own_price

        if analysis_id is None and req.persist:
            from silk_storage import create_research_run
            request_snapshot = {
                "product": product, "market": market_name, "hs_code": hs_code,
                "product_card": product_card_dict, "own_price": own_price,
                "agent_prefs": prefs, "allow_degraded": req.allow_degraded}
            analysis_id = create_research_run(
                product, market_ref.iso3, hs_code, request_snapshot)

        if req.async_run:
            if analysis_id is None:
                raise HTTPException(status_code=400, detail={
                    "error": "async_requires_persist",
                    "reason": "async_run=true needs persist=true (or an "
                             "existing resume target) — otherwise there is "
                             "no analysis_id to poll a status for."})
            threading.Thread(
                target=_research_background,
                args=(market_ref, product, hs_code, hs_note, product_card_dict,
                     ai_ok, ai_note, prefs, ready, ready_reason, analysis_id,
                     resume_reports),
                daemon=True).start()
            return JSONResponse(status_code=202, content={
                "analysis_id": analysis_id, "status": "running",
                "async": True,
                "poll_url": f"/research/{analysis_id}/status"})

        try:
            result = _run_research_pipeline(
                market_ref, product, hs_code, hs_note, product_card_dict,
                ai_ok, ai_note, prefs, ready, ready_reason, analysis_id,
                resume_reports)
        except Exception as e:  # noqa: BLE001 — P0: فشل لا يخسر البعثات المكتملة
            log.error("sync /research run %s failed: %s", analysis_id, e)
            if analysis_id is not None:
                from silk_storage import mark_research_failed
                mark_research_failed(analysis_id, f"{type(e).__name__}: {e}")
                raise HTTPException(status_code=500, detail={
                    "error": "research_run_failed",
                    "reason": f"{type(e).__name__}: {e}",
                    "analysis_id": analysis_id,
                    "hint": f"البعثات المكتملة قبل العطل محفوظة — أعد "
                            f"المحاولة بـ resume={analysis_id} بدل تشغيلة "
                            "كاملة جديدة (لا حرق اعتمادات مضاعف)."}) from e
            raise
        _finish_research_run(analysis_id, result)  # no-op إن persist=false
        return _json(result)

    # تسمية عربية للمرحلة الحيّة (GET /status) — مرآة نصّية لقيم `stage` التي
    # تُسجَّلها silk_context.snapshot_research_progress (missions/analyst/
    # writer/reviewer/done). قيمة غير معروفة (تشغيلة قديمة قبل هذه الميزة،
    # بلا لقطة بعد) تعرض None لا تسمية مُخترَعة.
    _STAGE_LABEL_AR = {
        "missions": "بحث البعثات", "analyst": "تحليل شامل",
        "writer": "كتابة التقرير", "reviewer": "مراجعة التقرير",
        "done": "اكتمل"}

    @app.get("/research/{analysis_id}/status")
    def research_status(analysis_id: int, request: Request):
        """حالة تشغيلة بحث عميق — تقدّم لكل بعثة من الاثنتي عشرة + الحالة
        العامة (P0، حادثة نفاد الاعتمادات) — اللوحة تستطلعها دورياً بدل
        انتظار اتصال HTTP واحد طويل قد تقطعه بوّابة عكسية.

        تقدّم حيّ (المرحلة/الزمن المنقضي/التكلفة حتى الآن): من لقطة
        `silk_storage.get_research_progress` — نفس عدّادات `data_economics`
        النهائية نفسها تُقرأ أثناء التشغيل بدل عدّاد جديد. التكلفة **مُقدَّرة
        من دفتر أسعار مُسعَّر فقط** (`silk_pricing`) — نموذج غير مُسعَّر يظهر
        في `cost_unpriced_models` صراحةً بدل أن يُحتسَب صفراً بصمت (لا اختلاق).
        """
        _require_key(request)
        _rate_limit(request)
        from silk_missions import MISSION_ORDER
        from silk_storage import (get_research_run, mission_status_map,
                                  get_research_progress)
        run_row = get_research_run(analysis_id)
        if run_row is None or run_row.get("kind") != "research":
            raise HTTPException(status_code=404,
                                detail=f"research run {analysis_id} not found")
        done = mission_status_map(analysis_id)
        missions = {key: done.get(key, "pending") for key in MISSION_ORDER}
        progress = get_research_progress(analysis_id)
        stage = progress.get("stage")
        elapsed_seconds = None
        started_at = progress.get("started_at")
        if started_at:
            try:
                import datetime as _dt
                elapsed_seconds = round(
                    (_dt.datetime.now() - _dt.datetime.fromisoformat(started_at))
                    .total_seconds())
            except Exception:  # noqa: BLE001 — طابع زمني فاسد = فجوة لا استثناء
                elapsed_seconds = None
        return _json({
            "analysis_id": analysis_id, "status": run_row.get("status"),
            "product": run_row.get("product"), "hs_code": run_row.get("hs_code"),
            "created_at": run_row.get("created_at"),
            "updated_at": run_row.get("updated_at"),
            "stage": stage, "stage_label": _STAGE_LABEL_AR.get(stage),
            "elapsed_seconds": elapsed_seconds,
            "llm_calls": progress.get("llm_calls"),
            "tool_calls": progress.get("tool_calls"),
            "cost_usd_estimate": progress.get("cost_usd_estimate"),
            "cost_unpriced_models": progress.get("cost_unpriced_models") or [],
            "missions": missions,
            "missions_completed": sum(1 for v in missions.values()
                                      if v != "pending"),
            "missions_total": len(missions),
        })

    class DiscoverRequest(BaseModel):
        """طلب اكتشاف الفرص المعكوس (الموجة ٥أ، vision §11) — سوق بدل منتج."""
        market_iso3: str
        year: int | None = None
        sector: str | None = None          # food|textile|industrial|None=الكل
        min_import_usd: float = 0.0
        with_seasonality: bool = False     # pytrends — تكميلية بوزن أدنى

    @app.post("/discover")
    def discover(req: DiscoverRequest, request: Request):
        """اكتشف فرص سوق — reverse discovery: "ما المطلوب في هذا السوق؟"

        مجاني (Comtrade + trends القائمان — صفر مصادر جديدة، §11.5-4)؛
        حارس المصادقة يعمل قبل أي جلب. كل فرصة تحمل hs_code يُمرَّر
        مباشرة إلى /analyze أو /deepen (زر "حلّل هذه الفرصة"، §11.5-3).
        """
        _require_key(request)
        _rate_limit(request)
        import silk_discovery
        return _json(silk_discovery.discover(
            req.market_iso3, req.year, sector=req.sector,
            min_import_usd=req.min_import_usd,
            with_seasonality=req.with_seasonality))

    class TrendRequest(BaseModel):
        """طلب خط الاتجاه متعدد السنوات — multi-year import-trend request."""
        hs_code: str
        market_iso3: str
        end_year: int | None = None
        span: int = 5

    @app.post("/trend")
    def trend(req: TrendRequest, request: Request):
        """خط اتجاه استيراد سوق لرمز عبر مدى سنوات — multi-year import trend.

        مجاني (Comtrade القائم — صفر مصادر جديدة)؛ حارس المصادقة يعمل قبل أي
        جلب. سنة بلا بيانات = فجوة معلنة لا صفر. يغذّي تبويب «الاتجاه» في الواجهة.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_trend
        from silk_data_layer import ISO3_TO_M49
        m49 = ISO3_TO_M49.get((req.market_iso3 or "").upper())
        if not m49:
            raise HTTPException(status_code=422,
                                detail=f"unknown market ISO3: {req.market_iso3}")
        end_year = req.end_year or 2023
        return _json(silk_trend.import_trend(req.hs_code, m49, end_year, req.span))

    @app.get("/diagnostics")
    def diagnostics(request: Request, year: int = 2022):
        """تشخيص المصادر الحيّ — probe each data source live with the server's keys.

        يفحص Comtrade والبنك الدولي وSerper وGoogle Maps وClaude فعلياً ويصنّف:
        متصل/فارغ/محجوب/بلا مفتاح مع تلميح إصلاح. للقراءة فقط، لا يُصدر 500.
        يخبرك على نشرك أيّ مفتاحٍ يعمل وأيّه لا.

        محروسة (مراجعة المشروع): كل نقرة تُطلق نداءاتٍ حيّةً بمفاتيح الخادم
        (Serper/Maps/Claude) — بلا مصادقةٍ وحدِّ معدّلٍ كانت باباً مفتوحاً
        لاستنزاف الرصيد من أي مجهول.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_diagnostics
        try:
            return silk_diagnostics.run_diagnostics(year)
        except Exception as e:  # noqa: BLE001 — diagnostics must never 500
            return {"overall": "unreachable", "agents_can_work": False,
                    "error": f"{type(e).__name__}: {e}", "sources": []}

    @app.get("/ops/last-errors")
    def ops_last_errors(request: Request, n: int = 20):
        """ITEM 5ب (مذكّرة العمليات، تدقيق 2026-07-15): آخر n خطأ تشغيلي —
        فشل تصدير (docx 501)، فشل كاتب (تقرير None)، رفض حجز (429 بحالة
        السقف) — بلا حاجة لسجلات Railway (البروكسي يمنع الوصول لها من
        صندوق تطوير معزول عن الشبكة الحيّة؛ هذه النقطة تقطع تلك الحلقة).

        محروسة كبقية سطوح المشغّل (`/diagnostics`)؛ كل سبب مخزَّن **مُطهَّر
        مسبقاً** (`silk_render._strip_internal_plumbing`، راجع مواقع
        `silk_ops_log.record_error`) — لا `stop_reason`/تتبّع استثناء خام
        يصل هذا الردّ إطلاقاً.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_ops_log
        return _json({"errors": silk_ops_log.last_errors(n)})

    @app.get("/sources")
    def sources(request: Request):
        """خريطة حالة طبقات المصادر الاثنتي عشرة — 12-layer data-source status map.

        For each layer: {name, type (free/paid), wired, key_env[, key_present]}.
        M0: عندما تكون المصادقة مفعّلة، أعلام key_present تُعرض لحامل المفتاح فقط
        — مجهول يرى قائمة الطبقات بلا كشف إعدادات الخادم (ANALYSIS.md §7-5).
        وضع التطوير (بلا SILK_API_KEY) يبقى كما كان: الأعلام ظاهرة.
        """
        _rate_limit(request)
        layers = [
            ("UN Comtrade", "free", None),
            ("World Bank", "free", None),
            ("FAOSTAT", "free", None),
            ("WITS", "free", None),
            ("Google Trends", "free", None),
            ("Google Maps", "free", "GOOGLE_MAPS_API_KEY"),
            ("Web Search", "free", "SEARCH_API_KEY"),
            ("Local retail prices", "paid", "LOCALPRICE_API_KEY"),
            ("Volza", "paid", "VOLZA_API_KEY"),
            ("explee", "paid", "EXPLEE_API_KEY"),
            ("Claude (AI judge)", "ai", "ANTHROPIC_API_KEY"),
            ("Requirements L1 reference (GCC + Saudi exit)", "free", None),
        ]
        expected = _api_key_expected()
        show_flags = (not expected) or hmac.compare_digest(
            request.headers.get("x-api-key", ""), expected)
        out = []
        for name, kind, key_env in layers:
            row = {"name": name, "type": kind, "wired": True, "key_env": key_env}
            if show_flags:  # أعلام المفاتيح للمصرَّح له (أو وضع التطوير) فقط
                row["key_present"] = (bool(os.environ.get(key_env))
                                      if key_env else False)
            out.append(row)
        return _json(out)

    @app.get("/analyses")
    def analyses(request: Request):
        """اسرد التحليلات المحفوظة — list persisted analyses (metadata only).

        C-1: محروسة بالمصادقة — الجرد يكشف ما يُحلَّل من منتجات/أسواق.
        """
        _require_key(request)
        _rate_limit(request)
        return _json(silk_storage.list_analyses())

    @app.get("/analyses/{analysis_id}")
    def analysis(analysis_id: int, request: Request):
        """أعد تحليلًا محفوظًا — fetch one persisted analysis, or 404.

        C-1: محروسة — البلوب المخزّن يحمل بطاقة المنتج الاقتصادية،
        والمعرّفات متسلسلة، فبلا مصادقة يقرؤها مجهول بالتعداد.

        ITEM 5أ (خدمة ذاتية للمشغّل، تدقيق 2026-07-15): `?economics=1` يعيد
        ملخّص اقتصاد التشغيلة فقط (لا البلوب الكامل — قد يبلغ عشرات
        الكيلوبايتات) — يقطع حلقة «الصق لي بيانات Railway» التي كانت
        مستحيلة الإغلاق من صندوق تطوير معزول عن الشبكة الحيّة.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        if str(request.query_params.get("economics") or "").strip().lower() \
                in ("1", "true", "yes"):
            return _json(_economics_summary(analysis_id, found))
        return _json(found)

    def _economics_summary(analysis_id: int, found: dict) -> dict:
        """ITEM 5أ: ملخّص اقتصاد تشغيلة واحدة — llm_usage/mission_usage
        (#96)/cost_usd_by_mission/العدّادات/التكلفة النهائية. تشغيلة سابقة
        لتفعيل الإسناد لكل بعثة تعرض `mission_usage`/`cost_usd_by_mission`
        فارغين صراحة (`mission_usage_available: false`) — فجوة معلنة، لا
        استثناء، ولا اختلاق رقم لتشغيلة أقدم من الميزة. `note` (نص حرّ
        بُنِي خادمياً) يمرّ عبر نفس مُطهِّر السباكة الداخلية دفاعاً بالعمق."""
        de = found.get("data_economics") or {}
        from silk_render import _strip_internal_plumbing
        note = de.get("note")
        return {
            "analysis_id": analysis_id,
            "llm_calls": de.get("llm_calls"),
            "tool_calls": de.get("tool_calls"),
            "store_hits": de.get("store_hits"),
            "cache_hits": de.get("cache_hits"),
            "live_fetches": de.get("live_fetches"),
            "llm_usage": de.get("llm_usage") or {},
            "mission_usage": de.get("mission_usage") or {},
            "mission_usage_available": bool(de.get("mission_usage")),
            "cost_usd_estimate": de.get("cost_usd_estimate"),
            "cost_usd_by_model": de.get("cost_usd_by_model") or {},
            "cost_usd_by_mission": de.get("cost_usd_by_mission") or {},
            "cost_unpriced_models": de.get("cost_unpriced_models") or [],
            "note": _strip_internal_plumbing(note) if note else None,
        }

    @app.get("/analyses/{analysis_id}/brief")
    def brief(analysis_id: int, request: Request):
        """المختصر (§10.4) — one-page mobile-style brief from the ONE template.

        C-1: محروسة — تشتق من التحليل المخزّن نفسه (بطاقة/هوامش).
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        from silk_render import build_view
        from silk_reports import render_brief
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(render_brief(build_view(found)))

    @app.get("/analyses/{analysis_id}/report.docx")
    def report_docx(analysis_id: int, request: Request):
        """تقرير Word — derived from the ONE view-model (build_view).

        فصل الجمهور (بلاغ المالك): نتيجة بحث عميق (/research) تُصدَّر بقالب
        **العميل** (`render_client_docx`) بمفردات تجارية بحتة بلا تِلِمِتري —
        هو ما يستلمه العميل الدافع. تِلِمِتري المشغّل (بعثات/حالات/اقتصاد
        بيانات) يبقى على اللوحة (web/index.html)، ويبقى التصدير التشغيلي
        الكامل للمدقّق متاحاً عبر `?internal=1`. نتيجة /analyze الكلاسيكية
        (بلا deep_research) تبقى على `render_docx` العادي.

        C-1: محروسة. 404 للتحليل المفقود؛ 501 بلا python-docx.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        import tempfile
        from silk_render import build_view
        from silk_reports import render_client_docx, render_docx
        from fastapi.responses import FileResponse
        view = build_view(found)
        # التصدير الكامل التشغيلي للمدقّق فقط عند طلب صريح.
        internal = str(request.query_params.get("internal") or "").lower() in (
            "1", "true", "yes")
        is_research = bool(view.get("deep_research"))
        try:
            if is_research and not internal:
                path = render_client_docx(
                    view, os.path.join(tempfile.mkdtemp(), "report.docx"))
                fname = f"silk_client_report_{analysis_id}.docx"
            else:
                path = render_docx(
                    view, os.path.join(tempfile.mkdtemp(), "report.docx"))
                fname = f"silk_report_{analysis_id}.docx"
        except RuntimeError as e:
            # ITEM 5ب: سبب ثابت عام لا نص الاستثناء الخام — رسالة حارس
            # التصدير (`_client_assert_clean`) قد تقتبس فئة/شظية داخلية
            # (مثال: "algorithm_language: «درجة الثقة»") لا يلتقطها مُطهِّر
            # السباكة العام (يعرّب EN→AR، لا يحذف أسماء فئات عربية موجودة
            # أصلاً) — فبدل مطاردة كل شكل تسريب محتمل بتعبير نمطي جديد،
            # لا يصل /ops/last-errors نص الاستثناء إطلاقاً؛ ردّ الـHTTP نفسه
            # (الذي يخصّ الطالب لا سطحاً عاماً) يبقى يحمل str(e) كاملاً كما
            # كان دوماً — لا تغيير هناك.
            import silk_ops_log
            silk_ops_log.record_error(
                "export_failure",
                "فشل تصدير docx (منصّة ناقصة أو محتوى رفضه حارس التصدير) — "
                "التفصيل الكامل في استجابة الطلب الأصلي، لا هنا",
                context={"analysis_id": analysis_id})
            raise HTTPException(status_code=501, detail=str(e))
        return FileResponse(
            path, filename=fname,
            media_type="application/vnd.openxmlformats-officedocument"
                       ".wordprocessingml.document")

    @app.get("/analyses/{analysis_id}/report.md")
    def report_md(analysis_id: int, request: Request):
        """التقرير الكامل Markdown (Stage 5، §7) — من القالب الموحّد نفسه.

        نفس عقد report.docx (محروسة، 404 للمفقود) لكن نصّ خالص بلا تبعيات —
        يعمل حيث لا python-docx، وهو مصدر اشتقاق PDF على النشر.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        from silk_render import build_view
        from silk_reports import render_markdown
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(render_markdown(build_view(found)),
                                 media_type="text/markdown; charset=utf-8")

    @app.post("/analyses/{analysis_id}/report")
    def regenerate_report(analysis_id: int, request: Request):
        """أعد توليد التقرير الكامل من بحث محفوظ — نداء كاتب واحد (+مراجع)
        فقط، بلا إعادة تشغيل أي بعثة من الاثنتي عشرة ولا المحلل الشامل.

        بلاغ حي (تمور/هولندا): كاتب التقرير قد يفشل (مهلة/شبكة) رغم نجاح
        كل شيء آخر في تشغيلة مكلفة كاملة — هذه النقطة تُنقِذ تلك التشغيلة
        بتكلفة نداء واحد بدل إعادة البحث كله (§سنتات لا دولارات)، ومصدر
        اختبار رخيص لإصلاحات مهلة الكاتب. تقرأ نقاط تفتيش البعثات
        (`silk_storage.load_mission_checkpoints`، مخزَّنة فور اكتمال كل
        بعثة بصرف النظر عن مصير الكاتب لاحقاً) بدل إعادة بنائها من
        `json_blob` النهائي — نفس آلية استئناف `/research`، لا منطق موازٍ.
        تحدّث السجل المخزَّن بالتقرير الجديد وتعيد بناء القالب الموحّد +
        بوابة الجودة قبل الحفظ.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        dr = found.get("deep_research")
        if not dr:
            raise HTTPException(
                status_code=400,
                detail=f"analysis {analysis_id} is not a /research run "
                       "(no deep_research section) — nothing to regenerate")
        ai_ok, ai_note = _free_ai_extras_allowed()
        if not ai_ok:
            return _json({"report": None, "note": ai_note})
        mission_reports = silk_storage.load_mission_checkpoints(analysis_id)
        if not mission_reports:
            raise HTTPException(
                status_code=409,
                detail=f"no mission checkpoints stored for analysis "
                       f"{analysis_id} — cannot regenerate without them")
        from silk_ai_judge import write_reviewed_report
        analyst_summary = ((dr.get("analyst") or {}).get("report") or {}) \
            .get("summary", "")
        verdict = dr.get("verdict") or {}
        market_name = (found.get("market") or {}).get("name_en", "")
        trace_id = dr.get("trace_id")
        report_out = write_reviewed_report(
            mission_reports, analyst_summary, verdict,
            found.get("product", ""), market_name, trace_id=trace_id,
            hs_code=found.get("hs_code"))
        # H1 (تدقيق): إعادة التوليد كانت تطمس التقرير المخزَّن بـreport_out حتى
        # لو فشل الكاتب هذه المرة (report=None) — فيُفقَد تقرير سابق ناجح كلّفت
        # تشغيلته الكاملة، وهو بالضبط ما تُنقِذه هذه النقطة. الآن: لا نحفظ null
        # فوق تقرير سابق ناجح؛ نُبقي المخزَّن ونُبلّغ الفشل (السجل لا يُلمَس).
        from silk_render import _strip_internal_plumbing
        prior_report = (dr.get("report") or {}).get("report")
        if not report_out.get("report"):
            # ITEM 5ب: فشل كاتب أثناء regen — يُسجَّل بصرف النظر عن وجود
            # تقرير سابق محفوظ أم لا (كلاهما فشل كاتب حقيقي يستحق الرصد).
            import silk_ops_log
            silk_ops_log.record_error(
                "writer_failure",
                _strip_internal_plumbing(report_out.get("failure_reason") or "")
                or "فشل الكاتب بلا سبب مسجَّل",
                context={"analysis_id": analysis_id, "regen": True,
                         "prior_preserved": bool(prior_report)})
        if not report_out.get("report") and prior_report:
            return _json({"report": None, "regenerated": False,
                          "note": "تعذّرت إعادة توليد التقرير هذه المرة؛ "
                                  "التقرير السابق محفوظ كما هو دون تغيير.",
                          "failure_reason": _strip_internal_plumbing(
                              report_out.get("failure_reason") or "")})
        found["deep_research"]["report"] = report_out
        found["analysis_id"] = analysis_id
        found["view"] = _view(found)
        _attach_quality_gate(found, trace_id)
        silk_storage.save_analysis(found, analysis_id=analysis_id)
        return _json(found)

    class AskRequest(BaseModel):
        """سؤال فوق تحليل قائم (10b) — question over a stored analysis."""
        question: str

    @app.post("/analyses/{analysis_id}/ask")
    def ask_analysis(analysis_id: int, req: AskRequest, request: Request):
        """دردشة سياقية فوق تحليل مخزّن (10b) — من الذاكرة حصراً.

        لا إعادة تشغيل وكلاء، لا نداء خارجي سوى نداء كلود الواحد؛ الأرضية
        سياق التحليل المحسوب (analysis_context) والسؤال داخل العزل. ما ليس
        في السياق يُعلن «غير متوفر في هذا التحليل» — لا اختلاق. نفس حارس
        إضافات كلود المجانية (H2): نشر غير محمي يحجبها، والمحمي يحجز من
        السقف اليومي.
        """
        _require_key(request)
        _rate_limit(request)
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        ai_ok, ai_note = _free_ai_extras_allowed()
        if not ai_ok:
            return _json({"answer": None, "note": ai_note})
        from silk_ai_judge import answer_about_analysis, failure_reason
        from silk_render import _strip_internal_plumbing, analysis_context
        out = answer_about_analysis(req.question, analysis_context(found))
        if out is None:
            # بلاغ حي (بحث "تمور/هولندا"): None لا يعني بالضرورة غياب
            # المفتاح — قد يكون فشل نداء فعلي (مهلة/شبكة) رغم مفتاح فعّال.
            # H3 (تدقيق): كان يعيد failure_reason() خاماً — يحمل
            # empty_response/stop_reason/«راجع سجلّات الخادم». يمرّ الآن عبر
            # نفس مُطهِّر طبقة العرض (H4 يُعرّب تلك الرموز).
            return _json({"answer": None,
                          "note": _strip_internal_plumbing(failure_reason())})
        # سدّ تسريب: جواب كلود يمرّ بلا أي مُطهِّر مباشرة للعميل — كلود قد
        # يقتبس مفتاحاً داخلياً حرفياً من السياق رغم تعريب السياق نفسه، أو
        # يستخدم رمز حكم خام بنفسه؛ نفس مُطهِّر طبقة العرض (مرة واحدة).
        if out.get("answer"):
            out["answer"] = _strip_internal_plumbing(out["answer"])
        return _json(out)

    class SnapshotRequest(BaseModel):
        """لقطة سريعة لمنتج جديد (R4) — هل يستحق دراسة كاملة؟"""
        product: str
        hs_code: "str | None" = None
        market: "str | None" = None
        refresh: bool = False
        confirm: bool = False

    @app.post("/products/snapshot")
    def product_snapshot(req: SnapshotRequest, request: Request):
        """لقطة سريعة لمنتج × سوق (R4) — تعيد استخدام بعثة الأسعار مقيَّدةً.

        التدفق: (١) المخزن أولاً ما لم يُطلب تحديث — تكرار السؤال مجاني بلا
        حرق أرصدة. (٢) بلا confirm=true تُعيد التكلفة المقدَّرة فقط ولا تشغّل
        (التكلفة تُعرَض قبل التشغيل). (٣) مع confirm تمرّ بنفس حارس إضافات
        كلود المجانية (_free_ai_extras_allowed): تحجز تفعيلة واحدة من السقف
        اليومي، وتُحجَب على النشر غير المحمي، وتتدهور معلنةً عند النفاد —
        ثم تشغّل وتخزّن. لا اختلاق: فجوات معلنة بلا مفتاح/شبكة.
        """
        _require_key(request)
        _rate_limit(request)
        import silk_snapshot
        product = (req.product or "").strip()
        if not product:
            raise HTTPException(status_code=422, detail="product required")

        from silk_market_resolver import resolve_market
        market_ref, suggestions = resolve_market(
            req.market or silk_snapshot._DEFAULT_PROBE_MARKET)
        if market_ref is None:
            raise HTTPException(status_code=422, detail={
                "error": f"unknown or ambiguous market {req.market!r}",
                "suggestions": suggestions})

        hs_code = (req.hs_code or "").strip() or None
        hs_note = None
        if not hs_code:
            from silk_hs_resolver import resolve as resolve_hs
            dp = resolve_hs(product)
            hs_code = dp.value
            if hs_code is None:
                hs_note = dp.note   # فجوة معلنة — لا اختلاق رمز HS

        # (١) المخزن أولاً — تكرار مجاني بلا حجز
        if not req.refresh:
            cached = silk_storage.get_product_snapshot(hs_code, market_ref.iso3)
            if cached is not None:
                return _json({"snapshot": cached, "cached": True,
                              "cost": {"claude_activations": 0,
                                       "note": "من المخزن — بلا تكلفة"}})

        est = {"claude_activations": 1,
               "note": "لقطة سريعة = تفعيلة كلود واحدة (بعثة الأسعار مقيَّدة "
                       "الميزانية) — تُحتسب من السقف اليومي"}

        # (٢) التكلفة قبل التشغيل — بلا confirm لا تشغيل ولا حجز
        if not req.confirm:
            return _json({"snapshot": None, "cached": False, "cost": est,
                          "would_exceed_cap": silk_usage.would_exceed_cap(1),
                          "hs_note": hs_note,
                          "note": "أكّد بإرسال confirm=true للتشغيل — تُحتسب "
                                  "تفعيلة واحدة من السقف اليومي"})

        # (٣) confirm — نفس حارس المدفوع المجاني (حجز/حجب/تدهور معلن)
        ai_ok, ai_note = _free_ai_extras_allowed()
        if not ai_ok:
            return _json({"snapshot": None, "cached": False, "cost": est,
                          "blocked_note": ai_note})

        snap = silk_snapshot.quick_snapshot(product, hs_code, market_ref)
        if hs_note:
            snap["hs_note"] = hs_note
        silk_storage.save_product_snapshot(hs_code, market_ref.iso3, snap)
        return _json({"snapshot": snap, "cached": False, "cost": est})

    class OutcomeRequest(BaseModel):
        """جسم تسجيل النتيجة الفعلية — actual-outcome body (wave 1)."""
        outcome: str

    @app.patch("/analyses/{analysis_id}/outcome")
    def set_outcome(analysis_id: int, req: OutcomeRequest, request: Request):
        """سجّل ما حدث فعلاً لتحليل — record the real-world outcome (wave 1).

        يبني سجل المصداقية التراكمي (عمودا outcome/outcome_date). 404 إن لم
        يوجد التحليل؛ لا يغيّر بيانات التحليل نفسها إطلاقاً.
        M0: خلف المصادقة وتحديد المعدّل — كانت الوحيدة المكشوفة، فكان بوسع أي
        مجهول الكتابة فوق سجل النتائج بالتعداد (ANALYSIS.md §7-1).
        """
        _require_key(request)
        _rate_limit(request)
        outcome = (req.outcome or "").strip()
        if not outcome:
            raise HTTPException(status_code=422, detail="outcome must be non-empty")
        if not silk_storage.set_outcome(analysis_id, outcome):
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        return {"id": analysis_id, "outcome": outcome, "recorded": True}

    # الواجهة الثابتة على نفس الخدمة — serve the static frontend at "/" so one
    # Render service hosts BOTH the API and the UI (same origin, no CORS needed).
    # Registered last so the API routes above take precedence over static files.
    web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    if os.path.isdir(web_dir):
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


# تطبيق على مستوى الوحدة — module-level app, None when fastapi is unavailable.
try:
    app = create_app()
except RuntimeError:  # fastapi absent: keep import working, hold None.
    app = None
    log.warning(_PIP_HINT)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        import uvicorn
    except ImportError:
        print(_PIP_HINT)
    else:
        uvicorn.run(create_app(), host="127.0.0.1", port=8000)
