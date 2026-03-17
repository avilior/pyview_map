# LangGraph Refactor — Design Notes

**Branch:** `refactor` (merged to `master` 2026-02-20)
**Started:** 2026-02-19  |  **Last updated:** 2026-02-20

---

## Motivation

The current debate engine has several structural limitations:

- Hardcoded Ollama-only LLM client
- 2-agent modulo turn counter (cannot generalise to N agents)
- Orchestration logic baked directly into `Debate.stream_turn()` — no separation between "who speaks next" and "how they speak"
- No evaluator agents
- Template `settings` (max_rounds, stop_phrase) parsed but never enforced
- In-memory dict only — state lost on restart unless manually saved

---

## Framework Decision: LangGraph

LangGraph chosen over AutoGen and CrewAI for the following reasons:

- **Graph model maps directly to debate flow** — nodes are agent turns / evaluator checks / human-in-the-loop; edges are conditional (evaluator decides who speaks next)
- **Evaluator agents are first-class nodes** — can route based on structured evaluator output
- **`interrupt()` primitive** for human-in-the-loop moderator — clean pause/resume, not bolted on
- **LangChain model abstraction** — 50+ LLM integrations (Ollama, OpenAI, Anthropic, etc.) via one interface
- **Checkpointing** — built-in state persistence (MemorySaver → SQLite/Redis/Postgres)
- Explicit routing logic is a *feature* here, not a cost — we have custom orchestration needs

---

## Architecture Decisions

### 1. Graph per Template Mode (not a single unified graph)

Each `mode` value in a template maps to its own compiled graph builder:

```python
GRAPH_REGISTRY: dict[str, Callable[[TemplateConfig], CompiledGraph]] = {
    "debate":   build_debate_graph,
    "freeform": build_freeform_graph,
    # future: "panel", "interview", "red_team"
}
```

Adding a new interaction style = one new builder function + one registry entry. Nothing else changes.

### 2. Router as an Injectable Protocol

The graph's routing node calls a `Router` instance injected at graph-build time. New router types drop in without touching the graph.

```python
class RouterDecision(BaseModel):
    next_action: Literal["speak", "end"]
    speaker: str | None = None
    reason: str | None = None

class Router(Protocol):
    def next(self, state: DebateState, debate: Debate, max_rounds: int) -> RouterDecision: ...
```

**Router types (progressive):**
| Type | Description |
|---|---|
| `round_robin` | Deterministic, agents speak in order. Phase 2. |
| `evaluator_directed` | Uses `evaluator_feedback[-1].recommendation`. Phase 5. |
| `llm_supervisor` | LLM reasons about who speaks next. Phase 5. |

Router type is set in the template YAML via `router.type`. Configured per-template so different debates can use different routers.

### 3. Evaluator Trigger — All Three Modes via Config

```yaml
evaluator:
  enabled: true
  model: "anthropic:claude-opus-4-6"
  trigger: every_n_rounds   # "every_turn" | "every_n_rounds" | "on_demand"
  every_n: 2
```

- `every_turn` — evaluator runs after every agent response
- `every_n_rounds` — evaluator runs every N complete rounds
- `on_demand` — moderator triggers via `/evaluate` command

---

## State Design

LangGraph manages **routing state** only. Full debate history lives in the `Debate` object (preserves serialization compatibility with existing save/load).

```python
class DebateState(TypedDict):
    debate_id: str
    current_speaker: str | None    # agent who just spoke (or will speak next)
    targeted_speaker: str | None   # @Agent override from moderator inject; cleared by router
    round_count: int               # incremented after each agent turn
    next_action: str               # "speak" | "end"
    status: str                    # "active" | "ended"
```

The `Debate` object is passed into each graph node via `config["configurable"]["debate"]` and is NOT stored in LangGraph state. This keeps the checkpointed state minimal and preserves backward compatibility with all existing save/load/transcript logic.

---

## Graph 1: Formal Debate (Supervisor Pattern)

```
START → router ──┬─ speak ──▶ agent_turn ─── (interrupt_after) ──▶ router (loop)
                 └─ end ────▶ END
```

