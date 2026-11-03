import json
import sys

from pmao.cli import main


def test_migrate_command_prints_counts(tmp_path, monkeypatch, capsys):
    (tmp_path / "initiatives.json").write_text(json.dumps([{"id": "init-001", "name": "Alpha", "status": "not_started"}]))
    monkeypatch.setattr(sys, "argv", ["pmao", "migrate", str(tmp_path)])
    main()
    assert "projects: 1" in capsys.readouterr().out
    assert list((tmp_path / "projects").glob("*.md"))


def test_init_then_ingest_end_to_end(tmp_path, monkeypatch):
    vault = tmp_path / "v"
    csv = tmp_path / "r.csv"
    csv.write_text("id,name,owner,priority\ninit-001,Alpha,Jane,high\n")
    monkeypatch.setattr("builtins.input", lambda *_: "")
    monkeypatch.setattr(sys, "argv", ["pmao", "init", str(vault), "--roster", str(csv)])
    main()

    src = tmp_path / "notes.md"
    src.write_text("Alpha is going well. Jane will send the deck. Bob mentioned Zed.")
    extraction = {
        "initiative_updates": [{"initiative_id": "init-001", "current_state": "Going well",
                                "next_steps": "", "last_touch_comment": "", "status": ""}],
        "new_actions": [{"initiative_id": "init-001", "description": "Send the deck", "owner": "Jane"}],
        "unmatched_references": [{"mention": "Zed", "context": "Bob mentioned Zed"}],
    }
    monkeypatch.setattr("pmao.llm.call_structured", lambda *a, **k: extraction)
    monkeypatch.setattr(sys, "argv", ["pmao", "ingest", str(vault), "--source", str(src), "--yes"])
    main()

    assert "Going well" in next((vault / "projects").glob("*.md")).read_text()
    assert list((vault / "tasks").glob("*.md"))
    assert list((vault / "inbox").glob("*.md"))
