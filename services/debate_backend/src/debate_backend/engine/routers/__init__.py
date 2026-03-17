"""Router registry and factory."""

from __future__ import annotations

from debate_backend.engine.routers.base import (
    Router,
    RouterDecision,
)
from debate_backend.engine.routers.round_robin import (
    RoundRobinRouter,
)

_ROUTER_REGISTRY: dict[str, type] = {
    "round_robin": RoundRobinRouter,
    # "evaluator_directed": EvaluatorDirectedRouter,  # Phase 5
    # "llm_supervisor": LLMSupervisorRouter,          # Phase 5
}


class RouterFactory:
    @staticmethod
    def create(router_type: str) -> Router:
        """Instantiate a router by type name."""
        cls = _ROUTER_REGISTRY.get(router_type)
        if cls is None:
            available = list(_ROUTER_REGISTRY)
            raise ValueError(
                f"Unknown router type: {router_type!r}. Available: {available}"
            )
        return cls()


__all__ = ["Router", "RouterDecision", "RoundRobinRouter", "RouterFactory"]
