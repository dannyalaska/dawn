from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any, TypedDict, cast

import sqlglot
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlglot import exp

from app.core.backend_connectors import (
    BackendConnectorError,
    get_schema_grants,
    list_backend_tables,
)
from app.core.chat_models import StubChatModel, get_chat_model
from app.core.config import settings
from app.core.db import session_scope
from app.core.models import (
    BackendConnection,
    Feed,
    FeedDataset,
    FeedVersion,
    Transform,
    TransformVersion,
)
from app.core.rag import format_context, search
from app.core.redis_client import redis_sync
from app.core.transforms import TransformDefinition

RECENT_KEY = "dawn:nl2sql:recent_questions"


class BackendConn(TypedDict):
    id: int
    name: str
    kind: str
    config: dict[str, Any]


def _recent_key(user_id: str) -> str:
    return f"{RECENT_KEY}:{user_id}"


@dataclass(slots=True)
class TableManifest:
    name: str
    columns: list[str]
    source: str
    primary_keys: list[str]
    foreign_keys: list[dict[str, Any]]
    description: str | None = None
    kind: str = "feed"
    schema: str | None = None
    table: str | None = None
    connection_id: int | None = None
    dialect: str | None = None


def _ensure_int_user_id(value: str | int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
        raise ValueError("user_id must be numeric for manifest generation") from exc


def _load_recent_questions(limit: int = 10, *, user_id: str) -> list[str]:
    raw = redis_sync.get(_recent_key(user_id))
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(data, list):
        return []
    return [str(q) for q in data[:limit]]


def _record_question(question: str, *, user_id: str, max_entries: int = 50) -> None:
    current = _load_recent_questions(max_entries, user_id=user_id)
    updated = [question] + [q for q in current if q != question]
    redis_sync.set(_recent_key(user_id), json.dumps(updated[:max_entries]))


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
        table=feed.identifier,
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
        table=definition.target_table,
    )


