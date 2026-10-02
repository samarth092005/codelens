from collections.abc import Sequence
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.analysis_job import AnalysisJob
from app.models.dependency import Dependency
from app.models.file_record import FileRecord
from app.models.repository_version import RepositoryVersion
from app.models.symbol import Symbol
from app.repositories.code_intelligence_repository import (
    CodeIntelligenceRepository,
    code_intel_repository as default_code_intel_repo,
)
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository as default_repo_repo,
)
from app.services.code_intelligence.ingestion_service import (
    RepositoryIngestionService,
    repository_ingestion_service as default_ingestion_svc,
)


class RepositoryAnalysisService:
    """Service orchestrating analysis jobs and querying code intelligence graphs."""

    def __init__(
        self,
        code_intel_repo: CodeIntelligenceRepository = default_code_intel_repo,
        repo_repo: RepositoryRepository = default_repo_repo,
        ingestion_svc: RepositoryIngestionService = default_ingestion_svc,
    ) -> None:
        self.code_intel_repo = code_intel_repo
        self.repo_repo = repo_repo
        self.ingestion_svc = ingestion_svc

    def trigger_analysis(
        self,
        db: Session,
        *,
        repository_id: int,
        custom_repo_path: str | None = None,
    ) -> AnalysisJob:
        """Trigger code analysis for a repository."""
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        job = self.code_intel_repo.create_job(db, repository_id=repository_id)
        self.code_intel_repo.update_job_running(db, job)

        try:
            result = self.ingestion_svc.ingest_repository(
                db=db,
                repository=repo,
                custom_repo_path=custom_repo_path,
            )
            return self.code_intel_repo.update_job_completed(
                db=db,
                job=job,
                repository_version_id=result.repository_version_id,
            )
        except Exception as e:
            self.code_intel_repo.update_job_failed(db=db, job=job, error_message=str(e))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Analysis failed: {e}",
            )

    def get_job(self, db: Session, *, repository_id: int, job_id: int) -> AnalysisJob:
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        job = self.code_intel_repo.get_job(db, repository_id=repository_id, job_id=job_id)
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Analysis job with id {job_id} not found for repository {repository_id}",
            )
        return job

    def list_jobs(
        self, db: Session, *, repository_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[AnalysisJob]:
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )
        return self.code_intel_repo.list_jobs(db, repository_id=repository_id, skip=skip, limit=limit)

    def list_versions(
        self, db: Session, *, repository_id: int, skip: int = 0, limit: int = 100
    ) -> Sequence[RepositoryVersion]:
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )
        return self.code_intel_repo.list_versions(db, repository_id=repository_id, skip=skip, limit=limit)

    def _resolve_version_id(self, db: Session, repository_id: int, version_id: int | None) -> int | None:
        if version_id is not None:
            return version_id
        latest = self.code_intel_repo.get_latest_version(db, repository_id=repository_id)
        return latest.id if latest else None

    def get_files(
        self,
        db: Session,
        *,
        repository_id: int,
        version_id: int | None = None,
        language: str | None = None,
        parsing_status: str | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[FileRecord]:
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        target_version_id = self._resolve_version_id(db, repository_id, version_id)
        if not target_version_id:
            return []

        return self.code_intel_repo.list_files(
            db,
            version_id=target_version_id,
            language=language,
            parsing_status=parsing_status,
            skip=skip,
            limit=limit,
        )

    def get_symbols(
        self,
        db: Session,
        *,
        repository_id: int,
        version_id: int | None = None,
        file_id: int | None = None,
        name: str | None = None,
        symbol_type: str | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[Symbol]:
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        target_version_id = self._resolve_version_id(db, repository_id, version_id)
        if not target_version_id:
            return []

        return self.code_intel_repo.list_symbols(
            db,
            version_id=target_version_id,
            file_id=file_id,
            name=name,
            symbol_type=symbol_type,
            skip=skip,
            limit=limit,
        )

    def get_dependencies(
        self,
        db: Session,
        *,
        repository_id: int,
        version_id: int | None = None,
        relationship_type: str | None = None,
        resolution_status: str | None = None,
        source_file_id: int | None = None,
        caller_symbol_id: int | None = None,
        callee_name: str | None = None,
        skip: int = 0,
        limit: int = 200,
    ) -> Sequence[Dependency]:
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        target_version_id = self._resolve_version_id(db, repository_id, version_id)
        if not target_version_id:
            return []

        return self.code_intel_repo.list_dependencies(
            db,
            version_id=target_version_id,
            relationship_type=relationship_type,
            resolution_status=resolution_status,
            source_file_id=source_file_id,
            caller_symbol_id=caller_symbol_id,
            callee_name=callee_name,
            skip=skip,
            limit=limit,
        )


repository_analysis_service = RepositoryAnalysisService()
