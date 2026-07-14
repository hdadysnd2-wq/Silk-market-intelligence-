---
name: pr-and-wave-discipline
description: How work ships in this repo — one wave per PR from fresh main, file:line-anchored PR descriptions, the committed-samples rule §10.6, owner gates, and the evidence-labeling discipline for documenting incidents and decisions. Load before opening any PR or writing any docs/DEEP_RESEARCH_DECISIONS.md entry.
---

# PR and wave discipline — how work ships here

These rules carried through every merged wave (see `git log --oneline`: every
merged commit is `Description (#N)`). They are the owner's working contract.

## 1. The PR shape

1. **One independent PR per work wave**, branched from fresh `main`,
   squash-merged, `Title (#N)` style.
2. **The existing suite stays green and each wave ADDS its tests.** Historical
   commit messages end with the exact suite count (484→487→…→715) — keep the
   habit; it makes silent test deletion visible.
3. **PR descriptions anchor every claim to `file:line`** and state absences
   explicitly ("not found") — the `docs/AUDIT_STATUS.md` method. A reviewer must
   be able to click from claim to code.
4. **Declared deviations beat silent ones.** When constraints force breaking a
   rule (e.g. deep-research waves 1–6 shipped on one branch), the deviation is
   stated in the PR description itself.
5. Commit trailers follow the existing log style (`Co-Authored-By: …`).

## 2. Rule §10.6 — committed samples (`docs/VISION.md` ~365)

Every render-layer change (anything in `silk_render.py`, `silk_reports.py`,
`silk_narrative.py`, or view-affecting engine changes) regenerates the committed
`samples/` in the SAME PR:

```bash
python3 tools/gen_analyze_samples.py     # analysis_latest.json, brief_latest.txt, report_full_latest.docx/.md
python3 tools/gen_research_sample.py     # research_report_latest.docx (mocked Spain/dates — declared)
```

Reviewers open the files from the repo directly — no attachment channels, no
screenshots ("I sent it and it never arrived" is the incident this rule came
from). PRs #66, #69, #71 all carry `samples/` in their diffstats — that is the
norm, not the exception. The research sample is a MOCKED run (no key in the
build env — a declared gap); the recipe to replace it with a real one is in
`docs/DEEP_RESEARCH_DECISIONS.md` (live-session runbook, Step 2).

## 3. Owner gates — when to stop and ask

Large phases stop for explicit owner approval (the `docs/REBUILD_PLAN.md` gates;
"⏸ STOPPED — awaiting your approval" is the literal pattern). When a decision is
needed, do what GATE 3 did: **compute the evidence for every option and show it**
(both decision-weight options' scores were computed side by side, and an env-var
switch `SILK_DECISION_WEIGHTS=B` shipped so the owner could flip without code).
Never present one option as inevitable; never bury a decision inside an
implementation PR. Settled decisions (change-rules §B) are NOT re-opened.

## 4. Documentation duties per change type

| Change | Document where | Style |
|---|---|---|
| Incident fix / live finding | `docs/DEEP_RESEARCH_DECISIONS.md`, wave-log style | Arabic-first; every diagnosis labeled with its evidence class (see §5) |
| Architecture shift | `docs/ARCHITECTURE.md` (the current-state reference; CLAUDE.md does not cover `/research`) | Update the §3 invariant table if an invariant moved |
| Convention change | `CLAUDE.md` | Keep it terse — it is the onboarding contract |
| Never | `docs/AUDIT_STATUS.md` | Frozen point-in-time snapshot; read for method only |

Bilingual rule: Arabic-first docstrings/comments/docs with English mirrors;
user-facing strings are Arabic and are part of the tested product contract.

## 5. The evidence-labeling discipline (institutionalized by PR #71)

Every diagnosis you write down carries its evidence class, explicitly:

- **"direct reproduction"** — you ran it and saw it fail/pass.
- **"static code review (file:line)"** — traced by reading code; not executed.
- **"no sufficient evidence — pending"** — say so and stop; do NOT guess.
  The correct next move is shipping instrumentation (the PR #71 pattern:
  `last_error()`, timeout split, traced calls) so the NEXT occurrence
  self-diagnoses.

Never claim to have read logs you didn't read — the wave-7 post-mortem states
that doing so would itself violate the platform's founding principle. The same
honesty contract that governs the product's numbers governs your engineering
writing.

## 6. Pre-merge checklist

1. `python3 -m pytest tests/ -q` — green, full suite, no selection tricks.
2. New tests included for the new behavior (hermetic, same day).
3. Render touched ⇒ samples regenerated and committed (§2).
4. Prompt touched ⇒ `evals/scores.json` updated and committed
   (`python3 -m silk_evals`; >10-point drop is a declared regression).
5. PR description: file:line anchors, evidence labels, declared deviations,
   suite count.
6. Branch is one wave from fresh main; no unrelated drive-by changes.
