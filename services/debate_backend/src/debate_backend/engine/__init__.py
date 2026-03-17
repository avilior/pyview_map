"""Debate engine — LangGraph-powered orchestration layer."""

from debate_backend.engine.graphs import (
    GRAPH_REGISTRY,
    get_graph,
)
from debate_backend.engine.models import (
    AgentConfig,
    EvaluatorConfig,
    RouterConfig,
    TemplateConfig,
)

__all__ = [
    "AgentConfig",
    "EvaluatorConfig",
    "RouterConfig",
    "TemplateConfig",
    "get_graph",
    "GRAPH_REGISTRY",
]
