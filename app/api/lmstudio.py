from __future__ import annotations

import os
from pathlib import Path

import requests
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.core.auth import CurrentUser
from app.core.lmstudio import (
    cli_available,
    fetch_models,
    load_model,
    normalized_rest_base,
    unload_model,
)

router = APIRouter(prefix="/lmstudio", tags=["lmstudio"])

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"


class LmStudioLoadRequest(BaseModel):
    model_key: str = Field(..., min_length=1)
    base_url: str | None = None
    identifier: str | None = None
    context_length: int | None = Field(default=None, ge=0, le=65536)
    gpu: str | None = None
    ttl_seconds: int | None = Field(default=None, ge=0, le=86_400)


class LmStudioUnloadRequest(BaseModel):
    model_key: str | None = None
    base_url: str | None = None
    unload_all: bool = False


class LmStudioUseRequest(BaseModel):
    model: str = Field(..., min_length=1)
    base_url: str | None = None
    provider: str | None = "lmstudio"


def _persist_env_vars(updates: dict[str, str | None]) -> None:
    meaningful = {k: v for k, v in updates.items() if v}
    if not meaningful:
        return

    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text().splitlines()

    positions: dict[str, int] = {}
    for idx, line in enumerate(lines):
        if "=" in line and not line.strip().startswith("#"):
            key = line.split("=", 1)[0]
            positions[key] = idx

    for key, raw_value in meaningful.items():
        value = str(raw_value)
        line = f"{key}={value}"
        if key in positions:
            lines[positions[key]] = line
        else:
            lines.append(line)
        os.environ[key] = value

    ENV_PATH.write_text("\n".join(lines) + ("\n" if lines else ""))


@router.get("/models")
async def list_models(
    base_url: str | None = None,
    *,
    current_user: CurrentUser,
) -> dict:
    try:
        models = await run_in_threadpool(fetch_models, base_url)
    except requests.RequestException as exc:  # pragma: no cover - network surface
        raise HTTPException(status_code=502, detail=f"LM Studio request failed: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "models": models,
        "base_url": normalized_rest_base(base_url),
        "cli_available": cli_available(),
    }


@router.post("/load")
async def load_lmstudio_model(
    payload: LmStudioLoadRequest,
    *,
    current_user: CurrentUser,
) -> dict:
    try:
        context_length = payload.context_length or None
        if context_length == 0:
            context_length = None
        ttl_seconds = payload.ttl_seconds or None
        if ttl_seconds == 0:
            ttl_seconds = None
        output = await run_in_threadpool(
            load_model,
            payload.model_key,
            base_url=payload.base_url,
            identifier=payload.identifier,
            context_length=context_length,
            gpu=payload.gpu,
            ttl_seconds=ttl_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, "output": output}


@router.post("/unload")
async def unload_lmstudio_model(
    payload: LmStudioUnloadRequest,
    *,
    current_user: CurrentUser,
) -> dict:
    try:
        output = await run_in_threadpool(
            unload_model,
            payload.model_key,
            base_url=payload.base_url,
            unload_all=payload.unload_all,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"ok": True, "output": output}


@router.post("/use")
async def use_lmstudio_model(
    payload: LmStudioUseRequest,
    *,
    current_user: CurrentUser,
) -> dict:
    updates = {"LLM_PROVIDER": payload.provider or "lmstudio", "OPENAI_MODEL": payload.model}
    if payload.base_url:
        updates["OPENAI_BASE_URL"] = payload.base_url
    await run_in_threadpool(_persist_env_vars, updates)
    return {"ok": True, "restart_required": True}
