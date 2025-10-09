from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd
import streamlit as st

from .ui import styled_block


def render_upload_area(
    *,
    preview_data: Mapping[str, Any] | None,
    preview_summary: Mapping[str, Any] | None,
    index_result: Mapping[str, Any] | None,
    suggested_questions: Iterable[str] | None,
    preview_chart: Mapping[str, Any] | None,
    can_index: bool = True,
    chunk_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Render the upload + ingest workspace and return triggered actions."""
    st.markdown(_upload_styles(), unsafe_allow_html=True)
    st.markdown('<h3 class="dawn-section-title">📄 Upload & Ingest</h3>', unsafe_allow_html=True)
    st.caption("Send spreadsheets into the DAWN engine. We will profile the data before indexing.")

    left, right = st.columns([3, 2], vertical_alignment="top")

    sheet_options = [str(opt) for opt in st.session_state.get("dawn_sheet_names", [])]
    selected_sheet_default = st.session_state.get("dawn_selected_sheet", "")

    preview_requested = False
    sheet_name_value = selected_sheet_default
    uploaded_file = None
    preview_form = left.form("dawn_preview_form", clear_on_submit=False)
    with preview_form:
        uploaded_file = st.file_uploader(
            "Drop your Excel file here ☀️",
            type=["xlsx", "xlsm", "xls"],
        )
        st.caption("Limit 200MB per file • .xlsx, .xlsm, .xls")
        if sheet_options:
            try:
                default_index = sheet_options.index(selected_sheet_default)
            except ValueError:
                default_index = 0
            sheet_name_value = st.selectbox(
                "Worksheet",
                options=sheet_options,
                index=default_index if sheet_options else 0,
                key="dawn_sheet_select",
            )
        else:
            sheet_name_value = st.text_input(
                "Sheet name (optional)", placeholder="Defaults to the first sheet"
            )
        preview_requested = st.form_submit_button("Generate preview", use_container_width=True)
        if sheet_name_value:
            st.session_state["dawn_selected_sheet"] = sheet_name_value.strip()

    index_requested = False

    with right, styled_block("dawn-inspector-card"):
        st.markdown("### Preview inspector")
        if chunk_config:
            st.caption(
                f"Chunk size: {chunk_config.get('max_chars', 600)} chars • Overlap: {chunk_config.get('overlap', 80)}"
            )
        if preview_data:
            shape = preview_data.get("shape") or ("—", "—")
            index_form = st.form("dawn_index_form", clear_on_submit=False)
            with index_form:
                st.metric("Sheet", preview_data.get("sheet", "—"))
                st.metric("Shape", f"{shape[0]} × {shape[1]}")
                st.metric("Columns profiled", len(preview_data.get("columns") or []))
                index_requested = st.form_submit_button(
                    "Index this preview",
                    use_container_width=True,
                    disabled=not can_index,
                )
            if not can_index:
                st.caption("Upload the source file again to send it into Redis.")
            if suggested_questions:
                st.divider()
                st.caption("Suggested questions")
                for question in suggested_questions:
                    st.markdown(f"- {question}")
        else:
            st.caption("No preview yet. Upload a file to see schema and headlines.")
        if index_result:
            st.divider()
            st.success(
                f"Indexed {index_result.get('indexed_chunks', 0)} chunks "
                f"from `{index_result.get('sheet')}`.",
                icon="✅",
            )
            st.caption(
                f"Source: {index_result.get('source')} • {index_result.get('indexed_at', '')}"
            )

    if preview_summary:
        st.divider()
        with st.expander("Dataset overview", expanded=True):
            text = preview_summary.get("text")
            if text:
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if lines:
                    st.caption(lines[0])
            metrics = preview_summary.get("metrics") or []
            if metrics:
                st.markdown("**Key metrics**")
                for metric in metrics:
                    label = metric.get("description") or metric.get("column", "Metric")
                    df_metric = pd.DataFrame(metric.get("values", []))
                    if not df_metric.empty:
                        df_metric.columns = ["Value", "Count"]
                        st.markdown(f"_{label}_")
                        st.table(df_metric)
            columns = preview_summary.get("columns") or []
            if columns:
                st.markdown("**Column insights**")
                with st.expander("Columns breakdown", expanded=False):
                    columns_df = _columns_dataframe(columns)
                    st.dataframe(columns_df, width="stretch")
            aggregates = preview_summary.get("aggregates") or []
            if aggregates:
                st.markdown("**Aggregate highlights**")
                for agg in aggregates:
                    group = agg.get("group")
                    value = agg.get("value")
                    stat = agg.get("stat")
                    best_entries = agg.get("best") or []
                    worst_entries = agg.get("worst") or []
                    if best_entries:
                        best_text = ", ".join(
                            f"{entry['label']}: {entry['value']:.2f}" for entry in best_entries
                        )
                        st.markdown(f"- Fastest {group} for {value} ({stat}): {best_text}")
                    if worst_entries:
                        worst_text = ", ".join(
                            f"{entry['label']}: {entry['value']:.2f}" for entry in worst_entries
                        )
                        st.markdown(f"- Slowest {group} for {value} ({stat}): {worst_text}")
    if preview_data and preview_data.get("rows") is not None:
        st.divider()
        with st.expander("Sample rows", expanded=False):
            st.dataframe(preview_data["rows"], width="stretch", hide_index=True)
    if preview_chart and preview_chart.get("values"):
        st.divider()
        chart_title = preview_chart.get("column", "Metric")
        with st.expander(f"Top values · {chart_title}", expanded=False):
            chart_df = pd.DataFrame(preview_chart.get("values")).astype({"count": int})
            chart_df = chart_df.set_index("label")
            st.bar_chart(chart_df["count"])

    sheet_value_out = sheet_name_value.strip() if isinstance(sheet_name_value, str) else ""

    return {
        "uploaded_file": uploaded_file,
        "sheet_name": sheet_value_out,
        "preview_requested": preview_requested,
        "index_requested": index_requested,
    }


def _columns_dataframe(columns: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(columns)
    if "top_values" in df.columns:
        df["top_values"] = df["top_values"].apply(_format_top_values)
    return df


def _format_top_values(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        pairs = list(value)
    except Exception:  # noqa: BLE001
        return str(value)
    formatted = []
    for pair in pairs:
        if isinstance(pair, list | tuple) and len(pair) == 2:
            formatted.append(f"{pair[0]} ({pair[1]})")
        else:
            formatted.append(str(pair))
    return "; ".join(formatted)


def _upload_styles() -> str:
    return """
    <style>
        .dawn-section-title {
            margin-bottom: 0;
            letter-spacing: 0.08em;
            font-weight: 700;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
            background: linear-gradient(90deg, #ffb347, #ff7e5f 45%, #8a63ff 90%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        div[data-testid="stFileUploader"] {
            width: 100%;
            margin-bottom: 0.75rem;
        }
        div[data-testid="stFileUploader"] > label {
            font-size: 1.05rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            color: rgba(242, 244, 255, 0.88);
            margin-bottom: 0.6rem;
        }
        div[data-testid="stFileUploaderDropzone"] {
            position: relative;
            border-radius: 22px;
            border: 1px dashed rgba(255, 142, 108, 0.5);
            background: rgba(23, 27, 43, 0.9);
            padding: 2.4rem 1.8rem;
            overflow: hidden;
            transition: border 0.25s ease, box-shadow 0.25s ease;
        }
        div[data-testid="stFileUploaderDropzone"]::after {
            content: "";
            position: absolute;
            inset: 0;
            border-radius: 22px;
            background:
                radial-gradient(circle at top, rgba(255, 155, 90, 0.32), transparent 62%),
                radial-gradient(circle at 85% 15%, rgba(138, 99, 255, 0.2), transparent 70%);
            opacity: 0.7;
            pointer-events: none;
        }
        div[data-testid="stFileUploaderDropzone"]:hover {
            border-color: rgba(147, 117, 255, 0.65);
            box-shadow: 0 18px 36px rgba(9, 11, 28, 0.55);
        }
        div[data-testid="stFileUploaderDropzone"] > div {
            position: relative;
            z-index: 2;
        }
        div[data-testid="stFileUploaderDropzone"] span {
            color: rgba(233, 235, 250, 0.85);
            font-weight: 500;
            letter-spacing: 0.03em;
            font-family: 'Inter', 'Helvetica Neue', 'Segoe UI', sans-serif;
        }
        div[data-testid="stFileUploaderDropzone"] small {
            color: rgba(214, 216, 236, 0.65);
        }
        div[data-testid="stFileUploaderDropzone"] button {
            border-radius: 12px;
            padding: 0.55rem 1.2rem;
            background: linear-gradient(130deg, rgba(255, 126, 95, 0.5), rgba(137, 101, 255, 0.55));
            border: 1px solid rgba(255, 150, 116, 0.4);
            color: rgba(249, 250, 255, 0.94);
            font-weight: 600;
        }
        div[data-testid="stFileUploaderDropzone"] button:hover {
            border: 1px solid rgba(147, 117, 255, 0.6);
        }
        div[data-testid="stVerticalBlock"]:has(> div.dawn-inspector-card-anchor) {
            border-radius: 22px;
            background: linear-gradient(150deg, rgba(20, 18, 34, 0.92), rgba(27, 23, 45, 0.9));
            padding: 1.5rem 1.7rem;
            border: 1px solid rgba(138, 112, 255, 0.28);
            box-shadow: 0 22px 44px rgba(6, 8, 22, 0.55);
        }
        .dawn-inspector-card-anchor {
            display: none;
        }
        .stTextInput>div>div>input {
            background: rgba(9, 12, 26, 0.95);
            border-radius: 12px;
            border: 1px solid rgba(137, 113, 255, 0.22);
        }
        .stTextInput>div>div>input:focus {
            border-color: rgba(255, 145, 116, 0.75);
        }
        .stFileUploader>div>div {
            background: transparent;
        }
        .stButton>button {
            border-radius: 12px;
            padding: 0.6rem 1.2rem;
            font-weight: 600;
            background: linear-gradient(120deg, rgba(255,126,95,0.38), rgba(138, 99, 255, 0.45));
            border: 1px solid rgba(255, 150, 116, 0.35);
            color: rgba(247, 248, 254, 0.95);
            transition: transform 0.2s ease, box-shadow 0.2s ease, border 0.2s ease;
        }
        .stButton>button:hover {
            transform: translateY(-1px);
            border-color: rgba(147, 117, 255, 0.55);
            box-shadow: 0 16px 34px rgba(126, 101, 255, 0.28);
        }
    </style>
    """
