import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from pmao.models import Initiative
from pmao.vault import init_vault, save_initiatives, load_list

SKILL_PATH = Path(__file__).parent.parent / "pmao" / "skills" / "syndicate.md"
PLACEHOLDERS = ["{initiative}", "{roster}", "{history}", "{signals}"]

SYNDICATE_OUTPUT = {
    "pathway": [{"step": 1, "stakeholders": ["Sarah Klein"], "purpose": "pricing pre-read",
                 "why": "controls pricing lever", "needs": "cost model", "timing": "first"}],
    "meetings_to_schedule": [{
        "initiative_id": "init-001", "purpose": "pricing pre-read with Sarah",
        "convener": "Sarah Klein", "convener_resolution": "matched_roster",
        "attendees": ["Sarah Klein"], "requester": "syndication", "functions": ["finance"],
        "target_timing": "next week", "cadence": "biweekly until pricing review",
        "related_decision": None, "related_question": None, "committee_ownership": False,
        "reconciliation_candidates": [], "source_span": "pathway step 1"}],
    "review_flags": [],
}


def _vault(tmp):
    vault = Path(tmp)
    init_vault(vault)
    save_initiatives(vault, [Initiative(
        id="init-001", name="Pricing", status="in_progress",
        created=date(2026, 6, 1), last_touched=date(2026, 6, 1))])
    return vault


def test_skill_file_has_placeholders():
    text = SKILL_PATH.read_text(encoding="utf-8")
    for ph in PLACEHOLDERS:
        assert ph in text, f"missing {ph}"
    assert "cadence" in text


def test_run_syndicate_stages_proposals(capsys):
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with patch("pmao.llm.call_structured", return_value=dict(SYNDICATE_OUTPUT)) as mock:
            run_syndicate(vault, "init-001")
        prompt = mock.call_args[0][0]
        for ph in PLACEHOLDERS:
            assert ph not in prompt
        staged_files = list((vault / "staging").glob("*.json"))
        assert len(staged_files) == 1
        assert "syndicate-init-001" in staged_files[0].name
        staged = json.loads(staged_files[0].read_text())
        mtgs = staged["extraction"]["meetings_to_schedule"]
        assert mtgs[0]["cadence"] == "biweekly until pricing review"
        assert load_list(vault, "meetings.json") == []     # canonical untouched
        out = capsys.readouterr().out
        assert "pricing pre-read" in out                   # pathway printed
        assert "pmao review" in out


def test_run_syndicate_unknown_initiative_raises():
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with pytest.raises(ValueError, match="init-999"):
            run_syndicate(vault, "init-999")


def test_run_syndicate_empty_output_stages_nothing(capsys):
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with patch("pmao.llm.call_structured",
                   return_value={"pathway": [], "meetings_to_schedule": [], "review_flags": []}):
            run_syndicate(vault, "init-001")
        assert list((vault / "staging").glob("*.json")) == []
        assert "no meetings proposed" in capsys.readouterr().out.lower()


def test_cli_syndicate_dispatches():
    import sys
    from unittest.mock import patch
    from pmao.cli import main
    with patch("pmao.syndicate.run_syndicate") as mock_syn, \
         patch.object(sys, "argv", ["pmao", "syndicate", "v/", "--initiative", "init-001"]):
        main()
    mock_syn.assert_called_once()
    assert mock_syn.call_args.kwargs["initiative_id"] == "init-001"


def test_run_syndicate_flags_unknown_initiative_id():
    """Fix 4: LLM-returned meetings with unknown initiative_ids must be flagged in review_flags."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        bad_output = {
            "pathway": [],
            "meetings_to_schedule": [{
                "initiative_id": "init-999",
                "purpose": "Ghost meeting",
                "convener": None,
                "attendees": [],
                "functions": [],
                "target_timing": "tbd",
                "cadence": "one-time",
                "reconciliation_candidates": [],
            }],
            "review_flags": [],
        }
        with patch("pmao.llm.call_structured", return_value=bad_output):
            run_syndicate(vault, "init-001")
        staged_files = list((vault / "staging").glob("*syndicate*"))
        assert len(staged_files) == 1
        ext = json.loads(staged_files[0].read_text())["extraction"]
        assert ext["review_flags"], "no flag raised for unknown initiative_id init-999"
        assert any("init-999" in f for f in ext["review_flags"])


def test_run_syndicate_prompt_history_includes_open_items_only():
    """Spec 3 Testing bullet 1: {history} must include decisions, open questions, and
    open/scheduled meetings (with cadence) for the initiative, plus outstanding_meetings
    free text — and exclude resolved/closed/other-initiative records."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        save_initiatives(vault, [
            Initiative(id="init-001", name="Pricing", status="in_progress",
                       outstanding_meetings="CFO sync still outstanding",
                       created=date(2026, 6, 1), last_touched=date(2026, 6, 1)),
            Initiative(id="init-002", name="Other", status="in_progress",
                       created=date(2026, 6, 1), last_touched=date(2026, 6, 1)),
        ])
        (vault / "decisions.json").write_text(json.dumps([
            {"id": "dec-1", "initiative_id": "init-001", "decision": "Adopt tiered pricing"},
            {"id": "dec-2", "initiative_id": "init-002", "decision": "Other-initiative decision"},
        ]))
        (vault / "questions.json").write_text(json.dumps([
            {"id": "q-1", "initiative_id": "init-001", "status": "open",
             "question": "What is the discount floor?"},
            {"id": "q-2", "initiative_id": "init-001", "status": "resolved",
             "question": "Already-resolved question"},
        ]))
        (vault / "meetings.json").write_text(json.dumps([
            {"id": "mtg-1", "initiative_id": "init-001", "status": "open",
             "purpose": "Pricing working session", "target_timing": "next week",
             "cadence": "weekly until launch"},
            {"id": "mtg-2", "initiative_id": "init-001", "status": "closed",
             "purpose": "Closed kickoff retro", "target_timing": "done"},
            {"id": "mtg-3", "initiative_id": "init-002", "status": "open",
             "purpose": "Other-initiative meeting", "target_timing": "tbd"},
        ]))
        with patch("pmao.llm.call_structured", return_value=dict(SYNDICATE_OUTPUT)) as mock:
            run_syndicate(vault, "init-001")
        prompt = mock.call_args[0][0]
        assert "decision: Adopt tiered pricing" in prompt
        assert "open question: What is the discount floor?" in prompt
        assert "open meeting: Pricing working session (next week, cadence: weekly until launch)" in prompt
        assert "outstanding meetings (free text): CFO sync still outstanding" in prompt
        assert "Already-resolved question" not in prompt
        assert "Closed kickoff retro" not in prompt
        assert "Other-initiative decision" not in prompt
        assert "Other-initiative meeting" not in prompt


