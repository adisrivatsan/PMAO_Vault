# Deep Extraction Pipeline — Design Spec (Spec 1 of 3)

**Date:** 2026-06-10
**Status:** Approved design, pending implementation plan
**Repo:** `PMAO GITHUB/pmao-cli`

## Overview

Integrate the rich transcript-extraction skill (`transcript-extraction-skill.md`) into pmao-cli as a second ingest mode: `pmao ingest --deep`. Deep ingest extracts facts, hypotheses, decisions, open questions, principal signals, meetings-to-schedule, and typed action items — with provenance, alias resolution, near-discard surfacing, and reconciliation flags — and writes the result to a **staging area**. Nothing touches canonical vault files until a human review gate (Spec 2) promotes it.

The existing quick ingest (`pmao ingest`) is unchanged and coexists.

## Three-spec roadmap

| Spec | Scope | Status |
|------|-------|--------|
| **1 (this doc)** | Deep extraction: roster, adapted skill, staging writes, reconciliation injection, calibration injection (read-only), workbook tabs | Approved |
| **2** | `pmao review` gate: approve/edit/reject, promotion to canonical files, reconciliation merge/close, self-learning writes (`verdicts.jsonl` + `calibration.md`) | Sketched below |
| **3** | `pmao syndicate <initiative-id>`: recommended stakeholder pathway, proposed meetings staged through the same gate | Sketched below |

## Locked decisions (from brainstorming, 2026-06-10)

1. Coexist — new `--deep` flag, quick ingest untouched.
2. Full staging + review gate architecture (gate itself is Spec 2).
3. **Single unified roster** — no separate principal roster. One `roster.yaml`; `decision_maker: true` is an attribute that scopes principal signals.
4. All new categories persist; meetings-to-schedule consolidates with the outstanding-meetings concept.
5. Reconciliation-candidate injection: build now.
6. Chunking: deferred. `meta.chunk` fixed at `"1/1"`.
7. Initiative mapping: inject the initiative list into the skill; every item carries `initiative_id`.
8. Workbook: add Facts, Signals, Meetings (combined), and Review Queue tabs.
9. Self-learning: verdict log + mechanical calibration file. Spec 1 only **reads** `learning/calibration.md`; Spec 2 writes it.
10. Architecture approach A: parameterized skill file + separate `staging/` dir (rejected: staging-as-status in canonical files; two-pass mapping).

## Architecture

```
transcript (.vtt/.txt/.md)
   │  preprocess_transcript (existing)
   ▼
prompt assembly:  skills/ingest-deep.md
   + {initiatives}                 ← initiatives.json
   + {roster}                      ← roster.yaml
   + {reconciliation_candidates}   ← open actions + recent decisions
   + {calibration}                 ← learning/calibration.md (if present)
   + {source}                      ← preprocessed transcript
   │  call_structured (existing)
   ▼
staging/<date>-<source-slug>.json   (status: pending_review)
   │  Spec 2 gate (pmao review)
   ▼
canonical: initiatives.json, actions.json, questions.json,
           decisions.json, hypotheses.json, facts.json,
           signals.json, meetings.json
   ▼
workbook.xlsx (regenerated; Review Queue tab reflects staging)
```

## New vault files

### `roster.yaml` (hand-maintained, optional)

```yaml
people:
  - name: Sarah Klein
    aliases: [Sarah, Sarah K]
    role: VP Finance
    domains: [finance, pricing]
    decision_maker: true        # optional; scopes principal signals
    levers: [budget, pricing]   # optional; only meaningful with decision_maker
  - name: Dev Patel
    aliases: [Dev]
    role: Analyst
    domains: [cost model]
```

