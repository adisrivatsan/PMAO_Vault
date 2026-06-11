# Design: PMAO Correctness Fixes + Hypotheses Feature
Date: 2026-06-09
Status: Approved

## Background

An LLM Council evaluation (4 evaluators, 2 rounds) identified three structural failures in the current pmao-cli implementation:

1. `pmao update` does not write back to the vault — a false affordance
2. `_append` accumulates string fields unboundedly — vault degrades with sustained use
3. `decisions.json` is initialized but never populated

This spec also adds a new **Hypotheses** feature: a structured log of non-intuitive ideas and emerging strategic beliefs extracted from meetings.

---

## Scope

Five files change. No new CLI commands. No changes to `cli.py`, `models.py`, `llm.py`, `transcript.py`, or `templates/`.

---

## Section 1: Correctness Fixes

### 1.1 Fix `pmao update` write-back

**Problem:** `run_update` calls `call_text` and prints LLM output. It never writes to `initiatives.json`. Users assume their tracker updated; it did not.

**Fix:** Change `run_update` to use `call_structured`. Since `claude -p` is non-interactive (no stdin during subprocess), Python captures the user's update note first, then includes it in the LLM prompt. `skills/update.md` receives both the current initiative state and the user's note, and outputs structured JSON in the same schema as `skills/ingest.md`. The parsed result flows through the existing `apply_updates` path with the same preview-and-confirm flow used by `pmao ingest`.

**Flow after fix:**
```
pmao update <vault>
→ Python prints current initiative list
→ Python prompts: "Describe the update (e.g. 'Jane confirmed budget for init-003'): "
→ User types their note
→ LLM receives: current state + user's note → outputs structured JSON
→ Preview: "2 initiatives updated, 1 action item"
→ User confirms [y/N]
→ apply_updates() writes to initiatives.json + regenerates workbook.xlsx
```

**Files:** `pmao/ingest.py` (run_update), `skills/update.md`

---

### 1.2 Fix `_append` → overwrite semantics

**Problem:** `_append` concatenates new text onto existing field values on every ingest. After repeated ingests, fields like `coordination_next_steps` become unreadable noise blobs. The audit trail for historical detail already exists in `actions.json` and `questions.json`.

**Fix:** Remove the `_append` helper. In `apply_updates`, replace all `_append` calls with direct assignment: if the extraction has a non-empty value for a field, overwrite; if empty string, leave the existing value untouched.

**Field-by-field behavior:**

| Field | Behavior |
|-------|----------|
| `current_state` | Overwrite if non-empty |
| `coordination_next_steps` | Overwrite if non-empty |
| `outstanding_questions` | Overwrite if non-empty |
| `outstanding_meetings` | Overwrite if non-empty |
| `last_touch_comment` | Overwrite if non-empty |
| `last_touch_timestamp` | Overwrite if non-empty (already did this) |
| `materials_link` | Overwrite if non-empty (already did this) |

The initiatives tab reflects current state. `actions.json` and `questions.json` remain the append-only audit logs.

**Files:** `pmao/ingest.py` (apply_updates, remove _append)

---

### 1.3 Wire `decisions.json`

**Problem:** `decisions.json` is initialized as `[]` on `pmao init` but no command ever writes to it.

**Fix:** Add a `decisions` extraction key to `skills/ingest.md`. In `apply_updates`, append confirmed decisions to `decisions.json` — same pattern as `action_items`.

**Extraction schema addition:**
```json
"decisions": [
  {
    "initiative_id": "init-001",
    "decision": "what was decided",
    "rationale": "why (if stated)",
    "owner": "who owns follow-through (if stated)",
    "source_type": "[transcript]"
  }
]
```

**Vault record written:**
```json
{
  "id": "dec-2026-06-09-0001",
  "initiative_id": "init-001",
  "decision": "...",
  "rationale": "...",
  "owner": "...",
  "status": "recorded",
  "created": "2026-06-09",
  "source": "transcript-filename.vtt",
  "source_type": "[transcript]"
}
```

Surface in `pmao summarize` under a "Decisions" section (already reads full vault state).

**Files:** `skills/ingest.md`, `pmao/ingest.py` (apply_updates)

---

## Section 2: Hypotheses Feature

