from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

import pandas as pd

ConditionOp = Literal["eq", "neq", "gt", "gte", "lt", "lte", "contains"]


@dataclass
class Condition:
    column: str
    op: ConditionOp
    value: object

    def to_mask(self, df: pd.DataFrame) -> pd.Series:
        series = df[self.column]
        if self.op == "contains":
            return series.astype(str).str.contains(str(self.value), case=False, na=False)
        if pd.api.types.is_datetime64_any_dtype(series):
            series = pd.to_datetime(series, errors="coerce")
            try:
                comp_value = pd.to_datetime(self.value)
            except Exception:  # noqa: BLE001
                comp_value = pd.NaT
        else:
            comp_value = self.value
        if self.op == "eq":
            if pd.api.types.is_string_dtype(series) or series.dtype == object:
                return series.astype(str).str.casefold() == str(comp_value).casefold()
            return series == comp_value
        if self.op == "neq":
            if pd.api.types.is_string_dtype(series) or series.dtype == object:
                return series.astype(str).str.casefold() != str(comp_value).casefold()
            return series != comp_value
        if self.op == "gt":
            return series > comp_value
        if self.op == "gte":
            return series >= comp_value
        if self.op == "lt":
            return series < comp_value
        if self.op == "lte":
            return series <= comp_value
        raise ValueError(f"Unsupported operator: {self.op}")


_OP_PATTERNS: list[tuple[str, ConditionOp]] = [
    ("greater than or equal to", "gte"),
    ("at least", "gte"),
    ("no less than", "gte"),
    ("less than or equal to", "lte"),
    ("at most", "lte"),
    ("no more than", "lte"),
    ("greater than", "gt"),
    ("more than", "gt"),
    ("over", "gt"),
    ("less than", "lt"),
    ("under", "lt"),
    ("below", "lt"),
    ("does not equal", "neq"),
    ("not equal to", "neq"),
    ("not", "neq"),
    ("equals", "eq"),
    ("equal to", "eq"),
    ("is", "eq"),
    ("=", "eq"),
    ("==", "eq"),
    ("contains", "contains"),
    ("includes", "contains"),
]

_NUMERIC_OPS: tuple[ConditionOp, ...] = ("gt", "gte", "lt", "lte")


def _normalize(text: str) -> str:
    text = text.lower()
    text = text.replace("_", " ")
    text = re.sub(r"[^\w\s\.%-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _column_map(columns: Iterable[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for col in columns:
        mapping[_normalize(col)] = col
    return dict(sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True))


def _heuristic_column(segment: str, column_lookup: dict[str, str]) -> str | None:
    words = set(segment.split())
    if not words:
        return None

    status_tokens = {"resolved", "unresolved", "open", "closed", "pending", "escalated", "active"}
    status_hints = ("status", "state", "resolution", "outcome", "stage")
    if words & status_tokens:
        for norm_name, original in column_lookup.items():
            if any(hint in norm_name for hint in status_hints):
                return original

    owner_tokens = {"owner", "assignee", "agent", "handler"}
    owner_hints = ("owner", "assignee", "agent", "handler", "resolver")
    if words & owner_tokens:
        for norm_name, original in column_lookup.items():
            if any(hint in norm_name for hint in owner_hints):
                return original

    priority_tokens = {"urgent", "priority", "high", "medium", "low", "severity"}
    priority_hints = ("priority", "severity", "impact")
    if words & priority_tokens:
        for norm_name, original in column_lookup.items():
            if any(hint in norm_name for hint in priority_hints):
                return original

    return None


def _heuristic_value(segment: str, column_name: str) -> object | None:
    tokens = segment.split()
    if not tokens:
        return None
    lower_column = column_name.lower()
    if any(hint in lower_column for hint in ("status", "state", "resolution", "stage")):
        status_map = {
            "resolved": "resolved",
            "unresolved": "unresolved",
            "pending": "pending",
            "open": "open",
            "closed": "closed",
            "escalated": "escalated",
            "active": "active",
        }
        for token in reversed(tokens):
            token_clean = token.strip().lower()
            if token_clean in status_map:
                return status_map[token_clean]
        # handle phrases like "yet to be resolved"
        for key, value in status_map.items():
            if key in segment:
                return value
    return None


def _to_number(value: str) -> object:
    value = value.strip()
    try:
        if "%" in value:
            return float(value.replace("%", "")) / 100.0
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value.strip("'\" ")


def _extract_value(text: str) -> object:
    match = re.search(r"[\"']([^\"']+)[\"']", text)
    if match:
        return match.group(1)
    match = re.search(r"-?\d+(?:\.\d+)?%?", text)
    if match:
        return _to_number(match.group(0))
    return text.strip()


def _parse_condition(segment: str, columns: Iterable[str]) -> Condition | None:
    segment = _normalize(segment)
    column_lookup = _column_map(columns)
    column_selected = None
    for norm_name, original_name in column_lookup.items():
        if norm_name and norm_name in segment:
            column_selected = original_name
            segment = segment.replace(norm_name, "").strip()
            break
    if not column_selected:
        column_selected = _heuristic_column(segment, column_lookup)
    if not column_selected:
        return None
    op_code: ConditionOp = "eq"
    for pattern, code in _OP_PATTERNS:
        if pattern in segment:
            op_code = code
            segment = segment.replace(pattern, "").strip()
            break
    value = _extract_value(segment)
    heuristic_value = _heuristic_value(segment, column_selected)
    if heuristic_value is not None:
        value = heuristic_value
    if op_code in _NUMERIC_OPS and not isinstance(value, int | float):
        value = _to_number(str(value))
    if value == "":
        return None
    return Condition(column=column_selected, op=op_code, value=value)  # type: ignore[arg-type]


def apply_nl_filter(df: pd.DataFrame, question: str) -> pd.DataFrame:
    """Apply a simple natural-language filter against a DataFrame.

    This is a rule-based translator that can later be swapped with a true LLM.
    """
    cleaned = question.lower()
    for phrase in ["show me", "all rows", "show rows", "show records"]:
        cleaned = cleaned.replace(phrase, " ")
    cleaned = cleaned.replace("?", " ")
    filler_words = [
        "all",
        "rows",
        "records",
        "users",
        "where",
        "with",
        "that have",
        "that has",
        "who have",
    ]
    for word in filler_words:
        cleaned = re.sub(rf"\b{re.escape(word)}\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        raise ValueError("Question is empty after cleaning.")

    parts = re.split(r"\b(and|or)\b", cleaned)
    conditions: list[Condition] = []
    connectors: list[str] = []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part in {"and", "or"}:
            connectors.append(part)
            continue
        condition = _parse_condition(part, df.columns)
        if condition:
            conditions.append(condition)
        else:
            raise ValueError(f"Could not understand condition: '{part}'")

    if not conditions:
        raise ValueError("No valid filter conditions found.")

    mask = conditions[0].to_mask(df)
    conn_iter = iter(connectors)
    for condition in conditions[1:]:
        connector = next(conn_iter, "and")
        cond_mask = condition.to_mask(df)
        mask = mask | cond_mask if connector == "or" else mask & cond_mask
    return df[mask]
