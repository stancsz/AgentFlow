from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple, Type

from agentflow.config import ConfigurationError, Settings

from .pipeline import PromptRunState, build_prompt_pipeline
from .plan import build_plan_document, resolve_plan_path, write_afl, write_plan
from .workflow import handle_workflow_command

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from agentflow.adapters import (
        CodexCLIAdapter,
        CodexCLIError,
        CopilotCLIAdapter,
        CopilotCLIError,
        MockAdapter,
        MockAdapterError,
        ClaudeCLIAdapter,
        ClaudeCLIError,
    )
    from agentflow.viewer import run_viewer


def _get_cli_module():
    """Return the agentflow.cli package for runtime indirection."""
    return import_module("agentflow.cli")


def _resolve_adapter(adapter_name: str) -> Tuple[Callable[[Settings], object], Type[BaseException]]:
    cli_module = _get_cli_module()
    adapters: Dict[str, Tuple[Callable[[Settings], object], Type[BaseException]]] = {
        "mock": (cli_module.MockAdapter, cli_module.MockAdapterError),
        "copilot": (cli_module.CopilotCLIAdapter, cli_module.CopilotCLIError),
        "codex": (cli_module.CodexCLIAdapter, cli_module.CodexCLIError),
        "claude": (cli_module.ClaudeCLIAdapter, cli_module.ClaudeCLIError),
    }
    if adapter_name not in adapters:
        raise KeyError(adapter_name)
    return adapters[adapter_name]


def _get_viewer_runner() -> Callable[..., None]:
    cli_module = _get_cli_module()
    return cli_module.run_viewer


@dataclass
class PromptExecutionResult:
    plan_path: Path
    plan_document: Dict[str, Any]
    final_state: Dict[str, Any]
    afl_path: Optional[Path]
    plan_status: str
    error_payload: Optional[Dict[str, Any]]


def _initialize_adapter() -> Tuple[object, Type[BaseException]]:
    from os import environ

    settings = Settings.from_env()
    adapter_name = environ.get("AGENTFLOW_ADAPTER", "codex").lower()
    adapter_factory, adapter_error_class = _resolve_adapter(adapter_name)
    adapter = adapter_factory(settings)
    return adapter, adapter_error_class


