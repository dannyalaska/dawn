from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import streamlit as st


def render_sidebar(
    *,
    recent_uploads: Iterable[Mapping[str, Any]] | None,
    suggested_questions: Iterable[str] | None,
    rag_overview: Mapping[str, Any] | None,
    llm_state: Mapping[str, Any],
    chunk_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Render the branded sidebar and return user interaction details."""
    st.sidebar.markdown(_sidebar_style_block(), unsafe_allow_html=True)
    st.sidebar.markdown(
        """
        <div class="sidebar-brand">☀️ <strong>DAWN</strong></div>
        """,
        unsafe_allow_html=True,
    )

    replay_request: Mapping[str, Any] | None = None
    delete_request: Mapping[str, Any] | None = None
    with st.sidebar.expander("📄 Upload + Ingest", expanded=True):
        st.caption("Bring in spreadsheets and send them to Redis for fast retrieval.")
        if recent_uploads:
            options = [
                f"{entry['filename']} • {entry.get('sheet') or 'Sheet'} • {entry['sha16'][:8]}"
                for entry in recent_uploads
            ]
            recent_key = st.selectbox(
                "Cached previews",
                options=options,
                index=0,
                key="cached_preview_select",
            )
            if st.button("Replay cached preview", key="sidebar_replay_button"):
                replay_request = next(
                    entry
                    for entry in recent_uploads
                    if f"{entry['filename']} • {entry.get('sheet') or 'Sheet'} • {entry['sha16'][:8]}"
                    == recent_key
                )
            if st.button("Delete selected preview", key="sidebar_delete_cached"):
                delete_request = next(
                    entry
                    for entry in recent_uploads
                    if f"{entry['filename']} • {entry.get('sheet') or 'Sheet'} • {entry['sha16'][:8]}"
                    == recent_key
                )
        else:
            st.caption("No uploads indexed yet. Drag one in to get started.")

        clear_all = st.button(
            "Clear all cached previews",
            key="sidebar_clear_cached",
            disabled=not bool(recent_uploads),
        )

    with st.sidebar.expander("🔍 Query + Chat", expanded=False):
        st.caption("Ask follow-ups or reuse helpful prompts.")
        for question in suggested_questions or []:
            st.button(f"Try: {question}", key=f"suggested_{abs(hash(question))}")

    with st.sidebar.expander("🧠 RAG Context Viewer", expanded=False):
        st.caption("Peek into the vector index to debug retrieval.")
        if rag_overview:
            cols = st.columns(2)
            cols[0].metric("Indexed files", rag_overview.get("files", "—"))
            cols[1].metric("Chunks", rag_overview.get("chunks", "—"))
            cols[0].metric("Vector dims", rag_overview.get("dimensions", "—"))
            cols[1].metric("Redis size", rag_overview.get("redis_size", "—"))
        else:
            st.caption("No diagnostics yet — index a file to populate stats.")

    llm_payload: dict[str, Any] | None = None
    with st.sidebar.expander("⚙️ Models & Settings", expanded=False):
        st.caption(
            "Switch between local and hosted models. Keys are stored privately in your .env."
        )
        provider_options = [
            ("stub", "Offline / Stub"),
            ("ollama", "Ollama (local)"),
            ("lmstudio", "LM Studio (OpenAI-compatible)"),
            ("openai", "OpenAI"),
            ("anthropic", "Anthropic Claude"),
        ]
        provider_values = [opt[0] for opt in provider_options]
        provider_index = next(
            (
                idx
                for idx, value in enumerate(provider_values)
                if value == llm_state.get("provider")
            ),
            0,
        )
        provider_choice = st.selectbox(
            "LLM provider",
            options=provider_values,
            index=provider_index,
            format_func=lambda opt: dict(provider_options)[opt],
            key="llm_provider_select",
        )

        llm_payload = {"provider": provider_choice}

        if provider_choice == "ollama":
            ollama_model = st.text_input(
                "Ollama model",
                value=llm_state.get("ollama_model", "llama3"),
                key="llm_ollama_model",
                help="Matches your local `ollama run` models (e.g., llama3.1, mistral-nemo).",
            )
            llm_payload["ollama_model"] = ollama_model.strip()
        elif provider_choice == "lmstudio":
            lmstudio_base = st.text_input(
                "LM Studio base URL",
                value=llm_state.get("lmstudio_base", "http://127.0.0.1:1234"),
                key="llm_lmstudio_base",
            )
            lmstudio_model = st.text_input(
                "LM Studio model",
                value=llm_state.get("lmstudio_model", "mistral-7b-instruct-v0.3"),
                key="llm_lmstudio_model",
            )
            llm_payload["lmstudio_base"] = lmstudio_base.strip()
            llm_payload["lmstudio_model"] = lmstudio_model.strip()
        elif provider_choice == "openai":
            openai_model = st.text_input(
                "OpenAI model",
                value=llm_state.get("openai_model", "gpt-4o-mini"),
                key="llm_openai_model",
            )
            openai_key = st.text_input(
                "OpenAI API key",
                type="password",
                placeholder="Stored" if llm_state.get("openai_key_set") else "sk-...",
                key="llm_openai_key",
            )
            llm_payload["openai_model"] = openai_model.strip()
            if openai_key.strip():
                llm_payload["openai_key"] = openai_key.strip()
        elif provider_choice == "anthropic":
            anthropic_model = st.text_input(
                "Anthropic model",
                value=llm_state.get("anthropic_model", "claude-3-sonnet-20240229"),
                key="llm_anthropic_model",
            )
            anthropic_key = st.text_input(
                "Anthropic API key",
                type="password",
                placeholder="Stored" if llm_state.get("anthropic_key_set") else "anthropic-key-...",
                key="llm_anthropic_key",
            )
            llm_payload["anthropic_model"] = anthropic_model.strip()
            if anthropic_key.strip():
                llm_payload["anthropic_key"] = anthropic_key.strip()

        st.caption(
            "Saving updates .env and environment variables. Restart DAWN if services reload."
        )
        save_clicked = st.button("Save model preferences", key="save_llm_preferences")
        if not save_clicked:
            llm_payload = None

        st.divider()
        st.caption("Vector indexing controls")
        chunk_max = st.slider(
            "Chunk size (characters)",
            min_value=200,
            max_value=2000,
            value=int(chunk_config.get("chunk_max_chars", 600)),
            step=50,
            key="chunk_size_slider",
        )
        chunk_overlap = st.slider(
            "Chunk overlap",
            min_value=0,
            max_value=min(chunk_max - 10, 600),
            value=min(int(chunk_config.get("chunk_overlap", 80)), chunk_max - 10),
            step=10,
            key="chunk_overlap_slider",
        )
        context_k = st.slider(
            "Context chunks (k)",
            min_value=1,
            max_value=12,
            value=int(chunk_config.get("top_k", 6)),
            key="context_k_slider",
        )

    return {
        "replay_request": replay_request,
        "delete_request": delete_request,
        "clear_cache": clear_all,
        "llm_payload": llm_payload,
        "chunk_settings": {
            "chunk_max_chars": chunk_max,
            "chunk_overlap": chunk_overlap,
            "top_k": context_k,
        },
    }


def _sidebar_style_block() -> str:
    return """
    <style>
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #070b18 5%, #10152b 55%, #171033 100%);
            border-right: 1px solid rgba(132, 109, 255, 0.25);
            box-shadow: 6px 0 24px rgba(7, 9, 20, 0.55);
        }
        section[data-testid="stSidebar"] .sidebar-brand {
            font-size: 1.1rem;
            padding-bottom: 1rem;
            margin-bottom: 0.3rem;
            border-bottom: 1px solid rgba(138, 110, 255, 0.3);
            color: rgba(244, 246, 255, 0.85);
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        section[data-testid="stSidebar"] .st-expander {
            border: 1px solid rgba(135, 111, 255, 0.22);
            border-radius: 16px;
            background: linear-gradient(145deg, rgba(16, 19, 35, 0.7), rgba(21, 16, 39, 0.78));
            box-shadow: 0 12px 28px rgba(6, 8, 20, 0.35);
            margin-bottom: 1rem;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        section[data-testid="stSidebar"] .st-expander:hover {
            border: 1px solid rgba(255, 152, 116, 0.45);
        }
        section[data-testid="stSidebar"] .stButton>button {
            width: 100%;
            border-radius: 10px;
            border: 1px solid rgba(255, 150, 116, 0.35);
            background: linear-gradient(135deg, rgba(255, 134, 102, 0.15), rgba(138, 99, 255, 0.18));
            color: rgba(249, 250, 255, 0.88);
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        section[data-testid="stSidebar"] .stButton>button:hover {
            border: 1px solid rgba(139, 104, 255, 0.55);
        }
    </style>
    """
