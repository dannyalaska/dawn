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


def summarize_dataframe(
    df: pd.DataFrame, *, max_values: int = 5
) -> tuple[str, list[ColumnSummary], list[DatasetMetric]]:
    """Create a lightweight textual + structured summary for the dataframe."""
    summaries: list[ColumnSummary] = []
    lines: list[str] = [f"Dataset summary: rows={len(df)}, columns={len(df.columns)}."]
    metrics: list[DatasetMetric] = []

    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        norm_name = str(col).strip().lower()

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

    return "\n".join(lines), summaries, metrics
