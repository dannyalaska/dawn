from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import streamlit as st


def render_query_workspace(
    *,
    history: Iterable[Mapping[str, Any]] | None,
    current_answer: Mapping[str, Any] | None,
    context_chunks: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Render the query and chat layout and return interaction signals."""
    st.markdown(_query_styles(), unsafe_allow_html=True)
    st.markdown('<div class="dawn-chat-heading">Ask Dawn</div>', unsafe_allow_html=True)
    st.caption("Answers cite the retrieved context from your indexed data.")

    regenerate_clicked = False
    copy_clicked = False

    if current_answer:
        st.chat_message("assistant").markdown(current_answer.get("text", "_No answer yet._"))
        action_cols = st.columns(2, gap="small")
        regenerate_clicked = action_cols[0].button(
            "Regenerate", key="regenerate_answer_btn", use_container_width=True
        )
        copy_clicked = action_cols[1].button(
            "Copy Answer", key="copy_answer_btn", use_container_width=True
        )
        with st.expander("Copy-ready answer", expanded=False):
            st.code(current_answer.get("text", ""), language="markdown")
    else:
        st.chat_message("assistant").write("Ask a question to see an answer.")

    filtered_citations: list[Mapping[str, Any]] = []
    for chunk in context_chunks or []:
        if not isinstance(chunk, Mapping):
            continue
        if any(chunk.get(key) for key in ("text", "source", "score")):
            filtered_citations.append(chunk)

    if filtered_citations:
        st.markdown(
            '<div class="dawn-section-subtitle">Retrieved context</div>', unsafe_allow_html=True
        )
        for idx, chunk in enumerate(filtered_citations, start=1):
            source_label = chunk.get("source", "Context")
            with st.expander(f"[{idx}] {source_label}", expanded=False):
                st.caption(f"Score: {chunk.get('score', '—')}")
                st.write(chunk.get("text", ""))

    st.markdown('<div class="dawn-section-subtitle">Recent questions</div>', unsafe_allow_html=True)
    rendered_history = False
    if history:
        st.markdown('<div class="dawn-history-list">', unsafe_allow_html=True)
        for entry in history:
            if not isinstance(entry, Mapping):
                continue
            question = str(entry.get("question") or "").strip()
            if not question:
                continue
            timestamp = str(entry.get("timestamp") or "").strip()
            st.markdown(
                f"""
                <div class="dawn-history-card">
                    <div class="dawn-history-question">{question}</div>
                    <div class="dawn-history-meta">{timestamp}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            rendered_history = True
        st.markdown("</div>", unsafe_allow_html=True)
    if not rendered_history:
        st.caption("No questions yet — your conversations will appear here.")

    if "dawn_query_draft" not in st.session_state:
        st.session_state["dawn_query_draft"] = ""

    with st.form("dawn_query_form", clear_on_submit=False):
        prompt = st.text_area(
            "Ask DAWN",
            placeholder="e.g. Summarize weekly revenue by region.",
            height=120,
            key="dawn_query_draft",
            label_visibility="collapsed",
        )
        store_as_note = st.checkbox(
            "Treat this message as a context note (store without querying)",
            value=False,
            key="dawn_query_store_as_note",
        )
        submitted = st.form_submit_button("Send")

    return {
        "prompt": prompt.strip(),
        "submitted": submitted,
        "as_note": store_as_note,
        "regenerate": regenerate_clicked,
        "copy_answer": copy_clicked,
    }


def _query_styles() -> str:
    return """
    <style>
        .dawn-chat-heading {
            font-size: 0.95rem;
            letter-spacing: 0.08em;
            font-weight: 700;
            text-transform: uppercase;
            color: rgba(242, 244, 255, 0.82);
            margin-bottom: 0.2rem;
        }
        .dawn-section-subtitle {
            font-size: 0.85rem;
            letter-spacing: 0.06em;
            text-transform: uppercase;
            color: rgba(221, 224, 255, 0.72);
            margin: 1.3rem 0 0.5rem;
            font-weight: 600;
        }
        .dawn-history-list {
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }
        .dawn-history-card {
            border-radius: 12px;
            background: linear-gradient(150deg, rgba(16, 20, 36, 0.85), rgba(24, 18, 40, 0.88));
            padding: 0.75rem;
            border: 1px solid rgba(135, 111, 255, 0.22);
            box-shadow: 0 12px 30px rgba(6, 8, 22, 0.4);
            transition: border 0.2s ease, transform 0.2s ease;
        }
        .dawn-history-card:hover {
            transform: translateX(4px);
            border-color: rgba(255, 154, 118, 0.55);
        }
        .dawn-history-question {
            color: rgba(248, 249, 255, 0.92);
            font-weight: 600;
            font-size: 0.95rem;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        .dawn-history-meta {
            color: rgba(217, 221, 244, 0.62);
            font-size: 0.75rem;
            margin-top: 0.25rem;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        div[data-testid="stChatMessageContent"] {
            border-radius: 18px;
            background: linear-gradient(150deg, rgba(18, 22, 40, 0.7), rgba(20, 17, 43, 0.75));
            border: 1px solid rgba(138, 109, 255, 0.28);
            box-shadow: 0 16px 32px rgba(6, 7, 20, 0.35);
            padding: 0.9rem 1rem;
        }
        div[data-testid="stVerticalBlock"]:has(> div.dawn-chat-panel-anchor) textarea {
            border-radius: 12px;
            border: 1px solid rgba(138, 109, 255, 0.32);
            background: rgba(16, 18, 32, 0.82);
            color: rgba(246, 247, 255, 0.92);
        }
        div[data-testid="stVerticalBlock"]:has(> div.dawn-chat-panel-anchor) textarea:focus {
            border-color: rgba(255, 154, 118, 0.55);
            box-shadow: 0 0 0 1px rgba(255, 154, 118, 0.32);
        }
        div[data-testid="stVerticalBlock"]:has(> div.dawn-chat-panel-anchor) .stButton>button {
            width: 100%;
            border-radius: 10px;
            border: 1px solid rgba(140, 116, 255, 0.35);
            background: linear-gradient(135deg, rgba(255, 140, 102, 0.18), rgba(137, 100, 255, 0.22));
            color: rgba(248, 249, 255, 0.92);
        }
        div[data-testid="stVerticalBlock"]:has(> div.dawn-chat-panel-anchor) .stButton>button:hover {
            border-color: rgba(255, 154, 118, 0.55);
        }
        div[data-testid="stVerticalBlock"]:has(> div.dawn-chat-panel-anchor) .st-expander {
            border-radius: 12px;
            border: 1px solid rgba(135, 111, 255, 0.24);
            background: linear-gradient(150deg, rgba(18, 21, 36, 0.85), rgba(25, 21, 44, 0.88));
            box-shadow: 0 12px 26px rgba(6, 7, 18, 0.35);
        }
        div[data-testid="stVerticalBlock"]:has(> div.dawn-chat-panel-anchor) .st-expander:hover {
            border-color: rgba(255, 154, 118, 0.48);
        }
    </style>
    """
