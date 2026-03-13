"""DQ execution engine — evaluates DQRules against materialized feed tables."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.core.models import DQResult, DQRule, FeedDataset

logger = logging.getLogger(__name__)

_PASS = "pass"
_FAIL = "fail"
_SKIP = "skip"


@dataclass
class RuleOutcome:
    rule_id: int
    rule_type: str
    column_name: str | None
    status: str  # pass | fail | skip
    details: dict[str, Any]


def _get_table_name(session: Session, feed_version_id: int) -> str | None:
    ds = session.scalar(select(FeedDataset).where(FeedDataset.feed_version_id == feed_version_id))
    return ds.table_name if ds else None


def _eval_row_count_min(table: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    min_rows = int(params.get("min_rows", 1))
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).fetchone()  # noqa: S608
    actual = int(row[0]) if row else 0
    if actual >= min_rows:
        return _PASS, {"actual_rows": actual, "min_rows": min_rows}
    return _FAIL, {"actual_rows": actual, "min_rows": min_rows}


def _eval_null_ratio_max(
    table: str, column: str, params: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    max_pct = float(params.get("max_null_percent", 100.0))
    safe_col = column.replace('"', "")
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f"SELECT COUNT(*) AS total,"  # noqa: S608
                f' SUM(CASE WHEN "{safe_col}" IS NULL THEN 1 ELSE 0 END) AS nulls'
                f' FROM "{table}"'
            )
        ).fetchone()
    if not row or row[0] == 0:
        return _SKIP, {"reason": "empty table"}
    total, nulls = int(row[0]), int(row[1] or 0)
    actual_pct = round(nulls / total * 100, 2)
    if actual_pct <= max_pct:
        return _PASS, {
            "actual_null_percent": actual_pct,
            "max_null_percent": max_pct,
            "nulls": nulls,
            "total": total,
        }
    return _FAIL, {
        "actual_null_percent": actual_pct,
        "max_null_percent": max_pct,
        "nulls": nulls,
        "total": total,
    }


def _eval_uniqueness(table: str, column: str, params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    max_dupes = int(params.get("max_duplicates", 0))
    safe_col = column.replace('"', "")
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                f'SELECT COUNT(*) AS total, COUNT(DISTINCT "{safe_col}") AS distinct_vals'  # noqa: S608
                f' FROM "{table}"'
            )
        ).fetchone()
    if not row or row[0] == 0:
        return _SKIP, {"reason": "empty table"}
    total, distinct = int(row[0]), int(row[1])
    duplicates = total - distinct
    if duplicates <= max_dupes:
        return _PASS, {"duplicates": duplicates, "total": total, "distinct": distinct}
    return _FAIL, {"duplicates": duplicates, "total": total, "distinct": distinct}


def _eval_datetime_parseable(table: str, column: str) -> tuple[str, dict[str, Any]]:
    """Sample up to 200 non-null values and attempt Python datetime parsing."""
    import dateutil.parser  # type: ignore[import-untyped]

    safe_col = column.replace('"', "")
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f'SELECT "{safe_col}" FROM "{table}"'  # noqa: S608
                f' WHERE "{safe_col}" IS NOT NULL LIMIT 200'
            )
        ).fetchall()
    if not rows:
        return _SKIP, {"reason": "no non-null values sampled"}

    failures = 0
    for (val,) in rows:
        try:
            dateutil.parser.parse(str(val))
        except Exception:  # noqa: BLE001
            failures += 1

    total_sampled = len(rows)
    if failures == 0:
        return _PASS, {"sampled": total_sampled, "parse_failures": 0}
    failure_pct = round(failures / total_sampled * 100, 1)
    if failure_pct > 10:
        return _FAIL, {
            "sampled": total_sampled,
            "parse_failures": failures,
            "failure_pct": failure_pct,
        }
    return _PASS, {"sampled": total_sampled, "parse_failures": failures, "failure_pct": failure_pct}


def _evaluate_rule(rule: DQRule, table: str) -> RuleOutcome:
    params = rule.params or {}
    col = rule.column_name or ""
    try:
        if rule.rule_type == "row_count_min":
            status, details = _eval_row_count_min(table, params)
        elif rule.rule_type == "null_ratio_max":
            if not col:
                return RuleOutcome(
                    rule.id, rule.rule_type, col, _SKIP, {"reason": "no column_name"}
                )
            status, details = _eval_null_ratio_max(table, col, params)
        elif rule.rule_type == "uniqueness":
            if not col:
                return RuleOutcome(
                    rule.id, rule.rule_type, col, _SKIP, {"reason": "no column_name"}
                )
            status, details = _eval_uniqueness(table, col, params)
        elif rule.rule_type == "datetime_parseable":
            if not col:
                return RuleOutcome(
                    rule.id, rule.rule_type, col, _SKIP, {"reason": "no column_name"}
                )
            status, details = _eval_datetime_parseable(table, col)
        else:
            return RuleOutcome(
                rule.id,
                rule.rule_type,
                col,
                _SKIP,
                {"reason": f"unknown rule_type: {rule.rule_type}"},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("DQ rule %d (%s) evaluation error: %s", rule.id, rule.rule_type, exc)
        status, details = _SKIP, {"error": str(exc)}

    return RuleOutcome(rule.id, rule.rule_type, col or None, status, details)


def run_dq_rules(
    feed_version_id: int,
    session: Session,
    *,
    job_run_id: int | None = None,
) -> list[RuleOutcome]:
    """
    Load all DQRules for feed_version_id, evaluate each against the materialized
    table, persist DQResult records, and return outcomes.
    """
    table = _get_table_name(session, feed_version_id)
    if not table:
        logger.warning(
            "DQ runner: no materialized table found for feed_version_id=%d", feed_version_id
        )
        return []

    rules = session.scalars(select(DQRule).where(DQRule.feed_version_id == feed_version_id)).all()

    if not rules:
        logger.info("DQ runner: no rules for feed_version_id=%d", feed_version_id)
        return []

    outcomes: list[RuleOutcome] = []
    for rule in rules:
        outcome = _evaluate_rule(rule, table)
        result = DQResult(
            rule_id=rule.id,
            job_run_id=job_run_id,
            status=outcome.status,
            details={**outcome.details, "evaluated_at": datetime.utcnow().isoformat()},
        )
        session.add(result)
        outcomes.append(outcome)

    session.flush()

    fails = [o for o in outcomes if o.status == _FAIL]
    errors = [
        o
        for o in fails
        if (r := next((r for r in rules if r.id == o.rule_id), None)) and r.severity == "error"
    ]
    logger.info(
        "DQ runner: feed_version_id=%d table=%s rules=%d pass=%d fail=%d skip=%d",
        feed_version_id,
        table,
        len(outcomes),
        sum(1 for o in outcomes if o.status == _PASS),
        len(fails),
        sum(1 for o in outcomes if o.status == _SKIP),
    )

    if errors:
        _send_dq_alert(feed_version_id, table, errors, rules)

    return outcomes


def dq_summary(outcomes: list[RuleOutcome]) -> dict[str, Any]:
    """Summarize outcomes for API response."""
    total = len(outcomes)
    if total == 0:
        return {"status": "no_rules", "pass": 0, "fail": 0, "skip": 0, "total": 0}
    fails = sum(1 for o in outcomes if o.status == _FAIL)
    skips = sum(1 for o in outcomes if o.status == _SKIP)
    passes = total - fails - skips
    overall = "pass" if fails == 0 else "fail"
    return {"status": overall, "pass": passes, "fail": fails, "skip": skips, "total": total}


def _send_dq_alert(
    feed_version_id: int,
    table: str,
    error_outcomes: list[RuleOutcome],
    all_rules: list[DQRule],
) -> None:
    import requests  # noqa: PLC0415

    from app.core.config import settings

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    lines = [f"🚨 *DAWN DQ Alert* — `{table}` (version id {feed_version_id})"]
    for o in error_outcomes[:5]:
        rule = next((r for r in all_rules if r.id == o.rule_id), None)
        desc = rule.description if rule else o.rule_type
        lines.append(f"  • FAIL: {desc}")
        for k, v in o.details.items():
            if k != "evaluated_at":
                lines.append(f"    {k}: {v}")
    if len(error_outcomes) > 5:
        lines.append(f"  …and {len(error_outcomes) - 5} more")

    msg = "\n".join(lines)
    try:
        requests.post(
            f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"},
            timeout=8,
        )
        logger.info("DQ runner: Telegram alert sent for %d error rules", len(error_outcomes))
    except Exception as exc:  # noqa: BLE001
        logger.warning("DQ runner: failed to send Telegram alert: %s", exc)
