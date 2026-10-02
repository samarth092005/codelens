from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.dependency import Dependency
from app.models.file_record import FileRecord
from app.models.repository import Repository
from app.models.repository_version import RepositoryVersion
from app.models.symbol import Symbol
from app.services.code_intelligence.impact_service import ImpactAnalysisService


def _create_impact_test_graph(db: Session):
    """Sets up a rich graph to verify direct, transitive, cycle, test, API, DB, and unresolved impact.
    
    Structure:
    - db/query.py:
        * execute_raw_sql (DB symbol)
    - src/service.py:
        * calculate_pricing (direct caller of execute_raw_sql, 1 hop)
    - src/api/routes.py:
        * get_quote_endpoint (API symbol, calls calculate_pricing, 2 hops from execute_raw_sql)
    - tests/test_quote.py:
        * test_pricing_flow (Test symbol, calls get_quote_endpoint, 3 hops from execute_raw_sql)
    - src/cycle.py:
        * cycle_func_a <-> cycle_func_b (calls calculate_pricing and each other)
    - src/unresolved.py:
        * orphan_func (has an UNRESOLVED call to 'execute_raw_sql')
    - src/isolated.py:
        * unused_helper (never calls execute_raw_sql)
    """
    repo = Repository(name="impact-repo", url="/dummy/impact-repo")
    db.add(repo)
    db.flush()

    ver = RepositoryVersion(
        repository_id=repo.id,
        commit_sha="c44444444444444444444444444444444444444",
        branch_name="main",
        commit_message="Impact test commit",
        analyzed_at=datetime.now(timezone.utc),
    )
    db.add(ver)
    db.flush()

    # Files
    f_db = FileRecord(
        repository_version_id=ver.id,
        path="db/query.py",
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
    f_api = FileRecord(
        repository_version_id=ver.id,
        path="src/api/routes.py",
        extension=".py",
        language="python",
        size_bytes=350,
        parsing_status="SUCCESS",
    )
    f_test = FileRecord(
        repository_version_id=ver.id,
        path="tests/test_quote.py",
        extension=".py",
        language="python",
        size_bytes=250,
        parsing_status="SUCCESS",
    )
    f_cycle = FileRecord(
        repository_version_id=ver.id,
        path="src/cycle.py",
        extension=".py",
        language="python",
        size_bytes=200,
        parsing_status="SUCCESS",
    )
    f_unresolved = FileRecord(
        repository_version_id=ver.id,
        path="src/unresolved.py",
        extension=".py",
        language="python",
        size_bytes=150,
        parsing_status="SUCCESS",
    )
    f_isolated = FileRecord(
        repository_version_id=ver.id,
        path="src/isolated.py",
        extension=".py",
        language="python",
        size_bytes=100,
        parsing_status="SUCCESS",
    )
    db.add_all([f_db, f_service, f_api, f_test, f_cycle, f_unresolved, f_isolated])
    db.flush()

    # Symbols
    s_sql = Symbol(file_id=f_db.id, name="execute_raw_sql", qualified_name="db.query.execute_raw_sql", symbol_type="function", line_start=5, line_end=15)
    s_service = Symbol(file_id=f_service.id, name="calculate_pricing", qualified_name="src.service.calculate_pricing", symbol_type="function", line_start=10, line_end=25)
    s_api = Symbol(file_id=f_api.id, name="get_quote_endpoint", qualified_name="src.api.routes.get_quote_endpoint", symbol_type="function", line_start=20, line_end=35)
    s_test = Symbol(file_id=f_test.id, name="test_pricing_flow", qualified_name="tests.test_quote.test_pricing_flow", symbol_type="function", line_start=5, line_end=15)
    
    s_cycle_a = Symbol(file_id=f_cycle.id, name="cycle_func_a", qualified_name="src.cycle.cycle_func_a", symbol_type="function", line_start=5, line_end=10)
    s_cycle_b = Symbol(file_id=f_cycle.id, name="cycle_func_b", qualified_name="src.cycle.cycle_func_b", symbol_type="function", line_start=15, line_end=20)
    
    s_unresolved = Symbol(file_id=f_unresolved.id, name="orphan_func", qualified_name="src.unresolved.orphan_func", symbol_type="function", line_start=1, line_end=5)
    s_isolated = Symbol(file_id=f_isolated.id, name="unused_helper", qualified_name="src.isolated.unused_helper", symbol_type="function", line_start=1, line_end=5)

    db.add_all([s_sql, s_service, s_api, s_test, s_cycle_a, s_cycle_b, s_unresolved, s_isolated])
    db.flush()

    # CALL dependencies:
    # 1. s_service -> s_sql (s_service is direct caller of s_sql, 1 hop)
    d1 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_service.id,
        target_file_id=f_db.id,
        caller_symbol_id=s_service.id,
        callee_symbol_id=s_sql.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="execute_raw_sql",
        line_number=14,
    )
    # 2. s_api -> s_service (s_api is caller of s_service, 2 hops from s_sql)
    d2 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_api.id,
        target_file_id=f_service.id,
        caller_symbol_id=s_api.id,
        callee_symbol_id=s_service.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="calculate_pricing",
        line_number=28,
    )
    # 3. s_test -> s_api (s_test is caller of s_api, 3 hops from s_sql)
    d3 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_test.id,
        target_file_id=f_api.id,
        caller_symbol_id=s_test.id,
        callee_symbol_id=s_api.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="get_quote_endpoint",
        line_number=10,
    )
    # 4. Cycle: s_cycle_a calls s_service (2 hops from s_sql), s_cycle_b calls s_cycle_a, s_cycle_a calls s_cycle_b
    d4 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_cycle.id,
        target_file_id=f_service.id,
        caller_symbol_id=s_cycle_a.id,
        callee_symbol_id=s_service.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="calculate_pricing",
        line_number=8,
    )
    d5 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_cycle.id,
        target_file_id=f_cycle.id,
        caller_symbol_id=s_cycle_b.id,
        callee_symbol_id=s_cycle_a.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="cycle_func_a",
        line_number=18,
    )
    d6 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_cycle.id,
        target_file_id=f_cycle.id,
        caller_symbol_id=s_cycle_a.id,
        callee_symbol_id=s_cycle_b.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="cycle_func_b",
        line_number=9,
    )
    # 5. Unresolved call: orphan_func calls execute_raw_sql
    d7 = Dependency(
        repository_version_id=ver.id,
        source_file_id=f_unresolved.id,
        caller_symbol_id=s_unresolved.id,
        callee_name="execute_raw_sql",
        relationship_type="CALL",
        resolution_status="UNRESOLVED",
        line_number=3,
    )

    db.add_all([d1, d2, d3, d4, d5, d6, d7])
    db.commit()

    return {
        "repo": repo,
        "version": ver,
        "files": {
            "db": f_db,
            "service": f_service,
            "api": f_api,
            "test": f_test,
            "cycle": f_cycle,
            "unresolved": f_unresolved,
            "isolated": f_isolated,
        },
        "symbols": {
            "sql": s_sql,
            "service": s_service,
            "api": s_api,
            "test": s_test,
            "cycle_a": s_cycle_a,
            "cycle_b": s_cycle_b,
            "unresolved": s_unresolved,
            "isolated": s_isolated,
        },
    }


