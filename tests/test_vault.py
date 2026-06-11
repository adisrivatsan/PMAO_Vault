import json
import tempfile
import yaml
from datetime import date
from pathlib import Path

from pmao.models import Initiative
from pmao.vault import init_vault, load_initiatives, save_initiatives, load_list, VAULT_FILES


def _make_initiative(id_="init-001", name="Customer Data Platform", **kwargs):
    defaults = dict(status="not_started", last_touched=date(2026, 6, 8))
    defaults.update(kwargs)
    return Initiative(id=id_, name=name, **defaults)


def test_vault_files_list_excludes_dead_files():
    assert "signals.json" not in VAULT_FILES
    assert "questions.json" not in VAULT_FILES


def test_init_vault_creates_expected_files():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        for fname in VAULT_FILES:
            assert (vault / fname).exists(), f"Missing {fname}"
        assert (vault / "workbook.xlsx").exists()
        assert (vault / "transcripts").is_dir()


def test_init_vault_does_not_create_dead_files():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        assert not (vault / "staging").exists()
        assert not (vault / "signals.json").exists()
        assert not (vault / "questions.json").exists()


def test_init_vault_writes_config():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault, project_name="Acme LRP", owner="J. Smith")
        cfg = yaml.safe_load((vault / "project-config.yaml").read_text())
        assert cfg["project_name"] == "Acme LRP"
        assert cfg["owner"] == "J. Smith"


def test_init_vault_creates_empty_initiatives():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        assert json.loads((vault / "initiatives.json").read_text()) == []


def test_save_and_load_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        loaded = load_initiatives(vault)
        assert len(loaded) == 1
        assert loaded[0].id == "init-001"
        assert loaded[0].name == "Customer Data Platform"


def test_save_creates_backup():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        save_initiatives(vault, [_make_initiative("init-002", "Second")])
        assert (vault / "initiatives.json.bak").exists()


def test_save_writes_slim_schema():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative(owner="Alex")])
        data = json.loads((vault / "initiatives.json").read_text())
        assert data[0]["owner"] == "Alex"
        assert "coordination_owner" not in data[0]
        assert "created" not in data[0]


def test_save_removes_dead_files():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        # Simulate old vault artifacts
        (vault / "signals.json").write_text("[]")
        (vault / "questions.json").write_text("[]")
        staging = vault / "staging"
        staging.mkdir()
        (staging / "x.json").write_text("{}")

        save_initiatives(vault, [_make_initiative()])

        assert not (vault / "signals.json").exists()
        assert not (vault / "questions.json").exists()
        assert not staging.exists()


def test_migration_old_schema_loads_and_writes_slim():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        old_record = [{
            "id": "init-001", "name": "Alpha",
            "status": "in_progress",
            "created": "2026-01-01",
            "last_touched": "2026-06-01",
            "coordination_owner": "Jane Smith",
            "responsible_owner": "Sam Lee",
            "coordination_next_steps": "- Book review",
            "outstanding_questions": "Budget?",
            "last_touch_comment": "[email] done",
            "last_touch_timestamp": "2026-06-09",
        }]
        (vault / "initiatives.json").write_text(json.dumps(old_record))

        loaded = load_initiatives(vault)
        assert loaded[0].owner == "Jane Smith"
        assert loaded[0].next_steps == "- Book review"
        assert loaded[0].last_touched == date(2026, 6, 9)
        assert "Open questions: Budget?" in loaded[0].notes

        # Write back → slim schema
        save_initiatives(vault, loaded)
        data = json.loads((vault / "initiatives.json").read_text())
        assert "coordination_owner" not in data[0]
        assert "created" not in data[0]
        assert data[0]["owner"] == "Jane Smith"


def test_no_lrp_in_config():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        config_text = (vault / "project-config.yaml").read_text()
        assert "lrp" not in config_text.lower()


def test_load_list_missing_file_returns_empty():
    with tempfile.TemporaryDirectory() as tmp:
        assert load_list(Path(tmp), "facts.json") == []


def test_load_list_reads_json_array():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "facts.json").write_text(json.dumps([{"id": "fact-1"}]))
        assert load_list(vault, "facts.json") == [{"id": "fact-1"}]


def test_seed_from_csv_owner_column():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        csv_path = vault / "seed.csv"
        csv_path.write_text("id,name,owner,priority\ninit-001,Alpha,Alex Jordan,high\n")
        from pmao.vault import seed_from_csv
        count = seed_from_csv(vault, csv_path)
        assert count == 1
        loaded = load_initiatives(vault)
        assert loaded[0].owner == "Alex Jordan"
        assert loaded[0].priority == "high"


def test_seed_from_csv_only_name_required():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        csv_path = vault / "seed.csv"
        csv_path.write_text("name\nAlpha\nBeta\n")
        from pmao.vault import seed_from_csv
        count = seed_from_csv(vault, csv_path)
        assert count == 2
        loaded = load_initiatives(vault)
        assert loaded[0].name == "Alpha"
        assert loaded[0].id == "init-001"


def test_seed_from_csv_missing_name_column_raises():
    import pytest
    from pmao.vault import seed_from_csv
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        csv_path = vault / "bad.csv"
        csv_path.write_text("id,owner\ninit-001,Alex Jordan\n")
        with pytest.raises(ValueError, match="name"):
            seed_from_csv(vault, csv_path)


def test_init_vault_refuses_existing_vault():
    import pytest
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        with pytest.raises(FileExistsError):
            init_vault(vault)
        assert len(load_initiatives(vault)) == 1


def test_cmd_init_existing_vault_exits_before_prompting(monkeypatch, capsys):
    import sys
    import pytest
    from unittest.mock import patch
    from pmao.cli import main
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        prompts = []
        monkeypatch.setattr("builtins.input", lambda *a: prompts.append(a) or "")
        with patch.object(sys, "argv", ["pmao", "init", tmp]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 1
        assert prompts == []
