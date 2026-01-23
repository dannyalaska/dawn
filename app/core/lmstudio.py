from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

import requests

DEFAULT_LMSTUDIO_BASE = "http://127.0.0.1:1234"


def normalized_rest_base(base_url: str | None) -> str:
    base = base_url or os.getenv("OPENAI_BASE_URL") or DEFAULT_LMSTUDIO_BASE
    base = base.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def lmstudio_host(base_url: str | None) -> str | None:
    raw = base_url or os.getenv("OPENAI_BASE_URL") or DEFAULT_LMSTUDIO_BASE
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = parsed.netloc or parsed.path
    return host or None


def cli_available() -> bool:
    return bool(shutil.which("lms"))


def _run_cli(args: list[str], *, base_url: str | None, timeout: int = 120) -> str:
    lms_path = shutil.which("lms")
    if not lms_path:
        raise RuntimeError("LM Studio CLI ('lms') not found. Install it or add to PATH.")
    host = lmstudio_host(base_url)
    cmd = [lms_path, *args]
    if host:
        cmd.extend(["--host", host])
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(message or "LM Studio CLI command failed.")
    return (result.stdout or "").strip()


def lmstudio_model_key(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "")
    publisher = str(model.get("publisher") or "")
    if not model_id:
        return ""
    if "/" in model_id or not publisher:
        return model_id
    return f"{publisher}/{model_id}"


def _lmstudio_display_name(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "")
    key = lmstudio_model_key(model)
    return key or model_id


def fetch_models(base_url: str | None) -> list[dict[str, Any]]:
    rest_base = normalized_rest_base(base_url)
    url = f"{rest_base}/api/v0/models"
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    payload = response.json()

    raw_models: list[Any]
    if isinstance(payload, dict):
        data = payload.get("data")
        raw_models = data if isinstance(data, list) else []
    elif isinstance(payload, list):
        raw_models = payload
    else:
        raw_models = []

    models: list[dict[str, Any]] = []
    for raw in raw_models:
        if not isinstance(raw, dict):
            continue
        model = dict(raw)
        model["model_key"] = lmstudio_model_key(model)
        model["display_name"] = _lmstudio_display_name(model)
        models.append(model)
    return models


def load_model(
    model_key: str,
    *,
    base_url: str | None,
    identifier: str | None = None,
    context_length: int | None = None,
    gpu: str | None = None,
    ttl_seconds: int | None = None,
) -> str:
    args = ["load", model_key]
    if identifier:
        args.extend(["--identifier", identifier])
    if context_length:
        args.extend(["--context-length", str(context_length)])
    if gpu:
        args.extend(["--gpu", gpu])
    if ttl_seconds:
        args.extend(["--ttl", str(ttl_seconds)])
    return _run_cli(args, base_url=base_url)


def unload_model(
    model_key: str | None,
    *,
    base_url: str | None,
    unload_all: bool = False,
) -> str:
    args = ["unload"]
    if unload_all:
        args.append("--all")
    elif model_key:
        args.append(model_key)
    else:
        raise RuntimeError("Model key required to unload a specific model.")
    return _run_cli(args, base_url=base_url)
