from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable
from contextlib import suppress
from datetime import date, datetime
from difflib import SequenceMatcher
from hashlib import sha256
from io import BytesIO
from typing import Any, BinaryIO, cast

import numpy as np
import pandas as pd
import requests
from sqlalchemy import Table, func, select

from app.core.config import settings
from app.core.db import get_engine, session_scope
from app.core.dq import sync_auto_rules
from app.core.excel.summary import ColumnSummary, DatasetMetric, summarize_dataframe
from app.core.limits import SizeLimitError, read_stream_bytes
from app.core.models import Feed, FeedDataset, FeedVersion
from app.core.rag import Chunk, simple_chunker, upsert_chunks
from app.core.redis_client import redis_sync
from app.core.storage import bucket_name, s3


class FeedIngestError(Exception):
    """Raised when feed ingestion cannot proceed."""


FEED_SOURCE_KINDS = {"upload", "s3", "http"}
DATA_FORMATS = {"excel", "csv"}
MAX_DATASET_ROWS = int(os.getenv("DAWN_MAX_DATASET_ROWS", "200000"))
DATASET_TABLE_PREFIX = "dawn_feed_"
logger = logging.getLogger(__name__)


def _infer_format(filename: str | None, declared: str | None) -> str:
    if declared and declared.lower() in DATA_FORMATS:
        return declared.lower()
    if filename:
        fname = filename.lower()
        if fname.endswith((".xlsx", ".xlsm", ".xls")):
            return "excel"
        if fname.endswith(".csv"):
            return "csv"
    return "excel"


def _ensure_kind(kind: str) -> str:
    k = kind.lower()
    if k not in FEED_SOURCE_KINDS:
        raise FeedIngestError(
            f"Unsupported source_type {kind!r}. Expected one of {sorted(FEED_SOURCE_KINDS)}."
        )
    return k


def _load_excel(content: bytes, sheet: str | None) -> tuple[pd.DataFrame, str, list[str]]:
    xl = pd.ExcelFile(BytesIO(content))
    target_sheet = sheet or xl.sheet_names[0]
    if target_sheet not in xl.sheet_names:
        raise FeedIngestError(
            f"Sheet {target_sheet!r} not found. Available sheets: {', '.join(xl.sheet_names)}."
        )
    return xl.parse(target_sheet), target_sheet, list(xl.sheet_names)


def _load_csv(content: bytes) -> pd.DataFrame:
    return pd.read_csv(BytesIO(content))


def _fetch_s3_bytes(path: str | None) -> bytes:
    if not path:
        raise FeedIngestError("s3_path must be provided for source_type='s3'.")
    bucket = None
    key = path
    if path.startswith("s3://"):
        without = path[len("s3://") :]
        if "/" not in without:
            raise FeedIngestError("s3_path must include an object key, e.g. s3://bucket/key.xlsx")
        bucket, key = without.split("/", 1)
    if bucket is None or not bucket:
        bucket = bucket_name()
    client = s3()
    resp = client.get_object(Bucket=bucket, Key=key)
    content_len = resp.get("ContentLength")
    _enforce_remote_limit(content_len, f"S3 object {path or key}")
    body = resp.get("Body")
    if body is None:
        raise FeedIngestError(f"Empty S3 object for path {path!r}")
    try:
        return read_stream_bytes(body, label=f"S3 object {path or key}")
    except SizeLimitError as exc:
        raise FeedIngestError(str(exc)) from exc


def _fetch_http_bytes(url: str | None) -> bytes:
    if not url:
        raise FeedIngestError("http_url must be provided for source_type='http'.")
    try:
        resp = requests.get(url, timeout=10, stream=True)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise FeedIngestError(f"Failed to download {url!r}: {exc}") from exc
    content_len = resp.headers.get("Content-Length")
    if content_len:
        with suppress(ValueError):
            _enforce_remote_limit(int(content_len), f"HTTP download {url}")
    try:
        return read_stream_bytes(cast(BinaryIO, resp.raw), label=f"HTTP download {url}")
    except SizeLimitError as exc:
        raise FeedIngestError(str(exc)) from exc
    finally:
        resp.close()


