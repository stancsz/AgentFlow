"""
Adapter implementations that integrate external systems with AgentFlow.
"""

from .codex_cli import CodexCLIAdapter, CodexCLIError, CodexResult
from .copilot_cli import CopilotCLIAdapter, CopilotCLIError, CopilotResult
from .mock_adapter import MockAdapter, MockAdapterError, MockResult

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
]