- Used for: owner/alias resolution, fact-vs-hypothesis authority (domain ownership), and principal-signal scoping (`decision_maker: true` people only).
- **Optional:** if absent, deep ingest prints a warning, the prompt states no roster was provided, and the skill marks authority `"unknown"` with lowered confidence (per the skill's own rule). Never a hard failure.

### `staging/<YYYY-MM-DD>-<source-slug>.json`

One file per deep-ingest run. Filename collisions get a `-2`, `-3` suffix.

```json
{
  "status": "pending_review",
  "ingested": "2026-06-10",
  "source": "2026-06-09-pricing-sync.vtt",
  "prompt_version": "pmao-deep-v1.0",
  "extraction": { ...full LLM output, verbatim, including meta... }
}
```

The extraction is stored verbatim — the gate (Spec 2) must see exactly what the extractor produced, including `review_flags`, `alias_flags`, `discard_note`, and near-discards.

### Canonical homes (schemas defined now; **written only by the Spec 2 gate**)

- `facts.json` — `id`, `initiative_id`, `claim`, `stated_by`, `authority`, `confidence`, `inferred`, `source_span`, `source`, `created`
- `signals.json` — `id`, `initiative_id`, `principal`, `lever`, `signal`, `implication`, `source_span`, `source`, `created`
- `meetings.json` — `id`, `initiative_id`, `purpose`, `convener`, `attendees`, `requester`, `functions`, `target_timing`, `related_decision`, `related_question`, `status` (`open`/`scheduled`/`done`), `source`, `created`

**Meetings consolidation rule:** `meetings.json` is canonical. On promotion (Spec 2), each initiative's free-text `outstanding_meetings` field is regenerated from its open `meetings.json` entries — the text field becomes derived, so existing views (quick ingest, status, summarize, Initiatives tab) keep working unchanged.

## Skill adaptation — `skills/ingest-deep.md`

Derived from `transcript-extraction-skill.md` with these changes (everything not listed is kept verbatim — staging discipline, recall-over-precision, near-discard surfacing, provenance spans, alias rules, category definitions, output shape, examples):

1. **Placeholders** in the existing house style: `{initiatives}`, `{roster}`, `{reconciliation_candidates}`, `{calibration}`, `{source}`.
2. **`initiative_id` added to every item** in all seven categories: a known initiative id, `"general"` (no match), or `null` (deliberately project-level, hypotheses especially). The injected initiative list is the mapping reference. Never force-map.
3. **Unified roster section** replaces `owner_roster`/`org_chart`/`principal_roster`: one people list; domain ownership drives authority; `decision_maker: true` entries are the principals for signal scoping.
4. **Chunking language removed** (deferred); `meta.chunk` hard-coded `"1/1"`.
5. **Calibration block:** "Lessons from prior review sessions" injected before the categories section; instructs the model to apply confirmed alias maps, boundary examples, and authority corrections. Empty placeholder text when no calibration file exists.
6. **`prompt_version`** set to `pmao-deep-v1.0`, bumped on any skill edit.
7. Self-learning stub section and "note for the broader build" section dropped from the prompt (they are design notes, not extraction instructions).

## CLI behavior

`pmao ingest <vault> --source FILE --deep [--backend ...]`

Flow (`run_ingest_deep` in `pmao/ingest.py`, dispatched from `cli.py`):

1. `preprocess_transcript(source)` (existing).
2. Load initiatives; load `roster.yaml` if present (warn if absent); build reconciliation-candidate block; load calibration block.
3. Assemble prompt, `call_structured` (existing).
4. Validate: `setdefault` all top-level extraction keys; for any item whose `initiative_id` is not a known id / `"general"` / `null`, **keep the item** and append a system-generated note to `review_flags` ("unknown initiative_id 'X' on <category>: <summary>"). Never silently drop (recall over precision).
5. If the extraction is entirely empty (all categories empty): print "Nothing extracted — nothing staged." and stop.
6. Write the staging file.
7. Print a summary: counts per category, then `review_flags` and near-discards in full, `alias_flags`, `discard_note`.
8. Regenerate `workbook.xlsx` (canonical data unchanged; Review Queue tab now reflects staging).
9. Final line: `Staged for review: staging/<file>. Run 'pmao review' to promote.`

**No y/N prompt, no `apply_updates`.** Deep ingest never writes canonical files. Until Spec 2 ships, staged files accumulate harmlessly (specs are built back-to-back).

### Reconciliation injection

- Candidates: all `status: "open"` entries from `actions.json` + the 20 most recent entries from `decisions.json`, rendered one per line with their existing ids: `act-2026-06-03-0002: Dev to build cost model (owner: Dev Patel, due: 2026-06-12)`.
- The skill echoes candidate ids in `reconciliation_candidates[].existing` with a confidence — flag only, never a merge (merging is the gate's job, Spec 2).
- If both sources are empty, inject `none` and the skill skips reconciliation (per its own contract).

### Calibration injection

- If `learning/calibration.md` exists: inject its contents, capped at the **last 200 lines** (newest lessons win). If absent: inject "No prior calibration."
- Spec 1 creates nothing under `learning/` — read-only.

## Workbook changes (`pmao/excel.py`)

`create_workbook` extended to accept `facts`, `signals`, `meetings`, and `staged` (list of pending staging files' summaries). `pmao export` and the end of both ingest paths load and pass them. New tabs:

| Tab | Contents |
|-----|----------|
| **Facts** | one row per `facts.json` entry: initiative, claim, stated_by, authority, confidence, source |
| **Signals** | one row per `signals.json` entry: initiative, principal, lever, signal, implication |
| **Meetings** | combined: structured `meetings.json` rows (typed) **plus** one row per initiative with non-empty free-text `outstanding_meetings` (marked `source: initiative-field`) — single tab, per locked decision 8 |
| **Review Queue** | one row per item in every `pending_review` staging file: staging filename, category, initiative, one-line summary, flags |

All tabs render correctly when empty (header row + formatting, same pattern as the existing Hypotheses tab fix).

## Error handling

| Condition | Behavior |
|-----------|----------|
| `roster.yaml` missing | Warn, proceed; skill marks authority `unknown` |
| `roster.yaml` malformed | Hard error with line context — a wrong roster silently corrupts authority calls |
| Unknown `initiative_id` from LLM | Keep item, system-append to `review_flags` |
| LLM returns malformed JSON | Existing `call_structured` error path (unchanged) |
| Staging filename collision | `-2`, `-3` suffix |
| Empty extraction | Print notice, write nothing |

## Testing

- Prompt assembly fills all five placeholders; no `{...}` literals survive.
- Roster loading: aliases, `decision_maker`, missing file (warn path), malformed file (error path).
- Reconciliation block: open-actions filter, 20-decision cap, `none` when empty.
- Calibration: present (200-line cap), absent (placeholder text).
- Staging write: wrapper shape, verbatim extraction, collision suffix, empty-extraction skip.
- Unknown-`initiative_id` handling appends review flag and keeps item.
- Workbook: four new tabs empty and populated; Meetings tab merges both sources.
- Regression: quick ingest (`run_ingest`) byte-for-byte unchanged behavior.

## Out of scope (this spec)

- The review gate itself, promotion, ID minting for staged items, reconciliation merge/close — **Spec 2**.
- Writes to `learning/` (verdicts.jsonl, calibration.md) — **Spec 2**.
- Syndication skill — **Spec 3**.
- Transcript chunking — deferred indefinitely.
- LLM-distilled calibration, quality scoreboard — deferred (rejected for this build / future option).

## Spec 2 sketch — Review gate

`pmao review` walks each `pending_review` staging file item-by-item: approve / edit / reject; hypothesis verdicts (promote-to-fact / keep / kill); near-discard confirm/overturn; alias confirm; reconciliation merge/close against the flagged candidates. Promotion mints IDs (system, never the LLM), writes canonical files, regenerates each touched initiative's derived `outstanding_meetings` text, regenerates the workbook, and marks the staging file `reviewed`. Every verdict appends to `learning/verdicts.jsonl`; durable lessons (confirmed alias maps, keep/discard boundary examples, authority corrections) mechanically append to `learning/calibration.md` (size-capped), which Spec 1's deep ingest already injects.

## Spec 3 sketch — Syndication

`pmao syndicate <initiative-id>` + `skills/syndicate.md`. Inputs: the initiative's full state, `roster.yaml` (decision-makers, domains, levers), the initiative's `meetings.json` history and `decisions.json` entries. Output: a recommended syndication pathway — which stakeholders must see the initiative before approval, why, and in what sequence — printed to the terminal, with the recommended meetings written to `staging/` as proposals that flow through the same review gate.
