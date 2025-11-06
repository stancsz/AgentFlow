Copilot CLI adapter
===================

This module provides a thin Copilot CLI adapter for use with the AgentFlow CLI.

Usage
-----

Configure an optional path or token via environment variables (recommended in a .env file):

- AGENTFLOW_COPILOT_PATH - path to the Copilot CLI binary (default: copilot)
- AGENTFLOW_COPILOT_TOKEN - token injected as COPILOT_TOKEN into the environment for CLI auth

Example
-------

In Python:

from agentflow.config import Settings
from agentflow.adapters import CopilotCLIAdapter

settings = Settings.from_env()
adapter = CopilotCLIAdapter(settings)
result = adapter.run("Say hello")

The adapter returns a CopilotResult with fields: message, events, usage.

Notes
-----
The Copilot CLI has many possible output formats. This adapter attempts to parse
JSONL event lines but falls back to returning the raw stdout as the assistant
message when no JSON events are detected.
