from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.dependency import Dependency
from app.models.file_record import FileRecord
from app.models.repository import Repository
from app.models.repository_version import RepositoryVersion
from app.models.symbol import Symbol
from app.services.code_intelligence.graph_service import GraphService


def _create_sample_graph(db: Session):
    """Helper creating a deterministic multi-file, multi-symbol call & import graph."""
    repo = Repository(name="graph-repo", url="/dummy/graph-repo")
    db.add(repo)
    db.flush()

    ver = RepositoryVersion(
        repository_id=repo.id,
        commit_sha="c111111111111111111111111111111111111111",
        branch_name="main",
        commit_message="Initial commit",
        analyzed_at=datetime.now(timezone.utc),
    )
    db.add(ver)
    db.flush()

    # Files
    f_main = FileRecord(
        repository_version_id=ver.id,
        path="src/main.py",
        extension=".py",
        language="python",
        size_bytes=300,
        parsing_status="SUCCESS",
    )
    f_service = FileRecord(
        repository_version_id=ver.id,
        path="src/service.py",
        extension=".py",
        language="python",
        size_bytes=400,
        parsing_status="SUCCESS",
    )
    f_repo = FileRecord(
        repository_version_id=ver.id,
        path="src/db/repo.py",
        extension=".py",
        language="python",
        size_bytes=500,
        parsing_status="SUCCESS",
    )
    f_isolated = FileRecord(
        repository_version_id=ver.id,
        path="src/utils.py",
        extension=".py",
        language="python",
        size_bytes=100,
        parsing_status="SUCCESS",
    )
    db.add_all([f_main, f_service, f_repo, f_isolated])
    db.flush()

    # Symbols:
    # main_func (f_main) -> run_service (f_service) -> fetch_record (f_repo)
    # Also cycle: fetch_record -> run_service
    # And isolated: helper_func (f_isolated)
    s_main = Symbol(
        file_id=f_main.id,
        name="main_func",
        qualified_name="src.main.main_func",
        symbol_type="function",
        line_start=5,
        line_end=15,
        visibility="public",
    )
    s_service = Symbol(
        file_id=f_service.id,
        name="run_service",
        qualified_name="src.service.run_service",
        symbol_type="function",
        line_start=10,
        line_end=25,
        visibility="public",
    )
    s_repo = Symbol(
        file_id=f_repo.id,
        name="fetch_record",
        qualified_name="src.db.repo.fetch_record",
        symbol_type="function",
        line_start=12,
        line_end=30,
        visibility="public",
    )
    s_isolated = Symbol(
        file_id=f_isolated.id,
        name="helper_func",
        qualified_name="src.utils.helper_func",
        symbol_type="function",
        line_start=1,
        line_end=5,
        visibility="private",
    )
    db.add_all([s_main, s_service, s_repo, s_isolated])
    db.flush()

    # Dependencies:
    # Imports: f_main imports f_service; f_service imports f_repo
    dep_imp1 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_main.id,
        target_file_id=f_service.id,
        relationship_type="IMPORT",
        resolution_status="RESOLVED",
        imported_module="src.service",
        import_type="named",
        line_number=1,
    )
    dep_imp2 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_service.id,
        target_file_id=f_repo.id,
        relationship_type="IMPORT",
        resolution_status="RESOLVED",
        imported_module="src.db.repo",
        import_type="named",
        line_number=2,
    )

    # Calls:
    # 1. s_main -> s_service
    dep_call1 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_main.id,
        target_file_id=f_service.id,
        caller_symbol_id=s_main.id,
        callee_symbol_id=s_service.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="run_service",
        line_number=8,
    )
    # 2. s_service -> s_repo
    dep_call2 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_service.id,
        target_file_id=f_repo.id,
        caller_symbol_id=s_service.id,
        callee_symbol_id=s_repo.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="fetch_record",
        line_number=18,
    )
    # 3. Cycle: s_repo -> s_service (e.g. recursive retry callback)
    dep_call3 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_repo.id,
        target_file_id=f_service.id,
        caller_symbol_id=s_repo.id,
        callee_symbol_id=s_service.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="run_service",
        line_number=22,
    )
    # 4. Unresolved call from s_main to external_log
    dep_call4 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_main.id,
        caller_symbol_id=s_main.id,
        relationship_type="CALL",
        resolution_status="UNRESOLVED",
        callee_name="external_log",
        line_number=12,
    )

    db.add_all([dep_imp1, dep_imp2, dep_call1, dep_call2, dep_call3, dep_call4])
    db.commit()

    return {
        "repo": repo,
        "version": ver,
        "files": {
            "main": f_main,
            "service": f_service,
            "repo": f_repo,
            "isolated": f_isolated,
        },
        "symbols": {
            "main": s_main,
            "service": s_service,
            "repo": s_repo,
            "isolated": s_isolated,
        },
    }


