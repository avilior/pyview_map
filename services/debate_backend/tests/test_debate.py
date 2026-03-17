"""Tests for the Debate domain class."""

from __future__ import annotations

import asyncio
from unittest.mock import patch


from unittest.mock import MagicMock

from debate_backend.debate import (
    Debate,
    DebateEngine,
    DEFAULT_MODEL,
    _MODERATOR_CLAUSE,
    _make_engine,
    _parse_target,
)
from http_stream_transport.jsonrpc.handler_meta import RequestInfo
from http_stream_transport.jsonrpc.jrpc_service import SSEQueue
from jrpc_common.jrpc_model import JSONRPCNotification, JSONRPCResponse


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_debate(**kwargs) -> Debate:
    defaults = dict(topic="Tabs vs spaces", agent1_name="Alice", agent2_name="Bob")
    defaults.update(kwargs)
    return Debate.create(**defaults)


def _make_debate_engine(**kwargs) -> DebateEngine:
    """Create a DebateEngine backed by the given debate kwargs."""
    debate = _make_debate(**kwargs)
    template_data = {
        "name": "test",
        "agents": [
            {"name": a.name, "model": a.model, "system_prompt": a.system_prompt}
            for a in debate.agents
        ],
    }
    return _make_engine(debate, template_data)


def _fake_llm(tokens: list[str]):
    """Return a mock LangChain LLM that streams the given tokens."""
    class _FakeLLM:
        async def astream(self, messages):
            for tok in tokens:
                yield MagicMock(content=tok)
    return _FakeLLM()


def _make_info(request_id: int = 1) -> RequestInfo:
    return RequestInfo(id=request_id, method="test")


# ---------------------------------------------------------------------------
# Creation
# ---------------------------------------------------------------------------


def test_create_defaults():
    d = Debate.create(topic="AI ethics")
    assert d.topic == "AI ethics"
    assert len(d.agents) == 2
    assert d.agents[0].name == "Agent Alpha"
    assert d.agents[1].name == "Agent Beta"
    assert d.agents[0].model == DEFAULT_MODEL
    assert d.current_turn == 0
    assert d.status == "active"
    assert d.history == []
    assert d.debate_id  # non-empty UUID string


def test_create_custom_names_and_models():
    d = Debate.create(
        topic="t", agent1_name="A", agent2_name="B", model1="m1", model2="m2"
    )
    assert d.agents[0].name == "A"
    assert d.agents[0].model == "m1"
    assert d.agents[1].name == "B"
    assert d.agents[1].model == "m2"


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


def test_current_and_next_agent():
    d = _make_debate()
    assert d.current_agent is d.agents[0]
    assert d.next_agent is d.agents[1]


# ---------------------------------------------------------------------------
# build_messages
# ---------------------------------------------------------------------------


def test_build_messages_empty_history():
    d = _make_debate()
    msgs = d.build_messages(0)
    # system prompt + kickoff user message
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert "Alice" in msgs[0]["content"]
    assert _MODERATOR_CLAUSE in msgs[0]["content"]
    assert msgs[1]["role"] == "user"
    assert d.topic in msgs[1]["content"]


def test_build_messages_moderator_clause_not_stored():
    """The moderator clause is injected at build time, not on the agent."""
    d = _make_debate()
    assert _MODERATOR_CLAUSE not in d.agents[0].system_prompt
    msgs = d.build_messages(0)
    assert _MODERATOR_CLAUSE in msgs[0]["content"]


def test_build_messages_with_history():
    d = _make_debate()
    d.history = [
        {"role": "agent-0", "name": "Alice", "content": "I say tabs"},
        {"role": "agent-1", "name": "Bob", "content": "I say spaces"},
        {"role": "moderator", "name": "Moderator", "content": "Elaborate"},
    ]

    # From agent-0's (Alice's) perspective
    msgs = d.build_messages(0)
    assert _MODERATOR_CLAUSE in msgs[0]["content"]
    assert msgs[1] == {"role": "assistant", "content": "I say tabs"}
    assert msgs[2] == {"role": "user", "content": "Bob: I say spaces", "name": "Bob"}
    assert msgs[3] == {"role": "user", "content": "Moderator: Elaborate", "name": "Moderator"}

    # From agent-1's (Bob's) perspective
    msgs = d.build_messages(1)
    assert msgs[1] == {"role": "user", "content": "Alice: I say tabs", "name": "Alice"}
    assert msgs[2] == {"role": "assistant", "content": "I say spaces"}
    assert msgs[3] == {"role": "user", "content": "Moderator: Elaborate", "name": "Moderator"}


# ---------------------------------------------------------------------------
# State mutations
# ---------------------------------------------------------------------------


