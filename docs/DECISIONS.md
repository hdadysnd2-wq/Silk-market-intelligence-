# DECISIONS LEDGER

Authoritative. When `docs/SPEC-v2.md` and this file conflict, **this file wins**.
Every command reads this before acting.

---

## Settled decisions

### D-01 — B2 vs E1 (readability vs cost)
Undefined jargon = **blocking issue**. Review cycle 2 fires ONLY on a blocking issue.
We accept a temporary cost increase as the price of readability.
**Interim ceiling: $1.7** until Part E lands. The $1.5 target is measured only after E.
*Rationale: B2 demanded more review, E1 demanded less. Readability wins now, cost is
optimized later against a stable baseline.*

### D-02 — C2 vs E3 (scraper vs runtime)
The scrape job is **async and does NOT count** against the 10-minute budget.
8-minute hard timeout; if it doesn't return, fall through the C4 chain and declare
the gap. **The run never waits on it.**
*Rationale: an 8-min poll inside a 10-min ceiling leaves zero margin. Decoupled instead.*

### D-03 — C1 is a manual owner step
Claude writes the Railway console steps and **stops**. Commands C2–C5 do not open
until the owner confirms the service is live.
*Rationale: Claude cannot provision Railway. A command that can't self-close is not
a command.*

### D-04 — Baseline is measured before any change
Measured in Command #1 and frozen at `docs/BASELINE-2026-07-16.md`.
Every before/after compares against a **frozen** file, never a moving target.
Part E re-measures into `docs/BASELINE-post-BC.md` because B and C shift the baseline
legitimately.

### D-05 — No "one run proves everything"
Each command closes with **its own live artifact**. The final run is confirmation,
not first contact.
*Rationale: a single acceptance run at the end means every defect surfaces at once,
with no way to attribute it.*

---

## Execution order (gated — do not skip ahead)

| # | Command | Scope | Closing gate | Status |
|---|---|---|---|---|
| 1 | Triage & baseline | read-only | Report + frozen BASELINE + ledger updated | ☑ 2026-07-16 — `docs/BASELINE-2026-07-16.md` + ledger below + report in PR |
| 2 | UI cleanup | A1–A3 | Zero orphan strings (grep pasted) + live UI: 2 actions + sidebar | ☑ 2026-07-16 — grep 0 orphans (prod) + live `GET /`→200, runbar 2 buttons + `#histList` |
| 3 | Assembly defects | D1–D3 | 3 green lock-tests + live run excerpts pasted | ☐ |
| 4 | Merchant language | B1–B3 | Green lock-test on md AND docx + glossary pasted | ☐ |
| 5a | Scraper: owner steps | C1 | Steps written + clean-disable wired + owner confirms service live | ☐ |
| 5b | Scraper: integration | C2–C5 | Importer table w/ real contacts + path printed + `/health` survives kill | ☐ |
| 6 | Cost & speed | E1–E3 | ≤ $1.5 + < 10 min printed + prior lock-tests still green | ☐ |
| — | Final run | confirmation | All 6 acceptance items with artifacts | ☐ |

**Ordering notes:**
- #3 precedes #4 deliberately — both touch the render path. Fixing fact-loss first
  prevents building the style contract on a broken foundation.
- #6 is last — B and C legitimately change the baseline. Optimizing before them
  measures nothing.
- If #3 blows up, split it: D2 alone, then D1 + D3. Don't fight the context window.

---

## Scope discipline

Out-of-scope findings are **logged here, not fixed**. Standing instruction to Claude:

> This is outside the current command's scope. Log it as a note in the ledger and
> continue within the defined scope.

### Out-of-scope findings log

| Date | Found during | Finding | Belongs to |
|---|---|---|---|
| | | | |

---

## Item status ledger

Two states only: **DONE-with-artifact** or **NOT DONE**. No third state.

