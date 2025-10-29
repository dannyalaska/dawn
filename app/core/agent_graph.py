from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy import select

from app.core.chat_graph import run_chat
from app.core.db import session_scope
from app.core.models import Feed, FeedVersion
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


def _derive_plan(summary: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    raw_plan = summary.get("analysis_plan") or []
    if not isinstance(raw_plan, list):
        raw_plan = []

    plan: list[dict[str, Any]] = []
    for entry in raw_plan:
        if isinstance(entry, dict) and entry.get("type"):
            plan.append(entry)
        if len(plan) >= limit:
            break

    if plan:
        return plan

    insights = summary.get("insights") or {}
    if isinstance(insights, dict):
        for column in insights:
            plan.append({"type": "count_by", "column": column})
            if len(plan) >= limit:
                return plan

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
) -> tuple[AgentResult | None, list[str]]:
    warnings: list[str] = []
    task_type = task.get("type")
    payload = task.get("payload", {})
    result: AgentResult | None = None

    if task_type == "count_by":
        column = str(payload.get("column"))
        counts: list[dict[str, Any]] = []
        insights = summary.get("insights") or {}
        if isinstance(insights, dict):
            raw_counts = insights.get(column) or []
            if isinstance(raw_counts, list):
                counts = [c for c in raw_counts if isinstance(c, dict)]
        if not counts:
            metrics = summary.get("metrics") or []
            for metric in metrics:
                if (
                    isinstance(metric, dict)
                    and metric.get("type") == "value_counts"
                    and metric.get("column") == column
                ):
                    raw_values = metric.get("values") or []
                    if isinstance(raw_values, list):
                        counts = [c for c in raw_values if isinstance(c, dict)]
                    break
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
        aggregates = summary.get("aggregates") or []
        aggregate_match = None
        for agg in aggregates:
            if not isinstance(agg, dict):
                continue
            if agg.get("group") == group and agg.get("value") == value:
                aggregate_match = agg
                break
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

    else:
        result = AgentResult(
            task_id=task["id"],
            type=task_type or "task",
            description=task["description"],
            data={"note": "Task type not recognized; no execution performed."},
        )

    return result, warnings


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
        }
        return {
            "feed_name": snapshot["feed_name"],
            "feed_version": snapshot["feed_version"],
            "summary": snapshot["summary"],
            "messages": messages,
            "run_log": [*state.get("run_log", []), log_entry],
        }

    def planner_node(state: AgentState) -> dict[str, Any]:
        summary = state.get("summary", {})
        plan = _derive_plan(summary, limit=state.get("max_plan_steps", 12))
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
        completed = list(state.get("completed", []))
        warnings = list(state.get("warnings", []))
        for task in state.get("tasks", []):
            result, task_warnings = _execute_task(task, summary=summary)
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