def test_symbol_detail_retrieval(db_session: Session):
    data = _create_sample_graph(db_session)
    s_main = data["symbols"]["main"]
    svc = GraphService()

    detail = svc.get_symbol(db_session, symbol_id=s_main.id)
    assert detail.id == s_main.id
    assert detail.name == "main_func"
    assert detail.qualified_name == "src.main.main_func"
    assert detail.file_path == "src/main.py"
    assert detail.language == "python"
    assert detail.line_start == 5
    assert detail.line_end == 15
    assert detail.visibility == "public"

    # Missing symbol raises 404
    with pytest.raises(HTTPException) as exc_info:
        svc.get_symbol(db_session, symbol_id=999999)
    assert exc_info.value.status_code == 404


def test_callers_and_callees_retrieval(db_session: Session):
    data = _create_sample_graph(db_session)
    s_service = data["symbols"]["service"]
    svc = GraphService()

    # Callers of s_service should be s_main and s_repo (due to cycle)
    callers = svc.get_callers(db_session, symbol_id=s_service.id)
    caller_names = [c.caller_name for c in callers]
    assert "main_func" in caller_names
    assert "fetch_record" in caller_names
    assert len(callers) == 2

    # Callees of s_service should be s_repo
    callees = svc.get_callees(db_session, symbol_id=s_service.id)
    assert len(callees) == 1
    assert callees[0].callee_name == "fetch_record"
    assert callees[0].callee_symbol_id == data["symbols"]["repo"].id
    assert callees[0].resolution_status == "RESOLVED"

    # Callees of s_main should include resolved run_service and unresolved external_log
    main_callees = svc.get_callees(db_session, symbol_id=data["symbols"]["main"].id)
    assert len(main_callees) == 2
    callee_map = {c.callee_name: c.resolution_status for c in main_callees}
    assert callee_map["run_service"] == "RESOLVED"
    assert callee_map["external_log"] == "UNRESOLVED"


def test_symbol_dependencies_retrieval(db_session: Session):
    data = _create_sample_graph(db_session)
    s_main = data["symbols"]["main"]
    svc = GraphService()

    deps = svc.get_symbol_dependencies(db_session, symbol_id=s_main.id)
    assert len(deps) == 2
    assert any(d.target_name == "run_service" for d in deps)
    assert any(d.target_name == "external_log" for d in deps)


def test_file_navigation(db_session: Session):
    data = _create_sample_graph(db_session)
    f_service = data["files"]["service"]
    svc = GraphService()

    # File detail
    detail = svc.get_file(db_session, file_id=f_service.id)
    assert detail.id == f_service.id
    assert detail.path == "src/service.py"
    assert detail.language == "python"
    assert detail.symbols_count == 1

    # File dependencies (imports)
    file_deps = svc.get_file_dependencies(db_session, file_id=f_service.id)
    assert len(file_deps) == 1
    assert file_deps[0].imported_module == "src.db.repo"
    assert file_deps[0].target_file_path == "src/db/repo.py"

    # File dependents (files importing f_service)
    dependents = svc.get_file_dependents(db_session, file_id=f_service.id)
    assert len(dependents) == 1
    assert dependents[0].source_file_path == "src/main.py"

    # Missing file raises 404
    with pytest.raises(HTTPException) as exc_info:
        svc.get_file(db_session, file_id=999999)
    assert exc_info.value.status_code == 404


def test_repository_graph_generation(db_session: Session):
    data = _create_sample_graph(db_session)
    repo = data["repo"]
    svc = GraphService()

    graph = svc.get_repository_graph(db_session, repository_id=repo.id)
    assert graph.repository_id == repo.id
    assert graph.repository_version_id == data["version"].id

    node_types = {n.type for n in graph.nodes}
    assert "FILE" in node_types
    assert "SYMBOL" in node_types
    assert graph.total_nodes == 8  # 4 files + 4 symbols

    edge_relationships = {e.relationship for e in graph.edges}
    assert "IMPORT" in edge_relationships
    assert "CALL" in edge_relationships
    # 2 resolved imports + 3 resolved calls = 5 edges
    assert graph.total_edges == 5