def build_manifest(
    *,
    user_id: str | int,
    feed_identifiers: list[str] | None = None,
) -> list[TableManifest]:
    manifests: list[TableManifest] = []
    numeric_user = _ensure_int_user_id(user_id)
    with session_scope() as s:
        feed_stmt = (
            select(Feed, FeedVersion)
            .join(FeedVersion, Feed.id == FeedVersion.feed_id)
            .where(Feed.user_id == numeric_user)
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
            .where(Transform.user_id == numeric_user)
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

    manifests.extend(_feed_dataset_manifests(numeric_user))
    manifests.extend(_backend_table_manifests(numeric_user))
    return manifests


def _backend_table_manifests(user_id: int) -> list[TableManifest]:
    manifests: list[TableManifest] = []
    with session_scope() as session:
        rows = (
            session.execute(select(BackendConnection).where(BackendConnection.user_id == user_id))
            .scalars()
            .all()
        )
        connections: list[BackendConn] = [
            {
                "id": conn.id,
                "name": conn.name,
                "kind": conn.kind,
                "config": dict(conn.config or {}),
            }
            for conn in rows
        ]
    for connection in connections:
        config = connection["config"]
        schemas = get_schema_grants(config)
        if not schemas:
            continue
        try:
            tables = list_backend_tables(connection["kind"], config, schemas)
        except BackendConnectorError:
            continue
        for table in tables:
            schema_name = table.get("schema")
            table_name = table.get("table")
            if not schema_name or not table_name:
                continue
            qualified = f"{schema_name}.{table_name}"
            manifests.append(
                TableManifest(
                    name=qualified,
                    columns=table.get("columns", []),
                    source=f"backend:{connection['id']}:{qualified}",
                    primary_keys=table.get("primary_keys", []),
                    foreign_keys=[],
                    description=f"{connection['name']} ({connection['kind']})",
                    kind=connection["kind"],
                    schema=schema_name,
                    table=table_name,
                    connection_id=connection["id"],
                )
            )
    return manifests


def _feed_dataset_manifests(user_id: int) -> list[TableManifest]:
    manifests: list[TableManifest] = []
    with session_scope() as session:
        rows = session.execute(
            select(FeedDataset, Feed)
            .join(Feed, FeedDataset.feed_id == Feed.id)
            .where(Feed.user_id == user_id)
        ).all()
        datasets = [
            {
                "table_name": dataset.table_name,
                "schema_name": dataset.schema_name,
                "columns": list(dataset.columns or []),
                "id": dataset.id,
                "feed_name": feed.name,
            }
            for dataset, feed in rows
        ]
    for entry in datasets:
        schema_name = entry["schema_name"] or "public"
        manifests.append(
            TableManifest(
                name=entry["table_name"],
                columns=entry["columns"],
                source=f"feed_dataset:{entry['id']}",
                primary_keys=[],
                foreign_keys=[],
                description=f"{entry['feed_name']} materialized",
                kind="feed_table",
                schema=schema_name,
                table=entry["table_name"],
                connection_id=entry["id"],
            )
        )
    return manifests


def _schema_block(manifest: list[TableManifest]) -> str:
    lines: list[str] = []
    for table in manifest:
        cols = ", ".join(table.columns) if table.columns else "(columns unknown)"
        pk = ", ".join(table.primary_keys) if table.primary_keys else "none"
        context = table.kind
        if table.schema:
            context = f"{table.kind} · schema {table.schema}"
        lines.append(f"- {table.name} [{context}] — columns: {cols}; primary keys: {pk}.")
    return "\n".join(lines)


def _recent_block(questions: list[str]) -> str:
    if not questions:
        return "(no recent questions)"
    return "\n".join(f"- {q}" for q in questions)


def _rag_block(
    question: str, k: int = 4, user_id: str = "default"
) -> tuple[str, list[dict[str, Any]]]:
    try:
        hits = search(question, k=k, user_id=user_id)
        context = format_context(hits, limit_chars=1800)
    except Exception as exc:  # noqa: BLE001
        hits = []
        context = f"RAG unavailable: {exc}"
    return context, hits


def _prompt(
    question: str,
    manifest: list[TableManifest],
    recent: list[str],
    rag_context: str,
    intent: dict[str, Any] | None = None,
) -> str:
    schema_text = _schema_block(manifest)
    recent_text = _recent_block(recent)
    intent_text = json.dumps(intent, ensure_ascii=True, indent=2) if intent else "(none)"
    guidance = textwrap.dedent(
        f"""
        You convert natural-language analytics questions into SQL.
        Use ONLY the tables and columns listed below. Avoid guessing names.
        Preserve exact column names; if a column has spaces or mixed case, wrap it in double quotes.
        Output a single SQL statement, no narration, no markdown fences.
        Prefer safe read-only queries (`SELECT`, `WITH`).
        If asked about duplicates, use GROUP BY with HAVING COUNT(*) > 1.
        Tables available:
        {schema_text}

        Recent questions (for context):
        {recent_text}

        Retrieved documentation:
        {rag_context or "(none)"}

        Interpretation (may be imperfect):
        {intent_text}

        Question: {question}
        """
    ).strip()
    return guidance


def _normalize_identifier(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _needs_quoting(name: str) -> bool:
    return re.fullmatch(r"[a-z_][a-z0-9_]*", name) is None


def _normalized_column_maps(
    manifest: list[TableManifest],
) -> tuple[dict[str, dict[str, list[str]]], dict[str, list[str]]]:
    by_table: dict[str, dict[str, list[str]]] = {}
    global_map: dict[str, list[str]] = {}
    for table in manifest:
        table_map: dict[str, list[str]] = {}
        for column in table.columns:
            norm = _normalize_identifier(column)
            table_map.setdefault(norm, [])
            if column not in table_map[norm]:
                table_map[norm].append(column)
            global_map.setdefault(norm, [])
            if column not in global_map[norm]:
                global_map[norm].append(column)
        by_table[table.name] = table_map
    return by_table, global_map


def _normalize_sql_columns(
    sql_text: str, manifest: list[TableManifest], *, dialect: str
) -> tuple[str, list[str]]:
    warnings: list[str] = []
    try:
        statement = sqlglot.parse_one(sql_text, read=dialect)
    except Exception:
        return sql_text, warnings

    lookup = _manifest_lookup(manifest)
    table_maps, global_map = _normalized_column_maps(manifest)
    alias_map: dict[str, TableManifest] = {}

    for table in statement.find_all(exp.Table):
        name = table.name
        if not name:
            continue
        db = table.db
        key = f"{db}.{name}".lower() if db else name.lower()
        table_manifest = lookup.get(key) or lookup.get(name.lower())
        if not table_manifest:
            continue
        alias = table.alias_or_name
        if alias:
            alias_map[alias.lower()] = table_manifest

    for column in statement.find_all(exp.Column):
        if column.name == "*":
            continue
        column_name = column.name
        if not column_name:
            continue
        table_ref = (column.table or "").lower()
        manifest_table: TableManifest | None = None
        if table_ref:
            manifest_table = alias_map.get(table_ref) or lookup.get(table_ref)
        if manifest_table:
            if column_name in manifest_table.columns:
                continue
            norm = _normalize_identifier(column_name)
            candidates = table_maps.get(manifest_table.name, {}).get(norm, [])
            if len(candidates) == 1:
                canonical = candidates[0]
                if canonical != column_name:
                    column.set(
                        "this",
                        exp.Identifier(this=canonical, quoted=_needs_quoting(canonical)),
                    )
                    warnings.append(
                        f'Normalized column {column_name} -> "{canonical}" in {manifest_table.name}'
                    )
            continue

        norm = _normalize_identifier(column_name)
        candidates = global_map.get(norm, [])
        if len(candidates) == 1:
            canonical = candidates[0]
            if canonical != column_name:
                column.set(
                    "this",
                    exp.Identifier(this=canonical, quoted=_needs_quoting(canonical)),
                )
                warnings.append(f'Normalized column {column_name} -> "{canonical}"')

    try:
        normalized = statement.sql(dialect=dialect)
    except Exception:
        return sql_text, warnings
    return normalized, warnings


def _quote_unquoted_columns(sql_text: str, manifest: list[TableManifest]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    columns_to_quote: list[str] = []
    for table in manifest:
        for column in table.columns:
            if _needs_quoting(column):
                columns_to_quote.append(column)

    if not columns_to_quote:
        return sql_text, warnings

    # Prefer longer names first to avoid partial replacements.
    columns_to_quote = sorted(set(columns_to_quote), key=len, reverse=True)
    updated = sql_text
    for column in columns_to_quote:
        quoted = f'"{column}"'
        pattern = rf'(?<!")(?<![\\w]){re.escape(column)}(?![\\w])(?!")'
        if re.search(pattern, updated):
            updated = re.sub(pattern, quoted, updated)
            warnings.append(f'Quoted column {column} -> "{column}"')
    return updated, warnings


def _repair_sql(
    sql_text: str, manifest: list[TableManifest], *, dialect: str
) -> tuple[str, list[str]]:
    try:
        sqlglot.parse_one(sql_text, read=dialect)
        return sql_text, []
    except Exception:
        pass

    repaired, warnings = _quote_unquoted_columns(sql_text, manifest)
    if repaired == sql_text:
        return sql_text, warnings
    try:
        sqlglot.parse_one(repaired, read=dialect)
        return repaired, warnings
    except Exception:
        return repaired, warnings


PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You convert natural-language analytics questions into SQL. Return a single SQL "
            "statement with no commentary, explanations, or markdown fences.",
        ),
        ("human", "{prompt}"),
    ]
)

