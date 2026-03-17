"""LangGraph routing state for the debate engine.

Only routing metadata is stored here.  Full debate history lives in the
``Debate`` object (passed via ``config["configurable"]["debate"]``) to
preserve serialisation compatibility with existing save/load logic.
"""

from __future__ import annotations

from typing import TypedDict


class DebateState(TypedDict):
    """Minimal state managed by LangGraph between turns."""

    debate_id: str
    current_speaker: str | None    # name of agent who just spoke (or will speak)
    targeted_speaker: str | None   # @Agent override from inject; cleared by router after use
    round_count: int               # incremented after each agent turn
    next_action: str               # "speak" | "end"; set by router node
    status: str                    # "active" | "ended"
    main_flow_speaker: str | None  # next main-debate speaker saved when side convo starts
