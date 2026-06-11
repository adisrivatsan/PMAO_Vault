import json
from datetime import date
from importlib import resources
from pathlib import Path
from typing import List

from pmao.models import Initiative
from pmao.vault import load_initiatives, save_initiatives, refresh_workbook, load_list

CLEAR_SENTINEL = "[clear]"


def _load_skill(skill_name: str) -> str:
    skill_file = resources.files("pmao") / "skills" / f"{skill_name}.md"
    if not skill_file.is_file():
        raise FileNotFoundError(f"Skill file not found: {skill_file}")
    return skill_file.read_text(encoding="utf-8")


def _build_ingest_prompt(
    skill: str,
    initiatives: List[Initiative],
    source_text: str,
    roster_text: str = "",
) -> str:
    init_list = "\n".join(
        f"  {i.id}: {i.name} (status: {i.status})"
        for i in initiatives
    )
    return (
        skill
        .replace("{initiatives}", init_list)
        .replace("{source}", source_text)
        .replace("{roster}", roster_text)
    )


def _print_diff(extraction: dict, initiatives: List[Initiative], actions: list) -> None:
    idx = {i.id: i for i in initiatives}
    actions_idx = {a["id"]: a for a in actions}

    updates = extraction.get("initiative_updates", [])
    new_actions = extraction.get("new_actions", [])
    completed = extraction.get("completed_actions", [])
    meetings = extraction.get("meetings", [])
    decisions = extraction.get("decisions", [])
    hypotheses = extraction.get("hypotheses", [])
    facts = extraction.get("facts", [])
    unmatched = extraction.get("unmatched_references", [])

    print("\n--- Proposed changes ---\n")

    for u in updates:
        iid = u.get("initiative_id", "?")
        init = idx.get(iid)
        if not init:
            continue
        print(f"[{iid}] {init.name}")
        for field, old_val in [
            ("status", init.status),
            ("current_state", init.current_state),
            ("next_steps", init.next_steps),
            ("last_touch_comment", init.last_touch_comment),
        ]:
            new_val = u.get(field, "")
            if new_val == CLEAR_SENTINEL:
                print(f"  {field}: \"{old_val}\" → [cleared]")
            elif new_val and new_val != old_val:
                print(f"  {field}: \"{old_val}\" → \"{new_val}\"")

    if new_actions:
        print(f"\nNew actions ({len(new_actions)}):")
        for a in new_actions:
            due = a.get("due") or "-"
            print(f"  {a.get('description', '?')} ({a.get('owner', '?')}, due {due})")

    if completed:
        print(f"\nCompleted actions ({len(completed)}):")
        for aid in completed:
            a = actions_idx.get(aid)
            desc = a["description"] if a else "(not found)"
            print(f"  {aid}: \"{desc}\" → done")

    if meetings:
        print(f"\nNew meetings ({len(meetings)})")
    if decisions:
        print(f"\nNew decisions ({len(decisions)})")
    if hypotheses:
        print(f"\nNew hypotheses ({len(hypotheses)})")
    if facts:
        print(f"\nNew facts ({len(facts)})")

    if unmatched:
        print(f"\nUNMATCHED REFERENCES ({len(unmatched)}):")
        for ref in unmatched:
            print(f"  \"{ref.get('mention', '?')}\" — {ref.get('context', '')}")

    print()


