"""
Gemini CLI adapter.

Thin wrapper around a hypothetical Gemini CLI. Mirrors the Codex/Copilot
adapter interface used by AgentFlow: exposes a .run(prompt) method that
returns a GeminiResult(message, events, usage) and raises GeminiCLIError on
failure.

The adapter attempts to parse JSONL event lines emitted on stdout. If no
JSON events are present it falls back to returning the raw stdout as the
assistant message.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from agentflow.config import Settings


class GeminiCLIError(RuntimeError):
    """Raised when the Gemini CLI returns a non-zero exit code or emits invalid output."""


@dataclass(slots=True)
class GeminiResult:
    """Structured representation of a Gemini execution."""

    message: str
    events: List[Dict]
    usage: Dict


class GeminiCLIAdapter:
    """
    Wrapper around a Gemini CLI command.

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
        """Construct the CLI command prior to adding the prompt.

        Honors optional Settings overrides when present (model, max tokens).
        """

        cli_path = getattr(self._settings, "gemini_cli_path", "gemini")
        # Conservative default invocation; real CLIs may differ. Keep flags
        # minimal and allow extra_args to customize behavior in tests.
        command = [cli_path, "chat", "--json"]

        # Optionally include model and max tokens if provided in Settings.
        model = getattr(self._settings, "gemini_model", None)
        if model:
            command += ["--model", str(model)]

        max_tokens = getattr(self._settings, "gemini_max_output_tokens", None)
        if isinstance(max_tokens, int) and max_tokens > 0:
            command += ["--max-output-tokens", str(max_tokens)]

        command.extend(self._extra_args)
        return command

    def run(
        self,
        prompt: str,
        *,
        timeout: int = 120,
        cwd: Optional[str] = None,
    ) -> GeminiResult:
        """
        Execute Gemini with the supplied prompt and return the parsed response.

        The method attempts to parse JSONL event lines from stdout. If parsing
        yields no assistant message events, the raw stdout is returned as the
        message. Raises GeminiCLIError on non-zero exit or parse failures.
        """

        env = os.environ.copy()

        # If the settings provide a Gemini API key, inject it into the
        # environment so the CLI can pick it up. Use a conservative env name
        # which can be overridden by the Settings if needed.
        gemini_key = getattr(self._settings, "gemini_api_key", None)
        if gemini_key:
            env["GEMINI_API_KEY"] = gemini_key

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
            raise GeminiCLIError(f"Gemini CLI exited with {completed.returncode}: {completed.stderr.strip()}")

        events: List[Dict] = []
        message_text: Optional[str] = None
        usage: Dict = {}

        for line in completed.stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Non-JSON output; fall back to raw stdout
                events = []
                message_text = completed.stdout.strip()
                break

            events.append(event)

            item = event.get("item")
            if item and item.get("type") in ("assistant_message", "agent_message"):
                message_text = item.get("text", "")

            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})

        if message_text is None:
            message_text = completed.stdout.strip()

        return GeminiResult(message=message_text, events=events, usage=usage)