def test_add_moderator_message():
    d = _make_debate()
    d.add_moderator_message("Please focus")
    assert len(d.history) == 1
    assert d.history[0] == {
        "role": "moderator",
        "name": "Moderator",
        "content": "Please focus",
    }


def test_record_turn_advances():
    d = _make_debate()
    assert d.current_turn == 0
    d.record_turn(0, "first response")
    assert d.current_turn == 1
    assert d.history[-1]["role"] == "agent-0"
    assert d.history[-1]["content"] == "first response"

    d.record_turn(1, "second response")
    assert d.current_turn == 0  # wraps around
    assert d.history[-1]["role"] == "agent-1"


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def test_stop():
    d = _make_debate()
    d.record_turn(0, "something")
    result = d.stop()
    assert d.status == "ended"
    assert result["status"] == "ended"
    assert result["turn_count"] == 1
    assert result["debate_id"] == d.debate_id


# ---------------------------------------------------------------------------
# status_dict
# ---------------------------------------------------------------------------


def test_status_dict():
    d = _make_debate()
    s = d.status_dict()
    assert s["debate_id"] == d.debate_id
    assert s["topic"] == "Tabs vs spaces"
    assert s["status"] == "active"
    assert s["current_turn"] == 0
    assert s["current_agent"] == "Alice"
    assert s["turn_count"] == 0
    assert len(s["agents"]) == 2


def test_status_dict_truncates_long_content():
    d = _make_debate()
    d.history.append({
        "role": "agent-0",
        "name": "Alice",
        "content": "x" * 200,
    })
    s = d.status_dict()
    assert s["history"][0]["content"].endswith("...")
    assert len(s["history"][0]["content"]) == 103  # 100 chars + "..."


# ---------------------------------------------------------------------------
# stream_turn (with mocked Ollama)
# ---------------------------------------------------------------------------


def test_stream_turn():
    async def _run():
        engine = _make_debate_engine()
        info = _make_info(request_id=42)
        queue: SSEQueue = asyncio.Queue()

        with patch(
            "debate_backend.engine.graphs.debate_graph.create_llm",
            return_value=_fake_llm(["Hello", " world"]),
        ):
            await engine.run_turn(queue, info)

        items = []
        while not queue.empty():
            items.append(queue.get_nowait())

        # 2 token notifications + 1 final response
        assert len(items) == 3

        assert isinstance(items[0], JSONRPCNotification)
        assert items[0].params["token"] == "Hello"
        assert items[0].params["agent"] == "Alice"

        assert isinstance(items[1], JSONRPCNotification)
        assert items[1].params["token"] == " world"

        assert isinstance(items[2], JSONRPCResponse)
        assert items[2].result["status"] == "turn_complete"
        assert items[2].result["agent"] == "Alice"
        assert items[2].result["next_agent"] == "Bob"

        # Turn should have advanced
        assert engine.current_turn == 1
        assert engine.history[-1]["content"] == "Hello world"

    asyncio.run(_run())


def test_stream_turn_ollama_error():
    async def _run():
        engine = _make_debate_engine()
        info = _make_info(request_id=99)
        queue: SSEQueue = asyncio.Queue()

        class _ErrorLLM:
            async def astream(self, messages):
                raise ConnectionError("LLM is down")
                yield  # make it a generator  # noqa: E501

        with patch(
            "debate_backend.engine.graphs.debate_graph.create_llm",
            return_value=_ErrorLLM(),
        ):
            await engine.run_turn(queue, info)

        items = []
        while not queue.empty():
            items.append(queue.get_nowait())

        # Only the final response (no tokens streamed)
        assert len(items) == 1
        assert isinstance(items[0], JSONRPCResponse)
        assert "Error" in engine.history[-1]["content"]

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Serialization: to_dict / from_dict
# ---------------------------------------------------------------------------


def test_to_dict_has_required_fields():
    d = _make_debate()
    d.record_turn(0, "hello")
    data = d.to_dict()
    assert data["version"] == 1
    assert data["debate_id"] == d.debate_id
    assert data["topic"] == "Tabs vs spaces"
    assert data["status"] == "active"
    assert data["current_turn"] == 1
    assert "template" in data
    assert len(data["template"]["agents"]) == 2
    assert data["template"]["agents"][0]["system_prompt"]  # resolved, not empty
    assert len(data["history"]) == 1
    assert "saved_at" in data


def test_to_dict_from_dict_roundtrip():
    d = _make_debate()
    d.record_turn(0, "first")
    d.add_moderator_message("go on")
    d.record_turn(1, "second")
    data = d.to_dict()
    restored = Debate.from_dict(data)
    assert restored.debate_id == d.debate_id
    assert restored.topic == d.topic
    assert restored.status == d.status
    assert restored.current_turn == d.current_turn
    assert len(restored.agents) == len(d.agents)
    assert restored.agents[0].name == d.agents[0].name
    assert restored.agents[0].system_prompt == d.agents[0].system_prompt
    assert restored.history == d.history


