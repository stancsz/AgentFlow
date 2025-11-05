"""
Configuration management for AgentFlow utilities.

Loads environment variables from `.env` and exposes strongly-typed settings used by
CLI adapters and runners.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Container for runtime configuration."""

    # OpenAI/Codex
    openai_api_key: Optional[str] = None
    codex_cli_path: str = "codex.cmd"
    model: str = "gpt-5-mini"
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "on-request"
    copilot_cli_path: str = "copilot"
    copilot_token: Optional[str] = None

    # Anthropic/Claude
    anthropic_api_key: Optional[str] = None
    anthropic_cli_path: str = "anthropic"
    anthropic_model: str = "claude-3-5-sonnet-latest"
    anthropic_max_tokens: int = 1024

    @classmethod
    def from_env(
        cls,
        env_file: Optional[Path] = None,
    ) -> "Settings":
        """
        Load settings from environment variables (optionally forcing a specific .env file).

        Parameters
        ----------
        env_file:
            Optional path to an alternate `.env` file. When provided the file is loaded explicitly.

        Returns
        -------
        Settings
            Parsed settings instance.
        """

        if env_file:
            load_dotenv(dotenv_path=env_file, override=True)

        from os import environ

        # Load both providers keys if present; actual adapter will validate.
        openai_api_key = environ.get("OPENAI_API_KEY")
        anthropic_api_key = environ.get("ANTHROPIC_API_KEY")

        cli_path = environ.get("AGENTFLOW_CODEX_PATH", "codex.cmd")
        model = environ.get("AGENTFLOW_CODEX_MODEL", "gpt-5-mini")
        sandbox = environ.get("AGENTFLOW_SANDBOX", "workspace-write")
        approval = environ.get("AGENTFLOW_APPROVAL_POLICY", "on-request")
        copilot_path = environ.get("AGENTFLOW_COPILOT_PATH", "copilot")
        copilot_token = environ.get("AGENTFLOW_COPILOT_TOKEN")

        anthropic_cli = environ.get("AGENTFLOW_ANTHROPIC_PATH", "anthropic")
        anthropic_model = environ.get("AGENTFLOW_ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
        try:
            anthropic_max_tokens = int(environ.get("AGENTFLOW_ANTHROPIC_MAX_TOKENS", "1024"))
        except ValueError:
            anthropic_max_tokens = 1024

        return cls(
            openai_api_key=openai_api_key,
            codex_cli_path=cli_path,
            model=model,
            sandbox_mode=sandbox,
            approval_policy=approval,
            copilot_cli_path=copilot_path,
            copilot_token=copilot_token,
            anthropic_api_key=anthropic_api_key,
            anthropic_cli_path=anthropic_cli,
            anthropic_model=anthropic_model,
            anthropic_max_tokens=anthropic_max_tokens,
        )
