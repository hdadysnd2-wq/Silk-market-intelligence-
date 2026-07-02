"""واجهة REST لمنصّة سِلك — FastAPI service exposing the Silk engine.

Lazy-imports FastAPI/pydantic inside create_app() so that `import api` works
offline and even when fastapi is absent (founding principle: graceful degrade,
never crash, never fabricate). Module-level `app` is None when fastapi is missing.

Run:  python3 api.py   (needs `pip install fastapi uvicorn`).
"""
import dataclasses
import logging
import os

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

    # CORS (الموجة ٠): الافتراضي صار **نفس الأصل فقط** (الواجهة تُقدَّم من نفس
    # الخدمة فلا تحتاج CORS). للواجهات المنفصلة (Netlify) اضبط CORS_ORIGINS
    # بقائمة أصول مفصولة بفواصل؛ "*" لم يعد افتراضياً ويتطلب ضبطاً صريحاً.
    allow = _cors_origins()
    if allow:
        app.add_middleware(CORSMiddleware, allow_origins=allow,
                           allow_methods=["*"], allow_headers=["*"])

    class ProductCard(BaseModel):
        """بطاقة المنتج (الموجة ٤، vision §2) — اختيارية، تفعّل محرّك التقاطع."""
        cost_per_unit: float
        unit: str | None = None
        tier: str | None = None            # premium|standard|economy
        monthly_capacity: float | None = None
        shipping_per_unit: float | None = None  # افتراض شحن معلَن قابل للتعديل

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
        product_card: ProductCard | None = None
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
        product_card: ProductCard | None = None
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
        unprotected = _unprotected_paid_keys()
        if unprotected:
            health["warnings"] = [
                "paid keys present without SILK_API_KEY ("
                + ", ".join(unprotected)
                + ") — paid layers will refuse with 503 until SILK_API_KEY "
                  "is set (or the paid keys are removed)"]
        return health

    @app.get("/resolve/{name}")
    def resolve(name: str):
        """صنّف اسم منتج إلى HS6 — resolve a product name to an HS6 DataPoint."""
        dp = silk_hs_resolver.resolve(name)
        return _json({"hs_code": dp.value, "confidence": dp.confidence,
                      "note": dp.note, "source": dp.source,
                      "retrieved_at": dp.retrieved_at})

    @app.get("/index")
    def index(q: str = "", limit: int = 20):
        """فهرس المنتجات للبحث — product search index for the dashboard combobox."""
        return _json(_index_search(q, limit))

    def _require_key(request: Request) -> None:
        """حارس المصادقة (الموجة ٠) — 401 before any agent when key mismatches."""
        expected = _api_key_expected()
        if expected and request.headers.get("x-api-key", "") != expected:
            raise HTTPException(status_code=401,
                                detail="missing or invalid API key "
                                       "(send X-API-Key header)")

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
        if paid_requested and silk_usage.would_exceed_cap(paid_requested):
            raise HTTPException(
                status_code=429,
                detail="daily paid-layer cap reached (SILK_PAID_DAILY_CAP) — "
                       "retry tomorrow or raise the cap")
        if paid_requested:
            silk_usage.record_paid_calls(paid_requested)

    @app.post("/analyze")
    def analyze(req: AnalyzeRequest, request: Request):
        """حلّل منتجًا عبر الأسواق (المسار العادي، مجاني حصراً) — free-only path.

        الموجة ٢: لا حقول مدفوعة في النموذج أصلاً، فلا يصل المحرّكَ أي علم
        مدفوع من هنا — الحصر بنيوي لا افتراضي. التعميق عبر POST /deepen.
        حارس الموجة ٠ (المصادقة) يعمل قبل أي وكيل.
        """
        _require_key(request)
        result = silk_engine.analyze(
            req.product, year=req.year, with_trends=req.with_trends,
            with_tariffs=req.with_tariffs, with_faostat=req.with_faostat,
            with_maps=req.with_maps, with_websearch=req.with_websearch,
            with_competitors=req.with_competitors,
            with_channels=req.with_channels,
            with_importers=req.with_importers,
            with_requirements=req.with_requirements,
            product_card=(req.product_card.model_dump()
                          if req.product_card else None),
            persist=req.persist)
        result["view"] = _view(result)
        return _json(result)

    @app.post("/deepen")
    def deepen(req: DeepenRequest, request: Request):
        """عمّق التحليل (المسار المدفوع الوحيد) — the only paid-layer path.

        يعمل داخل silk_context.deepen_context() فيسمح حارس BaseAgent البنيوي
        بتشغيل الوكلاء المدفوعين (localprice/volza/explee) — خارجه يستحيل
        تنفيذهم حتى مع مفاتيح مضبوطة. حارسا الموجة ٠ (401 المصادقة، 429
        السقف) يعملان قبل أي وكيل.
        """
        _require_key(request)
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
                product_card=(req.product_card.model_dump()
                              if req.product_card else None),
                persist=req.persist)
        result["view"] = _view(result)
        return _json(result)

    @app.get("/sources")
    def sources():
        """خريطة حالة المصادر التسع — 9-layer data-source status map.

        For each layer: {name, type (free/paid), wired, key_env, key_present}.
        key_present reflects whether the key env var is actually set right now.
        """
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
        return _json([
            {"name": name, "type": kind, "wired": True, "key_env": key_env,
             "key_present": bool(os.environ.get(key_env)) if key_env else False}
            for name, kind, key_env in layers
        ])

    @app.get("/analyses")
    def analyses():
        """اسرد التحليلات المحفوظة — list persisted analyses (metadata only)."""
        return _json(silk_storage.list_analyses())

    @app.get("/analyses/{analysis_id}")
    def analysis(analysis_id: int):
        """أعد تحليلًا محفوظًا — fetch one persisted analysis, or 404."""
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        return _json(found)

    class OutcomeRequest(BaseModel):
        """جسم تسجيل النتيجة الفعلية — actual-outcome body (wave 1)."""
        outcome: str

    @app.patch("/analyses/{analysis_id}/outcome")
    def set_outcome(analysis_id: int, req: OutcomeRequest):
        """سجّل ما حدث فعلاً لتحليل — record the real-world outcome (wave 1).

        يبني سجل المصداقية التراكمي (عمودا outcome/outcome_date). 404 إن لم
        يوجد التحليل؛ لا يغيّر بيانات التحليل نفسها إطلاقاً.
        """
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
