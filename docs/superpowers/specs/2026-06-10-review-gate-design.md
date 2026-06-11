# Review Gate — Design Spec (Spec 2 of 3)

**Date:** 2026-06-10
**Status:** Approved (decisions locked in 2026-06-10 brainstorm; implementation defaults confirmed in-session)
**Repo:** `PMAO GITHUB/pmao-cli`
**Depends on:** Spec 1 (deep extraction pipeline) — merged to main.

## Overview

`pmao review <vault>` — the human gate. Walks every `pending_review` staging file item by item, collects verdicts, promotes approved items to canonical vault files, records every verdict to `learning/verdicts.jsonl`, distills durable lessons into `learning/calibration.md` (which deep ingest already injects), and regenerates the workbook. No LLM call — this command is pure human interaction.

## CLI

`pmao review <vault>` (no --backend; no LLM). If no pending staging files: print "Nothing to review." and exit 0.

## Review flow

For each `staging/*.json` with `status: "pending_review"` (sorted by filename):

1. Print file header: source, ingested date, per-category counts, discard_note.
2. **Alias flags first** (they affect how the user reads owners): for each, show `variants -> resolved_to (confidence)`; prompt `[y]es confirm / [n]o reject`. Confirmed → calibration lesson. Rejected → calibration lesson + review continues (item owners are NOT auto-rewritten; the user can edit owners per item).
3. **Items**, category by category in `STAGED_CATEGORIES` order. Per item: display initiative, summary field, and salient fields (owner + resolution, due/timing, confidence/authority, source_span, reconciliation candidates). Prompt:
   - Normal categories: `[a]pprove / [e]dit / [r]eject`
   - Hypotheses instead: `[p]romote to fact / [k]eep as hypothesis / [x] kill`
   - `[q]uit` available everywhere: abandons the CURRENT file (its verdicts are discarded, file stays pending), prints what was skipped, exits.
4. **Edit** (`e`): re-prompt for `initiative_id`, owner, and the summary text, each defaulting to current value (empty input keeps it). Then treated as approved.
5. **Reconciliation**: if an approved item carries `reconciliation_candidates`, list them and ask `merge into existing <id>? [y/N]`. Yes → no new item is created; the verdict records `merged_into: <id>`; for action items the existing action's description gets `" [updated: <new description>]"` appended and its `due` is replaced if the new item has one. No → promote as a new item.
6. **Review flags**: printed at the end of the file, each logged to verdicts.jsonl as `acknowledged`. (Near-discards that the user decides ARE real items must be re-ingested or added via `pmao update` — the gate does not author items from flags. Each acknowledged near-discard becomes a calibration boundary lesson only when the user marks it `[o]verturn` vs `[enter]` to accept the drop.)
7. **Commit at file boundary**: all writes for a file (canonical promotions, learning appends, staging status flip to `"reviewed"` + `reviewed: <date>`) happen only after the last prompt of that file. Then `refresh_workbook`.

## Promotion mapping (system mints all IDs: `<prefix>-<date>-<counter>`)

| Staged category | Canonical file | Mapping |
|---|---|---|
| facts | `facts.json` (`fact-`) | claim, stated_by, authority, confidence, inferred, source_span + initiative_id, source, created |
| hypotheses `[p]` | `facts.json` (`fact-`) | claim=theory, stated_by=held_by, authority="unknown", confidence="high" (human-validated), inferred=false, source_span |
| hypotheses `[k]` | `hypotheses.json` (`hyp-`) | hypothesis=theory, owner=held_by, validation_path=would_confirm, status="open", source_type="[transcript]" |
| hypotheses `[x]` | nothing | verdict log only |
| decisions | `decisions.json` (`dec-`) | decision, rationale=context, owner=decided_by, status="recorded", source_type="[transcript]" |
| open_questions | `questions.json` (`q-`) | question, status="open" |
| principal_signals | `signals.json` (`sig-`) | principal, lever, signal, implication, source_span |
| meetings_to_schedule | `meetings.json` (`mtg-`) | purpose, convener, attendees, functions, target_timing, cadence (optional, Spec 3), status="open" |
| action_items | `actions.json` (`act-`) | existing schema + new optional `type` field; due="unspecified" → "" |

**Derived field:** after promoting any meetings, each touched initiative's `outstanding_meetings` free-text field is regenerated from its open `meetings.json` entries (`- <purpose> (<target_timing>)` lines), and `last_touched` is set to today. Initiatives referenced by any approved item also get `last_touched` updated.

`initiative_id` `"general"`/`null` items promote with that initiative_id preserved (no initiative fields touched).

## Learning writes

- `learning/verdicts.jsonl` (append-only): one JSON line per verdict — `{ts, staging_file, category, initiative_id, summary, verdict, merged_into?, edited?: {field: [old, new]}}`. Verdicts: approved | edited | rejected | promoted | kept | killed | alias_confirmed | alias_rejected | flag_acknowledged | flag_overturned | merged.
- `learning/calibration.md` (capped at 500 lines, oldest lines trimmed): mechanical one-line lessons, date-prefixed:
  - alias confirmed/rejected: `- 2026-06-10 alias: "Dev" → "Dev Patel" (confirmed)`
  - rejected item (boundary): `- 2026-06-10 boundary: rejected action_items: "<summary>" — do not extract similar`
  - overturned near-discard (boundary): `- 2026-06-10 boundary: near-discard overturned: "<flag>" — extract similar next time`
- `learning/` dir created on first write.

## Deep-ingest fix shipped with this spec

`run_ingest_deep` currently stages nothing when all seven categories are empty — even if `review_flags` exist. Change: stage whenever any category OR `review_flags` is non-empty, so the gate always sees near-discards. ("Nothing extracted" now requires both empty.)

## Error handling

- Corrupt staging JSON: skip the file with a warning naming it; continue with the rest.
- Unknown category keys in extraction: ignored (forward compatibility).
- EOF/Ctrl-C mid-file: same as `[q]` — current file's verdicts discarded, previously completed files stay reviewed.

## Testing

- Promotion functions tested directly per category (mapping, ID minting, counter, derived outstanding_meetings, last_touched).
- Interactive loop tested with `builtins.input` patched to scripted answer sequences: approve/edit/reject paths, hypothesis p/k/x, alias y/n, recon merge y/n, quit-mid-file leaves staging pending and canonical untouched.
- Learning: verdicts.jsonl shape; calibration line formats; 500-line cap trims oldest.
- Flags-only staging fix: extraction with only review_flags now stages.
- Full regression: quick ingest + deep ingest + export unchanged.

## Out of scope

LLM-distilled calibration; authoring new items from flags inside the gate; multi-user review; web UI.
