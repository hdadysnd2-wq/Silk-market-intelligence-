# Silk Market Intelligence — Engineering Audit (PROJECT REPORT)

> **Method:** every claim anchored to `file:line` (same discipline as `docs/AUDIT_STATUS.md`); "not found" is stated explicitly.
> **Revision reviewed:** `main` + this PR. **Scope:** ~7,700 LOC Python · one self-contained web UI · 108 hermetic tests.
> **Founding invariant:** the system never fabricates data — every value is `DataPoint(value, source, confidence, note, retrieved_at)`; on failure `value=None, confidence=0.0`.

## Findings at a glance

| Area | Rating | Headline |
|---|---|---|
| Architecture | 🟢 Strong, evolving | Principled modular monolith; flat namespace + procedural core are the debt |
| Security | 🟢 after this PR | The Critical read-auth hole (C-1) is **fixed here**; residual Low items remain |
| Code quality | 🟡 Good with debt | Superb docstrings & invariant; long-parameter core, dict-domain, duplication |
| Performance | 🟠 Real ceiling | ~150 **sequential blocking** HTTP calls per `/analyze` (P1 — next PR) |
| UI/UX | 🟢 Strong | Bilingual RTL/LTR enterprise UI; slow-analyze feedback & a11y gaps remain |

---

## 1 · Architecture Analysis

**Style.** A **modular monolith** shaped as an **implicit layered pipeline** with a **multi-agent (Manager→Agents→Jury) pattern** and a **single canonical view-model**. The defining force is a domain invariant enforced *structurally*, not a framework. Microservices were correctly avoided.

**Full data flow.** `POST /analyze` (`api.py`) → `resolve()` HS6 (`silk_hs_resolver`, weak match → `None`) → `rank_markets()` scores ~38 markets on 4 weighted components (`silk_market_ranker.py:158`, Comtrade + World Bank) → `ResearchManager.distribute()` runs TradeFlow/Economic/Competition per top-3 market (`silk_agents.py`) → additive enrichment layers (`silk_engine._enrich_*`) → `correlate()` in-memory only (`correlation.py`) → `synthesize()` deterministic jury + optional isolated Claude (`silk_synthesis.py:76`) → `build_view()` the ONE view-model (`silk_render.py:97`) → delivery (web / terminal / Word / brief / CSV / JSON). `POST /deepen` is the same inside `silk_context.deepen_context()` — the only state where `PAID` agents may run.

**Folder structure / layers / domain boundaries.** Flat namespace (30+ `silk_*.py` at root, no `silk/` package). Conceptual layers exist but are unenforced: acquisition (`silk_data_layer*`, `silk_cache`, `silk_*_agent`, `silk_ai_judge`), pure domain policy (`silk_market_ranker`, `correlation`, `silk_synthesis`, `silk_trend`), orchestration (`silk_engine`), delivery (`api`, `web/`, `silk_render`, `silk_reports`), cross-cutting (`silk_context`, `silk_storage`, `silk_usage`). The **cleanest boundary** is `correlation.py`/`silk_render.py` (pure, AST-enforced). The **weakest**: agents import the concrete data layer directly (`silk_agents.py:14-22`) — the acquisition boundary is conceptual, not architectural (no port to swap/mock without monkeypatching); and the "entities" are untyped dicts mutated across stages (`silk_engine.py:150-169`).

**Strengths.** Invariant enforced structurally (`silk_data_layer.py:137-151`); one view-model (`silk_render.py:97`); one verdict entry (`silk_synthesis.py:76`); structural paid/free guard via contextvars (`silk_agents.py:69-92`, `silk_context.py`); prompt-injection isolation that sanitizes its own delimiters (`silk_ai_judge.py:39-47`); pure correlation (`correlation.py:7-11`); atomic TOCTOU-safe cap (`silk_usage.py:108`); lazy imports + 108 hermetic tests.

**Weaknesses / risks.** R1 sequential blocking I/O (latency ceiling); R2 untyped mutated dicts (temporal coupling); R3 procedural core with 14 flag-args + duplicated `_enrich_*` (OCP violation); R4 no ports/repository abstraction; R5 import-time config capture (`silk_data_layer.py:50`).

---

## 2 · Security & Vulnerability Report

### 🔴 CRITICAL — RESOLVED IN THIS PR

**C-1 · Unauthenticated, enumerable exposure of persisted product economics.** `GET /analyses`, `/analyses/{id}`, `/brief`, `/report.docx` had **no auth**; IDs are `AUTOINCREMENT`; the persisted blob carries the user's cost card (`correlation.py:250-253` → `silk_storage.py:76-96`). An attacker could enumerate and harvest every client's cost/margins/target-markets even with `SILK_API_KEY` set.
**Fix (this PR):** `_require_key()` now guards all four read routes (`api.py`); proven by run — `GET /analyses/1` no key → **401**, correct key → **200**, wrong key → **401**. Regression test: `tests/test_wave7_security_p0.py`. **Operational requirement:** `SILK_API_KEY` **must** be set in production (`docs/DEPLOY_RAILWAY.md §3`) — in open dev mode the guard is a deliberate no-op.

