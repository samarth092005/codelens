from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.code_intelligence import (
    AnalysisJobResponse,
    AnalysisTriggerRequest,
    ArchitectureResponse,
    CommitDetailResponse,
    CommitImpactResponse,
    CommitSummaryResponse,
    DependencyResponse,
    FileResponse,
    GraphResponse,
    RepositoryVersionResponse,
    SymbolResponse,
)
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryResponse,
    RepositoryUpdate,
)
from app.services.code_intelligence.analysis_service import (
    RepositoryAnalysisService,
    repository_analysis_service,
)
from app.services.code_intelligence.evolution_service import (
    GitEvolutionService,
    git_evolution_service,
)
from app.services.code_intelligence.graph_service import (
    GraphService,
    graph_service,
)
from app.services.repository_service import (
    RepositoryService,
    repository_service,
)

router = APIRouter(prefix="/repositories", tags=["repositories"])


@router.post(
    "",
    response_model=RepositoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a repository",
)
def create_repository(
    repo_in: RepositoryCreate,
    db: Session = Depends(get_db),
    service: RepositoryService = Depends(lambda: repository_service),
):
    """Register a new repository in CodeLens."""
    return service.create_repository(db, repo_in=repo_in)


@router.get(
    "",
    response_model=list[RepositoryResponse],
    summary="List repositories",
)
def list_repositories(
    skip: int = Query(default=0, ge=0, description="Offset for pagination"),
    limit: int = Query(default=100, ge=1, le=500, description="Page size limit"),
    db: Session = Depends(get_db),
    service: RepositoryService = Depends(lambda: repository_service),
):
    """Retrieve a paginated list of repositories."""
    return service.list_repositories(db, skip=skip, limit=limit)


@router.get(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Get repository by ID",
)
def get_repository(
    repository_id: int,
    db: Session = Depends(get_db),
    service: RepositoryService = Depends(lambda: repository_service),
):
    """Get detailed information for a specific repository."""
    return service.get_repository(db, repo_id=repository_id)


@router.patch(
    "/{repository_id}",
    response_model=RepositoryResponse,
    summary="Update repository",
)
def update_repository(
    repository_id: int,
    repo_in: RepositoryUpdate,
    db: Session = Depends(get_db),
    service: RepositoryService = Depends(lambda: repository_service),
):
    """Update metadata for an existing repository."""
    return service.update_repository(db, repo_id=repository_id, repo_in=repo_in)


@router.delete(
    "/{repository_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete repository",
)
def delete_repository(
    repository_id: int,
    db: Session = Depends(get_db),
    service: RepositoryService = Depends(lambda: repository_service),
):
    """Delete a repository from CodeLens."""
    service.delete_repository(db, repo_id=repository_id)
    return None


# --- Sprint 2 Code Intelligence & Analysis Endpoints ---


@router.post(
    "/{repository_id}/analysis",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Trigger repository analysis",
)
def trigger_analysis(
    repository_id: int,
    trigger_req: AnalysisTriggerRequest | None = None,
    db: Session = Depends(get_db),
    analysis_svc: RepositoryAnalysisService = Depends(lambda: repository_analysis_service),
):
    """Trigger static code analysis and structural intelligence ingestion for a repository."""
    custom_path = trigger_req.repo_path if trigger_req else None
    return analysis_svc.trigger_analysis(
        db,
        repository_id=repository_id,
        custom_repo_path=custom_path,
    )


@router.get(
    "/{repository_id}/analysis",
    response_model=list[AnalysisJobResponse],
    summary="List analysis jobs for repository",
)
def list_analysis_jobs(
    repository_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    analysis_svc: RepositoryAnalysisService = Depends(lambda: repository_analysis_service),
):
    """Retrieve all analysis jobs for a given repository."""
    return analysis_svc.list_jobs(db, repository_id=repository_id, skip=skip, limit=limit)


@router.get(
    "/{repository_id}/analysis/{job_id}",
    response_model=AnalysisJobResponse,
    summary="Get analysis job status",
)
def get_analysis_job(
    repository_id: int,
    job_id: int,
    db: Session = Depends(get_db),
    analysis_svc: RepositoryAnalysisService = Depends(lambda: repository_analysis_service),
):
    """Get the current status and results of a specific analysis job."""
    return analysis_svc.get_job(db, repository_id=repository_id, job_id=job_id)


@router.get(
    "/{repository_id}/versions",
    response_model=list[RepositoryVersionResponse],
    summary="List analyzed repository versions",
)
def list_versions(
    repository_id: int,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    analysis_svc: RepositoryAnalysisService = Depends(lambda: repository_analysis_service),
):
    """List all analyzed versions for a repository."""
    return analysis_svc.list_versions(db, repository_id=repository_id, skip=skip, limit=limit)