def _enforce_remote_limit(size: int | None, label: str) -> None:
    limit = settings.MAX_REMOTE_BYTES
    if limit <= 0 or size is None:
        return
    if size > limit:
        raise FeedIngestError(f"{label} exceeds limit ({size} bytes > {limit} bytes).")


def _collect_existing_columns(
    exclude_identifier: str | None, *, user_id: int
) -> list[dict[str, str]]:
    with session_scope() as s:
        stmt = (
            select(Feed.identifier, FeedVersion.schema_)
            .join(FeedVersion, Feed.id == FeedVersion.feed_id)
            .where(Feed.user_id == user_id)
            .order_by(FeedVersion.created_at.desc())
        )
        rows = s.execute(stmt).all()
    seen: list[dict[str, str]] = []
    for identifier, schema_json in rows:
        if exclude_identifier and identifier == exclude_identifier:
            continue
        if not schema_json:
            continue
        columns = schema_json.get("columns") if isinstance(schema_json, dict) else None
        if not columns or not isinstance(columns, list):
            continue
        for col in columns:
            name = str(col.get("name", ""))
            dtype = str(col.get("dtype", ""))
            if not name:
                continue
            seen.append({"feed_identifier": identifier, "column": name, "dtype": dtype})
    return seen


def _dataset_table_name(identifier: str, version: int) -> str:
    slug = re.sub(r"[^a-z0-9_]", "_", identifier.lower()).strip("_")
    slug = slug or "feed"
    table = f"{DATASET_TABLE_PREFIX}{slug}_v{version}"
    return table[:60]


def _dataset_info(dataset: FeedDataset) -> dict[str, Any]:
    return {
        "table": dataset.table_name,
        "schema": dataset.schema_name,
        "rows": dataset.row_count,
        "columns": dataset.column_count,
    }


def _write_dataset_table(
    df: pd.DataFrame,
    *,
    identifier: str,
    version_number: int,
) -> tuple[dict[str, Any], list[str]] | None:
    if df.empty:
        return None
    if MAX_DATASET_ROWS > 0 and len(df) > MAX_DATASET_ROWS:
        return None

    table_name = _dataset_table_name(identifier, version_number)
    engine = get_engine()
    schema_name = getattr(engine.dialect, "default_schema_name", None)
    safe_df = df.copy()
    safe_df.columns = [str(col) for col in safe_df.columns]
    safe_df.to_sql(
        table_name,
        con=engine,
        if_exists="replace",
        index=False,
        chunksize=2000,
    )
    info = {
        "table": table_name,
        "schema": schema_name,
        "rows": int(len(safe_df)),
        "columns": int(len(safe_df.columns)),
    }
    return info, list(safe_df.columns)


def _record_dataset(
    *,
    feed_id: int,
    feed_version_id: int,
    info: dict[str, Any],
    columns: list[str],
) -> dict[str, Any]:
    with session_scope() as session:
        table = cast(Table, FeedDataset.__table__)
        table.create(bind=session.get_bind(), checkfirst=True)
        existing = (
            session.execute(
                select(FeedDataset).where(FeedDataset.feed_version_id == feed_version_id)
            )
            .scalars()
            .first()
        )
        if existing:
            return _dataset_info(existing)
        dataset = FeedDataset(
            feed_id=feed_id,
            feed_version_id=feed_version_id,
            table_name=info["table"],
            schema_name=info.get("schema"),
            storage="database",
            columns=columns,
            row_count=int(info.get("rows", 0)),
            column_count=int(info.get("columns", len(columns))),
        )
        session.add(dataset)
        version = session.get(FeedVersion, feed_version_id)
        if version:
            summary = dict(version.summary_json or {})
            summary["materialized_table"] = info
            version.summary_json = summary
        session.flush()
    return info


