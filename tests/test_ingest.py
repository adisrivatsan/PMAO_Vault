import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pmao.models import Initiative
from pmao.ingest import apply_updates, _build_ingest_prompt, CLEAR_SENTINEL
from pmao.vault import init_vault, save_initiatives, load_initiatives, load_list


def _make_initiative(id_="init-001", name="Customer Data Platform", status="not_started"):
    return Initiative(
        id=id_, name=name, status=status,
        last_touched=date(2026, 6, 8),
    )


def _empty_extraction():
    return {
        "initiative_updates": [],
        "new_actions": [],
        "completed_actions": [],
        "meetings": [],
        "decisions": [],
        "hypotheses": [],
        "facts": [],
        "unmatched_references": [],
    }


def test_apply_updates_initiative_fields():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), initiative_updates=[{
            "initiative_id": "init-001",
            "current_state": "Analysis complete",
            "next_steps": "- Alex to schedule review",
            "last_touch_comment": "[email] Alex confirmed",
            "status": "",
        }])
        apply_updates(vault, extraction, "meeting.md")

        initiatives = load_initiatives(vault)
        assert initiatives[0].current_state == "Analysis complete"
        assert initiatives[0].next_steps == "- Alex to schedule review"
        assert initiatives[0].last_touch_comment == "[email] Alex confirmed"
        assert initiatives[0].last_touched == date.today()


def test_apply_updates_status_change():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), initiative_updates=[{
            "initiative_id": "init-001",
            "status": "in_progress",
            "current_state": "", "next_steps": "", "last_touch_comment": "",
        }])
        apply_updates(vault, extraction, "notes.md")

        initiatives = load_initiatives(vault)
        assert initiatives[0].status == "in_progress"


def test_apply_updates_skips_unknown_initiative():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), initiative_updates=[{
            "initiative_id": "init-999",
            "current_state": "ignored",
            "status": "", "next_steps": "", "last_touch_comment": "",
        }])
        apply_updates(vault, extraction, "source.md")

        assert load_initiatives(vault)[0].current_state is None


def test_apply_updates_leaves_field_when_new_is_empty():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(status="in_progress")
        init.next_steps = "- Preserved step"
        save_initiatives(vault, [init])

        extraction = dict(_empty_extraction(), initiative_updates=[{
            "initiative_id": "init-001",
            "next_steps": "",
            "current_state": "New state",
            "status": "", "last_touch_comment": "",
        }])
        apply_updates(vault, extraction, "source.md")

        initiatives = load_initiatives(vault)
        assert initiatives[0].next_steps == "- Preserved step"
        assert initiatives[0].current_state == "New state"


def test_apply_updates_clears_field_with_sentinel():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(status="in_progress")
        init.next_steps = "- Step to clear"
        init.current_state = "Kept state"
        save_initiatives(vault, [init])

        extraction = dict(_empty_extraction(), initiative_updates=[{
            "initiative_id": "init-001",
            "next_steps": "[clear]",
            "current_state": "",
            "status": "", "last_touch_comment": "",
        }])
        apply_updates(vault, extraction, "manual-2026-06-11")

        initiatives = load_initiatives(vault)
        assert initiatives[0].next_steps is None
        assert initiatives[0].current_state == "Kept state"


def test_apply_updates_new_actions():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), new_actions=[{
            "initiative_id": "init-001",
            "description": "Schedule stakeholder review",
            "owner": "Alex Jordan",
            "due": "2026-06-15",
        }])
        apply_updates(vault, extraction, "meeting.md")

        actions = load_list(vault, "actions.json")
        assert len(actions) == 1
        assert actions[0]["owner"] == "Alex Jordan"
        assert actions[0]["status"] == "open"
        assert actions[0]["id"].startswith("act-")


def test_apply_updates_completed_actions():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        (vault / "actions.json").write_text(json.dumps([{
            "id": "act-2026-06-08-0000",
            "initiative_id": "init-001",
            "description": "Old task",
            "owner": "Sam",
            "due": "",
            "status": "open",
            "created": "2026-06-08",
            "source": "old.md",
        }]))

        extraction = dict(_empty_extraction(), completed_actions=["act-2026-06-08-0000"])
        apply_updates(vault, extraction, "meeting.md")

        actions = load_list(vault, "actions.json")
        assert actions[0]["status"] == "done"


def test_apply_updates_meetings():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), meetings=[{
            "initiative_id": "init-001",
            "purpose": "Kickoff with data team",
            "attendees": ["Alex", "Sam"],
        }])
        apply_updates(vault, extraction, "notes.md")

        meetings = load_list(vault, "meetings.json")
        assert len(meetings) == 1
        assert meetings[0]["purpose"] == "Kickoff with data team"
        assert meetings[0]["id"].startswith("mtg-")


def test_apply_updates_decisions():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), decisions=[{
            "initiative_id": "init-001",
            "decision": "Budget approved at $500K",
            "rationale": "Board approved in Q2",
            "owner": "Jane Smith",
        }])
        apply_updates(vault, extraction, "meeting.vtt")

        decisions = load_list(vault, "decisions.json")
        assert len(decisions) == 1
        assert decisions[0]["decision"] == "Budget approved at $500K"
        assert decisions[0]["status"] == "recorded"
        assert decisions[0]["id"].startswith("dec-")


