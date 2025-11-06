from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


def resolve_plan_path(base_name: str) -> Tuple[Path, str]:
    """Choose a unique plan artifact path in the current working directory."""
    directory = Path.cwd()
    candidate = directory / f"{base_name}.yaml"
    suffix = 1
    while candidate.exists():
        candidate = directory / f"{base_name}-{suffix}.yaml"
        suffix += 1

    filename = candidate.stem
    plan_id = f"plan-{filename.split('-', 1)[-1]}"
    return candidate, plan_id


def build_plan_document(
    *,
    plan_id: str,
    prompt: str,
    summary: str,
    plan_status: str,
    node_status: str,
    outputs: Dict[str, Any],
    usage: Dict[str, Any],
    events: List[Dict[str, Any]],
    error_payload: Optional[Dict[str, Any]],
    run_started: datetime,
    run_finished: datetime,
    duration_seconds: float,
    notes: str,
    evaluation_payload: Optional[Dict[str, Any]],
    synthetic_nodes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Assemble the AgentFlow plan document shared across CLI runs."""
    created_iso = run_started.isoformat()
    finished_iso = run_finished.isoformat()

    node: Dict[str, Any] = {
        "id": "codex_execution",
        "type": "agent",
        "summary": summary or "Codex execution",
        "depends_on": [],
        "status": "succeeded" if node_status == "succeeded" else "failed",
        "attempt": 1,
        "inputs": {
            "prompt": prompt,
        },
        "outputs": outputs,
        "artifacts": [],
        "metrics": build_metrics(usage, evaluation_payload),
        "timeline": {
            "queued_at": created_iso,
            "started_at": run_started.isoformat(),
            "ended_at": finished_iso,
            "duration_seconds": round(duration_seconds, 3),
        },
        "history": [
            {
                "attempt_id": 1,
                "timestamp": finished_iso,
                "status": "succeeded" if node_status == "succeeded" else "failed",
                "notes": notes,
            }
        ],
    }

    if error_payload:
        node["error"] = error_payload

    nodes: List[Dict[str, Any]] = [node]
    if synthetic_nodes:
        nodes.extend(synthetic_nodes)

    success_count = sum(1 for item in nodes if item.get("status") == "succeeded")
    failure_count = sum(1 for item in nodes if item.get("status") == "failed")

    plan_document: Dict[str, Any] = {
        "schema_version": "1.0",
        "plan_id": plan_id,
        "name": summary or "Codex execution",
        "description": prompt,
        "created_at": created_iso,
        "last_updated": finished_iso,
        "created_by": "agentflow-cli@local",
        "version": 1,
        "status": plan_status,
        "tags": [],
        "context": {},
        "nodes": nodes,
        "rollup": {
            "completion_percentage": 100 if plan_status == "completed" else 0,
            "counts": {
                "succeeded": success_count,
                "failed": failure_count,
            },
            "last_writer": "agentflow-cli@local",
        },
    }

    if events:
        plan_document["metadata"] = {"codex_events_count": len(events)}

    if evaluation_payload:
        eval_metrics: Dict[str, Any] = {}
        score = evaluation_payload.get("score") if isinstance(evaluation_payload, dict) else None
        if score is not None:
            eval_metrics["self_evaluation_score"] = score
        error = evaluation_payload.get("error") if isinstance(evaluation_payload, dict) else None
        if error:
            eval_metrics["self_evaluation_error"] = error
        if eval_metrics:
            plan_document["eval_metrics"] = eval_metrics

    return plan_document


def write_plan(path: Path, payload: Dict[str, Any]) -> None:
    """Persist the plan document as YAML."""
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def write_afl(path: Path, afl_text: str) -> None:
    """Persist the AgentFlowLanguage artifact."""
    with path.open("w", encoding="utf-8") as handle:
        handle.write(afl_text.rstrip() + "\n")


def build_metrics(usage: Dict[str, Any], evaluation_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine usage and evaluation details into the node metrics block."""
    metrics: Dict[str, Any] = {"usage": usage}
    if evaluation_payload:
        score = evaluation_payload.get("score")
        if score is not None:
            metrics["evaluation_score"] = score
        eval_usage = evaluation_payload.get("usage")
        if eval_usage:
            metrics["evaluation_usage"] = eval_usage
        error = evaluation_payload.get("error")
        if error:
            metrics["evaluation_error"] = error
    return metrics

