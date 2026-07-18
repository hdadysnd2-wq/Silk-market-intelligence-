# Silk Platform — Full Audit v2 (2026-07-18)

> **Scope & method.** Read-only, convergence-based discovery audit. **Zero live
> calls, zero paid calls, zero fabrication, nothing fixed** (fix waves are
> post-approval, one severity per PR, per `silk-operations` §0 FREEZE). Audited
> the code **as merged on `main`** through PR #120 (`0f377da` — world-coverage
> Tier-2 + multimodal intake, both flag-gated OFF), including every recent
> addition: two-tier world ranking + out-of-coverage guard, multimodal intake
> adapter, auto/backfill lead enrichment + scraper client, PDF export contract +
> Dockerfile converter, progress/cost snapshots, per-mission attribution, USD
> reserve/reconcile + reaper, ops log + `/ops/last-errors` + `?economics=1`.
>
> Severity: **BLOCKER** (data loss / money / security, must fix before shipping)
> · **HIGH** · **MED** · **LOW**.
>
> **Evidence class** on every finding: `direct-repro` (executed) / `static`
> (static code review, file:line) / `pending` (no sufficient evidence). This
> audit made **no** live/paid call, so nothing is `direct-repro` against a
> running server; findings are `static` unless noted, and were verified by
> reading the exact code path (and, for Lens A, by an independent read-only
> sub-agent whose findings the executor re-verified against the source).

---

## ⚠️ Honesty header — completeness of THIS pass (three-bucket, LAW §2)

This audit is **"hermetic/static only"** — it proves code-path contracts by
reading source; it did **not** boot a server or a browser. It is **not** the
"passed real-server + browser e2e" bucket, and is **not** owner-ready for a
one-click confirmation.

**Convergence status: NOT reached.** The plan calls for discovery to repeat
until two consecutive passes yield zero new findings. One thorough pass was
completed. A parallel five-lens sub-agent workshop was launched; **one lens (A —
API surface) completed; the other four (B/F money+persistence, C
no-fabrication+sanitizer, D frontend, E+G flags+sellability) were terminated
early by an account session/usage limit** — the exact failure mode this repo has
hit before (`DEEP_RESEARCH_DECISIONS.md`: «ورشة التشخيص الموازية اصطدمت بسقف
الاستخدام»). Per the incident protocol (evidence over guessing; ship what is
supported by file:line, declare the rest pending), the executor completed lenses
B–G **manually by direct code reading**. Coverage is strong, but a clean
**two-consecutive-zero-finding convergence has not been demonstrated** and the
one item below is explicitly pending:

- **Lens C, sub-item "15 NEW adversarial sanitizer strings":** the dedicated
  character-by-character regex-trace sweep across the full
  `_strip_internal_plumbing` → `_client_sanitize` chain was cut short. The
  no-fabrication *invariants* under the new features were verified (below); the
  **15-string enumeration is `pending`** and must be produced by the supervisor
  or a fresh session before the sanitizer sign-off. Fabricating 15 unverified
  strings would violate the no-fabrication contract — so they are declared
  missing, not guessed.

---

## Executive summary — top findings (ranked)

