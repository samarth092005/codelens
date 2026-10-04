import logging
from collections.abc import Sequence
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.commit_file_change import CommitFileChange
from app.models.commit_symbol_change import CommitSymbolChange
from app.models.file_record import FileRecord
from app.models.git_commit import GitCommit
from app.models.repository import Repository
from app.models.repository_version import RepositoryVersion
from app.models.symbol import Symbol
from app.repositories.code_intelligence_repository import (
    CodeIntelligenceRepository,
    code_intel_repository as default_code_intel_repo,
)
from app.schemas.code_intelligence import (
    AffectedFileItem,
    AffectedSymbolItem,
    CommitDetailResponse,
    CommitFileChangeItem,
    CommitImpactResponse,
    CommitSummaryResponse,
    CommitSymbolChangeItem,
    FileHistoryItem,
    FileHistoryResponse,
    SymbolHistoryItem,
    SymbolHistoryResponse,
)
from app.services.code_intelligence.git_service import GitService, git_service as default_git_service
from app.services.code_intelligence.impact_service import (
    ImpactAnalysisService,
    impact_analysis_service as default_impact_service,
)
from app.services.code_intelligence.language_detector import (
    LanguageDetector,
    language_detector as default_language_detector,
)
from app.services.code_intelligence.parser import CompositeCodeParser

logger = logging.getLogger(__name__)