### 🟠 MEDIUM — RESOLVED IN THIS PR

**M-1 · No rate limiting.** Added a simple in-memory fixed-window limiter (per `X-API-Key`/IP) on the compute + read endpoints (`api.py`); `SILK_RATE_LIMIT`/`SILK_RATE_WINDOW`, default 120/60s, `0` disables. Proven: 5× over a limit of 3 → `[200,200,200,429,429]`.

**M-2 · Fail-open paid cap.** `silk_usage.try_reserve_paid_calls()` now **fails closed** on DB error (`silk_usage.py`): the free path never touches it, and a broken counter must not silently uncap paid credit. Proven: corrupt `usage.db` → `try_reserve → False`, `POST /deepen{with_volza}` → **429**.

### 🟡 LOW

- **L-1 · Timing-safe key compare — RESOLVED:** `hmac.compare_digest` in `_require_key` (`api.py`).
- **L-2 · No security headers** on the `/`-mounted static UI (`Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`). *Open — recommend a headers middleware.*
- **L-3 · Third-party font CDN** (`fonts.googleapis.com`) — supply-chain surface + breaks under strict CSP/offline. *Open — self-host IBM Plex.*
- **M-3 (deferred by owner decision):** the settings UI collects provider keys in `localStorage` that the client never sends. Reconsider only if the platform becomes multi-user.

**Explicitly NOT done (owner decision):** redact-on-persist of `product_card`. This is a **single-tenant internal tool**; auth (C-1) closes the exposure, and redaction would sacrifice the value of reviewing historical analyses with their economics for no additional security once authenticated. Revisit only if it becomes multi-user.

**Verified safe:** all SQL parameterized (`silk_storage.py`, `silk_usage.py`); CORS same-origin default; injection isolation robust.

---

## 3 · Code Quality Report

Positives: exemplary bilingual docstrings; provenance-first modeling; hermetic per-wave tests; structural guards.

| # | Issue | Principle | file:line |
|---|---|---|---|
| Q1 | Flat 30+ module namespace, no package/layer boundaries | Clean Architecture | repo root |
| Q2 | `analyze()` — 20+ params, 14 `with_*` flags | SOLID (SRP/OCP), Clean Code | `silk_engine.py:27-39` |
| Q3 | Near-duplicate enrichment wrappers | DRY | `silk_engine.py:218-370` |
| Q4 | Income fetched twice per market | DRY / perf | `silk_market_ranker.py:179` vs `:184` |
| Q5 | Cross-module import of underscore-private symbols | Encapsulation | `silk_synthesis.py:24` |
| Q6 | Untyped dicts as domain entities, mutated in place | DDD / immutability | `silk_engine.py:150-169` |
| Q7 | Import-time side effects (`_load_dotenv`, key capture, `create_app`) | Testability / 12-Factor | `silk_data_layer.py:34,50`; `api.py` |
| Q8 | ~40 broad `except Exception` (deliberate but masks bugs) | Error handling | pervasive |
| Q9 | Config reads scattered, no `Settings` object | 12-Factor | multiple modules |
| Q10 | 700-line single-file UI (self-contained by house rule) | Separation of concerns | `web/index.html` |
| Q11 | No linter / type-checker / coverage gate | Tooling | CLAUDE.md |

---

## 4 · Performance & Scalability Report

**Primary bottleneck — sequential blocking HTTP.** `rank_markets()` loops ~38 countries (`silk_market_ranker.py:171`), each issuing 1 Comtrade + ≤3 World Bank synchronous `requests.get` → **≈150 blocking round-trips per `/analyze`**; `with_trend` adds `span × top-3` more (`silk_trend.py`). A cold offline `/analyze` took **>40 s** in the live browser test.

| # | Bottleneck | Optimization |
|---|---|---|
| P1 | Zero concurrency | `ThreadPoolExecutor` + shared `requests.Session` (house rule: stdlib/requests, not httpx) → 3–5× |
| P2 | No connection pooling | one `requests.Session` with keep-alive |
| P3 | Redundant WB income fetch (Q4) | reuse the one `DataPoint` → −38 calls/run |
| P4 | Fixed 38-market universe | make configurable/paged; pre-filter by region/sector |
| P5 | Repeat queries | 24 h on-disk cache exists (`silk_cache.py`) — layer a Session on top |

**Memory/scalability:** memory bounded (modest dicts, no large accumulation); SQLite adequate (owner-decided). The ceiling is I/O latency — replicas won't help until fan-out is concurrent and rate-limited (M-1, now in place).

