from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.commit_file_change import CommitFileChange
    from app.models.symbol import Symbol


class CommitSymbolChange(Base):
    __tablename__ = "commit_symbol_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    file_change_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("commit_file_changes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    symbol_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("symbols.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    symbol_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    qualified_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    symbol_type: Mapped[str] = mapped_column(String(50), nullable=False)  # function, class, method
    change_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # ADDED, MODIFIED, DELETED
    old_line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    old_line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    changed_lines_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    file_change: Mapped["CommitFileChange"] = relationship("CommitFileChange", back_populates="changed_symbols")
    symbol: Mapped["Symbol | None"] = relationship("Symbol", back_populates="commit_changes")

    @property
    def file_path(self) -> str:
        return self.file_change.file_path if self.file_change else ""

    @property
    def commit_id(self) -> int | None:
        return self.file_change.commit_id if self.file_change else None

    @property
    def commit(self) -> any:
        return self.file_change.commit if self.file_change else None

    @property
    def line_start(self) -> int | None:
        return self.new_line_start if self.new_line_start is not None else self.old_line_start

    @property
    def line_end(self) -> int | None:
        return self.new_line_end if self.new_line_end is not None else self.old_line_end

