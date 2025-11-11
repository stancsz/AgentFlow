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
        # Map of route -> handler callable stored by the route decorator.
        self._routes: Dict[str, Callable[..., Any]] = {}

    def route(self, rule: str, **kwargs) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        # Simple decorator passthrough; real Flask registers routes, but tests only
        # import modules that declare routes. Return the original function.
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            # Store the handler so a simple test client can invoke it later.
            try:
                self._routes[rule] = func
            except Exception:
                # If routes mapping can't be set for some reason, ignore.
                pass
            return func

        return decorator

    def run(self, host: str | None = None, port: int | None = None, debug: bool = False, use_reloader: bool = False) -> None:
        # No-op for tests.
        return None

    def test_client(self):
        """Return a minimal test client that can call registered route handlers.

        This is intentionally tiny: it only supports GET and returns an object with
        .status_code and .data attributes which is sufficient for unit tests that
        only check the HTTP status and rendered content.
        """

        app = self

        class _SimpleResponse:
            def __init__(self, data: Any, status_code: int = 200):
                self.data = data
                self.status_code = status_code

        class _SimpleClient:
            def get(self, path: str):
                # Exact-match lookup for registered route handlers.
                handler = app._routes.get(path)
                if handler is None:
                    # Not found: mimic Flask 404
                    return _SimpleResponse(f"Not Found: {path}", status_code=404)
                try:
                    result = handler()
                    return _SimpleResponse(result, status_code=200)
                except Exception as exc:  # pragma: no cover - surface errors to tests
                    return _SimpleResponse(f"Error invoking handler: {exc}", status_code=500)

        return _SimpleClient()


def render_template(template_name: str, **context: Any) -> str:
    return f"<rendered {template_name}>"


def jsonify(obj: Any) -> Any:
    # For our tests, returning the object is sufficient.
    return obj


def abort(code: int, description: str | None = None) -> None:
    raise RuntimeError(f"Abort called: {code} - {description}")


def send_from_directory(directory: str | None, filename: str) -> str:
    return f"FILE:{filename}"
