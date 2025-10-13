import io
import json
import zipfile
from collections.abc import Iterable
from typing import Any, NamedTuple

import pandas as pd
import requests
import streamlit as st

try:  # Allow running streamlit directly without editable install
    from app.core.nl_filter import apply_nl_filter
except ModuleNotFoundError:  # pragma: no cover - fallback for CLI usage
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from app.core.nl_filter import apply_nl_filter


class PendingFile(NamedTuple):
    name: str
    data: bytes
    content_type: str
    sheet: str | None


def _guess_feed_type(sample_columns: Iterable[str]) -> str:
    text = " ".join(col.lower() for col in sample_columns)
    if any(tok in text for tok in ["amount", "transaction", "balance", "merchant"]):
        return "Finance"
    if any(tok in text for tok in ["patient", "provider", "claim", "diagnosis"]):
        return "Healthcare"
    if any(tok in text for tok in ["ticket", "agent", "sla", "queue"]):
        return "Operations"
    return "General"


def _load_uploaded_files(files: list[Any]) -> list[PendingFile]:
    pending: list[PendingFile] = []
    for file in files:
        filename = file.name
        if filename.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(file.getvalue())) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    if not member.filename.lower().endswith((".csv", ".xlsx", ".xlsm", ".xls")):
                        continue
                    bytes_data = zf.read(member)
                    pending.append(
                        PendingFile(
                            name=member.filename.split("/")[-1],
                            data=bytes_data,
                            content_type="application/octet-stream",
                            sheet=None,
                        )
                    )
        else:
            pending.append(
                PendingFile(
                    name=filename,
                    data=file.getvalue(),
                    content_type=file.type or "application/octet-stream",
                    sheet=None,
                )
            )
    return pending


def _build_dataframes(
    pending_files: list[PendingFile], default_sheet: str | None
) -> dict[str, pd.DataFrame]:
    dataframes: dict[str, pd.DataFrame] = {}
    for pending in pending_files:
        name = pending.name
        data = pending.data
        buffer = io.BytesIO(data)
        try:
            if name.lower().endswith((".xlsx", ".xlsm", ".xls")):
                df = pd.read_excel(buffer, sheet_name=default_sheet or 0)
            else:
                df = pd.read_csv(buffer)
        except Exception:  # noqa: BLE001
            df = pd.DataFrame()
        dataframes[name] = df
    return dataframes


def _render_stepper(steps: list[str], current_step: int) -> None:
    cols = st.columns(len(steps))
    for idx, (col, name) in enumerate(zip(cols, steps, strict=False), start=1):
        if idx < current_step:
            icon = "✅"
        elif idx == current_step:
            icon = "🟢"
        else:
            icon = "⚪️"
        col.markdown(f"{icon} **Step {idx}: {name}**")


def _render_manifest_preview(manifest: dict[str, Any]) -> None:
    st.markdown("#### Manifest preview")
    st.json(manifest)
    download = json.dumps(manifest, indent=2).encode("utf-8")
    st.download_button(
        label="Download manifest.json",
        data=download,
        file_name=f"{manifest['feed']['identifier']}_manifest.json",
        mime="application/json",
        key="feed_wizard_manifest_download",
    )


def _render_drift_summary(results: list[dict[str, Any]]) -> None:
    drift = results[-1].get("drift") or {}
    if not drift:
        return
    st.markdown("#### Change summary")
    status = drift.get("status", "unknown").replace("_", " ").title()
    rows = drift.get("rows", {})
    cols = drift.get("columns", {})
    st.write(f"Status: **{status}** • Rows: {rows.get('current', '—')} (Δ {rows.get('delta', 0)})")
    if cols.get("added") or cols.get("removed"):
        st.write(
            "- New columns: "
            + ", ".join(cols.get("added", []) or ["None"])
            + " | Removed: "
            + ", ".join(cols.get("removed", []) or ["None"])
        )
    if cols.get("type_changes"):
        st.write("- Type changes:")
        for change in cols["type_changes"]:
            st.write(f"  • `{change['column']}`: {change['previous']} → {change['current']}")
    if cols.get("null_ratio_changes"):
        st.write("- Null ratio changes:")
        for change in cols["null_ratio_changes"]:
            st.write(
                f"  • `{change['column']}` Δ {change['delta']:.2f}% (now {change['current_null_percent']:.2f}%)"
            )


