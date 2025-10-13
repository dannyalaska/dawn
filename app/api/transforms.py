from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.core.db import session_scope
from app.core.models import Feed, Transform, TransformVersion
from app.core.transforms import (
    TransformDefinition,
    generate_dbt_model,
    generate_python_script,
    generate_transform_docs,
    run_dry_run,
)

router = APIRouter(prefix="/transforms", tags=["transforms"])


class TransformUpsertRequest(BaseModel):
    definition: TransformDefinition
    sample_rows: list[dict[str, Any]] | None = None
    context_samples: dict[str, list[dict[str, Any]]] | None = None


class TransformUpsertResponse(BaseModel):
    transform_id: int
    version: int
    code: str
    dbt_model: str | None
    dry_run: dict[str, Any] | None
    docs: dict[str, Any]


class TransformDryRunRequest(BaseModel):
    definition: TransformDefinition
    sample_rows: list[dict[str, Any]] = Field(min_length=1)
    context_samples: dict[str, list[dict[str, Any]]] | None = None


@router.post("", response_model=TransformUpsertResponse)
def create_transform(payload: TransformUpsertRequest) -> TransformUpsertResponse:
    definition = payload.definition
    python_code = generate_python_script(definition)
    dbt_model = generate_dbt_model(definition)
    docs = generate_transform_docs(definition)

    dry_run_report: dict[str, Any] | None = None
    if payload.sample_rows:
        try:
            dry_run_report = run_dry_run(
                sample_rows=payload.sample_rows,
                steps=definition.steps,
                context_samples=payload.context_samples,
            )
            dry_run_report["docs"] = docs
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"Dry-run failed: {exc}") from exc

    definition_dump = definition.model_dump(mode="json")
    definition_dump["docs"] = docs

    with session_scope() as s:
        feed = (
            s.execute(select(Feed).where(Feed.identifier == definition.feed_identifier))
            .scalars()
            .first()
        )
        if feed is None:
            raise HTTPException(404, f"Feed {definition.feed_identifier!r} not found")

        transform = (
            s.execute(select(Transform).where(Transform.name == definition.name)).scalars().first()
        )
        if transform is None:
            transform = Transform(
                name=definition.name,
                feed_id=feed.id,
                description=definition.description,
            )
            s.add(transform)
            s.flush()
        else:
            transform.feed_id = feed.id
            transform.description = definition.description

        max_version = (
            s.execute(
                select(func.max(TransformVersion.version)).where(
                    TransformVersion.transform_id == transform.id
                )
            ).scalar()
            or 0
        )
        next_version = int(max_version) + 1

        version_record = TransformVersion(
            transform_id=transform.id,
            version=next_version,
            definition=definition_dump,
            script=python_code,
            dbt_model=dbt_model,
            dry_run_report=dry_run_report,
        )
        s.add(version_record)
        s.flush()
        transform_id = transform.id
        version_number = version_record.version

    return TransformUpsertResponse(
        transform_id=transform_id,
        version=version_number,
        code=python_code,
        dbt_model=dbt_model,
        dry_run=dry_run_report,
        docs=docs,
    )


@router.post("/dry_run")
def dry_run_transform(payload: TransformDryRunRequest) -> dict[str, Any]:
    try:
        diff = run_dry_run(
            sample_rows=payload.sample_rows,
            steps=payload.definition.steps,
            context_samples=payload.context_samples,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Dry-run failed: {exc}") from exc

    return {
        "definition": payload.definition.model_dump(mode="json"),
        "diff": diff,
    }
