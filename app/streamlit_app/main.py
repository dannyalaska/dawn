import os
from typing import Any

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")

st.set_page_config(page_title="DAWN (dev)", layout="wide")
st.title("DAWN — dev")
st.caption("Streamlit is up. Next: API, Redis, and real features.")

# Backend health
st.subheader("Backend status")
try:
    api = "http://127.0.0.1:8000"
    r1 = requests.get(f"{api}/health", timeout=2).json()
    r2 = requests.get(f"{api}/health/redis", timeout=2).json()
    st.json({"health": r1, "redis": r2})
except Exception as e:
    st.warning(f"API not reachable: {e}")

st.divider()
st.subheader("Excel preview")

api = "http://127.0.0.1:8000"
up = st.file_uploader("Upload an Excel file (.xlsx, .xlsm, .xls)", type=["xlsx", "xlsm", "xls"])
sheet_name = st.text_input("Sheet name (optional)", value="")


def render_index_result(payload: dict[str, Any]) -> None:
    st.success(
        f"Indexed {payload.get('indexed_chunks', 0)} chunks "
        f"from `{payload.get('source')}` sheet `{payload.get('sheet')}`."
    )
    summary = payload.get("summary") or {}
    if summary.get("text"):
        st.markdown("**Dataset summary**")
        st.write(summary["text"])
    columns = summary.get("columns") or []
    if columns:
        import pandas as _pd

        rows = []
        for col in columns:
            rows.append(
                {
                    "column": col["name"],
                    "dtype": col["dtype"],
                    "top_values": ", ".join(
                        f"{name} ({count})" for name, count in (col.get("top_values") or [])
                    ),
                    "stats": col.get("stats"),
                }
            )
        _df = _pd.DataFrame(rows)
        st.dataframe(_df, use_container_width=True)

    metrics = summary.get("metrics") or []
    if metrics:
        import pandas as _pd

        st.markdown("**Key metrics**")
        metric_rows = []
        for metric in metrics:
            values = ", ".join(
                f"{entry['label']} ({entry['count']})" for entry in metric.get("values", [])
            )
            metric_rows.append(
                {
                    "metric": metric.get("description") or metric.get("column"),
                    "details": values,
                }
            )
        st.dataframe(_pd.DataFrame(metric_rows), use_container_width=True)

    st.session_state["latest_summary"] = summary
    st.session_state["latest_metrics"] = metrics

    suggestions: list[str] = []
    for metric in metrics:
        if metric.get("type") == "value_counts" and metric.get("values"):
            column = metric.get("column", "column")
            suggestions.append(f"Which {column} has the most records?")
    st.session_state["suggested_questions"] = suggestions[:3]


