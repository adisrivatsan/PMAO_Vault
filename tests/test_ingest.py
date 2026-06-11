import json
import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import patch

from pmao.models import Initiative
from pmao.ingest import apply_updates, _build_ingest_prompt
from pmao.vault import init_vault, save_initiatives, load_initiatives


def _make_initiative(id_="init-001", name="Customer Data Platform", status="not_started"):
    return Initiative(
        id=id_, name=name, status=status,
        created=date(2026, 6, 8), last_touched=date(2026, 6, 8)
    )



def test_apply_updates_maps_generic_fields():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = {
            "initiatives_updated": [{
                "initiative_id": "init-001",
                "current_state": "Analysis complete",
                "coordination_next_steps": "- Alex to schedule review",
                "outstanding_questions": "",
                "outstanding_meetings": "",
                "last_touch_comment": "[email] Alex confirmed done",
                "last_touch_timestamp": "2026-06-08",
                "materials_link": "",
            }],
            "action_items": [{
                "initiative_id": "init-001",
                "description": "Schedule stakeholder review",
                "owner": "Alex Jordan",
                "due": "2026-06-15",
            }],
            "open_questions": [],
        }

        apply_updates(vault, extraction, "meeting-notes.md")

        initiatives = load_initiatives(vault)
        init = initiatives[0]
        assert init.current_state == "Analysis complete"
        assert init.coordination_next_steps == "- Alex to schedule review"
        assert init.status == "in_progress"
        assert init.last_touch_comment == "[email] Alex confirmed done"
        assert init.last_touch_timestamp == date(2026, 6, 8)

        actions = json.loads((vault / "actions.json").read_text())
        assert len(actions) == 1
        assert actions[0]["owner"] == "Alex Jordan"
        assert actions[0]["description"] == "Schedule stakeholder review"


def test_apply_updates_skips_unknown_initiative():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = {
            "initiatives_updated": [{"initiative_id": "init-999", "current_state": "ignored"}],
            "action_items": [],
            "open_questions": [],
        }
        apply_updates(vault, extraction, "source.md")

        initiatives = load_initiatives(vault)
        assert initiatives[0].current_state is None


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


def test_apply_updates_clears_field_with_clear_sentinel():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(status="in_progress")
        init.coordination_next_steps = "- Step to be cleared"
        init.current_state = "Kept state"
        save_initiatives(vault, [init])

        extraction = {
            "initiatives_updated": [{
                "initiative_id": "init-001",
                "coordination_next_steps": "[clear]",
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
        apply_updates(vault, extraction, "manual-update-2026-06-11")

        initiatives = load_initiatives(vault)
        assert initiatives[0].coordination_next_steps is None
        assert initiatives[0].current_state == "Kept state"


def test_apply_updates_clear_sentinel_clears_materials_link():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(status="in_progress")
        init.materials_link = "https://example.com/old-deck"
        save_initiatives(vault, [init])

        extraction = {
            "initiatives_updated": [{
                "initiative_id": "init-001",
                "materials_link": "[clear]",
            }],
            "action_items": [],
            "open_questions": [],
        }
        apply_updates(vault, extraction, "manual-update-2026-06-11")

        initiatives = load_initiatives(vault)
        assert initiatives[0].materials_link is None


def test_build_ingest_prompt_substitutes_placeholders():
    skill = "## Initiatives\n{initiatives}\n## Source\n{source}"
    initiatives = [_make_initiative()]
    prompt = _build_ingest_prompt(skill, initiatives, "source content here")
    assert "init-001" in prompt
    assert "Customer Data Platform" in prompt
    assert "source content here" in prompt


def test_apply_updates_adds_open_questions():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])

        extraction = {
            "initiatives_updated": [],
            "action_items": [],
            "open_questions": [{"initiative_id": "init-001", "question": "What is the budget?"}],
        }
        apply_updates(vault, extraction, "source.md")

        questions = json.loads((vault / "questions.json").read_text())
        assert len(questions) == 1
        assert questions[0]["question"] == "What is the budget?"


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


def test_run_status_uses_vault_config_backend_and_timeout():
    import yaml

    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        config = yaml.safe_load((vault / "project-config.yaml").read_text())
        config["llm_backend"] = "codex"
        config["llm_timeout_seconds"] = 11
        (vault / "project-config.yaml").write_text(yaml.dump(config))

        with patch("pmao.llm._run", return_value="STATUS OUTPUT") as run, \
             patch("pmao.ingest._load_skill", return_value="{initiatives}"):
            from pmao.ingest import run_status
            run_status(vault)

        assert run.call_args[0][0] == "codex"
        assert run.call_args[0][2] == 11
