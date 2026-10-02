from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base

if TYPE_CHECKING:
    from app.models.repository import Repository
    from app.models.file_record import FileRecord
    from app.models.dependency import Dependency
    from app.models.analysis_job import AnalysisJob


class RepositoryVersion(Base):
    __tablename__ = "repository_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    repository_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("repositories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    commit_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    repository: Mapped["Repository"] = relationship("Repository", back_populates="versions")
    files: Mapped[list["FileRecord"]] = relationship(
        "FileRecord",
        back_populates="repository_version",
        cascade="all, delete-orphan",
    )
    dependencies: Mapped[list["Dependency"]] = relationship(
        "Dependency",
        back_populates="repository_version",
        cascade="all, delete-orphan",
    )
    analysis_jobs: Mapped[list["AnalysisJob"]] = relationship(
        "AnalysisJob",
        back_populates="repository_version",
    )
