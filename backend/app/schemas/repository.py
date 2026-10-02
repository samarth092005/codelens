from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class RepositoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Repository name")
    url: str = Field(..., min_length=1, max_length=512, description="Git clone URL or repository URL")
    description: str | None = Field(default=None, max_length=1000, description="Optional repository description")
    is_private: bool = Field(default=False, description="Whether the repository is private")
    default_branch: str = Field(default="main", max_length=100, description="Default git branch")


class RepositoryCreate(RepositoryBase):
    owner_id: int | None = Field(default=None, description="Optional ID of the user who owns this repository")


class RepositoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    is_private: bool | None = None
    default_branch: str | None = Field(default=None, max_length=100)
    status: str | None = Field(default=None, max_length=50)


class RepositoryResponse(RepositoryBase):
    id: int
    status: str = Field(default="pending", description="Ingestion/analysis status")
    owner_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
