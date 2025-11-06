from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agentflow.adapters import CodexCLIAdapter, CodexCLIError, CodexResult

from .evaluation import build_evaluation_outputs, perform_self_evaluation
from .flow_spec import (
    build_flow_nodes,
    compile_flow_spec_from_prompt,
    extract_flow_spec_from_message,
)
from .plan import build_plan_document


class PromptRunState(TypedDict, total=False):
    prompt: str
    summary: str
    plan_id: str
    request_afl: bool
    run_started: datetime
    run_finished: datetime
    duration_seconds: float
    plan_status: str
    node_status: str
    outputs: Dict[str, Any]
    usage: Dict[str, Any]
    events: List[Dict[str, Any]]
    notes: str
    error_payload: Optional[Dict[str, Any]]
    evaluation_payload: Optional[Dict[str, Any]]
    flow_spec_payload: Optional[Dict[str, Any]]
    flow_spec_source: Optional[str]
    afl_text: Optional[str]
    synthetic_nodes: List[Dict[str, Any]]
    codex_result: CodexResult
    plan_document: Dict[str, Any]


def timing_update(state: PromptRunState) -> Dict[str, Any]:
    """Record completion timestamps and durations for the current step."""
    run_started = state["run_started"]
    finished = datetime.now(timezone.utc)
    duration = (finished - run_started).total_seconds()
    return {"run_finished": finished, "duration_seconds": duration}


