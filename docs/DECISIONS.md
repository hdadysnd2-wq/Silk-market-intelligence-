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
| 3 | Assembly defects | D1–D3 | 3 green lock-tests + live run excerpts pasted | ☑ 2026-07-16 — lock-tests b1(9)/d2(6)/d3(5) green; excerpts in PR; suite 1068 pass |
| 4 | Merchant language | B1–B3 | Green lock-test on md AND docx + glossary pasted | ☑ 2026-07-16 — `test_merchant_language_b3.py` (5) md+docx green; glossary in PR + regenerated sample; suite 1073 pass |
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
| B1 | DONE-with-artifact | Versioned contract `silk_style_contract.py` (`WRITER_STYLE_CONTRACT` injected into `silk_ai_judge.deep_report`; `GLOSSARY`/`SAR_PEG`). Deterministic pass `silk_render._apply_merchant_language` glosses each term on first use, contextualizes USD→SAR at the 3.75 peg, and emits a structured `glossary` rendered in md + operator docx + client docx. No-fabrication intact (annotates/contextualizes only). Regenerated `samples/research_report_latest.md` shows glossary + `HHI (…)` + «بسعر الربط». | 2026-07-16 |
| B2 | DONE-with-artifact | Reviewer prompt now flags any technical term/acronym without an Arabic gloss on first use as **blocking** (`silk_ai_judge.py` reviewer checklist + `blocking` JSON note), folded into the existing cycle (no extra paid cycle). | 2026-07-16 |
| B3 | DONE-with-artifact | `tests/test_merchant_language_b3.py` (5) locks glossary-present + no standalone HHI/CAGR/LPI/MFN at first use on **md AND docx** (client docx built and re-opened), + USD→SAR + no-fabrication. Green. | 2026-07-16 |
| C1 | NOT DONE | `SILK_GMAPS_SCRAPER_URL` / `gosom` / `google-maps-scraper` exist only in `docs/SPEC-v2.md:87-89`; absent from `.env.example`, `railway.json`, `api.py`. Second Railway service not built. | 2026-07-16 |
| C2 | NOT DONE | `silk_importers_agent.py` (whole file) is Serper web search, single English query `:47-48`; no scrape-job submit, no async/poll, no 8-min timeout, no localized NL query set. | 2026-07-16 |
| C3 | NOT DONE | No fact parse (title/address/phone/EMAIL/website/rating/review_count/maps-link), no dedupe, no top-15, no per-(market,query-set) cache in `silk_importers_agent.py`. | 2026-07-16 |
| C4 | NOT DONE | No fallback chain (scraper→Places API→declared gap) in importers agent; Places path isolated in unused `silk_maps_agent.py:34-38`. | 2026-07-16 |
| C5 | NOT DONE | No "قائمة مستوردين وموزعين قابلين للتواصل" 7-col table (grep 0 in `.py`); report emits a bullet list `silk_reports.py:2510-2519`. No "◐ مرصود عبر خرائط قوقل" level. | 2026-07-16 |
| D1 | DONE-with-artifact | Closed by #107 + verified in Command #3. `silk_render._reconcile_mission_limits` retags a mission gap «حُسمت لاحقاً» only when a topic+number fact resolves it (else verbatim — no-fabrication); `_first_clause` gives the limits line the first sentence only (no mid-sentence «…»). Lock-tests `tests/test_limits_reconciliation_b1.py` (9) green. Live excerpt (reconstructed blob): limits show «حُسمت لاحقاً», zero «…». | 2026-07-16 |
| D2 | DONE-with-artifact | #107 shipped the diagnostics instrument but left the root fix NOT DONE. Command #3 adds a conservative synonym map (`silk_market_analyst._CATEGORY_SYNONYMS`) that rescues findings tagged with a category outside the literal 5 (e.g. `[pricing]`→price_competitiveness) — one of the three diagnosed causes; untagged findings stay diagnosed (nmt #8, no content-guessing). `diagnostics.synonym_rescued` surfaces drift. Lock-test `tests/test_analyst_synonym_rescue_d2.py` (6) green. Live excerpt: 5 synonym-tagged findings → all 5 intersections populated, synonym_rescued=4, missing=[]. | 2026-07-16 |
| D3 | DONE-with-artifact | Fetch was already fixed; the gap was writer-mapping (§9 relied on the `risk_news` LLM calling the tool for all 3 WGI). Command #3 adds deterministic augmentation `silk_missions._augment_risk_news_wgi` (all 3 incl. RL.EST which even RiskAgent omits) wired into `run_all_missions`; declared-gap on failure (no fabrication); §9 writer instruction updated to cite the attached `[risk]` facts `silk_ai_judge.py:918`. Lock-test `tests/test_wgi_governance_augment_d3.py` (5) green. Live: offline fetch → 3 declared gaps (None/0.0), no fabrication. | 2026-07-16 |
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