INTENT_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You interpret analytics questions. Return ONLY valid JSON with no extra text.",
        ),
        ("human", "{prompt}"),
    ]
)


class NL2SQLState(TypedDict, total=False):
    question: str
    manifest: list[TableManifest]
    recent: list[str]
    rag_context: str
    hits: list[dict[str, Any]]
    prompt: str
    intent: dict[str, Any]
    raw_sql: str
    sql: str
    user_id: str
    k: int


def _call_stub(manifest: list[TableManifest]) -> str:
    table = manifest[0].name if manifest else "dual"
    return f"SELECT * FROM {table} LIMIT 50;"


def _intent_prompt(question: str, manifest: list[TableManifest]) -> str:
    schema_text = _schema_block(manifest)
    return textwrap.dedent(
        f"""
        You interpret a user's analytics question and return JSON only.
        Use this schema to map column and table names exactly when possible.
        Schema:
        {schema_text}

        Return JSON with:
        - task: short verb like "duplicates", "count", "list", "aggregate", "trend", "unknown"
        - columns: list of column names (use exact schema names if present)
        - group_by: list of column names (optional)
        - filters: list of simple filter phrases (optional)
        - time_range: string or null (optional)
        - output: short description of expected output
        - notes: any short clarifying hint for SQL generation

        Question: {question}
        """
    ).strip()


