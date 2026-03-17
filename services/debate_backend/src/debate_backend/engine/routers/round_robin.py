"""Round-robin router — agents speak in order, cycling back to start."""

from __future__ import annotations

from debate_backend.engine.routers.base import (
    Router,
    RouterDecision,
)


class RoundRobinRouter:
    """Deterministic router: agents speak in declaration order, cycling.

    Respects ``targeted_speaker`` set by moderator ``@Agent`` inject.
    When a targeted turn starts, the next main-debate speaker is saved to
    ``main_flow_speaker`` so that after the side conversation the debate can
    resume from exactly the right position.
    Ends the debate when ``round_count >= max_rounds`` (only on main turns).
    """

    def next(
        self,
        state: dict,
        debate: object,
        max_rounds: int | None,
    ) -> RouterDecision:
        agents = debate.agents  # type: ignore[attr-defined]

        # Honor @Agent targeting injected by the moderator
        targeted = state.get("targeted_speaker")
        if targeted:
            main_flow_speaker = state.get("main_flow_speaker")
            if main_flow_speaker is None:
                # First targeted turn — compute and save the next main-debate speaker
                current_name = state.get("current_speaker")
                if current_name is None:
                    computed_main = agents[0].name
                else:
                    current_idx = next(
                        (i for i, a in enumerate(agents) if a.name == current_name), 0
                    )
                    computed_main = agents[(current_idx + 1) % len(agents)].name
                return RouterDecision(
                    next_action="speak",
                    speaker=targeted,
                    update_main_flow_speaker=True,
                    main_flow_speaker=computed_main,
                )
            else:
                # Continuing side convo — leave main_flow_speaker unchanged
                return RouterDecision(next_action="speak", speaker=targeted)

        # Main debate turn
        main_flow_speaker = state.get("main_flow_speaker")
        if main_flow_speaker:
            # Resuming from a side conversation — use saved speaker and clear it
            return RouterDecision(
                next_action="speak",
                speaker=main_flow_speaker,
                update_main_flow_speaker=True,
                main_flow_speaker=None,
            )

        # Normal round-robin — check max rounds only on main debate turns
        if max_rounds is not None and state.get("round_count", 0) >= max_rounds:
            return RouterDecision(next_action="end", reason="max rounds reached")

        current_name = state.get("current_speaker")
        if current_name is None:
            # First turn — start with agent 0
            return RouterDecision(next_action="speak", speaker=agents[0].name)

        # Advance to the next agent (wrapping)
        current_idx = next(
            (i for i, a in enumerate(agents) if a.name == current_name), 0
        )
        next_idx = (current_idx + 1) % len(agents)
        return RouterDecision(next_action="speak", speaker=agents[next_idx].name)


# Satisfy the Router protocol at import time (structural check)
_: Router = RoundRobinRouter()