- `interrupt_after=["agent_turn"]` — graph pauses after each agent speaks
- Each `debate.next_turn` / `debate.inject` call resumes the graph for one turn
- Moderator inject: updates LangGraph state (`targeted_speaker`) then resumes

### Evaluator placement (Phase 3+):
```
agent_turn → round_check → [optional] evaluator → router
```

### Full moderator interrupt (Phase 3+):
```
START → moderator_checkpoint (interrupt_before) → router → agent_turn → ...
```

## Graph 2: Freeform Conversation (Swarm Pattern) — Phase 4

Agents hold a `handoff` tool and decide who speaks next:

```
agent_A ──handoff("B")──▶ agent_B ──handoff("evaluator")──▶ evaluator ──▶ ...
```

No central supervisor. Evaluator is a peer agent that can be handed off to.

---

## Template Schema (Extended)

Existing templates (`classic.yaml`, etc.) are **backward compatible** — all new fields have defaults.

```yaml
name: formal_debate
mode: debate               # "debate" | "freeform" — selects graph from registry
                           # default: "debate"

router:
  type: round_robin        # "round_robin" | "evaluator_directed" | "llm_supervisor"
                           # default: "round_robin"
  # model: ...             # only for llm_supervisor

evaluator:
  enabled: false           # default: false
  model: "anthropic:claude-opus-4-6"
  trigger: every_n_rounds  # "every_turn" | "every_n_rounds" | "on_demand"
  every_n: 2

settings:
  max_rounds: 20           # now enforced (was parsed but ignored)
  stop_phrase: "I concede."
  moderator_pause: after_round  # "after_turn" | "after_round" | "never"

agents:
  - name: Prosecutor
    model: "anthropic:claude-sonnet-4-6"   # provider:model or bare model (defaults to ollama)
    role: for
    system_prompt: ...
  - name: Defender
    model: "openai:gpt-4o"
    role: against
    system_prompt: ...
```

### Model String Format

```
"llama3.2"                    → Ollama llama3.2   (bare name = ollama default)
"ollama:llama3.2"             → Ollama llama3.2
"openai:gpt-4o"               → OpenAI gpt-4o
"anthropic:claude-opus-4-6"   → Anthropic claude-opus-4-6
```

---

## How the Pieces Compose

```
TemplateConfig
    │
    ├── mode ──────────────▶ GRAPH_REGISTRY ──▶ CompiledGraph (one per debate)
    │
    ├── router.type ───────▶ RouterFactory ───▶ Router (captured in graph closure)
    │
    ├── evaluator config ──▶ round_check node (Phase 3+)
    │
    └── agents[].model ────▶ create_llm() ──▶ LangChain BaseChatModel
                                              (Ollama / OpenAI / Anthropic)
```

---

## DebateEngine Wrapper

Each debate session is represented by a `DebateEngine`:

```python
@dataclass
class DebateEngine:
    debate: Debate           # domain model — history, serialization, transcripts
    graph: CompiledGraph     # LangGraph graph — routing, orchestration
    thread_config: dict      # {"configurable": {"thread_id": debate_id}}
```

`debate.py` replaces `_debates: dict[str, Debate]` with `_engines: dict[str, DebateEngine]`.
`commands.py` accesses `engine.debate` for serialization/transcript operations.

---

## Phased Implementation Plan

| Phase | What | Status |
|---|---|---|
| 1 | `DebateState` + LangChain model abstraction (`create_llm`) | **Done** |
| 2 | `debate` graph with `RoundRobinRouter` (feature parity) | **Done** |
| 3 | Evaluator node + all three trigger modes | Planned |
| 4 | `freeform` graph (swarm pattern) | Planned |
| 5 | `EvaluatorDirectedRouter` + `LLMSupervisorRouter` | Planned |
| 6 | Moderator `interrupt()` — full pause/resume | Planned |
| 7 | Persistent checkpointer (SQLite/Postgres) | Planned |

---

## What Stays the Same

- `Debate` class (serialization, history management, transcript generation) — **unchanged**
- JSON-RPC API surface (same method names, same params, same SSE token format)
- All save/load/template file formats (backward compatible YAML + JSON)

## What Changed (Phases 1 & 2 — completed 2026-02-20)

