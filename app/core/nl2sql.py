from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import asdict, dataclass
from typing import Any

import requests
import sqlglot
from sqlalchemy import select
from sqlglot import exp

from app.core.db import session_scope
from app.core.llm import LLM_PROVIDER
from app.core.models import Feed, FeedVersion, Transform, TransformVersion
from app.core.rag import format_context, search
from app.core.redis_client import redis_sync
from app.core.transforms import TransformDefinition

RECENT_KEY = "dawn:nl2sql:recent_questions"


@dataclass(slots=True)
class TableManifest:
    name: str
    columns: list[str]
    source: str
    primary_keys: list[str]
    foreign_keys: list[dict[str, Any]]
    description: str | None = None
    kind: str = "feed"


def _load_recent_questions(limit: int = 10) -> list[str]:
    raw = redis_sync.get(RECENT_KEY)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    return [str(q) for q in data[:limit]]


def _record_question(question: str, max_entries: int = 50) -> None:
    current = _load_recent_questions(max_entries)
    updated = [question] + [q for q in current if q != question]
    redis_sync.set(RECENT_KEY, json.dumps(updated[:max_entries]))


def _manifest_from_feed(feed: Feed, version: FeedVersion) -> TableManifest:
    schema = version.schema_ or {}
    columns = [str(col.get("name")) for col in schema.get("columns", []) if col.get("name")]
    return TableManifest(
        name=feed.identifier,
        columns=columns,
        source=f"feed:{feed.identifier}:v{version.version}",
        primary_keys=[str(pk) for pk in schema.get("primary_keys", [])],
        foreign_keys=schema.get("foreign_keys", []),
        description=feed.name,
        kind="feed",
    )


def _manifest_from_transform(
    transform: Transform, version: TransformVersion
) -> TableManifest | None:
    definition_raw = version.definition or {}
    if not isinstance(definition_raw, dict):
        return None
    try:
        definition = TransformDefinition.model_validate(definition_raw)
    except Exception:  # noqa: BLE001
        return None
    columns: list[str] = []
    dry_run = version.dry_run_report or {}
    previews = dry_run.get("preview_after")
    if isinstance(previews, list) and previews:
        sample = previews[0]
        if isinstance(sample, dict):
            columns = list(sample.keys())
    return TableManifest(
        name=definition.target_table,
        columns=columns,
        source=f"transform:{transform.name}:v{version.version}",
        primary_keys=definition.unique_key or [],
        foreign_keys=[],
        description=transform.description,
        kind="transform",
    )


def build_manifest(feed_identifiers: list[str] | None = None) -> list[TableManifest]:
    manifests: list[TableManifest] = []

    with session_scope() as s:
        feed_stmt = (
            select(Feed, FeedVersion)
            .join(FeedVersion, Feed.id == FeedVersion.feed_id)
            .order_by(Feed.id, FeedVersion.version.desc())
        )
        if feed_identifiers:
            feed_stmt = feed_stmt.where(Feed.identifier.in_(feed_identifiers))
        feed_rows = s.execute(feed_stmt).all()

        seen_feed_ids: set[int] = set()
        for feed, version in feed_rows:
            if feed.id in seen_feed_ids:
                continue
            seen_feed_ids.add(feed.id)
            manifests.append(_manifest_from_feed(feed, version))

        transform_stmt = (
            select(Transform, TransformVersion)
            .join(TransformVersion, Transform.id == TransformVersion.transform_id)
            .order_by(Transform.id, TransformVersion.version.desc())
        )
        if feed_identifiers and seen_feed_ids:
            transform_stmt = transform_stmt.where(Transform.feed_id.in_(list(seen_feed_ids)))
        transform_rows = s.execute(transform_stmt).all()
        seen_transform_ids: set[int] = set()
        for transform, version in transform_rows:
            if transform.id in seen_transform_ids:
                continue
            seen_transform_ids.add(transform.id)
            manifest = _manifest_from_transform(transform, version)
            if manifest:
                manifests.append(manifest)

    return manifests


def _schema_block(manifest: list[TableManifest]) -> str:
    lines: list[str] = []
    for table in manifest:
        cols = ", ".join(table.columns) if table.columns else "(columns unknown)"
        pk = ", ".join(table.primary_keys) if table.primary_keys else "none"
        lines.append(f"- {table.name} [{table.kind}] — columns: {cols}; primary keys: {pk}.")
    return "\n".join(lines)


def _recent_block(questions: list[str]) -> str:
    if not questions:
        return "(no recent questions)"
    return "\n".join(f"- {q}" for q in questions)


def _rag_block(question: str, k: int = 4) -> tuple[str, list[dict[str, Any]]]:
    try:
        hits = search(question, k=k)
        context = format_context(hits, limit_chars=1800)
    except Exception as exc:  # noqa: BLE001
        hits = []
        context = f"RAG unavailable: {exc}"
    return context, hits


def _prompt(
    question: str, manifest: list[TableManifest], recent: list[str], rag_context: str
) -> str:
    schema_text = _schema_block(manifest)
    recent_text = _recent_block(recent)
    guidance = textwrap.dedent(
        f"""
        You convert natural-language analytics questions into SQL.
        Use ONLY the tables and columns listed below. Avoid guessing names.
        Output a single SQL statement, no narration, no markdown fences.
        Prefer safe read-only queries (`SELECT`, `WITH`).
        Tables available:
        {schema_text}

        Recent questions (for context):
        {recent_text}

        Retrieved documentation:
        {rag_context or '(none)'}

        Question: {question}
        """
    ).strip()
    return guidance


