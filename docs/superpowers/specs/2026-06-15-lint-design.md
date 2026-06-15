# PMAO Lint Command — Design Spec

**Date:** 2026-06-15
**Status:** Approved

## Overview

Add a `pmao lint <vault>` command that performs a periodic health check on vault state. It combines a fast Python pre-filter with a single LLM call to surface staleness, completeness gaps, and semantic contradictions. Output is read-only — the user takes findings to `pmao ingest` or edits directly.

## Motivation

PMAO's `ingest` command grows the vault incrementally. Over time, state drifts: initiatives go untouched, fields are never filled in, `current_state` diverges from `next_steps`, open actions go stale. `lint` is the periodic health check that catches this drift — the missing third operation from Karpathy's Ingest / Query / **Lint** pattern.

## Command Interface

```
pmao lint <vault> [--stale-days N] [--backend claude|codex]
```

- `--stale-days N`: flag initiatives not touched in N days (default: 30; must be >= 1)
- `--backend`: same as other commands — overrides vault config and PATH auto-detect
- No `--yes` flag — lint never mutates vault state

## Architecture

Four pieces are added across existing files plus one new skill file:

| Piece | File | Description |
|---|---|---|
| Prompt template | `pmao/skills/lint.md` | New skill with 6 placeholders |
| Pre-filter | `pmao/ingest.py` | `_compute_lint_flags()` — pure Python, no LLM |
| Run function | `pmao/ingest.py` | `run_lint()` — load → flag → prompt → print |
| CLI | `pmao/cli.py` | `cmd_lint()` + argparse registration |
| Tests | `tests/test_lint.py` | Unit + integration tests |

No new modules, no new data files, no schema changes.

## Data Flow

### Step 1 — Code pre-filter (`_compute_lint_flags`)

Pure Python. Returns a dict with three lists:

- `stale`: initiatives where `date.today() - last_touched > stale_days`. Each entry: `{id, name, days_since_touch}`.
- `incomplete`: initiatives missing any of `owner`, `current_state`, `next_steps`. Each entry: `{id, name, missing_fields: [...]}`.
- `overdue_actions`: actions with `status == "open"` and a non-empty `due` date that is in the past. Each entry: `{id, description, owner, days_overdue}`. Actions with no due date are skipped.

### Step 2 — Prompt construction

`run_lint` loads all vault JSON files and builds the prompt from `lint.md` with six injections:

- `{pre_flags}` — pre-computed annotations formatted as a plain-text block (see below)
- `{initiatives}` — all initiative fields serialized (same as `run_summarize`)
- `{actions}`, `{decisions}`, `{hypotheses}`, `{facts}` — open/recorded items as compact JSON

The `{pre_flags}` block format:
```
STALE INITIATIVES (>30 days since last touch):
  init-001: Growth Strategy — 45 days ago

INCOMPLETE INITIATIVES (missing required fields):
  init-003: Pricing Strategy — missing: owner, current_state

OVERDUE OPEN ACTIONS:
  act-2026-05-01-0002: "Alex to confirm budget" — 14 days overdue
```

### Step 3 — LLM call

`call_text` — free-form markdown output, same as `run_status` and `run_summarize`. The LLM is instructed to:

1. Accept pre-flags as ground truth — do not re-derive what the code already found
2. Enrich each flag with narrative context (why is this concerning?)
3. Scan across all vault data for semantic issues the code cannot catch — contradictions between `current_state` and `next_steps`, an initiative marked `in_progress` with no open actions, a decision that conflicts with an open hypothesis, etc.

### Step 4 — Output

Printed directly. Three sections:

```
STALENESS
  ...

COMPLETENESS GAPS
  ...

SEMANTIC ISSUES
  ...
```

No mutations. No confirm prompt. Human takes findings to `pmao ingest` or edits the vault directly.

## `lint.md` Skill — Placeholder Contract

| Placeholder | Content |
|---|---|
| `{pre_flags}` | Plain-text pre-computed flag block |
| `{initiatives}` | Full initiative data (all 10 fields per initiative) |
| `{actions}` | All actions as JSON |
| `{decisions}` | All decisions as JSON |
| `{hypotheses}` | All hypotheses as JSON |
| `{facts}` | All facts as JSON |

## Error Handling

- **Empty vault** (no initiatives): print `"Nothing to lint — vault has no initiatives."` and exit cleanly without calling the LLM
- **`--stale-days < 1`**: `cmd_lint` validates and exits with an error message before any work
- **LLM errors**: `LLMError` bubbles up to `main()` in `cli.py` and prints cleanly via the existing exception handler — no new handling needed

## Testing (`tests/test_lint.py`)

**Unit tests for `_compute_lint_flags`:**
- Stale detection: initiative last touched 45 days ago with `stale_days=30` → appears in `stale`
- Not-stale: initiative touched 10 days ago → absent from `stale`
- Incomplete: initiative missing `owner` and `current_state` → appears in `incomplete` with correct `missing_fields`
- Overdue action: open action with `due` 14 days ago → appears in `overdue_actions`
- Non-overdue action: due in the future → absent
- Action with no due date: absent from `overdue_actions`

**Integration test for `run_lint`:**
- Mock `call_text` (same pattern as `tests/test_ingest.py`)
- Verify prompt contains expected pre-flag annotations
- Verify LLM output is printed

No assertions on LLM output content — that is prompt engineering, not code behavior.
