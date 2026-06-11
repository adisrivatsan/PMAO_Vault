import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from pmao.llm import call_structured, call_text, LLMError

def test_call_text_returns_string():
    with patch("pmao.llm._run", return_value="status dashboard output"):
        result = call_text("show status", config_override="claude")
    assert result == "status dashboard output"

def test_call_structured_parses_json():
    with patch("pmao.llm._run", return_value='{"key": "value"}'):
        result = call_structured("extract json", config_override="claude")
    assert result == {"key": "value"}

def test_call_structured_strips_markdown_fences():
    raw = "```json\n{\"a\": 1}\n```"
    with patch("pmao.llm._run", return_value=raw):
        result = call_structured("extract", config_override="claude")
    assert result == {"a": 1}

def test_detect_backend_raises_when_none_found():
    with patch("shutil.which", return_value=None):
        from pmao.llm import LLMError, detect_backend
        try:
            detect_backend()
            assert False, "Should have raised"
        except LLMError:
            pass


def _vault_with_config(tmp, **settings):
    vault = Path(tmp)
    config = {"project_name": "Test", "owner": ""}
    config.update(settings)
    (vault / "project-config.yaml").write_text(yaml.dump(config))
    return vault

def test_config_llm_backend_is_read_from_vault():
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault_with_config(tmp, llm_backend="codex")
        with patch("pmao.llm._run", return_value="ok") as run:
            call_text("show status", vault_path=vault)
        assert run.call_args[0][0] == "codex"

def test_cli_backend_override_beats_config():
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault_with_config(tmp, llm_backend="codex")
        with patch("pmao.llm._run", return_value="ok") as run:
            call_text("show status", config_override="claude", vault_path=vault)
        assert run.call_args[0][0] == "claude"

def test_config_llm_timeout_is_read_from_vault():
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault_with_config(tmp, llm_backend="claude", llm_timeout_seconds=7)
        with patch("pmao.llm._run", return_value="ok") as run:
            call_text("show status", vault_path=vault)
        assert run.call_args[0][2] == 7

def test_call_structured_reads_config_settings():
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault_with_config(tmp, llm_backend="codex", llm_timeout_seconds=9)
        with patch("pmao.llm._run", return_value='{"a": 1}') as run:
            result = call_structured("extract", vault_path=vault)
        assert result == {"a": 1}
        assert run.call_args[0][0] == "codex"
        assert run.call_args[0][2] == 9

def test_null_config_backend_falls_through_to_autodetect():
    with tempfile.TemporaryDirectory() as tmp:
        vault = _vault_with_config(tmp, llm_backend=None)
        with patch("shutil.which", lambda name: "/usr/bin/claude" if name == "claude" else None), \
             patch("pmao.llm._run", return_value="ok") as run:
            call_text("show status", vault_path=vault)
        assert run.call_args[0][0] == "claude"
        assert run.call_args[0][2] == 120