def build_prompt_pipeline(adapter: CodexCLIAdapter):
    """Compile the LangGraph pipeline responsible for one prompt execution."""
    graph = StateGraph(PromptRunState)

    def initialize(state: PromptRunState) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        return {
            "run_started": now,
            "run_finished": now,
            "duration_seconds": 0.0,
            "plan_status": "pending",
            "node_status": "pending",
            "outputs": {},
            "usage": {},
            "events": [],
            "notes": "Codex invocation pending.",
        }

    def invoke_model(state: PromptRunState) -> Dict[str, Any]:
        try:
            result = adapter.run(state["prompt"])
        except CodexCLIError as exc:
            update: Dict[str, Any] = {
                "plan_status": "failed",
                "node_status": "failed",
                "error_payload": {"message": str(exc)},
                "notes": f"Codex invocation failed: {exc}",
                "outputs": {"events": []},
                "events": [],
                "usage": {},
            }
            update.update(timing_update(state))
            return update

        outputs = {
            "message": result.message,
            "events": result.events,
        }
        update = {
            "plan_status": "completed",
            "node_status": "succeeded",
            "codex_result": result,
            "outputs": outputs,
            "events": result.events,
            "usage": result.usage or {},
            "notes": "Codex invocation succeeded.",
        }
        update.update(timing_update(state))
        return update

    def parse_flow_spec(state: PromptRunState) -> Dict[str, Any]:
        if state.get("plan_status") != "completed":
            return {}
        result = state.get("codex_result")
        if not result:
            return {}

        flow_spec_payload = extract_flow_spec_from_message(result.message)
        outputs = dict(state.get("outputs") or {})
        update: Dict[str, Any] = {}
        if flow_spec_payload:
            outputs["flow_spec"] = flow_spec_payload["flow_spec"]
            outputs["flow_spec_raw"] = flow_spec_payload["raw_json"]
            outputs["flow_spec_source"] = "assistant"
            afl_candidate = flow_spec_payload.get("agentflowlanguage")
            if afl_candidate:
                outputs["agentflowlanguage"] = afl_candidate
                update["afl_text"] = afl_candidate
            update["flow_spec_payload"] = flow_spec_payload
            update["flow_spec_source"] = "assistant"

        update["outputs"] = outputs
        return update

    def maybe_compile(state: PromptRunState) -> Dict[str, Any]:
        if state.get("plan_status") != "completed":
            return {}

        flow_spec_payload = state.get("flow_spec_payload")
        request_afl = state.get("request_afl", False)
        afl_text = state.get("afl_text")
        need_compile = flow_spec_payload is None or (request_afl and not afl_text)
        if not need_compile:
            return {}

        compiler_details = compile_flow_spec_from_prompt(adapter, state["prompt"])
        outputs = dict(state.get("outputs") or {})
        outputs["flow_spec_compiler"] = {
            "message": compiler_details.get("message", ""),
            "usage": compiler_details.get("usage", {}),
            "events": compiler_details.get("events", []),
            "source": compiler_details.get("source", "agentflowlanguage_compiler"),
        }
        error = compiler_details.get("error")
        if error:
            outputs["flow_spec_compiler_error"] = error

        update: Dict[str, Any] = {"outputs": outputs}
        compiled_payload = compiler_details.get("flow_spec_payload")
        if compiled_payload:
            outputs["flow_spec"] = compiled_payload["flow_spec"]
            outputs["flow_spec_raw"] = compiled_payload["raw_json"]
            source = compiler_details.get("source") or "agentflowlanguage_compiler"
            outputs["flow_spec_source"] = source
            update["flow_spec_payload"] = compiled_payload
            update["flow_spec_source"] = source
            afl_candidate = compiled_payload.get("agentflowlanguage")
            if afl_candidate:
                outputs["agentflowlanguage"] = afl_candidate
                update["afl_text"] = afl_candidate

        afl_from_compiler = compiler_details.get("agentflowlanguage")
        if afl_from_compiler:
            outputs["agentflowlanguage"] = afl_from_compiler
            update["afl_text"] = afl_from_compiler

        update.update(timing_update(state))
        return update

    def self_evaluate(state: PromptRunState) -> Dict[str, Any]:
        if state.get("plan_status") != "completed":
            return {}

        result = state.get("codex_result")
        if not result:
            return {}

        evaluation_payload = perform_self_evaluation(adapter, state["prompt"], result.message)
        if not evaluation_payload:
            return {}

        outputs = dict(state.get("outputs") or {})
        outputs["evaluation"] = build_evaluation_outputs(evaluation_payload)

        update: Dict[str, Any] = {
            "evaluation_payload": evaluation_payload,
            "outputs": outputs,
        }
        update.update(timing_update(state))
        return update

    def synthesize_nodes(state: PromptRunState) -> Dict[str, Any]:
        if state.get("plan_status") != "completed":
            return {}

        flow_spec_payload = state.get("flow_spec_payload")
        if not flow_spec_payload:
            return {}

        synthetic_nodes = build_flow_nodes(
            flow_spec_payload["flow_spec"],
            run_started=state["run_started"],
            run_finished=state.get("run_finished", state["run_started"]),
        )
        outputs = dict(state.get("outputs") or {})
        if synthetic_nodes:
            outputs.setdefault("flow_spec", flow_spec_payload["flow_spec"])
            if state.get("flow_spec_source"):
                outputs["flow_spec_source"] = state["flow_spec_source"]

        return {"synthetic_nodes": synthetic_nodes, "outputs": outputs}

    def build_plan(state: PromptRunState) -> Dict[str, Any]:
        outputs = dict(state.get("outputs") or {})
        outputs.setdefault("events", state.get("events", []))
        flow_spec_source = state.get("flow_spec_source")
        if flow_spec_source and outputs.get("flow_spec"):
            outputs["flow_spec_source"] = flow_spec_source

        run_started = state["run_started"]
        previous_finished = state.get("run_finished", run_started)
        now = datetime.now(timezone.utc)
        if now > previous_finished:
            run_finished = now
            duration_seconds = (run_finished - run_started).total_seconds()
        else:
            run_finished = previous_finished
            duration_seconds = state.get("duration_seconds", (run_finished - run_started).total_seconds())

        plan_document = build_plan_document(
            plan_id=state["plan_id"],
            prompt=state["prompt"],
            summary=state["summary"],
            plan_status=state.get("plan_status", "failed"),
            node_status=state.get("node_status", "failed"),
            outputs=outputs,
            usage=state.get("usage", {}),
            events=state.get("events", []),
            error_payload=state.get("error_payload"),
            run_started=run_started,
            run_finished=run_finished,
            duration_seconds=duration_seconds,
            notes=state.get("notes", ""),
            evaluation_payload=state.get("evaluation_payload"),
            synthetic_nodes=state.get("synthetic_nodes"),
        )

        return {
            "plan_document": plan_document,
            "outputs": outputs,
            "run_finished": run_finished,
            "duration_seconds": duration_seconds,
        }

    def post_invoke_route(state: PromptRunState) -> str:
        return "failure" if state.get("plan_status") == "failed" else "success"

    graph.add_node("initialize", initialize)
    graph.add_node("invoke_model", invoke_model)
    graph.add_node("parse_flow_spec", parse_flow_spec)
    graph.add_node("maybe_compile", maybe_compile)
    graph.add_node("self_evaluate", self_evaluate)
    graph.add_node("synthesize_nodes", synthesize_nodes)
    graph.add_node("build_plan", build_plan)

    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "invoke_model")
    graph.add_conditional_edges(
        "invoke_model",
        post_invoke_route,
        {"failure": "build_plan", "success": "parse_flow_spec"},
    )
    graph.add_edge("parse_flow_spec", "maybe_compile")
    graph.add_edge("maybe_compile", "self_evaluate")
    graph.add_edge("self_evaluate", "synthesize_nodes")
    graph.add_edge("synthesize_nodes", "build_plan")
    graph.add_edge("build_plan", END)

    return graph.compile()

