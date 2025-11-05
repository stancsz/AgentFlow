"""
Claude (Anthropic) CLI adapter.

Executes the `anthropic messages create` command headlessly, parses JSON output, and exposes the
final assistant message plus usage. This adapter is designed to be embedded inside
the AgentFlow runner to execute agent tasks declaratively from the plan YAML.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from agentflow.config import Settings


class ClaudeCLIError(RuntimeError):
    """Raised when the Anthropic CLI returns a non-zero exit code or emits invalid output."""


@dataclass(slots=True)
class ClaudeResult:
    """Structured representation of a Claude execution."""

    message: str
    events: List[Dict]
    usage: Dict


class ClaudeCLIAdapter:
    """
    Thin wrapper around the Anthropic CLI `messages create` command.

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
        
        # Check if using Python wrapper script
        if self._settings.anthropic_cli_path.endswith("python.exe") or self._settings.anthropic_cli_path == "python":
            # Use the wrapper script in the repo root
            import pathlib
            repo_root = pathlib.Path(__file__).parent.parent.parent.parent
            wrapper_script = repo_root / "anthropic_cli_wrapper.py"
            
            command = [
                self._settings.anthropic_cli_path,
                str(wrapper_script),
                "messages",
                "create",
                "-m",
                self._settings.anthropic_model,
                "--max-tokens",
                str(self._settings.anthropic_max_tokens),
                "--json",
            ]
        else:
            # Standard CLI command
            command = [
                self._settings.anthropic_cli_path,
                "messages",
                "create",
                "-m",
                self._settings.anthropic_model,
                "--max-tokens",
                str(self._settings.anthropic_max_tokens),
                "--json",
            ]
        
        command.extend(self._extra_args)
        return command

    def run(
        self,
        prompt: str,
        *,
        timeout: int = 120,
        cwd: Optional[str] = None,
    ) -> ClaudeResult:
        """
        Execute Claude with the supplied prompt and return the parsed response.

        Raises
        ------
        ClaudeCLIError
            When the CLI exits with a non-zero status or the output cannot be parsed.
        """

        if not (self._settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")):
            raise ClaudeCLIError(
                "ANTHROPIC_API_KEY must be set in the environment or Settings for Claude adapter."
            )

        env = os.environ.copy()
        # Only set if provided to avoid overriding an already-exported value
        if self._settings.anthropic_api_key:
            env["ANTHROPIC_API_KEY"] = self._settings.anthropic_api_key

        # Anthropic CLI expects the prompt as -p/--prompt argument.
        command = self.build_base_command() + ["-p", prompt]

        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=cwd,
        )

        if completed.returncode != 0:
            raise ClaudeCLIError(
                f"Anthropic CLI exited with {completed.returncode}: {completed.stderr.strip()}"
            )

        stdout = (completed.stdout or "").strip()
        if not stdout:
            raise ClaudeCLIError("Anthropic CLI produced no output.")

        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise ClaudeCLIError(f"Failed to parse Anthropic JSON response: {exc}") from exc

        # Extract assistant text from content array
        message_text_parts: List[str] = []
        usage: Dict = {}

        if isinstance(payload, dict):
            # Usage is typically under payload["usage"]
            usage = payload.get("usage", {}) or {}
            content = payload.get("content")
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if (block.get("type") or "").lower() == "text":
                        text = block.get("text")
                        if isinstance(text, str) and text.strip():
                            message_text_parts.append(text.strip())

        message_text = "\n\n".join(message_text_parts).strip()
        if not message_text:
            # Some CLI responses may nest content deeper or label differently; provide a fallback.
            candidate = payload.get("message") if isinstance(payload, dict) else None
            if isinstance(candidate, str) and candidate.strip():
                message_text = candidate.strip()

        if not message_text:
            raise ClaudeCLIError("Anthropic CLI response did not contain assistant text content.")

        return ClaudeResult(message=message_text, events=[], usage=usage)
