"""ذاكرة سِلك التراكمية (RAG) — Silk cumulative memory via embeddings (V4).

عند اكتمال أي تحليل، تُولَّد Embeddings لخلاصته وتُحفظ (silk_db.market_vectors).
عند بحث جديد، تُجلب أقرب التقارير السابقة (Similarity Search) لتُغذّى كـ«سياق
تاريخي» للتركيب — فيصبح التحليل تراكمياً ومستنداً لمعرفة المنصّة السابقة.

مبادئ:
  • بلا مفتاح تضمين (VOYAGE_API_KEY / OPENAI_API_KEY) الذاكرة **معطّلة بأمان**
    (لا تخزين ولا استرجاع) — لا اختلاق، ولا نداء شبكة.
  • pgvector يُفعَّل إن سمحت قاعدة Postgres؛ وإلا نعود لعمود JSON محمول + تشابه
    جيب التمام (cosine) في بايثون — يعمل على SQLite/CI أيضاً. الفهرس الأصلي
    لـ pgvector هو تحسين إنتاجي لاحق للحجوم الكبيرة.

المزوّد الافتراضي Voyage AI (شريك التضمين الموصى به مع Anthropic)؛ OpenAI بديل.
'requests' يُستورد بكسل. أي فشل => None (الذاكرة تبقى معطّلة، بلا كسر التحليل).
"""
from __future__ import annotations

import logging
import math
import os

log = logging.getLogger(__name__)

_TIMEOUT = 30
_VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
_OPENAI_URL = "https://api.openai.com/v1/embeddings"
_VOYAGE_MODEL = os.environ.get("SILK_EMBED_MODEL_VOYAGE", "voyage-3")
_OPENAI_MODEL = os.environ.get("SILK_EMBED_MODEL_OPENAI", "text-embedding-3-small")


def _provider() -> str | None:
    """المزوّد المتاح — 'voyage' or 'openai' if its key is set, else None."""
    if os.environ.get("VOYAGE_API_KEY", "").strip():
        return "voyage"
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "openai"
    return None


def available() -> bool:
    """هل الذاكرة مفعّلة؟ — is an embeddings provider configured?"""
    return _provider() is not None


def embed(texts: list[str]) -> list[list[float]] | None:
    """ولّد تضمينات — embeddings for a list of texts, or None if unavailable.

    No key -> None (memory disabled, no network). Any provider error -> None.
    Never fabricates a vector.
    """
    texts = [t for t in (texts or []) if t and t.strip()]
    if not texts:
        return None
    prov = _provider()
    if prov is None:
        return None
    try:
        import requests  # lazy: keep module importable offline/keyless
        if prov == "voyage":
            r = requests.post(_VOYAGE_URL, timeout=_TIMEOUT,
                              headers={"Authorization": "Bearer " + os.environ["VOYAGE_API_KEY"].strip(),
                                       "Content-Type": "application/json"},
                              json={"input": texts, "model": _VOYAGE_MODEL})
        else:
            r = requests.post(_OPENAI_URL, timeout=_TIMEOUT,
                              headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"].strip(),
                                       "Content-Type": "application/json"},
                              json={"input": texts, "model": _OPENAI_MODEL})
        r.raise_for_status()
        data = r.json().get("data") or []
        vecs = [d.get("embedding") for d in data if d.get("embedding")]
        return vecs if len(vecs) == len(texts) else None
    except Exception as e:  # noqa: BLE001 — memory is best-effort, never crash analysis
        log.warning("embedding provider (%s) failed: %s", prov, e)
        return None


def cosine(a: list[float], b: list[float]) -> float:
    """جيب التمام — cosine similarity of two vectors (0 if degenerate)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _summary_text(result: dict) -> str:
    """نصّ الخلاصة للتضمين — a compact embed text from a finished analysis."""
    parts = [f"product: {result.get('product')}", f"hs: {result.get('hs_code')}"]
    markets = result.get("markets") or []
    if markets:
        top = markets[0]
        parts.append(f"top market: {top.get('country')}")
        syn = top.get("synthesis") or {}
        if syn.get("verdict"):
            parts.append("verdict: " + str(syn["verdict"]))
        for k in ("opportunities", "risks", "recommendations"):
            vals = syn.get(k) or []
            if vals:
                parts.append(k + ": " + " | ".join(str(v) for v in vals[:3]))
        if not syn:
            parts.append("verdict: " + str((top.get("jury") or {}).get("verdict", "")))
    return "\n".join(p for p in parts if p)


def remember_report(result: dict) -> int | None:
    """احفظ خلاصة التقرير في الذاكرة — embed + store a finished analysis (best-effort).

    No-op (returns None) when embeddings are unavailable or on any error — the
    analysis itself is never affected.
    """
    if not result or not result.get("classified") or not available():
        return None
    try:
        import silk_db
        text = _summary_text(result)
        vecs = embed([text])
        if not vecs:
            return None
        markets = result.get("markets") or []
        market = markets[0].get("country") if markets else None
        silk_db.try_enable_pgvector()  # best-effort; safe on repeat
        return silk_db.store_market_vector(
            result.get("product"), result.get("hs_code"), market,
            result.get("year"), text, vecs[0])
    except Exception as e:  # noqa: BLE001 — memory must not break the pipeline
        log.warning("remember_report failed: %s", e)
        return None


def similar_reports(product: str, market: str = "", k: int = 3,
                    min_score: float = 0.75) -> list[dict]:
    """أقرب تقارير سابقة — top-k prior reports similar to product+market.

    Embeds the query, cosine-ranks stored vectors, returns
    [{product, market, year, summary, score}] above min_score. Empty when memory
    is disabled / nothing stored / nothing similar. Never fabricates.
    """
    if not available():
        return []
    try:
        import silk_db
        q = f"product: {product}\nmarket: {market}".strip()
        qv = embed([q])
        if not qv:
            return []
        qv = qv[0]
        rows = silk_db.list_market_vectors()
        scored = []
        for r in rows:
            emb = r.get("embedding")
            if not emb or len(emb) != len(qv):
                continue
            s = cosine(qv, emb)
            if s >= min_score:
                scored.append({"product": r.get("product"), "market": r.get("market"),
                               "year": r.get("year"), "summary": r.get("summary"),
                               "score": round(s, 3)})
        scored.sort(key=lambda d: d["score"], reverse=True)
        return scored[: max(1, k)]
    except Exception as e:  # noqa: BLE001
        log.warning("similar_reports failed: %s", e)
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Silk vectors (RAG) — embeddings available?", available())
    print("cosine([1,0,0],[1,0,0]) =", cosine([1, 0, 0], [1, 0, 0]))
    print("cosine([1,0],[0,1]) =", cosine([1, 0], [0, 1]))
