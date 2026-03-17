"""Ollama LLM client for streaming chat completions."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator

import httpx

LOG = logging.getLogger(__name__)

DEFAULT_OLLAMA_URL = "http://localhost:11434"


async def ollama_chat_stream(
    model: str,
    messages: list[dict[str, str]],
    base_url: str = DEFAULT_OLLAMA_URL,
) -> AsyncGenerator[str]:
    """Stream tokens from Ollama's /api/chat endpoint.

    Args:
        model: Ollama model name (e.g. "llama3.2", "qwen2.5:0.5b").
        messages: Chat messages in OpenAI format [{"role": "...", "content": "..."}].
        base_url: Ollama server URL.

    Yields:
        Token strings as they arrive.
    """
    async with httpx.AsyncClient(timeout=None) as client:

        async with client.stream("POST", f"{base_url}/api/chat", json={"model": model, "messages": messages, "stream": True},) as response:

            response.raise_for_status()
            token_buffer = []  # for debug

            async for line in response.aiter_lines():

                line = line.strip()

                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    LOG.warning("Skipping non-JSON line: %s", line[:100])
                    continue

                if "message" in data and "content" in data["message"]:

                    if token := data["message"]["content"]:
                        token_buffer.append(token)
                        yield token

                if data.get("done", False):
                    prompt_response = "".join(token_buffer)
                    LOG.info(F"DONE token buffer [{len(token_buffer)}]:\n{prompt_response}")
                    return
                LOG.info(f"continue len of token buffer:[{len(token_buffer)}]:....")
            prompt_response = "".join(token_buffer)
            LOG.info(f"END token buffer[{len(token_buffer)}]:\n{prompt_response}")
