from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    username: str = Field(..., min_length=3, max_length=100, description="Unique username")
    full_name: str | None = Field(default=None, max_length=255, description="Full name")
    is_active: bool = Field(default=True, description="Whether the user account is active")


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=255)
    username: str | None = Field(default=None, min_length=3, max_length=100)
    full_name: str | None = Field(default=None, max_length=255)
    is_active: bool | None = None


class UserResponse(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
