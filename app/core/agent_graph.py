from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.core.backend_connectors import (
    BackendConnectorError,
    get_schema_grants,
    list_backend_tables,
)
from app.core.chat_graph import run_chat
from app.core.db import session_scope
from app.core.models import BackendConnection, Feed, FeedDataset, FeedVersion
from app.core.rag import Chunk, upsert_chunks

__all__ = ["AgentRunError", "run_multi_agent_session"]


class AgentRunError(Exception):
    """Raised when the multi-agent workflow cannot continue."""


class AgentTask(TypedDict, total=False):
    id: str
    type: str
    description: str
    payload: dict[str, Any]
    status: str


class AgentResult(TypedDict, total=False):
    task_id: str
    type: str
    description: str
    data: Any


class AgentState(TypedDict, total=False):
    user_id: str
    feed_identifier: str
    feed_name: str
    feed_version: int
    summary: dict[str, Any]
    plan: list[dict[str, Any]]
    backend_sources: list[dict[str, Any]]
    tasks: list[AgentTask]
    completed: list[AgentResult]
    warnings: list[str]
    messages: list[dict[str, str]]
    run_log: list[dict[str, Any]]
    context_updates: list[dict[str, Any]]
    refresh_context: bool
    question: str
    answer: str
    answer_sources: list[dict[str, Any]]
    final_report: str
    retrieval_k: int
    max_plan_steps: int


def _ensure_int_user_id(user_id: str) -> int:
    try:
        return int(user_id)
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise AgentRunError("user_id must be numeric for multi-agent execution") from exc


def _load_feed_snapshot(feed_identifier: str, user_id: str) -> dict[str, Any]:
    numeric_user = _ensure_int_user_id(user_id)
    with session_scope() as session:
        feed = (
            session.execute(
                select(Feed).where(Feed.identifier == feed_identifier, Feed.user_id == numeric_user)
            )
            .scalars()
            .first()
        )
        if feed is None:
            raise AgentRunError(f"Feed {feed_identifier!r} not found for user.")

        version = (
            session.execute(
                select(FeedVersion)
                .where(FeedVersion.feed_id == feed.id, FeedVersion.user_id == numeric_user)
                .order_by(FeedVersion.version.desc())
                .limit(1)
            )
            .scalars()
            .first()
        )

        if version is None:
            raise AgentRunError(f"No versions available for feed {feed_identifier!r}.")

        summary = dict(version.summary_json or {})

        return {
            "feed_name": feed.name,
            "feed_version": int(version.version),
            "summary": summary,
        }


def _load_backend_sources(user_id: str) -> list[dict[str, Any]]:
    numeric_user = _ensure_int_user_id(user_id)
    with session_scope() as session:
        connection_rows = (
            session.execute(
                select(BackendConnection).where(BackendConnection.user_id == numeric_user)
            )
            .scalars()
            .all()
        )
        dataset_rows = session.execute(
            select(FeedDataset, Feed)
            .join(Feed, FeedDataset.feed_id == Feed.id)
            .where(Feed.user_id == numeric_user)
        ).all()
        connections = [
            {
                "id": conn.id,
                "name": conn.name,
                "kind": conn.kind,
                "config": dict(conn.config or {}),
            }
            for conn in connection_rows
        ]
        datasets = [
            {
                "id": dataset.id,
                "table_name": dataset.table_name,
                "schema_name": dataset.schema_name,
                "columns": list(dataset.columns or []),
                "feed_identifier": feed.identifier,
                "feed_version_id": dataset.feed_version_id,
                "feed_name": feed.name,
            }
            for dataset, feed in dataset_rows
        ]

    sources: list[dict[str, Any]] = []
    for connection in connections:
        config = connection["config"]
        schemas = get_schema_grants(config)
        if not schemas:
            continue
        try:
            table_rows = list_backend_tables(connection["kind"], config, schemas)
        except BackendConnectorError as exc:
            sources.append(
                {
                    "id": connection["id"],
                    "name": connection["name"],
                    "kind": connection["kind"],
                    "schemas": schemas,
                    "schema_details": [],
                    "error": str(exc),
                }
            )
            continue
        tables_by_schema: dict[str, list[dict[str, Any]]] = {}
        for row in table_rows:
            schema_name = row.get("schema")
            if not schema_name:
                continue
            tables_by_schema.setdefault(schema_name, []).append(
                {
                    "name": row.get("table"),
                    "columns": row.get("columns", []),
                }
            )
        schema_details: list[dict[str, Any]] = []
        for schema_name in schemas:
            schema_details.append(
                {
                    "name": schema_name,
                    "tables": tables_by_schema.get(schema_name, []),
                }
            )
        sources.append(
            {
                "id": connection["id"],
                "name": connection["name"],
                "kind": connection["kind"],
                "schemas": schemas,
                "schema_details": schema_details,
                "error": None,
            }
        )

    for dataset in datasets:
        schema_name = dataset["schema_name"] or "public"
        sources.append(
            {
                "id": f"feed_dataset:{dataset['id']}",
                "name": f"{dataset['feed_identifier']} v{dataset['feed_version_id']}",
                "kind": "feed_table",
                "schemas": [schema_name],
                "schema_details": [
                    {
                        "name": schema_name,
                        "tables": [
                            {
                                "name": dataset["table_name"],
                                "columns": dataset["columns"],
                            }
                        ],
                    }
                ],
                "error": None,
            }
        )
    return sources


