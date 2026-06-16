import json
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from pmao.models import Initiative
from pmao.vault import init_vault, save_initiatives


def _make_initiative(id_="init-001", name="Alpha", status="in_progress",
                     days_ago=5, owner="Alex", current_state="Underway",
                     next_steps="- Review by Friday"):
    return Initiative(
        id=id_, name=name, status=status,
        last_touched=date.today() - timedelta(days=days_ago),
        owner=owner,
        current_state=current_state,
        next_steps=next_steps,
    )


def _make_action(id_="act-001", description="Confirm budget", owner="Sam",
                 due=None, status="open", initiative_id="init-001"):
    return {
        "id": id_,
        "initiative_id": initiative_id,
        "description": description,
        "owner": owner,
        "due": due or "",
        "status": status,
        "created": "2026-06-01",
        "source": "notes.md",
    }


# ── _compute_lint_flags unit tests ──────────────────────────────────────────

def test_stale_initiative_appears():
    from pmao.ingest import _compute_lint_flags
    init = _make_initiative(days_ago=45)
    flags = _compute_lint_flags([init], [], stale_days=30)
    assert len(flags["stale"]) == 1
    assert flags["stale"][0]["id"] == "init-001"
    assert flags["stale"][0]["days_since_touch"] == 45


def test_not_stale_initiative_absent():
    from pmao.ingest import _compute_lint_flags
    init = _make_initiative(days_ago=10)
    flags = _compute_lint_flags([init], [], stale_days=30)
    assert flags["stale"] == []


def test_incomplete_missing_owner():
    from pmao.ingest import _compute_lint_flags
    init = _make_initiative(owner=None)
    flags = _compute_lint_flags([init], [], stale_days=30)
    assert len(flags["incomplete"]) == 1
    assert "owner" in flags["incomplete"][0]["missing_fields"]


def test_incomplete_missing_current_state_and_next_steps():
    from pmao.ingest import _compute_lint_flags
    init = _make_initiative(current_state=None, next_steps=None)
    flags = _compute_lint_flags([init], [], stale_days=30)
    missing = flags["incomplete"][0]["missing_fields"]
    assert "current_state" in missing
    assert "next_steps" in missing


def test_complete_initiative_not_in_incomplete():
    from pmao.ingest import _compute_lint_flags
    init = _make_initiative()  # owner, current_state, next_steps all set
    flags = _compute_lint_flags([init], [], stale_days=30)
    assert flags["incomplete"] == []


def test_overdue_open_action_appears():
    from pmao.ingest import _compute_lint_flags
    past_due = (date.today() - timedelta(days=14)).isoformat()
    action = _make_action(due=past_due, status="open")
    flags = _compute_lint_flags([], [action], stale_days=30)
    assert len(flags["overdue_actions"]) == 1
    assert flags["overdue_actions"][0]["id"] == "act-001"
    assert flags["overdue_actions"][0]["days_overdue"] == 14


def test_future_due_action_absent():
    from pmao.ingest import _compute_lint_flags
    future_due = (date.today() + timedelta(days=7)).isoformat()
    action = _make_action(due=future_due, status="open")
    flags = _compute_lint_flags([], [action], stale_days=30)
    assert flags["overdue_actions"] == []


def test_action_with_no_due_date_absent():
    from pmao.ingest import _compute_lint_flags
    action = _make_action(due="", status="open")
    flags = _compute_lint_flags([], [action], stale_days=30)
    assert flags["overdue_actions"] == []


def test_done_action_not_overdue():
    from pmao.ingest import _compute_lint_flags
    past_due = (date.today() - timedelta(days=5)).isoformat()
    action = _make_action(due=past_due, status="done")
    flags = _compute_lint_flags([], [action], stale_days=30)
    assert flags["overdue_actions"] == []


# ── run_lint integration tests ───────────────────────────────────────────────

def test_run_lint_empty_vault_prints_message(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        # no initiatives

        from pmao.ingest import run_lint
        run_lint(vault)

        out = capsys.readouterr().out
        assert "Nothing to lint" in out


def test_run_lint_prompt_contains_pre_flags(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        stale_init = _make_initiative(days_ago=45)
        save_initiatives(vault, [stale_init])

        captured_prompt = []

        def fake_call_text(prompt, **kwargs):
            captured_prompt.append(prompt)
            return "LINT OUTPUT"

        with patch("pmao.llm.call_text", side_effect=fake_call_text), \
             patch("pmao.ingest._load_skill", return_value=(
                 "{pre_flags}\n{initiatives}\n{actions}\n"
                 "{decisions}\n{hypotheses}\n{facts}"
             )):
            from pmao.ingest import run_lint
            run_lint(vault, stale_days=30)

        prompt = captured_prompt[0]
        assert "STALE INITIATIVES" in prompt
        assert "Alpha" in prompt


def test_run_lint_prints_llm_output(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative(days_ago=5)])

        with patch("pmao.llm.call_text", return_value="MOCK LINT REPORT"), \
             patch("pmao.ingest._load_skill", return_value=(
                 "{pre_flags}\n{initiatives}\n{actions}\n"
                 "{decisions}\n{hypotheses}\n{facts}"
             )):
            from pmao.ingest import run_lint
            run_lint(vault)

        out = capsys.readouterr().out
        assert "MOCK LINT REPORT" in out
