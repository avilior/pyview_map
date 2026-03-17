"""Router protocol and decision model."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel


class RouterDecision(BaseModel):
    """Decision returned by a router on each routing step."""

    next_action: Literal["speak", "end"]
    speaker: str | None = None   # agent name; required when next_action == "speak"
    reason: str | None = None    # optional explanation (useful for LLM-based routers)
    # Side conversation support
    update_main_flow_speaker: bool = False  # whether to write main_flow_speaker to state
    main_flow_speaker: str | None = None    # value to write (None = clear it)


@runtime_checkable
class Router(Protocol):
    """Protocol for pluggable debate routers.

    Implementations decide who speaks next (or whether the debate ends)
    based on the current LangGraph state, the Debate object, and the
    configured max_rounds.

    New routers can be added without touching the graph — register them
    in ``RouterFactory`` and reference them via ``router.type`` in templates.
    """

    def next(
        self,
        state: dict,
        debate: object,
        max_rounds: int | None,
    ) -> RouterDecision: ...
