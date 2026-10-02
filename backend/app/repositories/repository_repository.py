from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.repository import Repository
from app.schemas.repository import RepositoryCreate, RepositoryUpdate


class RepositoryRepository:
    def get(self, db: Session, id: int) -> Repository | None:
        statement = select(Repository).where(Repository.id == id)
        return db.scalars(statement).first()

    def get_by_url(self, db: Session, url: str) -> Repository | None:
        statement = select(Repository).where(Repository.url == url)
        return db.scalars(statement).first()

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> Sequence[Repository]:
        statement = select(Repository).offset(skip).limit(limit).order_by(Repository.id.desc())
        return db.scalars(statement).all()

    def create(self, db: Session, *, obj_in: RepositoryCreate) -> Repository:
        db_obj = Repository(
            name=obj_in.name,
            url=obj_in.url,
            description=obj_in.description,
            is_private=obj_in.is_private,
            default_branch=obj_in.default_branch,
            owner_id=obj_in.owner_id,
            status="pending",
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: Repository,
        obj_in: RepositoryUpdate | dict,
    ) -> Repository:
        if isinstance(obj_in, dict):
            update_data = obj_in
        else:
            update_data = obj_in.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(db_obj, field, value)

        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def delete(self, db: Session, *, id: int) -> Repository | None:
        obj = self.get(db, id=id)
        if obj is not None:
            db.delete(obj)
            db.commit()
        return obj


repository_repository = RepositoryRepository()