Triage note (Command #1): at triage time nothing had been fixed — Command #1 is
read-only, so every SPEC item started **NOT DONE**, with the evidence column
recording the current `file:line` state and any partial scaffolding from prior
PRs. Rows flip to **DONE-with-artifact** only as each later command lands its
live proof (e.g. A1–A3 closed by Command #2).

| Item | Status | Evidence (path / grep / URL / printed output) | Date |
|---|---|---|---|
| A1 | DONE-with-artifact | Feature deleted by #107 (module/endpoint/button gone); Command #2 removed the leftover orphan strings. Prod grep (excl tests/docs) «معاينة فورية» = 0, `snapBtn`/`quickSnapshot`/`products/snapshot`/`silk_snapshot` = 0. `tools/acceptance_run.py` step 6 (live POST to deleted `/products/snapshot`) removed. Stale `test_r4` `.pyc` deleted. `product_snapshots` table kept dormant (no-delete-silk.db rule), comment de-named. | 2026-07-16 |
| A2 | DONE-with-artifact | Exact button label «حلّل السوق» reworded off `silk_market_analyst.py:162` docstring (→ «التحليل الشامل للسوق»). Prod grep (excl tests/docs) exact «حلّل السوق» = 0. «مسح الأسواق» kept `web/index.html:251,316`; legit verb uses («حلّل سوق تصدير», chat examples, STOP-word) untouched. Enforcement tests keep the phrase as absence-guards. | 2026-07-16 |
| A3 | DONE-with-artifact | Live `GET /` → 200: runbar serves exactly TWO action buttons — `researchBtn` «بحث عميق» (primary) + `runBtn` «مسح الأسواق» (secondary); `id="snapBtn"` absent from served page; `#histList` sidebar present. Guards: `tests/test_ui_action_buttons_have_purpose.py`, `tests/test_item3_analyze_screen_button.py` green. | 2026-07-16 |
| B1 | NOT DONE | No versioned writer style-contract file (grep hits only SPEC/DECISIONS). Writer prompt *permits* standalone HHI/CAGR/TAM/SAM/SOM `silk_ai_judge.py:824-827`; no first-use gloss, no auto-glossary, no USD→SAR (`:880-882` forbids currency conversion). | 2026-07-16 |
| B2 | NOT DONE | Reviewer checklist `silk_ai_judge.py:1084-1106` has no undefined-jargon / missing-gloss blocking check. | 2026-07-16 |
| B3 | NOT DONE | No lock-test for glossary-present / no-standalone-jargon on md or docx (grep of `tests/` finds only unrelated `test_p1_narrative.py:32`, `test_research_report_quality.py:5`). Sample: glossary count 0, HHI ×6 / LPI ×1 standalone, ريال count 0. | 2026-07-16 |
| C1 | NOT DONE | `SILK_GMAPS_SCRAPER_URL` / `gosom` / `google-maps-scraper` exist only in `docs/SPEC-v2.md:87-89`; absent from `.env.example`, `railway.json`, `api.py`. Second Railway service not built. | 2026-07-16 |
| C2 | NOT DONE | `silk_importers_agent.py` (whole file) is Serper web search, single English query `:47-48`; no scrape-job submit, no async/poll, no 8-min timeout, no localized NL query set. | 2026-07-16 |
| C3 | NOT DONE | No fact parse (title/address/phone/EMAIL/website/rating/review_count/maps-link), no dedupe, no top-15, no per-(market,query-set) cache in `silk_importers_agent.py`. | 2026-07-16 |
| C4 | NOT DONE | No fallback chain (scraper→Places API→declared gap) in importers agent; Places path isolated in unused `silk_maps_agent.py:34-38`. | 2026-07-16 |
| C5 | NOT DONE | No "قائمة مستوردين وموزعين قابلين للتواصل" 7-col table (grep 0 in `.py`); report emits a bullet list `silk_reports.py:2510-2519`. No "◐ مرصود عبر خرائط قوقل" level. | 2026-07-16 |
| D1 | NOT DONE | Limits assembled by concatenation, no reconciliation vs final facts `silk_render.py:912-925`. "…" truncation at TWO sites: assembly/storage `silk_llm_runtime.py:648-658` (via `silk_market_analyst.py:140,215`) + render `silk_reports.py:81-92`. Mid-word cut already fixed (word-boundary retreat); still appends "…". | 2026-07-16 |
| D2 | NOT DONE | Category-normalization fixed `silk_market_analyst.py:197-205`, but classification needs Claude bracket-tags per note `:198-204` with no fallback → residual fact-loss; "تقاطع المحلل بلا أدلة كافية" still emitted `silk_render.py:923`. Lock-test `tests/test_wave6_market_analyst.py:62`. | 2026-07-16 |
| D3 | NOT DONE | WGI FETCH fixed + lock-tested `silk_data_layer.py:382-385,412-444`; `tests/test_technical_mission_failures_item2.py:39,58,76`. §9 has NO deterministic WGI binding — writer relies on `risk_news` mission `silk_ai_judge.py:918-921`; sample §9 qualitative only `samples/research_report_latest.md:111`. Writer-mapping gap. | 2026-07-16 |
| E1 | NOT DONE | `SILK_MAX_REVIEW_CYCLES` absent from code (grep empty; proposed `docs/SPEC-v2.md:133`). Review loop default 2 `silk_ai_judge.py:1127,1162,1169`; cycle 2 fires on ANY issue, not blocking-only `:1122,1165`. Retries bounded (no storms). `usage.db` daily-aggregate only `silk_usage.py:66-74`. | 2026-07-16 |
| E2 | NOT DONE | Opus for all missions+analyst+writer; Haiku only reviewer/helpers `silk_ai_judge.py:20,111,1111`; `silk_llm_runtime.py:922,990`. No Sonnet tier / Haiku-for-extraction routing. Prompt caching EXISTS `silk_llm_provider.py:132,174,182`. Per-tail-stage cost line item MISSING `silk_context.py:194`. | 2026-07-16 |
| E3 | NOT DONE | Missions parallel `silk_missions.py:437-480`, tail sequential `api.py:884-898`. Per-call `elapsed_ms` in traces; run-level `elapsed_seconds` in UI `api.py:1237-1257`. No per-stage wall-time rollup / per-stage UI timing. | 2026-07-16 |

---

## Open questions (from triage)

| Q | Answer | Resolved |
|---|---|---|
| Which mission calls `google_maps` today? If none → "configured-but-unused" | **None.** No `/research` mission has a maps/places tool — full tool vocabulary in `silk_missions.py` `allowed_tools` + runtime registry `silk_llm_runtime.py:143-406` has no `find_places`. `/health` shows "on" purely on key presence `api.py:315-317`. Only the OLD `/analyze` path uses it (`silk_engine.py:164-165,470-471`; `silk_research.py:395,650`). **Verdict: configured-but-unused** (matches `docs/PLATFORM_ANALYSIS.md:173`). | ☑ |
| `/products/snapshot` — any internal callers? | **None.** Route defined `api.py:1675` and calls `silk_snapshot.quick_snapshot` at `api.py:1719` only inside that endpoint. No other module imports `silk_snapshot`. External callers: frontend `web/index.html:465,484`, acceptance harness `tools/acceptance_run.py:253`, tests only. → A1 may delete the endpoint + UI (module has no other consumer). | ☑ |
| `"…"` truncation — storage or renderer? | **Both.** Assembly/STORAGE: `silk_llm_runtime._truncate_at_word` `:648-658` via `silk_market_analyst.py:140,215` (summary capped at 3000 before store/writer). RENDER: `silk_reports.py:81-92` (`_clean_report_text`, default 300). Both retreat to word boundary (mid-word bug fixed) but still append "…". | ☑ |
| WGI — mission-fetch bug or writer-mapping bug? | **Writer-mapping bug.** Fetch is FIXED + lock-tested (`silk_data_layer.py:382-385,412-444`; `tests/test_technical_mission_failures_item2.py:39,58,76`). §9 has no deterministic binding of stored WGI facts — the writer prompt sources §9 from the `risk_news` mission's own findings `silk_ai_judge.py:918-921`, so numeric PV.EST/RL.EST + جودة التنظيم are absent when the mission doesn't surface them. | ☑ |
