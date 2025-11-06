"""
AgentFlow CLI entry point.

Supports two workflows:
1. `agentflow "<prompt>"` — execute the prompt through the Codex CLI adapter and persist a
   single-node plan YAML artifact capturing the run.
2. `agentflow view` — launch a lightweight Flask viewer over previously generated artifacts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from textwrap import dedent

import yaml

from agentflow.adapters import (
    CodexCLIAdapter,
    CodexCLIError,
    CopilotCLIAdapter,
    CopilotCLIError,
    MockAdapter,
    MockAdapterError,
)
from agentflow.config import ConfigurationError, Settings
from agentflow.viewer import run_viewer


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


def main(argv: Optional[List[str]] = None) -> int:
    """
    CLI dispatcher.

    When invoked without explicit subcommands, treats the arguments as a free-form prompt.
    """

    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        _print_usage()
        return 1

    if args[0] == "view":
        return _handle_view_command(args[1:])

    parser = argparse.ArgumentParser(
        prog="agentflow",
        add_help=True,
        description="Execute a prompt through the Codex adapter and persist an AgentFlow artifact.",
    )
    parser.add_argument(
        "--output",
        choices=["yaml", "afl"],
        default="yaml",
        help="Artifact output preference (default: yaml). Use 'afl' to also emit an AgentFlowLanguage file.",
    )
    parser.add_argument(
        "prompt",
        nargs=argparse.REMAINDER,
        help="Prompt text to send to the Codex adapter.",
    )

    namespace = parser.parse_args(args)
    prompt_parts = namespace.prompt
    prompt = " ".join(prompt_parts).strip()
    if not prompt:
        _print_usage()
        return 1

    return _handle_prompt(prompt, output_mode=namespace.output)


def _print_usage() -> None:
    print(
        "Usage:\n"
        '  agentflow "<prompt text>"        Execute prompt via Codex and capture YAML artifact.\n'
        "  agentflow view [options]         Launch local viewer for AgentFlow artifacts.\n"
    )


def _handle_view_command(args: List[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="agentflow view",
        description="Launch the AgentFlow artifact viewer.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface for the Flask server (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        default=5050,
        type=int,
        help="Port for the Flask server (default: 5050).",
    )
    parser.add_argument(
        "--directory",
        default=".",
        help="Directory containing AgentFlow-generated YAML artifacts (default: current directory).",
    )

    namespace = parser.parse_args(args)
    directory = Path(namespace.directory).resolve()

    if not directory.exists():
        print(f"Directory not found: {directory}", file=sys.stderr)
        return 1

    try:
        run_viewer(directory=directory, host=namespace.host, port=namespace.port)
    except KeyboardInterrupt:
        print("\nViewer stopped.")
        return 0
    return 0


def _handle_prompt(prompt: str, *, output_mode: str) -> int:
    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    timestamp = datetime.now(timezone.utc)
    base_name = timestamp.strftime("agentflow-%Y%m%d%H%M%S")
    target_path, plan_id = _resolve_plan_path(base_name)

    # Select adapter based on AGENTFLOW_ADAPTER environment variable
    from os import environ
    adapter_name = environ.get("AGENTFLOW_ADAPTER", "codex").lower()
    
    if adapter_name == "mock":
        adapter = MockAdapter(settings)
        adapter_error_class = MockAdapterError
    elif adapter_name == "copilot":
        adapter = CopilotCLIAdapter(settings)
        adapter_error_class = CopilotCLIError
    elif adapter_name == "codex":
        adapter = CodexCLIAdapter(settings)
        adapter_error_class = CodexCLIError
    else:
        print(f"Unknown adapter '{adapter_name}'. Use 'codex', 'copilot', or 'mock'.", file=sys.stderr)
        return 1

    node_status = "succeeded"
    plan_status = "completed"
    outputs: Dict[str, Any] = {}
    usage: Dict[str, Any] = {}
    events: List[Dict[str, Any]] = []
    error_payload: Optional[Dict[str, Any]] = None
    notes = "Codex invocation succeeded."
    evaluation_payload: Optional[Dict[str, Any]] = None
    flow_spec_payload: Optional[Dict[str, Any]] = None
    flow_spec_source: Optional[str] = None
    afl_text: Optional[str] = None
    request_afl = output_mode == "afl"

    run_started = datetime.now(timezone.utc)
    try:
        result = adapter.run(prompt)
        events = result.events
        outputs = {"message": result.message, "events": events}
        usage = result.usage or {}
        flow_spec_payload = _extract_flow_spec_from_message(result.message)
        if flow_spec_payload:
            flow_spec_source = "assistant"
            outputs["flow_spec"] = flow_spec_payload["flow_spec"]
            outputs["flow_spec_raw"] = flow_spec_payload["raw_json"]
            afl_candidate = flow_spec_payload.get("agentflowlanguage")
            if afl_candidate:
                afl_text = afl_candidate
                outputs["agentflowlanguage"] = afl_text
        evaluation_payload = _perform_self_evaluation(adapter, prompt, result.message)
        if evaluation_payload:
            outputs["evaluation"] = _build_evaluation_outputs(evaluation_payload)
    except (CodexCLIError, CopilotCLIError, MockAdapterError) as exc:
        node_status = "failed"
        plan_status = "failed"
        error_payload = {"message": str(exc)}
        notes = f"Adapter invocation failed: {exc}"
    except Exception as exc:  # pragma: no cover - defensive catch
        node_status = "failed"
        plan_status = "failed"
        error_payload = {"message": f"Unexpected error: {exc.__class__.__name__}: {exc}"}
        notes = f"Unexpected error: {exc.__class__.__name__}"
    run_finished = datetime.now(timezone.utc)

    if plan_status == "completed" and (flow_spec_payload is None or (request_afl and not afl_text)):
        compiler_details = _compile_flow_spec_from_prompt(adapter, prompt)
        if compiler_details:
            compiler_error = compiler_details.get("error")
            if compiler_error:
                outputs["flow_spec_compiler_error"] = compiler_error
            else:
                compiled_payload = compiler_details.get("flow_spec_payload")
                if compiled_payload:
                    flow_spec_payload = compiled_payload
                    flow_spec_source = compiler_details.get("source") or "agentflowlanguage_compiler"
                    outputs["flow_spec"] = flow_spec_payload["flow_spec"]
                    outputs["flow_spec_raw"] = flow_spec_payload["raw_json"]
                    afl_candidate = flow_spec_payload.get("agentflowlanguage")
                    if afl_candidate:
                        afl_text = afl_candidate
                afl_from_compiler = compiler_details.get("agentflowlanguage")
                if afl_from_compiler:
                    afl_text = afl_from_compiler
                outputs["flow_spec_compiler"] = {
                    "message": compiler_details.get("message", ""),
                    "usage": compiler_details.get("usage", {}),
                    "events": compiler_details.get("events", []),
                    "source": compiler_details.get("source", "agentflowlanguage_compiler"),
                }
                if afl_text:
                    outputs["agentflowlanguage"] = afl_text

    if "events" not in outputs:
        outputs = {**outputs, "events": events}

    if flow_spec_payload:
        outputs["flow_spec_source"] = flow_spec_source or outputs.get("flow_spec_source") or "assistant"
        if afl_text:
            outputs["agentflowlanguage"] = afl_text

    duration = (run_finished - run_started).total_seconds()
    synthetic_nodes: List[Dict[str, Any]] = []
    if plan_status == "completed" and flow_spec_payload:
        synthetic_nodes = _build_flow_nodes(
            flow_spec_payload["flow_spec"],
            run_started=run_started,
            run_finished=run_finished,
        )
        if synthetic_nodes:
            outputs.setdefault("flow_spec", flow_spec_payload["flow_spec"])

    summary = prompt[:80].replace("\n", " ").strip() or "Ad-hoc Codex execution"

    plan_document = _build_plan_document(
        plan_id=plan_id,
        prompt=prompt,
        summary=summary,
        plan_status=plan_status,
        node_status=node_status,
        outputs=outputs,
        usage=usage,
        events=events,
        error_payload=error_payload,
        run_started=run_started,
        run_finished=run_finished,
        duration_seconds=duration,
        notes=notes,
        evaluation_payload=evaluation_payload,
        synthetic_nodes=synthetic_nodes,
    )

    _write_plan(target_path, plan_document)

    print(f"Wrote plan artifact: {target_path}")
    if output_mode == "afl":
        if afl_text:
            afl_path = target_path.with_suffix(".afl")
            _write_afl(afl_path, afl_text)
            print(f"Wrote AgentFlowLanguage artifact: {afl_path}")
        else:
            print(
                "AgentFlowLanguage output requested but no representation was generated.",
                file=sys.stderr,
            )
    if plan_status == "failed":
        print("Execution failed; inspect the YAML artifact for details.", file=sys.stderr)
        return 1
    return 0


def _resolve_plan_path(base_name: str) -> Tuple[Path, str]:
    directory = Path.cwd()
    candidate = directory / f"{base_name}.yaml"
    suffix = 1
    while candidate.exists():
        candidate = directory / f"{base_name}-{suffix}.yaml"
        suffix += 1

    filename = candidate.stem
    plan_id = f"plan-{filename.split('-', 1)[-1]}"
    return candidate, plan_id


def _build_plan_document(
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
        "metrics": _build_metrics(usage, evaluation_payload),
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


def _write_plan(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def _write_afl(path: Path, afl_text: str) -> None:
    with path.open("w", encoding="utf-8") as handle:
        handle.write(afl_text.rstrip() + "\n")


def _perform_self_evaluation(
    adapter: CodexCLIAdapter,
    prompt: str,
    response: str,
) -> Optional[Dict[str, Any]]:
    evaluation_prompt = (
        "You are an impartial self-evaluation judge. Score how well the assistant's reply satisfies the "
        "original prompt. The score must be a float between 0.0 and 1.0 inclusive, where 1.0 represents a perfect answer.\n"
        "Respond STRICTLY with a single-line JSON object of the form "
        '{"score": <float>, "justification": "<concise reasoning>"}.\n'
        "Do not emit any extra text, markdown, or code fences. If you cannot evaluate, still return JSON with score 0.0.\n"
        "Conversation to evaluate:\n"
        "User:\n<<<\n"
        f"{prompt}\n"
        ">>>\n"
        "Assistant:\n<<<\n"
        f"{response}\n"
        ">>>\n"
        )

    try:
        evaluation_result = adapter.run(evaluation_prompt)
    except CodexCLIError as exc:
        return {"error": f"Self-evaluation failed: {exc}"}

    parsed = _parse_evaluation_payload(evaluation_result.message)
    payload: Dict[str, Any] = {
        "raw_message": evaluation_result.message,
        "events": evaluation_result.events,
        "usage": evaluation_result.usage or {},
    }
    if parsed:
        payload.update(parsed)
    else:
        payload["error"] = "Self-evaluation response was not valid JSON."
    return payload


def _parse_evaluation_payload(message: str) -> Optional[Dict[str, Any]]:
    candidate = message.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        if "\n" in candidate:
            candidate = candidate.split("\n", 1)[-1]

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return _parse_plaintext_evaluation(message)

    score = payload.get("score")
    try:
        if score is not None:
            score = float(score)
    except (TypeError, ValueError):
        score = None

    justification = payload.get("justification") or payload.get("reasoning")
    if justification is not None:
        justification = str(justification).strip()

    return {"score": score, "justification": justification}


def _build_metrics(usage: Dict[str, Any], evaluation_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
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


def _build_evaluation_outputs(evaluation_payload: Dict[str, Any]) -> Dict[str, Any]:
    outputs: Dict[str, Any] = {}
    if evaluation_payload.get("score") is not None:
        outputs["score"] = evaluation_payload["score"]
    if evaluation_payload.get("justification"):
        outputs["justification"] = evaluation_payload["justification"]
    if evaluation_payload.get("error"):
        outputs["error"] = evaluation_payload["error"]
    outputs["raw_message"] = evaluation_payload.get("raw_message", "")
    outputs["events"] = evaluation_payload.get("events", [])
    outputs["usage"] = evaluation_payload.get("usage", {})
    return outputs


def _parse_plaintext_evaluation(message: str) -> Optional[Dict[str, Any]]:
    score: Optional[float] = None
    justification_parts: List[str] = []
    lines = message.splitlines()

    for index, raw_line in enumerate(lines):
        stripped_line = raw_line.strip()
        if not stripped_line:
            continue

        normalized = stripped_line.lstrip("-*").strip()
        lower = normalized.lower()

        if lower.startswith("score"):
            numeric_match = re.search(r"([0-9]+(?:\.[0-9]+)?)", normalized)
            if numeric_match:
                try:
                    score = float(numeric_match.group(1))
                except ValueError:
                    score = None
            continue

        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", normalized):
            try:
                score = float(normalized)
            except ValueError:
                score = None
            continue

        if lower.startswith(("reason", "justification", "rationale")):
            text = normalized.split(":", 1)[1].strip() if ":" in normalized else normalized
            if text:
                justification_parts.append(text)

            for follow in lines[index + 1 :]:
                follow_stripped = follow.strip()
                if not follow_stripped:
                    continue
                follow_normalized = follow_stripped.lstrip("-*").strip()
                follow_lower = follow_normalized.lower()
                if follow_lower.startswith(("score", "reason", "justification", "rationale")):
                    break
                justification_parts.append(follow_normalized)
            break

    if score is None:
        return None

    justification = " ".join(justification_parts).strip() or None
    return {"score": score, "justification": justification}


def _extract_flow_spec_from_message(message: str) -> Optional[Dict[str, Any]]:
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
    flow_data = None
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


def _compile_flow_spec_from_prompt(
    adapter: CodexCLIAdapter,
    pseudo_code: str,
) -> Dict[str, Any]:
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

    payload = _extract_flow_spec_from_message(compilation.message)
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


def _build_flow_nodes(
    flow_spec: Dict[str, Any],
    *,
    run_started: datetime,
    run_finished: datetime,
) -> List[Dict[str, Any]]:
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
            # Ensure codex execution precedes everything.
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


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
