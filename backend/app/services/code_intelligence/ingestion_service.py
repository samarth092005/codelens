import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy.orm import Session

from app.models.dependency import Dependency
from app.models.file_record import FileRecord
from app.models.repository import Repository
from app.models.repository_version import RepositoryVersion
from app.models.symbol import Symbol
from app.services.code_intelligence.evolution_service import GitEvolutionService, git_evolution_service
from app.services.code_intelligence.file_discovery import FileDiscoveryService, file_discovery_service
from app.services.code_intelligence.git_service import GitRepositoryError, GitService, git_service
from app.services.code_intelligence.parser import CompositeCodeParser, composite_parser
from app.services.code_intelligence.resolver import DependencyResolver, dependency_resolver

logger = logging.getLogger(__name__)


@dataclass
class IngestionResult:
    repository_id: int
    repository_version_id: int
    commit_sha: str
    branch_name: str
    files_count: int
    symbols_count: int
    dependencies_count: int
    calls_count: int


class RepositoryIngestionService:
    """Service orchestrating full repository ingestion and code intelligence extraction."""

    def __init__(
        self,
        git_svc: GitService = git_service,
        discovery_svc: FileDiscoveryService = file_discovery_service,
        parser_svc: CompositeCodeParser = composite_parser,
        resolver_svc: DependencyResolver = dependency_resolver,
        evolution_svc: GitEvolutionService = git_evolution_service,
    ) -> None:
        self.git_svc = git_svc
        self.discovery_svc = discovery_svc
        self.parser_svc = parser_svc
        self.resolver_svc = resolver_svc
        self.evolution_svc = evolution_svc

    def validate_and_resolve_path(self, repo_url_or_path: str) -> Path:
        """Validate and resolve a repository path safely.
        
        Ensures the path exists, is a directory, and contains a git repository.
        Rejects directory traversal tricks.
        """
        # Strip file:// prefix if present
        clean_path = repo_url_or_path
        if clean_path.startswith("file:///"):
            clean_path = clean_path[8:]
        elif clean_path.startswith("file://"):
            clean_path = clean_path[7:]

        p = Path(clean_path).resolve()
        if not p.exists() or not p.is_dir():
            raise ValueError(f"Repository path does not exist or is not a directory: {p}")

        if not self.git_svc.is_git_repository(p):
            raise GitRepositoryError(f"Directory is not a valid Git repository (missing .git): {p}")

        return p

    def ingest_repository(
        self,
        db: Session,
        repository: Repository,
        custom_repo_path: str | None = None,
    ) -> IngestionResult:
        """Execute full deterministic code analysis on a repository and persist to DB."""
        target_path_str = custom_repo_path or repository.url
        repo_path = self.validate_and_resolve_path(target_path_str)

        # 1. Safely extract Git metadata
        git_meta = self.git_svc.extract_metadata(repo_path)

        # 2. Create RepositoryVersion
        version = RepositoryVersion(
            repository_id=repository.id,
            commit_sha=git_meta.commit_sha,
            branch_name=git_meta.branch_name,
            commit_message=git_meta.commit_message,
        )
        db.add(version)
        db.flush()  # Obtain version.id

        # 3. Discover repository files
        discovered_files = self.discovery_svc.discover_files(repo_path)

        # 4. Persist FileRecord for all discovered files
        file_records_by_rel_path: dict[str, FileRecord] = {}
        for df in discovered_files:
            file_rec = FileRecord(
                repository_version_id=version.id,
                path=df.relative_path,
                extension=df.extension,
                language=df.language,
                size_bytes=df.size_bytes,
                parsing_status="UNPARSED" if df.is_supported else "UNSUPPORTED",
                error_message=None if df.is_supported else "Language not supported for AST parsing",
            )
            db.add(file_rec)
            file_records_by_rel_path[df.relative_path] = file_rec

        db.flush()

        # Build mapping dictionaries for parsing & resolution
        files_by_rel_path: dict[str, int] = {
            rel: rec.id for rel, rec in file_records_by_rel_path.items()
        }
        file_languages: dict[int, str] = {
            rec.id: rec.language for rec in file_records_by_rel_path.values()
        }

        # 5. Parse supported source files
        symbols_by_id: dict[int, dict] = {}
        symbols_by_file: dict[int, list[int]] = {rec.id: [] for rec in file_records_by_rel_path.values()}
        raw_imports: list[tuple[int, any]] = []
        raw_calls: list[tuple[int, any]] = []

        total_symbols_count = 0

        for df in discovered_files:
            if not df.is_supported:
                continue

            file_rec = file_records_by_rel_path[df.relative_path]

            try:
                source_bytes = df.path.read_bytes()
            except Exception as e:
                file_rec.parsing_status = "PARSE_ERROR"
                file_rec.error_message = f"Failed to read file: {e}"
                continue

            parse_res = self.parser_svc.parse(source_bytes, df.relative_path, df.language)
            file_rec.parsing_status = parse_res.status
            file_rec.error_message = parse_res.error_message

            # Insert symbols: classes first, then methods and functions
            # to properly link parent_symbol_id
            classes = [s for s in parse_res.symbols if s.symbol_type == "class"]
            others = [s for s in parse_res.symbols if s.symbol_type != "class"]

            class_id_by_qname: dict[str, int] = {}
            for cs in classes:
                sym = Symbol(
                    file_id=file_rec.id,
                    name=cs.name,
                    qualified_name=cs.qualified_name,
                    symbol_type=cs.symbol_type,
                    parent_symbol_id=None,
                    line_start=cs.line_start,
                    line_end=cs.line_end,
                    visibility=cs.visibility,
                )
                db.add(sym)
                db.flush()
                class_id_by_qname[cs.qualified_name] = sym.id
                symbols_by_id[sym.id] = {
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "file_id": file_rec.id,
                    "parent_id": None,
                }
                symbols_by_file[file_rec.id].append(sym.id)
                total_symbols_count += 1

            for os in others:
                parent_id = class_id_by_qname.get(os.parent_name) if os.parent_name else None
                sym = Symbol(
                    file_id=file_rec.id,
                    name=os.name,
                    qualified_name=os.qualified_name,
                    symbol_type=os.symbol_type,
                    parent_symbol_id=parent_id,
                    line_start=os.line_start,
                    line_end=os.line_end,
                    visibility=os.visibility,
                )
                db.add(sym)
                db.flush()
                symbols_by_id[sym.id] = {
                    "name": sym.name,
                    "qualified_name": sym.qualified_name,
                    "file_id": file_rec.id,
                    "parent_id": parent_id,
                }
                symbols_by_file[file_rec.id].append(sym.id)
                total_symbols_count += 1

            # Collect raw imports & calls for dependency resolution
            for imp in parse_res.imports:
                raw_imports.append((file_rec.id, imp))
            for call in parse_res.calls:
                raw_calls.append((file_rec.id, call))

        # 6. Resolve dependencies
        resolved_imports, resolved_calls = self.resolver_svc.resolve_dependencies(
            files_by_rel_path=files_by_rel_path,
            file_languages=file_languages,
            symbols_by_id=symbols_by_id,
            symbols_by_file=symbols_by_file,
            raw_imports=raw_imports,
            raw_calls=raw_calls,
        )

        # 7. Persist dependencies
        for r_imp in resolved_imports:
            dep = Dependency(
                repository_version_id=version.id,
                relationship_type="IMPORT",
                source_file_id=r_imp.source_file_id,
                target_file_id=r_imp.target_file_id,
                caller_symbol_id=None,
                callee_symbol_id=None,
                callee_name=None,
                imported_module=r_imp.imported_module,
                import_type=r_imp.import_type,
                line_number=r_imp.line_number,
                resolution_status=r_imp.resolution_status,
            )
            db.add(dep)

        for r_call in resolved_calls:
            dep = Dependency(
                repository_version_id=version.id,
                relationship_type="CALL",
                source_file_id=r_call.source_file_id,
                target_file_id=None,
                caller_symbol_id=r_call.caller_symbol_id,
                callee_symbol_id=r_call.callee_symbol_id,
                callee_name=r_call.callee_name,
                imported_module=None,
                import_type=None,
                line_number=r_call.line_number,
                resolution_status=r_call.resolution_status,
            )
            db.add(dep)

        # 8. Mark version analyzed
        version.analyzed_at = datetime.now(timezone.utc)
        repository.status = "analyzed"
        db.commit()
        db.refresh(version)

        # 9. Extract & Persist Git Commit History & Evolution
        try:
            self.evolution_svc.ingest_git_history(
                db=db,
                repository=repository,
                repo_path=str(repo_path),
                current_version=version,
            )
        except Exception as ex:
            logger.warning(
                "Failed to ingest git history for repository %s: %s", repository.id, ex
            )

        total_dependencies = len(resolved_imports) + len(resolved_calls)

        return IngestionResult(
            repository_id=repository.id,
            repository_version_id=version.id,
            commit_sha=version.commit_sha,
            branch_name=version.branch_name,
            files_count=len(discovered_files),
            symbols_count=total_symbols_count,
            dependencies_count=total_dependencies,
            calls_count=len(resolved_calls),
        )


repository_ingestion_service = RepositoryIngestionService()