---

## 5 · UI/UX Report (`web/index.html` — bilingual enterprise, Carbon × Redwood)

**Strengths (verified in headless Chromium):** decision-first hierarchy + confidence gauge; truthful agent pipeline + study-completeness meter (NN/g #1); provenance under every number; gaps shown as "not observed"; **live AR⇄EN toggle** flipping RTL/LTR via CSS logical properties; light/dark; 16px base high contrast; `:focus-visible`; `prefers-reduced-motion`; responsive grids.

| # | Issue | Fix |
|---|---|---|
| U1 | Slow `/analyze` shows only a skeleton — no progress/cancel | stream top markets first; add cancel; fix P1 |
| U2 | Table rows not keyboard-operable (`<tr onclick>`) | `role="button"`+`tabindex`+Enter/Space |
| U3 | Font from external CDN → FOUT/offline loss | self-host IBM Plex (also L-3) |
| U4 | Settings collects keys the client never sends (M-3) | show source status only |
| U5 | No product-card validation (price < cost → silent negative margin) | inline validation |
| U6 | Loading/timeout state not distinct from "ready" | explicit timeout + retry copy |

---

## 6 · Final Recommendations (prioritized)

- **P0 — Security (DONE in this PR):** C-1 read-auth, M-1 rate limit, M-2 fail-closed cap, L-1 constant-time compare. **Action for ops:** set `SILK_API_KEY` in Railway Variables (else all of it is cosmetic).
- **P1 — Performance (next):** `ThreadPoolExecutor` + shared `requests.Session` fan-out across markets; dedupe the double income fetch. Keep the sync path for hermetic tests.
- **P2 — Architecture/quality:** `silk/` package (domain/application/adapters/interface) with re-export shims; enrichment registry (OCP); frozen `DataPoint` + typed `Market`/`ScoredMarket`; single `Settings`; add `ruff`+`mypy`+coverage gate.
- **P3 — UI/UX:** self-host fonts; progressive render + cancel; keyboard-accessible rows; drop client key inputs; product-card validation.

---

## Appendix A · V3 feature-gap analysis (governance)

**Question:** were rate limiting and background RQ queues documented as "done in V3 Phase 1", and are they missing from `main` — dropped by decision, or lost by accident?

**Evidence (repo-internal, exhaustive search):**
- **There is no "V3 plan" document in this repository** — stated verbatim in the repo's own audit: `docs/AUDIT_STATUS.md:407-410` ("لا توجد وثيقة «خطة V3» داخل المستودع — غير موجود، بحث شامل"). The actual roadmap is `docs/EXECUTION_PLAN.md` (waves 0–5), derived from the audit × `docs/VISION.md`.
- **Rate limiting** is documented as **absent**, not done: `docs/AUDIT_STATUS.md:318-319` ("لا rate limiting في api.py كاملاً ولا في أي وحدة"). It is **not** in the Wave-0 security scope (`EXECUTION_PLAN.md:14-28` = auth, cap, injection isolation, CORS).
- **RQ / background queues / redis / worker / celery:** **zero** occurrences across code, docs, and git history.

**Conclusion:** the premise ("documented as done in V3 Phase 1") **cannot be located anywhere in this repo**. Neither feature was ever present, claimed, or planned here, so neither was "dropped" nor "lost" — they are **acknowledged never-implemented gaps**. (Rate limiting is now added by this PR.)

### Classified list — VISION/plan items vs current `main`

**A) Deferred BY EXPLICIT OWNER DECISION** (documented, dated 2026-07-02 in `EXECUTION_PLAN.md:103-114`):
1. **Postgres migration** → SQLite stays (Decision 1).
2. **The 6 non-core Wave-3 agents** (cultural, exhibitions, religion, currency, ecommerce, factories) → deferred until real need (Wave-3 table + Decision 2).
3. **The "21 agents" target** → owner chose the selective 4; the 21-agent assumption was explicitly rejected (Decision 2).
4. **Trade-finance layer** (VISION §12.7) → deferred (Decision 4).

**B) Absent WITHOUT a recorded decision** (acknowledged gaps, never scoped — not regressions):
1. **Rate limiting** — `AUDIT_STATUS.md:319`; never in any wave. *(Now implemented by this PR.)*
2. **Background job queue (RQ/async workers)** — no reference anywhere; never planned or present.
3. **Security headers (CSP etc.)** on the static mount — never addressed (L-2).
4. **CrewAI agent wrapping** (README "next steps") — not adopted (implicit YAGNI/stdlib-first, not a formal decision).

**Net:** the V3 target vs `main` gaps that remain are either (A) owner-deferred by decision, or (B) never-scoped gaps — there is no evidence of a feature that was "completed then silently lost."
