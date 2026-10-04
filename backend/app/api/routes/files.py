from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.code_intelligence import (
    FileDependencyItem,
    FileDependentItem,
    FileDetailResponse,
    FileHistoryResponse,
)
from app.services.code_intelligence.evolution_service import (
    GitEvolutionService,
    git_evolution_service,
)
from app.services.code_intelligence.graph_service import (
    GraphService,
    graph_service,
)

router = APIRouter(prefix="/files", tags=["files"])


@router.get(
    "/{file_id}",
    response_model=FileDetailResponse,
    summary="Get file details",
)
def get_file(
    file_id: int,
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Retrieve detailed file metadata and symbol counts."""
    return service.get_file(db, file_id=file_id)


@router.get(
    "/{file_id}/dependencies",
    response_model=list[FileDependencyItem],
    summary="Get file dependencies (imports)",
)
def get_file_dependencies(
    file_id: int,
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Retrieve all internal and external dependencies imported by this file."""
    return service.get_file_dependencies(db, file_id=file_id)


@router.get(
    "/{file_id}/dependents",
    response_model=list[FileDependentItem],
    summary="Get file dependents (files importing this file)",
)
def get_file_dependents(
    file_id: int,
    db: Session = Depends(get_db),
    service: GraphService = Depends(lambda: graph_service),
):
    """Retrieve all files in the repository that depend on / import this file."""
    return service.get_file_dependents(db, file_id=file_id)


@router.get(
    "/{file_id}/history",
    response_model=FileHistoryResponse,
    summary="Get file commit history",
)
def get_file_history(
    file_id: int,
    db: Session = Depends(get_db),
    evolution_svc: GitEvolutionService = Depends(lambda: git_evolution_service),
):
    """Retrieve commit evolution history and symbol changes for a file."""
    return evolution_svc.get_file_history(db, file_id=file_id)

