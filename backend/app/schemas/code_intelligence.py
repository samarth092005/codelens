from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class AnalysisTriggerRequest(BaseModel):
    repo_path: str | None = Field(
        default=None,
        description="Optional local filesystem path override for repository analysis",
    )


class AnalysisJobResponse(BaseModel):
    id: int
    repository_id: int
    repository_version_id: int | None = None
    status: str
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RepositoryVersionResponse(BaseModel):
    id: int
    repository_id: int
    commit_sha: str
    branch_name: str
    commit_message: str | None = None
    analyzed_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileResponse(BaseModel):
    id: int
    repository_version_id: int
    path: str
    extension: str
    language: str
    size_bytes: int
    parsing_status: str
    error_message: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SymbolResponse(BaseModel):
    id: int
    file_id: int
    name: str
    qualified_name: str
    symbol_type: str
    parent_symbol_id: int | None = None
    line_start: int
    line_end: int
    visibility: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DependencyResponse(BaseModel):
    id: int
    repository_version_id: int
    relationship_type: str
    source_file_id: int | None = None
    target_file_id: int | None = None
    caller_symbol_id: int | None = None
    callee_symbol_id: int | None = None
    callee_name: str | None = None
    imported_module: str | None = None
    import_type: str | None = None
    line_number: int | None = None
    resolution_status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
