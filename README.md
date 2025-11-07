# AgentFlow

**Teaching AI to learn how to learn — by autonomously creating its own LangGraphs.**

AgentFlow rethinks agent orchestration. Instead of hand-written prompt chains, we ask the agent to draft _LangGraphs_ — directed workflows with branches, loops, and evaluation hooks. Each run becomes a rich artifact that captures source prompts, tool outputs, self-evaluations, and the synthetic graph structure that the agent just invented. Those artifacts feed a viewer, tests, and metrics that make it easier to iterate toward domain-specific agentic systems.

<img width="1237" height="887" alt="AgentFlow viewer" src="https://github.com/user-attachments/assets/c5fd8103-5e81-474c-be03-d05a2bbd39aa" />

## Why AgentFlow

Modern agent workflows span tools, retries, and backtracking, yet most planners still emit linear prompt chains. That leaves operators guessing about _what_ ran and _why_. AgentFlow closes that gap by standardising on a canonical YAML artifact that survives from planning through execution while layering on:

- **Autonomous LangGraph generation** – the agent itself proposes nodes, branches, and loop constructs. We persist those graphs as structured data and render them in the viewer.
- **Run-level evaluation nodes** – self-judgement results now show up as dedicated graph nodes, so it is obvious which answers passed or failed.
- **Explainable execution** – every node keeps prompts, responses, metrics, and timeline data so you can diff runs, audit decisions, and replay segments.
- **AgentOps-ready observability** – the CLI, viewer, and tests work together to surface evaluation scores, usage, and synthetic graph statistics for downstream analytics.

## Repository Layout

- `src/agentflow/` – core package, including the Codex CLI adapter and Flask viewer.
- `tests/` – unit tests plus live Codex scenarios that exercise LangGraph generation.
- `sandbox/` – local plan artifacts written by live runs (ignored by git).

## Quick Start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install -e ".[dev]"
```

Install the Codex CLI globally and export an OpenAI key (already wired via `.env`):

```bash
npm install -g @openai/codex
set OPENAI_API_KEY=sk-...
```

Alternatively, use Anthropic Claude via the official CLI:

```bash
npm install -g anthropic
set ANTHROPIC_API_KEY=sk-ant-...
```

You can select the backend adapter per run using `--adapter`:

```bash
py -3 -m agentflow.cli --adapter claude "Summarize the purpose of this repository in 3 bullets."
```

## Generate a Showcase Prompt Graph

Use the built-in CLI to trigger a demonstration run that produces a multi-branch DAG with evaluation nodes:

```bash
py -3 -m agentflow.cli "You are preparing a showcase AgentFlow run. Follow this exact output template:

SECTION 1 - MCP Server
Provide a ```python``` block named mcp_server with production-ready FastAPI code exposing the SQLite DB at C:\Users\stanc\github\AgentFlow\sandbox\workspace.db. Include comments for demo clarity.

SECTION 2 - flow_spec JSON
Return a ```json``` block named flow_spec. The JSON object must contain:
- \"nodes\": array with at least 6 objects (each needs \"id\", \"label\", \"type\").
- Include at least one node that has \"on_true\" and \"on_false\" targets.
- Include at least one node where \"type\" is \"loop\" plus a \"max_iterations\" >= 2.
- Include an \"edges\" array listing the control-flow connections among all nodes.
- Ensure the JSON validates (double quotes, no trailing commas).

SECTION 3 - Live test walkthrough
Provide a numbered list detailing two iterations through the DAG, referencing branch paths and loop behavior. Use exactly two bullet points.

