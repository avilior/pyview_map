# ---------------------------------------------------------------------------
# Debate application — two LLM agents debating with user as moderator
#
# JSON-RPC methods:
#   debate.start      — start a new debate
#   debate.next_turn  — trigger the next agent's turn (streaming)
#   debate.inject     — moderator injects a prompt (streaming)
#   debate.status     — get current debate state
#   debate.stop       — end the debate
# ---------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from jrpc_common.jrpc_model import JSONRPCNotification, JSONRPCResponse
from http_stream_transport.jsonrpc.handler_meta import RequestInfo
from http_stream_transport.jsonrpc.jrpc_service import SSEQueue, jrpc_service

from debate_backend.engine import TemplateConfig, get_graph
from debate_backend.engine.llm_factory import OLLAMA_DEFAULT_BASE_URL

LOG = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.2"

_MODERATOR_CLAUSE = (
    "\n\nAll participants in this debate are identified by a name prefix on "
    "their messages (e.g. 'Alice:', 'Moderator:'). A human Moderator oversees "
    "the debate and may send guidance prefixed with 'Moderator:'. When you "
    "receive moderator guidance, follow it naturally — do not quote, echo, or "
    "explicitly acknowledge it. Write your response directly, without prefixing "
    "it with your own name."
)

_THINK_RE = re.compile(r"<think>[\s\S]*?</think>\s*")
_THINK_OPEN_RE = re.compile(r"<think>[\s\S]*$")


