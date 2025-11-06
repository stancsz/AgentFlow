"""
Copilot CLI adapter.

Thin wrapper around a hypothetical GitHub Copilot CLI. This adapter mirrors the
Codex CLI adapter interface used by the AgentFlow CLI: it exposes a .run(prompt)
method that returns a CopilotResult(message, events, usage) and raises
CopilotCLIError on failures.

The implementation expects the CLI to optionally emit JSONL event lines (one
JSON object per line). It is lenient and will also accept plain text output by
returning the full stdout as the assistant message.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from agentflow.config import Settings


class CopilotCLIError(RuntimeError):
    """Raised when the Copilot CLI returns a non-zero exit code or emits invalid output."""


@dataclass(slots=True)
class CopilotResult:
    """Structured representation of a Copilot execution."""

    message: str
    events: List[Dict]
    usage: Dict


class CopilotCLIAdapter:
    """
    Wrapper around a Copilot CLI command.

    Parameters
    ----------
    settings:
        Injected Settings instance controlling authentication and execution policy.
    extra_args:
        Optional iterable of additional CLI flags supplied to each invocation.
    """

    def __init__(self, settings: Settings, extra_args: Optional[Iterable[str]] = None) -> None:
        self._settings = settings
        self._extra_args = list(extra_args or [])

    def build_base_command(self) -> List[str]:
        """Construct the CLI command prior to adding the prompt."""

        # Allow overriding the path via settings if provided. Use a conservative
        # default of 'copilot' which is commonly used for the CLI binary.
        cli_path = getattr(self._settings, "copilot_cli_path", "copilot")
        command = [cli_path, "exec", "--json"]
        command.extend(self._extra_args)
        return command

    def run(
        self,
        prompt: str,
        *,
        timeout: int = 120,
        cwd: Optional[str] = None,
    ) -> CopilotResult:
        """
        Execute Copilot with the supplied prompt and return the parsed response.

        The method attempts to parse JSONL event lines from stdout. If parsing
        yields no assistant message events, the raw stdout is returned as the
        message. Raises CopilotCLIError on non-zero exit or parse failures.
        """

        env = os.environ.copy()

        # If the settings provide a copilot token, inject it into the environment.
        token = getattr(self._settings, "copilot_token", None)
        if token:
            env["COPILOT_TOKEN"] = token

        # Pass the prompt as the final CLI argument so behavior matches the
        # Codex adapter and unit tests can assert on the command shape.
        command = self.build_base_command() + [prompt]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )

        if completed.returncode != 0:
            raise CopilotCLIError(
                f"Copilot CLI exited with {completed.returncode}: {completed.stderr.strip()}"
            )

        events: List[Dict] = []
        message_text: Optional[str] = None
        usage: Dict = {}

        # Try to parse JSONL event lines. If parsing fails for a line, raise
        # a parse error. If no JSON lines are present, fall back to raw stdout.
        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Not JSON; continue parsing but we will fall back later.
                events = []
                message_text = completed.stdout.strip()
                break

            events.append(event)

            # Common event shapes may use "item.type" similar to Codex. Accept
            # either 'agent_message' or 'assistant_message'.
            item = event.get("item")
            if item and item.get("type") in ("agent_message", "assistant_message"):
                message_text = item.get("text", "")

            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})

        if message_text is None:
            # If we parsed no events and there is raw stdout, use that.
            message_text = completed.stdout.strip()

        return CopilotResult(message=message_text, events=events, usage=usage)
