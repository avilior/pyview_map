"""LLM factory — create a LangChain chat model from a provider:model string.

Providers are imported lazily so only the packages actually used need to be
installed.  ``langchain-ollama`` is a required dependency; ``langchain-openai``
and ``langchain-anthropic`` are optional (install separately if needed).
"""

from __future__ import annotations

from langchain_core.language_models import BaseChatModel

# Canonical default Ollama server address.  Used as a fallback only when
# loading old saves or templates that pre-date the server_url field.
OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434"


def create_llm(model_string: str, server_url: str) -> BaseChatModel:
    """Return a LangChain ``BaseChatModel`` for the given model string.

    Format: ``"provider:model-name"`` or bare ``"model-name"`` (defaults to Ollama).
    Ollama model tags (``name:tag``) are handled automatically — any ``prefix:rest``
    where the prefix is not a known provider is passed to Ollama as-is.

    *server_url* sets the server address for the provider.  For Ollama it is
    always forwarded.  For OpenAI/Anthropic it is forwarded only when it differs
    from the Ollama default, so cloud agents are unaffected unless a proxy is
    explicitly configured::

        create_llm("llama3.2",           "http://localhost:11434")   # Ollama local
        create_llm("deepseek-r1:14b",    "http://nas:11434")         # Ollama remote
        create_llm("openai:gpt-4o",      "http://localhost:11434")   # OpenAI cloud (default ignored)
        create_llm("openai:gpt-4o",      "http://proxy/v1")          # OpenAI-compatible proxy
        create_llm("anthropic:claude-opus-4-6", "http://localhost:11434")  # Anthropic cloud
    """
    _KNOWN_PROVIDERS = {"ollama", "openai", "anthropic"}

    if ":" in model_string:
        prefix, rest = model_string.split(":", 1)
        if prefix in _KNOWN_PROVIDERS:
            provider, model = prefix, rest
        else:
            # Treat as an Ollama model with a tag, e.g. "deepseek-r1:14b"
            provider, model = "ollama", model_string
    else:
        provider, model = "ollama", model_string

    # For cloud providers, only forward server_url when it has been explicitly
    # overridden to a non-Ollama address.  Passing localhost:11434 to ChatOpenAI
    # or ChatAnthropic would break them.
    cloud_url = server_url if server_url != OLLAMA_DEFAULT_BASE_URL else None

    if provider == "ollama":
        from langchain_ollama import ChatOllama  # type: ignore[import-untyped]
        return ChatOllama(model=model, base_url=server_url)

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "langchain-openai is not installed. Run: uv add langchain-openai"
            ) from exc
        kwargs: dict = {"model": model}
        if cloud_url:
            kwargs["base_url"] = cloud_url
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "langchain-anthropic is not installed. Run: uv add langchain-anthropic"
            ) from exc
        kwargs = {"model": model}
        if cloud_url:
            kwargs["base_url"] = cloud_url
        return ChatAnthropic(**kwargs)

    raise ValueError(
        f"Unknown LLM provider: {provider!r}. "
        "Supported providers: 'ollama', 'openai', 'anthropic'."
    )
