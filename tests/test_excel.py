import tempfile
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from pmao.models import Initiative
from pmao.excel import create_workbook


def _make_initiative(id_="init-001", **kwargs):
    defaults = dict(
        name="Customer Data Platform",
        status="not_started",
        last_touched=date(2026, 6, 8),
    )
    defaults.update(kwargs)
    return Initiative(id=id_, **defaults)


def test_workbook_has_exactly_six_tabs():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        assert wb.sheetnames == [
            "Dashboard",
            "Initiatives",
            "Actions & Decisions",
            "Meetings",
            "Hypotheses",
            "Facts",
        ]


def test_dashboard_headers():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        ws = wb["Dashboard"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        assert "name" in headers
        assert "status" in headers
        assert "priority" in headers
        assert "owner" in headers
        assert "last_touched" in headers
        assert "current_state" in headers


def test_dashboard_populates_from_initiative():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative(
            status="in_progress", priority="high",
            owner="Alex Jordan", current_state="Analysis done",
            last_touched=date(2026, 6, 11),
        )
        create_workbook(path, [init])
        wb = load_workbook(path)
        ws = wb["Dashboard"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        assert ws.cell(2, headers["name"]).value == "Customer Data Platform"
        assert ws.cell(2, headers["status"]).value == "in_progress"
        assert ws.cell(2, headers["owner"]).value == "Alex Jordan"


def test_initiatives_tab_has_all_slim_fields():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        ws = wb["Initiatives"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        for field in ("id", "name", "status", "priority", "owner",
                      "current_state", "next_steps", "last_touched",
                      "last_touch_comment", "notes"):
            assert field in headers, f"Missing column: {field}"


def test_initiatives_tab_no_old_fields():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        ws = wb["Initiatives"]
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
        for old in ("coordination_owner", "responsible_owner",
                    "coordination_next_steps", "outstanding_questions",
                    "outstanding_meetings", "syndication_notes",
                    "materials_link", "created"):
            assert old not in headers, f"Old field still present: {old}"


def test_actions_decisions_tab_combined():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        actions = [{"id": "act-001", "initiative_id": "init-001",
                    "description": "Schedule review", "owner": "Alex",
                    "due": "2026-06-15", "status": "open",
                    "created": "2026-06-11", "source": "notes.md"}]
        decisions = [{"id": "dec-001", "initiative_id": "init-001",
                      "decision": "Budget approved", "rationale": "Board vote",
                      "owner": "Jane", "status": "recorded",
                      "created": "2026-06-11", "source": "meeting.vtt"}]
        create_workbook(path, [init], actions=actions, decisions=decisions)
        wb = load_workbook(path)
        ws = wb["Actions & Decisions"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        assert "type" in headers
        assert "description" in headers

        types = {ws.cell(r, headers["type"]).value for r in (2, 3)}
        assert "action" in types
        assert "decision" in types


def test_meetings_tab():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        meetings = [{"id": "mtg-001", "initiative_id": "init-001",
                     "purpose": "Kickoff", "attendees": ["Alex", "Sam"],
                     "status": "open", "created": "2026-06-11", "source": "notes.md"}]
        create_workbook(path, [init], meetings=meetings)
        wb = load_workbook(path)
        ws = wb["Meetings"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        assert "purpose" in headers
        assert "attendees" in headers
        assert ws.cell(2, headers["purpose"]).value == "Kickoff"


def test_hypotheses_tab_project_level_first():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        hyps = [
            {"id": "hyp-002", "initiative_id": "init-001", "hypothesis": "Initiative-level",
             "owner": "", "validation_path": "", "status": "open",
             "created": "2026-06-09", "source": "call.vtt"},
            {"id": "hyp-001", "initiative_id": None, "hypothesis": "Project-level",
             "owner": "", "validation_path": "", "status": "open",
             "created": "2026-06-09", "source": "call.vtt"},
        ]
        create_workbook(path, [init], hypotheses=hyps)
        wb = load_workbook(path)
        ws = wb["Hypotheses"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        assert ws.cell(2, headers["level"]).value == "Project"
        assert ws.cell(3, headers["level"]).value == "Initiative"


def test_facts_tab():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        facts = [{"id": "fact-001", "initiative_id": "init-001",
                  "claim": "Q2 cost up 9%", "stated_by": "Sarah Klein",
                  "status": "recorded", "created": "2026-06-11", "source": "sync.vtt"}]
        create_workbook(path, [init], facts=facts)
        wb = load_workbook(path)
        ws = wb["Facts"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        assert ws.cell(2, headers["claim"]).value == "Q2 cost up 9%"
        assert ws.cell(2, headers["initiative"]).value == "Customer Data Platform"


def test_formula_injection_guard():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        facts = [{"id": "fact-001", "initiative_id": "init-001",
                  "claim": '=HYPERLINK("http://x","y")', "stated_by": "Sarah",
                  "status": "recorded", "created": "2026-06-11", "source": "sync.vtt"}]
        create_workbook(path, [init], facts=facts)
        wb = load_workbook(path)
        ws = wb["Facts"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        cell = ws.cell(2, headers["claim"])
        assert cell.data_type != "f"


def test_control_characters_stripped():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        facts = [{"id": "fact-001", "initiative_id": "init-001",
                  "claim": "cost up 9%\x0b per Q2\x00", "stated_by": "Sarah",
                  "status": "recorded", "created": "2026-06-11", "source": "sync.vtt"}]
        create_workbook(path, [init], facts=facts)
        wb = load_workbook(path)
        ws = wb["Facts"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        assert wb["Facts"].cell(2, headers["claim"]).value == "cost up 9% per Q2"


def test_overlong_value_truncated():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        init = _make_initiative()
        facts = [{"id": "fact-001", "initiative_id": "init-001",
                  "claim": "x" * 40000, "stated_by": "S",
                  "status": "recorded", "created": "2026-06-11", "source": "s.vtt"}]
        create_workbook(path, [init], facts=facts)
        wb = load_workbook(path)
        ws = wb["Facts"]
        headers = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1)}
        val = ws.cell(2, headers["claim"]).value
        assert len(val) <= 32767
        assert val.endswith("[truncated]")


def test_workbook_empty_initiatives():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "test.xlsx"
        create_workbook(path, [])
        wb = load_workbook(path)
        assert wb["Initiatives"].max_row == 1
