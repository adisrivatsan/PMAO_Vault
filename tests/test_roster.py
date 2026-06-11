import tempfile
from pathlib import Path

from pmao.roster import load_roster, render_roster


ROSTER_YAML = """\
people:
  - name: Sarah Klein
    aliases: [Sarah, Sarah K]
  - name: Dev Patel
    aliases: [Dev]
"""


def test_load_roster_returns_people():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(ROSTER_YAML)
        people = load_roster(vault)
        assert len(people) == 2
        assert people[0]["name"] == "Sarah Klein"


def test_load_roster_missing_file_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_roster(Path(tmp)) is None


def test_load_roster_invalid_yaml_warns_and_returns_none(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people: [unclosed")
        result = load_roster(vault)
        assert result is None
        assert "Warning" in capsys.readouterr().out


def test_load_roster_missing_people_key_warns_and_returns_none(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("staff:\n  - name: X\n")
        result = load_roster(vault)
        assert result is None
        assert "Warning" in capsys.readouterr().out


def test_load_roster_person_without_name_warns_and_returns_none(capsys):
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text("people:\n  - aliases: [Bob]\n")
        result = load_roster(vault)
        assert result is None
        assert "Warning" in capsys.readouterr().out


def test_load_roster_valid_optional_fields_load():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "roster.yaml").write_text(ROSTER_YAML)
        people = load_roster(vault)
        assert people[0]["aliases"] == ["Sarah", "Sarah K"]


def test_render_roster_shows_name_and_aliases():
    people = [
        {"name": "Sarah Klein", "aliases": ["Sarah", "SK"]},
        {"name": "Dev Patel"},
    ]
    text = render_roster(people)
    assert "Sarah Klein" in text
    assert "Sarah, SK" in text
    assert "Dev Patel" in text


def test_render_roster_no_authority_text():
    people = [{"name": "Sarah Klein", "decision_maker": True, "levers": ["budget"]}]
    text = render_roster(people)
    assert "DECISION-MAKER" not in text
    assert "levers" not in text
    assert "domains" not in text


def test_render_roster_none_returns_empty_string():
    assert render_roster(None) == ""


def test_render_roster_empty_list_returns_empty_string():
    assert render_roster([]) == ""
