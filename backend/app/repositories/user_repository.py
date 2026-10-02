from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.user import UserCreate, UserUpdate


class UserRepository:
    def get(self, db: Session, id: int) -> User | None:
        statement = select(User).where(User.id == id)
        return db.scalars(statement).first()

    def get_by_email(self, db: Session, email: str) -> User | None:
        statement = select(User).where(User.email == email)
        return db.scalars(statement).first()

    def get_by_username(self, db: Session, username: str) -> User | None:
        statement = select(User).where(User.username == username)
        return db.scalars(statement).first()

    def get_multi(
        self, db: Session, *, skip: int = 0, limit: int = 100
    ) -> Sequence[User]:
        statement = select(User).offset(skip).limit(limit).order_by(User.id.desc())
        return db.scalars(statement).all()

    def create(self, db: Session, *, obj_in: UserCreate) -> User:
        db_obj = User(
            email=obj_in.email,
            username=obj_in.username,
            full_name=obj_in.full_name,
            is_active=obj_in.is_active,
        )
        db.add(db_obj)
        db.commit()
        db.refresh(db_obj)
        return db_obj

    def update(
        self,
        db: Session,
        *,
        db_obj: User,
        obj_in: UserUpdate | dict,
    ) -> User:
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

    def delete(self, db: Session, *, id: int) -> User | None:
        obj = self.get(db, id=id)
        if obj is not None:
            db.delete(obj)
            db.commit()
        return obj


user_repository = UserRepository()