### 2.1 What is a hypothesis

A hypothesis is a non-intuitive idea, emerging strategic belief, or speculative "what if" claim that surfaced in discussion. It is:
- **Not** an action item (no one is assigned to act on it yet)
- **Not** a question (not an unresolved process question)
- **Not** a decision (not something already agreed)

It is a candidate insight worth tracking and validating — e.g., "If we unbundle the onboarding fee, small practice conversion will increase by ~15%."

### 2.2 Data model

New file: `hypotheses.json`, initialized as `[]` in `vault.py`.

Each entry:
```json
{
  "id": "hyp-2026-06-09-0001",
  "initiative_id": "init-003",
  "hypothesis": "If we unbundle the onboarding fee, small practice conversion will increase ~15%",
  "owner": "Alex Chen",
  "validation_path": "Run A/B on next cohort; check 30-day activation rate",
  "status": "open",
  "source": "june-9-strategy-call.vtt",
  "source_type": "[transcript]",
  "created": "2026-06-09"
}
```

`initiative_id` is `null` for project-level hypotheses (ideas that span multiple initiatives or are directionally important to the whole project).

**Status lifecycle:** `open → exploring → confirmed | disproved | parked`

### 2.3 Extraction

Add `hypotheses` key to `skills/ingest.md` response schema:

```json
"hypotheses": [
  {
    "initiative_id": "init-001",
    "hypothesis": "the non-intuitive claim or insight",
    "owner": "First Last or empty string",
    "validation_path": "how to test/validate this, or empty string",
    "source_type": "[transcript]"
  }
]
```

Extraction instruction for the LLM (to be added to `skills/ingest.md`):

> **Hypotheses** — non-intuitive ideas, emerging strategic beliefs, or speculative "what if" claims that surfaced in discussion. Capture these when someone expresses a belief about cause-and-effect, a surprising insight, or an untested strategic assumption. These are distinct from action items (no one assigned to act) and open questions (not a process question). Use `initiative_id: null` when the idea spans multiple initiatives or applies to the project broadly. Do not force-map project-level hypotheses to a single initiative.

### 2.4 Workbook tab

New 6th tab: **Hypotheses**

Columns:
| Column | Source |
|--------|--------|
| ID | hyp-... |
| Level | "Project" if initiative_id null, "Initiative" if set |
| Initiative | resolved name from initiative_id; blank for project-level |
| Hypothesis | the claim |
| Owner | |
| Validation Path | |
| Status | open / exploring / confirmed / disproved / parked |
| Created | ISO date |
| Source | filename |

Sort order: project-level rows (Level = "Project") first, then initiative-level rows grouped by initiative name.

### 2.5 Surfaces

- `pmao summarize` — add "Emerging Hypotheses" section listing hypotheses with status `open` or `exploring`; show project-level ones first
- `pmao status` — add a count line to the dashboard: `Hypotheses: N open (X initiative-level, Y project-level)`

---

## Section 3: File Change Map

| File | What changes |
|------|-------------|
| `pmao/ingest.py` | Remove `_append`; overwrite semantics in `apply_updates`; add decisions + hypotheses processing; `run_update` uses `call_structured` + preview/confirm |
| `pmao/vault.py` | `init_vault` adds `hypotheses.json` initialization |
| `pmao/excel.py` | Add 6th Hypotheses tab; load from `hypotheses.json` |
| `skills/ingest.md` | Add `decisions` and `hypotheses` to extraction schema and instructions |
| `skills/update.md` | Change to structured JSON output; receives `{initiatives}` + `{user_note}` placeholders |

**Unchanged:** `cli.py`, `models.py`, `llm.py`, `transcript.py`, `templates/`, `vault.py` load/save functions

---

## Section 4: Success Criteria

- `pmao update` writes to `initiatives.json` and regenerates `workbook.xlsx`
- Running `pmao ingest` twice on the same source produces the same field values (idempotent, not doubled)
- `decisions.json` is populated after a `pmao ingest` run that contains a decision
- `hypotheses.json` is populated after a `pmao ingest` run that contains a non-intuitive claim
- Workbook has 6 tabs; Hypotheses tab shows project-level rows above initiative-level rows
- `pmao summarize` output includes Emerging Hypotheses and Decisions sections
