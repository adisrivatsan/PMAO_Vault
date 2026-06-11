# PMAO Correctness Fixes + Hypotheses Feature — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix three structural bugs in pmao-cli (`run_update` not writing back, `_append` accumulating unbounded noise, `decisions.json` never written) and add a new Hypotheses feature that extracts and tracks non-intuitive strategic claims.

**Architecture:** Five files change — two skill prompt files, `vault.py`, `ingest.py` (largest change), and `excel.py`. No new CLI commands, no changes to `cli.py`, `models.py`, `llm.py`, `transcript.py`, or `templates/`. All new data (decisions, hypotheses) follows the same append-to-JSON pattern already used for actions and questions.

**Tech Stack:** Python 3.9+, openpyxl, pytest (no new dependencies)

---

## Setup

All commands run from:

```bash
PMAO="PMAO GITHUB/pmao-cli"
# full path:
# /Users/adityasrivatsan/Library/CloudStorage/OneDrive-SharedLibraries-athenahealth/Corporate Strategy & Development - Documents/5 - Corporate Strategy/03 Strat Plan and LRP/2026/01 2026 LRP working teams folder/16 PRD Docs_Adi/PMAO GITHUB/pmao-cli
```

Run all tests with:

```bash
cd "$PMAO" && python -m pytest tests/ -v
```

---

## File Map

| File | Change |
|------|--------|
| `skills/ingest.md` | Add `decisions` + `hypotheses` to schema and extraction instructions |
| `skills/update.md` | Rewrite: structured JSON output; `{initiatives}` + `{user_note}` placeholders |
| `skills/summarize.md` | Add Decisions + Emerging Hypotheses section instructions |
| `pmao/vault.py` | Add `hypotheses.json` to `VAULT_FILES`; initialize in `init_vault` |
| `pmao/ingest.py` | Remove `_append`; overwrite semantics; add decisions+hypotheses to `apply_updates`; fix `run_update`; surface in `run_summarize`/`run_status` |
| `pmao/excel.py` | Add 6th Hypotheses tab; update `create_workbook` signature |
| `tests/test_ingest.py` | Remove `_append` tests; update overwrite test; add decisions/hypotheses/run_update/run_status tests |
| `tests/test_vault.py` | Add `hypotheses.json` assertion |
| `tests/test_excel.py` | Update tab count test; add Hypotheses tab tests |

---

## Task 1: Update skill prompts

No automated tests for prompt files. Do this first so later tasks have correct files to build against.

**Files:**
- Modify: `skills/ingest.md`
- Modify: `skills/update.md`
- Modify: `skills/summarize.md`

- [ ] **Step 1: Rewrite `skills/ingest.md`**

Replace the entire file with:

```markdown
---
name: pmao-ingest
description: Extract initiative updates from source material and apply to project state
---

# PMAO Ingest

You are a project management assistant. Read the source material and extract structured updates for the initiatives listed below.

## Current initiatives

{initiatives}

## Source material

{source}

## What to extract

1. **Initiative updates** — for each initiative mentioned in the source:
   - `current_state`: one-sentence summary of current status
   - `coordination_next_steps`: newline-delimited bullet list of high-level actions (e.g., "- Alex to schedule review\n- Sam to confirm budget")
   - `outstanding_questions`: newline-delimited list of unresolved questions (e.g., "- What is the budget?\n- Who owns legal review?")
   - `outstanding_meetings`: newline-delimited list of meetings that need to happen (e.g., "- Kickoff with data team\n- Review with leadership")
   - `last_touch_comment`: who communicated what and when — include source tag: `[email]`, `[transcript]`, `[teams]`, `[slack]`, `[notes]`
   - `last_touch_timestamp`: ISO date (YYYY-MM-DD) of the most recent meaningful interaction
   - `materials_link`: any document URL or file reference mentioned

2. **Action items** — each explicitly assigned to a named person:
   - `initiative_id`, `description`, `owner` (exact name), `due` (YYYY-MM-DD or empty), `status` (always "open")

3. **Open questions** — raised without a clear owner or answer:
   - `initiative_id`, `question`

4. **Decisions** — things that were confirmed, agreed, or resolved:
   - `initiative_id`, `decision` (what was decided), `rationale` (why, if stated), `owner` (who owns follow-through, if stated), `source_type`

5. **Hypotheses** — non-intuitive ideas, emerging strategic beliefs, or speculative "what if" claims that surfaced in discussion. Capture these when someone expresses a belief about cause-and-effect, a surprising insight, or an untested strategic assumption. These are distinct from action items (no one assigned to act) and open questions (not a process question). Use `initiative_id: null` when the idea spans multiple initiatives or applies to the project broadly. Do not force-map project-level hypotheses to a single initiative.
   - `initiative_id` (string or null), `hypothesis` (the claim), `owner` (First Last or empty string), `validation_path` (how to test/validate, or empty string), `source_type`

## Rules

- Only update initiatives explicitly mentioned in the source material
- Never guess owners — if ownership is unclear, add it as an open question
- Only include fields you have evidence from the source to update — omit fields you have no new information about (use empty string `""` for fields in the schema you cannot fill)
- Map all items to an initiative where possible; use `"general"` if no match; use `null` for initiative_id on project-level hypotheses
- Source tags: `[email]`, `[transcript]`, `[teams]`, `[slack]`, `[notes]`

## Response format

Respond ONLY with valid JSON matching this schema exactly:

```json
{
  "initiatives_updated": [
    {
      "initiative_id": "init-001",
      "current_state": "",
      "coordination_next_steps": "- Action one\n- Action two",
      "outstanding_questions": "- Question one",
      "outstanding_meetings": "",
      "last_touch_comment": "",
      "last_touch_timestamp": "YYYY-MM-DD",
      "materials_link": ""
    }
  ],
  "action_items": [
    {
      "initiative_id": "init-001",
      "description": "what needs to be done",
      "owner": "First Last",
      "due": "",
      "status": "open"
    }
  ],
  "open_questions": [
    {
      "initiative_id": "init-001",
      "question": "the unresolved question"
    }
  ],
  "decisions": [
    {
      "initiative_id": "init-001",
      "decision": "what was decided",
      "rationale": "why (if stated)",
      "owner": "who owns follow-through (if stated)",
      "source_type": "[transcript]"
    }
  ],
  "hypotheses": [
    {
      "initiative_id": "init-001",
      "hypothesis": "the non-intuitive claim or insight",
      "owner": "First Last or empty string",
      "validation_path": "how to test/validate this, or empty string",
      "source_type": "[transcript]"
    }
  ]
}
```

RESPOND ONLY WITH VALID JSON. NO PREAMBLE. NO EXPLANATION.
```