def test_graph_traversal_depths_and_cycles(db_session: Session):
    data = _create_sample_graph(db_session)
    s_main = data["symbols"]["main"]
    s_service = data["symbols"]["service"]
    s_repo = data["symbols"]["repo"]
    svc = GraphService()

    # Depth 1 from s_main: should visit s_service
    res1 = svc.traverse(db_session, root_id=s_main.id, direction="out", max_depth=1)
    assert 1 in res1["levels"]
    lvl1_ids = [n["symbol_id"] for n in res1["levels"][1]]
    assert lvl1_ids == [s_service.id]
    assert 2 not in res1["levels"]

    # Depth 2 from s_main: should visit s_service at depth 1, and s_repo at depth 2
    res2 = svc.traverse(db_session, root_id=s_main.id, direction="out", max_depth=2)
    assert 1 in res2["levels"]
    assert 2 in res2["levels"]
    lvl2_ids = [n["symbol_id"] for n in res2["levels"][2]]
    assert lvl2_ids == [s_repo.id]

    # Depth 3 from s_main:
    # s_main -> s_service -> s_repo -> (calls s_service which is already visited, cycle is avoided)
    res3 = svc.traverse(db_session, root_id=s_main.id, direction="out", max_depth=3)
    assert 1 in res3["levels"]
    assert 2 in res3["levels"]
    # Depth 3 should have no new unvisited neighbors because s_service was already visited!
    assert res3["levels"].get(3, []) == []
    # Total visited is exactly 2: s_service and s_repo (no infinite loop)
    assert res3["total_visited"] == 2

    # Inward traversal (callers) from s_repo:
    # s_repo callers: s_service (depth 1) -> s_main (depth 2)
    in_res = svc.traverse(db_session, root_id=s_repo.id, direction="in", max_depth=3)
    in_lvl1 = [n["symbol_id"] for n in in_res["levels"][1]]
    assert s_service.id in in_lvl1


def test_symbol_path_finding(db_session: Session):
    data = _create_sample_graph(db_session)
    s_main = data["symbols"]["main"]
    s_service = data["symbols"]["service"]
    s_repo = data["symbols"]["repo"]
    s_isolated = data["symbols"]["isolated"]
    svc = GraphService()

    # 1. Path between connected symbols: s_main -> s_repo
    paths_res = svc.find_paths(
        db_session,
        source_symbol_id=s_main.id,
        target_symbol_id=s_repo.id,
    )
    assert paths_res.paths_count >= 1
    p = paths_res.paths[0]
    assert len(p) == 3
    assert p[0].id == s_main.id
    assert p[1].id == s_service.id
    assert p[2].id == s_repo.id

    # 2. No path exists to isolated symbol
    no_path_res = svc.find_paths(
        db_session,
        source_symbol_id=s_main.id,
        target_symbol_id=s_isolated.id,
    )
    assert no_path_res.paths_count == 0
    assert no_path_res.paths == []

    # 3. Same symbol path
    same_path = svc.find_paths(
        db_session,
        source_symbol_id=s_main.id,
        target_symbol_id=s_main.id,
    )
    assert same_path.paths_count == 1
    assert same_path.paths[0][0].id == s_main.id

    # 4. Cycle handling: path from s_repo to s_service (direct call)
    cycle_res = svc.find_paths(
        db_session,
        source_symbol_id=s_repo.id,
        target_symbol_id=s_service.id,
    )
    assert cycle_res.paths_count >= 1
    assert cycle_res.paths[0][0].id == s_repo.id
    assert cycle_res.paths[0][1].id == s_service.id


