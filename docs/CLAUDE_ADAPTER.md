# Claude CLI Adapter for AgentFlow

## Overview

The Claude CLI adapter enables AgentFlow to execute agent tasks using Anthropic's Claude models via the `anthropic` CLI tool. This adapter follows the same interface pattern as the existing Codex adapter, allowing seamless switching between backends.

## Installation

1. Install the Anthropic CLI:
```bash
npm install -g anthropic
```

2. Set your API key:
```bash
set ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Basic Execution

Run AgentFlow with the Claude adapter:

```bash
py -3 -m agentflow.cli --adapter claude "Analyze the adapter pattern in this repository."
```

### Configuration Options

Configure Claude adapter behavior via environment variables:

```bash
# Path to the anthropic CLI (default: "anthropic")
set AGENTFLOW_ANTHROPIC_PATH=anthropic

# Model selection (default: "claude-3-5-sonnet-latest")
set AGENTFLOW_ANTHROPIC_MODEL=claude-3-5-sonnet-latest

# Max tokens for responses (default: 1024)
set AGENTFLOW_ANTHROPIC_MAX_TOKENS=2048
```

### Switching Between Adapters

You can mix Codex and Claude runs in the same workspace:

```bash
# Run with Codex (default)
py -3 -m agentflow.cli "Task A using GPT"

# Run with Claude
py -3 -m agentflow.cli --adapter claude "Task B using Claude"
```

Both will generate standard AgentFlow YAML artifacts viewable in the same viewer.

## Testing

### Unit Tests

```bash
py -3 -m pytest tests/unit/test_claude_adapter.py -v
```

### Live Integration Test

Requires `ANTHROPIC_API_KEY` to be set:

```bash
py -3 -m pytest tests/live/test_claude_adapter_live.py -m live
```

## Architecture

### Module Structure

- `src/agentflow/adapters/claude_cli.py` - Main adapter implementation
- `src/agentflow/adapters/__init__.py` - Exports and adapter registry
- `src/agentflow/config.py` - Configuration management with Anthropic settings
- `src/agentflow/cli.py` - CLI with `--adapter` flag support

### Adapter Registry

The `ADAPTERS` dictionary in `adapters/__init__.py` maps adapter names to classes:

```python
ADAPTERS = {
    "codex": CodexCLIAdapter,
    "claude": ClaudeCLIAdapter,
}
```

This allows easy extension with future adapters (e.g., OpenAI direct API, local models).

### Response Format

ClaudeResult mirrors CodexResult structure:

```python
@dataclass(slots=True)
class ClaudeResult:
    message: str      # Extracted assistant text
    events: List[Dict]  # Currently empty; reserved for future event capture
    usage: Dict       # Token usage from API response
```

## Example Output

Running with Claude generates a standard plan artifact:

```yaml
schema_version: 1.0
plan_id: "plan-20251105..."
name: "Ad-hoc Claude execution"
status: completed
nodes:
  - id: claude_execution
    type: agent
    outputs:
      message: "..." # Claude's response
      evaluation:
        score: 0.92
        justification: "..."
    metrics:
      usage:
        input_tokens: 850
        output_tokens: 320
```

See `_PRD/example-flow-claude.yml` for a complete example.

## Differences from Codex Adapter

| Feature | Codex Adapter | Claude Adapter |
|---------|---------------|----------------|
| CLI Tool | `codex exec` | `anthropic messages create` |
| Event Stream | JSONL streaming | Single JSON response |
| Default Model | gpt-5-mini | claude-3-5-sonnet-latest |
| Max Tokens | Not configurable | Configurable via `--max-tokens` |

## Future Enhancements

- **Event Capture**: Parse Claude's streaming output for granular events
- **Tool Use**: Support Claude's native tool/function calling
- **Multi-turn**: Enable conversation history for multi-step workflows
- **Prompt Caching**: Leverage Claude's prompt caching for cost optimization