| Before | After |
|---|---|
| `ollama_client.py` direct call | `create_llm(model_string).astream(messages)` |
| 2-agent modulo counter | N-agent `RoundRobinRouter` |
| Orchestration in `Debate.stream_turn()` | `agent_turn` node + `router` node |
| `_debates: dict[str, Debate]` | `_engines: dict[str, DebateEngine]` |
| Template settings ignored | `max_rounds` enforced via router |

---

## Implementation Notes (from Phase 1/2 session)

### Bug fixes discovered during live testing

**`_initial_state()` speaker bug** — `current_speaker` was seeded from
`history[-1]["name"]`, which returns `"Moderator"` if the last entry is a
moderator message. The router then couldn't find "Moderator" in agents and
defaulted to index 0, causing Agent Alpha to run twice in a row.
Fix: walk history in reverse and find the last entry whose `role != "moderator"`.

**Agent prefixing its own name** — LLM learned the `"Name: content"` convention
from history and applied it to its own output. Fixed by adding
"Write your response directly, without prefixing it with your own name."
to `_MODERATOR_CLAUSE`.

**`[Moderator]` appearing in agent output** — Old `_MODERATOR_CLAUSE` text
mentioned the `[Moderator]` bracket format, causing the LLM to echo it.
Rewritten to use plain `Moderator:` prefix with explicit "do not echo" instruction.

### Speaker identity — dual signal approach

Cloud providers (OpenAI, Anthropic) support an out-of-band `name` field on
`HumanMessage`. Ollama ignores it and relies on content prefix.
Both signals are sent simultaneously:

```python
messages.append({
    "role": "user",
    "content": f"{name}: {content}",   # content prefix — for Ollama
    "name": name,                       # name field — for OpenAI/Anthropic
})
```

The `name` field is sanitised to `[a-zA-Z0-9_-]` (OpenAI requirement):
```python
safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name)[:64]
```

### New RPC endpoint: `debate.announce`

```python
@jrpc_service.request("debate.announce")
async def debate_announce(info, debate_id, message) -> dict
```

Records a moderator message in history without triggering any agent response.
Used by the frontend to auto-post the opening announcement after `/new`.

### Frontend UI improvements (same session)

- **Auto-moderator opening** — after `/new`, frontend generates a formatted
  opening announcement, shows it as a Moderator bubble, and calls
  `debate.announce` to persist it in backend history.
- **Post-debate echo bug** — after `/end`, typing no longer routes to the
  backend echo handler; shows a hint message instead.
- **Generic status bar** — `ChatContext.session_title` + `ChatContext.status_bar`
  are application-populated fields; the template renders them without knowing
  about debates.
- **Agent bubble turn labels** — `_add_debate_turn_placeholder()` increments
  `ctx.agent_turn_count` and sets `sender_name = "Agent Alpha · 3"`.
  Seeded from agent-only history entries on `/load`.
- **Next Turn button** shows upcoming speaker: `"Next Turn → Agent Beta"`.
- **`@Agent` targeted inject** — frontend resolves the targeted agent name
  before creating the placeholder so the bubble shows the correct name
  during streaming (not `ctx.current_agent` which may differ).

---

## Next Session Starting Points

Pick up at **Phase 3: Evaluator node**.

Key files to read first:
- `packages/server_pkg/http_stream_transport/application/debate/engine/graphs/debate_graph.py`
- `packages/server_pkg/http_stream_transport/application/debate/engine/models.py`
- `packages/server_pkg/http_stream_transport/application/debate/engine/state.py`
- `packages/server_pkg/http_stream_transport/application/debate/engine/routers/round_robin.py`

Phase 3 plan:
1. Add `evaluator_feedback: list[dict]` to `DebateState`
2. Add `evaluator_turn` node in `debate_graph.py` — calls `create_llm(evaluator.model)`
   with a structured prompt asking for feedback + recommendation
3. Add `round_check` node between `agent_turn` and `router` — decides whether
   to call evaluator based on `trigger` config (`every_turn`, `every_n_rounds`)
4. Add `on_demand` trigger support via new `debate.evaluate` RPC endpoint
5. Update `TemplateConfig.EvaluatorConfig` (already defined in `models.py`)
6. Add evaluator feedback bubbles to frontend (new `"evaluator"` role in chat)