def test_direct_and_transitive_impact_analysis(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    # Full impact with max_depth=10
    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)

    assert res.changed_symbol.id == s_sql.id
    assert res.changed_symbol.name == "execute_raw_sql"

    # Direct callers should include calculate_pricing and unresolved orphan_func
    direct_symbols = [s for s in res.affected_symbols if s.impact_type == "DIRECT"]
    direct_names = [s.name for s in direct_symbols]
    assert "calculate_pricing" in direct_names
    assert "orphan_func" in direct_names
    assert res.direct_callers_count == 2

    # Transitive callers should include get_quote_endpoint (2 hops), test_pricing_flow (3 hops), cycle_func_a (2 hops), cycle_func_b (3 hops)
    transitive_symbols = [s for s in res.affected_symbols if s.impact_type == "TRANSITIVE"]
    transitive_names = [s.name for s in transitive_symbols]
    assert "get_quote_endpoint" in transitive_names
    assert "test_pricing_flow" in transitive_names
    assert "cycle_func_a" in transitive_names
    assert "cycle_func_b" in transitive_names

    # Check evidence structure
    api_item = next(s for s in res.affected_symbols if s.name == "get_quote_endpoint")
    assert api_item.hops == 2
    assert api_item.evidence.hops == 2
    assert "execute_raw_sql" in api_item.evidence.call_chain
    assert "calculate_pricing" in api_item.evidence.call_chain
    assert "get_quote_endpoint" in api_item.evidence.call_chain


def test_impact_analysis_max_depth_bounds(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    # max_depth=1: only direct callers (hops == 1)
    res_depth1 = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=1)
    assert all(s.hops == 1 for s in res_depth1.affected_symbols)
    names_d1 = [s.name for s in res_depth1.affected_symbols]
    assert "calculate_pricing" in names_d1
    assert "get_quote_endpoint" not in names_d1
    assert "test_pricing_flow" not in names_d1
    assert res_depth1.transitive_callers_count == 0

    # max_depth=2: includes get_quote_endpoint and cycle_func_a (2 hops), but NOT test_pricing_flow (3 hops)
    res_depth2 = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=2)
    names_d2 = [s.name for s in res_depth2.affected_symbols]
    assert "calculate_pricing" in names_d2
    assert "get_quote_endpoint" in names_d2
    assert "test_pricing_flow" not in names_d2


