from __future__ import annotations

from typing import BinaryIO

from fastapi import UploadFile

from app.core.config import settings

CHUNK_BYTES = 1024 * 1024


class SizeLimitError(ValueError):
    """Raised when an uploaded or remote payload exceeds the configured size limit."""


def _raise_if_over(limit: int | None, size: int, label: str) -> None:
    if limit is None or limit <= 0:
        return
    if size > limit:
        raise SizeLimitError(f"{label} exceeds limit ({size} bytes > {limit} bytes).")


async def read_upload_bytes(
    upload: UploadFile,
    *,
    label: str = "Upload",
    limit: int | None = None,
) -> bytes:
    """Read an UploadFile into memory while enforcing a maximum size."""
    max_bytes = settings.MAX_UPLOAD_BYTES if limit is None else limit
    buf = bytearray()
    while True:
        chunk = await upload.read(CHUNK_BYTES)
        if not chunk:
            break
        buf.extend(chunk)
        _raise_if_over(max_bytes, len(buf), label)
    return bytes(buf)


def read_stream_bytes(
    stream: BinaryIO,
    *,
    label: str = "Remote payload",
    limit: int | None = None,
) -> bytes:
    """Read a file-like stream into memory while enforcing a maximum size."""
    max_bytes = settings.MAX_REMOTE_BYTES if limit is None else limit
    buf = bytearray()
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        buf.extend(chunk)
        _raise_if_over(max_bytes, len(buf), label)
    return bytes(buf)
