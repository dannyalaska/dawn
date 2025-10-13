from __future__ import annotations

import io

import pandas as pd
import streamlit as st

try:
    from app.core.nl_filter import apply_nl_filter
except ModuleNotFoundError:  # pragma: no cover
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from app.core.nl_filter import apply_nl_filter


def render_nl_filter_lab(
    dataframes: dict[str, pd.DataFrame] | None,
    *,
    label: str = "Ask a question about this dataset",
    key_prefix: str = "workspace",
) -> None:
    st.markdown(f"#### {label}")
    if not dataframes:
        st.info("Load or preview a dataset to unlock natural-language filtering.")
        return
    dataset_names = [
        name for name, df in dataframes.items() if isinstance(df, pd.DataFrame) and not df.empty
    ]
    if not dataset_names:
        st.warning("No rows available to filter yet.")
        return
    dataset_key = st.selectbox(
        "Pick a dataset",
        dataset_names,
        key=f"{key_prefix}_nl_filter_dataset",
    )
    question = st.text_input(
        "Describe the rows you want",
        placeholder="e.g. transactions where status equals open and amount > 100",
        key=f"{key_prefix}_nl_filter_question",
    )
    run = st.button("Run query", key=f"{key_prefix}_nl_filter_run")
    if not run:
        return
    df = dataframes.get(dataset_key)
    if df is None or df.empty:
        st.error("That dataset has no rows.")
        return
    try:
        filtered = apply_nl_filter(df, question)
    except ValueError as exc:
        st.error(str(exc))
        return
    if filtered.empty:
        st.warning("No rows matched that description.")
        return
    st.success(f"{len(filtered)} rows found.")
    st.dataframe(filtered, use_container_width=True)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv_bytes,
        file_name=f"{dataset_key}_filtered.csv",
        mime="text/csv",
        key=f"{key_prefix}_nl_filter_csv",
    )

    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        filtered.to_excel(writer, index=False, sheet_name="Filtered")
    st.download_button(
        label="Download Excel",
        data=excel_buffer.getvalue(),
        file_name=f"{dataset_key}_filtered.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_nl_filter_xlsx",
    )
