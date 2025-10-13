from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from typing import Any

import numpy as np
import pandas as pd

from app.core.redis_client import redis_sync

PREVIEW_ROWS = 50
CACHE_TTL_SECONDS = 60 * 60  # 1 hour


@dataclass
class TablePreview:
    name: str
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]
    shape: tuple[int, int]
    cached: bool = False
    sheet_names: list[str] | None = None


def cache_key(content: bytes, sheet: str | None) -> str:
    h = sha256(content).hexdigest()[:16]
    suffix = f":{sheet}" if sheet else ""
    return f"dawn:dev:preview:{h}{suffix}"


def _sanitize_scalar(x: Any) -> Any:
    # NaNs/NaT → None
    if x is None:
        return None
    # pandas NA / numpy nan
    if isinstance(x, pd._libs.missing.NAType):  # type: ignore[attr-defined]
        return None
    if isinstance(x, float) and (pd.isna(x) or np.isnan(x)):
        return None
    # numpy types → python types
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    if isinstance(x, np.bool_):
        return bool(x)
    # timestamps/dates → ISO 8601
    if isinstance(x, pd.Timestamp | datetime | date):
        return x.isoformat()
    return x


def _sanitize_rows(df: pd.DataFrame, max_rows: int) -> list[dict[str, Any]]:
    head = df.head(max_rows)
    # Fast path: apply over a copy to preserve original dtypes
    return [
        {str(k): _sanitize_scalar(v) for k, v in row.items()}
        for row in head.to_dict(orient="records")
    ]


def df_profile(df: pd.DataFrame) -> list[dict[str, Any]]:
    cols: list[dict[str, Any]] = []
    for c in df.columns:
        s = df[c]
        cols.append(
            {
                "name": str(c),
                "dtype": str(s.dtype),
                "non_null": int(s.notna().sum()),
                "nulls": int(s.isna().sum()),
                "sample": [str(v) for v in s.dropna().astype(str).head(3).tolist()],
            }
        )
    return cols


def preview_from_bytes(
    content: bytes, sheet_name: str | None = None, max_rows: int = PREVIEW_ROWS
) -> TablePreview:
    import json

    xl = pd.ExcelFile(BytesIO(content))
    name = sheet_name or xl.sheet_names[0]
    key = cache_key(content, name)
    cached = redis_sync.get(key)
    if cached:
        obj = json.loads(cached)
        obj["cached"] = True
        return TablePreview(**obj)

    df = xl.parse(name)

    rows = _sanitize_rows(df, max_rows=max_rows)
    columns = df_profile(df)
    table = TablePreview(
        name=name,
        columns=columns,
        rows=rows,
        shape=(df.shape[0], df.shape[1]),
        cached=False,
        sheet_names=xl.sheet_names,
    )

    # Cache as JSON-safe dict
    redis_sync.setex(key, CACHE_TTL_SECONDS, json.dumps(asdict(table)))
    return table
