import json
import yaml

from pmao.migrate import migrate_vault
from pmao.roster import load_roster
from pmao.vault import load_initiatives, load_items


def _old_vault(path):
    (path / "initiatives.json").write_text(json.dumps([
        {"id": "init-001", "name": "Alpha: the first", "status": "in_progress",
         "last_touched": "2026-01-01", "current_state": "Going well"}]))
    (path / "actions.json").write_text(json.dumps([
        {"id": "act-1", "initiative_id": "init-001", "description": "Do it",
         "status": "open", "created": "2026-01-01", "source": "t.md"}]))
    (path / "meetings.json").write_text(json.dumps([
        {"id": "mtg-1", "initiative_id": "init-001", "purpose": "Kickoff", "status": "open"}]))
    (path / "decisions.json").write_text(json.dumps([
        {"id": "dec-1", "initiative_id": "init-001", "decision": "Go", "status": "recorded"}]))
    (path / "hypotheses.json").write_text(json.dumps([
        {"id": "hyp-1", "initiative_id": None, "hypothesis": "It works", "status": "open"}]))
    (path / "facts.json").write_text(json.dumps([
        {"id": "fact-1", "initiative_id": "init-001", "claim": "It is 5", "status": "recorded"}]))
    (path / "roster.yaml").write_text(yaml.dump({"people": [{"name": "Jane Smith", "aliases": ["Jane"]}]}))
    (path / "transcripts").mkdir()
    (path / "transcripts" / "call.vtt").write_text("hello")


def test_migrate_converts_all_types(tmp_path):
    _old_vault(tmp_path)
    counts = migrate_vault(tmp_path)
    assert counts["projects"] == 1 and counts["tasks"] == 1 and counts["meetings"] == 1
    assert counts["decisions"] == 1 and counts["notes"] == 2 and counts["people"] == 1
    assert load_initiatives(tmp_path)[0].name == "Alpha: the first"
    task = load_items(tmp_path, "tasks")[0]
    assert task["type"] == "task" and task["initiative_id"] == "init-001" and task["status"] == "open"
    assert task["description"] == "Do it"
    assert load_items(tmp_path, "notes", "hypothesis")[0]["hypothesis"] == "It works"
    assert load_items(tmp_path, "notes", "fact")[0]["claim"] == "It is 5"
    assert load_roster(tmp_path)[0]["aliases"] == ["Jane"]
    assert (tmp_path / "SCHEMA.md").exists()


def test_migrate_twice_adds_nothing(tmp_path):
    _old_vault(tmp_path)
    migrate_vault(tmp_path)
    counts = migrate_vault(tmp_path)
    assert all(v == 0 for v in counts.values())
    assert len(load_initiatives(tmp_path)) == 1
    assert len(load_items(tmp_path, "tasks")) == 1
    assert len(load_items(tmp_path, "notes")) == 2
    assert len(load_roster(tmp_path)) == 1


def test_migrate_tolerates_missing_files(tmp_path):
    counts = migrate_vault(tmp_path)
    assert all(v == 0 for v in counts.values())
    assert (tmp_path / "inbox").is_dir()


def test_migrate_moves_transcripts_to_docs(tmp_path):
    _old_vault(tmp_path)
    migrate_vault(tmp_path)
    assert (tmp_path / "docs" / "call.vtt").read_text() == "hello"
    assert not (tmp_path / "transcripts" / "call.vtt").exists()


def test_migrate_leaves_old_files(tmp_path):
    _old_vault(tmp_path)
    migrate_vault(tmp_path)
    assert (tmp_path / "initiatives.json").exists()
    assert (tmp_path / "roster.yaml").exists()


def test_migrate_keeps_duplicate_id_and_no_id_items(tmp_path):
    (tmp_path / "actions.json").write_text(json.dumps([
        {"id": "a1", "description": "First", "status": "open"},
        {"id": "a1", "description": "Second", "status": "open"},
        {"description": "No id one", "status": "open"},
        {"description": "No id two", "status": "open"}]))
    assert migrate_vault(tmp_path)["tasks"] == 4
    assert len(load_items(tmp_path, "tasks")) == 4
    assert migrate_vault(tmp_path)["tasks"] == 0
    assert len(load_items(tmp_path, "tasks")) == 4