def _render_schedule_section() -> None:
    st.markdown("### Schedule & automation preferences")
    st.caption(
        "Configure when DAWN should expect new files. We'll use this in Sprint 2 to auto-create jobs."
    )
    freq = st.selectbox(
        "Refresh cadence",
        ["Manual only", "Daily", "Weekly", "Monthly"],
        key="feed_wizard_schedule_freq",
    )
    time = st.time_input("Preferred run time", key="feed_wizard_schedule_time")
    notify = st.multiselect(
        "Notify via",
        ["Email", "Slack"],
        key="feed_wizard_schedule_notify",
    )
    st.session_state["feed_wizard_schedule"] = {
        "frequency": freq,
        "time": str(time),
        "notify": notify,
    }
    if st.button("Save schedule preferences", key="feed_wizard_schedule_save"):
        st.session_state["feed_wizard_schedule_saved"] = True
        st.session_state["feed_wizard_step"] = 3
        st.success("Schedule preferences saved. Automation hooks coming soon!")


def _ingest_files(
    api_base: str,
    identifier: str,
    name: str,
    owner: str,
    default_sheet: str,
    pending_files: list[PendingFile],
) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    total_files = len(pending_files)
    progress = st.progress(0, text="Starting ingestion…")

    for idx, pending in enumerate(pending_files, start=1):
        filename = pending.name.lower()
        data_format = "excel" if filename.endswith(("xlsx", "xlsm", "xls")) else "csv"
        form_fields: dict[str, Any] = {
            "identifier": identifier,
            "name": name,
            "owner": owner,
            "source_type": "upload",
            "data_format": data_format,
        }
        if default_sheet:
            form_fields["sheet"] = default_sheet

        files = {
            "file": (
                pending.name,
                pending.data,
                pending.content_type,
            )
        }

        progress.progress(
            idx / total_files, text=f"Ingesting {pending.name} ({idx}/{total_files})…"
        )
        try:
            resp = requests.post(
                f"{api_base}/feeds/ingest",
                data=form_fields,
                files=files,
                timeout=120,
            )
            resp.raise_for_status()
            result = resp.json()
            result["__source_file"] = pending.name
            results.append(result)
        except requests.RequestException as exc:
            errors.append(f"{pending.name}: {exc}")

    progress.progress(1.0, text="All done!")
    return results, errors


def _render_summary_card(result: dict[str, Any]) -> None:
    summary = result.get("summary", {}) or {}
    summary_json = summary.get("json", {}) if isinstance(summary.get("json"), dict) else {}
    schema = result.get("schema", {}) or {}
    columns = schema.get("columns") or []

    st.markdown(
        f"#### {result.get('feed', {}).get('name', 'Feed')} v{result.get('version', {}).get('number', 1)}"
    )
    cols = st.columns(4)
    cols[0].metric("Rows", str(result.get("version", {}).get("rows", "—")))
    cols[1].metric("Columns", str(result.get("version", {}).get("columns", "—")))
    pk = ", ".join(schema.get("primary_keys") or ["—"])
    cols[2].metric("Primary keys", pk or "—")
    cols[3].metric("FK candidates", str(len(schema.get("foreign_keys") or [])))

    if columns:
        sample_cols = ", ".join(col.get("name") for col in columns[:8] if col.get("name"))
        st.caption(f"Columns: {sample_cols}")

    mermaid = summary_json.get("mermaid")
    if mermaid:
        with st.expander("Visual ER diagram"):
            st.markdown(f"```mermaid\n{mermaid}\n```")


def _render_pk_override(api_base: str, result: dict[str, Any]) -> None:
    schema = result.get("schema", {}) or {}
    summary = result.get("summary", {}) or {}
    summary_json = summary.get("json", {}) if isinstance(summary.get("json"), dict) else {}
    columns = schema.get("columns") or []
    if not columns:
        return

    st.markdown("#### Manual column roles")
    options = [col.get("name") for col in columns if col.get("name")]
    default_pk = schema.get("primary_keys") or []
    selected_pk = st.multiselect(
        "Pick primary key columns",
        options=options,
        default=default_pk,
        key=f"feed_wizard_pk_{result.get('feed', {}).get('identifier')}",
    )

    if st.button(
        "Save column overrides", key=f"save_pk_{result.get('feed', {}).get('identifier')}"
    ):
        version = result.get("version", {}) or {}
        sha16 = version.get("sha16")
        sheet = (
            summary_json.get("sheet")
            or result.get("schema", {}).get("sheet")
            or result.get("summary", {}).get("sheet")
            or summary_json.get("name")
        )
        if not sha16 or not sheet:
            st.warning(
                "Unable to locate this feed in memory yet. Try reloading once profiling finishes."
            )
            return
        relationships = (
            summary_json.get("relationships", {}) if isinstance(summary_json, dict) else {}
        )
        relationships = dict(relationships)
        for col in options:
            if relationships.get(col) == "primary_key":
                relationships.pop(col)
        for col in selected_pk:
            relationships[col] = "primary_key"

        payload = {
            "sha16": sha16,
            "sheet": sheet,
            "relationships": relationships,
        }
        try:
            resp = requests.put(f"{api_base}/rag/memory", json=payload, timeout=15)
            resp.raise_for_status()
            st.success("Overrides saved! Future runs will remember your choices.")
        except requests.RequestException as exc:
            st.error(f"Could not save overrides: {exc}")


