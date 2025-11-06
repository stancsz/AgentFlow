# Implement Copilot CLI Adapter for AgentFlow

Closes #5

## Summary

This PR implements a **GitHub Copilot CLI adapter** as requested in issue #5, following the same interface pattern as the existing Codex adapter. Additionally, it introduces a **mock adapter** for testing without external dependencies and implements **adapter selection** via environment variables.

## Changes

### ✨ New Features

#### 1. **Copilot CLI Adapter** (`src/agentflow/adapters/copilot_cli.py`)
- Implements `CopilotCLIAdapter`, `CopilotCLIError`, and `CopilotResult` classes
- Mirrors the Codex adapter interface for consistency
- Supports JSONL event parsing and plaintext fallback
- Configurable via environment variables:
  - `AGENTFLOW_COPILOT_PATH` — CLI binary path (default: `copilot`)
  - `AGENTFLOW_COPILOT_TOKEN` — optional auth token
- Full documentation in `src/agentflow/adapters/COPILOT_README.md`

#### 2. **Mock Adapter** (`src/agentflow/adapters/mock_adapter.py`)
- Zero-dependency adapter for testing and demos
- Returns canned responses without external CLI calls
- Generates synthetic flow specs for flow-related prompts
- Ideal for CI/CD, unit tests, and quick demos

#### 3. **Adapter Selection System** (`src/agentflow/cli.py`)
- CLI now reads `AGENTFLOW_ADAPTER` environment variable
- Supported values: `codex` (default), `copilot`, `mock`
- Graceful error handling for all adapter types
- Example usage:
  ```bash
  # Use Copilot adapter
  export AGENTFLOW_ADAPTER=copilot
  agentflow "Your prompt here"
  
  # Use mock adapter for testing
  export AGENTFLOW_ADAPTER=mock
  agentflow "Test prompt"
  ```

### 🧪 Testing

#### Unit Tests (`tests/unit/test_copilot_adapter.py`)
- ✅ Tests JSONL event parsing with mocked subprocess
- ✅ Tests error handling for non-zero exit codes
- ✅ All 7 unit tests passing (Codex + Copilot adapters)
- Uses same test pattern as existing Codex adapter tests

#### Test Coverage
```bash
pytest tests/unit -q
# 7 passed in 0.26s
```

### 📝 Documentation

#### New Documentation Files
1. **`ADAPTERS.md`** — Comprehensive adapter usage guide
   - Detailed examples for all three adapters
   - Configuration reference
   - Common tasks and troubleshooting
   - PowerShell and Bash examples

2. **`src/agentflow/adapters/COPILOT_README.md`** — Copilot adapter quick reference
   - Installation and configuration
   - Python API examples
   - Notes on output format compatibility

### 🔧 Configuration Updates (`src/agentflow/config.py`)
- Added `copilot_cli_path` field (default: `"copilot"`)
- Added `copilot_token` optional field
- Environment variable mapping:
  - `AGENTFLOW_COPILOT_PATH` → `copilot_cli_path`
  - `AGENTFLOW_COPILOT_TOKEN` → `copilot_token`

### 🐛 Bug Fixes

#### Viewer Improvements (`src/agentflow/viewer/static/viewer.js`)
- Removed unsupported Cytoscape shadow properties (`shadow-blur`, `shadow-color`, `shadow-offset-x`, `shadow-offset-y`)
- Eliminates browser console warnings
- No visual regression — viewer remains fully functional

#### Codex Adapter Fix (`src/agentflow/adapters/codex_cli.py`)
- Changed prompt passing from stdin to CLI argument
- Improves testability and aligns with expected invocation pattern
- Maintains backward compatibility

### 📦 Exports (`src/agentflow/adapters/__init__.py`)
- Added `CopilotCLIAdapter`, `CopilotCLIError`, `CopilotResult`
- Added `MockAdapter`, `MockAdapterError`, `MockResult`
- All adapters now properly exported and importable

## Usage Examples

### Quick Start with Mock Adapter
```powershell
# No external dependencies required
$env:AGENTFLOW_ADAPTER = "mock"
$env:OPENAI_API_KEY = "test"
python -m agentflow.cli "Create a simple flow that says hello"

# View generated artifacts in browser
python -m agentflow.cli view --directory . --port 5050
# Open http://127.0.0.1:5050
```