def apply_updates(vault_path: Path, extraction: dict, transcript_name: str) -> None:
    initiatives = load_initiatives(vault_path)
    idx = {i.id: i for i in initiatives}
    today = date.today()
    today_str = today.isoformat()

    for update in extraction.get("initiative_updates", []):
        iid = update.get("initiative_id")
        if iid not in idx:
            continue
        init = idx[iid]
        for field in ("current_state", "next_steps", "last_touch_comment"):
            val = update.get(field, "")
            if val == CLEAR_SENTINEL:
                setattr(init, field, None)
            elif val:
                setattr(init, field, val)
        status = update.get("status", "")
        if status in ("not_started", "in_progress", "ready", "complete"):
            init.status = status
        init.last_touched = today

    actions = load_list(vault_path, "actions.json")
    actions_idx = {a["id"]: a for a in actions}
    for item in extraction.get("new_actions", []):
        if not item.get("description"):
            continue
        actions.append({
            "id": f"act-{today_str}-{len(actions):04d}",
            "initiative_id": item.get("initiative_id", ""),
            "description": item["description"],
            "owner": item.get("owner", ""),
            "due": item.get("due", ""),
            "status": "open",
            "created": today_str,
            "source": transcript_name,
        })
    for aid in extraction.get("completed_actions", []):
        if aid in actions_idx:
            actions_idx[aid]["status"] = "done"
    (vault_path / "actions.json").write_text(json.dumps(actions, indent=2))

    meetings = load_list(vault_path, "meetings.json")
    for m in extraction.get("meetings", []):
        if not m.get("purpose"):
            continue
        meetings.append({
            "id": f"mtg-{today_str}-{len(meetings):04d}",
            "initiative_id": m.get("initiative_id", ""),
            "purpose": m["purpose"],
            "attendees": m.get("attendees") or [],
            "status": "open",
            "created": today_str,
            "source": transcript_name,
        })
    (vault_path / "meetings.json").write_text(json.dumps(meetings, indent=2))

    decisions = load_list(vault_path, "decisions.json")
    for dec in extraction.get("decisions", []):
        if not dec.get("decision"):
            continue
        decisions.append({
            "id": f"dec-{today_str}-{len(decisions):04d}",
            "initiative_id": dec.get("initiative_id", ""),
            "decision": dec["decision"],
            "rationale": dec.get("rationale", ""),
            "owner": dec.get("owner", ""),
            "status": "recorded",
            "created": today_str,
            "source": transcript_name,
        })
    (vault_path / "decisions.json").write_text(json.dumps(decisions, indent=2))

    all_hyp = load_list(vault_path, "hypotheses.json")
    for hyp in extraction.get("hypotheses", []):
        if not hyp.get("hypothesis"):
            continue
        all_hyp.append({
            "id": f"hyp-{today_str}-{len(all_hyp):04d}",
            "initiative_id": hyp.get("initiative_id"),
            "hypothesis": hyp["hypothesis"],
            "owner": hyp.get("owner", ""),
            "validation_path": hyp.get("validation_path", ""),
            "status": "open",
            "created": today_str,
            "source": transcript_name,
        })
    (vault_path / "hypotheses.json").write_text(json.dumps(all_hyp, indent=2))

    all_facts = load_list(vault_path, "facts.json")
    for fact in extraction.get("facts", []):
        if not fact.get("claim"):
            continue
        all_facts.append({
            "id": f"fact-{today_str}-{len(all_facts):04d}",
            "initiative_id": fact.get("initiative_id", ""),
            "claim": fact["claim"],
            "stated_by": fact.get("stated_by", ""),
            "status": "recorded",
            "created": today_str,
            "source": transcript_name,
        })
    (vault_path / "facts.json").write_text(json.dumps(all_facts, indent=2))

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
    from pmao.roster import load_roster, render_roster

    print(f"Preprocessing {source_path.name}...")
    text = preprocess_transcript(source_path)

    initiatives = load_initiatives(vault_path)
    roster_people = load_roster(vault_path)
    roster_text = render_roster(roster_people) if roster_people else ""

    skill = _load_skill("ingest")
    prompt = _build_ingest_prompt(skill, initiatives, text, roster_text)

    print("Calling LLM for extraction (this may take ~30s)...")
    extraction = call_structured(prompt, config_override=config_override, vault_path=vault_path)

    for key in ("initiative_updates", "new_actions", "completed_actions",
                "meetings", "decisions", "hypotheses", "facts", "unmatched_references"):
        extraction.setdefault(key, [])

    actions = load_list(vault_path, "actions.json")
    _print_diff(extraction, initiatives, actions)

    has_changes = any(
        extraction.get(k) for k in
        ("initiative_updates", "new_actions", "completed_actions",
         "meetings", "decisions", "hypotheses", "facts")
    )
    if not has_changes:
        print("Nothing extracted — no changes made.")
        return

    if not yes:
        answer = input("Apply these updates? [y/N] ").strip().lower()
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
        f"owner={i.owner or 'none'} | "
        f"current_state={i.current_state or 'none'} | "
        f"next_steps={i.next_steps or 'none'} | "
        f"last_touched={i.last_touched.isoformat()}"
        for i in initiatives
    )
    prompt = skill.replace("{initiatives}", init_list)
    print(call_text(prompt, config_override=config_override, vault_path=vault_path))

    all_hyp = load_list(vault_path, "hypotheses.json")
    open_hyp = [h for h in all_hyp if h.get("status") in ("open", "exploring")]
    initiative_level = [h for h in open_hyp if h.get("initiative_id")]
    project_level = [h for h in open_hyp if not h.get("initiative_id")]
    print(f"\nHypotheses: {len(open_hyp)} open "
          f"({len(initiative_level)} initiative-level, {len(project_level)} project-level)")


def run_summarize(vault_path: Path, config_override: str = None) -> None:
    from pmao.llm import call_text

    initiatives = load_initiatives(vault_path)
    skill = _load_skill("summarize")
    state = json.dumps(
        {
            "initiatives": [i.to_dict() for i in initiatives],
            "actions": load_list(vault_path, "actions.json"),
            "decisions": load_list(vault_path, "decisions.json"),
            "hypotheses": load_list(vault_path, "hypotheses.json"),
            "meetings": load_list(vault_path, "meetings.json"),
            "facts": load_list(vault_path, "facts.json"),
        },
        indent=2,
        default=str,
    )
    prompt = skill.replace("{project_state}", state)
    print(call_text(prompt, config_override=config_override, vault_path=vault_path))
