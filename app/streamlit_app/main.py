from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "dawn_logo.png"
PAGE_ICON = LOGO_PATH if LOGO_PATH.exists() else "☀️"

st.set_page_config(
    page_title="Dawn — Data Copilot",
    page_icon=PAGE_ICON,
    layout="wide",
)

STATE_DEFAULTS: dict[str, Any] = {
    "preview": None,
    "preview_file": None,
    "preview_summary": None,
    "preview_sheet": None,
    "preview_sheets": [],
    "preview_sha": None,
    "last_index": None,
    "suggested_questions": [],
    "query_history": [],
    "current_answer": None,
    "context_notes": [],
    "context_source": None,
    "chunk_config": {"max_chars": 600, "overlap": 80, "top_k": 6},
    "last_prompt": "",
    "auth_token": None,
    "user": None,
    "auth_error": None,
    "backend_cache": None,
}


def _rerun() -> None:
    cast(Any, st).experimental_rerun()


LLM_OPTIONS = [
    ("stub", "Offline / Stub"),
    ("ollama", "Ollama"),
    ("lmstudio", "LM Studio"),
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
]


class APIError(RuntimeError):
    """Raised when an API request fails."""


@dataclass
class ServiceStatus:
    label: str
    detail: str
    state: str  # online | offline | degraded


def main() -> None:
    _init_state()
    _ensure_authenticated()
    health = _fetch_health()
    _render_sidebar(health)
    _render_header()

    tabs = st.tabs(["Upload & Preview", "Context & Memory", "Ask Dawn", "Backend Settings"])
    with tabs[0]:
        _render_preview_tab()
    with tabs[1]:
        _render_context_tab()
    with tabs[2]:
        _render_ask_tab()
    with tabs[3]:
        _render_backend_settings_tab()


def _init_state() -> None:
    for key, value in STATE_DEFAULTS.items():
        if key not in st.session_state:
            if isinstance(value, dict):
                st.session_state[key] = dict(value)
            elif isinstance(value, list):
                st.session_state[key] = list(value)
            else:
                st.session_state[key] = value


def _render_header() -> None:
    logo_col, info_col = st.columns([1, 3], gap="large")
    with logo_col:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=140)
        else:
            st.markdown("### ☀️ Dawn")
    with info_col:
        st.markdown("#### Local AI data copilot")
        st.caption(
            "Profile spreadsheets, capture context notes for retrieval, and ask targeted questions."
        )


def _render_sidebar(health: dict[str, Any] | None) -> None:
    with st.sidebar:
        _render_account_panel()
        st.divider()
        st.subheader("Connection status")
        for status in _service_statuses(health):
            badge = (
                "🟢" if status.state == "online" else ("🟡" if status.state == "degraded" else "🔴")
            )
            st.write(f"{badge} **{status.label}** — {status.detail}")

        st.divider()
        st.subheader("Context recall settings")
        chunk_config = st.session_state["chunk_config"]
        new_size = st.slider(
            "Note size (characters)",
            min_value=200,
            max_value=2000,
            value=int(chunk_config["max_chars"]),
            step=50,
        )
        new_overlap = st.slider(
            "Note overlap",
            min_value=0,
            max_value=min(new_size - 20, 600),
            value=int(chunk_config["overlap"]),
            step=10,
        )
        new_top_k = st.slider(
            "Notes to retrieve (k)",
            min_value=1,
            max_value=12,
            value=int(chunk_config["top_k"]),
        )
        st.session_state["chunk_config"] = {
            "max_chars": new_size,
            "overlap": new_overlap,
            "top_k": new_top_k,
        }

        st.divider()
        _render_llm_settings()


