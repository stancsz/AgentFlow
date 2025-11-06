from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Tuple, Type

from agentflow.config import ConfigurationError, Settings

from .pipeline import PromptRunState, build_prompt_pipeline
from .plan import build_plan_document, resolve_plan_path, write_afl, write_plan

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from agentflow.adapters import (
        CodexCLIAdapter,
        CodexCLIError,
        CopilotCLIAdapter,
        CopilotCLIError,
        MockAdapter,
        MockAdapterError,
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
    }
    if adapter_name not in adapters:
        raise KeyError(adapter_name)
    return adapters[adapter_name]


def _get_viewer_runner() -> Callable[..., None]:
    cli_module = _get_cli_module()
    return cli_module.run_viewer


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
    from os import environ

    try:
        settings = Settings.from_env()
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    timestamp = datetime.now(timezone.utc)
    base_name = timestamp.strftime("agentflow-%Y%m%d%H%M%S")
    target_path, plan_id = resolve_plan_path(base_name)

    adapter_name = environ.get("AGENTFLOW_ADAPTER", "codex").lower()

    try:
        adapter_factory, adapter_error_class = _resolve_adapter(adapter_name)
    except KeyError:
        print(f"Unknown adapter '{adapter_name}'. Use 'codex', 'copilot', or 'mock'.", file=sys.stderr)
        return 1
    adapter = adapter_factory(settings)

    summary = prompt[:80].replace("\n", " ").strip() or "Ad-hoc Codex execution"
    request_afl = output_mode == "afl"

    pipeline = build_prompt_pipeline(adapter)
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
        print(f"Wrote plan artifact: {target_path}")
        print("Execution failed; inspect the YAML artifact for details.", file=sys.stderr)
        return 1

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

    write_plan(target_path, plan_document)

    print(f"Wrote plan artifact: {target_path}")
    afl_text = final_state.get("afl_text")
    if not afl_text:
        outputs_for_afl = final_state.get("outputs") or {}
        if isinstance(outputs_for_afl, dict):
            afl_text = outputs_for_afl.get("agentflowlanguage")

    if output_mode == "afl":
        if afl_text:
            afl_path = target_path.with_suffix(".afl")
            write_afl(afl_path, afl_text)
            print(f"Wrote AgentFlowLanguage artifact: {afl_path}")
        else:
            print(
                "AgentFlowLanguage output requested but no representation was generated.",
                file=sys.stderr,
            )

    plan_status = plan_document.get("status") or final_state.get("plan_status", "failed")
    if plan_status == "failed":
        print("Execution failed; inspect the YAML artifact for details.", file=sys.stderr)
        return 1
    return 0
