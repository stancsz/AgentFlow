import yaml

from agentflow.adapters.codex_cli import CodexResult, CodexCLIError
from agentflow.cli import main as agentflow_main
from agentflow.config import Settings


class FakeAdapter:
    def __init__(self, settings):
        self.settings = settings
        self.calls = []

    def run(self, prompt: str):
        self.calls.append(prompt)
        if len(self.calls) == 1:
            events = [{"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}}]
            return CodexResult(
                message="Hello tester!",
                events=events,
                usage={"output_tokens": 5, "input_tokens": 10},
            )
        evaluation_message = "Score: 0.85\n- Reason: Meets requirements."
        return CodexResult(
            message=evaluation_message,
            events=[],
            usage={"output_tokens": 3, "input_tokens": 12},
        )


def test_main_creates_yaml_on_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings(openai_api_key="test-key")
    monkeypatch.setattr("agentflow.cli.Settings.from_env", lambda: settings)

    adapter = FakeAdapter(settings)
    # Mock the adapter resolver to return FakeAdapter
    monkeypatch.setattr("agentflow.cli.entry._resolve_adapter", lambda name: (lambda s: adapter, CodexCLIError))

    exit_code = agentflow_main(["Generate summary"])
    assert exit_code == 0

    files = sorted(tmp_path.glob("agentflow-*.yaml"))
    assert len(files) == 1
    payload = yaml.safe_load(files[0].read_text(encoding="utf-8"))

    assert payload["status"] == "completed"
    assert payload["nodes"][0]["outputs"]["message"] == "Hello tester!"
    assert payload["nodes"][0]["metrics"]["usage"]["output_tokens"] == 5
    evaluation = payload["nodes"][0]["outputs"]["evaluation"]
    assert evaluation["score"] == 0.85
    assert evaluation["justification"] == "Meets requirements."
    assert payload["nodes"][0]["metrics"]["evaluation_score"] == 0.85
    assert payload["eval_metrics"]["self_evaluation_score"] == 0.85


class FailingAdapter:
    def __init__(self, settings):
        self.settings = settings

    def run(self, prompt: str):
        raise CodexCLIError("simulated failure")


def test_main_writes_failed_artifact(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    settings = Settings(openai_api_key="test-key")
    monkeypatch.setattr("agentflow.cli.Settings.from_env", lambda: settings)
    # Mock the adapter resolver to return FailingAdapter
    failing_adapter_instance = FailingAdapter(settings)
    monkeypatch.setattr("agentflow.cli.entry._resolve_adapter", lambda name: (lambda s: failing_adapter_instance, CodexCLIError))

    exit_code = agentflow_main(["Do the thing"])
    assert exit_code == 1

    files = sorted(tmp_path.glob("agentflow-*.yaml"))
    assert len(files) == 1
    payload = yaml.safe_load(files[0].read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    node = payload["nodes"][0]
    assert node["status"] == "failed"
    # The error is now caught generically as Exception
    assert "simulated failure" in node["error"]["message"] or "CodexCLIError" in node["error"]["message"]


def test_view_command_invokes_server(monkeypatch, tmp_path):
    called = {}

    def fake_run_viewer(*, directory, host, port):
        called["directory"] = directory
        called["host"] = host
        called["port"] = port

    monkeypatch.setattr("agentflow.cli.run_viewer", fake_run_viewer)

    exit_code = agentflow_main(["view", "--directory", str(tmp_path), "--host", "0.0.0.0", "--port", "5055"])
    assert exit_code == 0
    assert called["directory"] == tmp_path.resolve()
    assert called["host"] == "0.0.0.0"
    assert called["port"] == 5055
