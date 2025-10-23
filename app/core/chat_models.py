from __future__ import annotations

import os
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_community.chat_models import ChatOllama
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import SecretStr


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
    base = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234")
    base = base.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def get_chat_model(provider: str) -> BaseChatModel:
    provider = (provider or "stub").lower()

    try:
        if provider == "openai":
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            api_key = os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL")
            init_kwargs: dict[str, Any] = {
                "model": model,
                "temperature": 0.1,
                "max_retries": 2,
            }
            if api_key:
                init_kwargs["api_key"] = SecretStr(api_key)
            if base_url:
                init_kwargs["base_url"] = base_url.rstrip("/")
            return ChatOpenAI(**init_kwargs)

        if provider == "lmstudio":
            model = os.getenv("OPENAI_MODEL", "mistral-7b-instruct-v0.3")
            base_url = _normalized_lmstudio_base_url()
            api_key = os.getenv("OPENAI_API_KEY", "lm-studio")
            return ChatOpenAI(
                model=model,
                base_url=base_url,
                api_key=SecretStr(api_key),
                temperature=0.1,
                max_retries=1,
            )

        if provider == "ollama":
            model = os.getenv("OLLAMA_MODEL", "llama3.1")
            base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
            return ChatOllama(model=model, base_url=base_url.rstrip("/"), temperature=0.1)

        if provider == "anthropic":
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
            api_key = os.getenv("ANTHROPIC_API_KEY")
            init_kwargs = {"model": model, "temperature": 0.1}
            if api_key:
                init_kwargs["api_key"] = SecretStr(api_key)
            return ChatAnthropic(**init_kwargs)

    except Exception:  # noqa: BLE001
        # Fall back to stub model if provider initialisation fails.
        pass

    return StubChatModel()
