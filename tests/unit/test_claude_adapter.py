import json
from subprocess import CompletedProcess

import pytest

from agentflow.adapters.claude_cli import ClaudeCLIAdapter, ClaudeCLIError
from agentflow.config import Settings


class SpyRun:
    def __init__(self, return_value: CompletedProcess) -> None:
        self.return_value = return_value
        self.calls = []

    def __call__(self, command, **kwargs):  # type: ignore[override]
        self.calls.append(command)
        return self.return_value


def make_completed_process(stdout_json: dict, returncode=0, stderr=""):
    stdout = json.dumps(stdout_json)
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_claude_adapter_parses_text_content(monkeypatch):
    payload = {
        "id": "msg_123",
        "content": [
            {"type": "text", "text": "Hello from Claude."},
        ],
        "usage": {"input_tokens": 5, "output_tokens": 7},
    }
    spy = SpyRun(make_completed_process(payload))
    monkeypatch.setattr("subprocess.run", spy)

    settings = Settings(anthropic_api_key="test-key")
    adapter = ClaudeCLIAdapter(settings)

    result = adapter.run("Say hello.")
    assert result.message == "Hello from Claude."
    assert result.usage == {"input_tokens": 5, "output_tokens": 7}

    assert spy.calls, "Expected subprocess to be invoked"
    command = spy.calls[0]
    # anthropic messages create -m <model> --max-tokens <n> --json -p <prompt>
    assert command[:3] == [settings.anthropic_cli_path, "messages", "create"]
    assert "-p" in command


def test_claude_adapter_raises_on_failure(monkeypatch):
    spy = SpyRun(CompletedProcess(args=[], returncode=1, stdout="", stderr="boom"))
    monkeypatch.setattr("subprocess.run", spy)

    settings = Settings(anthropic_api_key="test-key")
    adapter = ClaudeCLIAdapter(settings)

    with pytest.raises(ClaudeCLIError):
        adapter.run("test")