class GitEvolutionService:
    """Service providing Git history analysis and code evolution intelligence."""

    def __init__(
        self,
        git_svc: GitService = default_git_service,
        code_intel_repo: CodeIntelligenceRepository = default_code_intel_repo,
        impact_svc: ImpactAnalysisService = default_impact_service,
        parser: CompositeCodeParser | None = None,
        language_detector: LanguageDetector = default_language_detector,
    ) -> None:
        self.git_svc = git_svc
        self.code_intel_repo = code_intel_repo
        self.impact_svc = impact_svc
        self.parser = parser or CompositeCodeParser()
        self.language_detector = language_detector

    def ingest_git_history(
        self,
        db: Session,
        *,
        repository: Repository,
        repo_path: str,
        current_version: RepositoryVersion,
    ) -> None:
        """Extract and persist complete Git commit history and symbol evolution."""
        if not self.git_svc.is_git_repository(repo_path):
            logger.info("Path %s is not a git repository; skipping git history ingestion.", repo_path)
            return

        # Fetch commits in chronological order (oldest to newest)
        commits_info = self.git_svc.get_commit_history(repo_path, max_commits=500)
        if not commits_info:
            return

        # Cache existing commits in database
        stmt = select(GitCommit).where(GitCommit.repository_id == repository.id)
        existing_commits = {c.commit_hash: c for c in db.scalars(stmt).all()}

        # Index current version's files and symbols for entity linking
        current_files_by_path = {f.path: f for f in current_version.files}
        current_symbols_by_qual = {
            (f.path, s.qualified_name or s.name): s
            for f in current_version.files
            for s in f.symbols
        }

        for commit_info in commits_info:
            if commit_info.commit_hash in existing_commits:
                commit_record = existing_commits[commit_info.commit_hash]
                if (
                    commit_info.commit_hash == current_version.commit_hash
                    and commit_record.repository_version_id != current_version.id
                ):
                    commit_record.repository_version_id = current_version.id
                    db.add(commit_record)
                continue

            diff_files = self.git_svc.get_commit_diff_files(
                repo_path, commit_info.commit_hash, commit_info.parent_hash
            )
            insertions = sum(f.additions for f in diff_files)
            deletions = sum(f.deletions for f in diff_files)
            files_changed_count = len(diff_files)
            is_head = commit_info.commit_hash == current_version.commit_hash

            commit_record = GitCommit(
                repository_id=repository.id,
                repository_version_id=current_version.id if is_head else None,
                commit_hash=commit_info.commit_hash,
                parent_hash=commit_info.parent_hash,
                author_name=commit_info.author_name,
                author_email=commit_info.author_email,
                commit_message=commit_info.commit_message,
                committed_at=commit_info.committed_at,
            )
            db.add(commit_record)
            db.flush()

            for diff_file in diff_files:
                matched_file_id = None
                if diff_file.file_path in current_files_by_path:
                    matched_file_id = current_files_by_path[diff_file.file_path].id

                file_change = CommitFileChange(
                    commit_id=commit_record.id,
                    file_id=matched_file_id,
                    file_path=diff_file.file_path,
                    old_path=diff_file.old_path,
                    change_type=diff_file.change_type,
                    additions=diff_file.additions,
                    deletions=diff_file.deletions,
                )
                db.add(file_change)
                db.flush()

                # Symbol extraction & diffing if language is supported
                lang = self.language_detector.detect_language(diff_file.file_path)
                if lang in self.parser.parsers:
                    try:
                        self._diff_and_persist_symbols(
                            db=db,
                            repo_path=repo_path,
                            commit_record=commit_record,
                            file_change=file_change,
                            diff_file=diff_file,
                            language=lang,
                            current_symbols_by_qual=current_symbols_by_qual,
                        )
                    except Exception as ex:
                        logger.warning(
                            "Failed to diff symbols for %s at commit %s: %s",
                            diff_file.file_path,
                            commit_info.commit_hash,
                            ex,
                        )

            existing_commits[commit_info.commit_hash] = commit_record

        db.commit()

    def _diff_and_persist_symbols(
        self,
        db: Session,
        repo_path: str,
        commit_record: GitCommit,
        file_change: CommitFileChange,
        diff_file: any,
        language: str,
        current_symbols_by_qual: dict[tuple[str, str], Symbol],
    ) -> None:
        """Diff symbols between parent commit and current commit for a changed file."""
        parent_bytes = None
        if commit_record.parent_hash and diff_file.change_type not in ("A", "ADDED"):
            parent_bytes = self.git_svc.get_file_content_at_commit(
                repo_path,
                commit_record.parent_hash,
                diff_file.old_path or diff_file.file_path,
            )

        child_bytes = None
        if diff_file.change_type not in ("D", "DELETED"):
            child_bytes = self.git_svc.get_file_content_at_commit(
                repo_path,
                commit_record.commit_hash,
                diff_file.file_path,
            )

        parent_symbols = (
            self.parser.parse(
                parent_bytes, diff_file.old_path or diff_file.file_path, language
            ).symbols
            if parent_bytes is not None
            else []
        )
        child_symbols = (
            self.parser.parse(child_bytes, diff_file.file_path, language).symbols
            if child_bytes is not None
            else []
        )

        def sym_key(s: any) -> str:
            return s.qualified_name or s.name

        parent_map = {sym_key(s): s for s in parent_symbols}
        child_map = {sym_key(s): s for s in child_symbols}

        # Check added and modified symbols
        for key, child_s in child_map.items():
            matched_sym = current_symbols_by_qual.get((diff_file.path, key))
            sym_id = matched_sym.id if matched_sym else None

            if key not in parent_map:
                db.add(
                    CommitSymbolChange(
                        file_change_id=file_change.id,
                        symbol_id=sym_id,
                        symbol_name=child_s.name,
                        qualified_name=child_s.qualified_name or child_s.name,
                        symbol_type=child_s.symbol_type,
                        change_type="ADDED",
                        new_line_start=child_s.line_start,
                        new_line_end=child_s.line_end,
                        changed_lines_count=max(0, child_s.line_end - child_s.line_start + 1),
                    )
                )
            else:
                parent_s = parent_map[key]
                is_modified = False
                if child_bytes is not None and parent_bytes is not None:
                    child_lines = child_bytes.decode("utf-8", errors="replace").splitlines()
                    parent_lines = parent_bytes.decode("utf-8", errors="replace").splitlines()
                    child_slice = child_lines[child_s.line_start - 1 : child_s.line_end]
                    parent_slice = parent_lines[parent_s.line_start - 1 : parent_s.line_end]
                    if child_slice != parent_slice:
                        is_modified = True
                elif (
                    child_s.line_start != parent_s.line_start
                    or child_s.line_end != parent_s.line_end
                ):
                    is_modified = True

                if is_modified:
                    db.add(
                        CommitSymbolChange(
                            file_change_id=file_change.id,
                            symbol_id=sym_id,
                            symbol_name=child_s.name,
                            qualified_name=child_s.qualified_name or child_s.name,
                            symbol_type=child_s.symbol_type,
                            change_type="MODIFIED",
                            old_line_start=parent_s.line_start,
                            old_line_end=parent_s.line_end,
                            new_line_start=child_s.line_start,
                            new_line_end=child_s.line_end,
                            changed_lines_count=max(0, child_s.line_end - child_s.line_start + 1),
                        )
                    )

        # Check deleted symbols
        for key, parent_s in parent_map.items():
            if key not in child_map:
                db.add(
                    CommitSymbolChange(
                        file_change_id=file_change.id,
                        symbol_id=None,
                        symbol_name=parent_s.name,
                        qualified_name=parent_s.qualified_name or parent_s.name,
                        symbol_type=parent_s.symbol_type,
                        change_type="DELETED",
                        old_line_start=parent_s.line_start,
                        old_line_end=parent_s.line_end,
                        changed_lines_count=max(0, parent_s.line_end - parent_s.line_start + 1),
                    )
                )

    def list_commits(
        self,
        db: Session,
        repository_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> list[CommitSummaryResponse]:
        """List chronological Git commits for a repository (most recent first)."""
        repo = db.get(Repository, repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        commits = self.code_intel_repo.list_commits(db, repository_id, skip=skip, limit=limit)
        return [
            CommitSummaryResponse(
                id=c.id,
                repository_id=c.repository_id,
                commit_hash=c.commit_hash,
                parent_hash=c.parent_hash,
                author_name=c.author_name,
                author_email=c.author_email,
                commit_message=c.commit_message,
                committed_at=c.committed_at,
                repository_version_id=c.repository_version_id,
                files_changed_count=c.files_changed_count,
                insertions=c.insertions,
                deletions=c.deletions,
            )
            for c in commits
        ]

    def get_commit_details(
        self,
        db: Session,
        repository_id: int,
        commit_hash: str,
    ) -> CommitDetailResponse:
        """Get complete details of a specific commit including file and symbol changes."""
        repo = db.get(Repository, repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        commit = self.code_intel_repo.get_commit_by_hash(db, repository_id, commit_hash)
        if not commit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Commit {commit_hash} not found in repository {repository_id}",
            )

        file_items: list[CommitFileChangeItem] = []
        for fc in commit.changed_files:
            sym_items = [
                CommitSymbolChangeItem(
                    id=sc.id,
                    symbol_id=sc.symbol_id,
                    symbol_name=sc.symbol_name,
                    qualified_name=sc.qualified_name,
                    symbol_type=sc.symbol_type,
                    change_type=sc.change_type,
                    old_line_start=sc.old_line_start,
                    old_line_end=sc.old_line_end,
                    new_line_start=sc.new_line_start,
                    new_line_end=sc.new_line_end,
                    changed_lines_count=sc.changed_lines_count,
                )
                for sc in fc.changed_symbols
            ]
            file_items.append(
                CommitFileChangeItem(
                    id=fc.id,
                    file_id=fc.file_id,
                    file_path=fc.file_path,
                    old_path=fc.old_path,
                    change_type=fc.change_type,
                    additions=fc.additions,
                    deletions=fc.deletions,
                    changed_symbols=sym_items,
                )
            )

        all_symbols = [s for f in file_items for s in f.changed_symbols]

        return CommitDetailResponse(
            id=commit.id,
            repository_id=commit.repository_id,
            repository_version_id=commit.repository_version_id,
            commit_hash=commit.commit_hash,
            parent_hash=commit.parent_hash,
            author_name=commit.author_name,
            author_email=commit.author_email,
            commit_message=commit.commit_message,
            committed_at=commit.committed_at,
            changed_files=file_items,
            total_files_changed=len(file_items),
            total_symbols_changed=len(all_symbols),
            total_additions=sum(f.additions for f in file_items),
            total_deletions=sum(f.deletions for f in file_items),
        )

    def get_file_history(
        self,
        db: Session,
        file_id: int,
    ) -> FileHistoryResponse:
        """Get the commit history of a specific file."""
        file_record = self.code_intel_repo.get_file(db, file_id)
        if not file_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File with id {file_id} not found",
            )

        repository_id = file_record.repository_version.repository_id
        file_changes = self.code_intel_repo.get_file_commit_changes(
            db,
            repository_id,
            file_record.path,
            file_record.id,
        )

        history_items: list[FileHistoryItem] = []
        for fc in file_changes:
            commit = fc.commit
            sym_names = [sc.qualified_name or sc.symbol_name for sc in fc.changed_symbols]
            history_items.append(
                FileHistoryItem(
                    commit_hash=commit.commit_hash,
                    commit_message=commit.commit_message,
                    author_name=commit.author_name,
                    author_email=commit.author_email,
                    committed_at=commit.committed_at,
                    change_type=fc.change_type,
                    old_path=fc.old_path,
                    additions=fc.additions,
                    deletions=fc.deletions,
                    changed_symbols_count=len(fc.changed_symbols),
                    changed_symbols=sym_names,
                )
            )

        total_insertions = sum(c.additions for c in file_changes)
        total_deletions = sum(c.deletions for c in file_changes)

        return FileHistoryResponse(
            file_id=file_record.id,
            file_path=file_record.path,
            repository_id=repository_id,
            history=history_items,
            total_commits=len(history_items),
            total_insertions=total_insertions,
            total_deletions=total_deletions,
        )

    def get_symbol_history(
        self,
        db: Session,
        symbol_id: int,
    ) -> SymbolHistoryResponse:
        """Get the evolution history of a specific symbol."""
        symbol = self.code_intel_repo.get_symbol(db, symbol_id)
        if not symbol:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol with id {symbol_id} not found",
            )

        repository_id = symbol.file.repository_version.repository_id
        sym_changes = self.code_intel_repo.get_symbol_commit_changes(
            db,
            repository_id,
            symbol.name,
            symbol.qualified_name,
            symbol.file.path,
            symbol.id,
        )

        history_items: list[SymbolHistoryItem] = []
        for sc in sym_changes:
            commit = sc.commit
            evidence_str = (
                f"{sc.change_type} in {sc.file_path} at commit {commit.commit_hash[:7]}"
                if commit
                else f"{sc.change_type} in {sc.file_path}"
            )
            history_items.append(
                SymbolHistoryItem(
                    commit_hash=commit.commit_hash if commit else "",
                    commit_message=commit.commit_message if commit else None,
                    author_name=commit.author_name if commit else "Unknown",
                    author_email=commit.author_email if commit else "unknown@codelens.io",
                    committed_at=commit.committed_at if commit else datetime.now(timezone.utc),
                    change_type=sc.change_type,
                    old_line_start=sc.old_line_start,
                    old_line_end=sc.old_line_end,
                    new_line_start=sc.new_line_start,
                    new_line_end=sc.new_line_end,
                    changed_lines_count=sc.changed_lines_count,
                    evidence=evidence_str,
                )
            )

        introduced_at = None
        for item in reversed(history_items):
            if item.change_type == "ADDED":
                introduced_at = item.committed_at
                break

        last_modified_at = None
        for item in history_items:
            if item.change_type in ("MODIFIED", "ADDED"):
                last_modified_at = item.committed_at
                break

        return SymbolHistoryResponse(
            symbol_id=symbol.id,
            symbol_name=symbol.name,
            qualified_name=symbol.qualified_name or symbol.name,
            symbol_type=symbol.symbol_type,
            file_path=symbol.file.path,
            repository_id=repository_id,
            history=history_items,
            total_commits=len(history_items),
            introduced_at=introduced_at,
            last_modified_at=last_modified_at,
        )

    def analyze_commit_impact(
        self,
        db: Session,
        repository_id: int,
        commit_hash: str,
    ) -> CommitImpactResponse:
        """Analyze potential impact of changes made in a commit across the engineering graph."""
        repo = db.get(Repository, repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )

        commit = self.code_intel_repo.get_commit_by_hash(db, repository_id, commit_hash)
        if not commit:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Commit {commit_hash} not found in repository {repository_id}",
            )

        # Determine target version to evaluate graph impact against
        version_id = commit.repository_version_id
        if version_id:
            version = self.code_intel_repo.get_version(db, version_id)
        else:
            version = self.code_intel_repo.get_latest_version(db, repository_id)

        changed_symbols_list: list[CommitSymbolChangeItem] = []
        for sc in commit.symbol_changes:
            changed_symbols_list.append(
                CommitSymbolChangeItem(
                    id=sc.id,
                    symbol_id=sc.symbol_id,
                    symbol_name=sc.symbol_name,
                    qualified_name=sc.qualified_name,
                    symbol_type=sc.symbol_type,
                    change_type=sc.change_type,
                    old_line_start=sc.old_line_start,
                    old_line_end=sc.old_line_end,
                    new_line_start=sc.new_line_start,
                    new_line_end=sc.new_line_end,
                    changed_lines_count=sc.changed_lines_count,
                )
            )

        if not version:
            return CommitImpactResponse(
                repository_id=repository_id,
                commit_hash=commit.commit_hash,
                repository_version_id=None,
                commit_message=commit.commit_message,
                changed_symbols=changed_symbols_list,
                total_changed_symbols=len(changed_symbols_list),
                total_directly_affected=0,
                total_transitively_affected=0,
                total_affected_files=0,
                directly_affected=[],
                transitively_affected=[],
                unresolved_affected=[],
                affected_symbols=[],
                affected_files=[],
                affected_tests=[],
                direct_callers_count=0,
                transitive_callers_count=0,
                affected_symbols_count=0,
                affected_files_count=0,
            )

        # Map version symbols for fast lookup by (file_path, qualified_name or name)
        symbols_stmt = (
            select(Symbol)
            .options(selectinload(Symbol.file))
            .join(FileRecord, Symbol.file_id == FileRecord.id)
            .where(FileRecord.repository_version_id == version.id)
        )
        version_symbols = db.scalars(symbols_stmt).all()
        version_sym_map = {
            (s.file.path, s.qualified_name or s.name): s for s in version_symbols
        }
        version_sym_name_map = {
            (s.file.path, s.name): s for s in version_symbols
        }

        # Analyze impact for each changed symbol that exists in current engineering model
        aggregated_symbols: dict[int, AffectedSymbolItem] = {}
        aggregated_files: dict[int, AffectedFileItem] = {}
        aggregated_tests: dict[int, any] = {}

        for sc in commit.symbol_changes:
            target_symbol = None
            if sc.symbol_id is not None:
                target_symbol = db.get(Symbol, sc.symbol_id)
            if not target_symbol:
                key = (sc.file_path, sc.qualified_name or sc.symbol_name)
                target_symbol = version_sym_map.get(key)
                if not target_symbol:
                    target_symbol = version_sym_name_map.get((sc.file_path, sc.symbol_name))

            if not target_symbol:
                continue

            try:
                impact = self.impact_svc.analyze_symbol_impact(db, symbol_id=target_symbol.id, max_depth=10)
            except Exception as ex:
                logger.warning("Error analyzing impact for symbol %s: %s", target_symbol.id, ex)
                continue

            # Merge affected symbols
            for aff_sym in impact.affected_symbols:
                existing = aggregated_symbols.get(aff_sym.symbol_id)
                if not existing:
                    aggregated_symbols[aff_sym.symbol_id] = aff_sym
                else:
                    if aff_sym.hops < existing.hops:
                        aggregated_symbols[aff_sym.symbol_id] = aff_sym

            # Merge affected files
            for aff_file in impact.affected_files:
                existing_file = aggregated_files.get(aff_file.file_id)
                if not existing_file:
                    aggregated_files[aff_file.file_id] = aff_file
                else:
                    min_hops = min(existing_file.min_hops, aff_file.min_hops)
                    impact_type = "DIRECT" if min_hops == 1 else "TRANSITIVE"
                    combined_sym_ids = list(
                        dict.fromkeys(existing_file.affected_symbol_ids + aff_file.affected_symbol_ids)
                    )
                    aggregated_files[aff_file.file_id] = AffectedFileItem(
                        file_id=aff_file.file_id,
                        file_path=aff_file.file_path,
                        language=aff_file.language,
                        impact_type=impact_type,
                        min_hops=min_hops,
                        affected_symbol_count=len(combined_sym_ids),
                        affected_symbol_ids=combined_sym_ids,
                    )

            # Merge affected tests
            for aff_test in impact.affected_tests:
                if aff_test.symbol_id not in aggregated_tests:
                    aggregated_tests[aff_test.symbol_id] = aff_test

        sorted_symbols = sorted(
            aggregated_symbols.values(), key=lambda s: (s.hops, s.name)
        )
        sorted_files = sorted(
            aggregated_files.values(), key=lambda f: (f.min_hops, f.file_path)
        )

        directly_affected = [s for s in sorted_symbols if s.impact_type == "DIRECT"]
        transitively_affected = [s for s in sorted_symbols if s.impact_type == "TRANSITIVE"]

        return CommitImpactResponse(
            repository_id=repository_id,
            commit_hash=commit.commit_hash,
            repository_version_id=version.id,
            commit_message=commit.commit_message,
            changed_symbols=changed_symbols_list,
            total_changed_symbols=len(changed_symbols_list),
            total_directly_affected=len(directly_affected),
            total_transitively_affected=len(transitively_affected),
            total_affected_files=len(sorted_files),
            directly_affected=directly_affected,
            transitively_affected=transitively_affected,
            unresolved_affected=[],
            affected_symbols=sorted_symbols,
            affected_files=sorted_files,
            affected_tests=list(aggregated_tests.values()),
            direct_callers_count=len(directly_affected),
            transitive_callers_count=len(transitively_affected),
            affected_symbols_count=len(sorted_symbols),
            affected_files_count=len(sorted_files),
        )


git_evolution_service = GitEvolutionService()
