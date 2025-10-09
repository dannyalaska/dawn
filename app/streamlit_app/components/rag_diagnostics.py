from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from .ui import styled_block


def render_rag_diagnostics(*, diagnostics: Mapping[str, Any] | None) -> None:
    st.markdown(_diag_styles(), unsafe_allow_html=True)
    st.markdown('<h3 class="dawn-section-title">🧠 RAG Diagnostics</h3>', unsafe_allow_html=True)
    st.caption("Understand what DAWN indexed and how the vector store is shaping up.")

    with styled_block("dawn-diag-card"):
        if diagnostics:
            top = st.columns(4)
            top[0].metric("Indexed files", diagnostics.get("files", "—"))
            top[1].metric("Total chunks", diagnostics.get("chunks", "—"))
            top[2].metric("Redis size", diagnostics.get("redis_size_human", "—"))
            top[3].metric("Vector dims", diagnostics.get("dimensions", "—"))

            bottom_left, bottom_right = st.columns(2)
            with bottom_left:
                st.markdown("###### LLM Connection")
                llm_connected = diagnostics.get("llm_connected")
                if llm_connected:
                    st.success(
                        f"Connected to {diagnostics.get('llm_model', 'local model')}", icon="✅"
                    )
                else:
                    st.error("LLM not reachable", icon="⚠️")
                if diagnostics.get("llm_endpoint"):
                    st.caption(f"Endpoint: {diagnostics['llm_endpoint']}")

            with bottom_right:
                st.markdown("###### Redis Index")
                st.markdown(
                    f"""
                    <ul class="dawn-diag-list">
                        <li><strong>Namespace</strong>: {diagnostics.get('redis_namespace', '—')}</li>
                        <li><strong>Index name</strong>: {diagnostics.get('redis_index', '—')}</li>
                        <li><strong>Last refresh</strong>: {diagnostics.get('updated_at', '—')}</li>
                    </ul>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption(
                "No diagnostics loaded yet. Index a file or refresh the API to populate metrics."
            )


def _diag_styles() -> str:
    return """
    <style>
        div[data-testid="stVerticalBlock"]:has(> div.dawn-diag-card-anchor) {
            border-radius: 22px;
            background: linear-gradient(150deg, rgba(22, 20, 39, 0.9), rgba(29, 24, 48, 0.85));
            padding: 1.6rem 1.8rem;
            border: 1px solid rgba(136, 112, 255, 0.28);
            box-shadow: 0 20px 42px rgba(6, 8, 22, 0.5);
        }
        .dawn-diag-card-anchor {
            display: none;
        }
        .dawn-diag-list {
            list-style: none;
            padding-left: 0;
            color: rgba(229, 232, 248, 0.82);
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        .dawn-diag-list li {
            margin-bottom: 0.35rem;
        }
    </style>
    """
