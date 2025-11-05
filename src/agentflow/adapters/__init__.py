"""
Adapter implementations that integrate external systems with AgentFlow.
"""

from .codex_cli import CodexCLIAdapter, CodexCLIError, CodexResult
from .copilot_cli import CopilotCLIAdapter, CopilotCLIError, CopilotResult
from .mock_adapter import MockAdapter, MockAdapterError, MockResult
from .claude_cli import ClaudeCLIAdapter, ClaudeCLIError, ClaudeResult

# Simple registry for CLI-selectable adapters
ADAPTERS = {
    "codex": CodexCLIAdapter,
    "copilot": CopilotCLIAdapter,
    "mock": MockAdapter,
    "claude": ClaudeCLIAdapter,
}

__all__ = [
    "CodexCLIAdapter",
    "CodexCLIError",
    "CodexResult",
    "CopilotCLIAdapter",
    "CopilotCLIError",
    "CopilotResult",
    "MockAdapter",
    "MockAdapterError",
    "MockResult",
    "ClaudeCLIAdapter",
    "ClaudeCLIError",
    "ClaudeResult",
    "ADAPTERS",
]
