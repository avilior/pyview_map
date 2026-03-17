"""Pydantic config models for the debate engine.

These are used for template loading and graph construction.
They are NOT stored in LangGraph state.
"""

from __future__ import annotations

from pydantic import BaseModel

from debate_backend.engine.llm_factory import OLLAMA_DEFAULT_BASE_URL


class AgentConfig(BaseModel):
    """Configuration for a single debate agent."""

    name: str
    # Model string format: "provider:model" or bare "model" (defaults to ollama).
    # Examples: "llama3.2", "ollama:llama3.2", "openai:gpt-4o", "anthropic:claude-opus-4-6"
    model: str
    system_prompt: str
    role: str = ""  # semantic label: "for", "against", "evaluator", etc.
    # Server URL for the provider — e.g. "http://localhost:11434" for local Ollama,
    # "http://192.168.1.50:11434" for a remote Ollama, or "http://proxy/v1" for an
    # OpenAI-compatible endpoint.  Must be explicit; no default.
    server_url: str


class RouterConfig(BaseModel):
    """Configuration for the debate router."""

    type: str = "round_robin"  # "round_robin" | "evaluator_directed" | "llm_supervisor"
    model: str | None = None   # LLM model for llm_supervisor router


class EvaluatorConfig(BaseModel):
    """Configuration for the optional evaluator agent."""

    enabled: bool = False
    model: str = "anthropic:claude-opus-4-6"
    trigger: str = "every_n_rounds"  # "every_turn" | "every_n_rounds" | "on_demand"
    every_n: int = 2                 # only used when trigger = "every_n_rounds"


class TemplateConfig(BaseModel):
    """Full configuration parsed from a YAML debate template."""

    name: str
    description: str = ""
    mode: str = "debate"            # "debate" | "freeform" — selects graph from registry
    agents: list[AgentConfig] = []
    router: RouterConfig = RouterConfig()
    evaluator: EvaluatorConfig = EvaluatorConfig()
    max_rounds: int | None = None
    stop_phrase: str | None = None
    moderator_pause: str = "after_round"  # "after_turn" | "after_round" | "never"
    strip_think: bool = True

    @classmethod
    def from_template_dict(cls, data: dict, topic: str | None = None) -> TemplateConfig:
        """Parse from a raw YAML template dict.

        Agent system prompts have ``{topic}`` and ``{name}`` resolved when
        *topic* is provided.  Existing templates without the new keys
        (``mode``, ``router``, ``evaluator``) use their defaults so
        backward compatibility is preserved.
        """
        agents = []
        for agent_def in data.get("agents", []):
            prompt = agent_def["system_prompt"]
            if topic:
                prompt = prompt.format(topic=topic, name=agent_def["name"])
            agents.append(AgentConfig(
                name=agent_def["name"],
                model=agent_def.get("model", "llama3.2"),
                system_prompt=prompt,
                role=agent_def.get("role", ""),
                server_url=agent_def.get("server_url", OLLAMA_DEFAULT_BASE_URL),
            ))

        settings = data.get("settings", {})
        router_data = data.get("router", {})
        evaluator_data = data.get("evaluator", {})

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            mode=data.get("mode", "debate"),
            agents=agents,
            router=RouterConfig(**router_data) if router_data else RouterConfig(),
            evaluator=EvaluatorConfig(**evaluator_data) if evaluator_data else EvaluatorConfig(),
            max_rounds=None,  # max_rounds comes from spec files, not templates
            stop_phrase=settings.get("stop_phrase"),
            moderator_pause=settings.get("moderator_pause", "after_round"),
            strip_think=data.get("strip_think", True),
        )
