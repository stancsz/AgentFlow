import json
from subprocess import CompletedProcess
from typing import List

import pytest

from agentflow.adapters.codex_cli import CodexCLIAdapter, CodexCLIError
from agentflow.config import Settings


class SpyRun:
    """Helper to capture subprocess.run invocations."""

    def __init__(self, return_value: CompletedProcess) -> None:
        self.return_value = return_value
        self.calls: List[List[str]] = []

    def __call__(self, command, **kwargs):  # type: ignore[override]
        self.calls.append(command)
        return self.return_value


def make_completed_process(stdout_lines, returncode=0, stderr=""):
    stdout = "\n".join(stdout_lines)
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_codex_adapter_parses_agent_message(monkeypatch, settings):
    # Ensure settings has openai_api_key for this test
    settings = Settings(openai_api_key="test-key")
    event_lines = [
        json.dumps({"type": "thread.started", "thread_id": "abc"}),
        json.dumps(
            {"type": "item.completed", "item": {"type": "agent_message", "text": "Hello world!"}}
        ),
        json.dumps({"type": "turn.completed", "usage": {"output_tokens": 42}}),
    ]
    spy = SpyRun(make_completed_process(event_lines))
    monkeypatch.setattr("subprocess.run", spy)

    adapter = CodexCLIAdapter(settings)
    result = adapter.run("Say hello.")

    assert result.message == "Hello world!"
    assert result.usage == {"output_tokens": 42}

    assert len(spy.calls) == 1
    command = spy.calls[0]
    assert command[:3] == [settings.codex_cli_path, "exec", "--model"]
    assert command[-1] == "-"


def test_codex_adapter_raises_on_failure(monkeypatch, settings):
    # Ensure settings has openai_api_key for this test
    settings = Settings(openai_api_key="test-key")
    spy = SpyRun(make_completed_process([], returncode=1, stderr="boom"))
    monkeypatch.setattr("subprocess.run", spy)

    adapter = CodexCLIAdapter(settings)

    with pytest.raises(CodexCLIError):
        adapter.run("test")