- [ ] **Step 2: Rewrite `skills/update.md`**

Replace the entire file with:

```markdown
---
name: pmao-update
description: Apply a user's verbal update note to the project state as structured JSON
---

# PMAO Update

You are a project management assistant. The user has described a manual update to their project. Extract structured updates from their note and output the same JSON schema used by ingest.

## Current initiatives

{initiatives}

## User's update note

{user_note}

## What to extract

Apply the same extraction logic as ingest. The user note may describe:
1. **Initiative updates** — field changes for specific initiatives
2. **Action items** — tasks assigned to named people
3. **Open questions** — unresolved items without an owner
4. **Decisions** — things confirmed, agreed, or resolved
5. **Hypotheses** — non-intuitive claims or strategic bets (use `initiative_id: null` for project-level)

## Rules

- Only update initiatives explicitly mentioned in the note
- Never guess owners — if unclear, add as an open question
- If the user says a field should be cleared, output empty string `""` for that field
- Source tag for manually entered notes: `[notes]`

## Response format

Respond ONLY with valid JSON matching this schema exactly:

```json
{
  "initiatives_updated": [
    {
      "initiative_id": "init-001",
      "current_state": "",
      "coordination_next_steps": "",
      "outstanding_questions": "",
      "outstanding_meetings": "",
      "last_touch_comment": "",
      "last_touch_timestamp": "YYYY-MM-DD",
      "materials_link": ""
    }
  ],
  "action_items": [
    {
      "initiative_id": "init-001",
      "description": "what needs to be done",
      "owner": "First Last",
      "due": "",
      "status": "open"
    }
  ],
  "open_questions": [
    {
      "initiative_id": "init-001",
      "question": "the unresolved question"
    }
  ],
  "decisions": [
    {
      "initiative_id": "init-001",
      "decision": "what was decided",
      "rationale": "",
      "owner": "",
      "source_type": "[notes]"
    }
  ],
  "hypotheses": [
    {
      "initiative_id": "init-001",
      "hypothesis": "the non-intuitive claim",
      "owner": "",
      "validation_path": "",
      "source_type": "[notes]"
    }
  ]
}
```

RESPOND ONLY WITH VALID JSON. NO PREAMBLE. NO EXPLANATION.
```

- [ ] **Step 3: Update `skills/summarize.md`**

Replace the "What to include" section and project state description with:

```markdown
---
name: pmao-summarize
description: Produce a concise executive summary of the current project state
---

# PMAO Summarize

You are a project management assistant. Produce a concise executive summary from the project state below.

## Project state

The following is a JSON object containing the full vault state:
- `initiatives`: list of all initiative objects (each has id, name, status, priority, current_state, coordination_next_steps, outstanding_questions, outstanding_meetings, last_touch_comment, last_touch_timestamp, etc.)
- `actions`: list of open action items (each has initiative_id, description, owner, due, status)
- `questions`: list of open questions (each has initiative_id, question, status)
- `decisions`: list of recorded decisions (each has initiative_id, decision, rationale, owner, created, source)
- `hypotheses`: list of tracked hypotheses (each has initiative_id or null, hypothesis, owner, validation_path, status, created)

{project_state}

## What to include

1. **Overall status** — one sentence on where the project stands
2. **Initiatives by status** — brief bullet per initiative: name, status, key next step
3. **Biggest risks or blockers** — top 2-3 items needing attention
4. **Open questions** — unresolved questions across all initiatives
5. **Upcoming meetings** — any outstanding meetings flagged
6. **What needs a decision now** — items blocked on a decision
7. **Decisions** — decisions recorded (status: recorded); if none, omit this section
8. **Emerging Hypotheses** — hypotheses with status `open` or `exploring`; show project-level (initiative_id null) first, then initiative-level; if none, omit this section

## Format

Use short labeled sections (e.g., "OVERALL", "INITIATIVES", "RISKS", "OPEN QUESTIONS", "MEETINGS", "DECISIONS NEEDED", "DECISIONS", "EMERGING HYPOTHESES"). Write in plain prose within each section — no nested bullets within sections. Keep the total output under 500 words.

## Rules

- Write for a senior stakeholder who has not been following day-to-day
- Be direct and specific — no vague language
- Only include initiatives that have meaningful status (skip "not_started" with no updates)
```