def _call_ollama(prompt: str) -> str:
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    try:
        resp = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("response", "")).strip()
    except Exception as exc:  # noqa: BLE001
        return f"SELECT '-- ollama error: {exc}' AS error;"


def _call_lmstudio(prompt: str) -> str:
    base = os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234").rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    payload = {
        "model": os.getenv("OPENAI_MODEL", "mistral-7b-instruct-v0.3"),
        "messages": [
            {"role": "system", "content": "Return SQL only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', 'lm-studio')}",
    }
    try:
        resp = requests.post(f"{base}/chat/completions", json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        choices = data.get("choices") or []
        if not choices:
            return "SELECT '-- lmstudio empty response' AS error;"
        content = choices[0].get("message", {}).get("content", "")
        return str(content).strip()
    except Exception as exc:  # noqa: BLE001
        return f"SELECT '-- lmstudio error: {exc}' AS error;"


def _call_openai(prompt: str) -> str:
    try:
        from openai import OpenAI

        client = OpenAI()
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return SQL only. No commentary."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        content = resp.choices[0].message.content
        return str(content).strip() if content else ""
    except Exception as exc:  # noqa: BLE001
        return f"SELECT '-- openai error: {exc}' AS error;"


def _call_stub(manifest: list[TableManifest]) -> str:
    table = manifest[0].name if manifest else "dual"
    return f"SELECT * FROM {table} LIMIT 50;"


def generate_sql(prompt: str, manifest: list[TableManifest]) -> str:
    if LLM_PROVIDER == "ollama":
        return _call_ollama(prompt)
    if LLM_PROVIDER == "openai":
        return _call_openai(prompt)
    if LLM_PROVIDER == "lmstudio":
        return _call_lmstudio(prompt)
    return _call_stub(manifest)


def _clean_sql(sql_text: str) -> str:
    sql_text = sql_text.strip()
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", sql_text, re.IGNORECASE | re.DOTALL)
    if fence_match:
        sql_text = fence_match.group(1).strip()
    sql_text = sql_text.split("-- SQL:", 1)[0].strip()
    return sql_text


def _manifest_lookup(manifest: list[TableManifest]) -> dict[str, TableManifest]:
    return {table.name.lower(): table for table in manifest}


def validate_sql(
    sql_text: str,
    manifest: list[TableManifest],
    *,
    allow_writes: bool = False,
    dialect: str = "postgres",
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    tables_used: list[str] = []
    columns_used: list[str] = []

    lookup = _manifest_lookup(manifest)

    try:
        statements = sqlglot.parse(sql_text, read=dialect)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "errors": [f"SQL parse error: {exc}"],
            "warnings": warnings,
            "tables": tables_used,
            "columns": columns_used,
        }

    if len(statements) != 1:
        errors.append("Only a single SQL statement is allowed.")

    statement = statements[0]
    if (
        isinstance(statement, exp.Insert | exp.Update | exp.Delete | exp.Command)
        and not allow_writes
    ):
        errors.append("Write operations require allow_writes=True.")
    elif not allow_writes and hasattr(statement, "is_select") and not statement.is_select:
        warnings.append("Statement is not a typical read-only query.")

    # collect tables
    for table in statement.find_all(exp.Table):
        name = table.name
        if not name:
            continue
        tables_used.append(name)
        if name.lower() not in lookup:
            errors.append(f"Unknown table referenced: {name}")

    # collect columns
    for column in statement.find_all(exp.Column):
        if column.name == "*":
            continue
        table_name = (column.table or "").lower()
        lookup_table = lookup.get(table_name) if table_name else None
        if lookup_table and column.name not in lookup_table.columns:
            errors.append(f"Column {column.name} not found in table {lookup_table.name}")
        elif not lookup_table:
            # Attempt to match column across manifest when unqualified
            matches = [t for t in manifest if column.name in t.columns]
            if not matches:
                errors.append(f"Unknown column referenced: {column.name}")
            elif len(matches) > 1:
                warnings.append(
                    f"Column {column.name} is ambiguous across tables {[t.name for t in matches]}"
                )
        columns_used.append(column.name if not table_name else f"{table_name}.{column.name}")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "tables": sorted(set(tables_used)),
        "columns": sorted(set(columns_used)),
    }


def explain_stub(sql_text: str, dialect: str = "postgres") -> str:
    return f"EXPLAIN is not run in dev mode (dialect={dialect})."


def nl_to_sql(
    question: str,
    *,
    feed_identifiers: list[str] | None = None,
    allow_writes: bool = False,
    dialect: str = "postgres",
    explain: bool = False,
) -> dict[str, Any]:
    manifest = build_manifest(feed_identifiers)
    recent = _load_recent_questions()
    rag_context, hits = _rag_block(question)
    prompt = _prompt(question, manifest, recent, rag_context)
    raw_sql = generate_sql(prompt, manifest)
    sql_text = _clean_sql(raw_sql)
    validation = validate_sql(sql_text, manifest, allow_writes=allow_writes, dialect=dialect)
    explain_plan = explain_stub(sql_text, dialect) if explain and validation.get("ok") else None

    if validation.get("ok"):
        _record_question(question)

    return {
        "sql": sql_text,
        "prompt": prompt,
        "manifest": [asdict(table) for table in manifest],
        "validation": validation,
        "citations": {
            "tables": validation.get("tables", []),
            "columns": validation.get("columns", []),
            "context": hits,
        },
        "explain": explain_plan,
        "recent_questions": recent,
    }
