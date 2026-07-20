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

### D-06 — Cost-cutting budgets are re-measured against the CURRENT combined output; a new model is priced in the SAME command
Command #6/E2 shrank the writer/analyst `max_tokens` in the name of cost while four
earlier commands (B1, C5, D2, D3) had each **added required output**. Nobody
re-measured the combined load, so the first run that populated all four at once
(honey/UK) overran the ceiling and fell back to the skeleton — the anti-fabrication
guard held (every section «غير متاح», zero invented numbers), but there was no report.
Two permanent rules (LESSONS #16, enforced):
1. **A token budget in any cost-cutting change is re-measured against the summed
   output requirement of ALL prior commands, not the requirement it was first sized
   for.** This holds for every heavy stage: the writer (`_WRITER_MAX_TOKENS`, whose
   continuation call takes the ceiling not the base) AND the analyst
   (`_ANALYST_MAX_TOKENS` — it emits D2's five intersections + SWOT and must not fall
   back to the single-mission default of 6000, or the intersections truncate to
   «دليل غير كافٍ»).
2. **A new model integration is added to the `silk_pricing` table in the same command
   that introduces it** — a routed model with no price is silently excluded from the
   displayed total (understating it) while still being billed.

**Reconciliation method (documented, so "displayed ≈ billed" is checkable, not asserted):**
displayed total `= Σ_model ( input_tokens×input_rate + output_tokens×output_rate +
cache_read×input_rate×0.1 + cache_creation×input_rate×1.25 )` over
`silk_context.record_llm_usage`'s per-model counter (`silk_pricing.estimate_cost_usd`).
It reconciles with the Anthropic console when: (a) every routed model is priced
(else it appears in `unpriced_models` + the ⚠ chip, and `complete=False`), and
(b) every HTTP-200 response is metered **including `stop_reason=max_tokens`
truncations** — a failed/truncated call still burns (and is billed for) its tokens,
so it must still be counted. Both are locked by
`tests/test_command6_regression_budget_and_pricing.py`. A residual gap after those
two hold points at an env-set model id outside the pricing prefixes — add its real
rate (never guess one: no-fabrication).

*Consequence: the ≤$1.5 target from D-01 is REFUTED for a full report. A full
narrative carrying all four blocks on the Opus writer legitimately costs more than
$1.5; the ~$3 the owner was billed is the honest cost of a complete report, not an
overcharge. The target must be re-baselined against a run that actually succeeds
end-to-end — which is the #6 live re-run gate.*

---

## Execution order (gated — do not skip ahead)

| # | Command | Scope | Closing gate | Status |
|---|---|---|---|---|
| 1 | Triage & baseline | read-only | Report + frozen BASELINE + ledger updated | ☑ 2026-07-16 — `docs/BASELINE-2026-07-16.md` + ledger below + report in PR |
| 2 | UI cleanup | A1–A3 | Zero orphan strings (grep pasted) + live UI: 2 actions + sidebar | ☑ 2026-07-16 — grep 0 orphans (prod) + live `GET /`→200, runbar 2 buttons + `#histList` |
| 3 | Assembly defects | D1–D3 | 3 green lock-tests + live run excerpts pasted | ☑ 2026-07-16 — lock-tests b1(9)/d2(6)/d3(5) green; excerpts in PR; suite 1068 pass |
| 4 | Merchant language | B1–B3 | Green lock-test on md AND docx + glossary pasted | ☑ 2026-07-16 — `test_merchant_language_b3.py` (5) md+docx green; glossary in PR + regenerated sample; suite 1073 pass |
| 5a | Scraper: owner steps | C1 | Steps written + clean-disable wired + owner confirms service live | ⏳ 2026-07-16 — steps (`docs/DEPLOY_SCRAPER.md`) + clean-disable (`silk_gmaps.py`, `/health`) + lock-test done; **awaiting owner: deploy 2nd service + confirm live (D-03 gate)** |
| 5b | Scraper: integration | C2–C5 | Importer table w/ real contacts + path printed + `/health` survives kill | ☑ 2026-07-16 — table renders md+docx (sample), path logged, kill→gap test green; **live real-contacts run is owner-side (scraper on private net, unreachable from CI)**; suite 1093 pass |
| 6 | Cost & speed | E1–E3 | ≤ $1.5 + < 10 min printed + prior lock-tests still green | ☒ **NOT DONE (regressed)** 2026-07-16 — E1/E3 stand; **E2's per-stage `max_tokens` budget was set below the combined output of B1+C5+D2+D3** (each a prior command that added required output) → first live run (honey/UK) failed the narrative («بلغ التوليد الحدّ الأقصى للطول», skeleton held, zero fabrication). The **≤$1.5 was never reconciled against real billing**: displayed $0.39 vs owner-billed ~$3 with a ⚠ «unpriced models» warning. Fix (Command #6-regression): writer first-attempt 8000→16000, ceiling 16000→32000, continuation call now takes the **ceiling** not the base; pricing/metering hardened + reconciliation method documented. **The ≤$1.5 target is REFUTED for a full report** — a full narrative with all four blocks on Opus legitimately costs more; re-baseline pending owner's live run. |
| — | Final run | confirmation | All 6 acceptance items with artifacts + **live narrative success with reconciled cost** | ☐ — blocked on #6 live re-run (see D-06) |

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
| 2026-07-20 | Report-quality-upgrade self code-review (#3) | `TrendsAgent._execute` now always appends a `value=None` seasonality DataPoint when Trends returns no series — required so 2.2's gap+closure reaches the view, but it adds one extra `○ unverified` to `_client_confidence_section`'s tally on every trends-less report. **Kept as-is** (declaring the gap is the correct no-fabrication behavior vs. the old silent drop); follow-up: consider excluding pure closure-suggestion DataPoints from the evidence tally so the confidence % isn't diluted by a non-datum. | Confidence-tally refinement (future) |

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
| C1 | NOT DONE (owner-gated, Claude-side complete) | Claude-side delivered: exact Railway console steps `docs/DEPLOY_SCRAPER.md` (2nd service from `gosom/google-maps-scraper`, own volume, private-networking-only), clean-disable `silk_gmaps.py` (`SILK_GMAPS_SCRAPER_URL`, empty=disabled) + `/health` informational status not gating `research_ready`, `.env.example` entry, lock-test `tests/test_gmaps_scraper_c1.py` (5) green, live `/health` toggle proof. **Remaining (D-03 owner gate): owner deploys the 2nd service + confirms live → then #5b (C2–C5) opens.** | 2026-07-16 |
| C2 | DONE-with-artifact | `silk_gmaps.submit_scrape_async` submits ONE job at run start (before missions, `api.py` `_run_research_pipeline`), localized queries `localized_queries` (NL→dadels/groothandel/halal groothandel/arabische supermarkt groothandel from `market_locale.csv`), depth 1 + email on, async poll with 8-min hard cap (D-02), collected with a short grace so runtime doesn't grow. Lock-test `tests/test_gmaps_integration_c2345.py`. | 2026-07-16 |
| C3 | DONE-with-artifact | `_parse_lead` (title/address/phone/EMAIL/website/rating/review_count/maps_link), `_dedupe` + `parse_and_rank` top-15, per-(market,query-set) cache `cache_get/put` reused across runs. No-fabrication: missing field → '', gap → []. Tests in `test_gmaps_integration_c2345.py`. | 2026-07-16 |
| C4 | DONE-with-artifact | Fallback chain `finalize_leads`: scraper → official Places (`silk_maps_agent.find_places`, name/address/rating, no email) → declared gap; `path` logged (`api.py` `gmaps leads path=…`). Kill test: scraper+Places down → gap, report intact. | 2026-07-16 |
| C5 | DONE-with-artifact | 7-col table «قائمة مستوردين وموزعين قابلين للتواصل» rendered md + operator docx + client docx from structured `view.deep_research.importer_leads`; `◐ مرصود عبر خرائط قوقل` level + disclaimer line («لا أنه يستورد التمور السعودية»); web candidates cross-matched/merged (`_merge_web_candidates`). Lock-test `tests/test_importer_leads_render_c5.py`; regenerated samples show the table. No-fabrication untouched. | 2026-07-16 |
| D1 | DONE-with-artifact | Closed by #107 + verified in Command #3. `silk_render._reconcile_mission_limits` retags a mission gap «حُسمت لاحقاً» only when a topic+number fact resolves it (else verbatim — no-fabrication); `_first_clause` gives the limits line the first sentence only (no mid-sentence «…»). Lock-tests `tests/test_limits_reconciliation_b1.py` (9) green. Live excerpt (reconstructed blob): limits show «حُسمت لاحقاً», zero «…». | 2026-07-16 |
| D2 | DONE-with-artifact | #107 shipped the diagnostics instrument but left the root fix NOT DONE. Command #3 adds a conservative synonym map (`silk_market_analyst._CATEGORY_SYNONYMS`) that rescues findings tagged with a category outside the literal 5 (e.g. `[pricing]`→price_competitiveness) — one of the three diagnosed causes; untagged findings stay diagnosed (nmt #8, no content-guessing). `diagnostics.synonym_rescued` surfaces drift. Lock-test `tests/test_analyst_synonym_rescue_d2.py` (6) green. Live excerpt: 5 synonym-tagged findings → all 5 intersections populated, synonym_rescued=4, missing=[]. | 2026-07-16 |
| D3 | DONE-with-artifact | Fetch was already fixed; the gap was writer-mapping (§9 relied on the `risk_news` LLM calling the tool for all 3 WGI). Command #3 adds deterministic augmentation `silk_missions._augment_risk_news_wgi` (all 3 incl. RL.EST which even RiskAgent omits) wired into `run_all_missions`; declared-gap on failure (no fabrication); §9 writer instruction updated to cite the attached `[risk]` facts `silk_ai_judge.py:918`. Lock-test `tests/test_wgi_governance_augment_d3.py` (5) green. Live: offline fetch → 3 declared gaps (None/0.0), no fabrication. | 2026-07-16 |
| E1 | DONE-with-artifact | Closed by #107, verified: `SILK_MAX_REVIEW_CYCLES` default 1, cap 2 (`silk_ai_judge._max_review_cycles`); cycle-2 rewrite fires **only on blocking** (`:1217`); B2 jargon-blocking feeds it. Retries bounded. Lock-test `tests/test_wave6_report_writer.py` (default-1 / blocking-triggers-cycle-2 / non-blocking-doesn't). | 2026-07-16 |
| E2 | ☒ **NOT DONE (regressed → refixed)** | The routing itself is right (missions→Haiku `silk_llm_runtime._MISSION_MODEL`, analyst/writer→`_SMART_MODEL` Opus, both **priced** in `silk_pricing`). **But the per-stage `max_tokens` budget was set below the combined required output** of the four prior commands (B1 glossary+glosses+SAR, C5 importer table, D2 five intersections, D3 WGI) — starving the narrative on the first run where all four populated together (honey/UK): writer hit the 16000 ceiling, the continuation call took the **base 8000** not the ceiling, the tail couldn't finish → `report=None` → skeleton. And the **≤$1.5/<10min «DONE-with-artifact» was never reconciled against real billing** (displayed $0.39 vs owner-billed ~$3 + ⚠ unpriced). Refix in Command #6-regression (`_WRITER_MAX_TOKENS` 8000→16000, `_MAX_TOKENS_CEILING` 16000→32000, `_continue_truncated_report` → ceiling; **analyst `_ANALYST_MAX_TOKENS` 6000→12000** so D2's five intersections don't truncate to «دليل غير كافٍ»; guard test that every routed model is priced; metering + reconciliation locked). Lock-tests `tests/test_command6_regression_budget_and_pricing.py`. **Cost target re-opened — see D-06.** | 2026-07-16 |
| E3 | DONE-with-artifact | Per-stage wall-time `data_economics.stage_seconds` {missions/analyst/synthesis/writer} + `stage_total_seconds` + labeled `stage_top_sinks` (top-3) in `api._run_research_pipeline`. Missions already concurrent; scrape decoupled (D-02). Lock-test `tests/test_cost_speed_e.py::test_stage_seconds_and_top_sinks_in_data_economics`. ≤$1.5/<10min are owner-printed live (`docs/BASELINE-post-BC.md`). | 2026-07-16 |

---

## Open questions (from triage)

| Q | Answer | Resolved |
|---|---|---|
| Which mission calls `google_maps` today? If none → "configured-but-unused" | **None.** No `/research` mission has a maps/places tool — full tool vocabulary in `silk_missions.py` `allowed_tools` + runtime registry `silk_llm_runtime.py:143-406` has no `find_places`. `/health` shows "on" purely on key presence `api.py:315-317`. Only the OLD `/analyze` path uses it (`silk_engine.py:164-165,470-471`; `silk_research.py:395,650`). **Verdict: configured-but-unused** (matches `docs/PLATFORM_ANALYSIS.md:173`). | ☑ |
| `/products/snapshot` — any internal callers? | **None.** Route defined `api.py:1675` and calls `silk_snapshot.quick_snapshot` at `api.py:1719` only inside that endpoint. No other module imports `silk_snapshot`. External callers: frontend `web/index.html:465,484`, acceptance harness `tools/acceptance_run.py:253`, tests only. → A1 may delete the endpoint + UI (module has no other consumer). | ☑ |
| `"…"` truncation — storage or renderer? | **Both.** Assembly/STORAGE: `silk_llm_runtime._truncate_at_word` `:648-658` via `silk_market_analyst.py:140,215` (summary capped at 3000 before store/writer). RENDER: `silk_reports.py:81-92` (`_clean_report_text`, default 300). Both retreat to word boundary (mid-word bug fixed) but still append "…". | ☑ |
| WGI — mission-fetch bug or writer-mapping bug? | **Writer-mapping bug.** Fetch is FIXED + lock-tested (`silk_data_layer.py:382-385,412-444`; `tests/test_technical_mission_failures_item2.py:39,58,76`). §9 has no deterministic binding of stored WGI facts — the writer prompt sources §9 from the `risk_news` mission's own findings `silk_ai_judge.py:918-921`, so numeric PV.EST/RL.EST + جودة التنظيم are absent when the mission doesn't surface them. | ☑ |

---

## Report Quality Engine Upgrade (زبدة الفول السوداني/اليمن — تدقيق المالك التحريري)

**Principle (LESSON #32): engine fixes over report edits.** Every editorial defect
family becomes a writer-contract rule + a deterministic view-layer enforcement + a
lock-test against a production-shape reproduction blob (`tools/canonical_yemen.py`) —
never a hand-edit of one report. All rows below are **hermetic-only** (rung 1 green);
the end-to-end **live regeneration** (correct HS family via the new gate + measured
tone/length + clean exports) is the owner's paid gate (LAW §2 bucket 2), pending.

| Item | Status | Artifact (file:line / test) |
|---|---|---|
| 1.1 Verdict badge==body (AI-first single source) | DONE-with-artifact (hermetic) | `silk_render.py` `_deep_research_view` v_raw AI-first; `test_report_quality_upgrade.py::test_w1_1_verdict_badge_matches_body_verdict` |
| 1.2 HS pre-flight confirmation gate (discriminating terms) | DONE-with-artifact (hermetic) | `silk_hs_confirm.confirm_hs`; `api.py` /research 422 gate behind `SILK_HS_CONFIRM_GATE`; tests `test_w1_2_*` (classifier + gate + no-fabrication). **Image-intake path: NOT DONE** (gate covers text /research; product-intake wiring deferred). |
| 1.3 Invalidated-numbers reframe + confidence cap | DONE-with-artifact (hermetic) | `silk_render._deep_research_view` (single `CONTEXTUAL_TAG` note + `SILK_HS_FLAGGED_CONF_CAP`); writer reframe rule; `test_w1_3_*` |
| 2.1 Stale-data inline tag + `SILK_STALE_DATA_YEARS` | DONE-with-artifact (hermetic) — **redesigned to provenance-based (owner decision, LESSON #33)** | Staleness decided at the fact (`silk_staleness.fact_year`/`is_stale_fact`/`stale_fact_years` from `data_year`/`year=YYYY` marker/`retrieved_at`); tagged at the writer choke-point `silk_ai_judge._facts`; render tags the **stale-fact-year list** anywhere via `silk_render._tag_stale_years(text, stale_fact_years)` (regex demoted to conservative backstop) + `_stale_tag_misses` verification. Closes review findings #1/#2/#3/#5 in one design. `test_w2_1_*` (provenance, phrasing-independent, HS-2008-safe, food-word-safe, choke-point, verification). |
| 2.2 Seasonality gap declared once + closure step | DONE-with-artifact (hermetic) | `silk_trends_agent.SEASONALITY_GAP_CLOSURE` + `silk_render._has_seasonality_gap`; `test_w2_2_*` |
| 2.3 Weak-trends auto-broaden to category family | DONE-with-artifact (hermetic) | `silk_trends_agent.broaden_if_weak` (data-driven related term); `test_w2_3_*` |
| 3.1 Per-row price reason + single unlock | DONE-with-artifact (hermetic) | `silk_render._price_row_reason` + `PRICE_UNLOCK_LINE`; `test_w3_1_*` |
| 3.2 HHI context-only under flagged code | DONE-with-artifact (hermetic) | `silk_render` `concentration_context_only` + conf cap; `test_w3_2_*`. (Ranker /analyze HHI-score exclusion out of Yemen /research scope — noted.) |
| 4.1 De-duplicate HS warning (≤1 full note) | DONE-with-artifact (hermetic) | single `CONTEXTUAL_TAG` in limits + writer «انظر الملاحظة المنهجية»; `test_w4_1_*` |
| 4.2 Canonical section order | DONE-with-artifact (hermetic) | `silk_ai_judge._REPORT_SECTIONS`; `test_w4_2_*` |
| 4.3 Length budget (~30% tighter) | DONE-with-artifact (hermetic, contract) | `silk_style_contract.TARGET_TIGHTEN_PCT`/`PROFESSIONAL_TONE_RULE`; `test_w4_3_*`. **Measured word-count delta: owner live-regen gate.** |
| 5.1 Anti-alarmist tone + reviewer flag | DONE-with-artifact (hermetic) | Rule text `silk_style_contract.py:69` `PROFESSIONAL_TONE_RULE` (prepended to `WRITER_STYLE_CONTRACT` `:80`); banned list `:52` `ALARMIST_PHRASES` (3 examples + close variants incl. «يجب التوقف فوراً»); measured alt `:60` `MEASURED_TONE_HINT`. Deterministic reviewer enforcement in the **existing cycle, non-blocking** `silk_ai_judge.py:1188` `_alarmist_issues` → `:1278` `issues = structural + tone + llm`, reviewer-prompt line `:1250`. Tests `test_w5_1_reviewer_flags_alarmist_tone_as_nonblocking_issue`, `test_w5_1_measured_tone_draft_has_no_alarmist_issue`, **`test_w5_1_yemen_narrative_free_of_banned_phrases_and_rule_in_contract`** (Yemen narrative carries none of the 3 banned phrases nor variants). Deterministic before/after proof pasted in the exec report. **Live writer-tail regen: still owner's paid gate** (no ANTHROPIC key in CI sandbox — `available()==False`; keys live in Railway env, one-click). |
| 5.2 Sentence-length guidance | DONE-with-artifact (hermetic) | `silk_style_contract.py:66` `SENTENCE_MAX_WORDS=25` + `:73` «فضّل الجُمل القصيرة؛ الجملة التي تتجاوز خمساً وعشرين كلمة تُقسَم»; reviewer flags run-ons `silk_ai_judge.py:1252` («جُمَل مسترسِلة تتجاوز ~٢٥ كلمة»). Guidance-level, no hard char-count gate (per order). Test `test_w5_2_sentence_length_guidance_present`. |
| 6.1 Structured flip conditions + roadmap link | DONE-with-artifact (hermetic) | `silk_render._flip_conditions` (`view.flip_conditions`), rendered md + operator docx; writer roadmap-link rule; `test_w6_1_*` |
| 6.2 Exec-summary cap (verdict+flips+3 nums+3 risks) | DONE-with-artifact (writer contract) | `silk_ai_judge` deep_report 6.2 rule; `test_w6_2_*`. **Export length-cap enforcement + measured: owner live-regen gate.** |
| FINAL — live end-to-end regeneration | NOT DONE (owner paid gate) | Requires live server + paid writer tail. All engine fixes hermetic-green; regenerated committed samples updated (§10.6). |