def _looks_like_id(name: str) -> bool:
    lowered = name.lower()
    return lowered == "id" or lowered.endswith("_id") or "id" in lowered.split("_")


def _infer_foreign_keys(
    columns: list[dict[str, Any]],
    existing_columns: Iterable[dict[str, str]],
    current_identifier: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for col in columns:
        col_name = str(col["name"])
        if col.get("is_primary_key_candidate"):
            continue
        if not _looks_like_id(col_name):
            continue
        matches: list[dict[str, Any]] = []
        for other in existing_columns:
            if other["feed_identifier"] == current_identifier:
                continue
            score = SequenceMatcher(None, col_name.lower(), other["column"].lower()).ratio()
            if score >= 0.78:
                matches.append(
                    {
                        "feed_identifier": other["feed_identifier"],
                        "column": other["column"],
                        "similarity": round(score, 3),
                    }
                )
        if matches:
            matches.sort(key=lambda m: m["similarity"], reverse=True)
            results.append({"column": col_name, "candidates": matches[:5]})
    return results


def _columns_schema(df: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    rows = len(df)
    columns: list[dict[str, Any]] = []
    primary_candidates: list[str] = []

    for col in df.columns:
        series = df[col]
        non_null = int(series.notna().sum())
        null_percent = float(((rows - non_null) / rows) * 100) if rows else 0.0
        unique_count = int(series.nunique(dropna=True))
        unique_percent = float((unique_count / rows) * 100) if rows else 0.0
        sample_values = [str(v) for v in series.dropna().astype(str).head(5).tolist()]
        dtype = str(series.dtype)
        is_primary_candidate = bool(
            rows
            and non_null == rows
            and unique_count == rows
            and not pd.api.types.is_float_dtype(series)
        )
        if not is_primary_candidate and rows and unique_percent >= 98.0 and null_percent <= 5.0:
            is_primary_candidate = True

        column_info = {
            "name": str(col),
            "dtype": dtype,
            "null_percent": round(null_percent, 3),
            "unique_percent": round(unique_percent, 3),
            "non_null": non_null,
            "unique_count": unique_count,
            "sample_values": sample_values,
            "is_primary_key_candidate": is_primary_candidate,
        }
        if is_primary_candidate:
            primary_candidates.append(str(col))
        columns.append(column_info)

    return columns, primary_candidates


def _normalize_scalar(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, pd.Timestamp | datetime | date):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, bytes | bytearray):
        return value.decode("utf-8", errors="ignore")
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except Exception:
            pass
    return value


def _serialize_rows(df: pd.DataFrame, *, limit: int = 50) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if df.empty:
        return rows
    for record in df.head(limit).to_dict(orient="records"):
        normalized = {str(col): _normalize_scalar(val) for col, val in record.items()}
        rows.append(normalized)
    return rows


def _column_summaries_to_dict(summaries: Iterable[ColumnSummary]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for item in summaries:
        data = {
            "name": item.name,
            "dtype": item.dtype,
            "top_values": item.top_values,
            "stats": item.stats,
        }
        serialized.append(data)
    return serialized


def _metrics_to_dict(metrics: Iterable[DatasetMetric]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for metric in metrics:
        out.append(
            {
                "type": metric.type,
                "column": metric.column,
                "values": [{"label": label, "count": count} for label, count in metric.values],
                "description": metric.description,
            }
        )
    return out


def _markdown_summary(
    *,
    identifier: str,
    name: str,
    owner: str | None,
    source_kind: str,
    data_format: str,
    rows: int,
    cols: int,
    columns_schema: list[dict[str, Any]],
    primary_keys: list[str],
    foreign_keys: list[dict[str, Any]],
    summary_text: str,
) -> tuple[str, str]:
    lines = [
        f"# Feed {name} (`{identifier}`)",
        "",
        f"- Owner: {owner or 'n/a'}",
        f"- Source type: {source_kind}",
        f"- Format: {data_format}",
        f"- Rows: {rows}",
        f"- Columns: {cols}",
        "",
        "## Column Overview",
        "| Column | Type | Null % | Unique % | Sample Values |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for col in columns_schema:
        sample = ", ".join(col.get("sample_values", [])[:3]) or "—"
        lines.append(
            f"| `{col['name']}` | {col['dtype']} | {col['null_percent']:.2f} | "
            f"{col['unique_percent']:.2f} | {sample} |"
        )

    lines.append("")
    lines.append("## Primary Key Candidates")
    if primary_keys:
        for pk in primary_keys:
            lines.append(f"- `{pk}`")
    else:
        lines.append("- None detected")

    lines.append("")
    lines.append("## Foreign Key Candidates")
    if foreign_keys:
        for fk in foreign_keys:
            cand_text = ", ".join(
                f"{c['feed_identifier']}.{c['column']} ({c['similarity']:.2f})"
                for c in fk.get("candidates", [])
            )
            lines.append(f"- `{fk['column']}` → {cand_text}")
    else:
        lines.append("- None detected")

    lines.append("")
    lines.append("## Profile Summary")
    lines.append("")
    lines.append(summary_text or "No profile summary generated.")
    lines.append("")

    er_diagram = _mermaid_er(identifier, columns_schema, foreign_keys)
    if er_diagram:
        lines.append("## ER Diagram")
        lines.append("```mermaid")
        lines.extend(er_diagram.splitlines())
        lines.append("```")

    return "\n".join(lines), er_diagram


def _mermaid_er(
    identifier: str, columns_schema: list[dict[str, Any]], foreign_keys: list[dict[str, Any]]
) -> str:
    if not columns_schema:
        return ""
    lines = ["erDiagram", f"    {identifier} {{"]
    for col in columns_schema:
        dtype = str(col.get("dtype", "unknown"))
        name = str(col.get("name", "column"))
        pk_flag = " PK" if col.get("is_primary_key_candidate") else ""
        lines.append(f"        {dtype} {name}{pk_flag}")
    lines.append("    }")
    for fk in foreign_keys:
        column_name = str(fk.get("column", ""))
        for candidate in fk.get("candidates", []) or []:
            target_feed = candidate.get("feed_identifier")
            if not target_feed:
                continue
            rel = f'    {identifier} ||--o{{ {target_feed} : "{column_name}"'
            lines.append(rel)
    return "\n".join(lines)


def _persist_schema_to_redis(
    identifier: str, version: int, payload: dict[str, Any], markdown: str, *, user_id: int
) -> None:
    key = f"dawn:user:{user_id}:feed:{identifier}:v{version}"
    redis_sync.hset(
        key,
        mapping={
            "summary_markdown": markdown,
            "summary_json": json.dumps(payload),
        },
    )


def _chunk_summary(identifier: str, version: int, markdown: str, *, user_id: int) -> None:
    chunks: list[Chunk] = []
    source = f"feed:{identifier}:v{version}"
    for piece in simple_chunker(markdown, max_chars=900, overlap=120):
        chunks.append(
            Chunk(
                text=piece,
                source=source,
                row_index=-1,
                chunk_type="schema",
                metadata={"tags": ["feed", identifier]},
            )
        )
    if chunks:
        upsert_chunks(chunks, user_id=str(user_id))


def _build_manifest(
    *,
    identifier: str,
    name: str,
    owner: str | None,
    source_kind: str,
    data_format: str,
    sheet: str | None,
    columns_schema: list[dict[str, Any]],
    primary_keys: list[str],
    foreign_keys: list[dict[str, Any]],
) -> dict[str, Any]:
    manifest_columns: list[dict[str, Any]] = []
    for column in columns_schema:
        manifest_columns.append(
            {
                "name": column.get("name"),
                "dtype": column.get("dtype"),
                "primary_key": column.get("name") in primary_keys,
                "null_percent": column.get("null_percent"),
                "unique_percent": column.get("unique_percent"),
                "sample_values": (column.get("sample_values") or [])[:3],
            }
        )

    foreign_key_map: list[dict[str, Any]] = []
    for fk in foreign_keys:
        candidates = fk.get("candidates") or []
        top = candidates[0] if candidates else {}
        foreign_key_map.append(
            {
                "column": fk.get("column"),
                "target_feed": top.get("feed_identifier"),
                "target_column": top.get("column"),
            }
        )

    return {
        "feed": {
            "identifier": identifier,
            "name": name,
            "owner": owner,
            "source_type": source_kind,
            "format": data_format,
            "sheet": sheet,
        },
        "columns": manifest_columns,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_key_map,
    }


def _compute_drift(
    current_schema: dict[str, Any],
    current_profile: dict[str, Any],
    previous_version: FeedVersion | None,
) -> dict[str, Any]:
    if previous_version is None:
        return {"status": "baseline", "message": "First version ingested."}

    prev_schema = previous_version.schema_ or {}
    prev_columns = {col["name"]: col for col in prev_schema.get("columns", []) if col.get("name")}
    curr_columns = {
        col["name"]: col for col in current_schema.get("columns", []) if col.get("name")
    }

    added = sorted(set(curr_columns) - set(prev_columns))
    removed = sorted(set(prev_columns) - set(curr_columns))

    changed_types: list[dict[str, Any]] = []
    changed_nulls: list[dict[str, Any]] = []
    for name in sorted(set(curr_columns) & set(prev_columns)):
        prev_col = prev_columns[name]
        curr_col = curr_columns[name]
        if str(prev_col.get("dtype")) != str(curr_col.get("dtype")):
            changed_types.append(
                {
                    "column": name,
                    "previous": prev_col.get("dtype"),
                    "current": curr_col.get("dtype"),
                }
            )
        try:
            prev_null = float(prev_col.get("null_percent", 0.0) or 0.0)
        except (TypeError, ValueError):
            prev_null = 0.0
        try:
            curr_null = float(curr_col.get("null_percent", 0.0) or 0.0)
        except (TypeError, ValueError):
            curr_null = 0.0
        delta = curr_null - prev_null
        if abs(delta) >= 5.0:
            changed_nulls.append(
                {
                    "column": name,
                    "previous_null_percent": round(prev_null, 3),
                    "current_null_percent": round(curr_null, 3),
                    "delta": round(delta, 3),
                }
            )

    prev_rows = previous_version.row_count or 0
    curr_rows = current_profile.get("row_count") or 0
    if not curr_rows:
        curr_rows = prev_rows
    row_delta = curr_rows - prev_rows

    status = "no_change"
    if added or removed or changed_types or changed_nulls or row_delta != 0:
        status = "changed"

    return {
        "status": status,
        "rows": {
            "previous": prev_rows,
            "current": curr_rows,
            "delta": row_delta,
        },
        "columns": {
            "added": added,
            "removed": removed,
            "type_changes": changed_types,
            "null_ratio_changes": changed_nulls,
        },
        "previous_version": previous_version.version,
    }


def ingest_feed(
    *,
    identifier: str,
    name: str,
    source_kind: str,
    data_format: str | None,
    owner: str | None,
    file_bytes: bytes | None,
    filename: str | None,
    sheet: str | None,
    s3_path: str | None,
    http_url: str | None,
    user_id: int,
) -> dict[str, Any]:
    kind = _ensure_kind(source_kind)
    inferred_format = _infer_format(filename, data_format)
    if inferred_format not in DATA_FORMATS:
        raise FeedIngestError(
            f"Unsupported data_format {data_format!r}. Expected one of {sorted(DATA_FORMATS)}."
        )

    raw_bytes: bytes
    if kind == "upload":
        if not file_bytes:
            raise FeedIngestError("file upload required for source_type='upload'.")
        raw_bytes = file_bytes
    elif kind == "s3":
        raw_bytes = _fetch_s3_bytes(s3_path)
    else:  # http
        raw_bytes = _fetch_http_bytes(http_url)

    resolved_sheet: str | None = None
    sheet_names: list[str] = []

    if inferred_format == "excel":
        df, resolved_sheet, sheet_names = _load_excel(raw_bytes, sheet)
    elif inferred_format == "csv":
        df = _load_csv(raw_bytes)
    else:
        raise FeedIngestError(f"Unsupported format {inferred_format!r}.")

    if df.empty:
        raise FeedIngestError("The ingested dataframe is empty.")

    # profile
    row_count = int(len(df))
    sample_df = df.copy()
    if len(sample_df) > 50000:
        sample_df = sample_df.sample(n=50000, random_state=42)

    sample_rows = _serialize_rows(df, limit=50)

    columns_schema, primary_keys = _columns_schema(sample_df)
    col_count = int(len(sample_df.columns))
    existing_columns = _collect_existing_columns(identifier, user_id=user_id)
    foreign_keys = _infer_foreign_keys(columns_schema, existing_columns, identifier)

    summary_text, column_summaries, metrics, extras = summarize_dataframe(sample_df)
    profile_payload = {
        "summary_text": summary_text,
        "columns": _column_summaries_to_dict(column_summaries),
        "metrics": _metrics_to_dict(metrics),
        "extras": extras,
        "row_count": row_count,
        "column_count": col_count,
    }
    profile_payload["sheet"] = resolved_sheet
    profile_payload["sheet_names"] = sheet_names
    profile_payload["sample_rows"] = sample_rows

    schema_payload = {
        "columns": columns_schema,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
        "sheet": resolved_sheet,
    }

    relationships_raw = extras.get("relationships") if isinstance(extras, dict) else None
    relationships_map: dict[str, Any] = {}
    if isinstance(relationships_raw, dict):
        relationships_map = dict({str(k): v for k, v in relationships_raw.items()})
    for fk in foreign_keys:
        if fk.get("candidates"):
            relationships_map[fk["column"]] = fk["candidates"][0]["feed_identifier"]

    summary_payload = {
        "text": summary_text,
        "columns": profile_payload["columns"],
        "metrics": profile_payload["metrics"],
        "insights": extras.get("counts", {}),
        "aggregates": extras.get("aggregates", []),
        "relationships": relationships_map,
        "foreign_keys": foreign_keys,
        "analysis_plan": extras.get("plan", []),
        "row_count": row_count,
        "column_count": col_count,
        "sheet": resolved_sheet,
        "sheet_names": sheet_names,
        "sample_rows": sample_rows,
    }

    manifest = _build_manifest(
        identifier=identifier,
        name=name,
        owner=owner,
        source_kind=kind,
        data_format=inferred_format,
        sheet=resolved_sheet,
        columns_schema=columns_schema,
        primary_keys=primary_keys,
        foreign_keys=foreign_keys,
    )
    summary_payload["manifest"] = manifest

    digest = sha256(raw_bytes).hexdigest()[:16]

    materialized_table_info: dict[str, Any] | None = None
    pending_dataset: dict[str, int] | None = None

    with session_scope() as s:
        feed = (
            s.execute(select(Feed).where(Feed.identifier == identifier, Feed.user_id == user_id))
            .scalars()
            .first()
        )
        if feed is None:
            feed = Feed(
                identifier=identifier,
                name=name,
                source_type=kind,
                owner=owner,
                source_config={
                    "format": inferred_format,
                    "sheet": sheet,
                    "s3_path": s3_path,
                    "http_url": http_url,
                },
                user_id=user_id,
            )
            s.add(feed)
            s.flush()
        else:
            feed.name = name
            feed.owner = owner
            cfg = dict(feed.source_config or {})
            cfg.update(
                {
                    "format": inferred_format,
                    "sheet": sheet,
                    "s3_path": s3_path,
                    "http_url": http_url,
                }
            )
            feed.source_type = kind
            feed.source_config = cfg

        latest_version = (
            s.execute(
                select(FeedVersion)
                .where(FeedVersion.feed_id == feed.id)
                .order_by(FeedVersion.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        previous_version = latest_version

        if latest_version and latest_version.sha16 == digest:
            feed_version = latest_version
            version_number = feed_version.version
            drift_payload = {"status": "no_change", "message": "No differences detected"}
        else:
            next_version = (
                s.execute(
                    select(func.max(FeedVersion.version)).where(FeedVersion.feed_id == feed.id)
                ).scalar()
                or 0
            )
            version_number = int(next_version) + 1
            feed_version = FeedVersion(
                feed_id=feed.id,
                version=version_number,
                sha16=digest,
                schema_=schema_payload,
                profile=profile_payload,
                summary_markdown="",  # set later
                summary_json=summary_payload,
                row_count=row_count,
                column_count=col_count,
                user_id=user_id,
            )
            s.add(feed_version)
            drift_payload = _compute_drift(schema_payload, profile_payload, previous_version)

        summary_payload["drift"] = drift_payload

        markdown_doc, er_diagram = _markdown_summary(
            identifier=identifier,
            name=name,
            owner=owner,
            source_kind=kind,
            data_format=inferred_format,
            rows=row_count,
            cols=col_count,
            columns_schema=columns_schema,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            summary_text=summary_text,
        )

        feed_version.schema_ = schema_payload
        feed_version.profile = profile_payload
        feed_version.summary_markdown = markdown_doc
        feed_version.summary_json = summary_payload
        feed_version.row_count = row_count
        feed_version.column_count = col_count
        feed_version.sha16 = digest
        feed_version.user_id = user_id

        s.flush()

        existing_dataset = (
            s.execute(select(FeedDataset).where(FeedDataset.feed_version_id == feed_version.id))
            .scalars()
            .first()
        )
        if existing_dataset:
            materialized_table_info = _dataset_info(existing_dataset)
            summary_payload["materialized_table"] = materialized_table_info
        else:
            pending_dataset = {
                "feed_id": feed.id,
                "feed_version_id": feed_version.id,
            }

        if er_diagram:
            summary_payload["mermaid"] = er_diagram

        s.flush()
        sync_auto_rules(session=s, feed_version=feed_version, schema_payload=schema_payload)

    # Persist summary to Redis & RAG
    try:
        _persist_schema_to_redis(
            identifier, version_number, summary_payload, markdown_doc, user_id=user_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis persist failed: %s", exc, exc_info=True)
    try:
        _chunk_summary(identifier, version_number, markdown_doc, user_id=user_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Chunk embedding failed: %s", exc, exc_info=True)

    if pending_dataset:
        write_result = _write_dataset_table(
            df=df,
            identifier=identifier,
            version_number=version_number,
        )
        if write_result:
            info, safe_columns = write_result
            materialized_table_info = _record_dataset(
                feed_id=pending_dataset["feed_id"],
                feed_version_id=pending_dataset["feed_version_id"],
                info=info,
                columns=safe_columns,
            )
            summary_payload["materialized_table"] = materialized_table_info

    return {
        "feed": {
            "identifier": identifier,
            "name": name,
            "owner": owner,
            "source_type": kind,
            "format": inferred_format,
        },
        "version": {
            "number": version_number,
            "sha16": digest,
            "rows": row_count,
            "columns": col_count,
        },
        "schema": schema_payload,
        "profile": profile_payload,
        "summary": {
            "markdown": markdown_doc,
            "json": summary_payload,
        },
        "manifest": manifest,
        "drift": drift_payload,
        "materialized_table": materialized_table_info,
    }
