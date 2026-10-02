from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.test_graph_service import _create_sample_graph


def test_symbol_api_endpoints(client: TestClient, db_session: Session):
    data = _create_sample_graph(db_session)
    s_main_id = data["symbols"]["main"].id
    s_service_id = data["symbols"]["service"].id
    s_repo_id = data["symbols"]["repo"].id
    s_isolated_id = data["symbols"]["isolated"].id

    # 1. GET /api/v1/symbols/{id}
    res = client.get(f"/api/v1/symbols/{s_main_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == s_main_id
    assert body["name"] == "main_func"
    assert body["qualified_name"] == "src.main.main_func"
    assert body["symbol_type"] == "function"
    assert body["file_path"] == "src/main.py"
    assert body["language"] == "python"

    # 404 for non-existent symbol
    assert client.get("/api/v1/symbols/99999").status_code == 404

    # 2. GET /api/v1/symbols/{id}/callers
    res_callers = client.get(f"/api/v1/symbols/{s_service_id}/callers")
    assert res_callers.status_code == 200
    callers = res_callers.json()
    caller_names = [c["caller_name"] for c in callers]
    assert "main_func" in caller_names
    assert "fetch_record" in caller_names

    # 3. GET /api/v1/symbols/{id}/callees
    res_callees = client.get(f"/api/v1/symbols/{s_service_id}/callees")
    assert res_callees.status_code == 200
    callees = res_callees.json()
    assert len(callees) == 1
    assert callees[0]["callee_name"] == "fetch_record"
    assert callees[0]["callee_symbol_id"] == s_repo_id

    # 4. GET /api/v1/symbols/{id}/dependencies
    res_deps = client.get(f"/api/v1/symbols/{s_main_id}/dependencies")
    assert res_deps.status_code == 200
    deps = res_deps.json()
    assert len(deps) == 2

    # 5. GET /api/v1/symbols/{id}/paths?target_id=...
    res_paths = client.get(f"/api/v1/symbols/{s_main_id}/paths?target_id={s_repo_id}")
    assert res_paths.status_code == 200
    paths_data = res_paths.json()
    assert paths_data["paths_count"] >= 1
    p = paths_data["paths"][0]
    assert len(p) == 3
    assert p[0]["id"] == s_main_id
    assert p[1]["id"] == s_service_id
    assert p[2]["id"] == s_repo_id

    # Verify max_depth semantics (call hops):
    # s_main -> s_repo is 2 hops. max_depth=1 should return 0 paths, max_depth=2 should return 1 path.
    res_depth1 = client.get(f"/api/v1/symbols/{s_main_id}/paths?target_id={s_repo_id}&max_depth=1")
    assert res_depth1.status_code == 200
    assert res_depth1.json()["paths_count"] == 0

    res_depth2 = client.get(f"/api/v1/symbols/{s_main_id}/paths?target_id={s_repo_id}&max_depth=2")
    assert res_depth2.status_code == 200
    assert res_depth2.json()["paths_count"] == 1

    # Empty paths when no connection exists
    res_no_path = client.get(f"/api/v1/symbols/{s_main_id}/paths?target_id={s_isolated_id}")
    assert res_no_path.status_code == 200
    assert res_no_path.json()["paths_count"] == 0
    assert res_no_path.json()["paths"] == []

    # Missing target_id query param returns 422
    assert client.get(f"/api/v1/symbols/{s_main_id}/paths").status_code == 422


def test_file_api_endpoints(client: TestClient, db_session: Session):
    data = _create_sample_graph(db_session)
    f_main_id = data["files"]["main"].id
    f_service_id = data["files"]["service"].id

    # 1. GET /api/v1/files/{id}
    res = client.get(f"/api/v1/files/{f_service_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == f_service_id
    assert body["path"] == "src/service.py"
    assert body["language"] == "python"
    assert body["symbols_count"] == 1

    # 404 for non-existent file
    assert client.get("/api/v1/files/99999").status_code == 404

    # 2. GET /api/v1/files/{id}/dependencies
    res_deps = client.get(f"/api/v1/files/{f_main_id}/dependencies")
    assert res_deps.status_code == 200
    deps = res_deps.json()
    assert len(deps) == 1
    assert deps[0]["imported_module"] == "src.service"

    # 3. GET /api/v1/files/{id}/dependents
    res_depnts = client.get(f"/api/v1/files/{f_service_id}/dependents")
    assert res_depnts.status_code == 200
    depnts = res_depnts.json()
    assert len(depnts) == 1
    assert depnts[0]["source_file_path"] == "src/main.py"


def test_repository_graph_and_architecture_api(client: TestClient, db_session: Session):
    data = _create_sample_graph(db_session)
    repo_id = data["repo"].id

    # 1. GET /api/v1/repositories/{id}/graph
    res_graph = client.get(f"/api/v1/repositories/{repo_id}/graph")
    assert res_graph.status_code == 200
    g = res_graph.json()
    assert g["repository_id"] == repo_id
    assert g["total_nodes"] == 8
    assert g["total_edges"] == 5
    assert any(n["type"] == "FILE" for n in g["nodes"])
    assert any(n["type"] == "SYMBOL" for n in g["nodes"])
    assert any(e["relationship"] == "IMPORT" for e in g["edges"])
    assert any(e["relationship"] == "CALL" for e in g["edges"])

    # 2. GET /api/v1/repositories/{id}/architecture
    res_arch = client.get(f"/api/v1/repositories/{repo_id}/architecture")
    assert res_arch.status_code == 200
    arch = res_arch.json()
    assert arch["repository_id"] == repo_id
    assert arch["total_files"] == 4
    assert arch["total_symbols"] == 4
    assert len(arch["modules"]) >= 1
    assert any(m["name"] == "src" for m in arch["modules"])

    # 3. 404 on missing repository
    assert client.get("/api/v1/repositories/99999/graph").status_code == 404
    assert client.get("/api/v1/repositories/99999/architecture").status_code == 404
