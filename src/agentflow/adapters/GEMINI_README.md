Gemini CLI adapter
==================

This adapter provides a lightweight wrapper around a Gemini-style CLI for use
with AgentFlow CLI agents. It mirrors the existing Codex and Copilot adapters
and expects the CLI to optionally emit JSONL event lines on stdout.

Configuration
-------------

Set environment variables (or place them in a `.env` file) to configure the
adapter:

- `AGENTFLOW_GEMINI_PATH`: Path to the Gemini CLI binary (default: `gemini`).
- `AGENTFLOW_GEMINI_API_KEY`: Optional API key injected into the `GEMINI_API_KEY`
  environment variable for the CLI.
- `AGENTFLOW_GEMINI_MODEL`: Optional model name passed as `--model`.
- `AGENTFLOW_GEMINI_MAX_TOKENS`: Optional integer; when set adds `--max-output-tokens`.

Usage
-----

Example `.env` snippet:

AGENTFLOW_GEMINI_PATH=gemini
AGENTFLOW_GEMINI_API_KEY=ya29.xxx
AGENTFLOW_GEMINI_MODEL=gemini-1.5-flash
AGENTFLOW_GEMINI_MAX_TOKENS=512

The adapter exposes a simple `run(prompt)` method which returns a result
object with the fields `message`, `events`, and `usage`.

Note
----

The Gemini CLI invocation (subcommand/flags) used by this adapter is minimal
(`chat --json`) and intended to be overridden using the `extra_args` argument
when initializing the adapter if your CLI uses a different invocation shape. If
`AGENTFLOW_GEMINI_MODEL` or `AGENTFLOW_GEMINI_MAX_TOKENS` are set they are
included automatically.
