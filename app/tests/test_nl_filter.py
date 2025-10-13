from __future__ import annotations

import pandas as pd

from app.core.nl_filter import apply_nl_filter


def test_apply_nl_filter_basic_equals():
    df = pd.DataFrame(
        {
            "user_id": [1, 2, 3],
            "status": ["active", "inactive", "active"],
            "balance": [150.0, 20.0, 500.0],
        }
    )

    filtered = apply_nl_filter(df, "show me users where status equals active")
    assert len(filtered) == 2
    assert set(filtered["user_id"]) == {1, 3}


def test_apply_nl_filter_numeric_comparison():
    df = pd.DataFrame(
        {
            "user": ["a", "b", "c"],
            "balance": [50, 120, 30],
        }
    )

    filtered = apply_nl_filter(df, "users with balance greater than 100")
    assert filtered.iloc[0]["user"] == "b"


def test_apply_nl_filter_contains_and():
    df = pd.DataFrame(
        {
            "name": ["Alice Smith", "Bob Jones", "Carol Smith"],
            "status": ["active", "active", "inactive"],
        }
    )

    filtered = apply_nl_filter(df, "show rows where name contains smith and status equals active")
    assert len(filtered) == 1
    assert filtered.iloc[0]["name"] == "Alice Smith"
