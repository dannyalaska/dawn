from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

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
    "agent_feed_cache": None,
    "agent_runs": [],
    "agent_last_run": None,
    "runner_meta": None,
    "lmstudio_models": None,
    "lmstudio_models_error": None,
}


def _rerun() -> None:
    cast(Any, st).experimental_rerun()


def _is_embed_mode() -> bool:
    params = st.query_params
    raw = params.get("embed") if isinstance(params, dict) else None
    if isinstance(raw, list):
        embed = (raw[0] if raw else "").lower()
    elif isinstance(raw, str):
        embed = raw.lower()
    else:
        embed = ""
    env_embed = os.getenv("DAWN_EMBED", "").lower()
    return embed in {"1", "true", "runner"} or env_embed in {"1", "true", "runner"}


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
    embed_mode = _is_embed_mode()
    _ensure_authenticated()
    health = _fetch_health()
    runner_meta = _fetch_runner_meta()
    st.session_state["runner_meta"] = runner_meta

    if embed_mode:
        _render_runner_tab(embedded=True)
        return

    _render_sidebar(health)
    _render_header()

    tabs = st.tabs(
        [
            "Upload & Preview",
            "Context & Memory",
            "Agent Swarm",
            "Ask Dawn",
            "Backend Settings",
            "Runner Dashboard",
        ]
    )
    with tabs[0]:
        _render_preview_tab()
    with tabs[1]:
        _render_context_tab()
    with tabs[2]:
        _render_agents_tab()
    with tabs[3]:
        _render_ask_tab()
    with tabs[4]:
        _render_backend_settings_tab()
    with tabs[5]:
        _render_runner_tab()


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
        ollama_model = st.text_input(
            "Ollama model", os.getenv("OLLAMA_MODEL", "llama3"), key="ollama_model_input"
        )
        updates["OLLAMA_MODEL"] = ollama_model.strip() or None
    elif provider_choice == "lmstudio":
        base = st.text_input(
            "LM Studio base URL",
            os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234"),
            key="lmstudio_base_input",
        )
        model = st.text_input(
            "LM Studio model",
            os.getenv("OPENAI_MODEL", "mistral-7b-instruct"),
            key="lmstudio_model_input",
        )
        updates["OPENAI_BASE_URL"] = base.strip() or None
        updates["OPENAI_MODEL"] = model.strip() or None
        _render_lmstudio_controls(base.strip() or None)
    elif provider_choice == "openai":
        model = st.text_input(
            "OpenAI model", os.getenv("OPENAI_MODEL", "gpt-4o-mini"), key="openai_model_input"
        )
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
            key="anthropic_model_input",
        )
        key = st.text_input(
            "Anthropic API key",
            type="password",
            placeholder="Stored" if os.getenv("ANTHROPIC_API_KEY") else "anthropic-key-...",
        )
        updates["ANTHROPIC_MODEL"] = model.strip() or None
        if key.strip():
            updates["ANTHROPIC_API_KEY"] = key.strip()

    if st.button("Save preferences", width="stretch"):
        _persist_env_vars(updates)
        st.session_state["llm_provider"] = provider_choice
        st.success("Preferences saved. Restart the backend services if required.")


