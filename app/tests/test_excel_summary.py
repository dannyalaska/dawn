from __future__ import annotations

import pandas as pd

from app.core.excel.summary import DatasetMetric, summarize_dataframe


def test_summarize_dataframe_metrics():
    df = pd.DataFrame(
        {
            "Category": ["Login", "Billing", "Login", "Operations"],
            "Severity": ["P1", "P2", "P1", "P3"],
            "Count": [5, 2, 3, 1],
        }
    )

    summary_text, column_summaries, metrics = summarize_dataframe(df, max_values=3)

    assert "rows=4" in summary_text
    assert any(cs.name == "Category" for cs in column_summaries)

    value_metric = next(
        (m for m in metrics if isinstance(m, DatasetMetric) and m.column == "Category"), None
    )
    assert value_metric is not None
    assert value_metric.values[0][0] == "Login"
    assert value_metric.values[0][1] == 2


def test_summarize_dataframe_numeric_stats():
    df = pd.DataFrame({"Count": [1, 2, 3, 4, 5]})
    _, column_summaries, metrics = summarize_dataframe(df)

    num_summary = next(cs for cs in column_summaries if cs.name == "Count")
    assert num_summary.stats is not None
    assert num_summary.stats["min"] == 1
    assert num_summary.stats["max"] == 5
    assert metrics == []
