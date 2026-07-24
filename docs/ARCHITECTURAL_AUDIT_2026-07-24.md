# Architectural Audit — SILK-MI

**Date:** 2026-07-24 · **Auditor role:** independent senior architect · **Mode:** READ-ONLY (no production code changed, no PR of behavior, no paid/live calls).
**Pinned to:** `main` HEAD `a8abee02e2de882057261ac4da349b79b54584b2` (`a8abee0`, "hotfix: atomic source_id attribution + renderer truncation + plausibility guard (Qatar report) (#168)").
**Evidence discipline:** every status is anchored to a `file:line`, a test name, or a merged PR. Anything unprovable is marked **UNKNOWN** — that is itself a finding. Evidence class per claim: *direct reproduction* (D), *static code review* (S), *ledger/doc* (L).

> **Parallel-branch exclusion (required note).** A generalization-layer branch is reportedly in flight in a separate session. It is **NOT** part of this snapshot. Every statement in this document describes `a8abee0` only. Where the generalization work would change a finding, it is flagged; it is not credited as done.

---

## Sources Read

| # | Input | Path / location | Read? | Workstream IDs enumerable? |
|---|---|---|---|---|
| 1 | **This audit directive** | session message | ✅ | n/a |
| 2 | **Phase-1 gap elimination** | no standalone directive file on disk; reconstructed from `docs/WS_RECONCILIATION_2026-07-23.md` + `docs/DEEP_RESEARCH_DECISIONS.md` ledger + owner's message | ✅ | **WS1–WS11** (incl. WS4a/b/c). WS2/WS3/WS6 originally "undefined" in-repo; **owner supplied definitions**: WS2 = IndicatorResolver fallback chains, WS3 = snapshot cache for slow-moving official datasets, WS6 = derived-metrics engine. |
| 3 | **Hotfix directive** | no standalone file; ledger `docs/DEEP_RESEARCH_DECISIONS.md:2095–2136` + PR #168 | ✅ | **HF1–HF4** |
| 4 | **Generalization directive** | described as attached; **did not materialize as readable content** (no `docs/directives/`, no file carrying `G1`–`G6`, nothing in session context but the owner's prose theme "market generalization") | ⚠️ **theme only** | **G1–G6 item text NOT available** → Part A rows = UNKNOWN (directive text not retained/received) |
| 5 | **Analysis-depth directive** | as above; **did not materialize** (no file carrying `AWS1`–`AWS6`) | ⚠️ **theme only** | **AWS1–AWS6 item text NOT available** → Part A rows = UNKNOWN |

**Also read (on `a8abee0`):** `CLAUDE.md`; `docs/WS_RECONCILIATION_2026-07-23.md`; `docs/DEEP_RESEARCH_DECISIONS.md` (HF block + accepted-risk ledger); `docs/LESSONS.md` + `tests/test_regression_registry.py` (62 incident guards) + `tests/test_lessons_enforcement.py`; `docs/EXECUTION_PLAN.md`; `docs/GENERICNESS_AUDIT.md`; `docs/EXTERNAL_SERVICES_FAILURE_AUDIT.md`; the code (`silk_*.py`, `api.py`, `correlation.py`, `web/index.html`, `.github/workflows/*.yml`); `samples/`.

### The three reports (per audit directive, corrected by owner)

The audit's **stated real subjects are three Qatar × HS 200811 client reports.** **None is retained in-repo** — `grep -rli "qatar|قطر|200811" samples/` returns **zero**. → recorded as a Part B finding (**B-DOC-1**). The Qatar × 200811 run of 2026-07-23 survives only as a **prose incident writeup** in the ledger (`DEEP_RESEARCH_DECISIONS.md:2095+`), which is what motivated the HF1–HF4 hotfixes — not as a rendered report artifact.

What **is** on disk is the committed sample set — **all fixtures, all `⚠ TEST RUN`, none a real live run.** Provenance per `samples/README.md`:

| Sample file | Date | Market | HS | Declared-gap count | Provenance of the gap count |
|---|---|---|---|---|---|
| `samples/research_report_latest.md` | 2026-07-23 | Spain | 080410 (dates) | 1 | **Fixture** — `tools/gen_research_sample.py`, "نتيجة إسبانيا×تمور مموّهة" (masked) |
| `samples/report_full_latest.md` | 2026-07-22 | China | 080410 (dates) | 11 | **Seeded run** — `tools/gen_analyze_samples.py`, deterministic `silk_engine.analyze` with store seeded China+UAE, behind a network barrier (real engine, seeded/blocked data) |
| `samples/kuwait_peanut_butter_research_report.md` | 2026-07-22 | Kuwait | **040510** | 2 | **Fixture** — canonical peanut-butter blob; HS `040510` is a **deliberately hardcoded WRONG code** (`tools/canonical_dza_peanut_butter.py:38 DZA_WRONG_HS`) |

No declared-gap count above came from a real live run.

---

# PART A — Ground truth: what is actually on `main`

Status vocabulary: **DONE** (merged + guarded) / **PARTIAL** (some shipped, remainder deferred or scattered) / **NOT STARTED** / **SUPERSEDED** / **UNKNOWN** (cannot evidence). "DONE (hermetic)" = contracts proven by the hermetic suite; live server/browser rung not run in this audit (LAW: no paid spend without owner).

| ID | Intent (one line) | Status | Evidence (file:line · test · PR) | What remains |
|----|-------------------|--------|----------------------------------|--------------|
| **WS1** | DataPoint rung-enum + `tier`/`source_id`/`method` fields | **PARTIAL** | `source_id`/`source_ids` shipped: `silk_data_layer.py:214` (`source_ids`), `:258 is_atomic_source_id`, `:264 atomic_source_ids` (PR #168). Six-rung enum + `method` **deferred by owner text-decision**: `DEEP_RESEARCH_DECISIONS.md:1828`; reconciliation `WS_RECONCILIATION:23` | Six-rung enum + `method` field (owner decision — do not reopen from a branch) |
| **WS2** | *(owner def)* IndicatorResolver fallback chains | **UNKNOWN / NOT as-defined** | **No `IndicatorResolver` class/module exists** (grep: 0 hits). Only ad-hoc inline fallbacks: `silk_data_layer.py:549-556` (`_world_bank_for_year` latest-year), mirror fallback `:514` | The named abstraction is absent; decide whether to build it or fold WS2 into "already covered by inline fallbacks" |
| **WS3** | *(owner def)* snapshot cache for slow-moving official datasets | **PARTIAL** | Capability exists, pre-dates WS labelling: store-first freshness `silk_store.py:111,:114 fresh_days,:126 freshness` (stale-while-revalidate); seed snapshot `silk_collectors.py:122 _seed_fallback` | No net-new snapshot-cache module shipped *as WS3*; existing infra covers intent but no WS3-attributable PR |
| **WS4** | Per-source timeout + circuit breaker + fetch-failure event | **DONE (hermetic)** | `silk_data_layer.py:51 _timeout_for`, `:175 _record_fetch_failure_event`; `silk_circuit.py:28 CircuitBreaker`. Tests `test_ws4_ws11_resilience.py`, `test_p4_resilient_fetch.py`. **PR #163** | Live rung deferred (`:1891`) |
| **WS4a/b/c** | per-source timeout / per-host breaker / fetch-failure event + error hygiene | **DONE (hermetic)** | `silk_data_layer.py:51`; `silk_circuit.py:28-72`; `silk_data_layer.py:175`. Ledger `:1846/:1850/:1857` | — |
| **WS5** | Comtrade `netWgt` + partner shares/HHI | **DONE** | `silk_data_layer.py:436 primary_qty` (reads `netWgt :445`); HHI `silk_llm_runtime.py:224,:256`. Weight-gap wording fixed by HF (`test_hf_...::test_comtrade_reporter_no_weight_declares_gap_precisely`) | Nothing in-scope |
| **WS6** | *(owner def)* derived-metrics engine (TAM/SAM/SOM, HHI, unit-price, growth) | **PARTIAL** | Metrics exist but **not as one engine**: `silk_research.py:308-428` (TAM `:330`, SAM/SOM `:421-428`, growth `:319`), HHI `silk_llm_runtime.py:256`, unit-price `silk_data_layer.py:436` | No consolidated module/PR under a WS6 label; logic spread across `silk_research.py` + `silk_llm_runtime.py` |
| **WS7** | Logistics corridors / sea-transit shipping time | **PARTIAL (declared gap)** | `lead_time_days` is **clearance-only, not sea-transit**: `silk_research.py:1215-1218` (`IC.IMP.TMBC`, note "لا يشمل زمن الشحن البحري"). Ports ref `data/ports_l1.csv` | Real sea-transit source (deferred — no-fabrication of a number we don't have) |
| **WS8** | News chain GDELT→GoogleNews→Serper | **DONE (hermetic)** | `silk_google_news_agent.py:64 google_news_rss` + `news_with_fallback`. Test `test_ws8_news_fallback_chain.py`. **PR #162** | Live rung deferred (`:1822`) |
| **WS9** | References section = union of used sources | **DONE (restored by HF1)** | `silk_reports.py:2602 _client_references_section`; `references_integrity` gate `silk_evals.py:288/326`. Regressed via composite attribution, re-fixed. **PR #168** | Nothing (guarded both directions) |
| **WS10** | Clean report body of evidence badges/columns | **DONE (hermetic)** | `clean_body` gate `silk_evals.py:288,488-494`. Tests `test_ws10_golden_case.py`, `test_ws10_deterministic_no_evidence_columns.py`, `test_ws10_writer_prompt_no_evidence_columns.py`. **PR #164 + #165** | Live measured eval deferred (`:1984`) |
| **WS11** | Identity hardening + resilient Trends snapshot (WS11.1) | **DONE (hermetic)** | `silk_trends_agent.py:78 trends_interest_resilient`. Test `test_ws4_ws11_resilience.py:184`. **PR #163** | Nothing in-scope |
| **HF1** | Composite → atomic `source_id` | **DONE** | `silk_llm_runtime.py:1178-1184`; `silk_data_layer.py:214/258/264`. Tests `test_hf_attribution_truncation_plausibility.py`. **PR #168** | — |
| **HF2** | Truncation mid-number / empty parens | **DONE** | `silk_reports.py:168 _trim_sentence`; `silk_render.py:599 _DP_GROUP_RE,:601 _EMPTY_CITATION_GROUP_RE`. **PR #168** | — |
| **HF3** | Cross-source plausibility guard | **DONE — but Qatar/importer-shaped** (see Part B / **DEF-1**) | `silk_plausibility.py` (motivating case Qatar × 200811 in docstring `:6-7`); `:147 check_magnitudes,:207 annotate,:249 caveat_lines`. **PR #168** | Shape defect open — see DEF-1 |
| **HF4** | Minor fixes (EN prelim-note strip, sanitize disclosure gating, entity annotation, weight-gap wording) | **DONE** | `DEEP_RESEARCH_DECISIONS.md:2129-2136`; tests `test_hf_...`. **PR #168** | — |
| **G1–G6** | Generalization directive | **UNKNOWN** | **Directive text not on disk / not received.** Cannot enumerate or status the items. | Provide G1–G6 item text to populate this row. Substance (market-agnosticism) is audited from code in Part B / Part F Q1 regardless. |
| **AWS1–AWS6** | Analysis-depth directive | **UNKNOWN** | **Directive text not on disk / not received.** | Provide AWS1–AWS6 item text. The underlying symptom (data-starved → template report) is characterized in `docs/GENERICNESS_AUDIT.md` and Part F Q3. |

**Cross-cutting facts for Part A**

- **Hermetic suite (D):** bare checkout **fails collection** (5 `ModuleNotFoundError`, incl. `pandas`, which is **transitive-only via `pytrends`**, not a top-level `requirements.txt` entry). After installing test deps: **1837 passed, 20 skipped, ~5 min** (CLAUDE.md's "~5s" is stale). The 20 skips are exactly the money/live rungs (see Part E).
- **Every "DONE" item is "hermetic only."** No paid live regression run in this audit (LAW).
- **All four HFs shipped in one PR (#168)** despite being framed as four items.

---

# PART B — Architectural defect inventory

Class: **ARCHITECTURAL** (wrong structural decision, keeps generating symptoms) / **LOCALIZED** (contained) / **COSMETIC**. Each defect names the *future* market/product it breaks even if it looks fine today.

## The recurring failure mode: assumptions baked in from the markets we happened to test

The pipeline has **one correct config-driven template — `silk_prerun.py`** (origin from `SILK_ORIGIN_ISO3`, restrictions from `data/restricted_markets.csv`, guarded by `test_wave1p5_prerun_advisories.py` asserting zero hardcoded country/HS in logic). **Almost nothing else follows that discipline.** The defects below are all deviations from it, clustered around two baked shapes: *"the target market is a small importer with negligible domestic production"* (Qatar-shape) and *"the target market is in the EU"* (Netherlands/EU-shape).

### DEF-1 — HF3 plausibility guard is Qatar-shaped — **ARCHITECTURAL** · owner-flagged
`silk_plausibility.py:100-103, 147-204` (anchors `:128-146`, thresholds `:38-39`).
The guard flags a "market size" magnitude as implausible when it exceeds **total customs imports** by >20× (`_DEF_MAX_IMPORT_MULT = 20.0`) or implies >$500/capita/yr. The anchor is `imports_usd`. The code comment states the assumption outright: *"مضاعِفٌ مفرطٌ لسوقٍ قليلةِ الإنتاج المحليّ"* (excessive multiplier **for a market with little domestic production**).
**Breaks for producer markets.** For any target that produces the good domestically (peanuts → Nigeria/Egypt/Argentina; dates → Iran/Iraq/Algeria; honey → Turkey/Ethiopia), true market size = domestic production + imports legitimately runs 20×–200× imports. The guard then **caveats a correct number** ("cannot be reconciled with official trade data") or, under `SILK_PLAUSIBILITY_ACTION=drop`, **silently drops it** with only a manifest note. This is a *plausible-but-wrong-in-reverse*: it discredits true figures. There is **no domestic-production term** in the anchor and **no env var changes the shape** (only the thresholds). Default-ON, severity "high". Motivating case in the docstring is literally Qatar × HS 200811.
*Note:* the "fail-safe open" (no anchor → no judgment) protects the no-data case but **not** the producer-market case, where the imports anchor exists and is simply the wrong denominator.

### DEF-2 — `silk_requirements_agent._EU` lists only 15 of 27 members — **ARCHITECTURAL (correctness bug)**
`silk_requirements_agent.py:37-39, 60, 92-94`.
```
_EU = {DEU,FRA,ITA,ESP,NLD,BEL,AUT,SWE,DNK,FIN,POL,CZE,PRT,GRC,IRL}   # 15 of 27
```
This is **decision logic** (which requirement rows + codification tier apply, and whether the EU 2017/625 animal-origin eligibility gate fires), not reference data. **Missing: HUN, ROU, SVK, HRV, BGR, LUX, CYP, MLT, EST, LVA, LTU, SVN.** A shipment to Hungary or Romania **silently falls through** to "verify locally" and **misses the entire EU compliance chain**. Worse, `silk_tariffs_agent.py:30-33` carries the *full* 27-member `_EU_ISO3` — **two divergent hardcoded EU lists, one wrong.** Breaks for the 12 EU members absent from this set.

### DEF-3 — EU-only regulatory emphasis for every product/market — **ARCHITECTURAL**
`silk_ai_judge.py:729-763` (`_HS_CATEGORY`).
Every HS chapter is mapped to **EU frameworks** (CE, REACH, EMC, homologation, BRC/IFS/FSSC). For any non-EU target — USA (FDA/FCC/UL), Japan (PSE/JIS), China (CCC/GB), Gulf (GSO/SASO) — the pipeline emits the wrong compliance emphasis for **every product**. Deterministic, runs on all markets. Advisory text, not a hard gate, but structurally EU-centric — will keep surfacing wrong requirement language on every non-EU run. The standards names belong in `data/requirements_l1.csv`, not in the judge module (see DEF-9).

### DEF-4 — LLM narrative writer can inject a number that no finding contains — **ARCHITECTURAL (top silent-failure)**
`silk_ai_judge.py:917-919` (prompt-only rule), `1386-1387` + `1455-1459` (review), `1468` (default 1 cycle), `1533-1534` (ship path).
Every **structured** number is provenance-locked (Part F Q2). But the deep-research **narrative prose** is guarded only by (a) a prompt instruction "every number must appear literally in the facts" and (b) a single **probabilistic fast-LLM reviewer** whose finding only forces a revision if it self-labels `blocking`. **There is no deterministic post-generation check** that prose numbers appear in the structured findings (all deterministic checks — `_writer_incomplete :1210`, `_section_order_issues :1255`, `_alarmist_issues :1330`, `_repeated_key_figure_issues :1346` — are structural/stylistic only). A fabricated CAGR, HHI, price/kg, or segment size that the reviewer misses ships into the client report reading clean and sourced. This is the **single most dangerous surface for a paid product.**

### DEF-5 — Origin abstraction is half-built: `SILK_ORIGIN_ISO3` exists but is bypassed by literal `"SAU"` almost everywhere — **ARCHITECTURAL (latent; generalization-scope)**
Correct config point exists: `silk_prerun.origin_iso3()` (`silk_prerun.py:33-35`, default SAU). Bypassed by hardcoded `"SAU"` in: `silk_render.py:2023` (view header), `silk_tariffs_agent.py:122,245,299`, `silk_llm_runtime.py:292`, `silk_requirements_agent.py:200`, `silk_engine.py:516`, `silk_volza_agent.py:37,144`; plus `saudi_share`/`saudi_momentum` as a **named scoring pillar** (`silk_decision.py:80,87,95,100`; `silk_render.py:483-486`; `silk_discovery.py:106-115`).
**Judgment:** origin=SAU is the **intended product premise** (Silk = Saudi export house), so this does **NOT** break today's Saudi reports. But the *existence* of `SILK_ORIGIN_ISO3` proves the intent to generalize origin, and the abstraction is applied in exactly one module. If the (unread) **G directive** includes origin generalization, this scattered literal is the bulk of that work; if origin stays SAU, these are correct-by-premise. Classified latent-architectural pending G text.

### DEF-6 — `mirror_saudi_export` / "Saudi position" as a structural market-size component — **ARCHITECTURAL (coupled to DEF-5)**
`silk_research.py:501-502, 806, 815`; `silk_data_layer_v2.mirror_saudi_export`; `silk_quality.py:38,52,60`.
The "Saudi share/position" arm queries `reporter=SAU`. For a target that is itself a major producer/exporter of the good, or any non-SAU origin, the component is mis-framed. Same premise question as DEF-5.

### DEF-7 — B-DOC-1: the audit's real subjects are not retained; a known-wrong-HS fixture sits unmarked in `samples/` — **LOCALIZED (landmine)**
The three Qatar × 200811 client reports do not exist on disk. Separately, `samples/kuwait_peanut_butter_research_report.md` ships HS **040510** (dairy butter) for peanut butter, with **no "superseded" marker** — a reader of `samples/` sees a plausible-but-wrong classification presented as an output sample. It *is* a deliberate fixture (`tools/canonical_dza_peanut_butter.py:38 DZA_WRONG_HS`, comment "تصنيف خاطئ، يُصلَح في مسار آخر"), but nothing in the rendered sample says so.
**Important correction (evidence over recollection):** the owner's hypothesis that "the resolver maps peanut butter → butter" is **NOT true at HEAD.** Live hermetic run: `زبدة الفول السوداني` → **200811** (conf 1.0), `peanut butter` → **200811** (conf 1.0). The bug was **real historically and fixed in PR #157** (`bee589e`, "HS butter-family accuracy fix"), which also added the distinctive-adjective guard (`silk_hs_resolver.py:179-200`, `silk_hs_confirm.confirm_hs`, fail-safe open — verified sound/general). The residual risk is the **stale fixture**, not the resolver.

### DEF-8 — Stale value with a missing structural year renders as current — **ARCHITECTURAL (latent regression surface)**
`silk_staleness.py:58-84` (`fact_year` returns `None` when `data_year` absent + no `year=` note + `retrieved_at`=today), `:87-109` (`None` year ⇒ "not stale"), `silk_render.py:1831-1835` (`_tag_stale_years` never tags it). The guarantee holds **only because** current collectors set `data_year` (`silk_data_layer.py:634-635`, `silk_market_ranker.py:364,420`, `silk_llm_runtime.py:182,192`). **Any new/edited collector that forgets `data_year` silently reintroduces the Yemen-"2008"-family failure** (stale year shown as current) with no alarm and no guard test forbidding it. (The ranker's own year-fallback is honest — `silk_market_ranker.py:500-538` resolves the real `eff_year` and declares it.)

### DEF-9 — Regulation numbers/standards embedded in code, not the requirements CSV — **LOCALIZED (structural smell)**
`silk_research.py:741-745` derives the `eligibility_gate` boolean by substring-matching the literal `"2017/625"` — an equivalent gate under any non-EU regulation won't set it. `silk_ai_judge._HS_CATEGORY` (DEF-3) hardcodes CE/REACH/EMC. The correct home is `data/requirements_l1.csv` (which already cites regulation numbers per row).

### DEF-10 — Plausibility guard is opt-out-able and narrow — **MEDIUM (see DEF-1 sibling)**
`silk_plausibility.py:34-37` (`SILK_PLAUSIBILITY=0` disables entirely — silent pass), `:47-51` (default action "caveat" leaves the number in place), scope limited to market-size magnitudes only (`:100-103`) — a fabricated **price, CAGR, or HHI is out of scope**. So even where DEF-4's writer invents a non-market-size number, this guard cannot catch it.

### Lower-severity (contained) — logged for completeness
- **LOCALIZED:** `silk_quality.py:16` `_NEAR_ZERO_USD=1000.0` hardcoded (flags a genuinely tiny niche market as bad data); `silk_decision.py:88-100` scoring normalizers tuned to a mid-size-importer profile (TAM caps at 1e9, income at $50k, CAGR band −10..+30); `silk_hs_resolver.py:53-89` chapter-27 exclusion (Saudi non-oil *policy* baked in resolver — by design, but silently drops ch.27 products); `silk_requirements_agent.py:43,71-74` animal-origin EU-establishment gate (import-into-EU shaped, data-gated so mostly OK); `silk_hs_classifier.py:436` `product+"|"+ingredients` cache key (low collision surface, cache-only).
- **COSMETIC:** `silk_market_analyst.py:155` "Albert Heijn/Jumbo" Dutch retailers hardwired as the pricing-ladder example inside a "generic" prompt; `silk_ai_judge.py:964` "no conversion to Riyal" (SAR-shaped framing; USD-only is otherwise defensible as Comtrade's native unit).

### Composite-`source_id` sibling hunt (the known fix-induced-regression family)
The PR #168 atomic fix is **present and sound** (`silk_data_layer.py:251-264` reject «،»/«؛» joins; `silk_reports.py:2276-2287,2580-2623` resolve each source-id to its own link). **No other composite-source-id-style attribution bug found.** Only concatenated key with any collision surface is the `silk_hs_classifier.py:436` cache key (cache-scoped, not attribution) — noted above. Other `f"{a}:{b}"` uses (`silk_google_news_agent.py:49`, `silk_gmaps.py:289` sha1, `silk_collectors.py:95`) are collision-safe or display-only.

---

# PART C — Dependency and sequencing map (judgment)

### The spine (single points of failure)
- **`silk_render.build_view()` (`silk_render.py:1915`) is the one convergence point** — dashboard, terminal `format_result`, Streamlit `app.py`, `silk_reports.py` (docx/client-docx/markdown/brief), and `view["brief"]` all derive from it. A break here blocks **every** output. Reports depend on **the view**, not on a product_card/profile.
- **Two pipelines, three "research" names** (naming trap): `/analyze` → `silk_engine.analyze`; `/research` → `silk_missions.deep_research` (`api.py:1374,1404`) → `result["deep_research"]` → `_deep_research_view` (`silk_render.py:1621`) → `build_view`. **`silk_research.ResearchOrchestrator` is a dead-ish optional branch** (lazy `silk_engine.py:391`, `silk_decision.py:210`), NOT on the `/research` path — a standing confusion risk, not an active blocker.
- **There is no "profile layer."** `product_card` (pydantic `ProductCard`, `api.py:279/337/1106`) flows only into `silk_engine.analyze` and **gates correlation** (`correlation.py:141`); absent, correlation is skipped, not blocked. `silk_product_intake.py` is structurally isolated (AST guard `test_regression_registry.py:365-377` forbids it importing the engine). So the AWS-directive question "must the profile layer land before analysis depth?" is **moot as posed — no profile layer exists to block on.**

### Blockers vs. safe-parallel vs. cheap-high-impact
- **Blocker:** DEF-1 producer-market fix needs a **domestic-production signal** — FAOSTAT is already a connector (`silk_faostat_agent.py`), so the anchor can be widened without a new integration. Nothing else blocks it.
- **Safe-parallel (independent):** DEF-2 (`_EU` list), DEF-4 (number-provenance verifier — `silk_quality_gate.style_digest` tokenizer already exists), DEF-8 (collector `data_year` guard test), DEF-7 (mark/remove stale sample), DEF-3/DEF-9 (move standards to CSV). None depend on each other.
- **Cheap + high-impact:** DEF-2 (S, one list), DEF-8 (S, one guard test), DEF-7 (S, delete/mark one file), pandas→requirements (S). 
- **Expensive + high-impact:** the genericness/analysis-depth problem (data-starved → ~82–100% template report, `docs/GENERICNESS_AUDIT.md`) and DEF-4's deterministic verifier.
- **Expensive + low-impact (engineer-visible only):** consolidating WS2/WS3/WS6 into named modules — pure refactor of already-working capability; do only if it unblocks something.

### Where the existing directive ordering is wrong (audit contradicts prior instructions)
1. **HF3 (DEF-1) should not have been marked "done."** It closed the Qatar symptom by *encoding* the Qatar shape — a fix-induced architectural regression. It needs a follow-up before any producer-market report ships.
2. **The AWS sequencing premise ("profile layer → analysis depth → live baseline") is built on a layer that doesn't exist.** Re-scope against `build_view` + enrichment-flag activation, not a profile layer.
3. **WS2/WS3/WS6 as "reconcile the label" work is low value.** The capability exists; renaming it into an `IndicatorResolver`/engine buys nothing a client sees. Deprioritize below every DEF above.

---

# PART D — The single prioritized roadmap

Effort in **agent work-sessions** (S ≈ 1, M ≈ 2–3, L ≈ 4+). **Impact** answered by one test: *does it change what the client sees, or only what the engineer sees?* → **CLIENT** vs **ENG**.

| # | Item | Class | Effort | Impact | Blocks | Rationale |
|---|------|-------|--------|--------|--------|-----------|
| **1** | **DEF-4** — deterministic number-provenance verifier on the /research narrative (promote a prose number absent from findings to a *blocking* issue) | ARCH | M | **CLIENT** | — | Only remaining path for a fabricated number to reach a paid client report. Founding-principle breach. Tokenizer already exists (`style_digest`). |
| **2** | **DEF-1** — de-Qatar-shape the plausibility guard: add a domestic-production anchor (FAOSTAT) or producer-market detection before caveating/dropping market-size | ARCH | M | **CLIENT** | producer-market reports | Today it discredits *true* numbers for every producer market. Owner-flagged. |
| **3** | **DEF-2** — complete `_EU` to 27 members (or derive from the tariffs module's `_EU_ISO3`); add a guard test that the two EU lists agree | ARCH | S | **CLIENT** | EU compliance chain for 12 states | Cheap; silently drops the whole compliance section for Hungary/Romania/etc. |
| **4** | **DEF-8** — lessons-enforcement/AST test asserting every value-bearing collector sets `data_year` | ARCH | S | CLIENT (prevents regression) | — | Locks the Yemen-2008 family shut before the next collector reopens it. |
| **5** | **DEF-7** — remove or visibly mark the stale wrong-HS sample; record "no real Qatar reports retained" | LOCAL | S | ENG | — | Landmine in `samples/`; also the audit's stated subjects are missing. |
| **6** | **Genericness / analysis-depth** — make the enrichment layers actually fire for a normal run and raise market-specific content above the ~18–53% floor (this is the substance of the unread **AWS** directive) | ARCH | L | **CLIENT** | v1 "professional" bar | The difference between a real study and a token-substituted template. Scope against `build_view` + flag activation, not a profile layer. **Needs AWS text to finalize scope.** |
| **7** | **DEF-3 / DEF-9** — move standards/regulation emphasis out of `_HS_CATEGORY`/`silk_research` string-match into `data/requirements_l1.csv`; select by market | ARCH | M | CLIENT (non-EU targets) | correct non-EU compliance language | Removes the EU-shape from the judge for every non-EU market. |
| **8** | **DEF-10** — widen the plausibility guard beyond market-size and make the caveat unconditional for client exports (remove the `=0` off-switch on the delivery path) | LOCAL | S | CLIENT | — | Closes the price/CAGR/HHI gap and the opt-out. |
| **9** | pandas → top-level `requirements.txt`; wire **Rung 4** (dry cost-path) into a workflow | LOCAL | S | ENG | reliable CI | Removes transitive-dep CI fragility; closes the one unwired rung. |
| **10** | **DEF-5 / DEF-6** — route all origin through `origin_iso3()`; rename `saudi_*` pillars to origin-relative | ARCH | L | ENG (today) / CLIENT (if multi-origin) | multi-origin product | **Only if the G directive wants multi-origin.** Otherwise correct-by-premise; do not spend. |
| **11** | Consolidate WS2 (`IndicatorResolver`), WS3 (snapshot-cache module), WS6 (derived-metrics engine) into named modules | LOCAL | M | ENG | — | Pure label/refactor of working capability. Lowest value. |

**v1 release cut (a report a paying exporter would call professional):** **#1, #2, #3, #4, #5, #6.** These are the items where the client sees a fabricated number, a discredited-true number, a missing compliance section, a stale year, or a generic template. Everything from #7 down is post-v1 polish or engineer-facing, **except** #7/#8 which strengthen non-EU correctness and should land soon after.

**Post-v1:** #7, #8, #9, #10 (conditional on G), #11.

---

# PART E — Risk register

### E.1 Silent-failure risks (ranked first — most dangerous for a paid product)
1. **DEF-4 — writer-invented narrative number** (`silk_ai_judge.py:917-919`). Plausible fabricated figure passes the probabilistic reviewer → clean-looking, sourced-looking, wrong. **No structural catch.** #1 risk.
2. **DEF-1 — plausibility guard discredits/drops a TRUE producer-market number** (`silk_plausibility.py:100-103`). Client is told a correct figure is untrustworthy, or never sees it.
3. **DEF-8 — stale year rendered as current** (`silk_staleness.py:58-109`). One forgetful collector reintroduces Yemen-2008 with no alarm.
4. **DEF-2 — EU compliance chain silently dropped** for 12 member states (`silk_requirements_agent.py:37-39`). Report looks complete; the eligibility gate simply never fired.
5. **DEF-3 — wrong (EU) compliance emphasis** emitted confidently for every non-EU market.
6. **Canonical seed values are production-shaped** (`tools/canonical_netherlands.py:11`) and would NOT trip `_assert_production_clean`'s denylist (`silk_reports.py:26`) if they ever populated a production store — an ops/seeding risk, not a render leak.

### E.2 Live-unverified assumptions (proven only hermetically)
**Every paid connector is hermetic-only.** Call sites: Comtrade `silk_data_layer.py:497/613` (key-gated/budgeted), Volza `silk_volza_agent.py:66`, Explee `silk_explee_agent.py:67`, LocalPrice `silk_localprice_agent.py:122`, Serper `silk_websearch_agent.py:89`, Maps `silk_maps_agent.py:53`, GMaps scraper `silk_gmaps.py:154`, Anthropic `silk_llm_provider.py:197`. **The only connector with any automated live coverage is World Bank**, and only opt-in (`test_live_smoke.py`, `live-smoke.yml`, `workflow_dispatch`, `SILK_RUN_LIVE=1`). Failure modes that hermetic tests **cannot** catch: a provider changing its schema/auth, a real Comtrade throttle path (`docs/GENERICNESS_AUDIT.md` shows the keyless throttled case renders ~82% template), Anthropic response-shape drift.
**CI rungs:** Rung 1 (`ci.yml`) and **Rungs 2+3 (`e2e-live-shape.yml`, real uvicorn + chromium, paid providers simulated) run on every push/PR.** **Rung 4 (dry cost-path) is documented but wired to NO workflow.** Whether `e2e-live-shape` is a **required** check is set in GitHub branch protection (owner UI) — **UNKNOWN from source** (`e2e-live-shape.yml` header defers it to the owner).

### E.3 Known accepted risks already recorded (still acceptable?)
From `docs/EXECUTION_PLAN.md`: SQLite-stays / Postgres deferred (`:105`), selective wave-3 agents (`:110`), trade-finance deferred (`:113`) — **all still acceptable** (owner-settled, no client impact).
From `docs/DEEP_RESEARCH_DECISIONS.md`: measured eval + before/after report pair deferred (`:1930/:1954`) — **re-examine**, it's the evidence a v1 needs; live-proof deferred for lack of env key (`:1177/:1335`); phantom-cap false-429 near cap (`:1246`); WTO/Comtrade `ReadTimeout` permanent case not addressed (`:1734/:1770`).
From `docs/LESSONS.md` registry (open, guarded-not-fixed): **L1 parallel-missions cache-window race** ("known, not yet fixed", ThreadPoolExecutor still in `silk_missions.py`, guard `:167-172`); **L2 redaction min-length** ("structurally open", guard `:135-141`); L3/L4 fail-open by design (out-of-coverage market, prerun advisories off-by-default).
**Open case (not a ledger line):** `writer-timeout-open-case` skill — deep-research `report=None` writer failure marked **UNRESOLVED** across PRs 69/70/71. Given DEF-4 lives in the same writer, treat the writer as the highest-risk module overall.

---

# PART F — Straight answers

**1. Is the platform genuinely market-agnostic today?**
**No — target-market-agnostic in the data layer, but shaped by importer- and EU-assumptions in the analysis/requirements/plausibility layers.** Specifically: DEF-1 (plausibility assumes imports≈consumption → breaks producer markets), DEF-2 (`_EU` 15/27 → breaks 12 EU states), DEF-3 (`_HS_CATEGORY` EU-only standards → wrong for every non-EU target), DEF-9 (`2017/625` string-gate). Origin is intentionally SAU (product premise), so DEF-5/DEF-6 are *not* market-agnosticism defects unless the G directive mandates multi-origin. **Product-agnostic:** mostly yes, except the ch.27 policy exclusion (by design) and the EU-shaped requirement language. The one module that *is* properly agnostic — `silk_prerun.py` — is the template the rest should be refactored toward.

**2. Is there any remaining path by which a fabricated or unverifiable number can reach a client report? Trace it.**
**Yes — exactly one, and it is DEF-4.** Every *structured* number is closed: `build_view.components_detail` forces a source line per figure (`silk_render.py:1957-1969`), `None`→"—" never 0 (`silk_reports.py:74-75`), `_client_assert_clean` hard-raises on plumbing leaks (`:2161-2175`), `_assert_production_clean` rejects fixture markers in untagged runs (`:30-45`). The open path: **deep-research narrative writer** invents a number → prompt rule (`silk_ai_judge.py:917-919`) is text-only → single fast-LLM reviewer (`:1386-1387`) only forces revision if it self-labels `blocking` (`:1455-1459`) → **no deterministic prose-number-vs-findings check exists** → report ships (`:1533-1534`). Roadmap #1 closes it.

**3. Minimum remaining work for a report a paying exporter would call professional?**
Roadmap **#1–#6**: (a) close the fabricated-number path (#1), (b) stop discrediting true producer-market numbers (#2), (c) restore the EU compliance chain for all 27 (#3), (d) lock stale-year (#4), (e) clear the wrong-HS landmine sample (#5), and above all (f) **raise the report above the ~18–53% market-specific / ~82% template floor** documented in `docs/GENERICNESS_AUDIT.md` (#6 — the substance of the unread AWS directive). Without #6 the report is structurally a fill-in-the-blanks template; with it, the other five make it *trustworthy*.

**4. Which prior directive items are now obsolete or wrong and should be dropped rather than done?**
- **HF3 "done"** — drop the "done" status; it encoded the Qatar shape (DEF-1) and needs the producer-market follow-up, not closure.
- **WS2/WS3/WS6 as label-reconciliation** — drop as busywork; the capability exists (Part A). Only build the named modules if a concrete need appears (roadmap #11, lowest).
- **The AWS "profile layer → analysis depth → live baseline" sequencing** — wrong as posed; **no profile layer exists** (Part C). Re-scope against `build_view` + enrichment-flag activation.
- **WS1 six-rung enum + `method`** — leave deferred (owner text-decision); not obsolete, just not now.

**5. If you could only do three things next, which three, and why?**
1. **Roadmap #1 (DEF-4 number-provenance verifier).** It is the only way a *fabricated* number reaches a paying client — a direct breach of the founding principle, and it lives in the writer module that is already the repo's #1 unresolved-failure surface.
2. **Roadmap #2 (DEF-1 de-Qatar-shape plausibility).** It is the owner-flagged defect and it actively *discredits correct data* for every producer market — the reactive loop's latest instance, and it will recur on the next non-Qatar market until the shape (not the threshold) changes.
3. **Roadmap #3 (DEF-2 complete `_EU`).** One-session, cheap, and it silently deletes the entire compliance section for 12 EU destinations today — the highest impact-per-effort correctness fix on the board.

*Why these three over #6 (genericness):* #6 is the biggest quality lever but is L-effort and needs the AWS directive text to scope correctly; #1–#3 are the bleeding wounds (fabrication, discredited-truth, missing-compliance) that a single paid report would expose, and together they cost ~M+S+S.

---

## Definition-of-done check
`## Sources Read` is complete and verifiable (SHA-pinned; two directives declared missing, not reconstructed). Part D is the single ordered list; its **v1 cut (#1–#6)** defines "finished" for a ship-worthy report. Remaining gate on full completeness: **G1–G6 and AWS1–AWS6 item text** — supply it to convert those two Part A rows and finalize roadmap #6/#10 scope.
