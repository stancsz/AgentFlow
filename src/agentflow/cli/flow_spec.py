from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime
from textwrap import dedent
from typing import Any, Dict, List, Optional

from agentflow.adapters import CodexCLIAdapter, CodexCLIError

FLOW_SPEC_COMPILER_PROMPT = dedent(
    """\
    You are the AgentFlowLanguage compiler. Convert the provided pseudo code or natural language routine into a structured flow description.

    Return your answer as a markdown ```json``` block containing an object with exactly these keys:
      - "flow_spec": a JSON object with "nodes" (list) and "edges" (list) describing the control flow. Each node must include "id", "label", and "type".
      - "agentflowlanguage": a multiline string that mirrors the flow using AgentFlowLanguage syntax with constructs such as while(), if(), else, and semicolon-terminated actions.

    Flow spec requirements:
      * Use the node types "action", "branch", "loop", or other canonical AgentFlow types.
      * Provide "on_true" / "on_false" targets for branch and loop nodes when available.
      * Edges must include "source" and "target"; include a short "label" when it clarifies the path (e.g., "true", "false", "loop").

    Pseudo-code input:
    <<<
    {pseudo_code}
    >>>
    """
)


def extract_flow_spec_from_message(message: str) -> Optional[Dict[str, Any]]:
    """Pull a flow_spec JSON blob out of a markdown fenced payload."""
    if not message:
        return None

    fence_pattern = re.compile(r"```json(?:\s+flow_spec)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
    match = fence_pattern.search(message)
    if not match:
        return None

    candidate = match.group(1).strip()
    try:
        loaded = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    afl_text: Optional[str] = None
    flow_data: Optional[Dict[str, Any]] = None
    if isinstance(loaded, dict):
        flow_data = loaded.get("flow_spec")
        afl_candidate = loaded.get("agentflowlanguage")
        if isinstance(afl_candidate, str):
            afl_text = afl_candidate.strip()

    if flow_data is None:
        flow_data = loaded

    if not isinstance(flow_data, dict):
        return None

    nodes = flow_data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None

    payload: Dict[str, Any] = {"flow_spec": flow_data, "raw_json": candidate}
    if afl_text:
        payload["agentflowlanguage"] = afl_text
    return payload


def compile_flow_spec_from_prompt(adapter: CodexCLIAdapter, pseudo_code: str) -> Dict[str, Any]:
    """Ask the adapter to translate pseudo code into a flow_spec payload."""
    compiler_prompt = FLOW_SPEC_COMPILER_PROMPT.format(pseudo_code=pseudo_code.strip())

    try:
        compilation = adapter.run(compiler_prompt)
    except CodexCLIError as exc:
        return {
            "error": f"AgentFlowLanguage compilation failed: {exc}",
            "flow_spec_payload": None,
            "message": "",
            "events": [],
            "usage": {},
            "source": "agentflowlanguage_compiler",
        }

    payload = extract_flow_spec_from_message(compilation.message)
    response: Dict[str, Any] = {
        "flow_spec_payload": payload,
        "message": compilation.message,
        "events": compilation.events,
        "usage": compilation.usage or {},
        "source": "agentflowlanguage_compiler",
    }

    if payload:
        response["agentflowlanguage"] = payload.get("agentflowlanguage")
    else:
        response["agentflowlanguage"] = None
        response["error"] = "Compiler response did not contain a valid flow_spec."

    return response


def build_flow_nodes(
    flow_spec: Dict[str, Any],
    *,
    run_started: datetime,
    run_finished: datetime,
) -> List[Dict[str, Any]]:
    """Create synthetic plan nodes derived from a flow_spec document."""
    nodes_data = flow_spec.get("nodes")
    edges_data = flow_spec.get("edges", [])
    if not isinstance(nodes_data, list):
        return []

    dependency_map: Dict[str, List[str]] = defaultdict(list)
    if isinstance(edges_data, list):
        for edge in edges_data:
            if not isinstance(edge, dict):
                continue
            raw_source = str(edge.get("source") or edge.get("from") or "").strip()
            raw_target = str(edge.get("target") or edge.get("to") or "").strip()
            if not raw_source or not raw_target:
                continue
            dependency_map[raw_target].append(raw_source)

    synthetic_nodes: List[Dict[str, Any]] = []
    created_iso = run_started.isoformat()
    finished_iso = run_finished.isoformat()
    duration = round((run_finished - run_started).total_seconds(), 3)

    for entry in nodes_data:
        if not isinstance(entry, dict):
            continue
        raw_id = str(entry.get("id") or entry.get("name") or "").strip()
        if not raw_id:
            continue

        node_id = f"flow::{raw_id}"
        label = str(entry.get("label") or entry.get("name") or raw_id).strip()
        node_type = str(entry.get("type") or "flow").strip() or "flow"

        depends_on_raw = dependency_map.get(raw_id, [])
        depends_on = [f"flow::{source}" for source in depends_on_raw if source]
        if not depends_on:
            depends_on = ["codex_execution"]
        else:
            depends_on.insert(0, "codex_execution")

        depends_on = list(dict.fromkeys(depends_on))

        synthetic_nodes.append(
            {
                "id": node_id,
                "type": node_type,
                "summary": label,
                "depends_on": depends_on,
                "status": "succeeded",
                "attempt": 1,
                "inputs": {"flow_spec_node": entry},
                "outputs": {
                    "notes": "Synthetic node derived from flow_spec JSON.",
                    "source": "flow_spec",
                    "node_id": raw_id,
                },
                "artifacts": [],
                "metrics": {"flow_spec_type": node_type},
                "timeline": {
                    "queued_at": created_iso,
                    "started_at": created_iso,
                    "ended_at": finished_iso,
                    "duration_seconds": duration,
                },
                "history": [
                    {
                        "attempt_id": 1,
                        "timestamp": finished_iso,
                        "status": "succeeded",
                        "notes": "Generated from flow_spec JSON.",
                    }
                ],
            }
        )

    return synthetic_nodes

