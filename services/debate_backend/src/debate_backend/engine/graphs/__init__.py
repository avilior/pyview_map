"""Graph registry — maps template mode names to graph builder functions.

Adding a new interaction mode requires:
1. A new ``build_<mode>_graph(template)`` function
2. One entry in ``GRAPH_REGISTRY``
Nothing else changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from debate_backend.engine.graphs.debate_graph import (
    build_debate_graph,
)

if TYPE_CHECKING:
    from debate_backend.engine.models import TemplateConfig

GRAPH_REGISTRY: dict[str, Callable[["TemplateConfig"], Any]] = {
    "debate": build_debate_graph,
    # "freeform": build_freeform_graph,   # Phase 4
}


def get_graph(template: "TemplateConfig") -> Any:
    """Return a compiled LangGraph graph for *template.mode*."""
    builder = GRAPH_REGISTRY.get(template.mode)
    if builder is None:
        available = list(GRAPH_REGISTRY)
        raise ValueError(
            f"Unknown graph mode: {template.mode!r}. Available: {available}"
        )
    return builder(template)


__all__ = ["get_graph", "GRAPH_REGISTRY"]