def strip_think_blocks(text: str) -> str:
    """Remove ``<think>…</think>`` reasoning blocks from model output.

    Handles both closed tags and an unclosed trailing ``<think>`` block
    (which can occur if the model is cut off mid-reasoning).
    """
    text = _THINK_RE.sub("", text)
    text = _THINK_OPEN_RE.sub("", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Domain model
# ---------------------------------------------------------------------------


@dataclass
class DebateAgent:
    """One side of the debate."""

    name: str
    model: str
    system_prompt: str
    server_url: str  # server URL — must be explicit (e.g. "http://localhost:11434")


@dataclass
class Debate:
    """A single debate between two LLM agents.

    Encapsulates state (history, turn tracking) and behaviour (message
    building, streaming turns, status reporting).
    """

    debate_id: str
    topic: str
    agents: list[DebateAgent]  # always 2 for MVP
    history: list[dict[str, str]] = field(default_factory=list)
    # history entries: {"role": "agent-0"|"agent-1"|"moderator", "name": str, "content": str}
    current_turn: int = 0  # index into agents
    status: str = "active"  # "active" | "ended"
    template_name: str = ""
    template_description: str = ""
    strip_think: bool = True  # strip <think> blocks from LLM messages
    save_filename: str = ""  # pre-set filename for /save and /end
    # Spec file fields
    spec_file: str = ""                              # filename of the spec used (if any)
    background_info: str = ""                        # from spec # Background section
    agent_instructions: dict[str, str] = field(default_factory=dict)  # name → guidelines
    max_rounds: int | None = None                    # from spec; None = unlimited

    # -- factories --------------------------------------------------------

    @classmethod
    def create(
        cls,
        topic: str,
        agent1_name: str = "Agent Alpha",
        agent2_name: str = "Agent Beta",
        model1: str = DEFAULT_MODEL,
        model2: str = DEFAULT_MODEL,
    ) -> Debate:
        """Build a new debate with two agents and pre-configured system prompts."""
        agents = [
            DebateAgent(
                name=agent1_name,
                model=model1,
                server_url=OLLAMA_DEFAULT_BASE_URL,
                system_prompt=(
                    f"You are {agent1_name}, a skilled debater. "
                    f"The debate topic is: \"{topic}\". "
                    f"You argue FOR the topic. Be concise but persuasive. "
                    f"Keep your responses to 2-3 paragraphs."
                ),
            ),
            DebateAgent(
                name=agent2_name,
                model=model2,
                server_url=OLLAMA_DEFAULT_BASE_URL,
                system_prompt=(
                    f"You are {agent2_name}, a skilled debater. "
                    f"The debate topic is: \"{topic}\". "
                    f"You argue AGAINST the topic. Be concise but persuasive. "
                    f"Keep your responses to 2-3 paragraphs."
                ),
            ),
        ]
        return cls(debate_id=str(uuid.uuid4()), topic=topic, agents=agents)

    @classmethod
    def from_template(
        cls,
        template_data: dict,
        topic: str,
        spec_file: str = "",
        background_info: str = "",
        agent_instructions: dict[str, str] | None = None,
        max_rounds: int | None = None,
    ) -> "Debate":
        """Create a new Debate from a parsed YAML template dict.

        Placeholders ``{topic}`` and ``{name}`` in system prompts are resolved.
        Optional spec data (background and per-agent instructions) can be
        provided when the debate was created from a spec file.
        """
        agents = []
        for agent_def in template_data["agents"]:
            resolved_prompt = agent_def["system_prompt"].format(
                topic=topic,
                name=agent_def["name"],
            )
            agents.append(DebateAgent(
                name=agent_def["name"],
                model=agent_def.get("model", DEFAULT_MODEL),
                server_url=agent_def.get("server_url", OLLAMA_DEFAULT_BASE_URL),
                system_prompt=resolved_prompt,
            ))
        return cls(
            debate_id=str(uuid.uuid4()),
            topic=topic,
            agents=agents,
            template_name=template_data.get("name", ""),
            template_description=template_data.get("description", ""),
            strip_think=template_data.get("strip_think", True),
            spec_file=spec_file,
            background_info=background_info,
            agent_instructions=agent_instructions or {},
            max_rounds=max_rounds,
        )

    @classmethod
    def from_dict(cls, data: dict) -> "Debate":
        """Reconstruct a Debate from a saved JSON dict."""
        template = data.get("template", {})
        agents = [
            DebateAgent(
                name=a["name"],
                model=a["model"],
                server_url=a.get("server_url", OLLAMA_DEFAULT_BASE_URL),
                system_prompt=a["system_prompt"],
            )
            for a in template.get("agents", data.get("agents", []))
        ]
        return cls(
            debate_id=data["debate_id"],
            topic=data["topic"],
            agents=agents,
            history=data.get("history", []),
            current_turn=data.get("current_turn", 0),
            status=data.get("status", "active"),
            template_name=template.get("name", ""),
            template_description=template.get("description", ""),
            strip_think=data.get("strip_think", True),
            save_filename=data.get("save_filename", ""),
            spec_file=data.get("spec_file", ""),
            background_info=data.get("background_info", ""),
            agent_instructions=data.get("agent_instructions", {}),
            max_rounds=data.get("max_rounds", None),
        )

    # -- properties -------------------------------------------------------

    @property
    def current_agent(self) -> DebateAgent:
        return self.agents[self.current_turn]

    @property
    def next_agent(self) -> DebateAgent:
        return self.agents[(self.current_turn + 1) % len(self.agents)]

    def find_agent_index(self, name: str) -> int | None:
        """Find an agent index by name (case-insensitive, longest match first)."""
        name_lower = name.lower()
        for i, agent in sorted(
            enumerate(self.agents), key=lambda x: -len(x[1].name),
        ):
            if agent.name.lower() == name_lower:
                return i
        return None

    def set_current_turn(self, agent_index: int) -> None:
        """Set the current turn to a specific agent."""
        self.current_turn = agent_index

    # -- state mutations --------------------------------------------------

    def _clean(self, text: str) -> str:
        """Optionally strip ``<think>`` blocks from text sent to the LLM."""
        return strip_think_blocks(text) if self.strip_think else text

    def build_messages(self, agent_index: int) -> list[dict[str, str]]:
        """Build Ollama chat messages from the perspective of one agent.

        The agent sees its own past messages as ``"assistant"`` and
        everything else (opponent + moderator) as ``"user"``.
        When ``strip_think`` is enabled, ``<think>`` reasoning blocks are
        removed so the LLM sees only the final argument text.
        """
        agent = self.agents[agent_index]
        agent_role_key = f"agent-{agent_index}"

        system_content = agent.system_prompt + _MODERATOR_CLAUSE
        if self.background_info:
            system_content += f"\n\nBackground:\n{self.background_info}"
        if agent.name in self.agent_instructions:
            system_content += f"\n\nYour specific role instructions:\n{self.agent_instructions[agent.name]}"
        messages = [{"role": "system", "content": system_content}]

        for entry in self.history:
            content = self._clean(entry["content"])
            if entry["role"] == agent_role_key:
                messages.append({"role": "assistant", "content": content})
            else:
                # Label every non-self message with the speaker's name so the
                # agent can unambiguously distinguish opponent from moderator.
                # The name is also carried as a separate field so LangChain can
                # pass it to providers (e.g. OpenAI, Anthropic) that support
                # out-of-band speaker identity via the message `name` field.
                name = entry["name"]
                messages.append({
                    "role": "user",
                    "content": f"{name}: {content}",
                    "name": name,
                })

        # On the very first turn there's no history yet — add a kickoff
        # user message so the LLM has something to respond to.
        if len(messages) == 1:
            messages.append({"role": "user", "content": f"Begin. The topic is: {self.topic}"})

        return messages

    def add_moderator_message(self, message: str) -> None:
        """Append a moderator injection to the history."""
        self.history.append({
            "role": "moderator",
            "name": "Moderator",
            "content": message,
        })

    def record_turn(self, agent_index: int, content: str) -> None:
        """Record an agent's response and advance the turn counter."""
        self.history.append({
            "role": f"agent-{agent_index}",
            "name": self.agents[agent_index].name,
            "content": content,
        })
        self.current_turn = (agent_index + 1) % len(self.agents)

    # -- serialization ----------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize the full debate state to a JSON-compatible dict."""
        return {
            "version": 1,
            "debate_id": self.debate_id,
            "topic": self.topic,
            "status": self.status,
            "current_turn": self.current_turn,
            "template": {
                "name": self.template_name,
                "description": self.template_description,
                "agents": [
                    {
                        "name": a.name,
                        "model": a.model,
                        "server_url": a.server_url,
                        "system_prompt": a.system_prompt,
                    }
                    for a in self.agents
                ],
            },
            "strip_think": self.strip_think,
            "save_filename": self.save_filename,
            "spec_file": self.spec_file,
            "background_info": self.background_info,
            "agent_instructions": dict(self.agent_instructions),
            "max_rounds": self.max_rounds,
            "history": list(self.history),
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }

    # -- queries ----------------------------------------------------------

    def status_dict(self) -> dict:
        """Return the full status payload."""
        return {
            "debate_id": self.debate_id,
            "topic": self.topic,
            "status": self.status,
            "current_turn": self.current_turn,
            "current_agent": self.current_agent.name,
            "turn_count": len(self.history),
            "agents": [{"name": a.name, "model": a.model} for a in self.agents],
            "history": [
                {
                    "role": h["role"],
                    "name": h["name"],
                    "content": h["content"][:100] + "..." if len(h["content"]) > 100 else h["content"],
                }
                for h in self.history
            ],
        }

    def stop(self) -> dict:
        """Mark the debate as ended and return a summary."""
        self.status = "ended"
        LOG.info("Debate ended: %s — %d turns", self.debate_id, len(self.history))
        return {
            "debate_id": self.debate_id,
            "status": "ended",
            "turn_count": len(self.history),
        }


# ---------------------------------------------------------------------------
# DebateEngine — wraps Debate + LangGraph graph for a single debate session
# ---------------------------------------------------------------------------


@dataclass
class DebateEngine:
    """Ties a ``Debate`` domain object to a compiled LangGraph graph.

    ``Debate`` handles history, serialisation, and transcript generation.
    The LangGraph graph handles turn routing and LLM orchestration.
    """

    debate: Debate
    graph: Any                  # langgraph CompiledGraph
    thread_config: dict         # {"configurable": {"thread_id": debate_id}}

    # -- convenience proxies ----------------------------------------------

    @property
    def debate_id(self) -> str:
        return self.debate.debate_id

    @property
    def status(self) -> str:
        return self.debate.status

    @property
    def agents(self):
        return self.debate.agents

    @property
    def history(self):
        return self.debate.history

    @property
    def save_filename(self) -> str:
        return self.debate.save_filename

    @property
    def current_agent(self) -> DebateAgent:
        return self.debate.current_agent

    @property
    def current_turn(self) -> int:
        return self.debate.current_turn

    def stop(self) -> dict:
        return self.debate.stop()

    # -- internal helpers -------------------------------------------------

    def _initial_state(self, targeted_speaker: str | None = None) -> dict:
        """Build the initial LangGraph state for this debate.

        For loaded debates (with existing history) the round_count is seeded
        from the number of *complete* rounds already recorded so max_rounds is
        enforced correctly.  A round is complete when all agents have spoken
        once (i.e. agent_turns // num_agents).

        ``current_speaker`` is set to the last *agent* turn's speaker so the
        RoundRobinRouter advances to the correct next speaker.  Moderator
        entries in history are skipped — they don't count as an agent turn.
        """
        agent_turns = [h for h in self.debate.history if h["role"] != "moderator"]
        last_agent_turn = next(
            (h for h in reversed(self.debate.history) if h["role"] != "moderator"),
            None,
        )
        last_agent_name = last_agent_turn["name"] if last_agent_turn else None
        num_agents = len(self.debate.agents)
        completed_rounds = len(agent_turns) // num_agents if num_agents else 0
        return {
            "debate_id": self.debate.debate_id,
            "current_speaker": last_agent_name,
            "targeted_speaker": targeted_speaker,
            "round_count": completed_rounds,
            "next_action": "speak",
            "status": self.debate.status,
            "main_flow_speaker": None,
        }

    def _run_config(self, queue: SSEQueue, info: RequestInfo) -> dict:
        return {
            "configurable": {
                **self.thread_config["configurable"],
                "debate": self.debate,
                "sse_queue": queue,
                "request_info": info,
            }
        }

    # -- public API -------------------------------------------------------

    async def run_turn(
        self,
        queue: SSEQueue,
        info: RequestInfo,
        extra_result: dict | None = None,
        targeted_speaker: str | None = None,
    ) -> None:
        """Invoke the LangGraph graph for one agent turn.

        Streams tokens to *queue* via ``notifications/debate.token``, then
        puts a final ``JSONRPCResponse`` with the turn summary.

        On the first invocation for this debate the graph is initialised with
        the current debate state (supports resumed/loaded debates).
        On subsequent invocations the graph resumes from its last interrupt.
        """
        run_config = self._run_config(queue, info)

        try:
            current = self.graph.get_state(self.thread_config)
            if not current.values:
                # First invocation — initialise graph state
                await self.graph.ainvoke(
                    self._initial_state(targeted_speaker), config=run_config
                )
            else:
                # Resume from last interrupt_after=["agent_turn"] pause
                if targeted_speaker:
                    await self.graph.aupdate_state(
                        self.thread_config, {"targeted_speaker": targeted_speaker}
                    )
                await self.graph.ainvoke(None, config=run_config)
        except Exception:
            LOG.exception("Graph invocation failed for debate %s", self.debate_id)
            await queue.put(JSONRPCResponse(
                id=info.id, result={"error": "Internal engine error — see server logs"}
            ))
            return

        # Check if the router decided to end the debate (e.g. max_rounds reached).
        # When the graph goes router → END without calling agent_turn, no tokens
        # were streamed and the debate should be marked as ended.
        final_state = self.graph.get_state(self.thread_config)
        debate_ended = final_state.values.get("next_action") == "end"
        if debate_ended:
            self.debate.stop()

        result: dict = {
            "status": "turn_complete",
            "agent": self.debate.history[-1]["name"] if self.debate.history else "",
            "next_agent": self.debate.current_agent.name,
            "turn_count": len(self.debate.history),
            "debate_ended": debate_ended,
        }
        if extra_result:
            result.update(extra_result)
        await queue.put(JSONRPCResponse(id=info.id, result=result))


# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------


class _EngineDict(dict):
    """Dict that auto-wraps bare ``Debate`` objects as ``DebateEngine``.

    Allows test code that does ``_debates[id] = debate`` to continue working
    without modification — the ``Debate`` is silently wrapped in a default
    ``DebateEngine`` on insertion.
    """

    def __setitem__(self, key: str, value: object) -> None:
        if isinstance(value, Debate) and not isinstance(value, DebateEngine):
            value = _make_engine_default(value)
        super().__setitem__(key, value)


_engines: _EngineDict = _EngineDict()

# Alias so legacy code / tests that import ``_debates`` still work.
_debates = _engines


def _make_engine(debate: Debate, template_data: dict) -> DebateEngine:
    """Create a ``DebateEngine`` from a ``Debate`` and raw template dict."""
    template_config = TemplateConfig.from_template_dict(template_data)
    template_config.max_rounds = debate.max_rounds  # spec overrides template
    graph = get_graph(template_config)
    thread_config = {"configurable": {"thread_id": debate.debate_id}}
    return DebateEngine(debate=debate, graph=graph, thread_config=thread_config)


def _make_engine_default(debate: Debate) -> DebateEngine:
    """Create a ``DebateEngine`` for a loaded debate using default config."""
    template_config = TemplateConfig(name=debate.template_name or "", max_rounds=debate.max_rounds)
    graph = get_graph(template_config)
    thread_config = {"configurable": {"thread_id": debate.debate_id}}
    return DebateEngine(debate=debate, graph=graph, thread_config=thread_config)


def _parse_target(message: str, engine: DebateEngine) -> tuple[int | None, str]:
    """Parse an ``@AgentName`` prefix from *message*.

    Returns ``(agent_index, remaining_message)``.  If no ``@`` prefix
    matches a known agent, returns ``(None, original_message)``.
    """
    stripped = message.strip()
    if not stripped.startswith("@"):
        return None, message
    for i, agent in sorted(
        enumerate(engine.agents), key=lambda x: -len(x[1].name),
    ):
        prefix = f"@{agent.name}"
        if stripped.lower().startswith(prefix.lower()):
            remainder = stripped[len(prefix):].strip()
            return i, remainder
    return None, message


async def _error_queue(info: RequestInfo, message: str) -> SSEQueue:
    """Return a queue pre-loaded with a single error response."""
    queue: SSEQueue = asyncio.Queue()
    await queue.put(JSONRPCResponse(id=info.id, result={"error": message}))
    return queue


# ---------------------------------------------------------------------------
# JSON-RPC handlers
# ---------------------------------------------------------------------------


@jrpc_service.request("debate.start")
async def debate_start(
    info: RequestInfo,
    topic: str,
    agent1_model: str | None = None,
    agent2_model: str | None = None,
    agent1_name: str = "Agent Alpha",
    agent2_name: str = "Agent Beta",
) -> dict:
    """Start a new debate between two agents on the given topic."""
    debate = Debate.create(
        topic=topic,
        agent1_name=agent1_name,
        agent2_name=agent2_name,
        model1=agent1_model or DEFAULT_MODEL,
        model2=agent2_model or DEFAULT_MODEL,
    )
    # Build a minimal template dict so _make_engine can parse it
    template_data = {
        "name": "",
        "agents": [{"name": a.name, "model": a.model, "system_prompt": a.system_prompt}
                   for a in debate.agents],
    }
    engine = _make_engine(debate, template_data)
    _engines[engine.debate_id] = engine

    LOG.info("Debate started: %s — topic=%r", debate.debate_id, topic)
    return {
        "debate_id": debate.debate_id,
        "topic": topic,
        "agents": [{"name": a.name, "model": a.model} for a in debate.agents],
        "status": debate.status,
    }


@jrpc_service.request("debate.next_turn")
async def debate_next_turn(
    info: RequestInfo,
    debate_id: str,
) -> SSEQueue:
    """Trigger the next agent's turn and stream the response."""
    engine = _engines.get(debate_id)
    if engine is None:
        return await _error_queue(info, "Debate not found")
    if engine.status != "active":
        return await _error_queue(info, f"Debate is {engine.status}")

    queue: SSEQueue = asyncio.Queue()
    asyncio.create_task(engine.run_turn(queue, info))
    return queue


@jrpc_service.request("debate.inject")
async def debate_inject(
    info: RequestInfo,
    debate_id: str,
    message: str,
) -> SSEQueue:
    """Moderator injects a message and the current agent responds.

    If the message starts with ``@AgentName``, only that agent responds
    (targeted mode).  Otherwise the current agent responds and the
    response includes ``"mode": "round"`` so the frontend can chain
    a second turn for the other agent.
    """
    engine = _engines.get(debate_id)
    if engine is None:
        return await _error_queue(info, "Debate not found")
    if engine.status != "active":
        return await _error_queue(info, f"Debate is {engine.status}")

    # Parse @Agent targeting
    target_index, clean_message = _parse_target(message, engine)

    if target_index is not None:
        if not clean_message:
            return await _error_queue(info, "Message body is empty after @Agent prefix")
        targeted_speaker = engine.agents[target_index].name
        targeted = True
    else:
        targeted_speaker = None
        targeted = False

    engine.debate.add_moderator_message(clean_message)

    extra = {"mode": "targeted" if targeted else "round"}
    queue: SSEQueue = asyncio.Queue()
    asyncio.create_task(engine.run_turn(
        queue, info, extra_result=extra, targeted_speaker=targeted_speaker
    ))
    return queue


@jrpc_service.request("debate.status")
async def debate_status(
    info: RequestInfo,
    debate_id: str,
) -> dict:
    """Get the current state of a debate."""
    engine = _engines.get(debate_id)
    if engine is None:
        return {"error": "Debate not found"}
    return engine.debate.status_dict()


@jrpc_service.request("debate.stop")
async def debate_stop(
    info: RequestInfo,
    debate_id: str,
) -> dict:
    """End a debate."""
    engine = _engines.get(debate_id)
    if engine is None:
        return {"error": "Debate not found"}
    return engine.stop()


@jrpc_service.request("debate.announce")
async def debate_announce(
    info: RequestInfo,
    debate_id: str,
    message: str,
) -> dict:
    """Record a moderator announcement without triggering any agent response.

    Use this to add an opening statement or other moderator message to the
    debate history without causing any agent to speak.
    """
    engine = _engines.get(debate_id)
    if engine is None:
        return {"error": "Debate not found"}
    engine.debate.add_moderator_message(message)
    return {"status": "ok", "debate_id": debate_id}
