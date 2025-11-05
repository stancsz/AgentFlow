"""
Codex CLI adapter.

Executes the `codex exec` command headlessly, parses JSONL event output, and exposes the
final assistant message plus telemetry. This adapter is designed to be embedded inside
the AgentFlow runner to execute agent tasks declaratively from the plan YAML.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from agentflow.config import Settings


class CodexCLIError(RuntimeError):
    """Raised when the Codex CLI returns a non-zero exit code or emits invalid output."""


@dataclass(slots=True)
class CodexResult:
    """Structured representation of a Codex execution."""

    message: str
    events: List[Dict]
    usage: Dict


class CodexCLIAdapter:
    """
    Thin wrapper around the Codex CLI `exec` command.

    Parameters
    ----------
    settings:
        Injected Settings instance controlling authentication, model selection, and execution policy.
    extra_args:
        Optional iterable of additional CLI flags supplied to each invocation.
    """

    def __init__(self, settings: Settings, extra_args: Optional[Iterable[str]] = None) -> None:
        self._settings = settings
        self._extra_args = list(extra_args or [])

    def build_base_command(self) -> List[str]:
        """Construct the CLI command prior to adding the prompt."""

        command = [
            self._settings.codex_cli_path,
            "exec",
            "--model",
            self._settings.model,
            "--json",
            "--sandbox",
            self._settings.sandbox_mode,
        ]
        command.extend(self._extra_args)
        return command

    def run(
        self,
        prompt: str,
        *,
        timeout: int = 120,
        cwd: Optional[str] = None,
    ) -> CodexResult:
        """
        Execute Codex with the supplied prompt and return the parsed response.

        Raises
        ------
        CodexCLIError
            When the CLI exits with a non-zero status or the output cannot be parsed.
        """

        if not (self._settings.openai_api_key or os.environ.get("OPENAI_API_KEY")):
            raise CodexCLIError(
                "OPENAI_API_KEY must be set in the environment or Settings for Codex adapter."
            )

        env = os.environ.copy()
        if self._settings.openai_api_key:
            env["OPENAI_API_KEY"] = self._settings.openai_api_key

        # Pass the prompt as the final CLI argument for easier testing and
        # to match the expected invocation shape used across the test suite.
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
            raise CodexCLIError(
                f"Codex CLI exited with {completed.returncode}: {completed.stderr.strip()}"
            )

        events: List[Dict] = []
        message_text: Optional[str] = None
        usage: Dict = {}

        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise CodexCLIError(f"Failed to parse Codex JSON event: {exc}") from exc

            events.append(event)

            item = event.get("item")
            if item and item.get("type") == "agent_message":
                message_text = item.get("text", "")

            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})

        if message_text is None:
            raise CodexCLIError("Codex CLI completed without emitting an agent_message event.")

        return CodexResult(message=message_text, events=events, usage=usage)
