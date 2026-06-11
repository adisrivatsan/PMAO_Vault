import json
from datetime import date
from importlib import resources
from pathlib import Path
from typing import List

from pmao.models import Initiative
from pmao.vault import load_initiatives, save_initiatives, refresh_workbook

# Literal value an extraction may use to clear an initiative field (see skills/update.md).
# Plain empty string "" still means "no new information — leave the field untouched".
CLEAR_SENTINEL = "[clear]"


def _load_skill(skill_name: str) -> str:
    skill_file = resources.files("pmao") / "skills" / f"{skill_name}.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"Skill file not found: {skill_file}")
    return skill_file.read_text(encoding="utf-8")


def _build_ingest_prompt(skill: str, initiatives: List[Initiative], source_text: str) -> str:
    init_list = "\n".join(
        f"  {i.id}: {i.name} (status: {i.status})"
        for i in initiatives
    )
    return skill.replace("{initiatives}", init_list).replace("{source}", source_text)



def apply_updates(vault_path: Path, extraction: dict, transcript_name: str) -> None:
    initiatives = load_initiatives(vault_path)
    idx = {i.id: i for i in initiatives}
    today = date.today()

    for update in extraction.get("initiatives_updated", []):
        iid = update.get("initiative_id")
        if iid not in idx:
            continue
        init = idx[iid]
        for field in (
            "current_state",
            "coordination_next_steps",
            "outstanding_questions",
            "outstanding_meetings",
            "last_touch_comment",
            "materials_link",
        ):
            val = update.get(field, "")
            if val == CLEAR_SENTINEL:
                setattr(init, field, None)
            elif val:
                setattr(init, field, val)
        ts = update.get("last_touch_timestamp", "")
        if ts:
            try:
                init.last_touch_timestamp = date.fromisoformat(ts)
            except ValueError:
                pass
        if init.status == "not_started":
            init.status = "in_progress"
        init.last_touched = today

    actions_path = vault_path / "actions.json"
    actions = json.loads(actions_path.read_text()) if actions_path.exists() else []
    for item in extraction.get("action_items", []):
        if not item.get("description") or not item.get("owner"):
            continue
        actions.append({
            "id": f"act-{today.isoformat()}-{len(actions):04d}",
            "initiative_id": item.get("initiative_id", ""),
            "description": item["description"],
            "owner": item["owner"],
            "due": item.get("due", ""),
            "status": "open",
            "created": today.isoformat(),
            "source": transcript_name,
        })
    actions_path.write_text(json.dumps(actions, indent=2))

    questions_path = vault_path / "questions.json"
    questions = json.loads(questions_path.read_text()) if questions_path.exists() else []
    for q in extraction.get("open_questions", []):
        if not q.get("question"):
            continue
        questions.append({
            "id": f"q-{today.isoformat()}-{len(questions):04d}",
            "initiative_id": q.get("initiative_id", ""),
            "question": q["question"],
            "status": "open",
            "created": today.isoformat(),
            "source": transcript_name,
        })
    questions_path.write_text(json.dumps(questions, indent=2))

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

    save_initiatives(vault_path, initiatives)
    refresh_workbook(vault_path)


def run_ingest(
    vault_path: Path,
    source_path: Path,
    yes: bool = False,
    config_override: str = None,
) -> None:
    from pmao.transcript import preprocess_transcript
    from pmao.llm import call_structured

    print(f"Preprocessing {source_path.name}...")
    text = preprocess_transcript(source_path)

    initiatives = load_initiatives(vault_path)
    skill = _load_skill("ingest")
    prompt = _build_ingest_prompt(skill, initiatives, text)

    print("Calling LLM for extraction (this may take ~30s)...")
    extraction = call_structured(prompt, config_override=config_override, vault_path=vault_path)
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

    apply_updates(vault_path, extraction, transcript_name=source_path.name)
    print(f"\nDone. workbook.xlsx updated.")


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
    print(call_text(prompt, config_override=config_override, vault_path=vault_path))

    hyp_path = vault_path / "hypotheses.json"
    hypotheses = json.loads(hyp_path.read_text()) if hyp_path.exists() else []
    open_hyp = [h for h in hypotheses if h.get("status") in ("open", "exploring")]
    initiative_level = [h for h in open_hyp if h.get("initiative_id")]
    project_level = [h for h in open_hyp if not h.get("initiative_id")]
    print(f"\nHypotheses: {len(open_hyp)} open ({len(initiative_level)} initiative-level, {len(project_level)} project-level)")


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
    extraction = call_structured(prompt, config_override=config_override, vault_path=vault_path)
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
    print(call_text(prompt, config_override=config_override, vault_path=vault_path))
