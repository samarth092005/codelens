from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.file_record import FileRecord


class Symbol(Base):
    __tablename__ = "symbols"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    qualified_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    symbol_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    parent_symbol_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("symbols.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    line_start: Mapped[int] = mapped_column(Integer, nullable=False)
    line_end: Mapped[int] = mapped_column(Integer, nullable=False)
    visibility: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    file: Mapped["FileRecord"] = relationship("FileRecord", back_populates="symbols")
    parent_symbol: Mapped["Symbol | None"] = relationship(
        "Symbol",
        remote_side=[id],
        backref="children",
    )
