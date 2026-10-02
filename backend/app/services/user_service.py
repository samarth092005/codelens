from collections.abc import Sequence
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models.user import User
from app.repositories.user_repository import (
    UserRepository,
    user_repository as default_user_repo,
)
from app.schemas.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, user_repo: UserRepository = default_user_repo):
        self.user_repo = user_repo

    def get_user(self, db: Session, user_id: int) -> User:
        user = self.user_repo.get(db, id=user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id {user_id} not found",
            )
        return user

    def list_users(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> Sequence[User]:
        return self.user_repo.get_multi(db, skip=skip, limit=limit)

    def create_user(self, db: Session, *, user_in: UserCreate) -> User:
        if self.user_repo.get_by_email(db, email=user_in.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists",
            )
        if self.user_repo.get_by_username(db, username=user_in.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this username already exists",
            )
        return self.user_repo.create(db, obj_in=user_in)

    def update_user(
        self, db: Session, *, user_id: int, user_in: UserUpdate
    ) -> User:
        user = self.get_user(db, user_id=user_id)
        if user_in.email and user_in.email != user.email:
            if self.user_repo.get_by_email(db, email=user_in.email):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this email already exists",
                )
        if user_in.username and user_in.username != user.username:
            if self.user_repo.get_by_username(db, username=user_in.username):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A user with this username already exists",
                )
        return self.user_repo.update(db, db_obj=user, obj_in=user_in)

    def delete_user(self, db: Session, *, user_id: int) -> User:
        user = self.get_user(db, user_id=user_id)
        self.user_repo.delete(db, id=user_id)
        return user


user_service = UserService()
