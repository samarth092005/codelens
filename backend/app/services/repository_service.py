from collections.abc import Sequence
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.repository import Repository
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository as default_repo_repo,
)
from app.repositories.user_repository import (
    UserRepository,
    user_repository as default_user_repo,
)
from app.schemas.repository import RepositoryCreate, RepositoryUpdate


class RepositoryService:
    def __init__(
        self,
        repo_repo: RepositoryRepository = default_repo_repo,
        user_repo: UserRepository = default_user_repo,
    ):
        self.repo_repo = repo_repo
        self.user_repo = user_repo

    def get_repository(self, db: Session, repo_id: int) -> Repository:
        repo = self.repo_repo.get(db, id=repo_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repo_id} not found",
            )
        return repo

    def list_repositories(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> Sequence[Repository]:
        return self.repo_repo.get_multi(db, skip=skip, limit=limit)

    def create_repository(
        self, db: Session, *, repo_in: RepositoryCreate
    ) -> Repository:
        # Check if URL already registered
        existing_repo = self.repo_repo.get_by_url(db, url=repo_in.url)
        if existing_repo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A repository with this URL is already registered",
            )

        # Check if owner exists if owner_id is provided
        if repo_in.owner_id is not None:
            owner = self.user_repo.get(db, id=repo_in.owner_id)
            if not owner:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"User with id {repo_in.owner_id} not found",
                )

        return self.repo_repo.create(db, obj_in=repo_in)

    def update_repository(
        self, db: Session, *, repo_id: int, repo_in: RepositoryUpdate
    ) -> Repository:
        repo = self.get_repository(db, repo_id=repo_id)
        return self.repo_repo.update(db, db_obj=repo, obj_in=repo_in)

    def delete_repository(self, db: Session, *, repo_id: int) -> Repository:
        repo = self.get_repository(db, repo_id=repo_id)
        self.repo_repo.delete(db, id=repo_id)
        return repo


repository_service = RepositoryService()
