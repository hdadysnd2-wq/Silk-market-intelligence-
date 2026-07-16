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
| 1 | Triage & baseline | read-only | Report + frozen BASELINE + ledger updated | ☐ |
| 2 | UI cleanup | A1–A3 | Zero orphan strings (grep pasted) + live UI: 2 actions + sidebar | ☐ |
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

| Item | Status | Evidence (path / grep / URL / printed output) | Date |
|---|---|---|---|
| A1 | | | |
| A2 | | | |
| A3 | | | |
| B1 | | | |
| B2 | | | |
| B3 | | | |
| C1 | | | |
| C2 | | | |
| C3 | | | |
| C4 | | | |
| C5 | | | |
| D1 | | | |
| D2 | | | |
| D3 | | | |
| E1 | | | |
| E2 | | | |
| E3 | | | |

---

## Open questions (from triage)

| Q | Answer | Resolved |
|---|---|---|
| Which mission calls `google_maps` today? If none → "configured-but-unused" | | ☐ |
| `/products/snapshot` — any internal callers? | | ☐ |
| `"…"` truncation — storage or renderer? | | ☐ |
| WGI — mission-fetch bug or writer-mapping bug? | | ☐ |
