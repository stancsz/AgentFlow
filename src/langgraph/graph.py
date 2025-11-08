"""
Minimal shim of the small subset of `langgraph.graph` used by the tests.

This implements a tiny StateGraph capable of registering nodes, edges,
conditional edges, and compiling to a pipeline object with an `invoke`
method that runs the graph synchronously. It's sufficient for unit tests
and avoids adding an external dependency.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, Optional


class _EndSentinel:
    pass


END = _EndSentinel()


class StateGraph:
    def __init__(self, state_type: Any = None) -> None:
        self._nodes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self._edges: Dict[str, str] = {}
        self._conditional: Dict[str, tuple[Callable[[Dict[str, Any]], str], Dict[str, str]]] = {}
        self._entry: Optional[str] = None

    def add_node(self, name: str, func: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self._nodes[name] = func

    def set_entry_point(self, name: str) -> None:
        self._entry = name

    def add_edge(self, src: str, dst: str) -> None:
        # For our purposes we only support single-target edges.
        self._edges[src] = dst

    def add_conditional_edges(self, src: str, selector: Callable[[Dict[str, Any]], str], mapping: Dict[str, str]) -> None:
        self._conditional[src] = (selector, mapping)

    def compile(self):
        graph = self

        class CompiledPipeline:
            def __init__(self, graph: "StateGraph") -> None:
                self._graph = graph

            def invoke(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
                state = dict(initial_state)
                current = self._graph._entry
                if current is None:
                    raise RuntimeError("No entry point defined for StateGraph")

                while True:
                    func = self._graph._nodes.get(current)
                    if func is None:
                        raise RuntimeError(f"Node not found: {current}")
                    try:
                        update = func(state)
                    except Exception:
                        # Re-raise to allow upstream handlers to catch Adapter errors
                        raise
                    if update:
                        state.update(update)

                    # Check conditional edges first
                    if current in self._graph._conditional:
                        selector, mapping = self._graph._conditional[current]
                        key = selector(state)
                        next_node = mapping.get(key)
                    else:
                        next_node = self._graph._edges.get(current)

                    if next_node is None:
                        # No explicit next node => terminate
                        return state
                    if next_node is END:
                        return state

                    current = next_node

        return CompiledPipeline(graph)