def _derive_plan(
    summary: dict[str, Any],
    *,
    limit: int,
    backend_sources: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    raw_plan = summary.get("analysis_plan") or []
    if not isinstance(raw_plan, list):
        raw_plan = []

    plan: list[dict[str, Any]] = []
    for entry in raw_plan:
        if isinstance(entry, dict) and entry.get("type"):
            plan.append(entry)
        if len(plan) >= limit:
            break

    if not plan:
        insights = summary.get("insights") or {}
        if isinstance(insights, dict):
            for column in insights:
                plan.append({"type": "count_by", "column": column})
                if len(plan) >= limit:
                    break

    if not plan:
        aggregates = summary.get("aggregates") or []
        if isinstance(aggregates, list):
            for agg in aggregates:
                if not isinstance(agg, dict):
                    continue
                plan.append(
                    {
                        "type": agg.get("stat", "avg_by"),
                        "group": agg.get("group"),
                        "value": agg.get("value"),
                        "stat": agg.get("stat", "mean"),
                    }
                )
                if len(plan) >= limit:
                    break

    if backend_sources:
        plan = _extend_plan_with_backends(plan, backend_sources, limit=limit)

    return plan


def _extend_plan_with_backends(
    plan: list[dict[str, Any]], backend_sources: list[dict[str, Any]], *, limit: int
) -> list[dict[str, Any]]:
    for source in backend_sources:
        schema_details = source.get("schema_details") or []
        if not schema_details and source.get("schemas"):
            schema_details = [{"name": name} for name in source.get("schemas", [])]
        for schema in schema_details:
            if len(plan) >= limit:
                return plan
            schema_name = schema.get("name")
            if not schema_name:
                continue
            plan.append(
                {
                    "type": "schema_inventory",
                    "schema": schema_name,
                    "connection_id": source.get("id"),
                    "connection_name": source.get("name"),
                    "kind": source.get("kind"),
                }
            )
    return plan


def _task_description(entry: dict[str, Any]) -> str:
    task_type = entry.get("type") or "task"
    if task_type == "count_by":
        return f"Count rows by {entry.get('column', '?')}"
    if task_type in {"avg_by", "mean_by"}:
        return (
            f"Aggregate {entry.get('value', '?')} by {entry.get('group', '?')} "
            f"({entry.get('stat', 'mean')})"
        )
    if task_type == "schema_inventory":
        conn = entry.get("connection_name") or entry.get("kind") or "connection"
        return f"Inventory schema {entry.get('schema', '?')} on {conn}"
    return f"Execute plan step: {task_type}"


def _build_tasks(
    plan: list[dict[str, Any]], *, existing: list[AgentTask] | None = None
) -> list[AgentTask]:
    tasks: list[AgentTask] = []
    for entry in plan:
        tasks.append(
            AgentTask(
                id=uuid.uuid4().hex[:12],
                type=str(entry.get("type", "task")),
                description=_task_description(entry),
                payload=dict(entry),
                status="pending",
            )
        )
    if existing:
        return [*existing, *tasks]
    return tasks


def _execute_task(
    task: AgentTask,
    *,
    summary: dict[str, Any],
    backend_sources: list[dict[str, Any]],
) -> tuple[AgentResult | None, list[str]]:
    warnings: list[str] = []
    task_type = task.get("type")
    payload = task.get("payload", {})
    result: AgentResult | None = None

    if task_type == "count_by":
        column = str(payload.get("column"))
        counts = _column_counts(summary, column)
        if counts:
            result = AgentResult(
                task_id=task["id"],
                type=task_type,
                description=task["description"],
                data={"column": column, "counts": counts},
            )
        else:
            warnings.append(f"No value counts available for column {column!r}.")

    elif task_type in {"avg_by", "mean_by"}:
        group = str(payload.get("group"))
        value = str(payload.get("value"))
        stat = str(payload.get("stat", "mean"))
        aggregate_match = _aggregate_stats(summary, group, value)
        if aggregate_match:
            result = AgentResult(
                task_id=task["id"],
                type=task_type,
                description=task["description"],
                data={
                    "group": group,
                    "value": value,
                    "stat": stat,
                    "best": aggregate_match.get("best", []),
                    "worst": aggregate_match.get("worst", []),
                },
            )
        else:
            warnings.append(f"No aggregate metrics found for {value!r} by {group!r}.")

    elif task_type == "schema_inventory":
        result, warning = _execute_schema_inventory(task, backend_sources=backend_sources)
        if warning:
            warnings.append(warning)

    else:
        fallback_data, fallback_warning = _fallback_tooling(task_type or "task", payload, summary)
        result = AgentResult(
            task_id=task["id"],
            type=task_type or "task",
            description=task["description"],
            data=fallback_data,
        )
        if fallback_warning:
            warnings.append(fallback_warning)

    return result, warnings


def _fallback_tooling(
    task_type: str, payload: dict[str, Any], summary: dict[str, Any]
) -> tuple[dict[str, Any], str]:
    column_name = str(payload.get("column") or payload.get("target") or "").strip()
    columns = summary.get("columns") or []
    if column_name:
        for column in columns:
            if isinstance(column, dict) and str(column.get("name")) == column_name:
                profile = {
                    "dtype": column.get("dtype"),
                    "top_values": column.get("top_values"),
                    "stats": column.get("stats"),
                }
                return (
                    {
                        "column": column_name,
                        "profile": profile,
                        "payload": payload,
                        "source": "column_profile",
                    },
                    f"Used column profile for task {task_type!r}.",
                )
    relationships = summary.get("relationships")
    if column_name and isinstance(relationships, dict) and column_name in relationships:
        return (
            {
                "column": column_name,
                "relationship": relationships[column_name],
                "payload": payload,
                "source": "relationships",
            },
            f"Used relationship hints for task {task_type!r}.",
        )
    summary_text = summary.get("text")
    if isinstance(summary_text, str) and summary_text.strip():
        return (
            {
                "note": summary_text.strip()[:400],
                "payload": payload,
                "source": "dataset_summary",
            },
            f"Used dataset summary for task {task_type!r}.",
        )
    return (
        {
            "note": f"No structured data available for task {task_type!r}.",
            "payload": payload,
            "source": "fallback",
        },
        f"No structured data available for task {task_type!r}.",
    )


def _execute_schema_inventory(
    task: AgentTask,
    *,
    backend_sources: list[dict[str, Any]],
) -> tuple[AgentResult | None, str | None]:
    payload = task.get("payload") or {}
    connection_id = payload.get("connection_id")
    schema_name = str(payload.get("schema") or "").strip()
    if not connection_id or not schema_name:
        return None, "Schema inventory payload is incomplete."
    source = next((item for item in backend_sources if item.get("id") == connection_id), None)
    if source is None:
        return None, f"Backend connection {connection_id!r} not available."
    if source.get("error"):
        result = AgentResult(
            task_id=task["id"],
            type="schema_inventory",
            description=task["description"],
            data={
                "connection": source.get("name"),
                "schema": schema_name,
                "error": source.get("error"),
            },
        )
        return result, None
    schema_details = next(
        (item for item in source.get("schema_details", []) if item.get("name") == schema_name),
        None,
    )
    tables = (schema_details or {}).get("tables") or []
    preview = [
        {"table": entry.get("name"), "columns": (entry.get("columns") or [])[:6]}
        for entry in tables[:5]
        if entry.get("name")
    ]
    result = AgentResult(
        task_id=task["id"],
        type="schema_inventory",
        description=task["description"],
        data={
            "connection": source.get("name"),
            "kind": source.get("kind"),
            "schema": schema_name,
            "tables": preview,
            "table_count": len(tables),
        },
    )
    return result, None


def _column_counts(summary: dict[str, Any], column: str) -> list[dict[str, Any]]:
    def _normalise(raw: Any) -> list[dict[str, Any]]:
        if isinstance(raw, list):
            return [c for c in raw if isinstance(c, dict)]
        return []

    insights = summary.get("insights") or {}
    if isinstance(insights, dict):
        counts = _normalise(insights.get(column))
        if counts:
            return counts

    metrics = summary.get("metrics") or []
    for metric in metrics:
        if (
            isinstance(metric, dict)
            and metric.get("type") == "value_counts"
            and metric.get("column") == column
        ):
            return _normalise(metric.get("values"))

    return []


def _aggregate_stats(summary: dict[str, Any], group: str, value: str) -> dict[str, Any] | None:
    aggregates = summary.get("aggregates") or []
    for aggregate in aggregates:
        if not isinstance(aggregate, dict):
            continue
        if aggregate.get("group") == group and aggregate.get("value") == value:
            return aggregate
    return None


def _summarise_result(result: AgentResult) -> str:
    data = result.get("data") or {}
    if result.get("type") == "count_by":
        column = data.get("column")
        counts = data.get("counts") or []
        formatted = ", ".join(
            f"{row.get('label')}: {row.get('count')}" for row in counts[:5] if isinstance(row, dict)
        )
        return f"{column}: {formatted}"
    if result.get("type") in {"avg_by", "mean_by"}:
        stat = data.get("stat")
        group = data.get("group")
        best = data.get("best") or []
        worst = data.get("worst") or []
        best_txt = ", ".join(
            f"{row.get('label')}={float(row.get('value', 0.0)):.2f}"
            for row in best[:3]
            if isinstance(row, dict)
        )
        worst_txt = ", ".join(
            f"{row.get('label')}={float(row.get('value', 0.0)):.2f}"
            for row in worst[:3]
            if isinstance(row, dict)
        )
        return f"{stat} {group}: best [{best_txt}] | worst [{worst_txt}]"
    if result.get("type") == "schema_inventory":
        schema = data.get("schema")
        connection = data.get("connection")
        error = data.get("error")
        if error:
            return f"{schema} on {connection}: {error}"
        tables = data.get("tables") or []
        if tables:
            formatted = ", ".join(
                f"{entry.get('table')} ({', '.join(entry.get('columns') or [])})"
                for entry in tables[:3]
                if entry.get("table")
            )
        else:
            formatted = "no tables discovered"
        return f"{schema} on {connection}: {formatted}"
    note = data
    return f"{result.get('description')}: {note}"


def _needs_qa(state: AgentState) -> str:
    question = state.get("question", "")
    if question and question.strip():
        return "qa"
    return "guard"


@lru_cache(maxsize=1)
def _compiled_graph() -> Any:
    graph = StateGraph(AgentState)

    def bootstrap_node(state: AgentState) -> dict[str, Any]:
        snapshot = _load_feed_snapshot(state["feed_identifier"], state["user_id"])
        backend_sources = state.get("backend_sources", [])
        messages = [
            *state.get("messages", []),
            {
                "role": "system",
                "content": (
                    f"Loaded feed {state['feed_identifier']} v{snapshot['feed_version']} "
                    f"for analysis."
                ),
            },
        ]
        log_entry = {
            "agent": "bootstrap",
            "message": "Feed summary loaded.",
            "feed_version": snapshot["feed_version"],
            "backend_sources": len(backend_sources),
        }
        return {
            "feed_name": snapshot["feed_name"],
            "feed_version": snapshot["feed_version"],
            "summary": snapshot["summary"],
            "backend_sources": backend_sources,
            "messages": messages,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    def planner_node(state: AgentState) -> dict[str, Any]:
        summary = state.get("summary", {})
        plan = _derive_plan(
            summary,
            limit=state.get("max_plan_steps", 12),
            backend_sources=state.get("backend_sources", []),
        )
        tasks = _build_tasks(plan, existing=state.get("tasks"))
        log_entry = {
            "agent": "planner",
            "message": f"Planner produced {len(plan)} steps.",
        }
        return {
            "plan": plan,
            "tasks": tasks,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    def executor_node(state: AgentState) -> dict[str, Any]:
        summary = state.get("summary", {})
        backend_sources = state.get("backend_sources", [])
        completed = list(state.get("completed", []))
        warnings = list(state.get("warnings", []))
        for task in state.get("tasks", []):
            result, task_warnings = _execute_task(
                task,
                summary=summary,
                backend_sources=backend_sources,
            )
            warnings.extend(task_warnings)
            if result:
                completed.append(result)
        log_entry = {
            "agent": "executor",
            "message": f"Executed {len(state.get('tasks', []))} tasks.",
        }
        return {
            "completed": completed,
            "tasks": [],
            "warnings": warnings,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    def memory_node(state: AgentState) -> dict[str, Any]:
        completed = state.get("completed", [])
        if not completed:
            return {}
        refresh = state.get("refresh_context", True)
        user_id = state["user_id"]
        feed_id = state["feed_identifier"]
        context_updates = list(state.get("context_updates", []))
        chunks: list[Chunk] = []
        for idx, result in enumerate(completed, start=1):
            summary_text = _summarise_result(result)
            context_updates.append(
                {
                    "task_id": result["task_id"],
                    "text": summary_text,
                }
            )
            if refresh:
                chunks.append(
                    Chunk(
                        text=f"[{feed_id}] {summary_text}",
                        source=f"agent:{feed_id}",
                        row_index=idx,
                        chunk_type="agent_summary",
                        metadata={"tags": ["agentic", "metrics"]},
                    )
                )
        inserted = 0
        if refresh and chunks:
            inserted = upsert_chunks(chunks, user_id=user_id)
        log_entry = {
            "agent": "memory",
            "message": f"Memory curator processed {len(completed)} results.",
            "chunks_inserted": inserted,
        }
        return {
            "context_updates": context_updates,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    def qa_node(state: AgentState) -> dict[str, Any]:
        question = state.get("question", "").strip()
        if not question:
            return {}
        log_entry: dict[str, Any]
        try:
            chat_result = run_chat(
                [{"role": "user", "content": question}],
                k=state.get("retrieval_k", 6),
                user_id=state["user_id"],
            )
            answer = chat_result.get("answer", "")
            sources = chat_result.get("sources", [])
        except Exception as exc:  # noqa: BLE001
            answer = ""
            sources = []
            warnings = [*state.get("warnings", []), f"QA agent failed: {exc}"]
            log_entry = {
                "agent": "qa",
                "message": "Question answering failed.",
                "error": str(exc),
            }
            return {
                "answer": answer,
                "answer_sources": sources,
                "warnings": warnings,
                "run_log": [*state.get("run_log", []), log_entry],
            }
        log_entry = {
            "agent": "qa",
            "message": "Answer generated.",
            "sources": len(sources),
        }
        return {
            "answer": answer,
            "answer_sources": sources,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    def guard_node(state: AgentState) -> dict[str, Any]:
        warnings = list(state.get("warnings", []))
        if not state.get("completed"):
            warnings.append("No tasks completed; results may be incomplete.")
        log_entry: dict[str, Any] = {
            "agent": "guardrail",
            "message": "Validation complete.",
            "warnings": len(warnings),
        }
        return {
            "warnings": warnings,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    def respond_node(state: AgentState) -> dict[str, Any]:
        lines = []
        for result in state.get("completed", []):
            lines.append(f"- {result['description']}: {_summarise_result(result)}")
        answer = state.get("answer")
        if answer:
            lines.append("")
            lines.append("Answer:")
            lines.append(answer)
        if state.get("warnings"):
            lines.append("")
            lines.append("Warnings:")
            for warning in state["warnings"]:
                lines.append(f"! {warning}")
        report = "\n".join(lines)
        log_entry = {
            "agent": "responder",
            "message": "Session complete.",
        }
        return {
            "final_report": report,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    graph.add_node("bootstrap", bootstrap_node)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("memory", memory_node)
    graph.add_node("qa", qa_node)
    graph.add_node("guard", guard_node)
    graph.add_node("respond", respond_node)

    graph.set_entry_point("bootstrap")
    graph.add_edge("bootstrap", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "memory")
    graph.add_conditional_edges("memory", _needs_qa, {"qa": "qa", "guard": "guard"})
    graph.add_edge("qa", "guard")
    graph.add_edge("guard", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


def run_multi_agent_session(
    *,
    feed_identifier: str,
    user_id: str,
    question: str | None = None,
    refresh_context: bool = True,
    max_plan_steps: int = 12,
    retrieval_k: int = 6,
) -> dict[str, Any]:
    """Execute the multi-agent workflow and return the final agent state."""
    if not feed_identifier:
        raise AgentRunError("feed_identifier is required.")
    backend_sources = _load_backend_sources(user_id)

    initial_state: AgentState = {
        "user_id": user_id,
        "feed_identifier": feed_identifier,
        "plan": [],
        "tasks": [],
        "completed": [],
        "warnings": [],
        "messages": [],
        "run_log": [],
        "context_updates": [],
        "backend_sources": backend_sources,
        "refresh_context": refresh_context,
        "question": question or "",
        "answer": "",
        "answer_sources": [],
        "final_report": "",
        "retrieval_k": retrieval_k,
        "max_plan_steps": max_plan_steps,
    }
    compiled = _compiled_graph()
    state = compiled.invoke(initial_state)
    # Attach bounded plan metadata for reference
    if state.get("plan") and len(state["plan"]) > max_plan_steps:
        state["plan"] = state["plan"][:max_plan_steps]
    return state