def test_new_fields_default_empty():
    d = Debate.create(topic="test")
    assert d.template_name == ""
    assert d.template_description == ""


# ---------------------------------------------------------------------------
# from_template
# ---------------------------------------------------------------------------


def test_from_template():
    template_data = {
        "name": "test_tmpl",
        "description": "A test template",
        "agents": [
            {
                "name": "Pro",
                "model": "test-model",
                "system_prompt": "You are {name}. Topic: {topic}. Argue FOR.",
            },
            {
                "name": "Con",
                "model": "test-model",
                "system_prompt": "You are {name}. Topic: {topic}. Argue AGAINST.",
            },
        ],
    }
    d = Debate.from_template(template_data, "AI ethics")
    assert d.topic == "AI ethics"
    assert d.template_name == "test_tmpl"
    assert d.template_description == "A test template"
    assert d.agents[0].name == "Pro"
    assert "AI ethics" in d.agents[0].system_prompt
    assert "Pro" in d.agents[0].system_prompt
    assert d.agents[1].name == "Con"
    assert "AI ethics" in d.agents[1].system_prompt


def test_from_template_default_model():
    template_data = {
        "name": "minimal",
        "agents": [
            {"name": "A", "system_prompt": "{name} on {topic}"},
            {"name": "B", "system_prompt": "{name} on {topic}"},
        ],
    }
    d = Debate.from_template(template_data, "topic")
    assert d.agents[0].model == DEFAULT_MODEL
    assert d.agents[1].model == DEFAULT_MODEL


# ---------------------------------------------------------------------------
# find_agent_index / set_current_turn
# ---------------------------------------------------------------------------


def test_find_agent_index_found():
    d = _make_debate()
    assert d.find_agent_index("Alice") == 0
    assert d.find_agent_index("Bob") == 1


def test_find_agent_index_case_insensitive():
    d = _make_debate()
    assert d.find_agent_index("alice") == 0
    assert d.find_agent_index("BOB") == 1


def test_find_agent_index_not_found():
    d = _make_debate()
    assert d.find_agent_index("Charlie") is None


def test_set_current_turn():
    d = _make_debate()
    assert d.current_turn == 0
    d.set_current_turn(1)
    assert d.current_turn == 1
    assert d.current_agent.name == "Bob"


# ---------------------------------------------------------------------------
# _parse_target
# ---------------------------------------------------------------------------


def test_parse_target_match():
    d = _make_debate()
    idx, msg = _parse_target("@Alice focus on economics", d)
    assert idx == 0
    assert msg == "focus on economics"


def test_parse_target_case_insensitive():
    d = _make_debate()
    idx, msg = _parse_target("@bob elaborate", d)
    assert idx == 1
    assert msg == "elaborate"


def test_parse_target_no_at():
    d = _make_debate()
    idx, msg = _parse_target("just a regular message", d)
    assert idx is None
    assert msg == "just a regular message"


def test_parse_target_unknown_agent():
    d = _make_debate()
    idx, msg = _parse_target("@Charlie do something", d)
    assert idx is None
    assert msg == "@Charlie do something"


def test_parse_target_empty_body():
    d = _make_debate()
    idx, msg = _parse_target("@Alice", d)
    assert idx == 0
    assert msg == ""


# ---------------------------------------------------------------------------
# stream_turn with extra_result
# ---------------------------------------------------------------------------


def test_stream_turn_extra_result():
    async def _run():
        engine = _make_debate_engine()
        info = _make_info(request_id=42)
        queue: SSEQueue = asyncio.Queue()

        with patch(
            "debate_backend.engine.graphs.debate_graph.create_llm",
            return_value=_fake_llm(["ok"]),
        ):
            await engine.run_turn(queue, info, extra_result={"mode": "round"})

        items = []
        while not queue.empty():
            items.append(queue.get_nowait())

        final = items[-1]
        assert isinstance(final, JSONRPCResponse)
        assert final.result["status"] == "turn_complete"
        assert final.result["mode"] == "round"

    asyncio.run(_run())


def test_stream_turn_no_extra_result():
    async def _run():
        engine = _make_debate_engine()
        info = _make_info(request_id=42)
        queue: SSEQueue = asyncio.Queue()

        with patch(
            "debate_backend.engine.graphs.debate_graph.create_llm",
            return_value=_fake_llm(["ok"]),
        ):
            await engine.run_turn(queue, info)

        items = []
        while not queue.empty():
            items.append(queue.get_nowait())

        final = items[-1]
        assert isinstance(final, JSONRPCResponse)
        assert "mode" not in final.result

    asyncio.run(_run())
