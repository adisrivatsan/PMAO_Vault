import json
from pathlib import Path

from pmao.vault import load_initiatives, load_list, refresh_workbook
from pmao.roster import load_roster, render_roster
from pmao.deep import _write_staging


def _history_block(vault_path: Path, iid: str, outstanding_meetings: str) -> str:
    lines = []
    for d in load_list(vault_path, "decisions.json"):
        if d.get("initiative_id") == iid:
            lines.append(f"decision: {d.get('decision', '')}")
    for q in load_list(vault_path, "questions.json"):
        if q.get("initiative_id") == iid and q.get("status") == "open":
            lines.append(f"open question: {q.get('question', '')}")
    for m in load_list(vault_path, "meetings.json"):
        if m.get("initiative_id") == iid and m.get("status") in ("open", "scheduled"):
            cadence = f", cadence: {m['cadence']}" if m.get("cadence") else ""
            lines.append(f"open meeting: {m.get('purpose', '')} ({m.get('target_timing') or 'unscheduled'}{cadence})")
    if outstanding_meetings:
        lines.append(f"outstanding meetings (free text): {outstanding_meetings}")
    return "\n".join(lines) if lines else "none"


def _signals_block(vault_path: Path, iid: str) -> str:
    lines = [
        f"{s.get('principal', '?')} on {s.get('lever', '?')}: {s.get('signal', '')} (implication: {s.get('implication', '')})"
        for s in load_list(vault_path, "signals.json")
        if s.get("initiative_id") in (iid, "general")
    ]
    return "\n".join(lines) if lines else "none"


def run_syndicate(vault_path: Path, initiative_id: str, config_override: str = None) -> None:
    from pmao import llm
    from pmao.ingest import _load_skill

    initiatives = load_initiatives(vault_path)
    init = next((i for i in initiatives if i.id == initiative_id), None)
    if init is None:
        valid = ", ".join(i.id for i in initiatives) or "(none)"
        raise ValueError(f"Unknown initiative '{initiative_id}'. Valid ids: {valid}")

    people = load_roster(vault_path)
    if people is None:
        print("Warning: no roster.yaml found — recommendations will use roles instead of resolved people.")

    initiative_text = json.dumps(init.to_dict(), indent=2, default=str)
    skill = _load_skill("syndicate")
    prompt = (
        skill
        .replace("{initiative}", initiative_text)
        .replace("{roster}", render_roster(people))
        .replace("{history}", _history_block(vault_path, initiative_id, init.outstanding_meetings or ""))
        .replace("{signals}", _signals_block(vault_path, initiative_id))
    )

    print(f"Recommending syndication pathway for {init.name} (this may take ~30s)...")
    result = llm.call_structured(prompt, config_override=config_override, vault_path=vault_path)
    if not isinstance(result, dict):
        raise ValueError(
            f"LLM returned JSON of type {type(result).__name__}, "
            f"expected an object — nothing staged."
        )

    from pmao.deep import _validate_extraction
    extraction_check = {"meetings_to_schedule": result.get("meetings_to_schedule"),
                        "review_flags": result.get("review_flags")}
    _validate_extraction(extraction_check, initiatives)
    result["meetings_to_schedule"] = extraction_check["meetings_to_schedule"]
    result["review_flags"] = extraction_check["review_flags"]

    pathway = result.get("pathway")
    if not isinstance(pathway, list):
        if pathway is not None:
            result["review_flags"].append(
                f"malformed pathway: expected a list, got {type(pathway).__name__} — dropped"
            )
        pathway = []
    result["pathway"] = pathway

    print(f"\n--- Syndication pathway: {init.name} ---")
    for step in result["pathway"]:
        if not isinstance(step, dict):
            result["review_flags"].append(
                f"malformed pathway step dropped: {str(step)[:80]}"
            )
            continue
        stakeholders = step.get("stakeholders") or []
        if not isinstance(stakeholders, list):
            stakeholders = [stakeholders]
        who = ", ".join(str(s) for s in stakeholders)
        print(f"{step.get('step', '?')}. {who} — {step.get('purpose', '')}")
        if step.get("why"):
            print(f"   why: {step['why']}")
        if step.get("needs"):
            print(f"   needs: {step['needs']}")
        if step.get("timing"):
            print(f"   timing: {step['timing']}")
    if not result["pathway"]:
        print("(no pathway steps returned)")

    if not result["meetings_to_schedule"] and not result["review_flags"]:
        print("\nNo meetings proposed — nothing staged.")
        return

    staged_path = _write_staging(vault_path, extraction_check, f"syndicate-{initiative_id}")
    refresh_workbook(vault_path)
    n = len(result["meetings_to_schedule"])
    print(f"\nStaged {n} proposed meeting(s): staging/{staged_path.name}. Run 'pmao review' to promote.")
