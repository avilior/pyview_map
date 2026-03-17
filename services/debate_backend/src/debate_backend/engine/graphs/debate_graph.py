"""LangGraph debate graph — formal debate with supervisor-style routing.

Graph topology (Phase 2):

    START → router ──┬─ speak ──▶ agent_turn ── (interrupt_after) ──▶ router (loop)
                     └─ end ────▶ END

``interrupt_after=["agent_turn"]`` causes the graph to pause after each agent
speaks.  Each call to ``DebateEngine.run_turn()`` resumes the graph for exactly
one agent turn and then returns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from debate_backend.engine.llm_factory import create_llm
from debate_backend.engine.routers import RouterFactory
from debate_backend.engine.state import DebateState

if TYPE_CHECKING:
    from debate_backend.engine.models import TemplateConfig

LOG = logging.getLogger(__name__)


_NAME_SANITIZE_RE = re.compile(r"[^a-zA-Z0-9_-]")


def _to_langchain_messages(messages: list[dict[str, str]]) -> list[Any]:
    """Convert message dicts to LangChain ``BaseMessage`` objects.

    The optional ``name`` field on user messages is forwarded to
    ``HumanMessage`` after sanitising to meet OpenAI's requirement of
    ``[a-zA-Z0-9_-]`` only (e.g. "Agent Alpha" → "Agent_Alpha").
    Cloud providers (OpenAI, Anthropic) use this as an out-of-band speaker
    identity signal; Ollama ignores it and relies on the content prefix instead.
    """
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            raw_name = msg.get("name")
            if raw_name:
                safe_name = _NAME_SANITIZE_RE.sub("_", raw_name)[:64]
                result.append(HumanMessage(content=content, name=safe_name))
            else:
                result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
    return result


def build_debate_graph(template: "TemplateConfig") -> Any:
    """Build and compile a LangGraph debate graph for *template*.

    The router and max_rounds are captured in the node closures at build time.
    The ``Debate`` object and SSEQueue are injected per-invocation via
    ``config["configurable"]``.
    """
    router = RouterFactory.create(template.router.type)
    max_rounds = template.max_rounds

    # ------------------------------------------------------------------ nodes

    def router_node(state: DebateState, config: RunnableConfig) -> dict:
        debate = config["configurable"]["debate"]
        decision = router.next(state, debate, max_rounds)
        updates: dict = {
            "next_action": decision.next_action,
            "current_speaker": decision.speaker,
            "targeted_speaker": None,   # clear @Agent override after use
        }
        if decision.update_main_flow_speaker:
            updates["main_flow_speaker"] = decision.main_flow_speaker
        return updates

    async def agent_turn_node(state: DebateState, config: RunnableConfig) -> dict:
        from jrpc_common.jrpc_model import JSONRPCNotification  # avoid top-level cycle

        debate = config["configurable"]["debate"]
        queue = config["configurable"].get("sse_queue")
        info = config["configurable"].get("request_info")

        agent_name = state["current_speaker"]
        agent_idx = debate.find_agent_index(agent_name)
        if agent_idx is None:
            LOG.error("Agent %r not found in debate %s", agent_name, state["debate_id"])
            return {"round_count": state.get("round_count", 0)}

        agent = debate.agents[agent_idx]
        lc_messages = _to_langchain_messages(debate.build_messages(agent_idx))
        llm = create_llm(agent.model, agent.server_url)

        full_response = ""
        try:
            async for chunk in llm.astream(lc_messages):
                token = chunk.content
                if not token:
                    continue
                full_response += token
                if queue and info:
                    await queue.put(JSONRPCNotification(
                        method="notifications/debate.token",
                        params={
                            "requestId": info.id,
                            "debate_id": state["debate_id"],
                            "agent": agent_name,
                            "agent_index": agent_idx,
                            "token": token,
                        },
                    ))
        except Exception as exc:
            LOG.exception("LLM streaming failed for agent %s", agent_name)
            full_response = f"[LLM Error @ {agent.server_url} — {type(exc).__name__}: {exc}]"

        # Sync back to the Debate object (history + turn counter)
        debate.record_turn(agent_idx, full_response)

        # A round completes when the rotation wraps back to agent 0 (i.e. all
        # agents have spoken once).  Side convo turns don't count.
        is_side_convo = bool(state.get("main_flow_speaker"))
        round_complete = (not is_side_convo) and (debate.current_turn == 0)

        return {
            "round_count": state.get("round_count", 0) + (1 if round_complete else 0),
            "current_speaker": agent_name,
        }

    # --------------------------------------------------------------- routing

    def _route(state: DebateState) -> str:
        return state.get("next_action", "speak")

    # ------------------------------------------------------------------ graph

    builder = StateGraph(DebateState)
    builder.add_node("router", router_node)
    builder.add_node("agent_turn", agent_turn_node)

    builder.set_entry_point("router")
    builder.add_conditional_edges("router", _route, {"speak": "agent_turn", "end": END})
    builder.add_edge("agent_turn", "router")

    checkpointer = MemorySaver()
    return builder.compile(
        checkpointer=checkpointer,
        interrupt_after=["agent_turn"],
    )
