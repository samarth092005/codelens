from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user_service import UserService, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user",
)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    service: UserService = Depends(lambda: user_service),
):
    """Create a new user."""
    return service.create_user(db, user_in=user_in)


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List users",
)
def list_users(
    skip: int = Query(default=0, ge=0, description="Offset for pagination"),
    limit: int = Query(default=100, ge=1, le=500, description="Page size limit"),
    db: Session = Depends(get_db),
    service: UserService = Depends(lambda: user_service),
):
    """Retrieve a paginated list of users."""
    return service.list_users(db, skip=skip, limit=limit)


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user by ID",
)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    service: UserService = Depends(lambda: user_service),
):
    """Get detailed information for a specific user."""
    return service.get_user(db, user_id=user_id)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user",
)
def update_user(
    user_id: int,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    service: UserService = Depends(lambda: user_service),
):
    """Update user information."""
    return service.update_user(db, user_id=user_id, user_in=user_in)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user",
)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    service: UserService = Depends(lambda: user_service),
):
    """Delete a user."""
    service.delete_user(db, user_id=user_id)
    return None