def _render_llm_settings() -> None:
    st.subheader("Model preferences")
    provider = (st.session_state.get("llm_provider") or _current_provider()).lower()
    provider_labels = {value: label for value, label in LLM_OPTIONS}
    provider_choice = st.selectbox(
        "Provider",
        options=[value for value, _ in LLM_OPTIONS],
        index=_provider_index(provider),
        format_func=lambda value: provider_labels[value],
    )

    updates: dict[str, str | None] = {"LLM_PROVIDER": provider_choice}

    if provider_choice == "ollama":
        ollama_model = st.text_input("Ollama model", os.getenv("OLLAMA_MODEL", "llama3"))
        updates["OLLAMA_MODEL"] = ollama_model.strip() or None
    elif provider_choice == "lmstudio":
        base = st.text_input(
            "LM Studio base URL", os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234")
        )
        model = st.text_input("LM Studio model", os.getenv("OPENAI_MODEL", "mistral-7b-instruct"))
        updates["OPENAI_BASE_URL"] = base.strip() or None
        updates["OPENAI_MODEL"] = model.strip() or None
    elif provider_choice == "openai":
        model = st.text_input("OpenAI model", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        key = st.text_input(
            "OpenAI API key",
            type="password",
            placeholder="Stored" if os.getenv("OPENAI_API_KEY") else "sk-...",
        )
        updates["OPENAI_MODEL"] = model.strip() or None
        if key.strip():
            updates["OPENAI_API_KEY"] = key.strip()
    elif provider_choice == "anthropic":
        model = st.text_input(
            "Anthropic model",
            os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
        )
        key = st.text_input(
            "Anthropic API key",
            type="password",
            placeholder="Stored" if os.getenv("ANTHROPIC_API_KEY") else "anthropic-key-...",
        )
        updates["ANTHROPIC_MODEL"] = model.strip() or None
        if key.strip():
            updates["ANTHROPIC_API_KEY"] = key.strip()

    if st.button("Save preferences", use_container_width=True):
        _persist_env_vars(updates)
        st.session_state["llm_provider"] = provider_choice
        st.success("Preferences saved. Restart the backend services if required.")


def _render_account_panel() -> None:
    user = st.session_state.get("user") or {}
    auth_error = st.session_state.get("auth_error")

    if auth_error:
        st.error(auth_error)

    if user and not user.get("is_default", False):
        st.subheader("Account")
        st.caption(
            f"Signed in as {user.get('email', 'unknown')}"
            + (" (default)" if user.get("is_default") else "")
        )
        if st.button("Sign out", key="logout_button", use_container_width=True):
            st.session_state["auth_token"] = None
            st.session_state["user"] = None
            st.session_state["auth_error"] = None
            _ensure_authenticated(force_refresh=True)
            _rerun()
    else:
        st.subheader("Account")
        with st.form("login_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submit = st.form_submit_button("Sign in", use_container_width=True)
            if submit:
                if not email or not password:
                    st.session_state["auth_error"] = "Email and password are required."
                    _rerun()
                else:
                    try:
                        resp = _request_json(
                            "post",
                            "/auth/login",
                            json={"email": email.strip(), "password": password},
                        )
                        st.session_state["auth_token"] = resp.get("token")
                        user_payload = resp.get("user", {})
                        user_payload.setdefault("is_default", False)
                        st.session_state["user"] = user_payload
                        st.session_state["auth_error"] = None
                        _rerun()
                    except APIError as exc:
                        st.session_state["auth_error"] = str(exc)
                        _rerun()

        with st.expander("Create account", expanded=False), st.form("register_form"):
            reg_name = st.text_input("Full name", key="register_name")
            reg_email = st.text_input("Email", key="register_email")
            reg_password = st.text_input("Password", type="password", key="register_password")
            register = st.form_submit_button("Create account", use_container_width=True)
            if register:
                if not reg_email or not reg_password:
                    st.session_state["auth_error"] = "Registration requires an email and password."
                    _rerun()
                else:
                    try:
                        resp = _request_json(
                            "post",
                            "/auth/register",
                            json={
                                "email": reg_email.strip(),
                                "password": reg_password,
                                "full_name": reg_name or None,
                            },
                        )
                        st.session_state["auth_token"] = resp.get("token")
                        user_payload = resp.get("user", {})
                        user_payload.setdefault("is_default", False)
                        st.session_state["user"] = user_payload
                        st.session_state["auth_error"] = None
                        _rerun()
                    except APIError as exc:
                        st.session_state["auth_error"] = str(exc)
                        _rerun()


def _render_preview_tab() -> None:
    st.subheader("Upload an Excel workbook")
    uploaded = st.file_uploader(
        "Excel file",
        type=["xlsx", "xlsm", "xls"],
        help="Data remains on your machine. Upload a workbook to preview its structure.",
    )
    sheet_override = st.text_input(
        "Sheet (optional)",
        value=st.session_state.get("preview_sheet") or "",
        help="Leave blank to analyse the first sheet.",
    )
    preview_button = st.button("Generate preview", use_container_width=True)
    if preview_button:
        if uploaded is None:
            st.warning("Select a workbook before generating a preview.")
        else:
            _handle_preview(uploaded, sheet_override.strip() or None)

    st.divider()
    preview = st.session_state.get("preview")
    if preview:
        _render_preview_details(preview)
    else:
        st.info("No preview yet. Upload a workbook to see its schema and sample rows.")

    st.divider()
    _render_recent_uploads()


def _render_preview_details(preview: dict[str, Any]) -> None:
    cols = st.columns(3)
    cols[0].metric("Rows", preview.get("shape", [0, 0])[0])
    cols[1].metric("Columns", preview.get("shape", [0, 0])[1])
    cols[2].metric("Cached", "Yes" if preview.get("cached") else "No")

    st.markdown("##### Columns")
    columns_df = pd.DataFrame(preview.get("columns") or [])
    if not columns_df.empty:
        st.dataframe(columns_df, use_container_width=True, hide_index=True)
    else:
        st.caption("No columns detected.")

    st.markdown("##### Sample rows")
    rows_df = pd.DataFrame(preview.get("rows") or [])
    if not rows_df.empty:
        st.dataframe(rows_df, use_container_width=True, hide_index=True, height=260)
    else:
        st.caption("No sample rows returned.")

    st.markdown("##### Index to Redis")
    preview_file = st.session_state.get("preview_file")
    if not preview_file:
        st.caption("Re-upload the workbook above and regenerate the preview to enable indexing.")
    if st.button(
        "Index dataset",
        use_container_width=True,
        disabled=preview_file is None,
        help=None if preview_file else "Upload the original file to index it into Redis.",
    ):
        _handle_index()

    summary = st.session_state.get("preview_summary")
    if summary:
        _render_summary(summary)


def _render_summary(summary: dict[str, Any]) -> None:
    st.markdown("##### Highlights")
    metrics = summary.get("metrics") or []
    insights = summary.get("insights") or {}

    if metrics:
        for metric in metrics[:3]:
            label = metric.get("description") or metric.get("column") or "Metric"
            values = metric.get("values") or []
            df = pd.DataFrame(values, columns=["Value", "Count"])
            st.write(f"**{label}**")
            st.dataframe(df, use_container_width=True, hide_index=True)
    elif insights:
        for key, values in list(insights.items())[:3]:
            preview = ", ".join(f"{entry['label']} ({entry['count']})" for entry in values[:3])
            st.write(f"- **{key}** → {preview}")
    else:
        st.caption("Index the dataset to populate highlights and insights.")


def _render_recent_uploads() -> None:
    st.subheader("Cached previews")
    uploads = _fetch_recent_uploads()
    if not uploads:
        st.caption("No cached uploads yet.")
        return

    labels = [
        f"{entry['filename']} • {entry.get('sheet') or 'sheet'} • {entry['sha16'][:8]}"
        for entry in uploads
    ]
    selection = st.selectbox(
        "Recent uploads",
        options=["— Select —", *labels],
        index=0,
    )

    if selection != "— Select —":
        entry = uploads[labels.index(selection)]
        load_col, delete_col = st.columns(2)
        if load_col.button("Load preview", key=f"load_{entry['sha16']}"):
            _load_cached_preview(entry)
        if delete_col.button("Remove cached preview", key=f"delete_{entry['sha16']}"):
            _delete_cached_preview(entry)

    if st.button("Clear all cached previews", use_container_width=True):
        _clear_cached_previews()


def _render_context_tab() -> None:
    st.subheader("Context memory")
    source = st.session_state.get("context_source")
    if not source:
        st.info("Index a dataset to unlock your saved context notes and add commentary.")
        return

    st.write(f"Active source: `{source}`")
    st.caption("These notes are short excerpts Dawn saved so answers can cite the original data.")
    if st.button("Refresh context", use_container_width=True):
        _refresh_context()

    chunks = st.session_state.get("context_notes") or []
    if chunks:
        total_manual = sum(
            1
            for chunk in chunks
            if str(chunk.get("type", "")).lower() in {"note", "manual", "annotation"}
        )
        covered_rows = len(
            {chunk.get("row_index") for chunk in chunks if isinstance(chunk.get("row_index"), int)}
        )
        summary_cols = st.columns(3)
        summary_cols[0].metric("Saved context notes", len(chunks))
        summary_cols[1].metric("Manual notes", total_manual)
        summary_cols[2].metric("Rows represented", covered_rows)
    else:
        st.caption("No notes captured yet. Index a dataset or refresh after indexing.")

    for chunk in chunks[:20]:
        chunk_id = chunk.get("id", "unknown")
        header = f"{chunk_id} • row {chunk.get('row_index', '—')}"
        with st.expander(header, expanded=False):
            text_key = f"context_edit_{chunk_id}"
            new_text = st.text_area("Note text", value=chunk.get("text", ""), key=text_key)
            if st.button("Save", key=f"context_save_{chunk_id}"):
                _update_context_note(chunk_id, new_text)

    st.markdown("##### Add a note")
    with st.form("context_note"):
        note_text = st.text_area(
            "Store definitions, unit conversions, or gotchas.",
            placeholder="e.g. Resolution_Time_Hours is business hours, not calendar hours.",
            height=120,
        )
        submitted = st.form_submit_button("Add note")
    if submitted and note_text.strip():
        _add_context_note(note_text.strip())


def _render_ask_tab() -> None:
    st.subheader("Ask Dawn")

    suggestions = st.session_state.get("suggested_questions") or []
    if suggestions:
        st.caption("Suggested prompts")
        btn_cols = st.columns(len(suggestions))
        for col, suggestion in zip(btn_cols, suggestions, strict=False):
            if col.button(suggestion, key=f"suggestion_{hash(suggestion)}"):
                _handle_query(suggestion, reason="suggestion")

    answer = st.session_state.get("current_answer")
    if answer:
        st.markdown("##### Latest answer")
        st.write(answer.get("text") or "_No answer yet._")
        st.caption(f"Asked: {answer.get('timestamp')}")
        if st.button("Regenerate", use_container_width=True):
            last_prompt = st.session_state.get("last_prompt")
            if last_prompt:
                _handle_query(last_prompt, reason="regenerate")

    st.markdown("##### Ask a question")
    prompt = st.text_area(
        "Ask about indexed data",
        placeholder="e.g. Who resolved the most tickets last week?",
        height=140,
    )
    ask_button = st.button("Send", use_container_width=True)
    if ask_button:
        if prompt.strip():
            _handle_query(prompt.strip())
        else:
            st.warning("Enter a question first.")

    history = st.session_state.get("query_history") or []
    if history:
        st.markdown("##### Recent questions")
        for entry in history[:6]:
            st.write(f"- {entry['question']} ({entry['timestamp']})")


# ---------------------------------------------------------------------------
# Preview + indexing helpers
# ---------------------------------------------------------------------------


def _handle_preview(uploaded, sheet: str | None) -> None:
    file_bytes = uploaded.getvalue()
    files = {
        "file": (
            uploaded.name,
            file_bytes,
            uploaded.type or "application/octet-stream",
        )
    }
    params = {"sheet": sheet} if sheet else None
    try:
        with st.spinner("Profiling workbook…"):
            data = _request_json("post", "/ingest/preview", files=files, params=params, timeout=45)
    except APIError as exc:
        st.error(f"Preview failed: {exc}")
        return

    st.session_state["preview"] = data
    st.session_state["preview_file"] = {
        "name": uploaded.name,
        "bytes": file_bytes,
        "content_type": uploaded.type or "application/octet-stream",
    }
    st.session_state["preview_sheet"] = data.get("sheet")
    st.session_state["preview_sheets"] = data.get("sheet_names") or []
    st.session_state["preview_sha"] = data.get("sha16")
    st.session_state["preview_summary"] = None
    st.session_state["last_index"] = None
    st.session_state["context_notes"] = []
    st.toast(f"Preview ready for {uploaded.name}", icon="📊")


def _handle_index() -> None:
    payload = st.session_state.get("preview_file")
    preview = st.session_state.get("preview")
    if not payload or not preview:
        st.warning("Generate a preview first.")
        return

    params = {
        "sheet": st.session_state.get("preview_sheet"),
        "chunk_max_chars": str(st.session_state["chunk_config"]["max_chars"]),
        "chunk_overlap": str(st.session_state["chunk_config"]["overlap"]),
    }
    files = {
        "file": (
            payload["name"],
            payload["bytes"],
            payload.get("content_type", "application/octet-stream"),
        )
    }
    try:
        with st.spinner("Indexing into Redis…"):
            result = _request_json(
                "post", "/rag/index_excel", params=params, files=files, timeout=90
            )
    except APIError as exc:
        st.error(f"Indexing failed: {exc}")
        return

    st.session_state["last_index"] = {**result, "indexed_at": _timestamp()}
    st.session_state["preview_summary"] = result.get("summary")
    st.session_state["context_source"] = f"{result.get('source')}:{result.get('sheet')}"
    st.session_state["suggested_questions"] = _suggestions_from_summary(result.get("summary"))
    st.toast("Dataset indexed. Context is ready to query.", icon="✅")
    _refresh_context()


def _load_cached_preview(entry: dict[str, Any]) -> None:
    params = {"sha16": entry["sha16"]}
    if entry.get("sheet"):
        params["sheet"] = entry["sheet"]
    try:
        with st.spinner("Loading cached preview…"):
            data = _request_json("get", "/ingest/preview_cached", params=params, timeout=10)
    except APIError as exc:
        st.error(f"Failed to load cached preview: {exc}")
        return

    st.session_state["preview"] = data
    st.session_state["preview_file"] = None
    st.session_state["preview_sheet"] = data.get("sheet")
    st.session_state["preview_sheets"] = data.get("sheet_names") or []
    st.session_state["preview_summary"] = None
    st.session_state["last_index"] = None
    st.session_state["preview_sha"] = entry["sha16"]
    st.session_state["context_notes"] = []
    st.toast("Cached preview loaded.", icon="📂")


def _delete_cached_preview(entry: dict[str, Any]) -> None:
    params = {"sha16": entry["sha16"]}
    if entry.get("sheet"):
        params["sheet"] = entry["sheet"]
    try:
        _request_json("delete", "/ingest/preview_cached", params=params, timeout=10)
        st.toast("Cached preview removed.", icon="🗑️")
    except APIError as exc:
        st.error(f"Failed to delete cached preview: {exc}")


def _clear_cached_previews() -> None:
    try:
        _request_json("delete", "/ingest/preview_cached/all", timeout=15)
        st.toast("Cleared all cached previews.", icon="🧹")
    except APIError as exc:
        st.error(f"Failed to clear cached previews: {exc}")


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------


def _refresh_context() -> None:
    source = st.session_state.get("context_source")
    if not source:
        return
    try:
        data = _request_json("get", "/rag/context", params={"source": source}, timeout=15)
    except APIError as exc:
        st.error(f"Failed to load context: {exc}")
        return

    notes_payload = data.get("notes") or data.get("chunks") or []
    st.session_state["context_notes"] = notes_payload


def _update_context_note(chunk_id: str, text: str) -> None:
    if not text.strip():
        st.warning("Note text cannot be empty.")
        return
    try:
        _request_json("put", f"/rag/context/{chunk_id}", json={"text": text.strip()}, timeout=10)
    except APIError as exc:
        st.error(f"Failed to update note: {exc}")
        return
    st.toast("Note updated.", icon="✏️")
    _refresh_context()


def _add_context_note(note: str) -> None:
    source = st.session_state.get("context_source")
    if not source:
        st.warning("Index a dataset before adding notes.")
        return
    try:
        _request_json(
            "post",
            "/rag/context/note",
            json={"source": source, "text": note},
            timeout=10,
        )
    except APIError as exc:
        st.error(f"Failed to add note: {exc}")
        return
    st.toast("Note stored in context.", icon="📝")
    _refresh_context()


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def _handle_query(prompt: str, *, reason: str = "ask") -> None:
    params = {
        "q": prompt,
        "k": int(st.session_state["chunk_config"]["top_k"]),
    }
    try:
        with st.spinner("Searching indexed context…"):
            data = _request_json("get", "/rag/answer", params=params, timeout=60)
    except APIError as exc:
        st.error(f"Query failed: {exc}")
        return

    timestamp = _timestamp()
    st.session_state["current_answer"] = {
        "text": data.get("answer", ""),
        "timestamp": timestamp,
        "prompt": prompt,
    }
    sources = data.get("sources") or []
    st.session_state["context_notes"] = [
        {
            "id": chunk.get("id") or f"{idx}",
            "text": chunk.get("text", ""),
            "source": chunk.get("source", ""),
            "score": _format_score(chunk.get("score")),
            "row_index": chunk.get("row_index"),
        }
        for idx, chunk in enumerate(sources)
    ]

    history = st.session_state.get("query_history") or []
    history.insert(0, {"question": prompt, "timestamp": timestamp})
    st.session_state["query_history"] = history[:8]
    st.session_state["last_prompt"] = prompt

    toast = {
        "ask": "Answer ready.",
        "suggestion": "Loaded suggestion.",
        "regenerate": "Answer refreshed.",
    }.get(reason, "Answer ready.")
    st.toast(toast, icon="💡")


def _render_backend_settings_tab() -> None:
    st.subheader("Backend Settings")
    st.caption(
        "Configure external databases or storage endpoints. Saved connections stay local and are scoped to your account."
    )

    try:
        connections = _fetch_backend_connections()
    except APIError as exc:
        st.error(f"Unable to load backend connections: {exc}")
        connections = []

    if connections:
        for connection in connections:
            with st.expander(f"{connection['name']} ({connection['kind']})", expanded=False):
                name_input = st.text_input(
                    "Name",
                    value=connection["name"],
                    key=f"backend_name_{connection['id']}",
                )
                config_input = st.text_area(
                    "Configuration (JSON)",
                    value=json.dumps(connection.get("config") or {}, indent=2),
                    key=f"backend_config_{connection['id']}",
                    height=180,
                )
                col_save, col_delete = st.columns(2)
                if col_save.button("Save changes", key=f"backend_save_{connection['id']}"):
                    if not name_input.strip():
                        st.error("Name is required.")
                    else:
                        try:
                            config_payload = json.loads(config_input or "{}")
                        except json.JSONDecodeError as exc:
                            st.error(f"Invalid JSON: {exc}")
                        else:
                            try:
                                _request_json(
                                    "put",
                                    f"/backends/{connection['id']}",
                                    json={"name": name_input.strip(), "config": config_payload},
                                    timeout=10,
                                )
                                st.success("Connection updated")
                                _rerun()
                            except APIError as exc:
                                st.error(f"Failed to update connection: {exc}")
                if col_delete.button("Delete", key=f"backend_delete_{connection['id']}"):
                    try:
                        _delete_backend_connection(connection["id"])
                        _rerun()
                    except APIError as exc:
                        st.error(f"Failed to delete connection: {exc}")
    else:
        st.info("No backend connections yet.")

    st.divider()
    st.subheader("Add Connection")
    with st.form("backend_create_form"):
        name = st.text_input("Name", key="backend_new_name")
        kind = st.selectbox("Kind", ("postgres", "mysql", "s3"), key="backend_new_kind")
        config_text = st.text_area(
            "Configuration (JSON)",
            value="{}",
            key="backend_new_config",
            height=180,
        )
        submitted = st.form_submit_button("Save connection", use_container_width=True)
        if submitted:
            if not name.strip():
                st.error("Connection name is required.")
            else:
                try:
                    config_payload = json.loads(config_text or "{}")
                except json.JSONDecodeError as exc:
                    st.error(f"Invalid JSON: {exc}")
                else:
                    try:
                        _create_backend_connection(name.strip(), kind, config_payload)
                        st.success("Connection saved")
                        _rerun()
                    except APIError as exc:
                        st.error(f"Failed to save connection: {exc}")


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _request_json(
    method: str,
    path: str,
    *,
    timeout: float = 15,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    url = f"{API_BASE.rstrip('/')}/{path.lstrip('/')}"
    request_headers = dict(headers or {})
    token = st.session_state.get("auth_token")
    if token:
        request_headers.setdefault("Authorization", f"Bearer {token}")
    try:
        response = requests.request(
            method.upper(),
            url,
            timeout=timeout,
            params=params,
            json=json,
            files=files,
            headers=request_headers or None,
        )
        if response.status_code == 401:
            if st.session_state.get("auth_token"):
                st.session_state["auth_token"] = None
                st.session_state["user"] = None
            raise APIError("Unauthorized")
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - streamlit surface
        raise APIError(str(exc)) from exc

    if not response.content:
        return {}

    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        return response.json()
    try:
        return response.json()
    except ValueError:
        return {}


def _fetch_health() -> dict[str, Any] | None:
    try:
        return _request_json("get", "/health", timeout=5)
    except APIError:
        return None


def _ensure_authenticated(force_refresh: bool = False) -> None:
    if force_refresh:
        st.session_state["user"] = None

    if st.session_state.get("user") is not None:
        return

    try:
        user = _request_json("get", "/auth/me", timeout=5)
        st.session_state["user"] = user
        st.session_state["auth_error"] = None
    except APIError as exc:  # pragma: no cover - display in UI
        st.session_state["user"] = None
        st.session_state["auth_error"] = str(exc)


def _fetch_recent_uploads() -> list[dict[str, Any]]:
    try:
        data = _request_json("get", "/ingest/recent", timeout=8)
    except APIError:
        return []
    if isinstance(data, list):
        return data
    return []


def _service_statuses(health: dict[str, Any] | None) -> list[ServiceStatus]:
    if not health:
        return [
            ServiceStatus("API", "Unreachable", "offline"),
            ServiceStatus("Database", "Unknown", "offline"),
            ServiceStatus("Redis", "Unknown", "offline"),
            ServiceStatus("LLM", "Unknown", "offline"),
        ]
    statuses: list[ServiceStatus] = []
    statuses.append(
        ServiceStatus(
            "API",
            f"ENV: {health.get('env', 'dev')}",
            "online" if health.get("ok") else "degraded",
        )
    )
    statuses.append(
        ServiceStatus(
            "Database",
            "Connected" if health.get("db") else "Unavailable",
            "online" if health.get("db") else "offline",
        )
    )
    statuses.append(
        ServiceStatus(
            "Redis",
            "Connected" if health.get("redis") else "Unavailable",
            "online" if health.get("redis") else "offline",
        )
    )
    llm = health.get("llm") or {}
    statuses.append(
        ServiceStatus(
            "LLM",
            str(llm.get("detail") or llm.get("provider") or "Unknown"),
            "online" if llm.get("ok") else ("degraded" if llm else "offline"),
        )
    )
    return statuses


def _fetch_backend_connections() -> list[dict[str, Any]]:
    data = _request_json("get", "/backends", timeout=8)
    if isinstance(data, dict):
        return data.get("connections", [])
    return []


def _create_backend_connection(name: str, kind: str, config: dict[str, Any]) -> dict[str, Any]:
    payload = {"name": name, "kind": kind, "config": config}
    return _request_json("post", "/backends", json=payload, timeout=10)


def _delete_backend_connection(connection_id: int) -> None:
    _request_json("delete", f"/backends/{connection_id}", timeout=10)


def _persist_env_vars(updates: dict[str, str | None]) -> None:
    meaningful = {k: v for k, v in updates.items() if v}
    if not meaningful:
        return

    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text().splitlines()

    positions: dict[str, int] = {}
    for idx, line in enumerate(lines):
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0]
            positions[key] = idx

    for key, raw_value in meaningful.items():
        value = str(raw_value)
        line = f"{key}={value}"
        if key in positions:
            lines[positions[key]] = line
        else:
            lines.append(line)
        os.environ[key] = value

    ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""))


def _suggestions_from_summary(summary: dict[str, Any] | None) -> list[str]:
    if not summary:
        return []
    suggestions: list[str] = []
    metrics = summary.get("metrics") or []
    for metric in metrics:
        column = metric.get("column")
        if column:
            suggestions.append(f"Show the top values for {column}.")
    insights = summary.get("insights") or {}
    if not suggestions and insights:
        for column in insights:
            suggestions.append(f"Who leads for {column}?")
    return suggestions[:3]


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")


def _format_score(raw: Any) -> str:
    try:
        return f"{float(raw):.3f}"
    except Exception:  # noqa: BLE001
        return "-"


def _current_provider() -> str:
    return (st.session_state.get("llm_provider") or os.getenv("LLM_PROVIDER") or "stub").lower()


def _provider_index(provider: str) -> int:
    for idx, (value, _) in enumerate(LLM_OPTIONS):
        if value == provider:
            return idx
    return 0


if __name__ == "__main__":
    main()
