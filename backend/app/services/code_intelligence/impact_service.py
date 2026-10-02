from collections import deque
from collections.abc import Sequence
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
from app.schemas.code_intelligence import (
    AffectedFileItem,
    AffectedSymbolItem,
    ApiImpactItem,
    DatabaseImpactItem,
    ImpactAnalysisResponse,
    ImpactEvidence,
    SymbolDetailResponse,
    TestImpactItem,
)
from app.services.code_intelligence.graph_service import (
    GraphService,
    graph_service as default_graph_service,
)


class ImpactAnalysisService:
    """Deterministic Change Impact Intelligence Service.
    
    Given a persisted symbol, analyzes what code (symbols, files, tests, APIs, databases)
    may be affected if that symbol changes.
    """

    def __init__(
        self,
        code_intel_repo: CodeIntelligenceRepository = default_code_intel_repo,
        graph_svc: GraphService = default_graph_service,
    ) -> None:
        self.code_intel_repo = code_intel_repo
        self.graph_svc = graph_svc

    def _is_test_entity(self, file_path: str, symbol_name: str) -> bool:
        """Deterministically determine if an entity is part of test code."""
        norm_path = file_path.replace("\\", "/").lower()
        path_parts = norm_path.split("/")
        filename = path_parts[-1] if path_parts else norm_path

        if "tests" in path_parts or "test" in path_parts:
            return True
        if (
            filename.startswith("test_")
            or filename.endswith("_test.py")
            or filename.endswith(".test.ts")
            or filename.endswith(".test.js")
            or filename.endswith(".spec.ts")
            or filename.endswith(".spec.js")
        ):
            return True
        if symbol_name.startswith("test_") or symbol_name.startswith("test"):
            return True
        return False

    def _is_api_entity(self, file_path: str, symbol_name: str) -> bool:
        """Deterministically determine if an entity is part of an API or route handler."""
        norm_path = file_path.replace("\\", "/").lower()
        path_parts = norm_path.split("/")
        if "api" in path_parts or "routes" in path_parts or "endpoints" in path_parts:
            return True
        return False

    def _is_database_entity(self, file_path: str, symbol_name: str) -> bool:
        """Deterministically determine if an entity is a database model or query operation."""
        norm_path = file_path.replace("\\", "/").lower()
        path_parts = norm_path.split("/")
        if "db" in path_parts or "database" in path_parts or "models" in path_parts:
            return True
        db_keywords = {"execute_query", "query", "db_session", "session", "commit", "flush", "cursor"}
        if any(kw in symbol_name.lower() for kw in db_keywords):
            return True
        return False

    def analyze_symbol_impact(
        self,
        db: Session,
        *,
        symbol_id: int,
        max_depth: int = 10,
    ) -> ImpactAnalysisResponse:
        """Deterministically analyze code affected by a change to symbol_id."""
        # 1. Fetch changed symbol metadata (raises 404 if not found)
        changed_symbol_detail: SymbolDetailResponse = self.graph_svc.get_symbol(db, symbol_id=symbol_id)
        version_id = changed_symbol_detail.repository_version_id
        repo_id = changed_symbol_detail.repository_id

        # 2. Load all entities for this repository version (version boundary isolation)
        files, symbols, deps = self.code_intel_repo.get_version_graph_entities(db, version_id)
        files_by_id = {f.id: f for f in files}
        symbols_by_id = {s.id: s for s in symbols}

        # 3. Build reverse CALL adjacency map (callee -> list of (caller_id, line_number))
        callers_adj: dict[int, list[tuple[int, int | None]]] = {s.id: [] for s in symbols}
        for d in deps:
            if (
                d.relationship_type == "CALL"
                and d.resolution_status == "RESOLVED"
                and d.caller_symbol_id
                and d.callee_symbol_id
            ):
                callers_adj.setdefault(d.callee_symbol_id, []).append((d.caller_symbol_id, d.line_number))

        # 4. Cycle-safe BFS traversal starting from changed symbol
        # Queue stores: (current_symbol_id, call_chain_symbol_ids, call_line_numbers)
        queue: deque[tuple[int, list[int], list[int]]] = deque([(symbol_id, [symbol_id], [])])
        visited_min_hops: dict[int, int] = {symbol_id: 0}
        affected_symbols_map: dict[int, AffectedSymbolItem] = {}

        while queue:
            curr_sym_id, path_so_far, lines_so_far = queue.popleft()
            current_hops = len(path_so_far) - 1

            if current_hops >= max_depth:
                continue

            for caller_id, call_line in callers_adj.get(curr_sym_id, []):
                # Cycle prevention: if caller is already in current path, skip
                if caller_id in path_so_far:
                    continue

                next_path = path_so_far + [caller_id]
                next_lines = lines_so_far + ([call_line] if call_line is not None else [])
                next_hops = len(next_path) - 1

                # If this caller was already reached with equal or fewer hops, skip
                if caller_id in visited_min_hops and visited_min_hops[caller_id] <= next_hops:
                    continue

                visited_min_hops[caller_id] = next_hops

                caller_sym = symbols_by_id.get(caller_id)
                if not caller_sym:
                    continue

                caller_file = files_by_id.get(caller_sym.file_id)
                caller_file_path = caller_file.path if caller_file else ""

                impact_type = "DIRECT" if next_hops == 1 else "TRANSITIVE"

                chain_names = [symbols_by_id[sid].name for sid in next_path if sid in symbols_by_id]
                if next_hops == 1:
                    line_str = f" at line {call_line}" if call_line else ""
                    reason = f"Direct caller: '{caller_sym.name}' calls '{changed_symbol_detail.name}'{line_str} in '{caller_file_path}'"
                else:
                    chain_str = " -> ".join(chain_names)
                    reason = f"Transitive caller ({next_hops} hops): {chain_str}"

                evidence = ImpactEvidence(
                    call_chain=chain_names,
                    hops=next_hops,
                    call_line_numbers=next_lines,
                    reason=reason,
                )

                affected_symbols_map[caller_id] = AffectedSymbolItem(
                    symbol_id=caller_sym.id,
                    name=caller_sym.name,
                    qualified_name=caller_sym.qualified_name,
                    symbol_type=caller_sym.symbol_type,
                    file_id=caller_sym.file_id,
                    file_path=caller_file_path,
                    line_start=caller_sym.line_start,
                    line_end=caller_sym.line_end,
                    impact_type=impact_type,
                    hops=next_hops,
                    relationship_type="CALL",
                    resolution_status="RESOLVED",
                    evidence=evidence,
                )

                if next_hops < max_depth:
                    queue.append((caller_id, next_path, next_lines))

        # 5. Capture unresolved call relationships to the changed symbol
        for d in deps:
            if (
                d.relationship_type == "CALL"
                and d.resolution_status == "UNRESOLVED"
                and d.caller_symbol_id
                and (
                    d.callee_symbol_id == symbol_id
                    or (d.callee_name and d.callee_name == changed_symbol_detail.name)
                )
            ):
                caller_sym = symbols_by_id.get(d.caller_symbol_id)
                if caller_sym and caller_sym.id not in affected_symbols_map:
                    caller_file = files_by_id.get(caller_sym.file_id)
                    c_path = caller_file.path if caller_file else ""
                    line_str = f" at line {d.line_number}" if d.line_number else ""
                    affected_symbols_map[caller_sym.id] = AffectedSymbolItem(
                        symbol_id=caller_sym.id,
                        name=caller_sym.name,
                        qualified_name=caller_sym.qualified_name,
                        symbol_type=caller_sym.symbol_type,
                        file_id=caller_sym.file_id,
                        file_path=c_path,
                        line_start=caller_sym.line_start,
                        line_end=caller_sym.line_end,
                        impact_type="DIRECT",
                        hops=1,
                        relationship_type="CALL",
                        resolution_status="UNRESOLVED",
                        evidence=ImpactEvidence(
                            call_chain=[changed_symbol_detail.name, caller_sym.name],
                            hops=1,
                            call_line_numbers=[d.line_number] if d.line_number else [],
                            reason=f"Direct unresolved call to '{changed_symbol_detail.name}'{line_str} in '{c_path}'",
                        ),
                    )

        # 6. Aggregate affected files (deduplicated)
        files_map: dict[int, list[AffectedSymbolItem]] = {}
        for aff_sym in affected_symbols_map.values():
            files_map.setdefault(aff_sym.file_id, []).append(aff_sym)

        affected_files: list[AffectedFileItem] = []
        for f_id, sym_items in files_map.items():
            f_rec = files_by_id.get(f_id)
            if not f_rec:
                continue
            min_hops = min(s.hops for s in sym_items)
            impact_type = "DIRECT" if min_hops == 1 else "TRANSITIVE"
            affected_files.append(
                AffectedFileItem(
                    file_id=f_id,
                    file_path=f_rec.path,
                    language=f_rec.language,
                    impact_type=impact_type,
                    min_hops=min_hops,
                    affected_symbol_count=len(sym_items),
                    affected_symbol_ids=[s.symbol_id for s in sym_items],
                )
            )

        # Sort affected files by min_hops, then path
        affected_files.sort(key=lambda f: (f.min_hops, f.file_path))

        # 7. Identify test impacts
        affected_tests: list[TestImpactItem] = []
        for aff_sym in affected_symbols_map.values():
            if self._is_test_entity(aff_sym.file_path, aff_sym.name):
                affected_tests.append(
                    TestImpactItem(
                        symbol_id=aff_sym.symbol_id,
                        name=aff_sym.name,
                        qualified_name=aff_sym.qualified_name,
                        file_id=aff_sym.file_id,
                        file_path=aff_sym.file_path,
                        impact_type=aff_sym.impact_type,
                        hops=aff_sym.hops,
                        evidence=aff_sym.evidence,
                    )
                )

        # 8. Identify API impacts
        affected_apis: list[ApiImpactItem] = []
        for aff_sym in affected_symbols_map.values():
            if self._is_api_entity(aff_sym.file_path, aff_sym.name):
                affected_apis.append(
                    ApiImpactItem(
                        symbol_id=aff_sym.symbol_id,
                        name=aff_sym.name,
                        qualified_name=aff_sym.qualified_name,
                        file_id=aff_sym.file_id,
                        file_path=aff_sym.file_path,
                        impact_type=aff_sym.impact_type,
                        hops=aff_sym.hops,
                        evidence=aff_sym.evidence,
                    )
                )

        # 9. Identify Database impacts
        affected_databases: list[DatabaseImpactItem] = []
        # Check if the changed symbol itself is a database operation/model
        if self._is_database_entity(changed_symbol_detail.file_path, changed_symbol_detail.name):
            affected_databases.append(
                DatabaseImpactItem(
                    symbol_id=changed_symbol_detail.id,
                    name=changed_symbol_detail.name,
                    qualified_name=changed_symbol_detail.qualified_name,
                    file_id=changed_symbol_detail.file_id,
                    file_path=changed_symbol_detail.file_path,
                    operation="CHANGED_DATABASE_SYMBOL",
                    impact_type="DIRECT",
                    hops=0,
                    evidence=ImpactEvidence(
                        call_chain=[changed_symbol_detail.name],
                        hops=0,
                        call_line_numbers=[],
                        reason=f"Changed symbol '{changed_symbol_detail.name}' is defined in database layer: '{changed_symbol_detail.file_path}'",
                    ),
                )
            )

        # Check affected symbols that interact with the database
        for aff_sym in affected_symbols_map.values():
            if self._is_database_entity(aff_sym.file_path, aff_sym.name):
                affected_databases.append(
                    DatabaseImpactItem(
                        symbol_id=aff_sym.symbol_id,
                        name=aff_sym.name,
                        qualified_name=aff_sym.qualified_name,
                        file_id=aff_sym.file_id,
                        file_path=aff_sym.file_path,
                        operation="DATABASE_CALLER",
                        impact_type=aff_sym.impact_type,
                        hops=aff_sym.hops,
                        evidence=aff_sym.evidence,
                    )
                )

        # Sort affected symbols by hops, then qualified_name
        sorted_affected_symbols = sorted(
            affected_symbols_map.values(),
            key=lambda s: (s.hops, s.qualified_name),
        )

        direct_count = sum(1 for s in sorted_affected_symbols if s.impact_type == "DIRECT")
        transitive_count = sum(1 for s in sorted_affected_symbols if s.impact_type == "TRANSITIVE")

        return ImpactAnalysisResponse(
            changed_symbol=changed_symbol_detail,
            repository_id=repo_id,
            repository_version_id=version_id,
            max_depth=max_depth,
            total_affected_symbols=len(sorted_affected_symbols),
            total_affected_files=len(affected_files),
            direct_callers_count=direct_count,
            transitive_callers_count=transitive_count,
            affected_symbols=sorted_affected_symbols,
            affected_files=affected_files,
            affected_tests=affected_tests,
            affected_apis=affected_apis,
            affected_databases=affected_databases,
        )


impact_analysis_service = ImpactAnalysisService()
