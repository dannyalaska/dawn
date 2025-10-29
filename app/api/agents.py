from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.agent_graph import AgentRunError, run_multi_agent_session
from app.core.auth import CurrentUser

router = APIRouter(prefix="/agents", tags=["agents"])


class AgentRunRequest(BaseModel):
    feed_identifier: str = Field(min_length=1)
    question: str | None = Field(default=None, description="Optional question for the QA agent.")
    refresh_context: bool = Field(
        default=True,
        description="Persist agent outputs into the shared context store.",
    )
    max_plan_steps: int = Field(default=12, ge=1, le=50)
    retrieval_k: int = Field(default=6, ge=1, le=25)


class AgentRunResponse(BaseModel):
    status: str
    feed_identifier: str
    feed_name: str | None
    feed_version: int | None
    plan: list[dict[str, Any]]
    completed: list[dict[str, Any]]
    warnings: list[str]
    context_updates: list[dict[str, Any]]
    answer: str | None
    answer_sources: list[dict[str, Any]]
    final_report: str
    run_log: list[dict[str, Any]]


@router.post("/analyze", response_model=AgentRunResponse)
def run_agents(payload: AgentRunRequest, current_user: CurrentUser) -> AgentRunResponse:
    try:
        state = run_multi_agent_session(
            feed_identifier=payload.feed_identifier,
            user_id=str(current_user.id),
            question=payload.question,
            refresh_context=payload.refresh_context,
            max_plan_steps=payload.max_plan_steps,
            retrieval_k=payload.retrieval_k,
        )
    except AgentRunError as exc:
        raise HTTPException(400, str(exc)) from exc

    status = "ok" if not state.get("warnings") else "warnings"
    answer = state.get("answer", "") or None

    return AgentRunResponse(
        status=status,
        feed_identifier=payload.feed_identifier,
        feed_name=state.get("feed_name"),
        feed_version=state.get("feed_version"),
        plan=state.get("plan", []),
        completed=state.get("completed", []),
        warnings=state.get("warnings", []),
        context_updates=state.get("context_updates", []),
        answer=answer,
        answer_sources=state.get("answer_sources", []),
        final_report=state.get("final_report", ""),
        run_log=state.get("run_log", []),
    )
