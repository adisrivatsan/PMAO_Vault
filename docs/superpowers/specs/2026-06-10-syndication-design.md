# Syndication & Cadence — Design Spec (Spec 3 of 3)

**Date:** 2026-06-10
**Status:** Approved (decisions locked in 2026-06-10 brainstorm; cadence folded in per user direction)
**Repo:** `PMAO GITHUB/pmao-cli`
**Depends on:** Spec 1 (merged); Spec 2 (review gate — proposals flow through it).

## Overview

`pmao syndicate <vault> --initiative <id>` recommends the **syndication pathway** for an initiative — which stakeholders must see it before approval, why, in what sequence, and on what **cadence** (one-time vs recurring rhythm). The pathway is printed to the terminal; the recommended meetings are written to `staging/` as proposals that flow through the same `pmao review` gate before landing in `meetings.json`.

## CLI

`pmao syndicate <vault> --initiative <id> [--backend claude|codex]`
- Unknown initiative id → clean error listing valid ids.
- Missing roster.yaml → warn and proceed (recommendations will name roles/functions instead of resolved people).

## Skill: `skills/syndicate.md`

Same `.replace()` placeholder pattern. Placeholders:
- `{initiative}` — the full initiative record (all fields, pretty-printed)
- `{roster}` — rendered roster (same `render_roster` output; DECISION-MAKER markers drive who must sign off)
- `{history}` — this initiative's recorded decisions, open questions, open/scheduled meetings (from meetings.json), and current outstanding_meetings text
- `{signals}` — this initiative's principal signals (what each decision-maker cares about — drives sequencing and agenda emphasis)

Skill instructs: recommend the minimal stakeholder pathway to approval — sequence matters (e.g., data owner before decision-maker); each step names stakeholder(s), why they must see it, what they need to see, and timing relative to other steps; recommend a cadence per meeting: `"one-time"` or a recurrence with an end trigger (e.g., `"biweekly until pricing review"`); do not re-propose meetings that already exist open in the history; strict JSON out.

Output schema:

```json
{
  "pathway": [
    {"step": 1, "stakeholders": ["..."], "purpose": "", "why": "", "needs": "", "timing": ""}
  ],
  "meetings_to_schedule": [
    {
      "initiative_id": "<the id>",
      "purpose": "", "convener": "resolved name or null",
      "convener_resolution": "matched_roster|alias_merged|unresolved",
      "attendees": ["..."], "requester": "syndication",
      "functions": ["..."], "target_timing": "...",
      "cadence": "one-time | weekly | biweekly | monthly | <freq> until <trigger>",
      "related_decision": null, "related_question": null,
      "committee_ownership": false, "reconciliation_candidates": [],
      "source_span": "pathway step N"
    }
  ],
  "review_flags": ["anything uncertain about the pathway"]
}
```

## Flow (`run_syndicate` in new `pmao/syndicate.py`)

1. Load initiative (error if unknown), roster (warn if absent), history, signals.
2. Build prompt from `skills/syndicate.md`; `llm.call_structured`.
3. Print the pathway as a numbered list (step, stakeholders, why, timing, cadence).
4. Wrap `meetings_to_schedule` + `review_flags` into a standard staging extraction (other categories empty) and write via the Spec 1 staging writer, source name `syndicate-<initiative-id>`; existing open meetings for the initiative are injected into the prompt history so the skill avoids duplicates, and any meeting the LLM still duplicates is fine — the gate catches it.
5. `refresh_workbook`; final line: `Staged N proposed meetings: staging/<file>. Run 'pmao review' to promote.`
6. Empty `meetings_to_schedule` AND empty `review_flags` → print pathway only, stage nothing.

## Cadence (the new field)

- `cadence` is an optional string on meeting objects, end to end: staged proposals → `meetings.json` on promotion (Spec 2 mapping already carries it) → new `cadence` column on the workbook Meetings tab (after `target_timing`).
- Deep-ingest meetings (Spec 1 skill) don't emit cadence — absent/empty is fine everywhere.
- No staleness scanner, no scheduler — cadence is recorded advice, acted on by humans.

## Testing

- Prompt assembly: all four placeholders filled; history includes decisions/questions/meetings; unknown initiative raises clean error.
- `run_syndicate` with mocked `llm.call_structured`: staging file written with correct shape and source name; canonical untouched; pathway printed; empty-output case stages nothing.
- Cadence: column renders on Meetings tab; promotion carries cadence into meetings.json (covered with Spec 2's promotion tests).
- Regression: full suite.

## Out of scope

Staleness/`last_touch` scanning, calendar integration, auto-scheduling, per-stakeholder deck generation.
