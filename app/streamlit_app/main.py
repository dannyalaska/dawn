from __future__ import annotations

import base64
import os
import time
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st
from components import (
    render_context_editor,
    render_feed_wizard,
    render_header,
    render_nl_filter_lab,
    render_query_workspace,
    render_rag_diagnostics,
    render_sidebar,
    render_upload_area,
    styled_block,
)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
LOGO_PATH = "app/streamlit_app/assets/dawn_logo.png"
ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = (ROOT_DIR / ".env").resolve()

page_icon: str | Path = Path(LOGO_PATH) if Path(LOGO_PATH).exists() else "☀️"
st.set_page_config(
    page_title="DAWN — Local Data Copilot",
    page_icon=page_icon,
    layout="wide",
    initial_sidebar_state="expanded",
)


def _init_session_state() -> None:
    defaults: dict[str, Any] = {
        "dawn_preview_data": {},
        "dawn_preview_summary": None,
        "dawn_preview_upload": None,
        "dawn_last_index_result": None,
        "dawn_suggested_questions": [],
        "dawn_query_history": [],
        "dawn_current_answer": None,
        "dawn_context_chunks": [],
        "dawn_total_chunks_indexed": 0,
        "dawn_preview_chart": None,
        "dawn_sheet_names": [],
        "dawn_selected_sheet": "",
        "dawn_current_sha": None,
        "dawn_chat_open": True,
        "dawn_llm_provider": os.getenv("LLM_PROVIDER", "stub").lower(),
        "dawn_llm_restart_required": False,
        "dawn_chunk_max_chars": 600,
        "dawn_chunk_overlap": 80,
        "dawn_rag_top_k": 6,
        "dawn_splash_done": False,
        "dawn_last_prompt": "",
        "dawn_context_editor_refresh_token": 0.0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            if isinstance(value, list):
                st.session_state[key] = list(value)
            elif isinstance(value, dict):
                st.session_state[key] = dict(value)
            else:
                st.session_state[key] = value


def _inject_base_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                color-scheme: dark;
            }
            html, body, [data-testid="stAppViewContainer"], div, section, button {
                font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif !important;
            }
            .material-icons, [class*="material-icons"], span[data-baseweb="icon"] {
                font-family: 'Material Icons' !important;
            }
            [data-testid="stAppViewContainer"] {
                background:
                    radial-gradient(circle at 15% 10%, rgba(255, 140, 95, 0.18), transparent 58%),
                    radial-gradient(circle at 85% 5%, rgba(104, 81, 210, 0.22), transparent 50%),
                    linear-gradient(180deg, #050814 0%, #0b1022 55%, #120c2c 100%);
            }
            .block-container {
                padding: 2.4rem 2.6rem 3.6rem;
                max-width: 1480px;
            }
            hr {
                border: none;
                height: 2px;
                background: linear-gradient(90deg, #6b5bff, #3c7dff, #ff8a65, #ffd166, #ff8a65, #3c7dff, #6b5bff);
                opacity: 0.85;
            }
            .dawn-block-anchor { display: none; }
            div[data-testid="stVerticalBlock"]:has(> div.dawn-chat-panel-anchor) {
                background: linear-gradient(150deg, rgba(22, 20, 39, 0.92), rgba(29, 24, 48, 0.88));
                border-radius: 22px;
                border: 1px solid rgba(136, 112, 255, 0.35);
                box-shadow: 0 18px 36px rgba(5, 6, 18, 0.45);
                padding: 1.2rem 1.4rem;
                position: sticky;
                top: 6rem;
                height: fit-content;
                z-index: 5;
            }
            .dawn-chat-toggle-wrap {
                display: flex;
                justify-content: flex-end;
                margin-bottom: 0.75rem;
            }
            .dawn-chat-toggle-wrap button {
                width: auto;
            }
            .dawn-splash {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                gap: 0.8rem;
                height: 75vh;
                text-align: center;
                color: rgba(246, 247, 255, 0.92);
                animation: dawnFade 1s ease forwards;
            }
            .dawn-splash-title {
                font-size: 2.4rem;
                font-weight: 800;
                letter-spacing: 0.3em;
                background: linear-gradient(90deg, #ffb347, #ff7e5f 45%, #8a63ff 90%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            @keyframes dawnFade {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _maybe_show_splash() -> None:
    if st.session_state.get("dawn_splash_done"):
        return
    placeholder = st.empty()
    logo_path = _logo_path_or_none()
    if logo_path:
        encoded = base64.b64encode(Path(logo_path).read_bytes()).decode("utf-8")
        splash_markup = f"""
        <div class="dawn-splash">
            <img src="data:image/png;base64,{encoded}" width="220" alt="DAWN logo" />
        </div>
        """
    else:
        splash_markup = """
        <div class="dawn-splash">
            <div class="dawn-splash-title">DAWN</div>
        </div>
        """
    placeholder.markdown(splash_markup, unsafe_allow_html=True)
    time.sleep(1.0)
    placeholder.empty()
    st.session_state["dawn_splash_done"] = True


def _logo_path_or_none() -> str | None:
    path = Path(LOGO_PATH)
    return str(path) if path.exists() else None


def _current_provider() -> str:
    stored = st.session_state.get("dawn_llm_provider")
    if stored:
        return str(stored).lower()
    return os.getenv("LLM_PROVIDER", "stub").lower()


def _current_llm_config() -> dict[str, Any]:
    provider = _current_provider()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    lmstudio_model = os.getenv("OPENAI_MODEL", "mistral-7b-instruct-v0.3")
    return {
        "provider": provider,
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3"),
        "lmstudio_model": lmstudio_model,
        "lmstudio_base": os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234"),
        "openai_model": openai_model,
        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "anthropic_model": os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229"),
        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),
    }


def _update_env_vars(updates: dict[str, str | None]) -> None:
    if not updates:
        return
    env_path = ENV_PATH
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()
    key_positions: dict[str, int] = {}
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0]
        key_positions[key] = idx

    for key, raw_value in updates.items():
        if raw_value is None:
            continue
        value = str(raw_value)
        line = f"{key}={value}"
        if key in key_positions:
            lines[key_positions[key]] = line
        else:
            lines.append(line)
        os.environ[key] = value

    env_path.write_text("\n".join(lines) + "\n")


def _apply_llm_settings(payload: dict[str, Any]) -> None:
    if not payload:
        return
    provider = str(payload.get("provider") or _current_provider()).lower()
    updates: dict[str, str | None] = {"LLM_PROVIDER": provider}

    if provider == "ollama":
        model = str(payload.get("ollama_model") or os.getenv("OLLAMA_MODEL", "llama3"))
        updates["OLLAMA_MODEL"] = model
    elif provider == "lmstudio":
        base = str(
            payload.get("lmstudio_base") or os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234")
        )
        model = str(
            payload.get("lmstudio_model") or os.getenv("OPENAI_MODEL", "mistral-7b-instruct-v0.3")
        )
        updates["OPENAI_BASE_URL"] = base
        updates["OPENAI_MODEL"] = model
    elif provider == "openai":
        model = str(payload.get("openai_model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
        updates["OPENAI_MODEL"] = model
        key = payload.get("openai_key")
        if key:
            updates["OPENAI_API_KEY"] = str(key)
    elif provider == "anthropic":
        model = str(
            payload.get("anthropic_model")
            or os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
        )
        updates["ANTHROPIC_MODEL"] = model
        key = payload.get("anthropic_key")
        if key:
            updates["ANTHROPIC_API_KEY"] = str(key)

    _update_env_vars(updates)
    if st.session_state.get("dawn_llm_provider") != provider:
        st.session_state["dawn_llm_restart_required"] = True
    st.session_state["dawn_llm_provider"] = provider
    st.toast(
        "Model preferences saved. Restart DAWN to load the new model backend.",
        icon="⚙️",
    )


def _delete_cached_preview(entry: dict[str, Any]) -> None:
    params: dict[str, str] = {"sha16": str(entry.get("sha16", ""))}
    sheet = entry.get("sheet")
    if sheet:
        params["sheet"] = str(sheet)
    try:
        resp = requests.delete(
            f"{API_BASE}/ingest/preview_cached",
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        st.toast("Removed cached preview.", icon="🗑️")
        st.session_state.pop("cached_preview_select", None)
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to delete cached preview: {exc}")


def _clear_cached_previews() -> None:
    try:
        resp = requests.delete(f"{API_BASE}/ingest/preview_cached/all", timeout=10)
        resp.raise_for_status()
        st.toast("Cleared all cached previews.", icon="🧹")
        st.session_state["dawn_preview_data"] = None
        st.session_state["dawn_preview_summary"] = None
        st.session_state["dawn_preview_upload"] = None
        st.session_state["dawn_last_index_result"] = None
        st.session_state["dawn_preview_chart"] = None
        st.session_state["dawn_sheet_names"] = []
        st.session_state["dawn_selected_sheet"] = ""
        st.session_state["dawn_current_sha"] = None
        st.session_state.pop("cached_preview_select", None)
        st.rerun()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to clear cached previews: {exc}")


def _fetch_health() -> dict[str, Any] | None:
    try:
        resp = requests.get(f"{API_BASE}/health", timeout=3)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _service_statuses() -> list[dict[str, str]]:
    health = _fetch_health()
    return [
        _api_status(health),
        _db_status(health),
        _redis_status(health),
        _llm_status(health),
    ]


def _api_status(health: dict[str, Any] | None) -> dict[str, str]:
    if not health:
        return {"label": "API", "state": "offline", "detail": "API unreachable"}
    env = health.get("env", "dev")
    state = "online" if health.get("ok", False) else "degraded"
    return {"label": "API", "state": state, "detail": f"ENV: {env}"}


def _db_status(health: dict[str, Any] | None) -> dict[str, str]:
    connected = bool(health and health.get("db"))
    state = "online" if connected else "offline"
    detail = "Database connected" if connected else "DB not responding"
    return {"label": "DB", "state": state, "detail": detail}


def _redis_status(health: dict[str, Any] | None) -> dict[str, str]:
    connected = bool(health and health.get("redis"))
    state = "online" if connected else "offline"
    detail = "Redis connected" if connected else "Redis not responding"
    return {"label": "Redis", "state": state, "detail": detail}


def _llm_status(health: dict[str, Any] | None) -> dict[str, str]:
    if health and isinstance(health.get("llm"), dict):
        llm_info = health["llm"]
        provider = str(llm_info.get("provider", "stub")).upper()
        ok = bool(llm_info.get("ok", False))
        detail = llm_info.get("detail") or provider
        state = "online" if ok else ("degraded" if provider.lower() == "stub" else "offline")
        return {"label": "LLM", "state": state, "detail": detail}

    provider = _current_provider()
    if provider == "stub":
        return {
            "label": "LLM",
            "state": "degraded",
            "detail": "Stub responses active. Connect LM Studio or Ollama.",
        }
    if provider == "ollama":
        model = os.getenv("OLLAMA_MODEL", "llama3")
        return {
            "label": "LLM",
            "state": "online",
            "detail": f"Ollama • model: {model}",
        }
    if provider == "lmstudio":
        base = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234")
        model = os.getenv("OPENAI_MODEL", "mistral-7b-instruct-v0.3")
        return {
            "label": "LLM",
            "state": "online",
            "detail": f"LM Studio • {model} @ {base}",
        }
    if provider == "openai":
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        key_present = bool(os.getenv("OPENAI_API_KEY"))
        state = "online" if key_present else "offline"
        detail = f"OpenAI • model: {model}"
        if not key_present:
            detail = "OpenAI • API key missing"
        return {"label": "LLM", "state": state, "detail": detail}
    if provider == "anthropic":
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
        key_present = bool(os.getenv("ANTHROPIC_API_KEY"))
        state = "online" if key_present else "offline"
        detail = f"Anthropic • model: {model}"
        if not key_present:
            detail = "Anthropic • API key missing"
        return {"label": "LLM", "state": state, "detail": detail}
    label = provider.upper()
    return {"label": label, "state": "degraded", "detail": "Custom provider configured"}


def _fetch_recent_uploads() -> list[dict[str, Any]]:
    try:
        resp = requests.get(f"{API_BASE}/ingest/recent", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _fetch_rag_ping() -> dict[str, Any]:
    try:
        resp = requests.get(f"{API_BASE}/rag/ping", timeout=3)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {"index_ready": False}


def _fetch_jobs() -> list[dict[str, Any]]:
    refresh_token = st.session_state.get("dawn_jobs_refresh_token")
    _ = refresh_token
    try:
        resp = requests.get(f"{API_BASE}/jobs", timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            jobs = data.get("jobs")
            if isinstance(jobs, list):
                return jobs
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _run_job_now(job_id: int) -> dict[str, Any] | None:
    try:
        resp = requests.post(f"{API_BASE}/jobs/{job_id}/run", timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else None
    except Exception as exc:  # noqa: BLE001
        st.error(f"Job run failed: {exc}")
        return None


def _fetch_feed_catalog() -> list[dict[str, Any]]:
    refresh_token = st.session_state.get("dawn_feed_refresh_token")
    _ = refresh_token  # appease lint; token is read to trigger reruns
    try:
        resp = requests.get(f"{API_BASE}/feeds", timeout=8)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.session_state["dawn_feed_catalog_error"] = str(exc)
        return []

    st.session_state.pop("dawn_feed_catalog_error", None)
    if isinstance(data, dict):
        feeds = data.get("feeds")
        if isinstance(feeds, list):
            return feeds
    return []


def _apply_feed_to_quick_insight(feed: dict[str, Any]) -> bool:
    latest = feed.get("latest_version") or {}
    summary = latest.get("summary") or {}
    profile = latest.get("profile") or {}
    schema = latest.get("schema") or {}
    sample_rows = summary.get("sample_rows") or profile.get("sample_rows") or []
    if not sample_rows:
        st.warning("No sample rows stored yet. Re-ingest or preview the feed to snapshot data.")
        return False
    columns_schema = schema.get("columns") or []
    if not columns_schema:
        st.warning("Column metadata missing; cannot load Quick Insight view.")
        return False

    raw_row_count = summary.get("row_count") or profile.get("row_count")
    raw_col_count = (
        summary.get("column_count") or profile.get("column_count") or len(columns_schema)
    )
    total_rows = int(raw_row_count) if isinstance(raw_row_count, int | float) else len(sample_rows)
    total_cols = (
        int(raw_col_count) if isinstance(raw_col_count, int | float) else len(columns_schema)
    )

    preview_columns: list[dict[str, Any]] = []
    for column in columns_schema:
        name = column.get("name")
        if not name:
            continue
        dtype = column.get("dtype")
        non_null_raw = column.get("non_null")
        non_null_val = int(non_null_raw) if isinstance(non_null_raw, int | float) else None
        nulls_val: int | None = None
        if non_null_val is not None:
            nulls_val = max(total_rows - non_null_val, 0)
        samples: list[str] = []
        for row in sample_rows:
            if name in row and row[name] is not None:
                samples.append(str(row[name]))
            if len(samples) >= 3:
                break
        preview_columns.append(
            {
                "name": name,
                "dtype": dtype,
                "non_null": non_null_val if non_null_val is not None else 0,
                "nulls": nulls_val if nulls_val is not None else 0,
                "sample": samples,
            }
        )

    sheet_names = (
        latest.get("sheet_names") or summary.get("sheet_names") or profile.get("sheet_names") or []
    )
    sheet = (
        summary.get("sheet")
        or latest.get("sheet")
        or feed.get("favorite_sheet")
        or (sheet_names[0] if sheet_names else "Sheet1")
    )

    preview_data = {
        "sheet": sheet,
        "shape": (total_rows, total_cols),
        "columns": preview_columns,
        "rows": sample_rows,
    }

    st.session_state["dawn_preview_data"] = preview_data
    st.session_state["dawn_preview_summary"] = summary
    st.session_state["dawn_preview_upload"] = None
    st.session_state["dawn_preview_chart"] = None
    st.session_state["dawn_last_index_result"] = None
    st.session_state["dawn_sheet_names"] = sheet_names
    st.session_state["dawn_selected_sheet"] = sheet
    st.session_state["dawn_current_sha"] = latest.get("sha16")
    _update_suggestions(summary)
    _update_preview_chart(summary)
    st.toast(f"Loaded {feed.get('name') or feed.get('identifier')} into Quick Insight.", icon="📚")
    return True


def _set_feed_favorite(identifier: str, sheet: str) -> bool:
    try:
        resp = requests.post(
            f"{API_BASE}/feeds/{identifier}/favorite",
            json={"sheet": sheet},
            timeout=8,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to favorite sheet: {exc}")
        return False
    st.toast(f"Favorite sheet set to {sheet}.", icon="⭐️")
    return True


def _create_job(
    *,
    name: str,
    feed_identifier: str,
    feed_version: int,
    schedule: str | None,
    transform_name: str | None,
    run_after_create: bool,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "name": name,
        "feed_identifier": feed_identifier,
        "feed_version": feed_version,
        "schedule": schedule,
        "is_active": True,
    }
    if transform_name:
        payload["transform_name"] = transform_name
    try:
        resp = requests.post(f"{API_BASE}/jobs", json=payload, timeout=12)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to create job: {exc}")
        return None
    job = resp.json()
    st.toast(f"Job “{job.get('name', name)}” created.", icon="🛠️")
    job_id = job.get("id")
    if run_after_create and job_id:
        _run_job_now(int(job_id))
    return job


def _render_feed_overview(feeds: list[dict[str, Any]]) -> None:
    st.markdown("### 📚 Registered feeds")
    controls = st.columns([3, 1], vertical_alignment="center")
    with controls[1]:
        if st.button("Refresh feeds", key="dawn_refresh_feeds"):
            st.session_state["dawn_feed_refresh_token"] = time.time()
            st.experimental_rerun()

    error_msg = st.session_state.get("dawn_feed_catalog_error")
    if not feeds:
        if error_msg:
            st.error(f"Failed to load feeds: {error_msg}")
        else:
            st.info("Ingest a dataset to populate your feed library.")
        return

    options = [
        f"{feed.get('name') or feed['identifier']} · `{feed['identifier']}`" for feed in feeds
    ]
    identifier_map = {feed["identifier"]: idx for idx, feed in enumerate(feeds)}
    current_identifier = st.session_state.get("dawn_feed_selected")
    default_index = identifier_map.get(current_identifier, 0)
    selection = st.selectbox(
        "Pick a feed",
        options,
        index=default_index if 0 <= default_index < len(options) else 0,
        key="dawn_feed_selector",
    )
    selected_idx = options.index(selection)
    selected_feed = feeds[selected_idx]
    identifier = selected_feed["identifier"]
    st.session_state["dawn_feed_selected"] = identifier

    latest = selected_feed.get("latest_version") or {}
    summary = latest.get("summary") or {}
    columns_info = summary.get("columns") or []
    metrics_info = summary.get("metrics") or []
    plan_info = summary.get("analysis_plan") or []
    sample_rows = summary.get("sample_rows") or latest.get("profile", {}).get("sample_rows") or []

    def _fmt_int(value: Any) -> str:
        try:
            return f"{int(value):,}"
        except Exception:
            return "—"

    owner = selected_feed.get("owner") or "—"
    src_type = selected_feed.get("source_type") or "—"
    st.caption(f"Owner: {owner} • Source: {src_type}")

    metrics_cols = st.columns(4)
    metrics_cols[0].metric("Rows", _fmt_int(latest.get("rows")))
    metrics_cols[1].metric("Columns", _fmt_int(latest.get("columns")))
    metrics_cols[2].metric("Version", f"v{latest.get('number', '—')}")
    metrics_cols[3].metric("Favorite sheet", selected_feed.get("favorite_sheet") or "—")

    action_cols = st.columns([1, 1, 1])
    open_clicked = action_cols[0].button(
        "Open in Quick Insight",
        key=f"dawn_feed_open_{selected_feed['identifier']}",
    )
    if open_clicked and _apply_feed_to_quick_insight(selected_feed):
        st.session_state["workspace_mode"] = "Quick Insight"
        st.session_state.pop("quick_insight_seed", None)
        st.rerun()

    sheet_names = (
        latest.get("sheet_names")
        or summary.get("sheet_names")
        or latest.get("profile", {}).get("sheet_names")
        or selected_feed.get("favorite_sheet")
        or []
    )
    if isinstance(sheet_names, str):
        sheet_names = [sheet_names]
    if sheet_names:
        try:
            default_sheet_index = sheet_names.index(
                selected_feed.get("favorite_sheet") or summary.get("sheet") or sheet_names[0],
            )
        except ValueError:
            default_sheet_index = 0
    sheet_col, star_col = st.columns([3, 1])
    picked_sheet = sheet_col.selectbox(
        "Worksheet",
        sheet_names,
        index=default_sheet_index,
        key=f"dawn_sheet_choice_{identifier}",
    )
    favorite_clicked = star_col.button("⭐ Favorite", key=f"dawn_favorite_sheet_{identifier}")
    if favorite_clicked and _set_feed_favorite(identifier, picked_sheet):
        st.rerun()

    if metrics_info:
        st.markdown("#### Highlights")
        metric_columns = st.columns(max(1, min(2, len(metrics_info))))
        for idx, metric in enumerate(metrics_info[:4]):
            with metric_columns[idx % len(metric_columns)]:
                label = metric.get("description") or metric.get("column") or "Metric"
                values = metric.get("values") or []
                df_metric = pd.DataFrame(values)
                if not df_metric.empty:
                    df_metric.columns = ["Value", "Count"]
                    st.markdown(f"**{label}**")
                    st.table(df_metric)

    if columns_info:
        st.markdown("#### Column signals")
        for column in columns_info[:5]:
            name = column.get("name")
            dtype = column.get("dtype")
            top_values = column.get("top_values") or []
            stats = column.get("stats") or {}
            if top_values:
                preview = ", ".join(f"{label} ({count})" for label, count in top_values[:3])
                st.write(f"- **{name}** ({dtype}) → {preview}")
            elif stats:
                stat_preview = ", ".join(f"{k}={v:.2f}" for k, v in stats.items())
                st.write(f"- **{name}** ({dtype}) → {stat_preview}")
            else:
                st.write(f"- **{name}** ({dtype})")

    if plan_info:
        st.markdown("#### Analysis plan")
        for step in plan_info[:6]:
            parts = [
                str(step.get("type", "step")),
                str(step.get("column") or step.get("group") or ""),
            ]
            if step.get("value"):
                parts.append(str(step["value"]))
            if step.get("stat"):
                parts.append(str(step["stat"]))
            joined = " · ".join(part for part in parts if part)
            st.write(f"- {joined}")

    if sample_rows:
        st.markdown("#### Sample rows")
        sample_df = pd.DataFrame(sample_rows)
        st.dataframe(sample_df, use_container_width=True, height=260)

    version_number = latest.get("number")
    version_number_int = int(version_number) if isinstance(version_number, int | float) else None
    if version_number:
        context_source = f"feed:{identifier}:v{version_number}"
        context_chunks = _fetch_context_chunks(context_source)
        note_chunks = [
            chunk for chunk in context_chunks if str(chunk.get("type", "")).lower() == "note"
        ]
        st.markdown("#### Memory notes")
        if note_chunks:
            for note in note_chunks:
                st.write(f"- {note.get('text', '')}")
        else:
            st.caption("Capture unit conventions, business rules, or playbook tips here.")

        with st.form(f"dawn_context_note_form_{identifier}", clear_on_submit=False):
            note_text = st.text_area(
                "Add a note for assistants & automations",
                key=f"dawn_context_note_area_{identifier}",
                height=110,
            )
            note_saved = st.form_submit_button("Save note")
        if note_saved and _add_context_note(note_text, source=context_source):
            st.success("Note saved.")
            st.rerun()

    if version_number_int:
        st.markdown("#### Automation")
        default_job_name = f"{selected_feed.get('name') or identifier} refresh"
        with st.form(f"dawn_job_form_{identifier}", clear_on_submit=False):
            job_name = st.text_input(
                "Job name",
                value=default_job_name,
                key=f"dawn_job_name_{identifier}",
            )
            schedule_value = st.text_input(
                "Schedule (cron)",
                value="0 9 * * 1-5",
                help="Use cron format (e.g., 0 9 * * 1-5 for weekdays at 9am). Leave blank for manual runs.",
                key=f"dawn_job_schedule_{identifier}",
            )
            transform_value = st.text_input(
                "Transform name (optional)",
                value="",
                key=f"dawn_job_transform_{identifier}",
            )
            run_now = st.checkbox(
                "Run immediately after creating",
                value=True,
                key=f"dawn_job_run_now_{identifier}",
            )
            job_submit = st.form_submit_button("Create job")
        if job_submit:
            cleaned_name = job_name.strip() or default_job_name
            schedule_clean = schedule_value.strip() or None
            transform_clean = transform_value.strip() or None
            created_job = _create_job(
                name=cleaned_name,
                feed_identifier=identifier,
                feed_version=version_number_int,
                schedule=schedule_clean,
                transform_name=transform_clean,
                run_after_create=run_now,
            )
            if created_job:
                st.session_state["dawn_jobs_refresh_token"] = time.time()
                st.rerun()


def _render_jobs_panel(jobs: list[dict[str, Any]]) -> None:
    st.markdown("### Jobs & Pipelines")
    if not jobs:
        st.info("No jobs configured yet. Create a transform to enable automated runs.")
        return
    for job in jobs:
        job_id = job.get("id")
        name = job.get("name", "Job")
        feed_label = job.get("feed") or "—"
        feed_version = job.get("feed_version") or "—"
        transform_version = job.get("transform_version") or "—"
        with st.container():
            header_col, action_col = st.columns([3, 1])
            with header_col:
                st.markdown(f"**{name}**")
                st.caption(f"Feed: {feed_label} v{feed_version} • Transform v{transform_version}")
            with action_col:
                disabled = job_id is None
                if st.button("Run now", key=f"run_job_{job_id}", disabled=disabled):
                    result = _run_job_now(int(job_id)) if job_id is not None else None
                    if result:
                        status = str(result.get("run", {}).get("status", "unknown"))
                        icon = "✅" if status == "success" else "⚠️"
                        st.toast(f"{name} run {status}", icon=icon)
                        st.session_state["dawn_jobs_refresh_token"] = time.time()
                        st.rerun()

            last_run = job.get("last_run") or {}
            metrics_cols = st.columns(4)
            metrics_cols[0].metric("Last status", last_run.get("status", "—"))
            metrics_cols[1].metric("Rows in", last_run.get("rows_in", "—"))
            metrics_cols[2].metric("Rows out", last_run.get("rows_out", "—"))
            metrics_cols[3].metric("Finished", last_run.get("finished_at", "—"))

            warnings = last_run.get("warnings") or []
            if warnings:
                st.caption("Warnings")
                for warning in warnings:
                    st.code(str(warning))
            st.divider()


def _build_rag_diagnostics(
    recent_uploads: Iterable[dict[str, Any]], ping: dict[str, Any]
) -> dict[str, Any]:
    uploads = list(recent_uploads or [])
    indexed_files = len(uploads)
    chunks = int(st.session_state.get("dawn_total_chunks_indexed", 0))
    redis_ready = bool(ping.get("index_ready"))
    redis_size_label = "Index ready" if redis_ready else "Index not built"
    provider = _current_provider()
    llm_config = _current_llm_config()
    llm_connected = provider != "stub" and (
        provider not in {"openai", "anthropic"}
        or bool(
            os.getenv("OPENAI_API_KEY") if provider == "openai" else os.getenv("ANTHROPIC_API_KEY")
        )
    )
    if provider == "ollama":
        llm_model = llm_config.get("ollama_model", "llama3")
        llm_endpoint = "http://127.0.0.1:11434"
    elif provider == "lmstudio":
        llm_model = llm_config.get("lmstudio_model", "mistral-7b-instruct-v0.3")
        llm_endpoint = llm_config.get("lmstudio_base", "http://127.0.0.1:1234")
    elif provider == "openai":
        llm_model = llm_config.get("openai_model", "gpt-4o-mini")
        llm_endpoint = "https://api.openai.com/v1"
    elif provider == "anthropic":
        llm_model = llm_config.get("anthropic_model", "claude-3-sonnet-20240229")
        llm_endpoint = "https://api.anthropic.com"
    else:
        llm_model = "stub"
        llm_endpoint = "—"
    return {
        "files": indexed_files,
        "chunks": chunks,
        "redis_size": redis_size_label,
        "redis_size_human": redis_size_label,
        "dimensions": 384,
        "llm_connected": llm_connected,
        "llm_model": llm_model,
        "llm_endpoint": llm_endpoint,
        "redis_namespace": "dawn:rag:doc",
        "redis_index": "dawn:rag:index",
        "updated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    }


def _handle_preview(uploaded_file: Any, sheet_name: str) -> None:
    if uploaded_file is None:
        st.warning("Drop an Excel file before generating a preview.")
        return
    params: dict[str, str] = {}
    if sheet_name and sheet_name.strip():
        params["sheet"] = sheet_name.strip()
    file_bytes = uploaded_file.getvalue()
    files = {
        "file": (
            uploaded_file.name,
            file_bytes,
            uploaded_file.type or "application/octet-stream",
        )
    }
    try:
        with st.spinner("Profiling spreadsheet…"):
            resp = requests.post(
                f"{API_BASE}/ingest/preview", files=files, params=params, timeout=45
            )
            resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Preview failed: {exc}")
        return

    st.session_state["dawn_preview_data"] = data
    st.session_state["dawn_preview_summary"] = None
    st.session_state["dawn_preview_upload"] = {
        "name": uploaded_file.name,
        "bytes": file_bytes,
        "content_type": uploaded_file.type or "application/octet-stream",
        "sheet": data.get("sheet"),
        "sha16": data.get("sha16"),
    }
    st.session_state["dawn_last_index_result"] = None
    st.session_state["dawn_preview_chart"] = None
    st.session_state["dawn_current_sha"] = data.get("sha16")
    sheet_names = data.get("sheet_names") or []
    if sheet_names:
        st.session_state["dawn_sheet_names"] = sheet_names
        st.session_state["dawn_selected_sheet"] = data.get("sheet") or sheet_names[0]
    st.toast(f"Preview ready for {uploaded_file.name}", icon="📊")


def _handle_index() -> None:
    payload = st.session_state.get("dawn_preview_upload")
    if not payload:
        st.warning("Upload the source file before indexing.")
        return
    files = {
        "file": (
            payload["name"],
            payload["bytes"],
            payload.get("content_type", "application/octet-stream"),
        )
    }
    params: dict[str, str] = {}
    sheet = payload.get("sheet")
    if sheet:
        params["sheet"] = str(sheet)
    params["chunk_max_chars"] = str(st.session_state.get("dawn_chunk_max_chars", 600))
    params["chunk_overlap"] = str(st.session_state.get("dawn_chunk_overlap", 80))
    try:
        with st.spinner("Indexing chunks into Redis…"):
            resp = requests.post(
                f"{API_BASE}/rag/index_excel", params=params, files=files, timeout=90
            )
            resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Indexing failed: {exc}")
        return

    indexed_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    st.session_state["dawn_last_index_result"] = {**data, "indexed_at": indexed_at}
    st.session_state["dawn_preview_summary"] = data.get("summary")
    st.session_state["dawn_total_chunks_indexed"] = int(
        st.session_state.get("dawn_total_chunks_indexed", 0)
    ) + data.get("indexed_chunks", 0)
    _update_suggestions(data.get("summary"))
    _update_preview_chart(data.get("summary"))
    st.session_state["dawn_current_sha"] = data.get("sha16")
    if data.get("sheet"):
        st.session_state["dawn_selected_sheet"] = data.get("sheet")
    st.toast("Excel indexed successfully.", icon="✅")


def _handle_replay(entry: dict[str, Any]) -> None:
    params: dict[str, str] = {"sha16": str(entry.get("sha16", ""))}
    sheet = entry.get("sheet")
    if sheet:
        params["sheet"] = str(sheet)
    try:
        with st.spinner("Loading cached preview…"):
            resp = requests.get(f"{API_BASE}/ingest/preview_cached", params=params, timeout=10)
            resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load cached preview: {exc}")
        return

    st.session_state["dawn_preview_data"] = data
    st.session_state["dawn_preview_summary"] = None
    st.session_state["dawn_preview_upload"] = None  # cached previews lack source bytes
    st.session_state["dawn_last_index_result"] = None
    st.session_state["dawn_preview_chart"] = None
    st.toast(f"Replayed cached preview for {entry['filename']}", icon="📂")


def _handle_query(prompt: str, *, reason: str = "ask") -> None:
    try:
        with st.spinner("Consulting DAWN…"):
            params = {
                "q": prompt,
                "k": str(int(st.session_state.get("dawn_rag_top_k", 6))),
            }
            resp = requests.get(
                f"{API_BASE}/rag/answer",
                params=params,
                timeout=60,
            )
            resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Query failed: {exc}")
        return

    answer_text = data.get("answer", "")
    timestamp = _timestamp()
    st.session_state["dawn_current_answer"] = {
        "text": answer_text,
        "timestamp": timestamp,
        "prompt": prompt,
    }
    sources = data.get("sources") or []
    chunks = [
        {
            "source": src.get("source", "Unknown"),
            "text": src.get("text", ""),
            "score": _format_score(src.get("score")),
        }
        for src in sources
    ]
    st.session_state["dawn_context_chunks"] = chunks
    history = st.session_state.get("dawn_query_history", [])
    history.insert(0, {"question": prompt, "timestamp": timestamp})
    st.session_state["dawn_query_history"] = history[:8]
    st.session_state["dawn_last_prompt"] = prompt
    toast_msg = "Answer refreshed." if reason == "regenerate" else "Answer ready ✨"
    st.toast(toast_msg, icon="💡")


def _update_suggestions(summary: dict[str, Any] | None) -> None:
    if not summary:
        st.session_state["dawn_suggested_questions"] = []
        return
    suggestions: list[str] = []
    for metric in summary.get("metrics", []):
        if metric.get("type") == "value_counts" and metric.get("values"):
            column = metric.get("column", "column")
            suggestions.append(f"Which {column} has the highest frequency?")
    if not suggestions:
        for column in summary.get("columns", [])[:3]:
            suggestions.append(f"Give me a summary for {column.get('name')}.")
    st.session_state["dawn_suggested_questions"] = suggestions[:3]


def _update_preview_chart(summary: dict[str, Any] | None) -> None:
    if not summary:
        st.session_state["dawn_preview_chart"] = None
        return
    metrics = summary.get("metrics") or []
    for metric in metrics:
        if metric.get("type") == "value_counts" and metric.get("values"):
            values = metric.get("values", [])[:10]
            st.session_state["dawn_preview_chart"] = {
                "column": metric.get("column") or metric.get("description") or "Values",
                "values": [
                    {"label": str(entry.get("label", "")), "count": int(entry.get("count", 0))}
                    for entry in values
                ],
            }
            return
    st.session_state["dawn_preview_chart"] = None


def _current_context_source() -> str | None:
    last_index = st.session_state.get("dawn_last_index_result") or {}
    source = last_index.get("source")
    sheet = last_index.get("sheet")
    if source and sheet:
        return f"{source}:{sheet}"
    preview_upload = st.session_state.get("dawn_preview_upload") or {}
    preview_data = st.session_state.get("dawn_preview_data") or {}
    sheet = preview_data.get("sheet")
    name = preview_upload.get("name")
    if name and sheet:
        return f"{name}:{sheet}"
    return None


def _fetch_context_chunks(source: str | None) -> list[dict[str, Any]]:
    if not source:
        return []
    try:
        resp = requests.get(
            f"{API_BASE}/rag/context",
            params={"source": source, "limit": str(300)},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001
        return []
    if isinstance(data, dict):
        chunks = data.get("chunks")
        if isinstance(chunks, list):
            return chunks
    return []


def _fetch_memory_snapshot(sha16: str, sheet: str) -> dict[str, Any]:
    try:
        resp = requests.get(
            f"{API_BASE}/rag/memory",
            params={"sha16": sha16, "sheet": sheet},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to load context metadata: {exc}")
        return {}


def _update_memory_snapshot(
    sha16: str,
    sheet: str,
    *,
    relationships: dict[str, str] | None = None,
    plan: list[dict[str, Any]] | None = None,
) -> bool:
    payload: dict[str, Any] = {"sha16": sha16, "sheet": sheet}
    if relationships is not None:
        payload["relationships"] = relationships
    if plan is not None:
        payload["plan"] = plan
    try:
        resp = requests.put(f"{API_BASE}/rag/memory", json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to update context metadata: {exc}")
        return False


def _update_context_chunk(chunk_id: str, text: str) -> bool:
    payload = {"text": text.strip()}
    if not payload["text"]:
        st.warning("Context cannot be saved empty.")
        return False
    try:
        resp = requests.put(
            f"{API_BASE}/rag/context/{chunk_id}",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to update context chunk: {exc}")
        return False
    st.toast("Context chunk updated.", icon="🛠️")
    return True


def _add_context_note(text: str, *, source: str | None = None) -> bool:
    target = source or _current_context_source()
    if not target:
        st.warning("Index a dataset before adding context notes.")
        return False
    payload = {"source": target, "text": text.strip()}
    if not payload["text"]:
        st.warning("Write a note before saving it to context.")
        return False
    try:
        resp = requests.post(
            f"{API_BASE}/rag/context/note",
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to add context note: {exc}")
        return False
    st.toast("Context note added.", icon="📝")
    st.session_state["dawn_context_editor_refresh_token"] = time.time()
    return True


def _process_context_events(events: dict[str, Any]) -> None:
    if not events:
        return
    if events.get("refresh"):
        st.session_state["dawn_context_editor_refresh_token"] = time.time()
        st.rerun()
    updated = events.get("update")
    if (
        updated
        and updated.get("id") is not None
        and _update_context_chunk(updated["id"], updated.get("text", ""))
    ):
        st.session_state["dawn_context_editor_refresh_token"] = time.time()
        st.rerun()
    note_text = events.get("note")
    if note_text and _add_context_note(note_text):
        st.rerun()


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _format_score(val: Any) -> str:
    try:
        return f"{float(val):.3f}"
    except Exception:
        return str(val) if val is not None else "—"


def _process_upload_events(event: dict[str, Any]) -> None:
    if event.get("preview_requested"):
        _handle_preview(event.get("uploaded_file"), event.get("sheet_name", ""))
    if event.get("index_requested"):
        _handle_index()


def _process_query_events(events: dict[str, Any]) -> None:
    if events.get("submitted"):
        prompt = events.get("prompt") or ""
        if not prompt.strip():
            st.warning("Type a question before sending.")
        elif events.get("as_note"):
            if _add_context_note(prompt.strip()):
                st.session_state["dawn_query_reset"] = True
        else:
            _handle_query(prompt.strip())
            st.session_state["dawn_query_reset"] = True
    elif events.get("regenerate"):
        prompt = st.session_state.get("dawn_last_prompt")
        if prompt:
            _handle_query(prompt, reason="regenerate")
        else:
            st.info("Ask something first to regenerate an answer.")

    if events.get("copy_answer"):
        answer = st.session_state.get("dawn_current_answer")
        if answer and answer.get("text"):
            st.toast("Answer copied — use the copy icon or ⌘/Ctrl+C.", icon="📋")
        else:
            st.info("No answer available to copy yet.")


def main() -> None:
    _init_session_state()
    _inject_base_styles()
    _maybe_show_splash()

    statuses = _service_statuses()
    render_header(statuses, logo_path=_logo_path_or_none())

    if st.session_state.get("dawn_llm_restart_required"):
        st.warning(
            "Provider changed. Please restart the DAWN app (./start_dawn.sh) so the new LLM service starts.",
            icon="🔄",
        )

    recent_uploads = _fetch_recent_uploads()
    rag_ping = _fetch_rag_ping()
    diagnostics = _build_rag_diagnostics(recent_uploads, rag_ping)
    sidebar_overview = {
        "files": diagnostics.get("files"),
        "chunks": diagnostics.get("chunks"),
        "dimensions": diagnostics.get("dimensions"),
        "redis_size": diagnostics.get("redis_size"),
    }
    chunk_config_current = {
        "chunk_max_chars": st.session_state.get("dawn_chunk_max_chars", 600),
        "chunk_overlap": st.session_state.get("dawn_chunk_overlap", 80),
        "top_k": st.session_state.get("dawn_rag_top_k", 6),
    }

    sidebar_events = render_sidebar(
        recent_uploads=recent_uploads,
        suggested_questions=st.session_state.get("dawn_suggested_questions"),
        rag_overview=sidebar_overview,
        llm_state=_current_llm_config(),
        chunk_config=chunk_config_current,
    )
    replay_request = sidebar_events.get("replay_request")
    if replay_request:
        _handle_replay(replay_request)
    if sidebar_events.get("llm_payload"):
        _apply_llm_settings(sidebar_events["llm_payload"])
    if sidebar_events.get("delete_request"):
        _delete_cached_preview(sidebar_events["delete_request"])
    if sidebar_events.get("clear_cache"):
        _clear_cached_previews()
    chunk_settings = sidebar_events.get("chunk_settings") or {}
    if chunk_settings:
        new_max = int(chunk_settings.get("chunk_max_chars", 600))
        new_overlap = int(chunk_settings.get("chunk_overlap", 80))
        new_overlap = max(0, min(new_overlap, new_max - 10))
        st.session_state["dawn_chunk_max_chars"] = new_max
        st.session_state["dawn_chunk_overlap"] = new_overlap
        st.session_state["dawn_rag_top_k"] = int(chunk_settings.get("top_k", 6))

    query_events = {
        "prompt": "",
        "submitted": False,
        "as_note": False,
        "regenerate": False,
        "copy_answer": False,
    }

    mode_options = ["Quick Insight", "Datafeed Studio", "Context"]
    current_mode = st.session_state.get("workspace_mode", mode_options[0])
    mode = st.radio(
        "Pick a workspace",
        mode_options,
        index=mode_options.index(current_mode) if current_mode in mode_options else 0,
        horizontal=True,
    )
    st.session_state["workspace_mode"] = mode

    if mode == "Quick Insight":
        seed = st.session_state.pop("quick_insight_seed", None)
        if seed:
            if isinstance(seed, dict) and seed.get("kind") == "feed_version":
                payload = {
                    "identifier": seed.get("identifier"),
                    "name": seed.get("name"),
                    "favorite_sheet": (seed.get("summary") or {}).get("sheet"),
                    "latest_version": {
                        "number": (seed.get("version") or {}).get("number"),
                        "rows": (seed.get("summary") or {}).get("row_count"),
                        "columns": (seed.get("summary") or {}).get("column_count"),
                        "sha16": (seed.get("version") or {}).get("sha16"),
                        "summary": seed.get("summary"),
                        "profile": seed.get("profile"),
                        "schema": seed.get("schema"),
                        "sheet": (seed.get("summary") or {}).get("sheet"),
                        "sheet_names": (seed.get("summary") or {}).get("sheet_names"),
                    },
                }
                _apply_feed_to_quick_insight(payload)
            else:
                _handle_replay(seed)

        quick_main, quick_chat = st.columns([3.7, 1.3], gap="large", vertical_alignment="top")

        with quick_main:
            upload_events = render_upload_area(
                preview_data=st.session_state.get("dawn_preview_data"),
                preview_summary=st.session_state.get("dawn_preview_summary"),
                index_result=st.session_state.get("dawn_last_index_result"),
                suggested_questions=st.session_state.get("dawn_suggested_questions"),
                preview_chart=st.session_state.get("dawn_preview_chart"),
                can_index=st.session_state.get("dawn_preview_upload") is not None,
                chunk_config={
                    "max_chars": st.session_state.get("dawn_chunk_max_chars", 600),
                    "overlap": st.session_state.get("dawn_chunk_overlap", 80),
                },
            )
            _process_upload_events(upload_events)

            if st.session_state.get("dawn_preview_upload") and st.button(
                "Promote this file to Datafeed Studio", key="promote_to_feed"
            ):
                st.session_state["feed_wizard_prefill"] = st.session_state.get(
                    "dawn_preview_upload"
                )
                st.session_state["workspace_mode"] = "Datafeed Studio"
                st.rerun()
            st.divider()
            render_rag_diagnostics(diagnostics=diagnostics)

            preview_rows = st.session_state.get("dawn_preview_data", {}).get("rows")
            if isinstance(preview_rows, list) and preview_rows:
                preview_df = pd.DataFrame(preview_rows)
                if not preview_df.empty:
                    render_nl_filter_lab({"current_preview": preview_df}, key_prefix="workspace")

        with quick_chat:
            chat_open = st.session_state.get("dawn_chat_open", True)
            toggle_label = "Hide Chat" if chat_open else "Show Chat"
            st.markdown('<div class="dawn-chat-toggle-wrap">', unsafe_allow_html=True)
            if st.button(toggle_label, key="dawn_chat_toggle"):
                chat_open = not chat_open
                st.session_state["dawn_chat_open"] = chat_open
            st.markdown("</div>", unsafe_allow_html=True)

            if chat_open:
                with styled_block("dawn-chat-panel"):
                    if st.session_state.pop("dawn_query_reset", False):
                        st.session_state["dawn_query_draft"] = ""
                    query_events = render_query_workspace(
                        history=st.session_state.get("dawn_query_history"),
                        current_answer=st.session_state.get("dawn_current_answer"),
                        context_chunks=st.session_state.get("dawn_context_chunks"),
                    )
            else:
                st.caption("Chat panel hidden. Use the toggle above to reopen.")

    elif mode == "Datafeed Studio":
        st.session_state.pop("quick_insight_seed", None)
        render_feed_wizard(API_BASE)
        st.divider()
        feeds = _fetch_feed_catalog()
        _render_feed_overview(feeds)
        st.divider()
        jobs = _fetch_jobs()
        _render_jobs_panel(jobs)

    else:  # Context
        st.session_state.pop("quick_insight_seed", None)
        st.markdown("### Context Memory")
        st.caption(
            "Curate the knowledge base that Dawn uses when answering questions. Update existing chunks or add clarifying notes whenever the data needs an extra hint."
        )
        context_source = _current_context_source()
        context_entries = _fetch_context_chunks(context_source)
        context_events = render_context_editor(source=context_source, entries=context_entries)
        _process_context_events(context_events)

        current_sha = st.session_state.get("dawn_current_sha")
        current_sheet = st.session_state.get("dawn_selected_sheet")
        if not current_sheet and context_source and ":" in context_source:
            current_sheet = context_source.split(":", 1)[1]

        if current_sha and current_sheet:
            memory_snapshot = _fetch_memory_snapshot(current_sha, current_sheet)

            st.markdown("#### Column roles")
            relationships = memory_snapshot.get("relationships", {}) or {}
            rel_df = pd.DataFrame(
                [{"column": col, "role": role} for col, role in relationships.items()]
            )
            if rel_df.empty:
                rel_df = pd.DataFrame({"column": [], "role": []})
            edited_rel_df = st.data_editor(
                rel_df,
                num_rows="dynamic",
                use_container_width=True,
                key="dawn_relationship_editor",
            )
            if st.button("Save column roles", key="dawn_save_relationships"):
                rel_records = edited_rel_df.to_dict(orient="records")
                cleaned_relationships = {
                    str(row["column"]).strip(): str(row["role"]).strip()
                    for row in rel_records
                    if row.get("column") and row.get("role")
                }
                if _update_memory_snapshot(
                    current_sha,
                    current_sheet,
                    relationships=cleaned_relationships,
                ):
                    st.success("Column roles saved.")
                    st.rerun()

            st.markdown("#### Analysis plan")
            plan = memory_snapshot.get("analysis_plan") or []
            if plan:
                plan_df = pd.DataFrame(plan)
            else:
                st.info("No analysis plan defined yet. Add or edit rows below to guide Dawn.")
                plan_df = pd.DataFrame(
                    [{"type": "", "column": "", "group": "", "value": "", "stat": ""}]
                )
            edited_plan_df = st.data_editor(
                plan_df,
                num_rows="dynamic",
                use_container_width=True,
                key="dawn_plan_editor",
            )
            if st.button("Save plan", key="dawn_save_plan"):
                plan_records = [
                    {k: v for k, v in row.items() if v not in (None, "")}
                    for row in edited_plan_df.to_dict(orient="records")
                    if any(row.values())
                ]
                if _update_memory_snapshot(current_sha, current_sheet, plan=plan_records):
                    st.success("Analysis plan saved.")
                    st.rerun()

            insights = memory_snapshot.get("insights") or {}
            if insights:
                st.markdown("#### Insight snapshots")
                st.json(insights)

            aggregates = memory_snapshot.get("aggregates") or []
            if aggregates:
                st.markdown("#### Aggregate highlights")
                agg_df = pd.DataFrame(aggregates)
                st.dataframe(agg_df, use_container_width=True)
        else:
            st.info("Preview or index a worksheet to curate metadata.")

    _process_query_events(query_events)


if __name__ == "__main__":
    main()