- [ ] **Step 4: Commit skill prompt updates**

```bash
cd "$PMAO"
git add skills/ingest.md skills/update.md skills/summarize.md
git commit -m "feat: add decisions and hypotheses to skill schemas; fix update.md for structured output"
```

---

## Task 2: vault.py — hypotheses.json initialization

**Files:**
- Modify: `pmao/vault.py`
- Modify: `tests/test_vault.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_vault.py`:

```python
def test_init_vault_creates_hypotheses_json():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        hyp_path = vault / "hypotheses.json"
        assert hyp_path.exists()
        assert json.loads(hyp_path.read_text()) == []
```

Also update `test_init_vault_creates_expected_files` to assert `hypotheses.json` is expected:

```python
def test_init_vault_creates_expected_files():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        for fname in VAULT_FILES:
            assert (vault / fname).exists(), f"Missing {fname}"
        assert (vault / "workbook.xlsx").exists()
        assert (vault / "transcripts").is_dir()
        assert (vault / "hypotheses.json").exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "$PMAO" && python -m pytest tests/test_vault.py::test_init_vault_creates_hypotheses_json -v
```

Expected: FAIL — `hypotheses.json` does not exist yet.

- [ ] **Step 3: Implement in `vault.py`**

In `pmao/vault.py`, add `"hypotheses.json"` to `VAULT_FILES`:

```python
VAULT_FILES = [
    "project-config.yaml",
    "initiatives.json",
    "actions.json",
    "questions.json",
    "decisions.json",
    "hypotheses.json",
    "workbook.xlsx",
]
```

In `init_vault`, after the `decisions.json` line, add:

```python
(vault_path / "hypotheses.json").write_text("[]")
```

The full `init_vault` body after the change:

```python
def init_vault(vault_path: Path, project_name: str = "My Project", owner: str = "") -> None:
    vault_path.mkdir(parents=True, exist_ok=True)
    (vault_path / "transcripts").mkdir(exist_ok=True)

    config = {
        "project_name": project_name,
        "owner": owner,
        "llm_backend": None,
        "llm_timeout_seconds": 120,
    }
    (vault_path / "project-config.yaml").write_text(yaml.dump(config, default_flow_style=False))

    (vault_path / "initiatives.json").write_text("[]")
    (vault_path / "actions.json").write_text("[]")
    (vault_path / "questions.json").write_text("[]")
    (vault_path / "decisions.json").write_text("[]")
    (vault_path / "hypotheses.json").write_text("[]")

    from pmao.excel import create_workbook
    create_workbook(vault_path / "workbook.xlsx", [])
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "$PMAO" && python -m pytest tests/test_vault.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PMAO"
git add pmao/vault.py tests/test_vault.py
git commit -m "feat: initialize hypotheses.json in init_vault"
```

---

## Task 3: ingest.py — remove `_append`, overwrite semantics

**Files:**
- Modify: `pmao/ingest.py`
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Update the test that checks append behavior → now checks overwrite**

In `tests/test_ingest.py`, replace `test_apply_updates_appends_existing_next_steps` with:

```python
def test_apply_updates_overwrites_existing_next_steps():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(status="in_progress")
        init.coordination_next_steps = "- Old step"
        save_initiatives(vault, [init])

        extraction = {
            "initiatives_updated": [{
                "initiative_id": "init-001",
                "coordination_next_steps": "- New step replaces old",
                "current_state": "",
                "outstanding_questions": "",
                "outstanding_meetings": "",
                "last_touch_comment": "",
                "last_touch_timestamp": "",
                "materials_link": "",
            }],
            "action_items": [],
            "open_questions": [],
        }
        apply_updates(vault, extraction, "source.md")

        initiatives = load_initiatives(vault)
        assert initiatives[0].coordination_next_steps == "- New step replaces old"
        assert "- Old step" not in initiatives[0].coordination_next_steps


def test_apply_updates_leaves_field_when_new_is_empty():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(status="in_progress")
        init.coordination_next_steps = "- Preserved step"
        save_initiatives(vault, [init])

        extraction = {
            "initiatives_updated": [{
                "initiative_id": "init-001",
                "coordination_next_steps": "",
                "current_state": "New state",
                "outstanding_questions": "",
                "outstanding_meetings": "",
                "last_touch_comment": "",
                "last_touch_timestamp": "",
                "materials_link": "",
            }],
            "action_items": [],
            "open_questions": [],
        }
        apply_updates(vault, extraction, "source.md")

        initiatives = load_initiatives(vault)
        assert initiatives[0].coordination_next_steps == "- Preserved step"
        assert initiatives[0].current_state == "New state"
```

Also update the import line (remove `_append`):

```python
from pmao.ingest import apply_updates, _build_ingest_prompt
```

And remove the four `_append` unit tests (`test_append_none_existing`, `test_append_empty_existing`, `test_append_extends_with_newline`, `test_append_empty_new_preserves_existing`).