if up and st.button("Generate preview"):
    file_bytes = up.getvalue()
    files = {
        "file": (
            up.name,
            file_bytes,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    params = {}
    if sheet_name.strip():
        params["sheet"] = sheet_name.strip()
    try:
        r = requests.post(f"{api}/ingest/preview", files=files, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        st.write(f"Sheet: **{data['sheet']}** — Shape: `{data['shape']}`")
        with st.expander("Columns profile", expanded=False):
            st.json(data["columns"])
        st.write("Rows (first 50):")
        st.dataframe(data["rows"])
        st.session_state["last_preview_upload"] = {
            "name": up.name,
            "bytes": file_bytes,
            "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "sheet": data["sheet"],
        }
        st.session_state["last_preview_meta"] = data
    except Exception as exc:
        st.error(f"Preview failed: {exc}")


if "last_preview_upload" in st.session_state:
    meta = st.session_state.get("last_preview_meta", {})
    st.info(
        f"Latest preview ready to index: **{st.session_state['last_preview_upload']['name']}** "
        f"(sheet `{meta.get('sheet', st.session_state['last_preview_upload'].get('sheet', 'Sheet1'))}`)"
    )
    if st.button("Index this preview into Redis", key="index_latest_preview"):
        payload = st.session_state["last_preview_upload"]
        files = {
            "file": (
                payload["name"],
                payload["bytes"],
                payload.get("content_type", "application/octet-stream"),
            )
        }
        params = {}
        sheet_used = payload.get("sheet")
        if sheet_used:
            params["sheet"] = sheet_used
        resp = requests.post(f"{API_BASE}/rag/index_excel", params=params, files=files, timeout=60)
        if resp.ok:
            render_index_result(resp.json())
        else:
            st.error(resp.text)


# Sidebar: recent uploads
with st.sidebar:
    st.header("Recent uploads")
    api_base = "http://127.0.0.1:8000"
    try:
        rec = requests.get(f"{api_base}/ingest/recent", timeout=5).json()
        if not rec:
            st.caption("No uploads yet.")
        else:
            # show compact table
            import pandas as _pd

            _df = _pd.DataFrame(rec)[["filename", "sheet", "rows", "cols", "uploaded_at", "sha16"]]
            st.dataframe(_df, use_container_width=True, height=240)
            pick = st.selectbox(
                "Replay a cached preview (by filename)",
                options=[f"{r['filename']} | {r['sheet'] or ''} | {r['sha16']}" for r in rec],
                index=0,
            )
            if st.button("Replay cached preview"):
                # parse selection to get sha16 + sheet
                sel = next(
                    r for r in rec if f"{r['filename']} | {r['sheet'] or ''} | {r['sha16']}" == pick
                )
                resp = requests.get(
                    f"{api_base}/ingest/preview_cached",
                    params={"sha16": sel["sha16"], "sheet": sel["sheet"]},
                    timeout=10,
                )
                if resp.ok:
                    st.session_state["replayed"] = resp.json()
                else:
                    st.session_state.pop("replayed", None)
                    if resp.status_code == 404:
                        st.warning(
                            "Cached preview expired. Re-upload the file to regenerate a preview."
                        )
                    else:
                        st.error(f"Failed to load cached preview: {resp.text}")
    except Exception as _e:
        st.warning(f"Sidebar failed: {_e}")

# If we replayed, render under the main preview area
if "replayed" in st.session_state:
    st.divider()
    st.subheader("Replayed (from cache)")
    jj = st.session_state["replayed"]
    st.write(f"Sheet: **{jj['name']}** — Shape: `{tuple(jj['shape'])}`")
    with st.expander("Columns profile", expanded=False):
        st.json(jj["columns"])
    st.dataframe(jj["rows"])


st.divider()

st.header("RAG (Redis search)")

with st.expander("Index an Excel into the RAG store (manual upload)", expanded=False):
    rag_file = st.file_uploader("Excel file", type=["xlsx", "xlsm", "xls"], key="rag_upl")
    rag_sheet = st.text_input("Sheet name (optional)", value="", key="rag_sheet_name")
    if rag_file and st.button("Index to Redis", key="rag_manual_index"):
        files = {
            "file": (
                rag_file.name,
                rag_file.getvalue(),
                rag_file.type or "application/octet-stream",
            )
        }
        params = {}
        if rag_sheet.strip():
            params["sheet"] = rag_sheet.strip()
        resp = requests.post(f"{API_BASE}/rag/index_excel", params=params, files=files, timeout=60)
        if resp.ok:
            render_index_result(resp.json())
        else:
            st.error(resp.text)

st.subheader("Ask your data")

chat_history: list[dict[str, Any]] = st.session_state.setdefault("chat_history", [])
if chat_history:
    chat_container = st.container()
    for idx, message in enumerate(chat_history, start=1):
        speaker = "You" if message["role"] == "user" else "DAWN"
        with chat_container.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and message.get("sources"):
                with st.expander(f"Sources for response {idx}", expanded=False):
                    for i, src in enumerate(message["sources"], 1):
                        row_label = (
                            "summary" if int(src.get("row_index", 0)) < 0 else src.get("row_index")
                        )
                        st.write(
                            f"[{i}] {src.get('source')} row={row_label} score={src.get('score', 0):.4f}"
                        )
                        st.markdown(f"> {src.get('text', '')}")

suggestions = st.session_state.get("suggested_questions", [])
st.session_state.setdefault("chat_draft", "")
if suggestions:
    st.caption("Quick questions")
    cols = st.columns(len(suggestions))
    for idx, (col, suggestion) in enumerate(zip(cols, suggestions, strict=False)):
        if col.button(suggestion, key=f"suggestion_{idx}"):
            st.session_state["chat_draft"] = suggestion
            st.session_state.pop("chat_text_area", None)
            st.rerun()
top_k = st.slider("Context chunks to retrieve", min_value=5, max_value=40, value=12, step=1)

with st.form("chat_form"):
    user_question = st.text_area(
        "Question",
        value=st.session_state.get("chat_text_area", st.session_state.get("chat_draft", "")),
        placeholder="Ask about the indexed dataset…",
        key="chat_text_area",
    )
    submitted = st.form_submit_button("Send")

if submitted:
    if not user_question.strip():
        st.warning("Enter a question first.")
    else:
        payload = {
            "messages": [{"role": msg["role"], "content": msg["content"]} for msg in chat_history]
            + [{"role": "user", "content": user_question}],
            "k": top_k,
        }
        try:
            rr = requests.post(f"{API_BASE}/rag/chat", json=payload, timeout=90)
            rr.raise_for_status()
            data = rr.json()
            enriched_history = data["messages"]
            if data.get("sources"):
                enriched_history[-1]["sources"] = data["sources"]
            st.session_state["chat_history"] = enriched_history
            st.session_state["chat_draft"] = ""
            st.session_state.pop("chat_text_area", None)
            st.rerun()
        except Exception as exc:
            st.error(f"Chat failed: {exc}")

if st.button("Reset conversation"):
    st.session_state["chat_history"] = []
    st.session_state["chat_draft"] = ""
    st.session_state.pop("chat_text_area", None)
    st.rerun()