@router.get(
    "/{repository_id}/files",
    response_model=list[FileResponse],
    summary="Get repository files",
)
def get_files(
    repository_id: int,
    version_id: int | None = Query(default=None, description="Repository version ID (defaults to latest)"),
    language: str | None = Query(default=None, description="Filter by language"),
    parsing_status: str | None = Query(default=None, description="Filter by parsing status"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    analysis_svc: RepositoryAnalysisService = Depends(lambda: repository_analysis_service),
):
    """Retrieve discovered source files for a repository version."""
    return analysis_svc.get_files(
        db,
        repository_id=repository_id,
        version_id=version_id,
        language=language,
        parsing_status=parsing_status,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{repository_id}/symbols",
    response_model=list[SymbolResponse],
    summary="Get repository symbols",
)
def get_symbols(
    repository_id: int,
    version_id: int | None = Query(default=None, description="Repository version ID (defaults to latest)"),
    file_id: int | None = Query(default=None, description="Filter by file ID"),
    name: str | None = Query(default=None, description="Filter by symbol name"),
    symbol_type: str | None = Query(default=None, description="Filter by symbol type (function, class, method)"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    analysis_svc: RepositoryAnalysisService = Depends(lambda: repository_analysis_service),
):
    """Retrieve extracted symbols (functions, classes, methods) for a repository version."""
    return analysis_svc.get_symbols(
        db,
        repository_id=repository_id,
        version_id=version_id,
        file_id=file_id,
        name=name,
        symbol_type=symbol_type,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{repository_id}/dependencies",
    response_model=list[DependencyResponse],
    summary="Get repository dependencies and call relationships",
)
def get_dependencies(
    repository_id: int,
    version_id: int | None = Query(default=None, description="Repository version ID (defaults to latest)"),
    relationship_type: str | None = Query(default=None, description="Filter by relationship type (IMPORT, CALL)"),
    resolution_status: str | None = Query(default=None, description="Filter by resolution status (RESOLVED, UNRESOLVED, EXTERNAL)"),
    source_file_id: int | None = Query(default=None, description="Filter by source file ID"),
    caller_symbol_id: int | None = Query(default=None, description="Filter by caller symbol ID"),
    callee_name: str | None = Query(default=None, description="Filter by callee name"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    analysis_svc: RepositoryAnalysisService = Depends(lambda: repository_analysis_service),
):
    """Retrieve dependency relationships (imports and calls) for a repository version."""
    return analysis_svc.get_dependencies(
        db,
        repository_id=repository_id,
        version_id=version_id,
        relationship_type=relationship_type,
        resolution_status=resolution_status,
        source_file_id=source_file_id,
        caller_symbol_id=caller_symbol_id,
        callee_name=callee_name,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/{repository_id}/graph",
    response_model=GraphResponse,
    summary="Get repository engineering graph",
)
def get_repository_graph(
    repository_id: int,
    version_id: int | None = Query(default=None, description="Repository version ID (defaults to latest)"),
    db: Session = Depends(get_db),
    graph_svc: GraphService = Depends(lambda: graph_service),
):
    """Retrieve deterministic node-and-edge engineering graph for a repository version."""
    return graph_svc.get_repository_graph(
        db,
        repository_id=repository_id,
        version_id=version_id,
    )


@router.get(
    "/{repository_id}/architecture",
    response_model=ArchitectureResponse,
    summary="Get repository architectural structure",
)
def get_repository_architecture(
    repository_id: int,
    version_id: int | None = Query(default=None, description="Repository version ID (defaults to latest)"),
    db: Session = Depends(get_db),
    graph_svc: GraphService = Depends(lambda: graph_service),
):
    """Derive repository architectural modules and aggregated engineering facts."""
    return graph_svc.get_architecture_data(
        db,
        repository_id=repository_id,
        version_id=version_id,
    )


@router.get(
    "/{repository_id}/commits",
    response_model=list[CommitSummaryResponse],
    summary="List repository commits",
)
def list_repository_commits(
    repository_id: int,
    skip: int = Query(default=0, ge=0, description="Offset for pagination"),
    limit: int = Query(default=100, ge=1, le=500, description="Page size limit"),
    db: Session = Depends(get_db),
    evolution_svc: GitEvolutionService = Depends(lambda: git_evolution_service),
):
    """Retrieve chronological Git commit history for a repository."""
    return evolution_svc.list_commits(db, repository_id=repository_id, skip=skip, limit=limit)


@router.get(
    "/{repository_id}/commits/{commit_hash}",
    response_model=CommitDetailResponse,
    summary="Get commit details",
)
def get_commit_details(
    repository_id: int,
    commit_hash: str,
    db: Session = Depends(get_db),
    evolution_svc: GitEvolutionService = Depends(lambda: git_evolution_service),
):
    """Retrieve detailed commit metadata, changed files, and changed symbols."""
    return evolution_svc.get_commit_details(
        db, repository_id=repository_id, commit_hash=commit_hash
    )


@router.get(
    "/{repository_id}/commits/{commit_hash}/impact",
    response_model=CommitImpactResponse,
    summary="Analyze commit impact",
)
def analyze_commit_impact(
    repository_id: int,
    commit_hash: str,
    db: Session = Depends(get_db),
    evolution_svc: GitEvolutionService = Depends(lambda: git_evolution_service),
):
    """Deterministically analyze callers and files potentially affected by changes in a commit."""
    return evolution_svc.analyze_commit_impact(
        db, repository_id=repository_id, commit_hash=commit_hash
    )