Also update `test_apply_updates_maps_generic_fields` — it currently asserts on `_append` indirectly but doesn't actually test append (it starts from empty), so it's fine as-is.

- [ ] **Step 2: Run the new overwrite test to verify it fails**

```bash
cd "$PMAO" && python -m pytest tests/test_ingest.py::test_apply_updates_overwrites_existing_next_steps -v
```

Expected: FAIL — current code appends, so `"- Old step"` is still present.

- [ ] **Step 3: Implement overwrite semantics in `ingest.py`**

In `pmao/ingest.py`, remove the `_append` function entirely (lines 27–32).

Replace all `_append` calls in `apply_updates` with inline overwrite logic. The full updated loop in `apply_updates`:

```python
for update in extraction.get("initiatives_updated", []):
    iid = update.get("initiative_id")
    if iid not in idx:
        continue
    init = idx[iid]
    val = update.get("current_state", "")
    if val:
        init.current_state = val
    val = update.get("coordination_next_steps", "")
    if val:
        init.coordination_next_steps = val
    val = update.get("outstanding_questions", "")
    if val:
        init.outstanding_questions = val
    val = update.get("outstanding_meetings", "")
    if val:
        init.outstanding_meetings = val
    val = update.get("last_touch_comment", "")
    if val:
        init.last_touch_comment = val
    ts = update.get("last_touch_timestamp", "")
    if ts:
        try:
            init.last_touch_timestamp = date.fromisoformat(ts)
        except ValueError:
            pass
    if update.get("materials_link"):
        init.materials_link = update["materials_link"]
    if init.status == "not_started":
        init.status = "in_progress"
    init.last_touched = today
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
cd "$PMAO" && python -m pytest tests/test_ingest.py -v
```

Expected: All PASS. (The old `_append` tests are deleted; remaining tests pass with overwrite logic.)

- [ ] **Step 5: Commit**

```bash
cd "$PMAO"
git add pmao/ingest.py tests/test_ingest.py
git commit -m "fix: replace _append with overwrite semantics — idempotent ingest"
```

---

## Task 4: ingest.py — wire decisions.json and hypotheses.json

**Files:**
- Modify: `pmao/ingest.py`
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_ingest.py`:

```python
def test_apply_updates_writes_decisions():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = {
            "initiatives_updated": [],
            "action_items": [],
            "open_questions": [],
            "decisions": [{
                "initiative_id": "init-001",
                "decision": "Budget approved at $500K",
                "rationale": "Board approved in Q2 review",
                "owner": "Jane Smith",
                "source_type": "[transcript]",
            }],
            "hypotheses": [],
        }
        apply_updates(vault, extraction, "meeting.vtt")

        decisions = json.loads((vault / "decisions.json").read_text())
        assert len(decisions) == 1
        assert decisions[0]["decision"] == "Budget approved at $500K"
        assert decisions[0]["rationale"] == "Board approved in Q2 review"
        assert decisions[0]["owner"] == "Jane Smith"
        assert decisions[0]["status"] == "recorded"
        assert decisions[0]["source"] == "meeting.vtt"
        assert decisions[0]["id"].startswith("dec-")


def test_apply_updates_writes_hypotheses():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = {
            "initiatives_updated": [],
            "action_items": [],
            "open_questions": [],
            "decisions": [],
            "hypotheses": [{
                "initiative_id": "init-001",
                "hypothesis": "Unbundling onboarding fee will increase conversion by 15%",
                "owner": "Alex Chen",
                "validation_path": "Run A/B on next cohort",
                "source_type": "[transcript]",
            }],
        }
        apply_updates(vault, extraction, "strategy-call.vtt")

        hypotheses = json.loads((vault / "hypotheses.json").read_text())
        assert len(hypotheses) == 1
        assert hypotheses[0]["hypothesis"] == "Unbundling onboarding fee will increase conversion by 15%"
        assert hypotheses[0]["owner"] == "Alex Chen"
        assert hypotheses[0]["status"] == "open"
        assert hypotheses[0]["initiative_id"] == "init-001"
        assert hypotheses[0]["id"].startswith("hyp-")