def _extract_json_block(text: str) -> str | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return match.group(0)
    return None


def _normalize_intent_columns(
    intent: dict[str, Any], manifest: list[TableManifest]
) -> dict[str, Any]:
    _, global_map = _normalized_column_maps(manifest)
    updated = dict(intent)

    def normalize_list(values: Any) -> list[str]:
        if values is None:
            return []
        if isinstance(values, str):
            values_list = [values]
        elif isinstance(values, list):
            values_list = [str(v) for v in values if v is not None]
        else:
            values_list = [str(values)]
        out: list[str] = []
        for item in values_list:
            norm = _normalize_identifier(item)
            candidates = global_map.get(norm, [])
            if len(candidates) == 1:
                out.append(candidates[0])
            else:
                out.append(item)
        return out

    for key in ("columns", "group_by"):
        updated[key] = normalize_list(updated.get(key))
    return updated


def _interpret_stub(question: str, manifest: list[TableManifest]) -> dict[str, Any]:
    lowered = question.lower()
    task = "unknown"
    if "duplicate" in lowered or "dup" in lowered:
        task = "duplicates"
    elif "count" in lowered:
        task = "count"
    elif "list" in lowered or "show" in lowered:
        task = "list"
    intent = {
        "task": task,
        "columns": [],
        "group_by": [],
        "filters": [],
        "time_range": None,
        "output": "",
        "notes": "",
    }
    return _normalize_intent_columns(intent, manifest)


def _interpret_question(question: str, manifest: list[TableManifest], model: Any) -> dict[str, Any]:
    prompt = _intent_prompt(question, manifest)
    parser = StrOutputParser()
    chain = INTENT_PROMPT_TEMPLATE | model | parser
    try:
        raw = chain.invoke({"prompt": prompt}).strip()
    except Exception as exc:  # noqa: BLE001
        return {
            "task": "unknown",
            "columns": [],
            "group_by": [],
            "filters": [],
            "time_range": None,
            "output": "",
            "notes": f"intent parse error: {exc}",
        }

    payload = _extract_json_block(raw)
    if not payload:
        return {
            "task": "unknown",
            "columns": [],
            "group_by": [],
            "filters": [],
            "time_range": None,
            "output": "",
            "notes": "intent parse error: no JSON",
        }

    try:
        parsed = json.loads(payload)
    except Exception:  # noqa: BLE001
        parsed = {}

    if not isinstance(parsed, dict):
        parsed = {"notes": "intent parse error: invalid JSON"}

    return _normalize_intent_columns(parsed, manifest)


@lru_cache(maxsize=4)
def _compiled_graph(provider: str) -> Any:
    model = get_chat_model(provider)
    parser = StrOutputParser()
    graph = StateGraph(NL2SQLState)

    if isinstance(model, StubChatModel):

        def interpret_node(state: NL2SQLState) -> dict[str, Any]:
            return {"intent": _interpret_stub(state["question"], state["manifest"])}

    else:

        def interpret_node(state: NL2SQLState) -> dict[str, Any]:
            return {"intent": _interpret_question(state["question"], state["manifest"], model)}

    def prep_node(state: NL2SQLState) -> dict[str, Any]:
        k_value = cast(int, state.get("k", 4))
        user_id = state.get("user_id", "default")
        rag_context, hits = _rag_block(state["question"], k=k_value, user_id=user_id)
        prompt = _prompt(
            state["question"],
            state["manifest"],
            state.get("recent", []),
            rag_context,
            state.get("intent"),
        )
        return {"rag_context": rag_context, "hits": hits, "prompt": prompt}

    if isinstance(model, StubChatModel):

        def llm_node(state: NL2SQLState) -> dict[str, Any]:
            return {"raw_sql": _call_stub(state["manifest"])}

    else:
        chain = PROMPT_TEMPLATE | model | parser

        def llm_node(state: NL2SQLState) -> dict[str, Any]:
            try:
                sql_text = chain.invoke({"prompt": state["prompt"]}).strip()
            except Exception as exc:  # noqa: BLE001
                sql_text = f"SELECT '-- llm error: {exc}' AS error;"
            return {"raw_sql": sql_text}

    def clean_node(state: NL2SQLState) -> dict[str, Any]:
        return {"sql": _clean_sql(state.get("raw_sql", ""))}

    graph.add_node("interpret", interpret_node)
    graph.add_node("prep", prep_node)
    graph.add_node("llm", llm_node)
    graph.add_node("clean", clean_node)
    graph.set_entry_point("interpret")
    graph.add_edge("interpret", "prep")
    graph.add_edge("prep", "llm")
    graph.add_edge("llm", "clean")
    graph.add_edge("clean", END)

    return graph.compile()


