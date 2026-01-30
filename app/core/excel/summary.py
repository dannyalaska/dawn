from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ColumnSummary:
    name: str
    dtype: str
    top_values: list[tuple[str, int]] | None = None
    stats: dict[str, float] | None = None


@dataclass(frozen=True)
class DatasetMetric:
    type: str  # e.g. "value_counts"
    column: str
    values: list[tuple[str, int]]
    description: str | None = None


def _format_top_values(values: Iterable[tuple[str, int]]) -> str:
    return ", ".join(f"{label} ({count})" for label, count in values)


def _relationship_hint(col_name: str, dtype: str) -> str | None:
    name = col_name.lower()
    if "assigned" in name or "resolver" in name or "owner" in name:
        return "resolver"
    if "agent" in name or "handler" in name:
        return "agent"
    if "category" in name or "type" in name:
        return "category"
    if "status" in name or "state" in name:
        return "status"
    if dtype.startswith("float") or dtype.startswith("int"):
        if any(key in name for key in ["time", "hour", "duration", "days", "age"]):
            return "duration"
        if any(key in name for key in ["cost", "price", "amount", "revenue"]):
            return "cost"
        if any(key in name for key in ["count", "num", "tickets"]):
            return "count"
    return None


# Create a lightweight textual + structured summary for the dataframe
# this is what enables the RAG layer to reason about the dataset
# numerical vs categorical columns, top values, basic stats, etc.
def summarize_dataframe(
    df: pd.DataFrame, *, max_values: int = 5
) -> tuple[str, list[ColumnSummary], list[DatasetMetric], dict[str, object]]:
    """Create a lightweight textual + structured summary for the dataframe."""
    summaries: list[ColumnSummary] = []
    lines: list[str] = [f"Dataset summary: rows={len(df)}, columns={len(df.columns)}."]
    metrics: list[DatasetMetric] = []
    counts_by: dict[str, list[dict[str, int | str]]] = {}
    aggregates: list[dict[str, object]] = []
    plan: list[dict[str, object]] = []
    relationships: dict[str, str] = {}

    # Determine candidate column types
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    categorical_cols = [
        c for c in df.columns if not pd.api.types.is_numeric_dtype(df[c]) and df[c].nunique() > 1
    ]

    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        norm_name = str(col).strip().lower()

        hint = _relationship_hint(col, dtype)
        if hint:
            relationships[col] = hint

        if pd.api.types.is_numeric_dtype(series):
            clean = pd.to_numeric(series, errors="coerce").dropna()
            if clean.empty:
                summaries.append(ColumnSummary(name=str(col), dtype=dtype))
                continue
            stats = {
                "min": float(clean.min()),
                "max": float(clean.max()),
                "mean": float(clean.mean()),
                "median": float(clean.median()),
            }
            summaries.append(ColumnSummary(name=str(col), dtype=dtype, stats=stats))
            lines.append(
                f"{col}: numeric stats min={stats['min']:.2f}, median={stats['median']:.2f}, "
                f"mean={stats['mean']:.2f}, max={stats['max']:.2f}"
            )
        else:
            clean = series.fillna("∅").astype(str)
            top = clean.value_counts().head(max_values)
            top_pairs = [(str(idx), int(val)) for idx, val in top.items()]
            summaries.append(ColumnSummary(name=str(col), dtype=dtype, top_values=top_pairs))
            if top_pairs:
                lines.append(f"{col}: top values {_format_top_values(top_pairs)}")
                counts_by[str(col)] = [
                    {"label": label, "count": count} for label, count in top_pairs
                ]
                plan.append({"type": "count_by", "column": str(col)})
                if norm_name in {"category", "severity", "status", "owner", "assignee"}:
                    description = f"Most common {col}"
                    metrics.append(
                        DatasetMetric(
                            type="value_counts",
                            column=str(col),
                            values=top_pairs,
                            description=description,
                        )
                    )
            else:
                lines.append(f"{col}: no frequent values identified")

    # Aggregations: focus on resolver/time style combinations
    aggregation_keywords = ("time", "hour", "duration", "resolve", "age", "days")
    group_keywords = ("assign", "owner", "resolver", "agent", "team")

    for cat_col in categorical_cols:
        lower_cat = cat_col.lower()
        if any(key in lower_cat for key in group_keywords):
            for num_col in numeric_cols:
                lower_num = num_col.lower()
                if any(key in lower_num for key in aggregation_keywords):
                    grouped = (
                        df.groupby(cat_col)[num_col]
                        .apply(lambda s: pd.to_numeric(s, errors="coerce").dropna())
                        .dropna()
                    )
                    if grouped.empty:
                        continue
                    mean_series = grouped.groupby(level=0).mean().dropna()
                    if mean_series.empty:
                        continue
                    sorted_means = mean_series.sort_values()
                    best_entries = sorted_means.head(max_values)
                    worst_entries = mean_series.sort_values(ascending=False).head(max_values)
                    aggregates.append(
                        {
                            "group": cat_col,
                            "value": num_col,
                            "stat": "mean",
                            "best": [
                                {"label": str(idx), "value": float(val)}
                                for idx, val in best_entries.items()
                            ],
                            "worst": [
                                {"label": str(idx), "value": float(val)}
                                for idx, val in worst_entries.items()
                            ],
                        }
                    )
                    plan.append(
                        {"type": "avg_by", "group": cat_col, "value": num_col, "stat": "mean"}
                    )

    extras: dict[str, object] = {
        "counts": counts_by,
        "aggregates": aggregates,
        "relationships": relationships,
        "plan": plan,
    }

    return "\n".join(lines), summaries, metrics, extras
