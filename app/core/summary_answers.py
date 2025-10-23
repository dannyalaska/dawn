from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.core.db import session_scope
from app.core.models import Upload

_MOST_KEYWORDS = ("most", "highest", "largest", "top", "greatest")
_LEAST_KEYWORDS = ("fewest", "least", "lowest", "smallest")
_FAST_KEYWORDS = ("fastest", "quickest", "shortest", "lowest", "best")
_SLOW_KEYWORDS = ("slowest", "longest", "highest", "worst")


def source_to_file_sheet(source: str) -> tuple[str, str] | None:
    base = source
    if base.endswith(":summary"):
        base = base.rsplit(":", 1)[0]
    parts = base.split(":", 1)
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


def load_summary_for_source(source: str) -> dict[str, Any] | None:
    parsed = source_to_file_sheet(source)
    if not parsed:
        return None
    filename, sheet = parsed
    with session_scope() as session:
        stmt = (
            select(Upload)
            .where(Upload.filename == filename, Upload.sheet == sheet)
            .order_by(Upload.uploaded_at.desc())
            .limit(1)
        )
        rec = session.execute(stmt).scalars().first()
        if rec and rec.summary:
            return dict(rec.summary)
    return None


def _match_column(
    question_lower: str, insights: dict[str, Any], relationships: dict[str, str]
) -> str | None:
    for col, role in relationships.items():
        role_lower = (role or "").lower()
        col_lower = col.lower()
        if role_lower and role_lower in question_lower:
            return col
        if col_lower in question_lower:
            return col
    for col in insights:
        if col.lower() in question_lower:
            return col
    if any(word in question_lower for word in ("ticket", "resolve", "assigned", "who")):
        for col, role in relationships.items():
            if (role or "").lower() in {"resolver", "owner", "assignee", "agent"}:
                return col
    return None


def direct_answer_from_summary(question: str, summary: dict[str, Any]) -> str | None:
    q = question.lower()
    insights = summary.get("insights") or {}
    relationships = {str(k): str(v) for k, v in (summary.get("relationships") or {}).items()}
    aggregates = summary.get("aggregates") or []

    if insights and any(keyword in q for keyword in _MOST_KEYWORDS + _LEAST_KEYWORDS):
        column = _match_column(q, insights, relationships)
        if column and column in insights:
            entries = insights.get(column) or []
            if entries:
                descending = not any(keyword in q for keyword in _LEAST_KEYWORDS)
                descriptor = "most" if descending else "fewest"
                sorted_entries = sorted(entries, key=lambda e: int(e.get("count", 0)), reverse=True)
                if not descending:
                    sorted_entries = list(reversed(sorted_entries))
                top_entry = sorted_entries[0]
                others = ", ".join(
                    f"{entry['label']} ({entry['count']})" for entry in sorted_entries[1:3]
                )
                headline = (
                    f"{top_entry['label']} handled the {descriptor} tickets ({top_entry['count']})."
                )
                if others:
                    headline += f" Next: {others}."
                return headline

    target: str | None = None
    speed_descriptor: str | None = None
    if any(keyword in q for keyword in _FAST_KEYWORDS):
        target = "best"
        speed_descriptor = "fastest"
    elif any(keyword in q for keyword in _SLOW_KEYWORDS):
        target = "worst"
        speed_descriptor = "slowest"

    if target and aggregates:
        for agg in aggregates:
            group = str(agg.get("group", ""))
            value = str(agg.get("value", ""))
            role = (relationships.get(group) or "").lower()
            if not group:
                continue
            if group.lower() in q or (role and role in q) or (role == "resolver" and "ticket" in q):
                entries = agg.get(target) or []
                if entries:
                    entry = entries[0]
                    metric_value = entry.get("value")
                    if isinstance(metric_value, (int | float)):
                        value_str = f"{metric_value:.2f}"
                    else:
                        value_str = str(metric_value)
                    value_name = str(value or "metric")
                    nice_value = value_name.replace("_", " ")
                    descriptor_label = speed_descriptor or "fastest"
                    answer = (
                        f"{entry.get('label')} is the {descriptor_label} for {nice_value}"
                        f" ({value_str})."
                    )
                    peers = ", ".join(
                        (
                            f"{e['label']} ({e['value']:.2f})"
                            if isinstance(e.get("value"), (int | float))
                            else f"{e['label']} ({e.get('value')})"
                        )
                        for e in entries[1:3]
                    )
                    if peers:
                        answer += f" Next: {peers}."
                    return answer

    return None
