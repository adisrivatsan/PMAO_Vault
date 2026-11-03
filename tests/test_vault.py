import tempfile
import yaml
from datetime import date
from pathlib import Path

from pmao.models import Initiative
from pmao.store import write_item
from pmao.vault import init_vault, load_initiatives, save_initiatives, load_items, VAULT_DIRS


def _make_initiative(id_="init-001", name="Customer Data Platform", **kwargs):
    defaults = dict(status="not_started", last_touched=date(2026, 6, 8))
    defaults.update(kwargs)
    return Initiative(id=id_, name=name, **defaults)


def test_init_vault_creates_folders_and_schema():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        for d in VAULT_DIRS:
            assert (vault / d).is_dir(), f"Missing {d}"
        assert (vault / "SCHEMA.md").exists()
        assert (vault / "workbook.xlsx").exists()
        assert list(vault.glob("*.json")) == []


def test_init_vault_writes_config():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault, project_name="Acme LRP", owner="J. Smith")
        cfg = yaml.safe_load((vault / "project-config.yaml").read_text())
        assert cfg["project_name"] == "Acme LRP"
        assert cfg["owner"] == "J. Smith"


def test_save_and_load_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        loaded = load_initiatives(vault)
        assert len(loaded) == 1
        assert loaded[0].id == "init-001"
        assert loaded[0].name == "Customer Data Platform"


def test_project_round_trip_multiline():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        init = _make_initiative(next_steps="- a\n- b", notes="## not a heading\nx",
                                current_state="Going: well", last_touch_comment="[email] done")
        save_initiatives(vault, [init])
        assert load_initiatives(vault) == [init]


def test_project_file_is_readable_markdown():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative(current_state="Going well")])
        text = (vault / "projects" / "customer-data-platform.md").read_text()
        assert text.startswith("---")
        assert "type: project" in text
        assert "## Current state" in text
        assert "## Next steps" not in text


def test_save_initiatives_reuses_file_for_same_id():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        save_initiatives(vault, [_make_initiative()])
        save_initiatives(vault, [_make_initiative(name="Renamed")])
        files = list((vault / "projects").glob("*.md"))
        assert len(files) == 1
        assert load_initiatives(vault)[0].name == "Renamed"


def test_load_items_filters_by_type():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        write_item(vault, "notes", {"type": "hypothesis", "id": "h1"}, "H")
        write_item(vault, "notes", {"type": "fact", "id": "f1"}, "F")
        assert len(load_items(vault, "notes")) == 2
        assert [i["id"] for i in load_items(vault, "notes", "fact")] == ["f1"]


def test_no_lrp_in_config():
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        init_vault(vault)
        config_text = (vault / "project-config.yaml").read_text()
        assert "lrp" not in config_text.lower()


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
