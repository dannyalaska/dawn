from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Upload(Base):
    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sheet: Mapped[str | None] = mapped_column(String(256))
    sha16: Mapped[str] = mapped_column(String(32), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    rows: Mapped[int] = mapped_column(Integer, nullable=False)
    cols: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
