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
    render_header,
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
        "dawn_preview_data": None,
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


def _add_context_note(text: str) -> bool:
    source = _current_context_source()
    if not source:
        st.warning("Index a dataset before adding context notes.")
        return False
    payload = {"source": source, "text": text.strip()}
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

    col_main_area, col_chat_panel = st.columns([3.7, 1.3], gap="large", vertical_alignment="top")

    with col_main_area:
        workspace_tab, context_tab = st.tabs(["Workspace", "Context"])

        with workspace_tab:
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

            st.divider()
            render_rag_diagnostics(diagnostics=diagnostics)

        with context_tab:
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

    query_events = {
        "prompt": "",
        "submitted": False,
        "as_note": False,
        "regenerate": False,
        "copy_answer": False,
    }
    with col_chat_panel:
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

    _process_query_events(query_events)


if __name__ == "__main__":
    main()
