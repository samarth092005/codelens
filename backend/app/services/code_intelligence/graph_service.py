from collections import deque
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Any
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.dependency import Dependency
from app.models.file_record import FileRecord
from app.models.symbol import Symbol
from app.repositories.code_intelligence_repository import (
    CodeIntelligenceRepository,
    code_intel_repository as default_code_intel_repo,
)
from app.repositories.repository_repository import (
    RepositoryRepository,
    repository_repository as default_repo_repo,
)
from app.schemas.code_intelligence import (
    ArchitectureModule,
    ArchitectureResponse,
    CalleeResponse,
    CallerResponse,
    FileDependencyItem,
    FileDependentItem,
    FileDetailResponse,
    GraphEdge,
    GraphNode,
    GraphResponse,
    SymbolDependencyItem,
    SymbolDetailResponse,
    SymbolPathStep,
    SymbolPathsResponse,
)


class GraphService:
    """Service providing deterministic code intelligence graph traversal, symbol/file navigation, and path finding."""

    def __init__(
        self,
        code_intel_repo: CodeIntelligenceRepository = default_code_intel_repo,
        repo_repo: RepositoryRepository = default_repo_repo,
    ) -> None:
        self.code_intel_repo = code_intel_repo
        self.repo_repo = repo_repo

    # --- 1. Symbol Navigation ---

    def get_symbol(self, db: Session, symbol_id: int) -> SymbolDetailResponse:
        """Retrieve detailed symbol information and definition metadata."""
        sym = self.code_intel_repo.get_symbol(db, symbol_id=symbol_id)
        if not sym:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Symbol with id {symbol_id} not found",
            )

        file_rec = sym.file
        version = file_rec.repository_version

        return SymbolDetailResponse(
            id=sym.id,
            repository_id=version.repository_id,
            repository_version_id=version.id,
            file_id=file_rec.id,
            file_path=file_rec.path,
            name=sym.name,
            qualified_name=sym.qualified_name,
            symbol_type=sym.symbol_type,
            language=file_rec.language,
            line_start=sym.line_start,
            line_end=sym.line_end,
            parent_symbol_id=sym.parent_symbol_id,
            parent_symbol_name=sym.parent_symbol.name if sym.parent_symbol else None,
            visibility=sym.visibility,
            created_at=sym.created_at,
        )

    def get_callers(self, db: Session, symbol_id: int) -> list[CallerResponse]:
        """Find all resolved symbols that call this symbol."""
        # Ensure symbol exists
        self.get_symbol(db, symbol_id=symbol_id)

        caller_deps = self.code_intel_repo.get_symbol_callers(db, symbol_id=symbol_id)
        callers: list[CallerResponse] = []

        for dep in caller_deps:
            caller = dep.caller_symbol
            if not caller:
                continue
            caller_file = caller.file
            callers.append(
                CallerResponse(
                    dependency_id=dep.id,
                    caller_symbol_id=caller.id,
                    caller_name=caller.name,
                    caller_qualified_name=caller.qualified_name,
                    caller_symbol_type=caller.symbol_type,
                    caller_file_id=caller.file_id,
                    caller_file_path=caller_file.path if caller_file else "",
                    line_number=dep.line_number,
                )
            )

        return callers

    def get_callees(self, db: Session, symbol_id: int) -> list[CalleeResponse]:
        """Find all calls (both resolved and unresolved) made by this symbol."""
        # Ensure symbol exists
        self.get_symbol(db, symbol_id=symbol_id)

        callee_deps = self.code_intel_repo.get_symbol_callees(db, symbol_id=symbol_id)
        callees: list[CalleeResponse] = []

        for dep in callee_deps:
            callee_sym = dep.callee_symbol
            callee_file = callee_sym.file if callee_sym else None
            callee_name = dep.callee_name or (callee_sym.name if callee_sym else "")

            callees.append(
                CalleeResponse(
                    dependency_id=dep.id,
                    callee_name=callee_name,
                    callee_symbol_id=callee_sym.id if callee_sym else None,
                    callee_qualified_name=callee_sym.qualified_name if callee_sym else None,
                    callee_symbol_type=callee_sym.symbol_type if callee_sym else None,
                    callee_file_id=callee_file.id if callee_file else None,
                    callee_file_path=callee_file.path if callee_file else None,
                    resolution_status=dep.resolution_status,
                    line_number=dep.line_number,
                )
            )

        return callees

    def get_symbol_dependencies(self, db: Session, symbol_id: int) -> list[SymbolDependencyItem]:
        """Find outgoing dependencies originating from this symbol."""
        # Ensure symbol exists
        self.get_symbol(db, symbol_id=symbol_id)

        deps = self.code_intel_repo.get_symbol_dependencies(db, symbol_id=symbol_id)
        items: list[SymbolDependencyItem] = []

        for dep in deps:
            callee_sym = dep.callee_symbol
            target_name = dep.callee_name or (callee_sym.name if callee_sym else None)
            items.append(
                SymbolDependencyItem(
                    dependency_id=dep.id,
                    relationship_type=dep.relationship_type,
                    target_symbol_id=callee_sym.id if callee_sym else None,
                    target_name=target_name,
                    resolution_status=dep.resolution_status,
                    line_number=dep.line_number,
                )
            )

        return items

    # --- 2. File Navigation ---

    def get_file(self, db: Session, file_id: int) -> FileDetailResponse:
        """Retrieve detailed file metadata."""
        file_rec = self.code_intel_repo.get_file(db, file_id=file_id)
        if not file_rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"File with id {file_id} not found",
            )

        version = file_rec.repository_version
        return FileDetailResponse(
            id=file_rec.id,
            repository_id=version.repository_id,
            repository_version_id=version.id,
            path=file_rec.path,
            extension=file_rec.extension,
            language=file_rec.language,
            size_bytes=file_rec.size_bytes,
            parsing_status=file_rec.parsing_status,
            error_message=file_rec.error_message,
            symbols_count=len(file_rec.symbols),
            created_at=file_rec.created_at,
        )

    def get_file_dependencies(self, db: Session, file_id: int) -> list[FileDependencyItem]:
        """Find internal and external files/modules that this file imports."""
        # Ensure file exists
        self.get_file(db, file_id=file_id)

        deps = self.code_intel_repo.get_file_dependencies(db, file_id=file_id)
        items: list[FileDependencyItem] = []

        for dep in deps:
            target_file = dep.target_file
            items.append(
                FileDependencyItem(
                    dependency_id=dep.id,
                    target_file_id=dep.target_file_id,
                    target_file_path=target_file.path if target_file else None,
                    imported_module=dep.imported_module,
                    import_type=dep.import_type,
                    resolution_status=dep.resolution_status,
                    line_number=dep.line_number,
                )
            )

        return items

    def get_file_dependents(self, db: Session, file_id: int) -> list[FileDependentItem]:
        """Find all files in the repository that import/depend on this file."""
        # Ensure file exists
        self.get_file(db, file_id=file_id)

        dependents = self.code_intel_repo.get_file_dependents(db, file_id=file_id)
        items: list[FileDependentItem] = []

        for dep in dependents:
            src_file = dep.source_file
            if not src_file:
                continue
            items.append(
                FileDependentItem(
                    dependency_id=dep.id,
                    source_file_id=src_file.id,
                    source_file_path=src_file.path,
                    imported_module=dep.imported_module,
                    import_type=dep.import_type,
                    line_number=dep.line_number,
                )
            )

        return items

    # --- 3. Repository Engineering Graph ---

    def _resolve_version_id(self, db: Session, repository_id: int, version_id: int | None) -> int:
        repo = self.repo_repo.get(db, id=repository_id)
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Repository with id {repository_id} not found",
            )
        if version_id is not None:
            v = self.code_intel_repo.get_version(db, version_id=version_id)
            if not v or v.repository_id != repository_id:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Repository version {version_id} not found for repository {repository_id}",
                )
            return version_id

        latest = self.code_intel_repo.get_latest_version(db, repository_id=repository_id)
        if not latest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No analyzed versions found for repository {repository_id}",
            )
        return latest.id

    def get_repository_graph(
        self,
        db: Session,
        *,
        repository_id: int,
        version_id: int | None = None,
    ) -> GraphResponse:
        """Construct the deterministic node-and-edge engineering graph for a repository version."""
        target_version_id = self._resolve_version_id(db, repository_id, version_id)

        files, symbols, deps = self.code_intel_repo.get_version_graph_entities(db, target_version_id)

        nodes: list[GraphNode] = []
        edges: list[GraphEdge] = []

        # 1. FILE nodes
        for f in files:
            nodes.append(
                GraphNode(
                    id=f"file:{f.id}",
                    type="FILE",
                    label=f.path,
                    metadata={
                        "language": f.language,
                        "extension": f.extension,
                        "size_bytes": f.size_bytes,
                        "parsing_status": f.parsing_status,
                    },
                )
            )

        # 2. SYMBOL nodes
        for s in symbols:
            nodes.append(
                GraphNode(
                    id=f"symbol:{s.id}",
                    type="SYMBOL",
                    label=s.qualified_name,
                    metadata={
                        "name": s.name,
                        "symbol_type": s.symbol_type,
                        "file_id": s.file_id,
                        "line_start": s.line_start,
                        "line_end": s.line_end,
                        "visibility": s.visibility,
                    },
                )
            )

        # 3. EDGES
        for d in deps:
            if d.relationship_type == "IMPORT":
                # Only include resolved imports that connect two files
                if d.source_file_id and d.target_file_id and d.resolution_status == "RESOLVED":
                    edges.append(
                        GraphEdge(
                            id=f"import:{d.id}",
                            source=f"file:{d.source_file_id}",
                            target=f"file:{d.target_file_id}",
                            relationship="IMPORT",
                            metadata={
                                "imported_module": d.imported_module,
                                "import_type": d.import_type,
                                "line_number": d.line_number,
                            },
                        )
                    )
            elif d.relationship_type == "CALL":
                # Only include resolved calls connecting two symbols
                if d.caller_symbol_id and d.callee_symbol_id and d.resolution_status == "RESOLVED":
                    edges.append(
                        GraphEdge(
                            id=f"call:{d.id}",
                            source=f"symbol:{d.caller_symbol_id}",
                            target=f"symbol:{d.callee_symbol_id}",
                            relationship="CALL",
                            metadata={
                                "callee_name": d.callee_name,
                                "line_number": d.line_number,
                            },
                        )
                    )

        return GraphResponse(
            repository_id=repository_id,
            repository_version_id=target_version_id,
            nodes=nodes,
            edges=edges,
            total_nodes=len(nodes),
            total_edges=len(edges),
        )

    # --- 4. Deterministic Traversal with Depth and Cycle Handling ---

    def traverse(
        self,
        db: Session,
        *,
        root_id: int,
        direction: str = "out",  # "out" (callees) or "in" (callers)
        max_depth: int = 1,
    ) -> dict[str, Any]:
        """Perform cycle-safe deterministic BFS traversal up to max_depth.
        
        Guarantees:
        - Strict depth levels (1, 2, 3...)
        - Avoids infinite loops when cycles exist (e.g. A -> B -> A)
        - Only traverses RESOLVED relationships
        """
        # Ensure root symbol exists
        root_sym = self.get_symbol(db, symbol_id=root_id)

        # Build adjacency mapping for the version
        target_version_id = root_sym.repository_version_id
        _, symbols, deps = self.code_intel_repo.get_version_graph_entities(db, target_version_id)

        symbol_map = {s.id: s for s in symbols}

        # Adjacency: node -> list of (neighbor_id, dep_id)
        adj: dict[int, list[int]] = {s.id: [] for s in symbols}
        for d in deps:
            if d.relationship_type == "CALL" and d.resolution_status == "RESOLVED":
                if d.caller_symbol_id and d.callee_symbol_id:
                    if direction == "out":
                        adj.setdefault(d.caller_symbol_id, []).append(d.callee_symbol_id)
                    else:
                        adj.setdefault(d.callee_symbol_id, []).append(d.caller_symbol_id)

        # BFS level-by-level
        visited: set[int] = {root_id}
        levels: dict[int, list[dict[str, Any]]] = {}

        current_frontier = [root_id]
        for depth in range(1, max_depth + 1):
            next_frontier: list[int] = []
            level_nodes: list[dict[str, Any]] = []

            for curr in current_frontier:
                for neighbor in adj.get(curr, []):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
                        s = symbol_map.get(neighbor)
                        if s:
                            level_nodes.append({
                                "symbol_id": s.id,
                                "name": s.name,
                                "qualified_name": s.qualified_name,
                                "symbol_type": s.symbol_type,
                                "file_id": s.file_id,
                                "depth": depth,
                            })

            levels[depth] = level_nodes
            current_frontier = next_frontier
            if not current_frontier:
                break

        return {
            "root_symbol_id": root_id,
            "root_qualified_name": root_sym.qualified_name,
            "direction": direction,
            "max_depth": max_depth,
            "levels": levels,
            "total_visited": len(visited) - 1,
        }

    # --- 5. Cycle-Safe Path Finding ---

    def find_paths(
        self,
        db: Session,
        *,
        source_symbol_id: int,
        target_symbol_id: int,
        max_depth: int = 10,
    ) -> SymbolPathsResponse:
        """Find all directed call paths from source_symbol to target_symbol.
        
        `max_depth` specifies the maximum number of CALL edges/hops allowed in a path.
        Handles cycles safely and respects repository version isolation.
        """
        source_sym = self.get_symbol(db, symbol_id=source_symbol_id)
        target_sym = self.get_symbol(db, symbol_id=target_symbol_id)

        # Repository/version isolation check
        if source_sym.repository_version_id != target_sym.repository_version_id:
            return SymbolPathsResponse(
                source_symbol_id=source_symbol_id,
                target_symbol_id=target_symbol_id,
                paths=[],
                paths_count=0,
            )

        version_id = source_sym.repository_version_id

        # Edge case: source is target
        if source_symbol_id == target_symbol_id:
            step = SymbolPathStep(
                id=source_sym.id,
                name=source_sym.name,
                qualified_name=source_sym.qualified_name,
                symbol_type=source_sym.symbol_type,
                file_path=source_sym.file_path,
                line_start=source_sym.line_start,
                line_end=source_sym.line_end,
            )
            return SymbolPathsResponse(
                source_symbol_id=source_symbol_id,
                target_symbol_id=target_symbol_id,
                paths=[[step]],
                paths_count=1,
            )

        # Build adjacency graph for version
        files, symbols, deps = self.code_intel_repo.get_version_graph_entities(db, version_id)
        files_by_id = {f.id: f for f in files}
        symbols_by_id = {s.id: s for s in symbols}

        adj: dict[int, list[int]] = {s.id: [] for s in symbols}
        for d in deps:
            if (
                d.relationship_type == "CALL"
                and d.resolution_status == "RESOLVED"
                and d.caller_symbol_id
                and d.callee_symbol_id
            ):
                adj.setdefault(d.caller_symbol_id, []).append(d.callee_symbol_id)

        # BFS for paths: queue stores current path as list of symbol IDs
        queue = deque([[source_symbol_id]])
        discovered_paths: list[list[int]] = []

        while queue:
            current_path = queue.popleft()
            last_node = current_path[-1]

            current_hops = len(current_path) - 1
            if current_hops >= max_depth:
                continue

            for neighbor in adj.get(last_node, []):
                # Cycle prevention: if neighbor already in this path, skip
                if neighbor in current_path:
                    continue

                new_path = current_path + [neighbor]
                new_hops = len(new_path) - 1

                if neighbor == target_symbol_id:
                    discovered_paths.append(new_path)
                elif new_hops < max_depth:
                    queue.append(new_path)

        # Convert discovered ID paths to SymbolPathStep objects
        result_paths: list[list[SymbolPathStep]] = []
        for path_ids in discovered_paths:
            step_list: list[SymbolPathStep] = []
            for s_id in path_ids:
                s = symbols_by_id.get(s_id)
                f = files_by_id.get(s.file_id) if s else None
                if s and f:
                    step_list.append(
                        SymbolPathStep(
                            id=s.id,
                            name=s.name,
                            qualified_name=s.qualified_name,
                            symbol_type=s.symbol_type,
                            file_path=f.path,
                            line_start=s.line_start,
                            line_end=s.line_end,
                        )
                    )
            if step_list:
                result_paths.append(step_list)

        return SymbolPathsResponse(
            source_symbol_id=source_symbol_id,
            target_symbol_id=target_symbol_id,
            paths=result_paths,
            paths_count=len(result_paths),
        )

    # --- 6. Architecture Data API ---

    def get_architecture_data(
        self,
        db: Session,
        *,
        repository_id: int,
        version_id: int | None = None,
    ) -> ArchitectureResponse:
        """Derive architectural modules from directory hierarchy and aggregate engineering facts."""
        target_version_id = self._resolve_version_id(db, repository_id, version_id)
        version = self.code_intel_repo.get_version(db, version_id=target_version_id)
        files, symbols, deps = self.code_intel_repo.get_version_graph_entities(db, target_version_id)

        # Group files by top-level module / directory
        module_files: dict[str, list[FileRecord]] = {}
        languages: dict[str, int] = {}

        symbols_by_file: dict[int, list[Symbol]] = {}
        for s in symbols:
            symbols_by_file.setdefault(s.file_id, []).append(s)

        for f in files:
            p = PurePosixPath(f.path)
            mod_name = p.parts[0] if len(p.parts) > 1 else "root"
            module_files.setdefault(mod_name, []).append(f)
            languages[f.language] = languages.get(f.language, 0) + 1

        modules: list[ArchitectureModule] = []
        for mod_name, f_list in sorted(module_files.items()):
            file_paths = [f.path for f in f_list]
            sym_count = sum(len(symbols_by_file.get(f.id, [])) for f in f_list)
            modules.append(
                ArchitectureModule(
                    name=mod_name,
                    path=mod_name if mod_name != "root" else ".",
                    files=file_paths,
                    files_count=len(f_list),
                    symbols_count=sym_count,
                )
            )

        return ArchitectureResponse(
            repository_id=repository_id,
            repository_version_id=target_version_id,
            commit_sha=version.commit_sha if version else "",
            modules=modules,
            total_files=len(files),
            total_symbols=len(symbols),
            total_dependencies=len(deps),
            languages=languages,
        )


graph_service = GraphService()
