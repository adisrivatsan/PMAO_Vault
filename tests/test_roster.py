import tempfile
from pathlib import Path

import pytest

from pmao.roster import load_roster, render_roster, RosterError


ROSTER_YAML = """\
people:
  - name: Sarah Klein
    aliases: [Sarah, Sarah K]
    role: VP Finance
    domains: [finance, pricing]
    decision_maker: true
    levers: [budget, pricing]
  - name: Dev Patel
    aliases: [Dev]
    role: Analyst
    domains: [cost model]
"""


def test_load_roster_returns_people():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(ROSTER_YAML)
        people = load_roster(vault)
        assert len(people) == 2
        assert people[0]["name"] == "Sarah Klein"
        assert people[0]["decision_maker"] is True
        assert people[1].get("decision_maker") is None


def test_load_roster_missing_file_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_roster(Path(tmp)) is None


def test_load_roster_invalid_yaml_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people: [unclosed")
        with pytest.raises(RosterError):
            load_roster(vault)


def test_load_roster_missing_people_key_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("staff:\n  - name: X\n")
        with pytest.raises(RosterError, match="people"):
            load_roster(vault)


def test_load_roster_person_without_name_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people:\n  - role: Analyst\n")
        with pytest.raises(RosterError, match="name"):
            load_roster(vault)


def test_render_roster_marks_decision_makers():
    people = [
        {"name": "Sarah Klein", "aliases": ["Sarah"], "role": "VP Finance",
         "domains": ["finance"], "decision_maker": True, "levers": ["budget"]},
        {"name": "Dev Patel", "domains": ["cost model"]},
    ]
    text = render_roster(people)
    assert "Sarah Klein" in text
    assert "DECISION-MAKER" in text
    assert "levers: budget" in text
    assert "owns: cost model" in text
    # Non-decision-maker line must not be marked
    dev_line = [ln for ln in text.splitlines() if "Dev Patel" in ln][0]
    assert "DECISION-MAKER" not in dev_line


def test_render_roster_none_gives_no_roster_text():
    text = render_roster(None)
    assert "No roster was provided" in text
    assert "unknown" in text


def test_render_roster_none_is_context_neutral():
    # The fallback is shared by the deep-ingest and syndicate prompts, so it
    # must not leak deep-ingest-only wording like 'principal_signals'.
    text = render_roster(None)
    assert "principal_signals" not in text


def test_load_roster_non_string_name_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people:\n  - name: 2026\n")
        with pytest.raises(RosterError, match=r"people\[0\].*name"):
            load_roster(vault)


def test_load_roster_boolean_name_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people:\n  - name: true\n")
        with pytest.raises(RosterError, match=r"people\[0\].*name"):
            load_roster(vault)


def test_load_roster_scalar_aliases_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(
            "people:\n  - name: Bob\n    aliases: Bobby\n"
        )
        with pytest.raises(RosterError, match=r"people\[0\].*aliases"):
            load_roster(vault)


def test_load_roster_non_string_alias_item_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(
            "people:\n  - name: Bob\n    aliases: [Bobby, 7]\n"
        )
        with pytest.raises(RosterError, match=r"people\[0\].*aliases"):
            load_roster(vault)


def test_load_roster_null_alias_item_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(
            "people:\n  - name: Bob\n    aliases: [null]\n"
        )
        with pytest.raises(RosterError, match=r"people\[0\].*aliases"):
            load_roster(vault)


def test_load_roster_scalar_domains_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(
            "people:\n  - name: Bob\n    domains: pricing\n"
        )
        with pytest.raises(RosterError, match=r"people\[0\].*domains"):
            load_roster(vault)


def test_load_roster_non_string_lever_raises():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(
            "people:\n  - name: Sarah\n    decision_maker: true\n"
            "    levers: [budget, 3]\n"
        )
        with pytest.raises(RosterError, match=r"people\[0\].*levers"):
            load_roster(vault)


def test_load_roster_valid_optional_fields_still_load():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(ROSTER_YAML)
        people = load_roster(vault)
        assert people[0]["aliases"] == ["Sarah", "Sarah K"]
        assert people[1]["domains"] == ["cost model"]
