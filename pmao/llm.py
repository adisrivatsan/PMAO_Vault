import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

_KNOWN_BACKENDS = {"claude", "codex"}
DEFAULT_TIMEOUT = 120


class LLMError(Exception):
    pass


def load_llm_settings(vault_path: Path = None) -> tuple:
    """Read llm_backend / llm_timeout_seconds from the vault's project-config.yaml.

    Returns (backend or None, timeout seconds). Missing vault, missing file,
    or unreadable YAML falls back to (None, DEFAULT_TIMEOUT).
    """
    backend = None
    timeout = DEFAULT_TIMEOUT
    if vault_path is None:
        return backend, timeout
    config_path = Path(vault_path) / "project-config.yaml"
    if not config_path.exists():
        return backend, timeout
    try:
        config = yaml.safe_load(config_path.read_text())
    except yaml.YAMLError:
        return backend, timeout
    if not isinstance(config, dict):
        return backend, timeout
    backend = config.get("llm_backend") or None
    raw_timeout = config.get("llm_timeout_seconds")
    if raw_timeout:
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            pass
    return backend, timeout


def detect_backend(config_override: str = None) -> str:
    if config_override:
        return config_override
    if shutil.which("claude"):
        return "claude"
    if shutil.which("codex"):
        return "codex"
    raise LLMError(
        "No LLM backend found. Install Claude Code (claude) or OpenAI Codex CLI (codex)."
    )


def _run(backend: str, prompt: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    if backend not in _KNOWN_BACKENDS:
        raise LLMError(f"Unknown backend '{backend}'. Choose from: {_KNOWN_BACKENDS}")
    if backend == "claude":
        cmd = ["claude", "-p", prompt]
    else:
        cmd = ["codex", "-q", prompt]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise LLMError(f"Backend timed out after {timeout}s")
    if result.returncode != 0:
        raise LLMError(
            f"Backend '{backend}' exited {result.returncode}.\nstderr: {result.stderr.strip()[:500]}"
        )
    return result.stdout.strip()


def call_text(
    prompt: str,
    config_override: str = None,
    timeout: int = None,
    vault_path: Path = None,
) -> str:
    """Call the LLM and return raw text output (for status, summarize).

    Backend precedence: --backend CLI override, then the vault's
    project-config.yaml llm_backend, then PATH auto-detect. Timeout: explicit
    arg, then llm_timeout_seconds, then DEFAULT_TIMEOUT.
    """
    config_backend, config_timeout = load_llm_settings(vault_path)
    backend = detect_backend(config_override or config_backend)
    return _run(backend, prompt, timeout if timeout is not None else config_timeout)


def call_structured(
    prompt: str,
    config_override: str = None,
    timeout: int = None,
    vault_path: Path = None,
) -> Any:
    """Call the LLM and return parsed JSON (for ingest, update).

    Same backend/timeout precedence as call_text.
    """
    config_backend, config_timeout = load_llm_settings(vault_path)
    backend = detect_backend(config_override or config_backend)
    if timeout is None:
        timeout = config_timeout
    for attempt in range(2):
        if attempt == 0:
            current_prompt = prompt
        else:
            current_prompt = prompt + "\n\nIMPORTANT: Respond ONLY with valid JSON. No preamble, no explanation, no markdown."
        raw = _run(backend, current_prompt, timeout)
        text = raw
        if text.startswith("```"):
            text_lines = text.splitlines()
            if text_lines[0].startswith("```"):
                text_lines = text_lines[1:]
            if text_lines and text_lines[-1].startswith("```"):
                text_lines = text_lines[:-1]
            text = "\n".join(text_lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            if attempt == 1:
                raise LLMError(
                    f"LLM returned unparseable JSON after 2 attempts.\nRaw output:\n{raw[:500]}"
                )