def _run_graph(
    question: str, manifest: list[TableManifest], recent: list[str], *, user_id: str, k: int = 4
) -> dict[str, Any]:
    env_provider = os.getenv("LLM_PROVIDER")
    provider = (env_provider or settings.LLM_PROVIDER or "stub").lower()
    graph = _compiled_graph(provider)
    return graph.invoke(
        {
            "question": question,
            "manifest": manifest,
            "recent": recent,
            "user_id": user_id,
            "k": k,
        }
    )


def _clean_sql(sql_text: str) -> str:
    sql_text = sql_text.strip()
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", sql_text, re.IGNORECASE | re.DOTALL)
    if fence_match:
        sql_text = fence_match.group(1).strip()
    sql_text = sql_text.split("-- SQL:", 1)[0].strip()
    return sql_text


def _manifest_lookup(manifest: list[TableManifest]) -> dict[str, TableManifest]:
    lookup: dict[str, TableManifest] = {}
    for table in manifest:
        keys = {table.name.lower()}
        if table.table:
            keys.add(table.table.lower())
        if table.schema and table.table:
            keys.add(f"{table.schema.lower()}.{table.table.lower()}")
        for key in keys:
            lookup[key] = table
    return lookup


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

    statement = cast(exp.Expression, statements[0])
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
        db = table.db or ""
        key = name.lower()
        match = None
        if db:
            qualified = f"{db.lower()}.{key}"
            match = lookup.get(qualified)
        if match is None and table.catalog:
            catalog_qualified = f"{table.catalog.lower()}.{key}"
            match = lookup.get(catalog_qualified)
        if match is None:
            match = lookup.get(key)
        if match is None:
            errors.append(f"Unknown table referenced: {name if not db else f'{db}.{name}'}")
        else:
            tables_used.append(match.name)

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
    user_id: str = "default",
) -> dict[str, Any]:
    manifest = build_manifest(user_id=user_id, feed_identifiers=feed_identifiers)
    recent = _load_recent_questions(user_id=user_id)
    state = _run_graph(question, manifest, recent, user_id=user_id)
    prompt = state.get("prompt") or _prompt(
        question, manifest, recent, state.get("rag_context", ""), state.get("intent")
    )
    sql_text = state.get("sql") or _clean_sql(state.get("raw_sql", ""))
    sql_text, repair_warnings = _repair_sql(sql_text, manifest, dialect=dialect)
    sql_text, normalization_warnings = _normalize_sql_columns(sql_text, manifest, dialect=dialect)
    hits = state.get("hits", [])
    validation = validate_sql(sql_text, manifest, allow_writes=allow_writes, dialect=dialect)
    if normalization_warnings or repair_warnings:
        warnings = list(validation.get("warnings") or [])
        for warning in repair_warnings + normalization_warnings:
            if warning not in warnings:
                warnings.append(warning)
        validation["warnings"] = warnings
    explain_plan = explain_stub(sql_text, dialect) if explain and validation.get("ok") else None

    if validation.get("ok"):
        _record_question(question, user_id=user_id)

    return {
        "sql": sql_text,
        "prompt": prompt,
        "manifest": [asdict(table) for table in manifest],
        "intent": state.get("intent"),
        "validation": validation,
        "citations": {
            "tables": validation.get("tables", []),
            "columns": validation.get("columns", []),
            "context": hits,
        },
        "explain": explain_plan,
        "recent_questions": recent,
    }