Do not include any other prose outside these sections."
```

The CLI will emit `sandbox/agentflow-<timestamp>.yaml`. That artifact contains:

- The original Codex exchange.
- Structured `flow_spec` JSON.
- Synthetic `flow::` nodes injected into the plan so the viewer graph shows every branch, loop, and evaluation path.
- Optional AgentFlowLanguage (`.afl`) transcription when `--output afl` is provided.

The same workflow works with the Claude adapter by adding `--adapter claude`. Ensure `ANTHROPIC_API_KEY` is set and optionally tune via:

```
set AGENTFLOW_ANTHROPIC_PATH=anthropic
set AGENTFLOW_ANTHROPIC_MODEL=claude-3-5-sonnet-latest
set AGENTFLOW_ANTHROPIC_MAX_TOKENS=1024
```

## AgentFlowLanguage Output

Pseudo-code prompts are auto-compiled when the Codex reply does not already contain a `flow_spec`. Use `--output afl` to persist an AgentFlowLanguage file alongside the YAML artifact; the compiler asks the model to translate the snippet into both structured graph data and a readable loop/branch script.

```bash
py -3 -m agentflow.cli --output afl "while(exploring){ ask_questions(); investigate_clues(); connect_patterns(surprises); if (blocked) { rethink_strategy(); } }"
```

The command above writes the standard `sandbox/agentflow-<timestamp>.yaml` artifact plus `sandbox/agentflow-<timestamp>.afl`, which captures the flow in AgentFlowLanguage form.

## Adaptive Workflow Runs

AgentFlow can now self-improve across multiple cycles. The `workflow` subcommand loops through repeated LangGraph executions, reads the prior cycle’s evaluation, and amends the next prompt with targeted directives before invoking the model again.

```bash
py -3 -m agentflow.cli workflow --cycles 3 --output afl "Design a LangGraph that triages support tickets by urgency and required department."
```

Each cycle writes a standard plan artifact (and optional `.afl` file) plus a shared history trail at `sandbox/workflows/<workflow_id>/history.yaml`. The history log records:

- the prompt that was actually issued for each cycle,
- the self-evaluation score and justification gathered from the previous run,
- structural statistics about the emitted `flow_spec` (node counts, branching, loops),
- and the adaptive directives injected into the next prompt.

Every per-cycle plan also receives a `workflow_reflection_cycle_<n>` node so the viewer surfaces what changed between iterations, making it obvious how the LangGraph reasoning evolves.

## LangGraph Orchestration

AgentFlow now delegates prompt execution and evaluation to a LangGraph state machine. The CLI builds a LangGraph pipeline that:

- invokes the Codex adapter,
- extracts LangGraph-friendly `flow_spec` payloads (or compiles them when missing),
- performs self-evaluation,
- and injects synthetic LangGraph nodes into the persisted plan artifact.

You can extend this orchestration by editing `build_prompt_pipeline` in `src/agentflow/cli/pipeline.py`; add new nodes, conditional edges, or tooling integrations while staying inside the LangGraph execution model.

## Inspect the DAG in the Viewer

```bash
py -3 -m agentflow.cli view --directory sandbox --host 127.0.0.1 --port 5050
```

The Flask viewer offers:

- Sidebar search over saved plans.
- DAG visualisation with prompt, response, and evaluation node cards.
- Graph stats banner reporting total prompts, responses, and evaluation nodes.
- Detailed panel for the currently selected node (raw prompt/response, evaluation score, metrics, timeline).

## Running Tests

- `pytest -k unit` covers fast, local tests.
- `py -3 -m pytest tests/live/test_agentflow_cli_live.py -k branches` kicks off the live scenario that asks Codex to produce a six-node graph with branching and loops. It writes a plan artifact identical to the showcase run above (requires `OPENAI_API_KEY`).

For Claude live smoke test:

```
py -3 -m pytest tests/live/test_claude_adapter_live.py -m live
```

## Roadmap

This repository is an evolving prototype toward a full AgentOps toolkit. Near-term work includes:

- richer synthetic-node attribution (surfacing tool outputs and loop counters),
- comparative run analytics across plan artifacts,
- and adapters beyond Codex so multiple LLM backends can propose and execute LangGraphs.

Feedback, issues, and contributions are welcome! Tag your ideas with **#AgentOps** and share how you are using AgentFlow to teach agents how to learn.
