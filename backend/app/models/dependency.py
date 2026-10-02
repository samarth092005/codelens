from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.repository_version import RepositoryVersion
    from app.models.file_record import FileRecord
    from app.models.symbol import Symbol


class Dependency(Base):
    __tablename__ = "dependencies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repository_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # IMPORT, CALL

    # Source & target files
    source_file_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("files.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    target_file_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Caller & callee symbols
    caller_symbol_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("symbols.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    callee_symbol_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("symbols.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Specific metadata
    callee_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_module: Mapped[str | None] = mapped_column(String(512), nullable=True)
    import_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)

    resolution_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UNRESOLVED",
        index=True,
    )  # RESOLVED, UNRESOLVED, EXTERNAL

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    repository_version: Mapped["RepositoryVersion"] = relationship(
        "RepositoryVersion",
        back_populates="dependencies",
    )
    source_file: Mapped["FileRecord | None"] = relationship(
        "FileRecord",
        foreign_keys=[source_file_id],
    )
    target_file: Mapped["FileRecord | None"] = relationship(
        "FileRecord",
        foreign_keys=[target_file_id],
    )
    caller_symbol: Mapped["Symbol | None"] = relationship(
        "Symbol",
        foreign_keys=[caller_symbol_id],
    )
    callee_symbol: Mapped["Symbol | None"] = relationship(
        "Symbol",
        foreign_keys=[callee_symbol_id],
    )
