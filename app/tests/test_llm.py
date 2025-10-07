from __future__ import annotations

import importlib


class _Resp:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:  # pragma: no cover - nothing to raise
        return None

    def json(self) -> dict[str, object]:
        return self._payload


def test_lmstudio_answer_builds_openai_payload(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "lmstudio")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1234")
    monkeypatch.setenv("OPENAI_MODEL", "demo-model")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")

    sent = {}

    def fake_post(url, json, headers, timeout):
        sent["url"] = url
        sent["json"] = json
        sent["headers"] = headers
        return _Resp({"choices": [{"message": {"content": "Answer!"}}]})

    monkeypatch.setattr("requests.post", fake_post)

    import app.core.llm as llm_module

    importlib.reload(llm_module)

    output = llm_module.answer("Q?", "context", hits=[{"source": "s", "row_index": 1}])
    assert output == "Answer!"
    assert sent["url"].endswith("/v1/chat/completions")
    assert sent["json"]["messages"][0]["role"] == "user"
    assert sent["headers"]["Authorization"] == "Bearer fake-key"


def test_lmstudio_answer_handles_error(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "lmstudio")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1234")

    def fake_post(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("requests.post", fake_post)

    import app.core.llm as llm_module

    importlib.reload(llm_module)

    result = llm_module.answer("Q?", "ctx", hits=[])
    assert "lmstudio error" in result