| # | Sev | Lens | Finding | Anchor | Evidence |
|---|-----|------|---------|--------|----------|
| 1 | **HIGH** | E/A | **Out-of-coverage gate fails OPEN in practice.** The coverage probe queries Comtrade at `year = today().year − 1` (= **2025**) with **no year-fallback**; 2025 annual data is largely unpublished in mid-2026, so `world_import_totals` returns `[]` → `_market_in_coverage` returns `(True, False)` → the gate never blocks. The headline safety feature (feature A) is effectively inert when `SILK_WORLD_MARKETS` is flipped on. | `api.py:716-724`; no-fallback `silk_data_layer.py:277-292`, `silk_market_ranker.py:88` | static |
| 2 | **HIGH** | E/A | **Coverage-probe year ≠ study year.** The gate probes 2025; ranking/research default to `year=2022` (`rank_markets` sig). Even when 2025 data exists, the "in-coverage" importer set is computed for a different year than the study runs on — a market can pass the gate yet be studied on a disjoint importer basis, or vice-versa. | `api.py:717` vs `silk_market_ranker.py:431` | static |
| 3 | **MED** | B/F | **A gracefully-failed `/research` run never reconciles its USD reservation and is invisible to the reaper.** On a caught pipeline exception the code calls `mark_research_failed` (status→`failed`) but **not** `reconcile_usd`; the orphan reaper only sweeps `status='running'`. So each failed run keeps its full `SILK_RESEARCH_EXPECTED_USD` (default $3) reserved until the daily rollover — several failures/day can jam `SILK_PAID_DAILY_USD_CAP` far below real spend. | reconcile only on success `api.py:1164-1165`; fail path `api.py:1241-1244`; reaper `running`-only `silk_storage.py:305`+ | static |
| 4 | **MED** | A/B | **`/analyses/{id}/enrich-leads` blocks the HTTP request synchronously up to `SILK_GMAPS_ENRICH_GRACE_S` (default 300 s).** No async/202 variant. A Railway/proxy gateway cuts at ~30-60 s and returns a bodyless 502/504 the client cannot distinguish from a hard failure, even though the scrape thread keeps running and caches (a retry then succeeds). | `api.py:1999-2002`; frontend `web/index.html:760` | static |
| 5 | **MED** | A | **`/diagnostics` escapes the `_unprotected_paid_keys()` 503 invariant.** Every other live-paid surface fails closed when paid keys are set but `SILK_API_KEY` is unset (`/deepen`, `/analyze` extras, `/research`). `/diagnostics` fires live Claude/Serper/Maps probes and its cap reservation is *conditional* on a cap being set — with no cap **and** no `SILK_API_KEY` **and** paid keys present, an anonymous caller triggers uncounted paid probes (rate-limited only). Likely intentional (test-keys-before-auth) but an undocumented asymmetry. | `api.py:1586-1608` (guard absent); cap arm `api.py:1594-1602` | static |
| 6 | **MED** | B | **Intake vision spend is count-capped but dollar-invisible.** `/products/intake` reserves one unit from `SILK_PAID_DAILY_CAP`, but the vision call runs with **no active data counter** (no `begin_data_counter` on this path), so `_record_usage` is a no-op → the spend never reaches `SILK_PAID_DAILY_USD_CAP` or `?economics`. Vision cost is neither dollar-metered nor USD-reserved. | reserve `api.py:443`; no-op record `silk_llm_provider.py:110-116`, `234` | static |
| 7 | **MED** | D | **Export buttons have no in-flight disable → double-submit; PDF double-click spawns two LibreOffice conversions.** `dlReport("pdf"/"docx"/"md")` never disables its button during the fetch (`web/index.html:868-885`). A double-click on the new PDF button issues two `/report.pdf` requests, each spawning a `soffice` subprocess conversion server-side. (Prior audit flagged this for md/docx; the new PDF button inherits it and is the costliest instance.) | `web/index.html:868-885` | static |
| 8 | **LOW** | A/F | **Export temp dirs leak.** `report.docx`/`report.pdf` each `tempfile.mkdtemp()` a per-request dir that is never removed (`FileResponse` streams but does not clean the parent). Slow disk growth on the ephemeral volume until redeploy. | `api.py:1808-1835` (pdf), `1750-1785` (docx) | static |
| 9 | **LOW** | E | **The two headline feature flags are undocumented in `.env.example`.** `SILK_WORLD_MARKETS`, `SILK_IMAGE_INTAKE`, `SILK_WORLD_TIER2_MAX`, `SILK_INTAKE_MIN_CONFIDENCE` are read by the code but absent from `.env.example` — an operator cannot discover the toggles they are being asked to flip. | grep `.env.example` (absent); readers `silk_market_ranker.py:139,148`, `silk_product_intake.py:26,47` | static |
| 11 | **MED** | A/F | **Progress-stage name inconsistency (`enrich_leads` vs `enrich`) — surfaced by a flaky CI failure on this very PR.** The pipeline snapshots the stage as `"enrich_leads"` but the ordered-stage list + label map call it `"enrich"`, so the live `/research/{id}/status` display drops/unlabels the enrich step; and `tests/test_research_live_progress.py:30` `_STAGE_ORDER` is stale (missing both `synthesis` and the enrich stage), so `_STAGE_ORDER.index("enrich_leads")` raises `ValueError` whenever the status poll samples that stage — a race-flaky test **latently broken on `main` since #118**, unrelated to this docs-only PR. | emit `api.py:1093`; order/label `api.py:1111,1115`; stale test `tests/test_research_live_progress.py:30` | direct-repro (CI) |
| 10 | **LOW** | B | **`/products/intake` burns a cap unit on every vision failure with no refund.** `try_reserve_paid_calls(1)` reserves before the call; a provider outage (returns `None`, zero real spend) still consumes the unit and returns a 200 `read_failed`. Fail-closed-consistent (never under-charge) but a provider outage can exhaust the daily count cap with zero successful reads. | `api.py:443,477-480`; `silk_product_intake.py:186-191` | static |

