from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime

from pyview import LiveView, LiveViewSocket, ConnectedLiveViewSocket, is_connected
from pyview.events import InfoEvent

from jrpc_common.jrpc_model import (
    JSONRPCNotification,
    JSONRPCResponse,
    JSONRPCErrorResponse,
)
from debate_bff.services.rpc_client import ChatRPCClient
from debate_bff import transcript_store

LOG = logging.getLogger(__name__)


def _extract_str(payload: dict, key: str) -> str:
    """Extract a string value from a payload that may contain lists."""
    value = payload.get(key, "")
    if isinstance(value, list):
        value = value[0] if value else ""
    return (value or "").strip()


@dataclass
class ChatMessage:
    """A single message in the chat."""

    id: str
    role: str  # "user", "agent", "system"
    sender_name: str
    content: str
    timestamp: str
    is_streaming: bool = False
    link_url: str = ""
    link_label: str = ""


@dataclass
class ChatContext:
    """State for the chat UI."""

    messages: list[ChatMessage] = field(default_factory=list)
    input_text: str = ""
    is_connected: bool = False
    session_id: str | None = None
    status: str = "idle"  # "idle", "streaming", "error"
    next_id: int = 1
    error_message: str = ""
    # Generic session metadata (application-populated)
    session_title: str = ""           # shown as header subtitle
    status_bar: list[dict] = field(default_factory=list)  # [{"label": str, "value": str}]
    # Debate state (internal — not referenced directly in template)
    debate_id: str | None = None
    debate_topic: str = ""
    debate_agents: list[dict] = field(default_factory=list)
    current_agent: str = ""
    turn_count: int = 0        # len(history) from backend — includes moderator entries
    agent_turn_count: int = 0  # count of agent-only turns, used for bubble labels
    in_side_conversation: bool = False  # True after a targeted @Agent turn
    debate_ended: bool = False          # True when max_rounds reached or debate stopped
    debate_max_rounds: int | None = None  # max rounds configured for this debate
    debate_template: str = ""           # template name used to create this debate
    debate_spec_file: str = ""          # spec file used (empty if none)


