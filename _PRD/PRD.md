AgentFlow - Plan/Execute Visualizer PRD
=======================================

1. Product Overview
-------------------
- **Problem**: Multi-step agent workflows lack a persistent, explainable representation of their plan and execution state. CLI-first tooling makes it hard to inspect dependency graphs, observe progress, or audit decisions.
- **Solution**: AgentFlow emits a canonical YAML graph that captures tasks, dependencies, execution metadata, and outputs. A Codex-like CLI runner executes nodes step by step, updates the YAML after each attempt, and a lightweight Flask UI visualizes the plan in near real time.

2. Goals and Non-Goals
----------------------
- **Goals**
  - Generate machine-editable YAML plans before execution with explicit graph structure.
  - Execute plans node by node, updating the YAML with timestamps, outputs, and status transitions.
  - Provide a Flask-based web UI that renders the plan graph, node timeline, and node detail panels.
  - Offer an API contract so external runners can read and write plan YAML safely (locking, diffing).
  - Support human-in-the-loop overrides such as pause, edit, rerun, and manual annotations.
- **Non-Goals**
  - Building a full agent marketplace or workflow marketplace.
  - Implementing complex role-based access control; assume a single trusted operator in v1.
  - Delivering real-time multi-user collaboration; polling or simple push is sufficient for MVP.

3. Personas
-----------
- **Automation Engineer** - designs flows, cares about reproducibility, inspects plan logic before running.
- **Agent Operator** - triggers flows, monitors progress, intervenes on failures or retries nodes.
- **Stakeholder Reviewer** - opens the UI in read-only mode to understand what ran and to export evidence.

4. Key User Stories
-------------------
- As an Automation Engineer, I create a YAML plan describing agent, tool, and service steps and validate the structure before running.
- As an Agent Operator, I start execution via CLI; the runner locks the plan, updates node state, and streams logs.
- As an Agent Operator, I pause after a node, edit parameters in YAML, and resume without losing history.
- As a Stakeholder Reviewer, I open the web UI and quickly grasp overall plan status through graph and KPI views.
- As a Stakeholder Reviewer, I inspect a single node to read prompts, inputs, outputs, artifacts, and error details.

5. System Overview
------------------
- **Planner**: Generates initial YAML from prompt or template, enforces schema validation, and signs the plan with a checksum.
- **Execution Orchestrator (CLI Runner)**: Reads YAML, finds runnable nodes (status pending and dependencies satisfied), executes via adapters (agent, tool, service), and writes back results.
- **State Writer**: Uses optimistic locking (version or hash) to avoid concurrent edits and appends a history entry per attempt.
- **Persistence**: Stores YAML on disk (git friendly). Future database or cloud storage is out of scope for v1.
- **Web UI (Flask)**: Serves REST endpoints such as `/plan`, `/plan/nodes/<id>`, `/plan/stream` and renders a lightweight SPA (HTMX or Alpine.js). UI polls or uses Server-Sent Events for freshness.
- **CLI and UI Contract**: Updates are atomic; the runner writes to a temporary file and swaps in to prevent partial writes. UI is read-only in MVP.

6. Detailed Functional Requirements
-----------------------------------
### 6.1 Plan Lifecycle
- Plan metadata includes `plan_id`, `name`, `description`, `created_at`, `created_by`, `version`, and `status`.
- Plan status values: `draft`, `running`, `paused`, `completed`, `failed`, `cancelled`.
- Nodes contain:
  - Required fields: `id`, `type` (`agent`, `tool`, `service`, `check`, `decision`), `summary`, `depends_on`.
  - Execution payload: structured `inputs`, plus `prompt` (for agent), `command` (shell), or `request` (HTTP).
  - Status machine: `pending -> ready -> in_progress -> succeeded / failed / skipped`; `blocked` indicates dependency failure.
  - Result envelope: `outputs`, `artifacts`, `metrics`, `error`.
  - Timeline fields: `queued_at`, `started_at`, `ended_at`, `duration_seconds`.
  - History array storing each attempt with `attempt_id`, `timestamp`, `status`, and `notes`.