def test_apply_updates_hypothesis_with_null_initiative_id():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = {
            "initiatives_updated": [],
            "action_items": [],
            "open_questions": [],
            "decisions": [],
            "hypotheses": [{
                "initiative_id": None,
                "hypothesis": "Market timing matters more than product quality in this segment",
                "owner": "",
                "validation_path": "",
                "source_type": "[transcript]",
            }],
        }
        apply_updates(vault, extraction, "all-hands.vtt")

        hypotheses = json.loads((vault / "hypotheses.json").read_text())
        assert len(hypotheses) == 1
        assert hypotheses[0]["initiative_id"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "$PMAO" && python -m pytest tests/test_ingest.py::test_apply_updates_writes_decisions tests/test_ingest.py::test_apply_updates_writes_hypotheses tests/test_ingest.py::test_apply_updates_hypothesis_with_null_initiative_id -v
```

Expected: All FAIL — `apply_updates` doesn't process decisions or hypotheses yet.

- [ ] **Step 3: Implement decisions + hypotheses in `apply_updates`**

In `pmao/ingest.py`, after the `questions_path.write_text(...)` block and before `save_initiatives(...)`, add:

```python
    decisions_path = vault_path / "decisions.json"
    decisions = json.loads(decisions_path.read_text()) if decisions_path.exists() else []
    for dec in extraction.get("decisions", []):
        if not dec.get("decision"):
            continue
        decisions.append({
            "id": f"dec-{today.isoformat()}-{len(decisions):04d}",
            "initiative_id": dec.get("initiative_id", ""),
            "decision": dec["decision"],
            "rationale": dec.get("rationale", ""),
            "owner": dec.get("owner", ""),
            "status": "recorded",
            "created": today.isoformat(),
            "source": transcript_name,
            "source_type": dec.get("source_type", ""),
        })
    decisions_path.write_text(json.dumps(decisions, indent=2))

    hyp_path = vault_path / "hypotheses.json"
    all_hyp = json.loads(hyp_path.read_text()) if hyp_path.exists() else []
    for hyp in extraction.get("hypotheses", []):
        if not hyp.get("hypothesis"):
            continue
        all_hyp.append({
            "id": f"hyp-{today.isoformat()}-{len(all_hyp):04d}",
            "initiative_id": hyp.get("initiative_id"),
            "hypothesis": hyp["hypothesis"],
            "owner": hyp.get("owner", ""),
            "validation_path": hyp.get("validation_path", ""),
            "status": "open",
            "source": transcript_name,
            "source_type": hyp.get("source_type", ""),
            "created": today.isoformat(),
        })
    hyp_path.write_text(json.dumps(all_hyp, indent=2))
```

Also update the `create_workbook` call at the end of `apply_updates` to pass hypotheses:

```python
    save_initiatives(vault_path, initiatives)
    create_workbook(vault_path / "workbook.xlsx", initiatives, hypotheses=all_hyp)
```

Note: `all_hyp` is already in scope from the hypotheses block above. The full tail of `apply_updates` becomes:

```python
    decisions_path.write_text(json.dumps(decisions, indent=2))

    hyp_path = vault_path / "hypotheses.json"
    all_hyp = json.loads(hyp_path.read_text()) if hyp_path.exists() else []
    for hyp in extraction.get("hypotheses", []):
        if not hyp.get("hypothesis"):
            continue
        all_hyp.append({
            "id": f"hyp-{today.isoformat()}-{len(all_hyp):04d}",
            "initiative_id": hyp.get("initiative_id"),
            "hypothesis": hyp["hypothesis"],
            "owner": hyp.get("owner", ""),
            "validation_path": hyp.get("validation_path", ""),
            "status": "open",
            "source": transcript_name,
            "source_type": hyp.get("source_type", ""),
            "created": today.isoformat(),
        })
    hyp_path.write_text(json.dumps(all_hyp, indent=2))

    save_initiatives(vault_path, initiatives)
    create_workbook(vault_path / "workbook.xlsx", initiatives, hypotheses=all_hyp)
```

Also update `run_ingest` to set defaults for the new keys:

```python
    extraction.setdefault("initiatives_updated", [])
    extraction.setdefault("action_items", [])
    extraction.setdefault("open_questions", [])
    extraction.setdefault("decisions", [])
    extraction.setdefault("hypotheses", [])
```

And update the preview print in `run_ingest`:

```python
    decisions = extraction["decisions"]
    hypotheses = extraction["hypotheses"]

    print(f"\n--- Extraction results ---")
    print(f"Initiatives updated: {len(init_updates)}")
    for u in init_updates:
        iid = u.get("initiative_id", "?")
        name = next((i.name for i in initiatives if i.id == iid), iid)
        print(f"  [{iid}] {name}")
    print(f"Action items: {len(action_items)}")
    print(f"Open questions: {len(questions)}")
    print(f"Decisions: {len(decisions)}")
    print(f"Hypotheses: {len(hypotheses)}")

    if not init_updates and not action_items and not questions and not decisions and not hypotheses:
        print("\nNothing extracted — no changes made.")
        return
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "$PMAO" && python -m pytest tests/test_ingest.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PMAO"
git add pmao/ingest.py tests/test_ingest.py
git commit -m "feat: wire decisions.json and hypotheses.json in apply_updates"
```

---

## Task 5: excel.py — add 6th Hypotheses tab

**Files:**
- Modify: `pmao/excel.py`
- Modify: `tests/test_excel.py`

- [ ] **Step 1: Write failing tests**

In `tests/test_excel.py`, update `test_workbook_has_five_tabs` to expect 6 tabs:

```python
def test_workbook_has_six_tabs():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        assert wb.sheetnames == [
            "Initiatives",
            "Full Next Steps Log",
            "Last Touch Log",
            "Meeting Requests",
            "Milestones",
            "Hypotheses",
        ]
```

(Delete the old `test_workbook_has_five_tabs`.)

Add new tests:

```python
def test_hypotheses_tab_has_headers():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        ws = wb["Hypotheses"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert headers == ["id", "level", "initiative", "hypothesis", "owner", "validation_path", "status", "created", "source"]


def test_hypotheses_tab_project_level_rows_first():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        hyps = [
            {
                "id": "hyp-2026-06-09-0001",
                "initiative_id": "init-001",
                "hypothesis": "Initiative-level hypothesis",
                "owner": "",
                "validation_path": "",
                "status": "open",
                "created": "2026-06-09",
                "source": "call.vtt",
            },
            {
                "id": "hyp-2026-06-09-0000",
                "initiative_id": None,
                "hypothesis": "Project-level hypothesis",
                "owner": "",
                "validation_path": "",
                "status": "open",
                "created": "2026-06-09",
                "source": "call.vtt",
            },
        ]
        create_workbook(path, [init], hypotheses=hyps)
        wb = load_workbook(path)
        ws = wb["Hypotheses"]
        # Row 2 should be the project-level hypothesis (initiative_id None)
        level_col = 2  # "level" is column index 2
        assert ws.cell(2, level_col).value == "Project"
        assert ws.cell(3, level_col).value == "Initiative"


def test_hypotheses_tab_populates_level_column():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        hyps = [
            {
                "id": "hyp-2026-06-09-0001",
                "initiative_id": "init-001",
                "hypothesis": "Small practices respond better to outcome-based pricing",
                "owner": "Alex Chen",
                "validation_path": "Run A/B test",
                "status": "open",
                "created": "2026-06-09",
                "source": "strategy-call.vtt",
            },
        ]
        create_workbook(path, [init], hypotheses=hyps)
        wb = load_workbook(path)
        ws = wb["Hypotheses"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        assert ws.cell(2, headers["level"]).value == "Initiative"
        assert ws.cell(2, headers["initiative"]).value == "Customer Data Platform"
        assert ws.cell(2, headers["hypothesis"]).value == "Small practices respond better to outcome-based pricing"
        assert ws.cell(2, headers["owner"]).value == "Alex Chen"
        assert ws.cell(2, headers["status"]).value == "open"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "$PMAO" && python -m pytest tests/test_excel.py::test_workbook_has_six_tabs tests/test_excel.py::test_hypotheses_tab_has_headers tests/test_excel.py::test_hypotheses_tab_project_level_rows_first -v
```

Expected: All FAIL — workbook has 5 tabs, no Hypotheses tab.

- [ ] **Step 3: Implement in `excel.py`**

Add the column definition at the top of `excel.py` (after `MILESTONE_COLS`):

```python
HYPOTHESIS_COLS = [
    "id", "level", "initiative", "hypothesis", "owner",
    "validation_path", "status", "created", "source",
]
```

Update the `create_workbook` signature to accept `hypotheses`:

```python
def create_workbook(
    path: Path,
    initiatives: List[Initiative],
    meeting_requests: Optional[list] = None,
    milestones: Optional[list] = None,
    hypotheses: Optional[list] = None,
) -> None:
```

Add the Hypotheses tab at the end of `create_workbook`, before `wb.save(path)`:

```python
    # ── Tab 6: Hypotheses ─────────────────────────────────────────────────────
    ws_hyp = wb.create_sheet("Hypotheses")
    _write_header_row(ws_hyp, HYPOTHESIS_COLS)

    if hypotheses:
        # Build initiative name lookup
        init_names = {i.id: i.name for i in initiatives}

        # Sort: project-level (initiative_id is None) first, then initiative-level by name
        project_rows = [h for h in hypotheses if not h.get("initiative_id")]
        initiative_rows = sorted(
            [h for h in hypotheses if h.get("initiative_id")],
            key=lambda h: init_names.get(h["initiative_id"], h["initiative_id"]),
        )
        sorted_hyp = project_rows + initiative_rows

        for row_num, h in enumerate(sorted_hyp, start=2):
            iid = h.get("initiative_id")
            record = {
                "id": h.get("id", ""),
                "level": "Project" if not iid else "Initiative",
                "initiative": init_names.get(iid, "") if iid else "",
                "hypothesis": h.get("hypothesis", ""),
                "owner": h.get("owner", ""),
                "validation_path": h.get("validation_path", ""),
                "status": h.get("status", ""),
                "created": h.get("created", ""),
                "source": h.get("source", ""),
            }
            _write_data_row(ws_hyp, row_num, HYPOTHESIS_COLS, record)

    ws_hyp.column_dimensions["A"].width = 22
    ws_hyp.column_dimensions["B"].width = 12
    ws_hyp.column_dimensions["C"].width = 32
    ws_hyp.column_dimensions["D"].width = 60
    ws_hyp.column_dimensions["E"].width = 20
    ws_hyp.column_dimensions["F"].width = 40
    ws_hyp.column_dimensions["G"].width = 14
    ws_hyp.column_dimensions["H"].width = 12
    ws_hyp.column_dimensions["I"].width = 30
    ws_hyp.freeze_panes = "A2"

    wb.save(path)
```

(Move `wb.save(path)` to here — it was at the end before; the Milestones tab code previously ended with `wb.save(path)`.)

- [ ] **Step 4: Run all tests to verify they pass**

```bash
cd "$PMAO" && python -m pytest tests/test_excel.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PMAO"
git add pmao/excel.py tests/test_excel.py
git commit -m "feat: add Hypotheses tab (6th tab) to workbook with project-level rows first"
```

---

## Task 6: ingest.py — fix `run_update` write-back

**Files:**
- Modify: `pmao/ingest.py`
- Modify: `tests/test_ingest.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_ingest.py` (add `from unittest.mock import patch` at the top of the imports):

```python
from unittest.mock import patch
```

Then add:

```python
def test_run_update_writes_to_vault():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(status="in_progress")
        save_initiatives(vault, [init])

        extraction = {
            "initiatives_updated": [{
                "initiative_id": "init-001",
                "current_state": "Budget confirmed by Jane",
                "coordination_next_steps": "",
                "outstanding_questions": "",
                "outstanding_meetings": "",
                "last_touch_comment": "[notes] Jane confirmed budget",
                "last_touch_timestamp": "2026-06-09",
                "materials_link": "",
            }],
            "action_items": [],
            "open_questions": [],
            "decisions": [],
            "hypotheses": [],
        }

        with patch("pmao.llm.call_structured", return_value=extraction), \
             patch("pmao.ingest._load_skill", return_value="{initiatives}\n{user_note}"), \
             patch("builtins.input", side_effect=["Jane confirmed budget for init-001", "y"]):
            from pmao.ingest import run_update
            run_update(vault, yes=False)

        initiatives = load_initiatives(vault)
        assert initiatives[0].current_state == "Budget confirmed by Jane"
        assert (vault / "workbook.xlsx").exists()


def test_run_update_aborts_on_empty_note():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative(status="in_progress")])

        with patch("pmao.ingest._load_skill", return_value="{initiatives}\n{user_note}"), \
             patch("builtins.input", return_value=""):
            from pmao.ingest import run_update
            run_update(vault, yes=False)

        initiatives = load_initiatives(vault)
        assert initiatives[0].current_state is None  # unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd "$PMAO" && python -m pytest tests/test_ingest.py::test_run_update_writes_to_vault tests/test_ingest.py::test_run_update_aborts_on_empty_note -v
```

Expected: FAIL — `run_update` uses `call_text` and never writes to vault.

- [ ] **Step 3: Implement the new `run_update` in `ingest.py`**

Replace the entire `run_update` function with:

```python
def _build_update_prompt(skill: str, initiatives: List[Initiative], user_note: str) -> str:
    init_list = "\n".join(
        f"  {i.id}: {i.name} (status: {i.status})\n"
        f"    current_state: {i.current_state or 'none'}\n"
        f"    coordination_next_steps: {i.coordination_next_steps or 'none'}"
        for i in initiatives
    )
    return skill.replace("{initiatives}", init_list).replace("{user_note}", user_note)


def run_update(vault_path: Path, config_override: str = None, yes: bool = False) -> None:
    from pmao.llm import call_structured

    initiatives = load_initiatives(vault_path)
    print("Initiatives:")
    for i in initiatives:
        print(f"  {i.id}: {i.name} ({i.status})")

    user_note = input("\nDescribe the update (e.g. 'Jane confirmed budget for init-003'): ").strip()
    if not user_note:
        print("No update provided. Aborted.")
        return

    skill = _load_skill("update")
    prompt = _build_update_prompt(skill, initiatives, user_note)

    print("Calling LLM for extraction...")
    extraction = call_structured(prompt, config_override=config_override)
    extraction.setdefault("initiatives_updated", [])
    extraction.setdefault("action_items", [])
    extraction.setdefault("open_questions", [])
    extraction.setdefault("decisions", [])
    extraction.setdefault("hypotheses", [])

    init_updates = extraction["initiatives_updated"]
    action_items = extraction["action_items"]
    questions = extraction["open_questions"]
    decisions = extraction["decisions"]
    hypotheses = extraction["hypotheses"]

    print(f"\n--- Extraction results ---")
    print(f"Initiatives updated: {len(init_updates)}")
    for u in init_updates:
        iid = u.get("initiative_id", "?")
        name = next((i.name for i in initiatives if i.id == iid), iid)
        print(f"  [{iid}] {name}")
    print(f"Action items: {len(action_items)}")
    print(f"Open questions: {len(questions)}")
    print(f"Decisions: {len(decisions)}")
    print(f"Hypotheses: {len(hypotheses)}")

    if not init_updates and not action_items and not questions and not decisions and not hypotheses:
        print("\nNothing extracted — no changes made.")
        return

    if not yes:
        answer = input("\nApply these updates? [y/N] ").strip().lower()
        if answer != "y":
            print("Aborted.")
            return

    apply_updates(vault_path, extraction, transcript_name=f"manual-update-{date.today().isoformat()}")
    print(f"\nDone. workbook.xlsx updated.")
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
cd "$PMAO" && python -m pytest tests/test_ingest.py -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PMAO"
git add pmao/ingest.py tests/test_ingest.py
git commit -m "fix: run_update now calls call_structured and writes back to vault via apply_updates"
```

---

## Task 7: ingest.py — surface decisions + hypotheses in `run_summarize` and `run_status`

**Files:**
- Modify: `pmao/ingest.py`

No automated tests for these functions (they call the live LLM). We'll verify with behavioral assertions on what data is passed.

- [ ] **Step 1: Write a unit test for `run_status` hypothesis count**

Add to `tests/test_ingest.py`:

```python
def test_run_status_prints_hypothesis_count(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        hyps = [
            {"initiative_id": "init-001", "hypothesis": "A", "status": "open", "owner": "", "validation_path": "", "created": "2026-06-09", "source": "x.vtt", "id": "hyp-1", "source_type": "[transcript]"},
            {"initiative_id": None, "hypothesis": "B", "status": "open", "owner": "", "validation_path": "", "created": "2026-06-09", "source": "x.vtt", "id": "hyp-2", "source_type": "[transcript]"},
            {"initiative_id": "init-001", "hypothesis": "C", "status": "parked", "owner": "", "validation_path": "", "created": "2026-06-09", "source": "x.vtt", "id": "hyp-3", "source_type": "[transcript]"},
        ]
        (vault / "hypotheses.json").write_text(json.dumps(hyps))

        with patch("pmao.llm.call_text", return_value="STATUS OUTPUT"), \
             patch("pmao.ingest._load_skill", return_value="{initiatives}"):
            from pmao.ingest import run_status
            run_status(vault)

        captured = capsys.readouterr()
        assert "Hypotheses: 2 open" in captured.out
        assert "1 initiative-level" in captured.out
        assert "1 project-level" in captured.out
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd "$PMAO" && python -m pytest tests/test_ingest.py::test_run_status_prints_hypothesis_count -v
```

Expected: FAIL — `run_status` doesn't print a count line yet.

- [ ] **Step 3: Implement `run_status` count line and `run_summarize` data inclusion**

Update `run_status` in `pmao/ingest.py`:

```python
def run_status(vault_path: Path, config_override: str = None) -> None:
    from pmao.llm import call_text

    initiatives = load_initiatives(vault_path)
    skill = _load_skill("status")
    init_list = "\n".join(
        f"  {i.id}: {i.name} | {i.status} | priority={i.priority or 'none'} | "
        f"current_state={i.current_state or 'none'} | "
        f"coordination_next_steps={i.coordination_next_steps or 'none'} | "
        f"outstanding_questions={i.outstanding_questions or 'none'} | "
        f"outstanding_meetings={i.outstanding_meetings or 'none'} | "
        f"last_touch={i.last_touch_timestamp or 'none'}"
        for i in initiatives
    )
    prompt = skill.replace("{initiatives}", init_list)
    print(call_text(prompt, config_override=config_override))

    hyp_path = vault_path / "hypotheses.json"
    hypotheses = json.loads(hyp_path.read_text()) if hyp_path.exists() else []
    open_hyp = [h for h in hypotheses if h.get("status") in ("open", "exploring")]
    initiative_level = [h for h in open_hyp if h.get("initiative_id")]
    project_level = [h for h in open_hyp if not h.get("initiative_id")]
    print(f"\nHypotheses: {len(open_hyp)} open ({len(initiative_level)} initiative-level, {len(project_level)} project-level)")
```

Update `run_summarize` in `pmao/ingest.py` to include decisions and hypotheses:

```python
def run_summarize(vault_path: Path, config_override: str = None) -> None:
    import json as _json
    from pmao.llm import call_text

    initiatives = load_initiatives(vault_path)
    actions_path = vault_path / "actions.json"
    questions_path = vault_path / "questions.json"
    decisions_path = vault_path / "decisions.json"
    hyp_path = vault_path / "hypotheses.json"

    actions = _json.loads(actions_path.read_text()) if actions_path.exists() else []
    questions = _json.loads(questions_path.read_text()) if questions_path.exists() else []
    decisions = _json.loads(decisions_path.read_text()) if decisions_path.exists() else []
    hypotheses = _json.loads(hyp_path.read_text()) if hyp_path.exists() else []

    skill = _load_skill("summarize")
    state = _json.dumps(
        {
            "initiatives": [i.to_dict() for i in initiatives],
            "actions": actions,
            "questions": questions,
            "decisions": decisions,
            "hypotheses": hypotheses,
        },
        indent=2,
        default=str,
    )
    prompt = skill.replace("{project_state}", state)
    print(call_text(prompt, config_override=config_override))
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
cd "$PMAO" && python -m pytest tests/ -v
```

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
cd "$PMAO"
git add pmao/ingest.py tests/test_ingest.py
git commit -m "feat: surface decisions + hypotheses in run_summarize; add hypothesis count to run_status"
```

---

## Final verification

- [ ] **Run the full test suite**

```bash
cd "$PMAO" && python -m pytest tests/ -v
```

Expected: All tests pass. If any fail, fix before proceeding.

- [ ] **Verify success criteria**

Manually check each criterion from the spec:

1. `pmao update` — calls `call_structured`, shows preview, prompts [y/N], writes to `initiatives.json` and regenerates `workbook.xlsx`. **Covered by `test_run_update_writes_to_vault`.**

2. Idempotent ingest — running `pmao ingest` twice on same source produces same field values (not doubled). **Covered by `test_apply_updates_overwrites_existing_next_steps` and `test_apply_updates_leaves_field_when_new_is_empty`.**

3. `decisions.json` is populated after an ingest with a decision. **Covered by `test_apply_updates_writes_decisions`.**

4. `hypotheses.json` is populated after an ingest with a hypothesis. **Covered by `test_apply_updates_writes_hypotheses` and `test_apply_updates_hypothesis_with_null_initiative_id`.**

5. Workbook has 6 tabs; Hypotheses tab shows project-level rows first. **Covered by `test_workbook_has_six_tabs`, `test_hypotheses_tab_has_headers`, `test_hypotheses_tab_project_level_rows_first`.**

6. `pmao summarize` output includes Emerging Hypotheses and Decisions sections. **Covered by `skills/summarize.md` updated instructions; data is passed via `run_summarize` update.**
