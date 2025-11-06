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

    openai_api_key: str
    codex_cli_path: str = "codex.cmd"
    model: str = "gpt-5-mini"
    sandbox_mode: str = "workspace-write"
    approval_policy: str = "on-request"
    copilot_cli_path: str = "copilot"
    copilot_token: Optional[str] = None

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

        api_key = environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError("OPENAI_API_KEY must be set in the environment or .env file.")

        cli_path = environ.get("AGENTFLOW_CODEX_PATH", "codex.cmd")
        model = environ.get("AGENTFLOW_CODEX_MODEL", "gpt-5-mini")
        sandbox = environ.get("AGENTFLOW_SANDBOX", "workspace-write")
        approval = environ.get("AGENTFLOW_APPROVAL_POLICY", "on-request")
        copilot_path = environ.get("AGENTFLOW_COPILOT_PATH", "copilot")
        copilot_token = environ.get("AGENTFLOW_COPILOT_TOKEN")

        return cls(
            openai_api_key=api_key,
            codex_cli_path=cli_path,
            model=model,
            sandbox_mode=sandbox,
            approval_policy=approval,
            copilot_cli_path=copilot_path,
            copilot_token=copilot_token,
        )
