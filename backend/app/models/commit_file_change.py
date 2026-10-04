from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.git_commit import GitCommit
    from app.models.file_record import FileRecord
    from app.models.commit_symbol_change import CommitSymbolChange


class CommitFileChange(Base):
    __tablename__ = "commit_file_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    commit_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("git_commits.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("files.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False, index=True)
    old_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    change_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # ADDED, MODIFIED, DELETED, RENAMED
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    commit: Mapped["GitCommit"] = relationship("GitCommit", back_populates="changed_files")
    file: Mapped["FileRecord | None"] = relationship("FileRecord", back_populates="commit_changes")
    changed_symbols: Mapped[list["CommitSymbolChange"]] = relationship(
        "CommitSymbolChange",
        back_populates="file_change",
        cascade="all, delete-orphan",
        order_by="CommitSymbolChange.symbol_name",
    )

    @property
    def insertions(self) -> int:
        return self.additions

