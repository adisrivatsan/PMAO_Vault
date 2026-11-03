from pmao.roster import load_roster, render_roster


def _person(vault, stem, text):
    d = vault / "people"
    d.mkdir(exist_ok=True)
    (d / f"{stem}.md").write_text(text)


def test_load_roster_reads_people_folder(tmp_path):
    _person(tmp_path, "jane-smith",
            "---\ntype: person\nname: Jane Smith\naliases: [Jane]\nrole: PM\n---\n")
    people = load_roster(tmp_path)
    assert len(people) == 1
    assert people[0]["name"] == "Jane Smith"
    assert people[0]["aliases"] == ["Jane"]
    assert people[0]["role"] == "PM"


def test_load_roster_missing_folder_returns_none(tmp_path):
    assert load_roster(tmp_path) is None


def test_load_roster_empty_folder_returns_none(tmp_path):
    (tmp_path / "people").mkdir()
    assert load_roster(tmp_path) is None


def test_load_roster_skips_person_without_name(tmp_path, capsys):
    _person(tmp_path, "nameless", "---\ntype: person\nrole: PM\n---\n")
    _person(tmp_path, "dev-patel", "---\ntype: person\nname: Dev Patel\n---\n")
    people = load_roster(tmp_path)
    assert [p["name"] for p in people] == ["Dev Patel"]
    assert "Warning" in capsys.readouterr().err


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
