from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import streamlit as st


def render_context_editor(
    *,
    source: str | None,
    entries: Iterable[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Render a lightweight context editing surface for Redis-backed chunks."""
    events: dict[str, Any] = {}

    if not source:
        st.info("Index a dataset to unlock context editing.")
        return events

    st.caption(f"Active context source: `{source}`")

    chunks = list(entries or [])
    refresh_clicked = st.button("Refresh context", key="dawn_context_refresh_button")
    if refresh_clicked:
        events["refresh"] = True

    total_chunks = len(chunks)
    note_count = sum(1 for c in chunks if (c.get("type") or "excel").lower() == "note")
    summary_cols = st.columns(2)
    summary_cols[0].metric("Chunks", total_chunks)
    summary_cols[1].metric("Notes", note_count)

    filter_text = st.text_input(
        "Filter chunks",
        key="dawn_context_filter",
        placeholder="Search text, source, or row number",
    ).strip()
    if filter_text:
        lowered = filter_text.lower()
        chunks = [
            c
            for c in chunks
            if lowered in str(c.get("text", "")).lower()
            or lowered in str(c.get("source", "")).lower()
            or lowered in str(c.get("row_index", "")).lower()
            or lowered in str(c.get("type", "")).lower()
        ]

    if not chunks:
        st.info("No context chunks found yet. Index a file or add a note below.")
    else:
        list_col, editor_col = st.columns([1.4, 2])
        selected_chunk = None
        with list_col:
            options = [
                f"{c['id']} • row {c.get('row_index', '—')} • {c.get('type', 'excel')}"
                for c in chunks
            ]
            default_index = 0
            selected_label = st.selectbox(
                "Stored chunks",
                options=options,
                index=default_index if options else 0,
                key="dawn_context_editor_select",
            )
            if selected_label:
                idx = options.index(selected_label)
                selected_chunk = chunks[idx]

            if selected_chunk:
                st.write("**Preview**")
                st.write(selected_chunk.get("text", ""))

        with editor_col:
            if selected_chunk:
                st.caption(
                    f"Row: {selected_chunk.get('row_index', '—')} · Type: {selected_chunk.get('type', 'excel')}"
                )
                with st.form("dawn_context_editor_update_form", clear_on_submit=False):
                    new_text = st.text_area(
                        "Edit chunk",
                        value=selected_chunk.get("text", ""),
                        height=240,
                    )
                    save_clicked = st.form_submit_button("Save changes")
                if save_clicked:
                    events["update"] = {
                        "id": selected_chunk["id"],
                        "text": new_text,
                    }
            else:
                st.info("Select a chunk to edit its contents.")

    with st.form("dawn_context_editor_add_form", clear_on_submit=False):
        new_note = st.text_area(
            "Add a context note",
            placeholder="e.g. The `Amount` column is stored in cents; divide by 100 for dollars.",
            height=140,
        )
        add_clicked = st.form_submit_button("Add note to context")
    if add_clicked:
        if new_note.strip():
            events["note"] = new_note.strip()
        else:
            st.warning("Enter some text before adding a context note.")

    return events
