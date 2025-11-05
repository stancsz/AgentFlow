# Implement Claude CLI Adapter for AgentFlow

Closes: — (no linked issue)

## Summary
This PR implements an Anthropic Claude CLI adapter for AgentFlow, following the same adapter interface used by Codex. It also includes a lightweight wrapper with a mock mode for testing without external dependencies. Adapter selection is handled via a CLI flag.

Benefits
- Multi‑provider support (Claude + Codex)
- Mock mode for fast, cost‑free local testing and CI
- Web viewer compatibility (artifacts render in UI)
- Backward‑compatible (no breaking changes)

---

## Changes

### ✨ New Features

#### 1) Claude CLI Adapter (`src/agentflow/adapters/claude_cli.py`)
- Implements `ClaudeCLIAdapter`, `ClaudeCLIError`, `ClaudeResult`
- JSON response parsing with text extraction and usage metrics
- Robust subprocess error handling; helpful error messages

#### 2) Anthropic Wrapper (`anthropic_cli_wrapper.py`)
- Python wrapper providing CLI‑like behavior
- Intelligent mock mode (auto‑enabled if API key missing/placeholder)
- Contextual responses for predictable tests and demos

#### 3) Adapter Selection (`src/agentflow/cli.py`)
- Adds `--adapter` flag (`codex` | `claude`)
- Preserves existing Codex flow; no behavior change when flag omitted

### 🔧 Configuration Updates (`src/agentflow/config.py`)
- Adds Anthropic fields: `anthropic_api_key`, `anthropic_cli_path`, `anthropic_model`, `anthropic_max_tokens`
- Environment variables: `ANTHROPIC_API_KEY`, `AGENTFLOW_ANTHROPIC_PATH`
- OpenAI API key now optional to support Claude‑only workflows

### 📝 Documentation
- `docs/CLAUDE_ADAPTER.md` — setup, configuration, examples, troubleshooting
- `_PRD/example-flow-claude.yml` — example plan

---

## Usage Examples

### Quick Start with Mock Mode (no external deps)
```powershell
py -m agentflow.cli --adapter claude "Create a user authentication flow"

py -m agentflow.cli view --port 5050
# Open http://127.0.0.1:5050
```

### Production Use with Claude
```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-api03-..."
$env:AGENTFLOW_ANTHROPIC_PATH = "D:\\AgentFlow\\anthropic_cli_wrapper.py"
py -m agentflow.cli --adapter claude "Create a user authentication flow"
```

### Switch Between Adapters
```powershell
py -m agentflow.cli --adapter codex  "prompt with codex"
py -m agentflow.cli --adapter claude "prompt with claude"
```

---

## Testing Instructions

### Run Unit Tests
```powershell
pytest tests/unit -v
# Expect: 7 passed
```

### Manual Testing
```powershell
py -m agentflow.cli --adapter claude "Create a sample 3‑step workflow"
Get-ChildItem .\agentflow-*.yaml

py -m agentflow.cli view --port 5050
# Open http://127.0.0.1:5050 and inspect artifacts
```

---

## Implementation Details

### Adapter Interface Contract
```python
class Adapter:
	def __init__(self, settings, extra_args=None):
		...

	def run(self, prompt: str, *, timeout: int = 120, cwd=None) -> "Result":
		...

@dataclass
class Result:
	message: str
	events: list
	usage: dict
```

### Design Decisions
1. Mock mode: enables CI and local demos without API keys or costs
2. Backward compatibility: Codex remains default; `--adapter` is opt‑in
3. Wrapper approach: isolates Anthropic specifics; keeps CLI simple

---

## Screenshots
Viewer renders generated plans (sidebar list, details pane). Artifacts include messages, steps, and token usage. — (No image attached)

---

## Checklist
- [x] Implemented Claude adapter and wrapper
- [x] Added `--adapter` flag; registry wiring
- [x] Updated config with Anthropic fields and ENV vars
- [x] Added documentation and example flow
- [x] Unit tests added; all tests passing (7/7)
- [x] No breaking changes; Codex remains functional

---

## Files Changed (13, +781/−18)
New: `src/agentflow/adapters/claude_cli.py`, `anthropic_cli_wrapper.py`, `docs/CLAUDE_ADAPTER.md`, `tests/unit/test_claude_adapter.py`, `tests/live/test_claude_adapter_live.py`, `_PRD/example-flow-claude.yml`

Modified: `src/agentflow/adapters/__init__.py`, `src/agentflow/cli.py`, `src/agentflow/config.py`, `README.md`, `tests/unit/test_cli.py`, `tests/unit/test_codex_adapter.py`

---

## Breaking Changes
None. Fully backward‑compatible.

## Future Enhancements
- Live integration tests against real Anthropic API
- Adapter profile presets via config files
- Additional adapters (e.g., Gemini) following the same pattern

## Acknowledgments
Thanks to maintainers for the adapter pattern and viewer foundation that made this addition straightforward.