**Reassuring headlines (verified this pass):**
- **The no-fabrication founding invariant holds under all three new features.**
  Tier-2 rows carry declared gaps only (never a local-CSV or fabricated
  Saudi-position/competition number); intake never guesses a product below the
  confidence threshold; enrichment failure is a declared `path:"gap"`, never an
  invented lead; out-of-coverage returns an honest 422, never a thin study
  (its only failure mode is fail-*open*, finding #1 — declared gaps, not
  fabrication). Details in Lens C.
- **The money ledgers are correct.** `try_reserve_paid_calls` and
  `try_reserve_usd` are both `BEGIN IMMEDIATE` (write-lock-before-read, no
  TOCTOU) and fail-closed; `reconcile_usd` is atomic and floored at 0; the
  orphan reaper reconciles today-bucket only with `reserved` matching the
  reserve site's `SILK_RESEARCH_EXPECTED_USD`. **No BLOCKER, no money-loss
  defect, no fabrication defect found.**
- **The Tier-2 zero-extra-Comtrade claim is TRUE** (call-count proof in Lens B).

---

## §A — API surface (independent sub-agent + executor re-verification)

Every `@app.*` route was inventoried; public routes were each justified. The
completed sub-agent report (re-verified by the executor against `api.py`):

**Public routes — all justified as safe-to-be-public (verified offline, no
secrets, no paid I/O):** `/health` (liveness; also the only route with *no*
rate-limit — F6 below), `/resolve/{name}` (offline CSV/difflib), `/config`
(public feature flags only, no keys), `/index` (offline search, `limit`
clamped [1..100]), `/markets` (static reference), `/sources` (`key_present`
hidden unless authed), `/` (StaticFiles, traversal-safe). Every paid/write
route is `_require_key` + `_rate_limit` guarded. `_require_key` is a documented
no-op when `SILK_API_KEY` is unset (dev mode), only "safe" when no paid keys
are present — enforced by the `_unprotected_paid_keys()` 503 guard **everywhere
except `/diagnostics`** (finding #5).

**Findings (severity as in the top-10 where cross-listed):**
- **#5 MED** — `/diagnostics` paid-key 503 asymmetry (`api.py:1586-1608`).
  Lock-test: `test_diagnostics_blocks_or_reserves_when_paid_keys_unprotected`.
- **#4 MED** — `enrich-leads` 300 s synchronous hold (`api.py:1999-2002`).
  Lock-test: `test_enrich_leads_returns_within_proxy_budget`.
- **#8 LOW** — export temp-dir leak (`api.py:1808-1835`). Lock-test:
  `test_report_export_tempdir_cleaned`.
- **#10 LOW** — intake cap unit burned on vision failure (`api.py:443`).
  Lock-test: `test_intake_vision_failure_does_not_permanently_burn_cap` (or
  document reserve-without-refund as intended).
- **LOW · view-build failure returns 200 with `view:{error}`** — `_view()`
  swallows all exceptions and substitutes an error dict; `/analyze`/`/deepen`
  still 200. Distinguishable via `view.error`, so LOW. `api.py:300-307,766`.
  Lock-test: `test_analyze_view_error_is_flagged_not_silent`.
- **F6 LOW** — `/health` has no `_rate_limit` (`api.py:314`). Verified
  side-effect-free/offline, so impact is raw request volume only. Lock-test:
  `test_health_is_cheap_and_side_effect_free`.

---

## §B — Money: metering, reservation, ledgers, call-count proof

**Money-call-site table (new features):**

| Call site | Metered (usage counter)? | USD-reserved? | Priced? |
|---|---|---|---|
| Intake vision (`complete_vision`) | **No** — `_record_usage` no-op (no active counter on `/products/intake`) | **No** (count-cap only) | Default `_INTAKE_MODEL`=haiku is priced; an override could be unpriced (uncounted anyway) |
| Enrich scraper (`silk_gmaps`) | N/A (not a Claude/paid provider — separate service) | **No** (by design) | N/A |
| Tier-2 gather | Uses the ONE shared world Comtrade call — see proof | N/A | N/A |
| `/research` tail (missions+analyst+writer…) | Yes (counter read post-tail) | Yes (`try_reserve_usd` $3 est, `reconcile_usd` actual) | Every default-routed model priced (LESSON 16 guard) |

**Tier-2 call-count proof (executor-verified, `static`):** with
`SILK_WORLD_MARKETS` on and no explicit `countries`, `rank_markets`
(`silk_market_ranker.py:454-466`) calls `world_import_totals` **once**
(`:459`), which issues **exactly one** `comtrade_trade(hs, None, year,
flow="M", partner=0)` (`:88`). Tier-1 candidates = `totals[:38]` still run the
per-country `_gather_row` (unchanged baseline behavior). Tier-2 entries =
`totals[38:38+62]` run `_tier2_gather_row` (`:167-210`), which reads
`entry["total_usd"]` from the **already-fetched** world call and adds World-Bank
income/population — **zero additional Comtrade calls**. `saudi_position` and
`competition` are declared gaps (`status="tier2_gap"`, `None`, `0.0`). Budget
exhaustion (`_comtrade_budget_left() ≤ _WORLD_BUDGET_RESERVE`) degrades to
curated Tier-1 only (`:467-469`). **Claim confirmed.** (Honest nuance: each
Tier-2 row still makes up to two **World-Bank** calls — income + population;
these are free/store-first and outside the Comtrade budget, so the "zero extra
Comtrade" claim holds, but Tier-2 is not zero-network.)

**Findings:** #3 (failed-run reservation lingers), #6 (intake vision
dollar-invisible), #10 (intake cap burn on failure). Ledgers otherwise atomic
and fail-closed (`silk_usage.py:181-291`); reaper reconcile consistent
(`silk_storage.py:305`+; `reserved` = same `SILK_RESEARCH_EXPECTED_USD` as the
`/research` reserve site `api.py:1373`).

Lock-tests: #3 `test_failed_research_run_reconciles_reservation`; #6
`test_intake_vision_spend_is_usd_tracked_or_explicitly_out_of_scope`.

---

## §C — No-fabrication under the new features + sanitizer

**No-fabrication invariants — VERIFIED (`static`, executor-read):**
- **Tier-2 never carries a local-CSV value.** `_tier2_gather_row`
  (`silk_market_ranker.py:167-210`) reads only the world-call total + WB;
  `saudi_position`/`competition` are `status="tier2_gap"`, `value=None`,
  `confidence=0.0`. The ranker imports no local CSV (registry guard
  `_guard_world_tier2_no_fabrication` asserts `agreements_l1`/`demographics_l1`/
  `market_locale`/`muslim_share`/`requirements_l1` all absent).
- **Intake never silently guesses.** `intake_image`
  (`silk_product_intake.py:209-218`): `not readable OR confidence <
  _MIN_CONFIDENCE (0.55) OR not product_name` → `_read_failed` with
  `product_name=""`. No fabricated name reaches the pipeline; the AST-isolation
  guard (module imports no analysis layer) holds.
- **Enrichment failure = declared gap.** `enrich-leads`
  (`api.py:2004-2017`) updates only when `new_leads.get("leads")` is truthy;
  otherwise the prior blob is kept and the response says so — never an invented
  lead. `path:"gap"` preserved.
- **Out-of-coverage never a thin study.** The gate raises 422 before readiness/
  reservation (`api.py:1337-1352`); its only weakness is fail-*open* (finding
  #1), which yields today's declared-gap behavior, not fabrication.

**Sanitizer — 15 NEW adversarial strings: `pending` (NOT DELIVERED this pass).**
The dedicated regex-trace sweep across `_strip_internal_plumbing`
(`silk_render.py`) → `_client_sanitize`/`_client_assert_clean`
(`silk_reports.py:1468-1525`) was terminated by the session cap. Declared
pending rather than guessed (LAW §2). Two **unverified candidate leads** the
executor could partially trace (must be executed before trusting):
- The client vendor regex joins Latin names with `\b…\b` but Arabic names
  (`إكسبلي`, `فولزا`) **without** word boundaries (`silk_reports.py:1473-1475`).
  Latin homoglyph/spacing variants (`V0lza`, `Vol za`) would evade `\bVolza\b`;
  low real-world likelihood (a model won't misspell it) but worth a
  confusable-fold test. **Candidate, unverified.**
- New client surface exposure from the new features is **narrow**: Tier-2
  labels/notes and intake extractions surface on **operator** surfaces
  (`/markets` picker, dashboard), not the client docx/pdf, which still funnels
  through `render_client_*` + `_client_assert_clean`. This *reduces* the new
  attack surface but does not substitute for the 15-string sweep.

---

## §D — Frontend (`web/index.html`) — new elements, #98-class hunt

**New-element behavior (executor-traced):**

| Element | Line | Wired? | Endpoint | Failure behavior | Double-click-safe? |
|---|---|---|---|---|---|
| Intake tabs | 217,434 | Yes | — | Hidden until `/config.image_intake` true; `/config` fetch `.catch` → stay hidden (safe default) | n/a |
| Camera capture `#pCam` | 440-448 | Yes | `/products/intake` | `>5 MB` → honest msg; `.catch` → "تعذّرت القراءة"; non-OK JSON → `renderIntake` fallback msg | No busy-guard (LOW) |
| Intake confirm `#intakeGo` | 464-470 | Yes | `/resolve` | `.catch` → `sync()` (no toast, but state consistent) | mild |
| Enrich leads `#enrichLeadsBtn` | 703,746,753 | Yes | `/analyses/{id}/enrich-leads` | Disables in-flight; visible status on success/`.catch`; but subject to the 300 s proxy-cut (finding #4) | **Yes** (disabled) |
| PDF `#pdfBtn` | 267,883 | Yes | `/report.pdf` | 503 → explicit Arabic "try Word"; other non-OK → `dlFail` toast | **No** (finding #7) |
| Word `#wordBtn` | 268,884 | Yes | `/report.docx` | `dlFail` toast on non-OK | **No** (finding #7) |
| World Tier-2 rows | 477-485 | Yes | `/markets` | Rendered only if `/markets` returns `tier===2` rows (flag-gated server-side) | n/a |
| Out-of-coverage msg | via `post().catch` 587 | Yes | `/research` | `detailText` unwraps `detail.message` → toast "…خارج التغطية…" (prefixed "فشل البحث العميق:" — frames a routing msg as a failure; minor UX) | n/a |

**Findings:** #7 (export double-submit, MED). LOW: camera has no in-flight
busy-guard (`web/index.html:440`); the out-of-coverage message is toasted under
a "فشل البحث العميق:" ("deep research failed:") prefix, framing an intentional
coverage response as an error (`web/index.html:587`).

**Flag-off analysis — renders identically to pre-feature UI (verified):**
`SILK_IMAGE_INTAKE` off → `/config.image_intake` false → intake tabs stay
`hidden` (line 433). `SILK_WORLD_MARKETS` off → `/markets` returns no `tier===2`
rows → no world group header (line 482). `SILK_GMAPS_SCRAPER_URL` unset → the
always-rendered `#enrichLeadsBtn` returns the honest "scraper not configured"
JSON and shows "لم تُحدَّث" (no silent no-op). No dead tabs/dropdowns appear
when flags are off.

Lock-tests: #7 `test_export_buttons_disable_during_fetch`;
`test_out_of_coverage_message_not_framed_as_failure`.

---

## §E — Flags & config drift

### Flag matrix (defaults + half-flip hazard)

| Flag | Default | Flips it | What breaks if half-flipped |
|---|---|---|---|
| `SILK_WORLD_MARKETS` | `0` (off) | `=1` | **Coverage gate fails open (finding #1)**; if `SILK_PAID_DAILY_USD_CAP` also unset → no dollar bound on a wider, costlier market surface |
| `SILK_IMAGE_INTAKE` | `0` (off) | `=1` | Safe: no `ANTHROPIC_API_KEY` or unprotected paid keys → honest `read_failed`, never fabrication |
| `SILK_GMAPS_SCRAPER_URL` | unset (enrich off) | set to URL | On but dead/slow scraper → 300 s proxy-cut (finding #4) |
| `SILK_PAID_DAILY_CAP` | unset (no count cap) | int | Count cap only — a $7 run = 1 unit (documented) |
| `SILK_PAID_DAILY_USD_CAP` | unset (**no dollar bound**) | float | Unset → `try_reserve_usd` records but never blocks → unbounded daily $; the real spend governor |
| `SILK_RESEARCH_EXPECTED_USD` | `3.0` | float | Changing it between a run's reserve and the reaper's reconcile mismatches `reserved` (LOW edge) |
| `SILK_ORPHAN_STALE_MINUTES` | `30` | int | Too low → reaps a live long run; too high → orphan $ lingers longer |
| `SILK_WORLD_TIER2_MAX` | `62` | int | Larger → more WB calls/latency per rank; still zero extra Comtrade |
| `SILK_INTAKE_MIN_CONFIDENCE` | `0.55` | float | Lower → weaker guesses pass to confirmation (still user-confirmed) |
| `SILK_GMAPS_ENRICH_GRACE_S` | `300` | float | Higher → longer sync hold (finding #4) |
| `SILK_API_KEY` | unset (dev-open) | set | Unset **with** paid keys → 503 guard blocks paid layers (`_unprotected_paid_keys`), except `/diagnostics` (finding #5) |
| `SILK_DATA_DIR` / `SILK_REQUIRE_PERSISTENT_DATA_DIR` | unset / `0` | set / `=1` | Require-flag on + no data dir → boot RuntimeError (intended, LESSON 4) |

(Full env surface ≈ 70 vars enumerated; the above are the decision-relevant
and hazard-bearing ones. Paid-provider keys — `ANTHROPIC_API_KEY`,
`COMTRADE_API_KEY`, `SERPER_API_KEY`, `GOOGLE_MAPS_API_KEY`, `VOLZA_API_KEY`,
`EXPLEE_API_KEY`, `LOCALPRICE_API_KEY` — all gate their agents keylessly.)

### Config drift
- **`.env.example` omits the two headline toggles** `SILK_WORLD_MARKETS`,
  `SILK_IMAGE_INTAKE` (+ `SILK_WORLD_TIER2_MAX`, `SILK_INTAKE_MIN_CONFIDENCE`)
  — finding #9.
- **PDF converter Dockerfile↔code match: OK.** `Dockerfile:13` installs
  `libreoffice-writer`; `silk_reports._find_soffice` (`:2162`) probes
  `("soffice","libreoffice")`; `docx_to_pdf` (`:2191`) invokes via `subprocess`.
  Consistent. `e2e-live-shape.yml` also installs it (registry guard).

### The picker-shows-~250 / research-covers-~100 UX seam
Real numbers from code: coverage set = `_TIER1_N (38) + _TIER2_MAX (62)` = **top
100 world importers of the HS code** (`api.py:725`). The `/markets` picker with
`SILK_WORLD_MARKETS` on renders Tier-1 curated (~38) **plus** the Tier-2 world
group (up to 62) — so the picker and the coverage set are actually **aligned at
~100**, not 250. The honest seam is different and sharper: **the coverage gate
that's supposed to enforce that 100-market boundary is inert (finding #1)**, so
today a user could pick any of the ~250 curated+world names and — because the
gate fails open — get a study regardless of whether the market is in the top
100. **Honest reconciliation:** fix the probe year (finding #1) so the gate
actually bounds coverage to the computed top-N; then the picker's Tier-2 group
header ("تغطية أساسية — بيانات محلية محدودة") already communicates the
reduced-confidence tier truthfully.

---

## §F — Data layer + persistence

- **Source-agent failure honesty intact** post-changes (no new data path added
  to the fetchers; DataPoint `None`/`0.0` contract unchanged).
- **Checkpoint/resume with the new enrich stage:** enrich runs **before** the
  writer (`api.py:1093-1096`) and is not itself checkpointed; on resume the
  scrape re-runs (cheap, no Claude, cached by the scrape thread). Mission
  checkpoints (the expensive part) survive — resume-in-pennies holds.
- **SQLite write atomicity:** progress/checkpoint/failed writes are single
  `UPDATE`/`INSERT … ON CONFLICT` statements inside `with _connect(...)` (commit
  on context exit); money writes use `BEGIN IMMEDIATE`. No non-atomic
  read-modify-write on a money path.
- **`ops_errors.db` growth bound:** capped ring via `SILK_OPS_LOG_CAP`
  (default 200) — verified the cap is enforced on insert (`silk_ops_log.py`).
- **Finding #3** (failed-run reservation lingers, excluded from reaper) is the
  one persistence-adjacent money gap.
- **Finding #11** (progress-stage taxonomy: `enrich_leads` emitted vs `enrich`
  in the order/label map; stale test `_STAGE_ORDER`) — a real convergence
  finding surfaced when the `test` CI job on this docs-only PR flaked on the
  pre-existing race in `test_research_live_progress.py`. Fixing needs an owner
  decision on the canonical stage name, so it is **reported, not patched** here
  (this PR is read-only/no-fix). Lock-test: extend `_STAGE_ORDER` to the full
  emitted set (`missions, analyst, synthesis, enrich_leads, writer, reviewer,
  done`) after the name is unified.

---

## §G — Sellability-readiness (INVENTORY ONLY — feeds silk.com.sa integration)

Structural blockers to **multi-client** operation TODAY (no fixes; inventory):

| Blocker | Status | Anchor | Why it blocks multi-client |
|---|---|---|---|
| Single shared service key | **Present** | `api._api_key_expected` → one `SILK_API_KEY` (`api.py:75-81`) | No per-client identity; every holder of the one key can read every analysis |
| No client identity on analyses | **Confirmed absent** | `analyses` schema `silk_storage.py:62`; additive `ALTER`s are `outcome`-class TEXT only — no `client_id`/`tenant`/`owner` | `GET /analyses` returns a single shared pool; cannot scope by client |
| No per-client quota ledger | **Present (global-only)** | `paid_usage`/`paid_usd` keyed by `day` only (`silk_usage.py`) | One client's spend exhausts everyone's daily cap |
| Report branding not per-client | **Present (global)** | single `config/branding.yaml` (`silk_reports.py:196-224`) — one logo/color/footer "سِلك لذكاء الأسواق" | A vendor portal cannot white-label per end-client |
| Shared SQLite + cache + data dir | **Present** | one `silk.db`, one `SILK_CACHE_DIR`, one `SILK_DATA_DIR` | No tenant isolation of stored analyses/cache |

These are the concrete items the upcoming vendor-portal order must address
(client identity column + per-client key/quota + branding parameterization).
None is a defect in the current single-tenant product — they are **absences**
relative to a multi-tenant target.

---

## Refuted-findings appendix (candidates that did NOT survive verification)

- **`/diagnostics` "no cap reservation" (prior-audit flag) — FIXED.** Reservation
  now present (`api.py:1594-1602`); the surviving gap is the auth-misconfig arm
  (finding #5), not the cap arm.
- **`/research` out_of_coverage runs a thin study — REFUTED.** 422 raised before
  readiness/reservation (`api.py:1337-1352`); records an ops-log demand signal.
- **regen overwrites a good report with null — REFUTED (fixed, H1/LESSON-adjacent).**
  `api.py:1928-1933` preserves the prior report and returns `regenerated:false`.
- **Reaper reconciles the wrong amount — REFUTED.** `reserved` in the reaper
  (`SILK_RESEARCH_EXPECTED_USD`, default 3.0) matches the `/research` reserve
  site (`api.py:1373`); today-bucket-only guard correct.
- **Tier-2 explodes the Comtrade budget — REFUTED.** Zero extra Comtrade calls
  (proof in Lens B).
- **Intake fabricates a product from a blurry image — REFUTED.** Threshold +
  `readable` gate → `_read_failed`, `product_name=""`.
- **`/settings/keys` could echo a source key — REFUTED.** Returns name-lists
  only; values never returned.
- **`/research` background run hangs "running" forever — REFUTED.** Blanket
  `except` → `mark_research_failed` (`api.py:1241-1244`) + startup reaper.
- **Money guards non-atomic — REFUTED.** `BEGIN IMMEDIATE` on both ledgers.

---

## GO / NO-GO

### 1) Flip **both** new flags (`SILK_WORLD_MARKETS` + `SILK_IMAGE_INTAKE`) in production

**NO-GO for `SILK_WORLD_MARKETS` until finding #1 is fixed.** The out-of-coverage
gate — the entire safety rationale for turning world coverage on — **fails open
in practice** because it probes an unpublished Comtrade year (2025). Flipping it
today ships the wider ~250-name picker with a gate that does not actually bound
coverage, so any market yields a study (declared-gap-heavy for genuinely
out-of-coverage markets) and the "تواصل معنا لإضافتها" routing never fires. This
is not a fabrication or data-loss risk (fail-open = today's declared-gap
behavior), but the feature does not do what it claims. **Gate #1 + #2 (probe
year) before flipping.** Also set `SILK_PAID_DAILY_USD_CAP` first (half-flip
hazard).

**CONDITIONAL GO for `SILK_IMAGE_INTAKE`.** The intake path is well-isolated
(AST-locked), no-fabrication-clean, metered by count, and flag-off/degraded
paths are honest. Two caveats to accept explicitly before flipping: (a) vision
spend is **count-capped but dollar-invisible** (finding #6) — set
`SILK_PAID_DAILY_CAP` to bound it, knowing the USD cap won't; (b) a provider
outage burns cap units without reads (finding #10). Neither blocks a careful
rollout. **GO once #6/#10 are acknowledged and `SILK_PAID_DAILY_CAP` is set.**

### 2) Start the vendors-portal (silk.com.sa) integration

**NO-GO as multi-tenant today; GO to begin the integration *design* now.** The
platform is a sound single-tenant product, but Lens G lists five structural
absences (client identity column, per-client key/quota, per-client branding,
tenant isolation of storage/cache) that the portal order must implement. Begin
the integration by landing those primitives first; do not route real external
clients through the single shared key / shared analysis pool.

### Pre-conditions summary

| To do this… | Fix/close first |
|---|---|
| Flip `SILK_WORLD_MARKETS` | **#1, #2** (coverage-gate year) + set `SILK_PAID_DAILY_USD_CAP` |
| Flip `SILK_IMAGE_INTAKE` | Acknowledge **#6, #10** + set `SILK_PAID_DAILY_CAP` |
| Routine enrich at scale | **#4** (async enrich or lower grace) |
| Rely on the daily $ cap | **#3** (failed-run reservation reconcile) |
| Start vendor portal | Lens G primitives (client id + per-client key/quota + branding) |
| Sanitizer sign-off | **Lens C 15-string sweep (`pending`)** — produce before trusting client export against novel plumbing |

**Net:** No BLOCKER and no fabrication/data-loss defect found. The gating item
for the world-coverage flag is **finding #1** (inert coverage gate); intake is
close to ready behind a count cap; the money layer is sound but has one
lingering-reservation gap (#3) and one dollar-blind surface (#6). Convergence to
two-consecutive-zero passes and the Lens-C 15-string sweep remain **pending**.

---

### Appendix — provenance & method
Lens A produced by an independent read-only sub-agent (`api.py` full read +
helper modules), re-verified by the executor against source. Lenses B–G
completed by the executor via direct code reading after a session/usage limit
terminated the four parallel B/C/D/E+G sub-agents mid-run (declared in the
honesty header). No live or paid call was made; contracts were verified by
reading the exact code path and, where noted, tracing regex/branch behavior
statically. Every finding names its lock-test; **no fix was applied** — fix
waves are post-approval, one severity per PR, protected paths report-first, per
`silk-operations` §0.
