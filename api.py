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


def create_app():
    """أنشئ تطبيق FastAPI — build the FastAPI app, or raise if fastapi is absent."""
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import JSONResponse
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(_PIP_HINT) from exc

    import silk_engine
    import silk_hs_resolver
    import silk_storage

    app = FastAPI(title="Silk Market Intelligence API",
                  description="Real public-data export-market analysis "
                              "(UN Comtrade + World Bank). Preliminary, never fabricated.")

    # CORS: يسمح لواجهة Netlify بالنداء — allow the static frontend to call the API.
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
        with_volza: bool = False
        with_explee: bool = False
        persist: bool = False

    def _json(payload: object):
        """رد JSON آمن للـ DataPoint — JSONResponse with DataPoint-safe payload."""
        return JSONResponse(content=_to_jsonable(payload))

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
        return {"status": "ok", "deps": deps}

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

    @app.post("/analyze")
    def analyze(req: AnalyzeRequest):
        """حلّل منتجًا عبر الأسواق — run the full engine.analyze pipeline."""
        result = silk_engine.analyze(
            req.product, year=req.year, with_trends=req.with_trends,
            with_tariffs=req.with_tariffs, with_faostat=req.with_faostat,
            with_maps=req.with_maps, with_websearch=req.with_websearch,
            with_volza=req.with_volza, with_explee=req.with_explee,
            persist=req.persist)
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
            ("Volza", "paid", "VOLZA_API_KEY"),
            ("explee", "paid", "EXPLEE_API_KEY"),
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
