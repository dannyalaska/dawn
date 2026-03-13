from __future__ import annotations

import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.core.config import settings


class StubChatModel(BaseChatModel):
    """Minimal chat model that mirrors the legacy stub behaviour."""

    model_name: str = "stub"

    def _generate(
        self,
        messages: list,
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> Any:  # pragma: no cover - uses inherited convenience wrapper
        from langchain_core.messages import AIMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        content_blocks: list[str] = []
        for msg in messages:
            content = getattr(msg, "content", "")
            if content:
                content_blocks.append(str(content))
        joined = "\n\n".join(content_blocks)
        text = f"(stub) Using retrieved context only:\n\n{joined.strip()}"
        generation = ChatGeneration(message=AIMessage(content=text))
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return "stub"


def _normalized_lmstudio_base_url() -> str:
    base = (settings.OPENAI_BASE_URL or "http://127.0.0.1:1234").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def get_chat_model(provider: str) -> BaseChatModel:
    provider = (provider or "stub").lower()

    try:
        if provider == "openai":
            init_kwargs: dict[str, Any] = {
                "model": settings.OPENAI_MODEL,
                "temperature": 0.1,
                "max_retries": 2,
            }
            if settings.OPENAI_API_KEY:
                init_kwargs["api_key"] = SecretStr(settings.OPENAI_API_KEY)
            if settings.OPENAI_BASE_URL:
                init_kwargs["base_url"] = settings.OPENAI_BASE_URL.rstrip("/")
            return ChatOpenAI(**init_kwargs)

        if provider == "lmstudio":
            base_url = _normalized_lmstudio_base_url()
            api_key = settings.OPENAI_API_KEY or "lm-studio"
            return ChatOpenAI(
                model=settings.OPENAI_MODEL,
                base_url=base_url,
                api_key=SecretStr(api_key),
                temperature=0.1,
                max_retries=1,
            )

        if provider == "ollama":
            return ChatOllama(
                model=settings.OLLAMA_MODEL,
                base_url=settings.OLLAMA_BASE_URL.rstrip("/"),
                temperature=0.1,
            )

        if provider == "anthropic":
            init_kwargs = {"model": settings.ANTHROPIC_MODEL, "temperature": 0.1}
            if settings.ANTHROPIC_API_KEY:
                init_kwargs["api_key"] = SecretStr(settings.ANTHROPIC_API_KEY)
            return ChatAnthropic(**init_kwargs)

    except Exception as exc:  # noqa: BLE001
        logging.warning(
            "chat_models: failed to init provider=%s (%s) — falling back to stub",
            provider,
            exc,
        )

    return StubChatModel()
