import os

import pytest

from agentflow.adapters.claude_cli import ClaudeCLIAdapter
from agentflow.config import Settings


pytestmark = pytest.mark.live


def _can_run_live() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


@pytest.mark.skipif(not _can_run_live(), reason="ANTHROPIC_API_KEY is required for live test.")
def test_claude_adapter_live_round_trip():
    settings = Settings(anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"))
    adapter = ClaudeCLIAdapter(settings)
    result = adapter.run("Return the word ok.")
    assert "ok" in result.message.lower()
    assert isinstance(result.usage, dict)