def _render_filter_lab(dataframes: dict[str, pd.DataFrame]) -> None:
    st.markdown("#### Ask DAWN to filter your feed")
    if not dataframes:
        st.info("Upload a dataset to unlock natural-language filtering.")
        return
    dataset_names = [name for name, df in dataframes.items() if not df.empty]
    if not dataset_names:
        st.warning("We couldn't read the uploaded files. Try a different format.")
        return
    dataset_key = st.selectbox("Pick a dataset", dataset_names, key="feed_wizard_dataset")
    question = st.text_input(
        "Describe the rows you want (e.g., “users where status equals active and age > 30”)",
        key="feed_wizard_question",
    )
    run = st.button("Run LLM-style filter", key="feed_wizard_run_filter")
    if run:
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
            key="feed_wizard_download_csv",
        )
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
            filtered.to_excel(writer, index=False, sheet_name="Filtered")
        st.download_button(
            label="Download Excel",
            data=excel_buffer.getvalue(),
            file_name=f"{dataset_key}_filtered.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="feed_wizard_download_xlsx",
        )


def render_feed_wizard(api_base: str) -> None:
    steps = ["Upload", "Review & Manifest", "Schedule"]
    current_step = st.session_state.get("feed_wizard_step", 1)
    last_result = st.session_state.get("feed_wizard_last_result")
    if last_result and last_result.get("status") == "success":
        current_step = max(current_step, 2)
    if st.session_state.get("feed_wizard_schedule_saved"):
        current_step = max(current_step, 3)
    st.session_state["feed_wizard_step"] = current_step

    _render_stepper(steps, current_step)

    st.markdown(
        """
        ### 🚀 Datafeed Mode
        1. Give your feed a **name**.
        2. Drop in one file, a whole folder, or a zip bundle.
        3. Tap the big friendly button.

        We do the rest — profile the file, save the schema, draw an ER diagram,
        and register auto data-quality checks.
        """,
    )

    prefill_info = st.session_state.get("feed_wizard_prefill")
    if isinstance(prefill_info, dict):
        promoted_name = str(prefill_info.get("name", "uploaded_file"))
        st.info(
            f"File promoted from Quick Insight: `{promoted_name}`. Fill in the details below to make it a managed feed.",
            icon="👉",
        )

    with st.form("feed_wizard_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            feed_name = st.text_input("What should we call it?", value="My Awesome Feed")
        with col2:
            feed_identifier = st.text_input(
                "Short ID (letters & underscores)", value="my_awesome_feed"
            )

        owner = st.text_input("Who owns this data?", value="Data Team")
        _ = st.selectbox(
            "Where is it coming from?",
            options=["Upload (CSV/Excel)", "S3 (soon)", "HTTP API (soon)"],
            index=0,
            disabled=True,
            help="Today we support uploads. Additional sources are coming next sprint.",
        )

        uploaded_files = st.file_uploader(
            "Drop CSV, Excel, or a ZIP of files",
            type=["csv", "xlsx", "xlsm", "xls", "zip"],
            accept_multiple_files=True,
        )
        sheet_name = st.text_input(
            "If it's an Excel workbook, which sheet?", placeholder="Leave blank for the first sheet"
        )

        submitted = st.form_submit_button("✨ Make my feed!")

    if submitted:
        if not feed_name.strip() or not feed_identifier.strip():
            st.error("A name and identifier make the magic happen. Give them a quick tweak!")
            return
        pending_files = _load_uploaded_files(uploaded_files) if uploaded_files else []
        if not pending_files and prefill_info:
            pending_files = [
                PendingFile(
                    name=prefill_info.get("name", "promoted_feed"),
                    data=prefill_info.get("bytes", b""),
                    content_type=prefill_info.get("content_type", "application/octet-stream"),
                    sheet=prefill_info.get("sheet"),
                )
            ]
        if not pending_files:
            st.error(
                "Drop at least one file (or promote from Quick Insight) and we'll handle the rest."
            )
            return

        default_sheet = sheet_name.strip() or (prefill_info.get("sheet") if prefill_info else None)
        dataframes = _build_dataframes(pending_files, default_sheet)
        st.session_state["feed_wizard_dataframes"] = dataframes
        results, errors = _ingest_files(
            api_base=api_base,
            identifier=feed_identifier.strip(),
            name=feed_name.strip(),
            owner=owner.strip(),
            default_sheet=default_sheet or "",
            pending_files=pending_files,
        )
        if errors:
            st.error("Some files had issues:\n" + "\n".join(errors))

        if results:
            st.session_state["feed_wizard_last_result"] = {
                "status": "success",
                "data": results,
                "form": {
                    "identifier": feed_identifier.strip(),
                    "name": feed_name.strip(),
                    "owner": owner.strip(),
                    "sheet": sheet_name.strip(),
                },
                "files": [
                    {
                        "name": pending.name,
                        "data": pending.data,
                        "type": pending.content_type,
                    }
                    for pending in pending_files
                ],
            }
            last_result = st.session_state["feed_wizard_last_result"]
            guess = _guess_feed_type(
                [col.get("name", "") for col in results[0].get("schema", {}).get("columns", [])]
            )
            st.success(f"Feed created! I think this looks like a **{guess}** dataset.")
            st.session_state["feed_wizard_step"] = 2
            st.session_state.pop("feed_wizard_prefill", None)

    if last_result and last_result.get("status") == "success":
        results = last_result.get("data", [])
        if isinstance(results, dict):
            results = [results]
        if results:
            for result in results:
                _render_summary_card(result)
                _render_pk_override(api_base, result)
                version_meta = result.get("version", {})
                summary_payload = result.get("summary", {})
                summary_json = (
                    summary_payload.get("json", {}) if isinstance(summary_payload, dict) else {}
                )
                if st.button(
                    "Open latest version in Quick Insight",
                    key=f"open_quick_{version_meta.get('number', 1)}",
                ):
                    st.session_state["quick_insight_seed"] = {
                        "sha16": version_meta.get("sha16"),
                        "sheet": summary_json.get("sheet"),
                        "filename": result.get("feed", {}).get("name", "feed") + ".csv",
                    }
                    st.session_state["workspace_mode"] = "Quick Insight"
                    st.rerun()
            manifest = results[0].get("manifest")
            if manifest:
                _render_manifest_preview(manifest)
            _render_drift_summary(results)

        if st.session_state.get("feed_wizard_step", 1) < 3 and st.button(
            "Next: scheduling & automation", key="feed_wizard_go_schedule"
        ):
            st.session_state["feed_wizard_step"] = 3

        if st.button("🔁 Re-run ingestion", key="feed_wizard_rerun"):
            saved = st.session_state.get("feed_wizard_last_result", {})
            form = saved.get("form", {})
            files_info = saved.get("files", [])
            if not form or not files_info:
                st.warning("Upload a feed first before re-running.")
            else:
                st.info("Replaying the last ingestion…")
                pending_files = [
                    PendingFile(
                        name=info["name"], data=info["data"], content_type=info["type"], sheet=None
                    )
                    for info in files_info
                ]
                dataframes = _build_dataframes(pending_files, form.get("sheet") or None)
                st.session_state["feed_wizard_dataframes"] = dataframes
                results, errors = _ingest_files(
                    api_base=api_base,
                    identifier=form.get("identifier", ""),
                    name=form.get("name", ""),
                    owner=form.get("owner", ""),
                    default_sheet=form.get("sheet", ""),
                    pending_files=pending_files,
                )
                if errors:
                    st.error("Re-run issues:\n" + "\n".join(errors))
                if results:
                    st.session_state["feed_wizard_last_result"]["data"] = results
                    st.success("Feed refreshed! All summaries are up to date.")

    if st.session_state.get("feed_wizard_step", 1) >= 3:
        _render_schedule_section()
    elif last_result and last_result.get("status") == "error":
        st.error(last_result.get("message", "Unknown error"))
