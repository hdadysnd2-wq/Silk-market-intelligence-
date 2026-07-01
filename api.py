"""واجهة REST لمنصّة سِلك — FastAPI service exposing the Silk engine.

Lazy-imports FastAPI/pydantic inside create_app() so that `import api` works
offline and even when fastapi is absent (founding principle: graceful degrade,
never crash, never fabricate). Module-level `app` is None when fastapi is missing.

Run:  python3 api.py   (needs `pip install fastapi uvicorn`).
"""
import logging
import os

from silk_jsonutil import to_jsonable as _to_jsonable

log = logging.getLogger(__name__)

_PIP_HINT = "FastAPI/uvicorn not installed — run: pip install fastapi uvicorn"


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


def create_app():
    """أنشئ تطبيق FastAPI — build the FastAPI app, or raise if fastapi is absent."""
    try:
        from fastapi import Depends, FastAPI, HTTPException, Header, Request
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(_PIP_HINT) from exc

    import silk_auth
    import silk_db
    import silk_hs_resolver
    import silk_jobs
    import silk_ratelimit
    import silk_storage

    app = FastAPI(title="Silk Market Intelligence API",
                  description="Real public-data export-market analysis "
                              "(UN Comtrade + World Bank). Preliminary, never fabricated.")

    # CORS: يسمح لواجهة خارجية بالنداء — allow an external frontend to call the API.
    # افتراضيًا أي أصل؛ قيّده بـ CORS_ORIGINS (مفصولة بفواصل) في الإنتاج.
    _origins = os.environ.get("CORS_ORIGINS", "*").strip()
    allow = ["*"] if _origins == "*" else [o.strip() for o in _origins.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=allow,
                       allow_methods=["*"], allow_headers=["*"])

    class AnalyzeRequest(BaseModel):
        """طلب تحليل منتج — analyze request body."""
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
        persist: bool = False

    class RequestLinkBody(BaseModel):
        """طلب رابط دخول سحري — magic-link request body."""
        email: str

    def _json(payload: object):
        """رد JSON آمن للـ DataPoint — JSONResponse with DataPoint-safe payload."""
        return JSONResponse(content=_to_jsonable(payload))

    def _client_ip(request: Request) -> str:
        """عنوان العميل — best-effort client IP for pre-auth rate limiting."""
        return request.client.host if request.client else "unknown"

    def _current_user_id(authorization: str = Header(default="")) -> int:
        """المستخدم الحالي — resolve the bearer session token, or 401.

        Guards every cost-incurring endpoint (analyze/jobs/analyses/usage) —
        an unauthenticated visitor cannot trigger paid work (founding V3
        production-readiness requirement: no free-riding on Claude/paid tools).
        """
        token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
        user_id = silk_auth.session_user_id(token)
        if user_id is None:
            raise HTTPException(status_code=401,
                                detail="unauthorized — missing/expired session token; "
                                       "request a login link via POST /auth/request-link")
        return user_id

    def _enforce_rate_limit(identity: str) -> None:
        """طبّق حدود الاستخدام أو أعد 429 — enforce caps, translating to HTTP 429."""
        try:
            silk_ratelimit.enforce_analysis_limits(identity)
        except silk_ratelimit.RateLimitExceeded as e:
            raise HTTPException(
                status_code=429,
                detail=f"rate limit exceeded ({e.scope}): max {e.limit}; "
                       f"retry after {e.retry_after_seconds}s") from e

    @app.get("/health")
    def health():
        """فحص الصحّة — liveness plus optional-dep availability flags."""
        deps = {}
        for name in ("fastapi", "uvicorn", "pytrends", "streamlit", "requests",
                    "sqlalchemy", "redis", "rq"):
            try:
                __import__(name)
                deps[name] = True
            except Exception:  # noqa: BLE001
                deps[name] = False
        return {"status": "ok", "deps": deps,
                "database_configured": bool(os.environ.get("DATABASE_URL")),
                "redis_configured": bool(os.environ.get("REDIS_URL"))}

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

    @app.post("/auth/request-link")
    def request_link(body: RequestLinkBody, request: Request):
        """اطلب رابط دخول سحري — issue a magic login link, emailed or logged.

        Rate-limited by IP (pre-auth, so no user id exists yet). Response is
        identical whether the email is known or not (no user enumeration).
        """
        _enforce_rate_limit(f"ip:{_client_ip(request)}")
        base_url = os.environ.get("PUBLIC_BASE_URL", "").strip() or str(request.base_url)
        return _json(silk_auth.request_magic_link(body.email, base_url))

    @app.get("/auth/verify")
    def verify_link(token: str):
        """تحقق من الرابط وأصدر جلسة — consume a one-time token, issue a session."""
        out = silk_auth.verify_magic_link(token)
        if out is None:
            raise HTTPException(status_code=400,
                                detail="invalid, expired, or already-used login link")
        return _json(out)

    @app.post("/analyze")
    def analyze(req: AnalyzeRequest, user_id: int = Depends(_current_user_id)):
        """أرسل تحليلاً للتنفيذ بالخلفية — enqueue analyze() as a background job.

        Requires a session (Authorization: Bearer <token>, via /auth/verify) and
        is rate-limited per user. Returns {job_id, status, cached} immediately —
        poll GET /jobs/{job_id} for the result. own_price (with_localprice=True)
        attaches a price-positioning comparison per top market.
        """
        _enforce_rate_limit(str(user_id))
        out = silk_jobs.enqueue_analysis(req.model_dump(), user_id)
        return _json(out)

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str, user_id: int = Depends(_current_user_id)):
        """حالة مهمة — poll a background analysis job's status/result."""
        status = silk_jobs.job_status(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"job {job_id} not found")
        row = silk_db.get_job(job_id)
        if row is not None and row.get("user_id") is not None and row["user_id"] != user_id:
            raise HTTPException(status_code=404, detail=f"job {job_id} not found")
        return _json(status)

    @app.get("/usage")
    def usage(user_id: int = Depends(_current_user_id)):
        """عدّاد الاستخدام الشهري — analyses this month + a rough cost estimate.

        Rough, not a final invoice (see README's cost table) — the per-analysis
        figure is a configurable constant (SILK_EST_COST_PER_ANALYSIS_USD),
        not a computed Claude/infra bill.
        """
        count = silk_db.count_jobs_this_month(user_id)
        per_analysis = float(os.environ.get("SILK_EST_COST_PER_ANALYSIS_USD", "1.5"))
        return _json({"analyses_this_month": count,
                      "estimated_cost_usd": round(count * per_analysis, 2),
                      "note": "تقدير تقريبي فقط، ليس فاتورة نهائية — "
                              "rough estimate only, not a final invoice."})

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
        ]
        return _json([
            {"name": name, "type": kind, "wired": True, "key_env": key_env,
             "key_present": bool(os.environ.get(key_env)) if key_env else False}
            for name, kind, key_env in layers
        ])

    @app.get("/analyses")
    def analyses(user_id: int = Depends(_current_user_id)):
        """اسرد التحليلات المحفوظة — list persisted analyses (metadata only).

        Note: silk_storage predates per-user auth and isn't ownership-scoped
        yet (any signed-in user sees all persisted analyses) — auth here only
        blocks anonymous access. Per-user scoping is a follow-up once
        analyses persistence moves into silk_db alongside jobs.
        """
        return _json(silk_storage.list_analyses())

    @app.get("/analyses/{analysis_id}")
    def analysis(analysis_id: int, user_id: int = Depends(_current_user_id)):
        """أعد تحليلًا محفوظًا — fetch one persisted analysis, or 404."""
        found = silk_storage.get_analysis(analysis_id)
        if found is None:
            raise HTTPException(status_code=404,
                                detail=f"analysis {analysis_id} not found")
        return _json(found)

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