def test_apply_updates_hypotheses():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), hypotheses=[{
            "initiative_id": "init-001",
            "hypothesis": "Unbundling fee increases conversion by 15%",
            "owner": "Alex Chen",
            "validation_path": "Run A/B test",
        }])
        apply_updates(vault, extraction, "call.vtt")

        hypotheses = load_list(vault, "hypotheses.json")
        assert len(hypotheses) == 1
        assert hypotheses[0]["status"] == "open"
        assert hypotheses[0]["id"].startswith("hyp-")


def test_apply_updates_hypothesis_null_initiative_id():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), hypotheses=[{
            "initiative_id": None,
            "hypothesis": "Market timing > product quality",
            "owner": "", "validation_path": "",
        }])
        apply_updates(vault, extraction, "all-hands.vtt")

        hypotheses = load_list(vault, "hypotheses.json")
        assert hypotheses[0]["initiative_id"] is None


def test_apply_updates_facts():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), facts=[{
            "initiative_id": "init-001",
            "claim": "Q2 cost-to-serve up 9%",
            "stated_by": "Sarah Klein",
        }])
        apply_updates(vault, extraction, "sync.vtt")

        facts = load_list(vault, "facts.json")
        assert len(facts) == 1
        assert facts[0]["claim"] == "Q2 cost-to-serve up 9%"
        assert facts[0]["id"].startswith("fact-")


def test_print_diff_shows_unmatched_references(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = dict(_empty_extraction(), unmatched_references=[
            {"mention": "Project Phoenix", "context": "mentioned in Q3 discussion"}
        ])
        from pmao.ingest import _print_diff
        _print_diff(extraction, load_initiatives(vault), [])

        out = capsys.readouterr().out
        assert "UNMATCHED REFERENCES" in out
        assert "Project Phoenix" in out


def test_build_ingest_prompt_substitutes_placeholders():
    skill = "## Initiatives\n{initiatives}\n## Roster\n{roster}\n## Source\n{source}"
    initiatives = [_make_initiative()]
    prompt = _build_ingest_prompt(skill, initiatives, "source content here", "- Jane Smith")
    assert "init-001" in prompt
    assert "Customer Data Platform" in prompt
    assert "source content here" in prompt
    assert "Jane Smith" in prompt


def test_run_ingest_applies_on_yes(tmp_path):
    vault = tmp_path / "vault"
    init_vault(vault)
    save_initiatives(vault, [_make_initiative()])
    source = tmp_path / "notes.md"
    source.write_text("Alpha is in progress")

    extraction = dict(_empty_extraction(), initiative_updates=[{
        "initiative_id": "init-001",
        "current_state": "In progress now",
        "next_steps": "", "last_touch_comment": "", "status": "",
    }])

    with patch("pmao.llm.call_structured", return_value=extraction), \
         patch("pmao.ingest._load_skill", return_value="{initiatives}\n{roster}\n{source}"), \
         patch("builtins.input", return_value="y"):
        from pmao.ingest import run_ingest
        run_ingest(vault, source, yes=False)

    assert load_initiatives(vault)[0].current_state == "In progress now"


def test_run_ingest_aborts_on_no(tmp_path):
    vault = tmp_path / "vault"
    init_vault(vault)
    save_initiatives(vault, [_make_initiative()])
    source = tmp_path / "notes.md"
    source.write_text("Some content")

    extraction = dict(_empty_extraction(), initiative_updates=[{
        "initiative_id": "init-001",
        "current_state": "Should not apply",
        "next_steps": "", "last_touch_comment": "", "status": "",
    }])

    with patch("pmao.llm.call_structured", return_value=extraction), \
         patch("pmao.ingest._load_skill", return_value="{initiatives}\n{roster}\n{source}"), \
         patch("builtins.input", return_value="n"):
        from pmao.ingest import run_ingest
        run_ingest(vault, source, yes=False)

    assert load_initiatives(vault)[0].current_state is None


def test_run_status_uses_slim_fields(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        with patch("pmao.llm.call_text", return_value="STATUS OUTPUT"), \
             patch("pmao.ingest._load_skill", return_value="{initiatives}"):
            from pmao.ingest import run_status
            run_status(vault)

        out = capsys.readouterr().out
        assert "STATUS OUTPUT" in out


def test_run_status_shows_hypothesis_count(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        hyps = [
            {"initiative_id": "init-001", "hypothesis": "A", "status": "open",
             "owner": "", "validation_path": "", "created": "2026-06-09",
             "source": "x.vtt", "id": "hyp-1"},
            {"initiative_id": None, "hypothesis": "B", "status": "open",
             "owner": "", "validation_path": "", "created": "2026-06-09",
             "source": "x.vtt", "id": "hyp-2"},
            {"initiative_id": "init-001", "hypothesis": "C", "status": "parked",
             "owner": "", "validation_path": "", "created": "2026-06-09",
             "source": "x.vtt", "id": "hyp-3"},
        ]
        (vault / "hypotheses.json").write_text(json.dumps(hyps))

        with patch("pmao.llm.call_text", return_value="STATUS OUTPUT"), \
             patch("pmao.ingest._load_skill", return_value="{initiatives}"):
            from pmao.ingest import run_status
            run_status(vault)

        out = capsys.readouterr().out
        assert "Hypotheses: 2 open" in out
        assert "1 initiative-level" in out
        assert "1 project-level" in out
