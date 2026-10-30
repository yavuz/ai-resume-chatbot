from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from openai import AsyncOpenAI

from app.config import Settings


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None


@dataclass
class StreamEvent:
    """Akıştan gelen tek parça: ya metin (delta) ya da bitiş bilgisi."""

    delta: str = ""
    finish_reason: str | None = None
    usage: Usage | None = None


class LLMClient(Protocol):
    model: str

    def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[StreamEvent]: ...


class OpenAICompatibleClient:
    """OpenAI uyumlu herhangi bir endpoint (Gemini'nin /openai yolu, kendi gateway'in vb.)."""

    def __init__(self, settings: Settings):
        self.model = settings.llm_model
        self._settings = settings
        self._client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
        )

    async def stream(self, messages: list[dict[str, str]]) -> AsyncIterator[StreamEvent]:
        s = self._settings
        kwargs = {}
        if s.llm_reasoning_effort:
            kwargs["reasoning_effort"] = s.llm_reasoning_effort
        if s.llm_stream_usage:
            kwargs["stream_options"] = {"include_usage": True}

        response = await self._client.chat.completions.create(
            model=s.llm_model,
            messages=messages,
            temperature=s.llm_temperature,
            max_tokens=s.llm_max_tokens,
            stream=True,
            **kwargs,
        )
        async for chunk in response:
            event = StreamEvent()
            if chunk.choices:
                choice = chunk.choices[0]
                event.delta = choice.delta.content or ""
                event.finish_reason = choice.finish_reason
            if chunk.usage:
                details = chunk.usage.prompt_tokens_details
                event.usage = Usage(
                    prompt_tokens=chunk.usage.prompt_tokens,
                    completion_tokens=chunk.usage.completion_tokens,
                    cached_tokens=details.cached_tokens if details else None,
                )
            if event.delta or event.finish_reason or event.usage:
                yield event