def _execute_prompt_run(
    adapter: object,
    adapter_error_class: Type[BaseException],
    *,
    prompt: str,
    summary: str,
    plan_id_prefix: Optional[str] = None,
    request_afl: bool = False,
) -> PromptExecutionResult:
    timestamp = datetime.now(timezone.utc)
    base_name = plan_id_prefix or timestamp.strftime("agentflow-%Y%m%d%H%M%S")
    target_path, plan_id = resolve_plan_path(base_name)

    pipeline = build_prompt_pipeline(adapter)  # type: ignore[arg-type]
    initial_state: PromptRunState = {
        "prompt": prompt,
        "summary": summary,
        "plan_id": plan_id,
        "request_afl": request_afl,
    }

    try:
        final_state = pipeline.invoke(initial_state)
    except adapter_error_class as exc:  # type: ignore[misc]
        run_finished = datetime.now(timezone.utc)
        duration = (run_finished - timestamp).total_seconds()
        final_state = {
            "plan_status": "failed",
            "node_status": "failed",
            "error_payload": {"message": str(exc)},
            "notes": f"Adapter invocation failed: {exc}",
            "run_started": timestamp,
            "run_finished": run_finished,
            "duration_seconds": duration,
            "outputs": {"events": []},
            "usage": {},
            "events": [],
        }
    except Exception as exc:  # pragma: no cover - defensive catch
        run_finished = datetime.now(timezone.utc)
        duration = (run_finished - timestamp).total_seconds()
        error_payload = {"message": f"Unexpected pipeline error: {exc.__class__.__name__}: {exc}"}
        plan_document = build_plan_document(
            plan_id=plan_id,
            prompt=prompt,
            summary=summary,
            plan_status="failed",
            node_status="failed",
            outputs={"events": []},
            usage={},
            events=[],
            error_payload=error_payload,
            run_started=timestamp,
            run_finished=run_finished,
            duration_seconds=duration,
            notes=f"Pipeline error: {exc.__class__.__name__}",
            evaluation_payload=None,
            synthetic_nodes=None,
        )
        write_plan(target_path, plan_document)
        return PromptExecutionResult(
            plan_path=target_path,
            plan_document=plan_document,
            final_state={
                "plan_status": "failed",
                "plan_document": plan_document,
                "error_payload": error_payload,
            },
            afl_path=None,
            plan_status="failed",
            error_payload=error_payload,
        )

    if not isinstance(final_state, dict):
        final_state = {}

    plan_document = final_state.get("plan_document")
    if not plan_document:
        outputs = dict(final_state.get("outputs") or {})
        usage = dict(final_state.get("usage") or {})
        events = list(final_state.get("events") or [])
        error_payload = final_state.get("error_payload")
        run_started = final_state.get("run_started", timestamp)
        run_finished = final_state.get("run_finished", run_started)
        duration = final_state.get("duration_seconds", (run_finished - run_started).total_seconds())
        plan_document = build_plan_document(
            plan_id=plan_id,
            prompt=prompt,
            summary=summary,
            plan_status=final_state.get("plan_status", "failed"),
            node_status=final_state.get("node_status", "failed"),
            outputs=outputs or {"events": events},
            usage=usage,
            events=events,
            error_payload=error_payload,
            run_started=run_started,
            run_finished=run_finished,
            duration_seconds=duration,
            notes=final_state.get("notes", "Pipeline produced no plan document."),
            evaluation_payload=final_state.get("evaluation_payload"),
            synthetic_nodes=final_state.get("synthetic_nodes"),
        )
        final_state["plan_document"] = plan_document

    write_plan(target_path, plan_document)

    afl_text = final_state.get("afl_text")
    if not afl_text:
        outputs_for_afl = final_state.get("outputs") or {}
        if isinstance(outputs_for_afl, dict):
            afl_text = outputs_for_afl.get("agentflowlanguage")

    afl_path: Optional[Path] = None
    if request_afl:
        if afl_text:
            afl_path = target_path.with_suffix(".afl")
            write_afl(afl_path, afl_text)
        else:
            afl_path = None

    plan_status = plan_document.get("status") or final_state.get("plan_status", "failed")
    error_payload = final_state.get("error_payload")
    return PromptExecutionResult(
        plan_path=target_path,
        plan_document=plan_document,
        final_state=final_state,
        afl_path=afl_path,
        plan_status=plan_status,
        error_payload=error_payload if isinstance(error_payload, dict) else None,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """
    CLI dispatcher.

    When invoked without explicit subcommands, treats the arguments as a free-form prompt.
    """
    args = list(argv if argv is not None else sys.argv[1:])
    if not args:
        print_usage()
        return 1

    if args[0] == "view":
        return handle_view_command(args[1:])
    if args[0] == "workflow":
        return handle_workflow_command(
            args[1:],
            initialize_adapter=_initialize_adapter,
            execute_prompt=_execute_prompt_run,
        )

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
        print_usage()
        return 1

    return handle_prompt(prompt, output_mode=namespace.output)


def print_usage() -> None:
    print(
        "Usage:\n"
        '  agentflow "<prompt text>"        Execute prompt via Codex and capture YAML artifact.\n'
        '  agentflow workflow [options]     Run a multi-cycle self-improving workflow.\n'
        "  agentflow view [options]         Launch local viewer for AgentFlow artifacts.\n"
    )


def handle_view_command(args: List[str]) -> int:
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

    run_viewer = _get_viewer_runner()

    try:
        run_viewer(directory=directory, host=namespace.host, port=namespace.port)
    except KeyboardInterrupt:
        print("\nViewer stopped.")
        return 0
    return 0


def handle_prompt(prompt: str, *, output_mode: str) -> int:
    try:
        adapter, adapter_error_class = _initialize_adapter()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1
    except KeyError as exc:
        print(f"Unknown adapter '{exc.args[0]}'. Use 'codex', 'copilot', or 'mock'.", file=sys.stderr)
        return 1
    summary = prompt[:80].replace("\n", " ").strip() or "Ad-hoc Codex execution"
    request_afl = output_mode == "afl"

    result = _execute_prompt_run(
        adapter,
        adapter_error_class,
        prompt=prompt,
        summary=summary,
        request_afl=request_afl,
    )

    print(f"Wrote plan artifact: {result.plan_path}")
    if request_afl:
        if result.afl_path:
            print(f"Wrote AgentFlowLanguage artifact: {result.afl_path}")
        else:
            print(
                "AgentFlowLanguage output requested but no representation was generated.",
                file=sys.stderr,
            )

    if result.plan_status == "failed":
        print("Execution failed; inspect the YAML artifact for details.", file=sys.stderr)
        return 1
    return 0