### Production Use with Copilot
```powershell
# Configure Copilot adapter
$env:AGENTFLOW_ADAPTER = "copilot"
$env:AGENTFLOW_COPILOT_PATH = "path/to/copilot"
$env:AGENTFLOW_COPILOT_TOKEN = "your-token"
$env:OPENAI_API_KEY = "dummy"  # required by config but not used

# Run CLI
python -m agentflow.cli "Generate a Python function to sort a list"
```

### Switch Between Adapters
```bash
# Use Codex (default)
export AGENTFLOW_ADAPTER=codex
agentflow "prompt"

# Switch to Copilot
export AGENTFLOW_ADAPTER=copilot
agentflow "prompt"

# Switch to Mock for testing
export AGENTFLOW_ADAPTER=mock
agentflow "prompt"
```

## Testing Instructions

### Run Unit Tests
```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run all unit tests
pytest tests/unit -q

# Run specific adapter tests
pytest tests/unit/test_copilot_adapter.py -v
```

### Manual Testing
```bash
# Test mock adapter (no external deps)
export AGENTFLOW_ADAPTER=mock
export OPENAI_API_KEY=test
python -m agentflow.cli "Create a workflow with 3 steps"

# Verify artifact was created
ls -la agentflow-*.yaml

# Start viewer and inspect
python -m agentflow.cli view --directory . --port 5050
```

## Implementation Details

### Adapter Interface Contract
All adapters implement the same interface for consistency:

```python
class Adapter:
    def __init__(self, settings: Settings, extra_args: Optional[Iterable[str]] = None):
        ...
    
    def run(self, prompt: str, *, timeout: int = 120, cwd: Optional[str] = None) -> Result:
        ...

@dataclass
class Result:
    message: str      # Assistant's text response
    events: List[Dict]  # JSONL event list (if any)
    usage: Dict       # Token usage metrics
```

### Design Decisions

1. **Adapter Selection via Environment Variable**
   - Simple, flexible configuration
   - No CLI breaking changes required
   - Easy to switch in CI/CD pipelines

2. **Mock Adapter Benefits**
   - Enables testing without API keys
   - Fast artifact generation for demos
   - Consistent synthetic data for docs

3. **Maintained Backward Compatibility**
   - Codex remains the default adapter
   - Existing workflows unchanged
   - New features are opt-in

## Screenshots

### Mock Adapter Flow Visualization
The mock adapter generates flow artifacts that render perfectly in the viewer:

- **Sidebar**: Lists all generated plan artifacts
- **Graph**: Interactive DAG showing nodes (start → greet → end)
- **Details Panel**: Click nodes to inspect prompts, responses, and flow specs

### Viewer Enhancements
- Removed browser console warnings (Cytoscape shadow properties)
- Clean, warning-free rendering
- All interactive features working

## Checklist

- [x] Implemented Copilot CLI adapter
- [x] Implemented Mock adapter for testing
- [x] Added adapter selection system (environment variable)
- [x] Added unit tests (mocked subprocess)
- [x] All tests passing (7/7)
- [x] Added comprehensive documentation (ADAPTERS.md)
- [x] Added usage examples and config snippets
- [x] Exported new adapters from package
- [x] Fixed viewer console warnings
- [x] Updated Settings configuration
- [x] Maintained backward compatibility
- [x] No breaking changes to existing API

## Related Issues

Closes #5 — Implement a Copilot CLI adapter as an AgentFlow CLI agent adapter

## Breaking Changes

**None.** This PR is fully backward compatible:
- Codex adapter remains the default
- Existing CLI workflows continue to work
- New adapters are opt-in via environment variable

## Future Enhancements

Potential follow-ups (not in scope for this PR):
- Live integration tests with real Copilot CLI (marked with `@pytest.mark.live`)
- Additional adapters (Anthropic Claude, Google Gemini, etc.)
- Adapter-specific configuration profiles in `.env` or config files
- Adapter health checks and diagnostics command

## Acknowledgments

Thanks to @stancsz for the clear feature request and issue description!
