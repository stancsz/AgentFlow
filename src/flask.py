"""
Tiny shim for Flask used to allow running unit tests without installing Flask.

This shim provides a minimal subset of the Flask API used by the project
for import-time behavior. It is NOT a full replacement for Flask and should
only be used in the test/dev container where installing dependencies is
undesirable. For real usage, install `Flask` from pip and remove this shim.
"""
from __future__ import annotations

from typing import Any, Callable, Dict


class Flask:
    def __init__(self, import_name: str, *, static_folder: str | None = None, template_folder: str | None = None):
        self.import_name = import_name
        self.static_folder = static_folder
        self.template_folder = template_folder
        self.config: Dict[str, Any] = {}

    def route(self, rule: str, **kwargs) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        # Simple decorator passthrough; real Flask registers routes, but tests only
        # import modules that declare routes. Return the original function.
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return func

        return decorator

    def run(self, host: str | None = None, port: int | None = None, debug: bool = False, use_reloader: bool = False) -> None:
        # No-op for tests.
        return None


def render_template(template_name: str, **context: Any) -> str:
    return f"<rendered {template_name}>"


def jsonify(obj: Any) -> Any:
    # For our tests, returning the object is sufficient.
    return obj


def abort(code: int, description: str | None = None) -> None:
    raise RuntimeError(f"Abort called: {code} - {description}")


def send_from_directory(directory: str | None, filename: str) -> str:
    return f"FILE:{filename}"