def test_cycle_handling_and_duplicate_prevention(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    # cycle_func_a and cycle_func_b call each other. Traversal must not hang or duplicate.
    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)

    # Verify no duplicates in affected symbols
    sym_ids = [s.symbol_id for s in res.affected_symbols]
    assert len(sym_ids) == len(set(sym_ids)), "Every affected symbol must be unique"

    # Isolated helper must never appear
    assert "unused_helper" not in [s.name for s in res.affected_symbols]


def test_affected_files_calculation(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)

    # Check deduplicated files
    file_paths = [f.file_path for f in res.affected_files]
    assert len(file_paths) == len(set(file_paths)), "Affected files must be distinct"
    assert "src/service.py" in file_paths
    assert "src/api/routes.py" in file_paths
    assert "tests/test_quote.py" in file_paths
    assert "src/isolated.py" not in file_paths

    service_file = next(f for f in res.affected_files if f.file_path == "src/service.py")
    assert service_file.impact_type == "DIRECT"
    assert service_file.min_hops == 1


def test_test_impact_detection(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)

    # Affected tests
    test_names = [t.name for t in res.affected_tests]
    assert "test_pricing_flow" in test_names
    test_item = res.affected_tests[0]
    assert test_item.file_path == "tests/test_quote.py"
    assert test_item.hops == 3


def test_api_impact_detection(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)

    api_names = [a.name for a in res.affected_apis]
    assert "get_quote_endpoint" in api_names
    api_item = res.affected_apis[0]
    assert api_item.file_path == "src/api/routes.py"
    assert api_item.hops == 2


def test_database_impact_detection(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)

    # Changed symbol is execute_raw_sql in db/query.py, so it is detected as CHANGED_DATABASE_SYMBOL
    assert len(res.affected_databases) >= 1
    db_item = res.affected_databases[0]
    assert db_item.name == "execute_raw_sql"
    assert db_item.file_path == "db/query.py"
    assert db_item.operation == "CHANGED_DATABASE_SYMBOL"


def test_unresolved_call_relationship_impact(db_session: Session):
    data = _create_impact_test_graph(db_session)
    s_sql = data["symbols"]["sql"]
    svc = ImpactAnalysisService()

    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)

    # orphan_func made an UNRESOLVED call by name to execute_raw_sql
    orphan_item = next((s for s in res.affected_symbols if s.name == "orphan_func"), None)
    assert orphan_item is not None
    assert orphan_item.resolution_status == "UNRESOLVED"
    assert orphan_item.impact_type == "DIRECT"
    assert "Direct unresolved call" in orphan_item.evidence.reason


def test_repository_version_isolation_impact(db_session: Session):
    data1 = _create_impact_test_graph(db_session)
    s_sql = data1["symbols"]["sql"]

    # Create a separate repository and version with a caller
    repo2 = Repository(name="isolated-repo", url="/dummy/isolated-repo")
    db_session.add(repo2)
    db_session.flush()

    ver2 = RepositoryVersion(
        repository_id=repo2.id,
        commit_sha="c55555555555555555555555555555555555555",
        branch_name="main",
        commit_message="Isolated ver",
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

    s_foreign = Symbol(
        file_id=f2.id,
        name="foreign_caller",
        qualified_name="src.other.foreign_caller",
        symbol_type="function",
        line_start=1,
        line_end=5,
    )
    db_session.add(s_foreign)
    db_session.flush()

    # Foreign call pointing to s_sql from another version
    d_foreign = Dependency(
        repository_version_id=ver2.id,
        source_file_id=f2.id,
        caller_symbol_id=s_foreign.id,
        callee_symbol_id=s_sql.id,
        relationship_type="CALL",
        resolution_status="RESOLVED",
        callee_name="execute_raw_sql",
        line_number=2,
    )
    db_session.add(d_foreign)
    db_session.commit()

    svc = ImpactAnalysisService()
    # Impact on s_sql must strictly exclude foreign_caller from the other repo version!
    res = svc.analyze_symbol_impact(db_session, symbol_id=s_sql.id, max_depth=10)
    affected_names = [s.name for s in res.affected_symbols]
    assert "foreign_caller" not in affected_names


def test_nonexistent_symbol_raises_404(db_session: Session):
    svc = ImpactAnalysisService()
    with pytest.raises(HTTPException) as exc_info:
        svc.analyze_symbol_impact(db_session, symbol_id=999999)
    assert exc_info.value.status_code == 404
