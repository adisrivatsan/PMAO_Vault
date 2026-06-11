# Final Hardening Plan — close out all three specs (ultracode)

**Date:** 2026-06-10 · **Branch:** `final-hardening` · **Baseline:** main @ 783f348, 92/92 tests

All three specs are implemented and merged. This plan finishes the project: fix the four known minor drifts, then run an exhaustive multi-agent audit of implementation vs all three spec documents, adversarially verify every finding, fix what's confirmed, and close with an end-to-end lifecycle verification.

## Phases (executed as a Workflow with sub-agents)

1. **Audit (parallel ×6):** one auditor per spec document (deep extraction / review gate / syndication) walking requirement-by-requirement against the code, plus three adversarial bug hunters with distinct lenses: lifecycle data integrity (init → deep ingest → review → syndicate → review, scripted probes), error handling & edge cases, docs/UX consistency (README vs actual behavior, prompt text).
2. **Verify:** dedup findings; critical/important findings face a 3-vote adversarial refutation panel (kept on ≥2 "real"); minors get 1 verifier. The four pre-confirmed seeds skip verification.
3. **Fix (sequential, TDD):** confirmed findings grouped by file; one fixer agent per group, failing test first, one commit each. Sequential to avoid working-tree conflicts.
4. **Final:** full regression + scripted end-to-end lifecycle run + a completeness critic checking every spec section maps to implementation.

## Pre-confirmed seeds (from the Spec 2+3 final review, items 5–8)

1. `pmao/review.py` — review file header should print per-category counts (spec "Review flow" step 1).
2. `pmao/review.py` — quit mid-file should print what was skipped, not just "left pending" (spec step 3).
3. `pmao/review.py` — reconciliation merge prompt is spec'd `[y/N]` (enter = No); `_ask` currently re-prompts on empty input.
4. `pmao/roster.py` — `render_roster(None)` fallback text says "leave principal_signals empty" (deep-ingest wording) and leaks into the syndicate prompt; make the no-roster text context-neutral.

## Accepted deviations (NOT findings — do not fix)

- Review Queue emits review_flags as their own rows instead of a flags column.
- `run_ingest_deep` lives in `pmao/deep.py`, not `pmao/ingest.py`.
- Cadence is not echoed per pathway step in syndicate output (pathway schema has no cadence field).

## Exit criteria

Full suite green, lifecycle e2e passes, completeness critic finds no unimplemented spec section, branch merged to main and pushed.
