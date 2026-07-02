# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt pytest httpx   # httpx is test-only (TestClient)
python3 -m pytest tests/ -q                    # full hermetic suite (~5s, no network needed)
python3 -m pytest tests/test_wave0_security.py -q                    # one file
python3 -m pytest tests/test_smoke.py::test_resolver_real_hs_codes -q  # one test
uvicorn api:app --host 0.0.0.0 --port 8000     # API + dashboard (web/ served at /)
python3 silk_engine.py                         # engine demo from the terminal
python3 silk_requirements_agent.py             # most silk_*.py files have a __main__ demo
```

CI (`.github/workflows/ci.yml`) runs exactly `python -m pytest tests/ -q`. There is no linter config.

## The founding principle (enforced, not advisory)

**The system never fabricates data.** Every value travels as a `DataPoint(value, source, confidence, note, retrieved_at)` (`silk_data_layer.py`). On any failure — no key, no network, bad payload — the value is `None` with `confidence=0.0` and a `note` explaining why. Numbers are never guessed, gaps are declared, and tests enforce this hermetically (they cut the network via `socket.socket` monkeypatching and assert `None`, not zeros). Any new data path must follow this contract or the review will reject it.

## Architecture — the pipeline

`silk_engine.analyze()` is the spine. Order matters because later stages consume earlier stages' in-memory output:

1. **Resolve** — product name → HS6 via `silk_hs_resolver` (CSV seed + difflib; weak match = `None`, never guessed). An explicit `hs_code` arg bypasses this (used by the discovery hand-off).
2. **Rank** — `silk_market_ranker.rank_markets()` scores ~38 markets on 4 weighted components (Comtrade + World Bank); missing components lower row confidence, weights renormalize.
3. **Core agents** — `ResearchManager` runs TradeFlow/Economic/Competition per top market; reports are held until after enrichment.
4. **Enrichment layers** — optional `with_*` flags attach additive context per top market (trends, tariffs, faostat, maps, localprice, volza, explee, competitors_named, channels, importers, requirements). They NEVER change `total_score`. Wrapper exceptions become `_enrich_error_dp()` DataPoints — silent `[]`/`None` is a regression.
5. **Correlation** (`correlation.py`) — runs only when a `product_card` is present. Builds the four threads (competitor/feasibility/entry/contacts) **strictly from in-memory agent findings; zero external calls** — an AST test asserts it imports no network library. Incomplete threads are declared ("سعر غير مرصود"), never invented. Name matching is a conservative Dice coefficient over distinctive tokens.
6. **Synthesis** (`silk_synthesis.synthesize()`) — the ONLY verdict entry point. Stage 1 is the deterministic `JuryCommittee`; stage 2 (with `with_ai` + `ANTHROPIC_API_KEY`) is a Claude judgment over isolated inputs, switching to the "confrontation" prompt when correlation threads exist. Do not add parallel verdict paths — the old `ai_verdict` duality was deliberately deleted.
7. **View** (`silk_render.build_view()`) — the ONE canonical view-model. Every output derives from it: dashboard (`result["view"]` attached by the API, rendered by `web/index.html`), terminal (`format_result`), Streamlit (`app.py`), Word report + one-page brief (`silk_reports.py`), `view["brief"]`. Per-number provenance lives in `components_detail` inside the template, so a figure without a source line is structurally impossible. **Never add a separate render path; extend `build_view` instead.**

## BaseAgent and the paid/free boundary

All 15 agents inherit `BaseAgent` (`silk_agents.py`), which enforces the protocol structurally:

- `PAID = True` agents (LocalPrice, Volza, Explee — exactly these three) cannot execute outside the deepen context (`silk_context.deepen_context()`, a contextvar set only by `POST /deepen`). Outside it they return a tagged skipped report **without attempting any call**, even with keys set.
- An unexpected exception in `_execute()` automatically becomes a failed report with a noted DataPoint — silent failure is impossible.
- New agents: subclass `BaseAgent`, set `PAID`/`SOURCE`, implement `_execute(task) -> AgentReport`, and ship a hermetic test the same day.

`POST /analyze` (free path) structurally cannot trigger paid layers — its pydantic model has no paid fields, so they're dropped from any request body. `POST /deepen` is the only paid path.

## Security guards (all run BEFORE any agent)

Configured via env vars (`.env.example` documents all of them); unset = open dev mode, which is legitimate **only when no paid keys are present**:

- `SILK_API_KEY` → requests without a matching `X-API-Key` header get 401.
- `SILK_PAID_DAILY_CAP` → paid-layer activations counted in a separate SQLite file (`data/usage.db` / `SILK_USAGE_DB`, never `silk.db`); exceeding = 429.
- Any paid provider key present while `SILK_API_KEY` is unset → paid requests get 503 and `/health` carries a warning.
- `CORS_ORIGINS` → default is same-origin only; wildcard requires explicit opt-in.
- Prompt injection: every external text reaching Claude goes through `silk_ai_judge._isolate()` (`[RAW_FINDINGS_START/END]` delimiters, with the delimiters themselves sanitized out of the content).

## Testing conventions

Tests are hermetic and live in `tests/test_smoke.py` + `tests/test_wave*.py`. Reused patterns: `_block_network()` (monkeypatch `socket.socket`) for library-level tests; `patch("requests.get", side_effect=OSError(...))` for FastAPI `TestClient` tests (blocking sockets globally breaks the TestClient transport); `_env(**vals)` context manager for env vars with guaranteed restore. The vision's acceptance criteria (§1.7, §11.5, §12.7) exist as named tests — keep that mapping when touching those areas.

## Storage

SQLite only (`silk_storage.py`, default `data/silk.db`) — Postgres migration is an explicitly deferred owner decision; don't introduce it. Schema changes go through additive `ALTER TABLE` migration inside `init_db()` (existing rows untouched). `analyses` carries `outcome`/`outcome_date` (the cumulative track record) settable via `PATCH /analyses/{id}/outcome`. Never delete or modify existing data in `data/silk.db`.

## Governance docs (read before large changes)

- `docs/VISION.md` — the target architecture (its header says so explicitly: actual state ≠ this doc).
- `docs/AUDIT_STATUS.md` — the audit method: every claim anchored to file:line; "not found" stated explicitly.
- `docs/EXECUTION_PLAN.md` — the wave plan (waves 0–5 are implemented and merged) and the owner's settled decisions: SQLite stays, wave-3 agents are the selective four, trade finance is deferred.

House rules that carried through every wave: one independent PR per work wave branched from fresh `main` (squash-merged, `title (#N)` style); the existing suite stays green and each wave adds its tests; PR descriptions anchor claims to file:line; every render-layer change regenerates the committed samples in `samples/` (rule §10.6 — reviewers open files from the repo, no attachment channels).

## Misc

- The repo is bilingual: Arabic-first docstrings/comments/docs with English mirrors. Match that style.
- `web/index.html` is a single self-contained vanilla-JS file; it consumes `result.view` from the API — extend the view, then render it.
- The ponytail plugin is configured in `.claude/settings.json` (YAGNI, stdlib-first, minimal code) — the codebase follows it: no heavy frameworks, lazy imports so every module imports offline and keyless.
