from collections.abc import Sequence
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.analysis_job import AnalysisJob
from app.models.dependency import Dependency
from app.models.file_record import FileRecord
from app.models.repository_version import RepositoryVersion
from app.models.symbol import Symbol


class CodeIntelligenceRepository:
    """Repository handling database queries for versions, files, symbols, dependencies, and jobs."""

    # 1. Repository Versions
    def get_version(self, db: Session, version_id: int) -> RepositoryVersion | None:
        stmt = select(RepositoryVersion).where(RepositoryVersion.id == version_id)
        return db.scalars(stmt).first()

    def get_latest_version(self, db: Session, repository_id: int) -> RepositoryVersion | None:
        stmt = (
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == repository_id)
            .order_by(RepositoryVersion.id.desc())
        )
        return db.scalars(stmt).first()

    def list_versions(
        self, db: Session, repository_id: int, *, skip: int = 0, limit: int = 100
    ) -> Sequence[RepositoryVersion]:
        stmt = (
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == repository_id)
            .order_by(RepositoryVersion.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return db.scalars(stmt).all()

    # 2. Files
    def list_files(
        self,
        db: Session,
        version_id: int,
        *,
        language: str | None = None,
        parsing_status: str | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[FileRecord]:
        stmt = select(FileRecord).where(FileRecord.repository_version_id == version_id)
        if language:
            stmt = stmt.where(FileRecord.language == language)
        if parsing_status:
            stmt = stmt.where(FileRecord.parsing_status == parsing_status)
        stmt = stmt.order_by(FileRecord.path.asc()).offset(skip).limit(limit)
        return db.scalars(stmt).all()

    def get_file(self, db: Session, file_id: int) -> FileRecord | None:
        stmt = (
            select(FileRecord)
            .options(
                selectinload(FileRecord.symbols),
                selectinload(FileRecord.repository_version),
            )
            .where(FileRecord.id == file_id)
        )
        return db.scalars(stmt).first()

    def get_file_dependencies(self, db: Session, file_id: int) -> Sequence[Dependency]:
        stmt = (
            select(Dependency)
            .options(selectinload(Dependency.target_file))
            .where(
                Dependency.relationship_type == "IMPORT",
                Dependency.source_file_id == file_id,
            )
            .order_by(Dependency.line_number.asc().nulls_last(), Dependency.id.asc())
        )
        return db.scalars(stmt).all()

    def get_file_dependents(self, db: Session, file_id: int) -> Sequence[Dependency]:
        stmt = (
            select(Dependency)
            .options(selectinload(Dependency.source_file))
            .where(
                Dependency.relationship_type == "IMPORT",
                Dependency.target_file_id == file_id,
                Dependency.resolution_status == "RESOLVED",
            )
            .order_by(Dependency.id.asc())
        )
        return db.scalars(stmt).all()

    # 3. Symbols
    def list_symbols(
        self,
        db: Session,
        version_id: int,
        *,
        file_id: int | None = None,
        name: str | None = None,
        symbol_type: str | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[Symbol]:
        stmt = (
            select(Symbol)
            .join(FileRecord, Symbol.file_id == FileRecord.id)
            .where(FileRecord.repository_version_id == version_id)
        )
        if file_id is not None:
            stmt = stmt.where(Symbol.file_id == file_id)
        if name:
            stmt = stmt.where(Symbol.name == name)
        if symbol_type:
            stmt = stmt.where(Symbol.symbol_type == symbol_type)
        stmt = stmt.order_by(Symbol.id.asc()).offset(skip).limit(limit)
        return db.scalars(stmt).all()

    def get_symbol(self, db: Session, symbol_id: int) -> Symbol | None:
        stmt = (
            select(Symbol)
            .options(
                selectinload(Symbol.file).selectinload(FileRecord.repository_version),
                selectinload(Symbol.parent_symbol),
            )
            .where(Symbol.id == symbol_id)
        )
        return db.scalars(stmt).first()

    def get_symbol_callers(self, db: Session, symbol_id: int) -> Sequence[Dependency]:
        stmt = (
            select(Dependency)
            .options(
                selectinload(Dependency.caller_symbol).selectinload(Symbol.file),
                selectinload(Dependency.source_file),
            )
            .where(
                Dependency.relationship_type == "CALL",
                Dependency.callee_symbol_id == symbol_id,
                Dependency.resolution_status == "RESOLVED",
            )
            .order_by(Dependency.line_number.asc().nulls_last(), Dependency.id.asc())
        )
        return db.scalars(stmt).all()

    def get_symbol_callees(self, db: Session, symbol_id: int) -> Sequence[Dependency]:
        stmt = (
            select(Dependency)
            .options(
                selectinload(Dependency.callee_symbol).selectinload(Symbol.file),
                selectinload(Dependency.source_file),
            )
            .where(
                Dependency.relationship_type == "CALL",
                Dependency.caller_symbol_id == symbol_id,
            )
            .order_by(Dependency.line_number.asc().nulls_last(), Dependency.id.asc())
        )
        return db.scalars(stmt).all()

    def get_symbol_dependencies(self, db: Session, symbol_id: int) -> Sequence[Dependency]:
        stmt = (
            select(Dependency)
            .options(
                selectinload(Dependency.callee_symbol).selectinload(Symbol.file),
                selectinload(Dependency.source_file),
            )
            .where(Dependency.caller_symbol_id == symbol_id)
            .order_by(Dependency.line_number.asc().nulls_last(), Dependency.id.asc())
        )
        return db.scalars(stmt).all()

    def get_version_graph_entities(
        self, db: Session, version_id: int
    ) -> tuple[Sequence[FileRecord], Sequence[Symbol], Sequence[Dependency]]:
        files_stmt = (
            select(FileRecord)
            .where(FileRecord.repository_version_id == version_id)
            .order_by(FileRecord.path.asc())
        )
        files = db.scalars(files_stmt).all()

        symbols_stmt = (
            select(Symbol)
            .join(FileRecord, Symbol.file_id == FileRecord.id)
            .where(FileRecord.repository_version_id == version_id)
            .order_by(Symbol.id.asc())
        )
        symbols = db.scalars(symbols_stmt).all()

        deps_stmt = (
            select(Dependency)
            .where(Dependency.repository_version_id == version_id)
            .order_by(Dependency.id.asc())
        )
        deps = db.scalars(deps_stmt).all()

        return files, symbols, deps

    # 4. Dependencies
    def list_dependencies(
        self,
        db: Session,
        version_id: int,
        *,
        relationship_type: str | None = None,
        resolution_status: str | None = None,
        source_file_id: int | None = None,
        caller_symbol_id: int | None = None,
        callee_name: str | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[Dependency]:
        stmt = select(Dependency).where(Dependency.repository_version_id == version_id)
        if relationship_type:
            stmt = stmt.where(Dependency.relationship_type == relationship_type)
        if resolution_status:
            stmt = stmt.where(Dependency.resolution_status == resolution_status)
        if source_file_id is not None:
            stmt = stmt.where(Dependency.source_file_id == source_file_id)
        if caller_symbol_id is not None:
            stmt = stmt.where(Dependency.caller_symbol_id == caller_symbol_id)
        if callee_name:
            stmt = stmt.where(Dependency.callee_name == callee_name)
        stmt = stmt.order_by(Dependency.id.asc()).offset(skip).limit(limit)
        return db.scalars(stmt).all()

    # 5. Analysis Jobs
    def create_job(self, db: Session, repository_id: int) -> AnalysisJob:
        job = AnalysisJob(
            repository_id=repository_id,
            status="PENDING",
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def get_job(self, db: Session, repository_id: int, job_id: int) -> AnalysisJob | None:
        stmt = (
            select(AnalysisJob)
            .where(AnalysisJob.id == job_id, AnalysisJob.repository_id == repository_id)
        )
        return db.scalars(stmt).first()

    def list_jobs(
        self, db: Session, repository_id: int, *, skip: int = 0, limit: int = 100
    ) -> Sequence[AnalysisJob]:
        stmt = (
            select(AnalysisJob)
            .where(AnalysisJob.repository_id == repository_id)
            .order_by(AnalysisJob.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return db.scalars(stmt).all()

    def update_job_running(self, db: Session, job: AnalysisJob) -> AnalysisJob:
        job.status = "RUNNING"
        job.started_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def update_job_completed(
        self, db: Session, job: AnalysisJob, repository_version_id: int
    ) -> AnalysisJob:
        job.status = "COMPLETED"
        job.repository_version_id = repository_version_id
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    def update_job_failed(
        self, db: Session, job: AnalysisJob, error_message: str
    ) -> AnalysisJob:
        job.status = "FAILED"
        job.error_message = error_message
        job.completed_at = datetime.now(timezone.utc)
        db.add(job)
        db.commit()
        db.refresh(job)
        return job


code_intel_repository = CodeIntelligenceRepository()
