from __future__ import annotations

import os
import textwrap

import requests

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "stub").lower()


def _format_citations(hits: list[dict]) -> str:
    # renders [1], [2]… with source and row hints
    lines = []
    for i, h in enumerate(hits, 1):
        lines.append(f"[{i}] {h.get('source', '?')} (row {h.get('row_index', '?')})")
    return "\n".join(lines) if lines else "No sources."


def _prompt(question: str, context: str, hits: list[dict]) -> str:
    citations = _format_citations(hits)
    return textwrap.dedent(
        f"""
    You are a careful analyst. Use ONLY the context to answer.
    If the answer isn't contained in the context, say you don't know.

    Question:
    {question}

    Context:
    {context}

    Cite relevant snippets with bracketed numbers like [1], [2] mapping to the Sources list.

    Sources:
    {citations}
    """
    ).strip()


# ---------- OLLAMA ----------
def _answer_ollama(question: str, context: str, hits: list[dict]) -> str:
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    prompt = _prompt(question, context, hits)
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("response", "").strip() or "No answer."
    except Exception as e:
        return f"(ollama error: {e})\n\nFallback context:\n{context}"


# ---------- LM STUDIO ----------
def _normalized_base_url() -> str:
    base = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234")
    base = base.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _answer_lmstudio(question: str, context: str, hits: list[dict]) -> str:
    prompt = _prompt(question, context, hits)
    url = f"{_normalized_base_url()}/chat/completions"
    payload = {
        "model": os.getenv("OPENAI_MODEL", "mistral-7b-instruct-v0.3"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'lm-studio')}",
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return f"(lmstudio error: empty response)\n\nFallback context:\n{context}"
        return choices[0].get("message", {}).get("content", "").strip() or "No answer."
    except Exception as e:
        return f"(lmstudio error: {e})\n\nFallback context:\n{context}"


# ---------- OPENAI ----------
def _answer_openai(question: str, context: str, hits: list[dict]) -> str:
    try:
        from openai import OpenAI  # modern SDK

        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        prompt = _prompt(question, context, hits)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Answer with citations like [1], [2]. If unknown, say so.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"(openai error: {e})\n\nFallback context:\n{context}"


# ---------- STUB ----------
def _answer_stub(question: str, context: str, hits: list[dict]) -> str:
    return f"(stub) Using retrieved context only:\n\n{context}\n\nSuggested: set LLM_PROVIDER=ollama or openai."


def answer(question: str, context: str, hits: list[dict]) -> str:
    if LLM_PROVIDER == "ollama":
        return _answer_ollama(question, context, hits)
    if LLM_PROVIDER == "openai":
        return _answer_openai(question, context, hits)
    if LLM_PROVIDER == "lmstudio":
        return _answer_lmstudio(question, context, hits)
    # convenience: if user points OPENAI_BASE_URL at LM Studio but forgets to change provider
    base = os.getenv("OPENAI_BASE_URL", "")
    if base and ("127.0.0.1" in base or "localhost" in base):
        return _answer_lmstudio(question, context, hits)
    return _answer_stub(question, context, hits)
