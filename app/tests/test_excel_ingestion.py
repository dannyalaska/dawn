import pandas as pd

from app.core.excel.ingestion import cache_key, df_profile


def test_df_profile_basic():
    df = pd.DataFrame({"a": [1, 2, None], "b": ["x", "y", "z"]})
    cols = df_profile(df)
    names = {c["name"] for c in cols}
    assert {"a", "b"} <= names
    a = next(c for c in cols if c["name"] == "a")
    assert a["nulls"] == 1
    assert a["non_null"] == 2


def test_cache_key_changes_with_content_and_sheet():
    c1 = b"abc"
    c2 = b"abcd"
    assert cache_key(c1, None) != cache_key(c2, None)
    assert cache_key(c1, "S1") != cache_key(c1, "S2")
