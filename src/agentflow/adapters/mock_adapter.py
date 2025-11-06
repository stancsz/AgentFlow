"""
Mock adapter for testing and demos.

Returns canned responses without calling any external CLI or API. Useful for:
- Testing the AgentFlow CLI and viewer without external dependencies.
- Generating sample artifacts for demos and documentation.
- Running unit/integration tests that don't require real API keys.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from agentflow.config import Settings


class MockAdapterError(RuntimeError):
    """Raised when the mock adapter encounters an error (for testing error paths)."""


@dataclass(slots=True)
class MockResult:
    """Structured representation of a mock execution."""

    message: str
    events: List[Dict]
    usage: Dict


class MockAdapter:
    """
    Mock adapter that returns canned responses for testing.

    Parameters
    ----------
    settings:
        Injected Settings instance (not used by mock, but kept for interface compatibility).
    extra_args:
        Optional iterable of additional flags (not used by mock).
    """

    def __init__(self, settings: Settings, extra_args: Optional[Iterable[str]] = None) -> None:
        self._settings = settings
        self._extra_args = list(extra_args or [])

    def run(
        self,
        prompt: str,
        *,
        timeout: int = 120,
        cwd: Optional[str] = None,
    ) -> MockResult:
        """
        Return a canned response based on the prompt.

        The mock adapter generates a synthetic flow spec for prompts that mention
        "flow" or "workflow", and a simple message otherwise.
        """

        prompt_lower = prompt.lower()

        # Generate a flow spec if the prompt mentions flow/workflow
        if "flow" in prompt_lower or "workflow" in prompt_lower:
            flow_spec = {
                "nodes": [
                    {"id": "start", "type": "action", "label": "Start", "name": "start"},
                    {"id": "greet", "type": "action", "label": "Say Hello", "name": "greet"},
                    {"id": "end", "type": "action", "label": "End", "name": "end"},
                ],
                "edges": [
                    {"source": "start", "target": "greet", "label": "begin"},
                    {"source": "greet", "target": "end", "label": "finish"},
                ],
            }
            afl_text = (
                "start();\n"
                "greet();\n"
                "end();\n"
            )
            message = (
                f"Here is a simple flow for your request:\n\n"
                f"```json flow_spec\n"
                f'{{"flow_spec": {flow_spec}, "agentflowlanguage": "{afl_text}"}}\n'
                f"```\n\n"
                f"This flow has three steps: start, greet (say hello), and end."
            )
            # Embed the flow_spec in the message so the CLI can extract it
            import json
            message = (
                f"Here is a simple flow for your request:\n\n"
                f"```json\n"
                f'{json.dumps({"flow_spec": flow_spec, "agentflowlanguage": afl_text}, indent=2)}\n'
                f"```\n\n"
                f"This flow has three steps: start, greet (say hello), and end."
            )
        else:
            message = f"Mock response: I received your prompt '{prompt[:50]}...' and here is a canned reply. This is a test response from the mock adapter."

        events = [
            {"type": "thread.started", "thread_id": "mock-thread-123"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": message}},
            {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 25}},
        ]

        usage = {"input_tokens": 10, "output_tokens": 25, "total_tokens": 35}

        return MockResult(message=message, events=events, usage=usage)
