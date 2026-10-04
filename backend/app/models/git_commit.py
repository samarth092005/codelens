from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.repository_version import RepositoryVersion
    from app.models.commit_file_change import CommitFileChange


class GitCommit(Base):
    __tablename__ = "git_commits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repository_version_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("repository_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    commit_hash: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    parent_hash: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    author_name: Mapped[str] = mapped_column(String(255), nullable=False)
    author_email: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    committed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="commits")
    repository_version: Mapped["RepositoryVersion | None"] = relationship("RepositoryVersion")
    changed_files: Mapped[list["CommitFileChange"]] = relationship(
        "CommitFileChange",
        back_populates="commit",
        cascade="all, delete-orphan",
        order_by="CommitFileChange.file_path",
    )

    @property
    def file_changes(self) -> list["CommitFileChange"]:
        return self.changed_files

    @property
    def symbol_changes(self) -> list[any]:
        return [sym for fc in self.changed_files for sym in fc.changed_symbols]

    @property
    def files_changed_count(self) -> int:
        return len(self.changed_files)

    @property
    def insertions(self) -> int:
        return sum(fc.additions for fc in self.changed_files)

    @property
    def deletions(self) -> int:
        return sum(fc.deletions for fc in self.changed_files)