class ChatLiveView(LiveView[ChatContext]):
    """Application-agnostic chat UI that communicates with a backend via JSON-RPC."""

    def __init__(self):
        super().__init__()
        self._rpc_client: ChatRPCClient | None = None

    async def mount(self, socket: LiveViewSocket[ChatContext], session):
        socket.context = ChatContext()

        if is_connected(socket):
            socket.schedule_info_once(InfoEvent("connect_backend"))

    async def handle_event(self, event, payload, socket: LiveViewSocket[ChatContext]):
        ctx = socket.context
        if event == "send_message":
            text = _extract_str(payload, "message")
            if not text or ctx.status == "streaming":
                return

            ctx.input_text = ""

            # Slash commands: don't add a user message, just dispatch
            if text.startswith("/"):
                if not is_connected(socket) or not ctx.is_connected:
                    self._add_system_message(ctx, "Not connected to backend")
                    return
                socket.schedule_info_once(InfoEvent("debate_command", {
                    "command": text,
                }))
                return

            # Regular message — add user bubble
            in_debate = bool(ctx.is_connected and ctx.debate_id)
            msg = ChatMessage(
                id=str(ctx.next_id),
                role="user",
                sender_name="Moderator" if in_debate else "You",
                content=text,
                timestamp=datetime.now().strftime("%H:%M"),
            )
            ctx.messages.append(msg)
            ctx.next_id += 1

            if not is_connected(socket):
                return

            if ctx.is_connected and ctx.debate_id:
                # In a debate: targeted (@Agent) messages auto-respond;
                # untagged messages are recorded only (user clicks Next Turn).
                if text.startswith("@"):
                    # Resolve the targeted agent up-front so the placeholder
                    # bubble shows the correct name even while streaming.
                    responding_agent = ctx.current_agent
                    text_lower = text.lower()
                    for agent in ctx.debate_agents:
                        if text_lower.startswith(f"@{agent['name'].lower()}"):
                            responding_agent = agent["name"]
                            break
                    ctx.status = "streaming"
                    agent_msg = self._add_debate_turn_placeholder(ctx, responding_agent)
                    socket.schedule_info_once(InfoEvent("debate_inject", {
                        "msg_id": agent_msg.id,
                        "message": text,
                    }))
                else:
                    # Untagged — record only; user clicks Next Turn to advance
                    socket.schedule_info_once(InfoEvent("debate_announce", {
                        "message": text,
                    }))
            elif ctx.is_connected:
                # Connected but no active debate — don't echo
                self._add_system_message(
                    ctx, "No active debate. Use /new -t <template> <topic> to start one."
                )
            else:
                # Not connected: simulate
                ctx.status = "streaming"
                agent_msg = self._add_agent_placeholder(ctx, "Agent")
                socket.schedule_info_once(InfoEvent("simulate_stream", {
                    "msg_id": agent_msg.id,
                    "prompt": text,
                }))

        elif event == "update_input":
            ctx.input_text = _extract_str(payload, "message") or _extract_str(payload, "value")

        elif event == "connect":
            socket.schedule_info_once(InfoEvent("connect_backend"))

        elif event == "next_turn":
            if ctx.status == "streaming" or not ctx.debate_id or ctx.debate_ended:
                return
            ctx.in_side_conversation = False
            ctx.status = "streaming"
            agent_msg = self._add_debate_turn_placeholder(ctx, ctx.current_agent)
            socket.schedule_info_once(InfoEvent("debate_next_turn", {"msg_id": agent_msg.id}))

        elif event == "resume_debate":
            if ctx.status == "streaming" or not ctx.debate_id or ctx.debate_ended:
                return
            ctx.in_side_conversation = False
            ctx.status = "streaming"
            agent_msg = self._add_debate_turn_placeholder(ctx, ctx.current_agent)
            socket.schedule_info_once(InfoEvent("debate_next_turn", {"msg_id": agent_msg.id}))

        elif event == "end_debate":
            if ctx.debate_id and ctx.is_connected:
                socket.schedule_info_once(InfoEvent("debate_command", {
                    "command": "/end",
                }))

    async def handle_info(self, event: InfoEvent, socket: ConnectedLiveViewSocket[ChatContext]):
        ctx = socket.context

        if event.name == "connect_backend":
            await self._do_connect(socket)

        elif event.name == "send_to_backend":
            await self._do_send_generic(event.payload, socket)

        elif event.name == "simulate_stream":
            await self._do_simulate_stream(event.payload, socket)

        elif event.name == "debate_command":
            await self._do_debate_command(event.payload, socket)

        elif event.name == "debate_next_turn":
            await self._do_debate_next_turn(event.payload, socket)

        elif event.name == "debate_inject":
            await self._do_debate_inject(event.payload, socket)

        elif event.name == "debate_announce":
            await self._do_debate_announce(event.payload, socket)

        elif event.name == "debate_continue":
            await self._do_debate_continue(event.payload, socket)

        elif event.name == "stream_error":
            msg_id = event.payload.get("msg_id")
            error = event.payload.get("error", "Unknown error")
            if msg_id:
                for msg in ctx.messages:
                    if msg.id == msg_id:
                        msg.content = f"Error: {error}"
                        msg.is_streaming = False
                        break
            ctx.status = "idle"
            ctx.error_message = error

        elif event.name == "_noop":
            pass

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _add_agent_placeholder(self, ctx: ChatContext, sender_name: str) -> ChatMessage:
        """Add an empty agent message placeholder for streaming."""
        agent_msg = ChatMessage(
            id=str(ctx.next_id),
            role="agent",
            sender_name=sender_name,
            content="",
            timestamp=datetime.now().strftime("%H:%M"),
            is_streaming=True,
        )
        ctx.messages.append(agent_msg)
        ctx.next_id += 1
        return agent_msg

    def _add_system_message(self, ctx: ChatContext, content: str) -> None:
        """Add a system message to the chat."""
        ctx.messages.append(ChatMessage(
            id=str(ctx.next_id),
            role="system",
            sender_name="System",
            content=content,
            timestamp=datetime.now().strftime("%H:%M"),
        ))
        ctx.next_id += 1

    def _add_debate_turn_placeholder(self, ctx: ChatContext, agent_name: str) -> ChatMessage:
        """Add a streaming placeholder whose label includes the agent-turn number.

        The turn counter increments here — before the response arrives — so the
        bubble label matches the turn that is about to be recorded.
        """
        ctx.agent_turn_count += 1
        return self._add_agent_placeholder(ctx, f"{agent_name} · {ctx.agent_turn_count}")

    def _handle_debate_ended(self, ctx: ChatContext, msg_id: str) -> None:
        """Remove the empty placeholder bubble and mark the debate as complete."""
        ctx.messages = [m for m in ctx.messages if m.id != msg_id]
        ctx.agent_turn_count -= 1
        ctx.debate_ended = True
        self._add_system_message(
            ctx, "Debate complete — max rounds reached. Use /end to save."
        )

    def _update_status_bar(self, ctx: ChatContext) -> None:
        """Rebuild the generic status bar from current session state.

        Populated by the debate application; cleared when no session is active.
        Other applications can call this with different items.
        """
        if not ctx.debate_id:
            ctx.status_bar = []
            return
        items = []
        if ctx.debate_template:
            items.append({"label": "Template", "value": ctx.debate_template})
        if ctx.debate_spec_file:
            items.append({"label": "Spec", "value": ctx.debate_spec_file})
        num_agents = len(ctx.debate_agents) if ctx.debate_agents else 1
        rounds_done = ctx.agent_turn_count // num_agents if num_agents else 0
        if ctx.debate_max_rounds is not None:
            round_value = f"{rounds_done} / {ctx.debate_max_rounds}"
        else:
            round_value = str(rounds_done)
        items.append({"label": "Round", "value": round_value})
        ctx.status_bar = items

    # ------------------------------------------------------------------
    # Backend connection
    # ------------------------------------------------------------------

    async def _do_connect(self, socket: ConnectedLiveViewSocket[ChatContext]) -> None:
        ctx = socket.context
        try:
            self._rpc_client = ChatRPCClient()
            session_id = await self._rpc_client.connect()
            ctx.is_connected = True
            ctx.session_id = session_id
            ctx.error_message = ""
            LOG.info("Backend connected — session_id=%s", session_id)
        except Exception as e:
            LOG.warning("Backend connection failed: %s", e)
            ctx.is_connected = False
            ctx.error_message = str(e)
            self._rpc_client = None

    # ------------------------------------------------------------------
    # Generic backend request (echo, etc.)
    # ------------------------------------------------------------------

    async def _do_send_generic(
        self, payload: dict, socket: ConnectedLiveViewSocket[ChatContext],
    ) -> None:
        ctx = socket.context
        msg_id = payload["msg_id"]
        text = payload["text"]

        if self._rpc_client is None or not self._rpc_client.is_connected:
            socket.schedule_info_once(
                InfoEvent("stream_error", {"msg_id": msg_id, "error": "Not connected"})
            )
            return

        try:
            async for rpc_msg in self._rpc_client.send_request("echo", {"message": text}):
                if isinstance(rpc_msg, JSONRPCResponse):
                    result = rpc_msg.result
                    response_text = result.get("message", str(result)) if isinstance(result, dict) else str(result)
                    for msg in ctx.messages:
                        if msg.id == msg_id:
                            if not msg.content:
                                msg.content = response_text
                            msg.is_streaming = False
                            break
                    ctx.status = "idle"
                elif isinstance(rpc_msg, JSONRPCErrorResponse):
                    error_msg = rpc_msg.error.message if rpc_msg.error else "Unknown error"
                    socket.schedule_info_once(
                        InfoEvent("stream_error", {"msg_id": msg_id, "error": error_msg})
                    )
                    return
        except Exception as e:
            LOG.exception("Backend request failed")
            socket.schedule_info_once(
                InfoEvent("stream_error", {"msg_id": msg_id, "error": str(e)})
            )

    # ------------------------------------------------------------------
    # Debate operations
    # ------------------------------------------------------------------

    async def _do_debate_command(
        self, payload: dict, socket: ConnectedLiveViewSocket[ChatContext],
    ) -> None:
        """Dispatch a slash command to the backend debate.command RPC method."""
        ctx = socket.context
        command = payload["command"]

        if self._rpc_client is None or not self._rpc_client.is_connected:
            self._add_system_message(ctx, "Not connected to backend")
            return

        params = {"command": command, "debate_id": ctx.debate_id}

        try:
            async for rpc_msg in self._rpc_client.send_request("debate.command", params):
                if isinstance(rpc_msg, JSONRPCResponse) and isinstance(rpc_msg.result, dict):
                    result = rpc_msg.result
                    cmd = result.get("command", "")

                    if cmd == "new":
                        ctx.debate_id = result["debate_id"]
                        ctx.debate_topic = result["topic"]
                        ctx.debate_agents = result["agents"]
                        ctx.current_agent = ctx.debate_agents[0]["name"] if ctx.debate_agents else ""
                        ctx.turn_count = 0
                        ctx.agent_turn_count = 0
                        ctx.debate_ended = False
                        ctx.debate_max_rounds = result.get("max_rounds")
                        ctx.debate_template = result.get("template_name", "")
                        ctx.debate_spec_file = result.get("spec_file", "")
                        ctx.session_title = result["topic"]
                        self._update_status_bar(ctx)
                        agents_str = " vs ".join(a["name"] for a in ctx.debate_agents)
                        self._add_system_message(
                            ctx,
                            f"Debate started: \"{result['topic']}\" — {agents_str}"
                        )
                        # Auto-generate a moderator opening and persist it in
                        # backend history so agents are aware of it.
                        debaters = " and ".join(a["name"] for a in ctx.debate_agents)
                        spec_note = ""
                        if result.get("spec_file"):
                            spec_note = f" Background and guidelines loaded from: {result['spec_file']}."
                        announcement = (
                            f"Welcome to today's debate on the topic: \"{result['topic']}\". "
                            f"Our debaters are {debaters}."
                            f"{spec_note} "
                            f"Please keep your arguments concise and respectful. "
                            f"Let the debate begin!"
                        )
                        ctx.messages.append(ChatMessage(
                            id=str(ctx.next_id),
                            role="user",
                            sender_name="Moderator",
                            content=announcement,
                            timestamp=datetime.now().strftime("%H:%M"),
                        ))
                        ctx.next_id += 1
                        if self._rpc_client is not None:
                            async for _ in self._rpc_client.send_request(
                                "debate.announce",
                                {"debate_id": result["debate_id"], "message": announcement},
                            ):
                                pass

                    elif cmd == "load":
                        ctx.debate_id = result["debate_id"]
                        ctx.debate_topic = result["topic"]
                        ctx.debate_agents = result["agents"]
                        ctx.current_agent = result.get("current_agent", "")
                        ctx.turn_count = result.get("history_count", 0)
                        ctx.agent_turn_count = sum(
                            1 for e in result.get("history", [])
                            if e.get("role", "").startswith("agent-")
                        )
                        ctx.debate_ended = result.get("status") == "ended"
                        ctx.debate_max_rounds = result.get("max_rounds")
                        ctx.debate_template = result.get("template_name", "")
                        ctx.debate_spec_file = result.get("spec_file", "")
                        ctx.session_title = result["topic"]
                        self._update_status_bar(ctx)
                        # Populate chat with history from the loaded debate
                        ctx.messages = []
                        ctx.next_id = 1
                        for entry in result.get("history", []):
                            content = entry.get("content", "")
                            if not content:
                                continue
                            sender = entry.get("name", "Agent")
                            ctx.messages.append(ChatMessage(
                                id=str(ctx.next_id),
                                role="agent",
                                sender_name=sender,
                                content=content,
                                timestamp="",
                            ))
                            ctx.next_id += 1
                        self._add_system_message(
                            ctx,
                            f"Loaded debate: \"{result['topic']}\" "
                            f"({result['history_count']} turns)"
                        )

                    elif cmd in ("save", "save_as"):
                        self._add_system_message(
                            ctx, f"Debate saved as \"{result['filename']}\""
                        )

                    elif cmd == "end":
                        self._add_system_message(
                            ctx,
                            f"Debate ended and saved as \"{result['filename']}\" "
                            f"({result['turn_count']} turns)"
                        )
                        ctx.debate_id = None
                        ctx.debate_topic = ""
                        ctx.debate_agents = []
                        ctx.current_agent = ""
                        ctx.turn_count = 0
                        ctx.agent_turn_count = 0
                        ctx.in_side_conversation = False
                        ctx.debate_ended = False
                        ctx.debate_max_rounds = None
                        ctx.debate_template = ""
                        ctx.debate_spec_file = ""
                        ctx.session_title = ""
                        self._update_status_bar(ctx)

                    elif cmd == "templates":
                        lines = ["Available templates:"]
                        for t in result["templates"]:
                            lines.append(f"  {t['name']}  —  {t['description']}")
                        self._add_system_message(ctx, "\n".join(lines))

                    elif cmd == "template":
                        self._add_system_message(
                            ctx, f"Template: {result['name']}\n\n{result['content']}"
                        )

                    elif cmd == "specs":
                        if not result["specs"]:
                            self._add_system_message(ctx, "No spec files found.")
                        else:
                            lines = ["Available spec files:"]
                            for s in result["specs"]:
                                lines.append(f"  {s['filename']}  —  {s['topic']}")
                            self._add_system_message(ctx, "\n".join(lines))

                    elif cmd == "debates":
                        if not result["debates"]:
                            self._add_system_message(ctx, "No saved debates found.")
                        else:
                            lines = ["Saved debates:"]
                            for d in result["debates"]:
                                lines.append(
                                    f"  {d['filename']}  —  \"{d['topic']}\" "
                                    f"({d['turn_count']} turns)"
                                )
                            self._add_system_message(ctx, "\n".join(lines))

                    elif cmd == "debate":
                        lines = [
                            f"Debate: \"{result['topic']}\"",
                            f"Status: {result['status']}",
                        ]
                        if result.get("template_name"):
                            lines.append(f"Template: {result['template_name']}")
                        if result.get("spec_file"):
                            lines.append(f"Spec: {result['spec_file']}")
                        agents_str = ", ".join(a["name"] for a in result.get("agents", []))
                        lines.append(f"Agents: {agents_str}")
                        lines.append(f"Turns: {result['history_count']}")
                        for entry in result.get("history", []):
                            content = entry.get("content", "")
                            if not content:
                                continue
                            name = entry.get("name", "Agent")
                            lines.append(f"\n--- {name} ---")
                            lines.append(content)
                        self._add_system_message(ctx, "\n".join(lines))

                    elif cmd == "spec":
                        self._add_system_message(
                            ctx, f"Spec: {result['filename']}\n\n{result['content']}"
                        )

                    elif cmd in ("help", "config"):
                        self._add_system_message(ctx, result.get("text", ""))

                    elif cmd == "transcript":
                        debate_id = result["debate_id"]
                        transcript_store.transcripts[debate_id] = (
                            result["content"],
                            result.get("format", "markdown"),
                        )
                        url = f"/transcript/{debate_id}"
                        msg = ChatMessage(
                            id=str(ctx.next_id),
                            role="system",
                            sender_name="System",
                            content=f"Transcript for \"{result['topic']}\"",
                            timestamp=datetime.now().strftime("%H:%M"),
                            link_url=url,
                            link_label="Open Transcript",
                        )
                        ctx.messages.append(msg)
                        ctx.next_id += 1

                    elif cmd == "continue":
                        rounds = result.get("rounds", 1)
                        total_turns = rounds * 2
                        self._add_system_message(
                            ctx,
                            f"Running {rounds} round(s) ({total_turns} turns)..."
                        )
                        ctx.status = "streaming"
                        agent_msg = self._add_debate_turn_placeholder(ctx, ctx.current_agent)
                        socket.schedule_info_once(InfoEvent("debate_continue", {
                            "msg_id": agent_msg.id,
                            "remaining_turns": total_turns,
                        }))

                    elif cmd == "error":
                        self._add_system_message(ctx, f"Error: {result['message']}")

                elif isinstance(rpc_msg, JSONRPCErrorResponse):
                    error_msg = rpc_msg.error.message if rpc_msg.error else "Command failed"
                    self._add_system_message(ctx, f"Error: {error_msg}")
        except Exception as e:
            LOG.exception("debate.command failed")
            self._add_system_message(ctx, f"Error: {e}")

    async def _do_debate_streaming(
        self, method: str, params: dict, msg_id: str,
        socket: ConnectedLiveViewSocket[ChatContext],
    ) -> dict | None:
        """Common handler for debate.next_turn and debate.inject — both stream tokens.

        Returns the final result dict from the JSONRPCResponse, or None on error.
        """
        ctx = socket.context

        if self._rpc_client is None or not self._rpc_client.is_connected:
            socket.schedule_info_once(
                InfoEvent("stream_error", {"msg_id": msg_id, "error": "Not connected"})
            )
            return None

        try:
            async for rpc_msg in self._rpc_client.send_request(method, params):
                if isinstance(rpc_msg, JSONRPCNotification):
                    if rpc_msg.params and isinstance(rpc_msg.params, dict):
                        token = rpc_msg.params.get("token", "")
                        if token:
                            for msg in ctx.messages:
                                if msg.id == msg_id:
                                    msg.content += token
                                    break

                elif isinstance(rpc_msg, JSONRPCResponse):
                    result = rpc_msg.result if isinstance(rpc_msg.result, dict) else {}
                    ctx.current_agent = result.get("next_agent", "")
                    ctx.turn_count = result.get("turn_count", ctx.turn_count)
                    self._update_status_bar(ctx)
                    for msg in ctx.messages:
                        if msg.id == msg_id:
                            msg.is_streaming = False
                            break
                    ctx.status = "idle"
                    return result

                elif isinstance(rpc_msg, JSONRPCErrorResponse):
                    error_msg = rpc_msg.error.message if rpc_msg.error else "Unknown error"
                    socket.schedule_info_once(
                        InfoEvent("stream_error", {"msg_id": msg_id, "error": error_msg})
                    )
                    return None

        except Exception as e:
            LOG.exception("%s failed", method)
            socket.schedule_info_once(
                InfoEvent("stream_error", {"msg_id": msg_id, "error": str(e)})
            )
        return None

    async def _do_debate_next_turn(
        self, payload: dict, socket: ConnectedLiveViewSocket[ChatContext],
    ) -> None:
        ctx = socket.context
        msg_id = payload["msg_id"]
        result = await self._do_debate_streaming(
            "debate.next_turn",
            {"debate_id": ctx.debate_id},
            msg_id,
            socket,
        )
        if result and result.get("debate_ended"):
            self._handle_debate_ended(ctx, msg_id)

    async def _do_debate_inject(
        self, payload: dict, socket: ConnectedLiveViewSocket[ChatContext],
    ) -> None:
        ctx = socket.context
        # Preserve current_agent so the Resume button shows the correct main-flow
        # speaker rather than whoever follows the targeted agent in the rotation.
        main_flow_agent = ctx.current_agent
        result = await self._do_debate_streaming(
            "debate.inject",
            {"debate_id": ctx.debate_id, "message": payload["message"]},
            payload["msg_id"],
            socket,
        )
        if result:
            ctx.in_side_conversation = True
            ctx.current_agent = main_flow_agent

    async def _do_debate_announce(
        self, payload: dict, socket: ConnectedLiveViewSocket[ChatContext],
    ) -> None:
        """Record an untagged moderator message via debate.announce (no agent response)."""
        ctx = socket.context
        if self._rpc_client is None or not self._rpc_client.is_connected:
            return
        try:
            async for _ in self._rpc_client.send_request(
                "debate.announce",
                {"debate_id": ctx.debate_id, "message": payload["message"]},
            ):
                pass
        except Exception:
            LOG.exception("debate.announce failed")
        ctx.status = "idle"

    async def _do_debate_continue(
        self, payload: dict, socket: ConnectedLiveViewSocket[ChatContext],
    ) -> None:
        """Run one turn of a /continue sequence, then chain the next if remaining."""
        ctx = socket.context
        msg_id = payload["msg_id"]
        remaining = payload["remaining_turns"]

        result = await self._do_debate_streaming(
            "debate.next_turn",
            {"debate_id": ctx.debate_id},
            msg_id,
            socket,
        )

        remaining -= 1

        if result and result.get("debate_ended"):
            self._handle_debate_ended(ctx, msg_id)
            return

        if remaining > 0 and result and ctx.debate_id:
            next_agent = result.get("next_agent", ctx.current_agent)
            ctx.status = "streaming"
            agent_msg = self._add_debate_turn_placeholder(ctx, next_agent)
            socket.schedule_info_once(InfoEvent("debate_continue", {
                "msg_id": agent_msg.id,
                "remaining_turns": remaining,
            }))
        elif remaining == 0:
            self._add_system_message(ctx, "Continue rounds complete.")

    # ------------------------------------------------------------------
    # Local simulation (fallback)
    # ------------------------------------------------------------------

    async def _do_simulate_stream(
        self, payload: dict, socket: ConnectedLiveViewSocket[ChatContext],
    ) -> None:
        ctx = socket.context
        msg_id = payload["msg_id"]
        prompt = payload["prompt"]
        response_text = (
            f'I received your message: "{prompt}". '
            f"This is a simulated response (backend not connected)."
        )
        words = response_text.split(" ")

        for i, word in enumerate(words):
            for msg in ctx.messages:
                if msg.id == msg_id:
                    msg.content += (" " if msg.content else "") + word
                    break
            await asyncio.sleep(0.05)
            if i < len(words) - 1:
                socket.schedule_info_once(InfoEvent("_noop"))

        for msg in ctx.messages:
            if msg.id == msg_id:
                msg.is_streaming = False
                break
        ctx.status = "idle"

    async def disconnect(self, socket: ConnectedLiveViewSocket[ChatContext]):
        if self._rpc_client is not None:
            try:
                await self._rpc_client.disconnect()
            except Exception:
                pass
            self._rpc_client = None