def test_run_syndicate_top_level_list_raises_clean_error():
    """Fix: a top-level JSON list from the LLM must raise a clean ValueError,
    not AttributeError on setdefault."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with patch("pmao.llm.call_structured", return_value=[{"pathway": []}]):
            with pytest.raises(ValueError, match="expected an object"):
                run_syndicate(vault, "init-001")
        assert list((vault / "staging").glob("*.json")) == []


def test_run_syndicate_null_and_wrong_type_fields_do_not_crash(capsys):
    """Fix: null/wrong-type pathway, meetings_to_schedule, review_flags must not crash
    (setdefault keeps existing None values)."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    cases = [
        {"pathway": None, "meetings_to_schedule": None, "review_flags": None},
        {"pathway": "talk to finance first"},
    ]
    for payload in cases:
        with tempfile.TemporaryDirectory() as tmp:
            vault = _vault(tmp)
            with patch("pmao.llm.call_structured", return_value=payload):
                run_syndicate(vault, "init-001")
    out = capsys.readouterr().out
    assert "(no pathway steps returned)" in out


def test_run_syndicate_malformed_pathway_steps_flagged():
    """Fix: a null pathway step or null stakeholders must not crash; malformed
    steps are review-flagged and staged for human review."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        payload = {
            "pathway": [None, {"step": 1, "stakeholders": None, "purpose": "x"}],
            "meetings_to_schedule": [],
            "review_flags": [],
        }
        with patch("pmao.llm.call_structured", return_value=payload):
            run_syndicate(vault, "init-001")
        staged_files = list((vault / "staging").glob("*.json"))
        assert len(staged_files) == 1
        ext = json.loads(staged_files[0].read_text())["extraction"]
        assert any("pathway step" in f for f in ext["review_flags"])


def test_run_syndicate_string_stakeholders_not_character_joined(capsys):
    """Fix: "stakeholders": "Bob" must print 'Bob', not 'B, o, b'."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        payload = {
            "pathway": [{"step": 1, "stakeholders": "Bob", "purpose": "x"}],
            "meetings_to_schedule": [],
            "review_flags": [],
        }
        with patch("pmao.llm.call_structured", return_value=payload):
            run_syndicate(vault, "init-001")
        out = capsys.readouterr().out
        assert "Bob" in out
        assert "B, o, b" not in out


def test_run_syndicate_string_meeting_item_dropped_with_flag():
    """Fix: "meetings_to_schedule": ["kickoff"] must not crash; the non-dict item
    is dropped with a review flag."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        payload = {"pathway": [], "meetings_to_schedule": ["kickoff"], "review_flags": []}
        with patch("pmao.llm.call_structured", return_value=payload):
            run_syndicate(vault, "init-001")
        staged_files = list((vault / "staging").glob("*.json"))
        assert len(staged_files) == 1
        ext = json.loads(staged_files[0].read_text())["extraction"]
        assert ext["meetings_to_schedule"] == []
        assert any("kickoff" in f for f in ext["review_flags"])


def test_run_syndicate_stages_standard_extraction_shape():
    """Fix: staged syndicate extraction must be a standard staging extraction —
    all STAGED_CATEGORIES keys present (others empty), plus alias_flags and discard_note."""
    from unittest.mock import patch
    from pmao.syndicate import run_syndicate
    from pmao.vault import STAGED_CATEGORIES
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault(tmp)
        with patch("pmao.llm.call_structured", return_value=dict(SYNDICATE_OUTPUT)):
            run_syndicate(vault, "init-001")
        staged_files = list((vault / "staging").glob("*.json"))
        assert len(staged_files) == 1
        ext = json.loads(staged_files[0].read_text())["extraction"]
        for category in STAGED_CATEGORIES:
            assert category in ext, f"staged extraction missing category '{category}'"
            if category != "meetings_to_schedule":
                assert ext[category] == []
        assert ext["meetings_to_schedule"] == SYNDICATE_OUTPUT["meetings_to_schedule"]
        assert ext["alias_flags"] == []
        assert ext["discard_note"] == ""