def _render_lmstudio_controls(base_url: str | None) -> None:
    with st.expander("LM Studio model manager", expanded=False):
        st.caption("Requires the LM Studio server and CLI. Start it with `lms server start`.")

        if st.button("Refresh LM Studio models", width="stretch"):
            try:
                st.session_state["lmstudio_models"] = _fetch_lmstudio_models(base_url)
                st.session_state["lmstudio_models_error"] = None
            except Exception as exc:  # noqa: BLE001
                st.session_state["lmstudio_models"] = None
                st.session_state["lmstudio_models_error"] = str(exc)

        error = st.session_state.get("lmstudio_models_error")
        if error:
            st.error(f"LM Studio models unavailable: {error}")

        models = st.session_state.get("lmstudio_models") or []
        if not models:
            st.info("Click refresh to load available models.")
            return

        loaded = [model for model in models if model.get("state") == "loaded"]
        st.write(f"Loaded models: {len(loaded)}")

        table_rows: list[dict[str, Any]] = []
        model_key_map: dict[str, str] = {}
        for model in models:
            model_id = model.get("id", "")
            model_key = _lmstudio_model_key(model)
            if model_id:
                model_key_map[str(model_id)] = model_key or str(model_id)
            table_rows.append(
                {
                    "id": model_id,
                    "publisher": model.get("publisher", ""),
                    "state": model.get("state", ""),
                    "type": model.get("type", ""),
                    "quantization": model.get("quantization", ""),
                    "max_context": model.get("max_context_length", ""),
                }
            )
        st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

        model_ids = [model.get("id") for model in models if model.get("id")]
        if not model_ids:
            st.warning("No model identifiers returned by LM Studio.")
            return

        default_model = os.getenv("OPENAI_MODEL") or (
            loaded[0].get("id") if loaded else model_ids[0]
        )
        if default_model not in model_ids:
            default_model = model_ids[0]
        selected_model = st.selectbox(
            "Select model",
            options=model_ids,
            index=model_ids.index(default_model),
            key="lmstudio_model_select",
        )

        selected_state: dict[str, Any] = next(
            (m for m in models if m.get("id") == selected_model), {}
        )
        is_loaded = selected_state.get("state") == "loaded"
        selected_key = model_key_map.get(str(selected_model), str(selected_model))
        st.caption(f"CLI model key: {selected_key}")

        with st.expander("Advanced load options", expanded=False):
            identifier = st.text_input(
                "Identifier (optional)",
                value=selected_model,
                help="Overrides the model name exposed via the API.",
                key="lmstudio_identifier_input",
            )
            context_length = st.number_input(
                "Context length (optional)",
                min_value=0,
                max_value=65536,
                value=0,
                step=256,
                help="Set to 0 to use the model default.",
                key="lmstudio_context_length_input",
            )
            gpu_setting = st.text_input(
                "GPU setting (optional)",
                value="",
                help="Example: max, auto, or a specific GPU preset supported by LM Studio.",
                key="lmstudio_gpu_input",
            )
            ttl_seconds = st.number_input(
                "Unload after (seconds, optional)",
                min_value=0,
                max_value=86_400,
                value=0,
                step=60,
                help="Set to 0 to disable automatic unload.",
                key="lmstudio_ttl_input",
            )

        action_col, eject_col, swap_col = st.columns(3)
        with action_col:
            if st.button("Load", disabled=is_loaded, width="stretch"):
                try:
                    _lmstudio_load_model(
                        selected_key,
                        base_url=base_url,
                        identifier=identifier.strip() or None,
                        context_length=int(context_length) or None,
                        gpu=gpu_setting.strip() or None,
                        ttl_seconds=int(ttl_seconds) or None,
                    )
                    st.success(f"Loaded {selected_model}")
                    st.session_state["lmstudio_models"] = _fetch_lmstudio_models(base_url)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Load failed: {exc}")

        with eject_col:
            if st.button("Eject", disabled=not is_loaded, width="stretch"):
                try:
                    _lmstudio_unload_model(selected_key, base_url=base_url)
                    st.success(f"Ejected {selected_model}")
                    st.session_state["lmstudio_models"] = _fetch_lmstudio_models(base_url)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Eject failed: {exc}")
            if st.button("Eject all", width="stretch"):
                try:
                    _lmstudio_unload_model(None, base_url=base_url, unload_all=True)
                    st.success("All models unloaded")
                    st.session_state["lmstudio_models"] = _fetch_lmstudio_models(base_url)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Eject failed: {exc}")

        with swap_col:
            unload_first = st.checkbox("Unload others before swap", value=True)
            if st.button("Swap + use", width="stretch"):
                try:
                    api_model_name = identifier.strip() or selected_model
                    if unload_first:
                        _lmstudio_unload_model(None, base_url=base_url, unload_all=True)
                    _lmstudio_load_model(
                        selected_key,
                        base_url=base_url,
                        identifier=api_model_name or None,
                        context_length=int(context_length) or None,
                        gpu=gpu_setting.strip() or None,
                        ttl_seconds=int(ttl_seconds) or None,
                    )
                    _persist_env_vars(
                        {
                            "LLM_PROVIDER": "lmstudio",
                            "OPENAI_MODEL": api_model_name,
                            "OPENAI_BASE_URL": base_url or None,
                        }
                    )
                    st.session_state["llm_provider"] = "lmstudio"
                    st.session_state["lmstudio_model_input"] = api_model_name
                    st.success(f"Swapped to {api_model_name}")
                    st.session_state["lmstudio_models"] = _fetch_lmstudio_models(base_url)
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Swap failed: {exc}")


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
        if st.button("Sign out", key="logout_button", width="stretch"):
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
            submit = st.form_submit_button("Sign in", width="stretch")
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
            register = st.form_submit_button("Create account", width="stretch")
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
    preview_button = st.button("Generate preview", width="stretch")
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
        st.dataframe(columns_df, width="stretch", hide_index=True)
    else:
        st.caption("No columns detected.")

    st.markdown("##### Sample rows")
    rows_df = pd.DataFrame(preview.get("rows") or [])
    if not rows_df.empty:
        st.dataframe(rows_df, width="stretch", hide_index=True, height=260)
    else:
        st.caption("No sample rows returned.")

    st.markdown("##### Index to Redis")
    preview_file = st.session_state.get("preview_file")
    if not preview_file:
        st.caption("Re-upload the workbook above and regenerate the preview to enable indexing.")
    if st.button(
        "Index dataset",
        width="stretch",
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
            st.dataframe(df, width="stretch", hide_index=True)
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

    if st.button("Clear all cached previews", width="stretch"):
        _clear_cached_previews()


def _render_context_tab() -> None:
    st.subheader("Context memory")
    source = st.session_state.get("context_source")
    if not source:
        st.info("Index a dataset to unlock your saved context notes and add commentary.")
        return

    st.write(f"Active source: `{source}`")
    st.caption("These notes are short excerpts Dawn saved so answers can cite the original data.")
    if st.button("Refresh context", width="stretch"):
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


def _render_agents_tab() -> None:
    st.subheader("Agent Swarm")
    feed_cache = _ensure_agent_feeds()
    with st.expander("Available feeds", expanded=False):
        if st.button("Reload feed list", key="agent_reload_feeds", use_container_width=True):
            feed_cache = _ensure_agent_feeds(force_refresh=True)
        if feed_cache:
            for feed in feed_cache[:6]:
                latest = feed.get("latest_version") or {}
                name = feed.get("name", feed["identifier"])
                version = latest.get("number", "—")
                rows = latest.get("rows", 0) or 0
                st.write(f"- **{name}** (`{feed['identifier']}`) — v{version}, {rows} rows")

    if not feed_cache:
        st.info(
            "Index a dataset first—agents depend on stored summaries. "
            "Once a feed exists, reload the list above."
        )
        return

    selected_feed = st.selectbox(
        "Select feed",
        options=feed_cache,
        format_func=lambda feed: f"{feed.get('name', feed['identifier'])} ({feed['identifier']})",
        key="agent_feed_choice",
    )
    question = st.text_area(
        "Optional question for QA agent",
        placeholder="Who resolved the most tickets last week?",
        key="agent_question",
        height=120,
    )
    col_opts = st.columns(3)
    refresh_context = col_opts[0].toggle(
        "Refresh context memory", value=True, key="agent_refresh_toggle"
    )
    max_plan = col_opts[1].slider(
        "Max plan steps", min_value=3, max_value=20, value=12, key="agent_plan_steps"
    )
    retrieval_k = col_opts[2].slider(
        "Retrieval k", min_value=3, max_value=12, value=6, key="agent_retrieval_k"
    )

    run_button = st.button("Run agents", use_container_width=True, key="agent_run_button")
    if run_button and selected_feed:
        payload = {
            "feed_identifier": selected_feed["identifier"],
            "question": question.strip() or None,
            "refresh_context": refresh_context,
            "max_plan_steps": max_plan,
            "retrieval_k": retrieval_k,
        }
        try:
            with st.spinner("Coordinating multi-agent workflow…"):
                result = _trigger_agent_run(payload)
        except APIError as exc:
            st.error(f"Agent run failed: {exc}")
        else:
            result["requested_at"] = _timestamp()
            st.session_state["agent_last_run"] = result
            history = [result, *st.session_state.get("agent_runs", [])]
            st.session_state["agent_runs"] = history[:5]
            st.toast("Agent run complete.", icon="🤖")

    last_run = st.session_state.get("agent_last_run")
    if not last_run:
        st.caption("Run the agents to see plan steps, outputs, and QA answers.")
        return

    _render_agent_run(last_run)

    history = st.session_state.get("agent_runs") or []
    if len(history) > 1:
        st.markdown("##### Recent runs")
        for run in history[1:]:
            label = run.get("requested_at", "unknown time")
            st.write(f"- {run.get('feed_identifier', 'unknown')} @ {label} — {run.get('status')}")


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
        if st.button("Regenerate", width="stretch"):
            last_prompt = st.session_state.get("last_prompt")
            if last_prompt:
                _handle_query(last_prompt, reason="regenerate")

    st.markdown("##### Ask a question")
    prompt = st.text_area(
        "Ask about indexed data",
        placeholder="e.g. Who resolved the most tickets last week?",
        height=140,
    )
    ask_button = st.button("Send", width="stretch")
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
                grants_text = "\n".join(connection.get("schema_grants") or [])
                grants_input = st.text_area(
                    "Schema grants (one per line)",
                    value=grants_text,
                    key=f"backend_schema_grants_{connection['id']}",
                    height=120,
                    help="Restrict agent access to specific schemas. Applies to Postgres and Snowflake.",
                )
                if st.button(
                    "List available schemas",
                    key=f"backend_schema_list_{connection['id']}",
                ):
                    try:
                        schema_resp = _request_json(
                            "get",
                            f"/backends/{connection['id']}/schemas",
                            timeout=12,
                        )
                    except APIError as exc:
                        st.error(f"Failed to list schemas: {exc}")
                    else:
                        schemas = schema_resp.get("schemas") or []
                        if schemas:
                            st.success(f"Available schemas: {', '.join(schemas)}")
                        else:
                            st.info("No schemas returned for this connection.")
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
                            schema_grants = _parse_schema_grants_input(grants_input)
                            try:
                                _request_json(
                                    "put",
                                    f"/backends/{connection['id']}",
                                    json={
                                        "name": name_input.strip(),
                                        "config": config_payload,
                                        "schema_grants": schema_grants,
                                    },
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
        kind = st.selectbox(
            "Kind", ("postgres", "mysql", "s3", "snowflake"), key="backend_new_kind"
        )
        config_text = st.text_area(
            "Configuration (JSON)",
            value="{}",
            key="backend_new_config",
            height=180,
        )
        grants_text = st.text_area(
            "Schema grants (optional, one per line)",
            key="backend_new_grants",
            height=100,
        )
        submitted = st.form_submit_button("Save connection", width="stretch")
        if submitted:
            if not name.strip():
                st.error("Connection name is required.")
            else:
                try:
                    config_payload = json.loads(config_text or "{}")
                except json.JSONDecodeError as exc:
                    st.error(f"Invalid JSON: {exc}")
                else:
                    schema_grants = _parse_schema_grants_input(grants_text)
                    try:
                        _create_backend_connection(
                            name.strip(),
                            kind,
                            config_payload,
                            schema_grants=schema_grants,
                        )
                        st.success("Connection saved")
                        _rerun()
                    except APIError as exc:
                        st.error(f"Failed to save connection: {exc}")


def _render_runner_tab(embedded: bool = False) -> None:
    meta = st.session_state.get("runner_meta") or {}
    jobs = meta.get("jobs") or {}
    runs = meta.get("runs") or {}
    st.subheader("Runner Dashboard")
    if not meta:
        st.info("Runner stats unavailable. Ensure you're authenticated and try again.")
        if st.button("Retry"):
            _rerun()
        return

    col_jobs, col_active, col_runs = st.columns(3)
    col_jobs.metric("Jobs", jobs.get("total", 0), f"scheduled {jobs.get('scheduled', 0)}")
    col_active.metric("Active jobs", jobs.get("active", 0))
    col_runs.metric("Runs", runs.get("total", 0), f"success {runs.get('success', 0)}")

    col_success, col_failed = st.columns(2)
    col_success.metric("Successful runs", runs.get("success", 0))
    col_failed.metric("Failed runs", runs.get("failed", 0))

    last_run = runs.get("last_run") or {}
    st.markdown("##### Last run")
    if last_run.get("status"):
        st.write(
            f"- Status: **{last_run['status']}**\n"
            f"- Finished at: {last_run.get('finished_at') or 'n/a'}\n"
            f"- Duration: {last_run.get('duration_seconds') or 'n/a'}s"
        )
    else:
        st.write("No runs recorded yet.")

    if not embedded:
        st.divider()
        st.markdown("##### Embed in portal")
        app_url = os.getenv("DAWN_APP_URL", "http://127.0.0.1:8501")
        iframe_url = f"{app_url.rstrip('/')}/?embed=runner"
        snippet = (
            f'<iframe src="{iframe_url}" width="100%" height="640" frameborder="0" '
            f'allow="clipboard-write; clipboard-read"></iframe>'
        )
        st.code(snippet, language="html")
        if st.button("Refresh stats"):
            _rerun()


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _lmstudio_rest_base(base_url: str | None) -> str:
    base = base_url or os.getenv("OPENAI_BASE_URL") or "http://127.0.0.1:1234"
    base = base.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def _lmstudio_host(base_url: str | None) -> str | None:
    raw = base_url or os.getenv("OPENAI_BASE_URL") or "http://127.0.0.1:1234"
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path
    return host or None


def _lmstudio_model_key(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "")
    publisher = str(model.get("publisher") or "")
    if not model_id:
        return ""
    if "/" in model_id or not publisher:
        return model_id
    return f"{publisher}/{model_id}"


def _fetch_lmstudio_models(base_url: str | None) -> list[dict[str, Any]]:
    rest_base = _lmstudio_rest_base(base_url)
    url = f"{rest_base}/api/v0/models"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data
    if isinstance(payload, list):
        return payload
    return []


def _run_lms_command(args: list[str], *, base_url: str | None, timeout: int = 60) -> str:
    lms_path = shutil.which("lms")
    if not lms_path:
        raise RuntimeError("LM Studio CLI ('lms') not found. Install it or add to PATH.")
    host = _lmstudio_host(base_url)
    cmd = [lms_path, *args]
    if host:
        cmd.extend(["--host", host])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(message or "LM Studio CLI command failed.")
    return (result.stdout or "").strip()


def _lmstudio_load_model(
    model_key: str,
    *,
    base_url: str | None,
    identifier: str | None = None,
    context_length: int | None = None,
    gpu: str | None = None,
    ttl_seconds: int | None = None,
) -> str:
    args = ["load", model_key]
    if identifier:
        args.extend(["--identifier", identifier])
    if context_length:
        args.extend(["--context-length", str(context_length)])
    if gpu:
        args.extend(["--gpu", gpu])
    if ttl_seconds:
        args.extend(["--ttl", str(ttl_seconds)])
    return _run_lms_command(args, base_url=base_url)


def _lmstudio_unload_model(
    model_key: str | None,
    *,
    base_url: str | None,
    unload_all: bool = False,
) -> str:
    args = ["unload"]
    if unload_all:
        args.append("--all")
    elif model_key:
        args.append(model_key)
    else:
        raise RuntimeError("Model key required to unload a specific model.")
    return _run_lms_command(args, base_url=base_url)


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


def _fetch_feeds_index() -> list[dict[str, Any]]:
    data = _request_json("get", "/feeds", timeout=10)
    if isinstance(data, dict):
        feeds = data.get("feeds")
        if isinstance(feeds, list):
            return feeds
    return []


def _trigger_agent_run(payload: dict[str, Any]) -> dict[str, Any]:
    return _request_json("post", "/agents/analyze", json=payload, timeout=120)


def _ensure_agent_feeds(*, force_refresh: bool = False) -> list[dict[str, Any]]:
    cache_key = "agent_feed_cache"
    if force_refresh or cache_key not in st.session_state or st.session_state[cache_key] is None:
        try:
            feeds = _fetch_feeds_index()
        except APIError as exc:
            st.error(f"Unable to load feeds: {exc}")
            feeds = []
        if feeds:
            st.session_state[cache_key] = feeds
            st.success(f"Loaded {len(feeds)} feeds.")
        else:
            st.session_state[cache_key] = []
    return st.session_state.get(cache_key) or []


def _render_agent_run(run: dict[str, Any]) -> None:
    st.markdown("#### Latest run")
    info_cols = st.columns(3)
    info_cols[0].metric(
        "Feed",
        run.get("feed_identifier", "—"),
        help=run.get("feed_name") or "Feed identifier",
    )
    info_cols[1].metric("Status", (run.get("status") or "unknown").upper())
    info_cols[2].metric("Warnings", len(run.get("warnings") or []))
    st.caption(f"Requested at {run.get('requested_at', _timestamp())}")

    plan = run.get("plan") or []
    if plan:
        st.markdown("##### Planner output")
        plan_rows = [
            {"step": idx + 1, **entry} for idx, entry in enumerate(plan) if isinstance(entry, dict)
        ]
        st.dataframe(pd.DataFrame(plan_rows), use_container_width=True)

    completed = run.get("completed") or []
    if completed:
        st.markdown("##### Executor results")
        for result in completed:
            st.markdown(f"**{result.get('description', result.get('type'))}**")
            st.json(result.get("data", {}), expanded=False)

    answer = run.get("answer")
    if answer:
        st.markdown("##### QA answer")
        st.write(answer)
        sources = run.get("answer_sources") or []
        if sources:
            st.caption("Sources")
            st.json(sources, expanded=False)

    context_updates = run.get("context_updates") or []
    if context_updates:
        st.markdown("##### Memory updates")
        for update in context_updates[:10]:
            st.write(f"- {update.get('text')}")

    warnings = run.get("warnings") or []
    if warnings:
        st.warning("\n".join(str(msg) for msg in warnings))

    final_report = run.get("final_report")
    if final_report:
        st.markdown("##### Final report")
        st.code(final_report, language="markdown")

    run_log = run.get("run_log") or []
    if run_log:
        st.markdown("##### Run log")
        log_rows = [
            {
                "agent": entry.get("agent"),
                "message": entry.get("message"),
                "details": json.dumps(
                    {k: v for k, v in entry.items() if k not in {"agent", "message"}}, indent=2
                ),
            }
            for entry in run_log
        ]
        st.table(pd.DataFrame(log_rows))


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


def _fetch_runner_meta() -> dict[str, Any] | None:
    try:
        return _request_json("get", "/jobs/runner/meta", timeout=6)
    except APIError:
        return None


def _create_backend_connection(
    name: str, kind: str, config: dict[str, Any], *, schema_grants: list[str] | None = None
) -> dict[str, Any]:
    payload = {"name": name, "kind": kind, "config": config}
    if schema_grants:
        payload["schema_grants"] = schema_grants
    return _request_json("post", "/backends", json=payload, timeout=10)


def _delete_backend_connection(connection_id: int) -> None:
    _request_json("delete", f"/backends/{connection_id}", timeout=10)


def _parse_schema_grants_input(raw_text: str | None) -> list[str]:
    if not raw_text:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for line in raw_text.splitlines():
        cleaned = line.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


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