def test_symbol_path_finding_max_depth_call_hops(db_session: Session):
    """Explicitly verify max_depth semantics as maximum number of CALL edges/hops.
    
    A -> B (1 hop)
    B -> C (1 hop, A->C is 2 hops)
    C -> D (1 hop, A->D is 3 hops)
    """
    repo = Repository(name="hops-repo", url="/dummy/hops-repo")
    db_session.add(repo)
    db_session.flush()

    ver = RepositoryVersion(
        repository_id=repo.id,
        commit_sha="c33333333333333333333333333333333333333",
        branch_name="main",
        commit_message="Hops test commit",
        analyzed_at=datetime.now(timezone.utc),
    )
    db_session.add(ver)
    db_session.flush()

    f = FileRecord(
        repository_version_id=ver.id,
        path="src/chain.py",
        extension=".py",
        language="python",
        size_bytes=200,
        parsing_status="SUCCESS",
    )
    db_session.add(f)
    db_session.flush()

    # Create A, B, C, D
    s_a = Symbol(file_id=f.id, name="func_a", qualified_name="src.chain.func_a", symbol_type="function", line_start=1, line_end=5)
    s_b = Symbol(file_id=f.id, name="func_b", qualified_name="src.chain.func_b", symbol_type="function", line_start=6, line_end=10)
    s_c = Symbol(file_id=f.id, name="func_c", qualified_name="src.chain.func_c", symbol_type="function", line_start=11, line_end=15)
    s_d = Symbol(file_id=f.id, name="func_d", qualified_name="src.chain.func_d", symbol_type="function", line_start=16, line_end=20)
    db_session.add_all([s_a, s_b, s_c, s_d])
    db_session.flush()

    # CALL edges: A -> B -> C -> D
    d_ab = Dependency(repository_version_id=ver.id, source_file_id=f.id, caller_symbol_id=s_a.id, callee_symbol_id=s_b.id, relationship_type="CALL", resolution_status="RESOLVED", line_number=2)
    d_bc = Dependency(repository_version_id=ver.id, source_file_id=f.id, caller_symbol_id=s_b.id, callee_symbol_id=s_c.id, relationship_type="CALL", resolution_status="RESOLVED", line_number=7)
    d_cd = Dependency(repository_version_id=ver.id, source_file_id=f.id, caller_symbol_id=s_c.id, callee_symbol_id=s_d.id, relationship_type="CALL", resolution_status="RESOLVED", line_number=12)
    db_session.add_all([d_ab, d_bc, d_cd])
    db_session.commit()

    svc = GraphService()

    # 1. A -> B (1 edge/hop):
    # max_depth=1 => path is allowed
    p_ab_1 = svc.find_paths(db_session, source_symbol_id=s_a.id, target_symbol_id=s_b.id, max_depth=1)
    assert p_ab_1.paths_count == 1
    assert [step.name for step in p_ab_1.paths[0]] == ["func_a", "func_b"]

    # max_depth=0 => path is not allowed
    p_ab_0 = svc.find_paths(db_session, source_symbol_id=s_a.id, target_symbol_id=s_b.id, max_depth=0)
    assert p_ab_0.paths_count == 0

    # 2. A -> B -> C (2 edges/hops):
    # max_depth=1 => path is not allowed
    p_ac_1 = svc.find_paths(db_session, source_symbol_id=s_a.id, target_symbol_id=s_c.id, max_depth=1)
    assert p_ac_1.paths_count == 0

    # max_depth=2 => path is allowed
    p_ac_2 = svc.find_paths(db_session, source_symbol_id=s_a.id, target_symbol_id=s_c.id, max_depth=2)
    assert p_ac_2.paths_count == 1
    assert [step.name for step in p_ac_2.paths[0]] == ["func_a", "func_b", "func_c"]

    # 3. A -> B -> C -> D (3 edges/hops):
    # max_depth=2 => path is not allowed
    p_ad_2 = svc.find_paths(db_session, source_symbol_id=s_a.id, target_symbol_id=s_d.id, max_depth=2)
    assert p_ad_2.paths_count == 0

    # max_depth=3 => path is allowed
    p_ad_3 = svc.find_paths(db_session, source_symbol_id=s_a.id, target_symbol_id=s_d.id, max_depth=3)
    assert p_ad_3.paths_count == 1
    assert [step.name for step in p_ad_3.paths[0]] == ["func_a", "func_b", "func_c", "func_d"]


def test_symbol_path_finding_repository_isolation(db_session: Session):
    data1 = _create_sample_graph(db_session)
    s1 = data1["symbols"]["main"]

    # Create a second repo with a symbol
    repo2 = Repository(name="other-repo", url="/dummy/repo2")
    db_session.add(repo2)
    db_session.flush()

    ver2 = RepositoryVersion(
        repository_id=repo2.id,
        commit_sha="c222222222222222222222222222222222222222",
        branch_name="main",
        commit_message="Ver 2",
        analyzed_at=datetime.now(timezone.utc),
    )
    db_session.add(ver2)
    db_session.flush()

    f2 = FileRecord(
        repository_version_id=ver2.id,
        path="src/other.py",
        extension=".py",
        language="python",
        size_bytes=100,
        parsing_status="SUCCESS",
    )
    db_session.add(f2)
    db_session.flush()

    s2 = Symbol(
        file_id=f2.id,
        name="other_func",
        qualified_name="src.other.other_func",
        symbol_type="function",
        line_start=1,
        line_end=5,
    )
    db_session.add(s2)
    db_session.commit()

    svc = GraphService()
    # Paths across different repositories must return empty list
    diff_repo_res = svc.find_paths(
        db_session,
        source_symbol_id=s1.id,
        target_symbol_id=s2.id,
    )
    assert diff_repo_res.paths_count == 0
    assert diff_repo_res.paths == []


def test_architecture_derivation(db_session: Session):
    data = _create_sample_graph(db_session)
    repo = data["repo"]
    svc = GraphService()

    arch = svc.get_architecture_data(db_session, repository_id=repo.id)
    assert arch.repository_id == repo.id
    assert arch.total_files == 4
    assert arch.total_symbols == 4
    assert arch.total_dependencies == 6
    assert arch.languages.get("python") == 4

    module_names = [m.name for m in arch.modules]
    assert "src" in module_names
    src_mod = next(m for m in arch.modules if m.name == "src")
    assert src_mod.files_count == 4
    assert src_mod.symbols_count == 4
