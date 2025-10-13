from __future__ import annotations

from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.models import DQRule, FeedVersion


def sync_auto_rules(
    session: Session,
    feed_version: FeedVersion,
    *,
    schema_payload: dict[str, Any],
) -> None:
    """Regenerate automatic data-quality rules for the given feed version."""
    session.execute(
        delete(DQRule).where(
            DQRule.feed_version_id == feed_version.id,
            DQRule.is_manual.is_(False),
        )
    )

    rules: list[DQRule] = []

    row_count = feed_version.row_count or 0
    if row_count > 0:
        minimum_rows = max(1, int(row_count * 0.9))
        rules.append(
            DQRule(
                feed_version_id=feed_version.id,
                column_name=None,
                rule_type="row_count_min",
                params={"min_rows": minimum_rows},
                is_manual=False,
                description=f"Ensure at least {minimum_rows} rows (90% of profiled count).",
                severity="warn",
            )
        )

    columns = schema_payload.get("columns") if isinstance(schema_payload, dict) else []
    for column in columns or []:
        name = column.get("name")
        if not name:
            continue
        null_percent = float(column.get("null_percent", 0.0))
        threshold = min(100.0, null_percent + 10.0)
        rules.append(
            DQRule(
                feed_version_id=feed_version.id,
                column_name=str(name),
                rule_type="null_ratio_max",
                params={"max_null_percent": threshold},
                is_manual=False,
                description=f"{name} null ratio should remain below {threshold:.1f}%.",
                severity="warn",
            )
        )

        if column.get("is_primary_key_candidate"):
            rules.append(
                DQRule(
                    feed_version_id=feed_version.id,
                    column_name=str(name),
                    rule_type="uniqueness",
                    params={"max_duplicates": 0},
                    is_manual=False,
                    description=f"{name} should remain unique (primary key candidate).",
                    severity="error",
                )
            )

        dtype = str(column.get("dtype", "")).lower()
        if any(token in dtype for token in ("datetime", "date")):
            rules.append(
                DQRule(
                    feed_version_id=feed_version.id,
                    column_name=str(name),
                    rule_type="datetime_parseable",
                    params={},
                    is_manual=False,
                    description=f"{name} should contain parseable datetimes.",
                    severity="warn",
                )
            )

    for rule in rules:
        session.add(rule)
