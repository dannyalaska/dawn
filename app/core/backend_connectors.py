from __future__ import annotations

from collections import defaultdict
from contextlib import suppress
from typing import Any

import psycopg2

try:  # pragma: no cover - optional dependency
    import snowflake.connector as snowflake_connector  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    snowflake_connector = None  # type: ignore[assignment]


class BackendConnectorError(Exception):
    """Raised when a backend connection cannot be established or introspected."""


SUPPORTED_SCHEMA_BACKENDS = {"postgres", "snowflake"}
MAX_TABLES_PER_SCHEMA = 25
MAX_COLUMNS_PER_TABLE = 64


def list_backend_schemas(kind: str, config: dict[str, Any]) -> list[str]:
    """Return available schemas for the given backend connection."""
    if kind == "postgres":
        return _postgres_schemas(config)
    if kind == "snowflake":
        return _snowflake_schemas(config)
    msg = f"Schema introspection is not supported for backend kind '{kind}'."
    raise BackendConnectorError(msg)


def _postgres_schemas(config: dict[str, Any]) -> list[str]:
    required = {"host", "port", "database", "user", "password"}
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        msg = f"Postgres config is missing required fields: {', '.join(sorted(missing))}"
        raise BackendConnectorError(msg)

    conn = psycopg2.connect(
        host=config["host"],
        port=int(config["port"]),
        dbname=config["database"],
        user=config["user"],
        password=config["password"],
        connect_timeout=int(config.get("connect_timeout") or 5),
        sslmode=str(config.get("sslmode") or "prefer"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select schema_name
                from information_schema.schemata
                where schema_name not in ('pg_catalog', 'information_schema')
                order by schema_name
                """
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return _normalise_schema_names([row[0] for row in rows])


def _snowflake_schemas(config: dict[str, Any]) -> list[str]:
    if snowflake_connector is None:
        raise BackendConnectorError(
            "snowflake-connector-python is not installed. Install it to use Snowflake backends."
        )

    required = {"user", "password", "account", "database"}
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        msg = f"Snowflake config is missing required fields: {', '.join(sorted(missing))}"
        raise BackendConnectorError(msg)

    connect_kwargs = {
        "user": config["user"],
        "password": config["password"],
        "account": config["account"],
        "warehouse": config.get("warehouse"),
        "database": config["database"],
        "role": config.get("role"),
    }
    # Remove None values to avoid connector warnings.
    clean_kwargs = {k: v for k, v in connect_kwargs.items() if v}

    ctx = snowflake_connector.connect(**clean_kwargs)
    cursor = ctx.cursor()
    try:
        cursor.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA ORDER BY SCHEMA_NAME")
        rows = cursor.fetchall()
    finally:
        with suppress(Exception):
            cursor.close()
        with suppress(Exception):
            ctx.close()

    return _normalise_schema_names([row[0] for row in rows])


def _normalise_schema_names(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in rows:
        name = str(value or "").strip()
        if not name:
            continue
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    return ordered


def normalize_schema_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in values:
        cleaned = str(raw or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(cleaned)
    return ordered


def get_schema_grants(config: dict[str, Any] | None) -> list[str]:
    if not isinstance(config, dict):
        return []
    raw = config.get("schema_grants")
    if not isinstance(raw, list):
        return []
    return normalize_schema_list(raw)


def list_backend_tables(
    kind: str, config: dict[str, Any], schemas: list[str]
) -> list[dict[str, Any]]:
    """Return table + column metadata for allowed schemas."""
    cleaned_schemas = normalize_schema_list(schemas)
    if not cleaned_schemas:
        raise BackendConnectorError("At least one schema is required for table introspection.")
    if kind == "postgres":
        rows = _postgres_table_rows(config, cleaned_schemas)
    elif kind == "snowflake":
        rows = _snowflake_table_rows(config, cleaned_schemas)
    else:
        raise BackendConnectorError(f"Table introspection unsupported for backend kind '{kind}'.")
    return _rows_to_table_entries(rows)


def _postgres_connection(config: dict[str, Any]):
    required = {"host", "port", "database", "user", "password"}
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        msg = f"Postgres config is missing required fields: {', '.join(sorted(missing))}"
        raise BackendConnectorError(msg)
    return psycopg2.connect(
        host=config["host"],
        port=int(config["port"]),
        dbname=config["database"],
        user=config["user"],
        password=config["password"],
        connect_timeout=int(config.get("connect_timeout") or 5),
        sslmode=str(config.get("sslmode") or "prefer"),
    )


def _postgres_table_rows(config: dict[str, Any], schemas: list[str]) -> list[tuple[str, str, str]]:
    conn = _postgres_connection(config)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.table_schema, c.table_name, c.column_name
                FROM information_schema.columns c
                JOIN information_schema.tables t
                  ON c.table_schema = t.table_schema AND c.table_name = t.table_name
                WHERE c.table_schema = ANY(%s)
                  AND t.table_type = 'BASE TABLE'
                ORDER BY c.table_schema, c.table_name, c.ordinal_position
                """,
                (schemas,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()
    return [(str(schema), str(table), str(column)) for schema, table, column in rows]


def _snowflake_cursor(config: dict[str, Any]):
    if snowflake_connector is None:
        raise BackendConnectorError(
            "snowflake-connector-python is not installed. Install it to use Snowflake backends."
        )
    required = {"user", "password", "account", "database"}
    missing = [key for key in required if not str(config.get(key) or "").strip()]
    if missing:
        msg = f"Snowflake config is missing required fields: {', '.join(sorted(missing))}"
        raise BackendConnectorError(msg)
    connect_kwargs = {
        "user": config["user"],
        "password": config["password"],
        "account": config["account"],
        "warehouse": config.get("warehouse"),
        "database": config["database"],
        "role": config.get("role"),
    }
    clean_kwargs = {k: v for k, v in connect_kwargs.items() if v}
    return snowflake_connector.connect(**clean_kwargs)


def _snowflake_table_rows(config: dict[str, Any], schemas: list[str]) -> list[tuple[str, str, str]]:
    ctx = _snowflake_cursor(config)
    cursor = ctx.cursor()
    try:
        placeholders = ", ".join(["%s"] * len(schemas))
        query = f"""
            SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA IN ({placeholders})
            ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION
        """
        cursor.execute(query, schemas)
        rows = cursor.fetchall()
    finally:
        with suppress(Exception):
            cursor.close()
        with suppress(Exception):
            ctx.close()
    return [(str(schema), str(table), str(column)) for schema, table, column in rows]


def _rows_to_table_entries(rows: list[tuple[str, str, str]]) -> list[dict[str, Any]]:
    table_columns: dict[tuple[str, str], list[str]] = {}
    for schema, table, column in rows:
        key = (schema, table)
        table_columns.setdefault(key, []).append(column)

    per_schema_counts: dict[str, int] = defaultdict(int)
    entries: list[dict[str, Any]] = []
    for (schema, table), columns in sorted(table_columns.items()):
        if per_schema_counts[schema] >= MAX_TABLES_PER_SCHEMA:
            continue
        per_schema_counts[schema] += 1
        entries.append(
            {
                "schema": schema,
                "table": table,
                "columns": columns[:MAX_COLUMNS_PER_TABLE],
            }
        )
    return entries
