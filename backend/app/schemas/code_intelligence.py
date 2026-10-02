from datetime import datetime
from typing import Any
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


# --- Sprint 3: Navigation & Graph Schemas ---


class SymbolDetailResponse(BaseModel):
    id: int
    repository_id: int
    repository_version_id: int
    file_id: int
    file_path: str
    name: str
    qualified_name: str
    symbol_type: str
    language: str
    line_start: int
    line_end: int
    parent_symbol_id: int | None = None
    parent_symbol_name: str | None = None
    visibility: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CallerResponse(BaseModel):
    dependency_id: int
    caller_symbol_id: int
    caller_name: str
    caller_qualified_name: str
    caller_symbol_type: str
    caller_file_id: int
    caller_file_path: str
    line_number: int | None = None

    model_config = ConfigDict(from_attributes=True)


class CalleeResponse(BaseModel):
    dependency_id: int
    callee_name: str
    callee_symbol_id: int | None = None
    callee_qualified_name: str | None = None
    callee_symbol_type: str | None = None
    callee_file_id: int | None = None
    callee_file_path: str | None = None
    resolution_status: str
    line_number: int | None = None

    model_config = ConfigDict(from_attributes=True)


class SymbolDependencyItem(BaseModel):
    dependency_id: int
    relationship_type: str
    target_symbol_id: int | None = None
    target_name: str | None = None
    resolution_status: str
    line_number: int | None = None

    model_config = ConfigDict(from_attributes=True)


class FileDetailResponse(BaseModel):
    id: int
    repository_id: int
    repository_version_id: int
    path: str
    extension: str
    language: str
    size_bytes: int
    parsing_status: str
    error_message: str | None = None
    symbols_count: int = 0
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileDependencyItem(BaseModel):
    dependency_id: int
    target_file_id: int | None = None
    target_file_path: str | None = None
    imported_module: str | None = None
    import_type: str | None = None
    resolution_status: str
    line_number: int | None = None

    model_config = ConfigDict(from_attributes=True)


class FileDependentItem(BaseModel):
    dependency_id: int
    source_file_id: int
    source_file_path: str
    imported_module: str | None = None
    import_type: str | None = None
    line_number: int | None = None

    model_config = ConfigDict(from_attributes=True)


class GraphNode(BaseModel):
    id: str  # e.g. "symbol:10" or "file:2"
    type: str  # "SYMBOL" or "FILE"
    label: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relationship: str  # "CALL" or "IMPORT"
    metadata: dict[str, Any] = Field(default_factory=dict)


class GraphResponse(BaseModel):
    repository_id: int
    repository_version_id: int
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    total_nodes: int
    total_edges: int


class SymbolPathStep(BaseModel):
    id: int
    name: str
    qualified_name: str
    symbol_type: str
    file_path: str
    line_start: int
    line_end: int


class SymbolPathsResponse(BaseModel):
    source_symbol_id: int
    target_symbol_id: int
    paths: list[list[SymbolPathStep]]
    paths_count: int


class ArchitectureModule(BaseModel):
    name: str
    path: str
    files: list[str]
    files_count: int
    symbols_count: int


class ArchitectureResponse(BaseModel):
    repository_id: int
    repository_version_id: int
    commit_sha: str
    modules: list[ArchitectureModule]
    total_files: int
    total_symbols: int
    total_dependencies: int
    languages: dict[str, int]
