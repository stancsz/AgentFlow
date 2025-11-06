# AgentFlow Adapters Guide

AgentFlow CLI supports multiple adapters for executing agent tasks. Choose the adapter that fits your environment and requirements.

## Available Adapters

### 1. Mock Adapter (for testing/demos)
**No external dependencies required** — returns canned responses.

**Use when:**
- Testing the CLI and viewer without external APIs
- Creating demo artifacts for documentation
- Running unit/integration tests

**Usage:**
```powershell
# Set adapter to mock
$env:AGENTFLOW_ADAPTER = "mock"
$env:OPENAI_API_KEY = "test"  # dummy key

# Run CLI
agentflow "Create a simple flow that says hello"
# or
python -m agentflow.cli "Create a simple flow that says hello"
```

**Features:**
- Generates synthetic flow specs for prompts mentioning "flow" or "workflow"
- Returns simple text responses for other prompts
- Includes mock usage metrics (tokens)
- No network calls or external CLI required

---

### 2. Codex CLI Adapter (default)
**Requires:** Codex CLI installed and OPENAI_API_KEY

**Use when:**
- You have the Codex CLI binary available
- You want to use OpenAI models via Codex

**Usage:**
```powershell
# Set paths (optional if codex is on PATH)
$env:AGENTFLOW_CODEX_PATH = "C:\path\to\codex.exe"  # or codex.cmd
$env:AGENTFLOW_CODEX_MODEL = "gpt-4"  # optional, default: gpt-5-mini
$env:OPENAI_API_KEY = "sk-..."

# Codex is the default adapter, no need to set AGENTFLOW_ADAPTER
agentflow "Your prompt here"
```

**Configuration:**
- `AGENTFLOW_CODEX_PATH` — path to Codex CLI binary (default: `codex.cmd`)
- `AGENTFLOW_CODEX_MODEL` — model to use (default: `gpt-5-mini`)
- `OPENAI_API_KEY` — required for authentication

---

### 3. Copilot CLI Adapter
**Requires:** GitHub Copilot CLI installed

**Use when:**
- You have GitHub Copilot CLI available
- You prefer Copilot over Codex

**Usage:**
```powershell
# Set adapter to copilot
$env:AGENTFLOW_ADAPTER = "copilot"

# Set paths (optional if copilot is on PATH)
$env:AGENTFLOW_COPILOT_PATH = "C:\path\to\copilot.exe"  # default: copilot
$env:AGENTFLOW_COPILOT_TOKEN = "ghp_..."  # optional auth token
$env:OPENAI_API_KEY = "test"  # dummy value to satisfy config

# Run CLI
agentflow "Your prompt here"
```

**Configuration:**
- `AGENTFLOW_COPILOT_PATH` — path to Copilot CLI binary (default: `copilot`)
- `AGENTFLOW_COPILOT_TOKEN` — optional token injected as `COPILOT_TOKEN` env var

---

## Adapter Selection

The CLI reads the `AGENTFLOW_ADAPTER` environment variable to choose which adapter to use:

| Adapter | Environment Variable Value |
|---------|---------------------------|
| Codex (default) | `codex` or unset |
| Copilot | `copilot` |
| Mock | `mock` |

**Example: switch between adapters**
```powershell
# Use mock for testing
$env:AGENTFLOW_ADAPTER = "mock"
agentflow "test prompt"

# Switch to Copilot
$env:AGENTFLOW_ADAPTER = "copilot"
agentflow "real prompt"

# Switch back to default (Codex)
Remove-Item Env:AGENTFLOW_ADAPTER
agentflow "another prompt"
```

---

## Common Tasks

### Generate a test artifact with mock adapter
```powershell
$env:AGENTFLOW_ADAPTER = "mock"
$env:OPENAI_API_KEY = "test"
python -m agentflow.cli "Create a workflow with 3 steps"
```

### View artifacts in the web UI
```powershell
# Start viewer (serves current directory on port 5050)
python -m agentflow.cli view --directory . --host 127.0.0.1 --port 5050

# Open http://127.0.0.1:5050 in your browser
```

### Run with a specific Copilot CLI
```powershell
$env:AGENTFLOW_ADAPTER = "copilot"
$env:AGENTFLOW_COPILOT_PATH = "D:\tools\copilot\copilot.exe"
$env:OPENAI_API_KEY = "test"
python -m agentflow.cli "Generate a Python function to sort a list"
```

---

## Adapter Implementation Details

All adapters implement the same interface:
- `__init__(settings: Settings, extra_args: Optional[Iterable[str]] = None)`
- `run(prompt: str, timeout: int = 120, cwd: Optional[str] = None) -> Result`

**Result dataclass:**
- `message: str` — assistant's text response
- `events: List[Dict]` — JSONL event list (if any)
- `usage: Dict` — token usage metrics

See `src/agentflow/adapters/` for implementation details.