- Validation:
  - CLI validates schema before running, rejecting circular dependencies, missing nodes, or illegal status transitions.
  - Pre-execution dry run ensures all required variables are supplied.

### 6.2 Execution Flow
1. Runner loads YAML, validates checksum, and switches plan status to `running`.
2. Runner picks a runnable node with satisfied dependencies.
3. Runner executes node via adapter:
   - `agent`: send prompt to LLM backend through Codex CLI.
   - `tool`: run shell command or script.
   - `service`: send HTTP request with defined method, headers, and body.
4. Runner writes back node status, outputs, timestamps, and appends to history.
5. Runner updates plan rollups (counts, percent complete, critical path estimate).
6. On failure, runner marks node `failed`, optionally marks downstream nodes `blocked`, and emits alerts.
7. Runner sets plan status to `completed` when all nodes succeed or `failed` when any critical node fails without retry.

### 6.3 Human Oversight
- Manual overrides can edit node inputs or mark statuses; runner detects `manual_override` flags and revalidates.
- Pause and resume: plan status `paused` prevents new node execution until restored to `running`.
- Notes: plan-level `notes` and node-level `notes` support markdown comments for audit context.

7. Web UI Requirements
----------------------
- Flask endpoints:
  - `GET /plan/<plan_id>` returns plan metadata and node summaries.
  - `GET /plan/<plan_id>/nodes` returns node list with pagination and filters.
  - `GET /plan/<plan_id>/nodes/<node_id>` returns full node detail including history.
  - `POST /plan/<plan_id>/actions` handles pause, resume, and rerun requests (feature flagged in MVP).
- Frontend layout:
  - Header with plan title, status badge, progress bar, and timing stats.
  - Left panel that renders DAG graph with color-coded node statuses.
  - Right panel with tabs for Overview, Inputs and Outputs, History, and Artifacts.
  - Secondary views for chronological activity feed and filterable node table.
  - Alert banner or toast area for failures or manual action requests.
- Visualization behavior:
  - Nodes colored by status; edges highlight current critical path.
  - Timeline view (Gantt style) derived from node timestamps.
- Performance target: support plans up to 200 nodes with less than 2 seconds initial load and less than 1 second incremental refresh.

8. Interfaces and Integrations
------------------------------
- **CLI Commands**
  - `agentflow plan create --spec spec.md` produces validated YAML.
  - `agentflow run plan.yml` orchestrates execution and writes updates.
  - `agentflow node rerun plan.yml --node <id>` reruns a single node.
- **File Contract**
  - YAML encoded in UTF-8 with two-space indentation.
  - Runner maintains trailing comment or metadata hash describing last update.
  - Optional `.planstate` JSON cache for fast diffing (stretch goal).
- **Notification Hooks**
  - Webhook triggers on plan state changes.
  - Email or Slack adapters are optional stretch targets.

9. Non-Functional Requirements
------------------------------
- **Reliability**: Runner restarts by re-reading YAML and continuing from the last known state.
- **Observability**: Structured logs; plan YAML stores summaries, large logs are referenced through artifact paths.
- **Security**: Local-first assumption; commands sanitized; future authentication deferred.
- **Extensibility**: Schema versioning via `schema_version` and documented migration steps.
- **Testing**: Unit tests for schema validation and integration tests for sample plans.

10. Success Metrics and Milestones
----------------------------------
- MVP: CLI can run sample plan, update YAML, and UI renders the graph with live polling.
- 30-day goal: Support modifying plan mid-run and rerunning failed nodes through the UI.
- Quality: Less than 5 percent of plan runs fail due to orchestration errors; schema validator catches 95 percent of authoring mistakes pre-run.

11. Open Questions
------------------
- Should updates be chunked into an append-only log to avoid merge conflicts?
- Is streaming of long-running node output required for the UI?
- What level of authentication is needed for Flask UI access beyond localhost?
- Do we need a plugin system for node types beyond agent, tool, and service in the MVP?
