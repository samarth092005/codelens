from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field, computed_field


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


# --- Sprint 4: Change Impact Intelligence Schemas ---


class ImpactEvidence(BaseModel):
    call_chain: list[str]  # e.g. ["calculate_tax", "InvoiceService.process_invoice", "test_process"]
    hops: int
    call_line_numbers: list[int] = Field(default_factory=list)
    reason: str


class AffectedSymbolItem(BaseModel):
    symbol_id: int
    name: str
    qualified_name: str
    symbol_type: str
    file_id: int
    file_path: str
    line_start: int
    line_end: int
    impact_type: str  # "DIRECT" or "TRANSITIVE"
    hops: int
    relationship_type: str = "CALL"
    resolution_status: str = "RESOLVED"
    evidence: ImpactEvidence

    @computed_field
    @property
    def distance(self) -> int:
        return self.hops


class AffectedFileItem(BaseModel):
    file_id: int
    file_path: str
    language: str
    impact_type: str  # "DIRECT" or "TRANSITIVE"
    min_hops: int
    affected_symbol_count: int
    affected_symbol_ids: list[int]

    @computed_field
    @property
    def path(self) -> str:
        return self.file_path


class TestImpactItem(BaseModel):
    symbol_id: int
    name: str
    qualified_name: str
    file_id: int
    file_path: str
    impact_type: str  # "DIRECT" or "TRANSITIVE"
    hops: int
    evidence: ImpactEvidence


class ApiImpactItem(BaseModel):
    symbol_id: int
    name: str
    qualified_name: str
    file_id: int
    file_path: str
    impact_type: str  # "DIRECT" or "TRANSITIVE"
    hops: int
    evidence: ImpactEvidence


class DatabaseImpactItem(BaseModel):
    symbol_id: int
    name: str
    qualified_name: str
    file_id: int
    file_path: str
    operation: str  # "DATABASE_OPERATION"
    impact_type: str  # "DIRECT" or "TRANSITIVE"
    hops: int
    evidence: ImpactEvidence


class ImpactAnalysisResponse(BaseModel):
    changed_symbol: SymbolDetailResponse
    repository_id: int
    repository_version_id: int
    max_depth: int
    total_affected_symbols: int
    total_affected_files: int
    direct_callers_count: int
    transitive_callers_count: int
    affected_symbols: list[AffectedSymbolItem]
    affected_files: list[AffectedFileItem]
    affected_tests: list[TestImpactItem]
    affected_apis: list[ApiImpactItem]
    affected_databases: list[DatabaseImpactItem]


# --- Sprint 5: Git Evolution & Commit Impact Schemas ---


class CommitSummaryResponse(BaseModel):
    id: int
    repository_id: int
    repository_version_id: int | None = None
    commit_hash: str
    parent_hash: str | None = None
    author_name: str
    author_email: str
    commit_message: str | None = None
    committed_at: datetime
    changed_files_count: int = 0
    total_additions: int = 0
    total_deletions: int = 0

    @computed_field
    @property
    def files_changed_count(self) -> int:
        return self.changed_files_count

    @computed_field
    @property
    def insertions(self) -> int:
        return self.total_additions

    @computed_field
    @property
    def deletions(self) -> int:
        return self.total_deletions

    model_config = ConfigDict(from_attributes=True)


class CommitSymbolChangeItem(BaseModel):
    id: int
    symbol_id: int | None = None
    symbol_name: str
    qualified_name: str
    symbol_type: str
    change_type: str  # ADDED, MODIFIED, DELETED
    old_line_start: int | None = None
    old_line_end: int | None = None
    new_line_start: int | None = None
    new_line_end: int | None = None
    changed_lines_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class CommitFileChangeItem(BaseModel):
    id: int
    file_id: int | None = None
    file_path: str
    old_path: str | None = None
    change_type: str  # ADDED, MODIFIED, DELETED, RENAMED
    additions: int
    deletions: int
    changed_symbols: list[CommitSymbolChangeItem] = Field(default_factory=list)

    @computed_field
    @property
    def insertions(self) -> int:
        return self.additions

    model_config = ConfigDict(from_attributes=True)


class CommitDetailResponse(BaseModel):
    id: int
    repository_id: int
    repository_version_id: int | None = None
    commit_hash: str
    parent_hash: str | None = None
    author_name: str
    author_email: str
    commit_message: str | None = None
    committed_at: datetime
    changed_files: list[CommitFileChangeItem] = Field(default_factory=list)
    total_files_changed: int
    total_symbols_changed: int
    total_additions: int
    total_deletions: int

    @computed_field
    @property
    def files(self) -> list[CommitFileChangeItem]:
        return self.changed_files

    @computed_field
    @property
    def symbols(self) -> list[CommitSymbolChangeItem]:
        return [sym for fc in self.changed_files for sym in fc.changed_symbols]

    @computed_field
    @property
    def files_changed_count(self) -> int:
        return self.total_files_changed

    @computed_field
    @property
    def insertions(self) -> int:
        return self.total_additions

    @computed_field
    @property
    def deletions(self) -> int:
        return self.total_deletions

    model_config = ConfigDict(from_attributes=True)


class FileHistoryItem(BaseModel):
    commit_hash: str
    commit_message: str | None = None
    author_name: str
    author_email: str
    committed_at: datetime
    change_type: str
    old_path: str | None = None
    additions: int
    deletions: int
    changed_symbols_count: int = 0
    changed_symbols: list[str] = Field(default_factory=list)


class FileHistoryResponse(BaseModel):
    file_id: int
    file_path: str
    repository_id: int | None = None
    history: list[FileHistoryItem]
    total_commits: int
    total_insertions: int = 0
    total_deletions: int = 0


class SymbolHistoryItem(BaseModel):
    commit_hash: str
    commit_message: str | None = None
    author_name: str
    author_email: str
    committed_at: datetime
    change_type: str  # ADDED, MODIFIED, DELETED
    old_line_start: int | None = None
    old_line_end: int | None = None
    new_line_start: int | None = None
    new_line_end: int | None = None
    changed_lines_count: int = 0
    evidence: str


class SymbolHistoryResponse(BaseModel):
    symbol_id: int
    symbol_name: str
    qualified_name: str
    file_path: str
    symbol_type: str | None = None
    repository_id: int | None = None
    history: list[SymbolHistoryItem]
    total_commits: int
    introduced_at: datetime | None = None
    last_modified_at: datetime | None = None

    @computed_field
    @property
    def name(self) -> str:
        return self.symbol_name


class CommitImpactResponse(BaseModel):
    commit_hash: str
    repository_id: int
    repository_version_id: int | None = None
    commit_message: str | None = None
    changed_symbols: list[CommitSymbolChangeItem]
    total_changed_symbols: int = 0
    total_directly_affected: int = 0
    total_transitively_affected: int = 0
    total_affected_files: int = 0
    directly_affected: list[AffectedSymbolItem] = Field(default_factory=list)
    transitively_affected: list[AffectedSymbolItem] = Field(default_factory=list)
    unresolved_affected: list[AffectedSymbolItem] = Field(default_factory=list)
    affected_symbols: list[AffectedSymbolItem] = Field(default_factory=list)
    affected_files: list[AffectedFileItem] = Field(default_factory=list)
    affected_tests: list[TestImpactItem] = Field(default_factory=list)
    direct_callers_count: int = 0
    transitive_callers_count: int = 0
    affected_symbols_count: int = 0
    affected_files_count: int = 0

    @computed_field
    @property
    def changed_symbols_count(self) -> int:
        return self.total_changed_symbols

