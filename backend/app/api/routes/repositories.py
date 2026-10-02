from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.repository import (
    RepositoryCreate,
    RepositoryResponse,
    RepositoryUpdate,
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
