from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, TypedDict, cast

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langgraph.graph import END, StateGraph

from app.core.chat_models import get_chat_model
from app.core.config import settings
from app.core.rag import format_context, search
from app.core.summary_answers import direct_answer_from_summary, load_summary_for_source


class ChatState(TypedDict, total=False):
    question: str
    history: list[dict[str, str]]
    k: int
    user_id: str
    hits: list[dict[str, Any]]
    documents: list[Document]
    context: str
    sources_block: str
    answer: str
    direct_answer: bool


PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a careful analyst. Use ONLY the provided context to answer the question. "
            "If the context does not contain the answer, say you don't know. Cite supporting "
            "snippets with numbered references like [1], [2].",
        ),
        (
            "human",
            "Question:\n{question}\n\n"
            "Conversation so far:\n{history}\n\n"
            "Retrieved context:\n{context}\n\n"
            "Sources:\n{sources}\n",
        ),
    ]
)


def _history_block(history: list[dict[str, str]] | None) -> str:
    if not history:
        return "(none)"
    lines = []
    for msg in history:
        role = msg.get("role", "user").capitalize()
        content = msg.get("content", "")
        lines.append(f"{role}: {content}")
    return "\n".join(lines)


def _sources_block(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "No sources."
    lines: list[str] = []
    for idx, hit in enumerate(hits, 1):
        source = hit.get("source", "?")
        row = hit.get("row_index", "?")
        lines.append(f"[{idx}] {source} (row {row})")
    return "\n".join(lines)


def _needs_llm(state: ChatState) -> str:
    return "guard" if state.get("answer") else "llm"


@lru_cache(maxsize=4)
def _compiled_graph(provider: str) -> Any:
    model = get_chat_model(provider)
    parser = StrOutputParser()

    chain: Runnable[dict[str, Any], str]
    if model.__class__.__name__ == "StubChatModel":
        chain = cast(
            Runnable[dict[str, Any], str],
            RunnableLambda(
                lambda payload: f"(stub) Using retrieved context only:\n\n{payload['context']}\n"
            ),
        )
    else:
        chain = cast(Runnable[dict[str, Any], str], PROMPT_TEMPLATE | model | parser)

    graph = StateGraph(ChatState)

    def retrieve_node(state: ChatState) -> dict[str, Any]:
        k = state.get("k", 6)
        user_id = state.get("user_id", "default")
        hits = search(state["question"], k=k, user_id=user_id)
        documents = [
            Document(
                page_content=hit.get("text", ""),
                metadata={
                    "source": hit.get("source"),
                    "row_index": hit.get("row_index"),
                    "id": hit.get("id"),
                    "score": hit.get("score"),
                    "tags": hit.get("tags", []),
                    "user_id": user_id,
                },
            )
            for hit in hits
        ]
        context = format_context(hits)
        return {
            "hits": hits,
            "documents": documents,
            "context": context,
            "sources_block": _sources_block(hits),
        }

    def metrics_node(state: ChatState) -> dict[str, Any]:
        hits = state.get("hits") or []
        question = state["question"]
        for hit in hits:
            source = hit.get("source")
            if not source:
                continue
            summary = load_summary_for_source(source)
            if not summary:
                continue
            direct = direct_answer_from_summary(question, summary)
            if direct:
                return {"answer": direct, "direct_answer": True}
        return {}

    def llm_node(state: ChatState) -> dict[str, Any]:
        payload = {
            "question": state["question"],
            "history": _history_block(state.get("history")),
            "context": state.get("context", ""),
            "sources": state.get("sources_block", "No sources."),
        }
        answer = chain.invoke(payload)
        if isinstance(answer, str):
            return {"answer": answer.strip(), "direct_answer": False}
        return {"answer": str(answer), "direct_answer": False}

    def guard_node(state: ChatState) -> dict[str, Any]:
        answer = state.get("answer", "").strip()
        if not answer:
            return {
                "answer": "I don't have enough context yet. Try indexing more data or restating the question.",
                "direct_answer": False,
            }
        # Ensure citation hints exist for LLM-generated answers.
        if not state.get("direct_answer") and "[" not in answer:
            answer = f"{answer}\n\n(Consider reviewing sources for citations.)"
        return {"answer": answer}

    graph.add_node("retrieve", retrieve_node)
    graph.add_node("metrics", metrics_node)
    graph.add_node("llm", llm_node)
    graph.add_node("guard", guard_node)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "metrics")
    graph.add_conditional_edges("metrics", _needs_llm, {"llm": "llm", "guard": "guard"})
    graph.add_edge("llm", "guard")
    graph.add_edge("guard", END)

    return graph.compile()


def run_chat(
    messages: list[dict[str, str]], *, k: int = 6, user_id: str = "default"
) -> dict[str, Any]:
    if not messages or messages[-1].get("role") != "user":
        msg = "Last message must be from the user."
        raise ValueError(msg)

    question = messages[-1].get("content", "").strip()
    if not question:
        msg = "Question content cannot be empty."
        raise ValueError(msg)

    history = messages[:-1]
    provider = os.getenv("LLM_PROVIDER", settings.LLM_PROVIDER)
    compiled = _compiled_graph(provider)
    state = compiled.invoke({"question": question, "history": history, "k": k, "user_id": user_id})

    hits = state.get("hits", [])
    answer = state.get("answer", "")
    assistant_message = {"role": "assistant", "content": answer}
    updated_messages = history + [messages[-1], assistant_message]

    return {
        "answer": answer,
        "sources": hits,
        "messages": updated_messages,
        "direct_answer": state.get("direct_answer", False),
    }
