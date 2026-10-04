from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.repository_version import RepositoryVersion
    from app.models.symbol import Symbol
    from app.models.commit_file_change import CommitFileChange


class FileRecord(Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repository_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    extension: Mapped[str] = mapped_column(String(50), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown", index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parsing_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="UNPARSED",
        index=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    repository_version: Mapped["RepositoryVersion"] = relationship("RepositoryVersion", back_populates="files")
    symbols: Mapped[list["Symbol"]] = relationship(
        "Symbol",
        back_populates="file",
        cascade="all, delete-orphan",
    )
    commit_changes: Mapped[list["CommitFileChange"]] = relationship(
        "CommitFileChange",
        back_populates="file",
    )
