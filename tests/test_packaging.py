from pathlib import Path

import pytest

import pmao
from pmao.ingest import _load_skill

PKG_DIR = Path(pmao.__file__).parent
SKILL_NAMES = ["ingest", "ingest-deep", "status", "summarize", "syndicate", "update"]


def test_skills_ship_inside_the_pmao_package():
    # Regression: skills/ used to live next to the repo checkout (a sibling of
    # pmao/), so a pip-installed pmao-cli had no skill files at all and every
    # LLM command died with FileNotFoundError. Skills must live inside the
    # importable package so they are installed as package data.
    for name in SKILL_NAMES:
        skill_file = PKG_DIR / "skills" / f"{name}.md"
        assert skill_file.is_file(), f"{skill_file} missing from the pmao package"


def test_templates_ship_inside_the_pmao_package():
    for name in ["initiative-template.csv", "project-config.yaml", "workbook-schema.yaml"]:
        template_file = PKG_DIR / "templates" / name
        assert template_file.is_file(), f"{template_file} missing from the pmao package"


def test_load_skill_resolves_via_package_resources():
    for name in SKILL_NAMES:
        text = _load_skill(name)
        assert text.strip(), f"skill {name} loaded empty"


def test_load_skill_missing_skill_raises():
    with pytest.raises(FileNotFoundError):
        _load_skill("no-such-skill")


def test_pyproject_declares_skill_and_template_package_data():
    # Without [tool.setuptools.package-data], non-.py files inside pmao/ are
    # silently dropped from wheels and the installed CLI breaks again.
    pyproject = (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.setuptools.package-data]" in pyproject
    assert "skills/*.md" in pyproject
    assert "templates/*" in pyproject
