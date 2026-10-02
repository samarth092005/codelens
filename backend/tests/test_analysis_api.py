import subprocess
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.repository import Repository


def _setup_git_repo(path: Path) -> str:
    subprocess.run(["git", "init", "-b", "main"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "api_tester@codelens.io"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "API Tester"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "API test commit"], cwd=str(path), check=True, capture_output=True)
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(path), check=True, capture_output=True, text=True)
    return res.stdout.strip()


def test_analysis_api_flow(client: TestClient, db_session: Session, tmp_path: Path):
    # 1. Prepare files in a test repository
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "tax.py").write_text(
        "def compute_tax(val):\n    return val * 0.15\n",
        encoding="utf-8",
    )
    (tmp_path / "app" / "invoice.py").write_text(
        "from app.tax import compute_tax\n\ndef create_invoice(subtotal):\n    tax = compute_tax(subtotal)\n    return subtotal + tax\n",
        encoding="utf-8",
    )
    (tmp_path / "index.js").write_text(
        "function startServer() { return true; }\n",
        encoding="utf-8",
    )

    commit_sha = _setup_git_repo(tmp_path)

    # 2. Register repository via API
    create_res = client.post(
        "/api/v1/repositories",
        json={
            "name": "api-sample-repo",
            "url": str(tmp_path),
            "description": "Repo for API tests",
            "default_branch": "main",
        },
    )
    assert create_res.status_code == 201
    repo_data = create_res.json()
    repo_id = repo_data["id"]

    # 3. Trigger Analysis via POST /api/v1/repositories/{id}/analysis
    analysis_res = client.post(f"/api/v1/repositories/{repo_id}/analysis")
    assert analysis_res.status_code == 200
    job_data = analysis_res.json()
    assert job_data["status"] == "COMPLETED"
    assert job_data["repository_id"] == repo_id
    assert job_data["repository_version_id"] is not None
    job_id = job_data["id"]
    version_id = job_data["repository_version_id"]

    # 4. Inspect Analysis Job via GET /api/v1/repositories/{id}/analysis/{job_id}
    job_res = client.get(f"/api/v1/repositories/{repo_id}/analysis/{job_id}")
    assert job_res.status_code == 200
    assert job_res.json()["id"] == job_id
    assert job_res.json()["status"] == "COMPLETED"

    # 5. List versions via GET /api/v1/repositories/{id}/versions
    versions_res = client.get(f"/api/v1/repositories/{repo_id}/versions")
    assert versions_res.status_code == 200
    versions = versions_res.json()
    assert len(versions) == 1
    assert versions[0]["commit_sha"] == commit_sha
    assert versions[0]["branch_name"] == "main"

    # 6. Retrieve files via GET /api/v1/repositories/{id}/files
    files_res = client.get(f"/api/v1/repositories/{repo_id}/files")
    assert files_res.status_code == 200
    files = files_res.json()
    assert len(files) == 3
    paths = [f["path"] for f in files]
    assert "app/tax.py" in paths
    assert "app/invoice.py" in paths
    assert "index.js" in paths

    # Test file language filter
    py_files_res = client.get(f"/api/v1/repositories/{repo_id}/files?language=python")
    assert py_files_res.status_code == 200
    assert len(py_files_res.json()) == 2

    # 7. Retrieve symbols via GET /api/v1/repositories/{id}/symbols
    symbols_res = client.get(f"/api/v1/repositories/{repo_id}/symbols")
    assert symbols_res.status_code == 200
    symbols = symbols_res.json()
    symbol_names = [s["name"] for s in symbols]
    assert "compute_tax" in symbol_names
    assert "create_invoice" in symbol_names
    assert "startServer" in symbol_names

    # Test symbol name filter
    tax_sym_res = client.get(f"/api/v1/repositories/{repo_id}/symbols?name=compute_tax")
    assert tax_sym_res.status_code == 200
    assert len(tax_sym_res.json()) == 1
    assert tax_sym_res.json()[0]["name"] == "compute_tax"
    assert tax_sym_res.json()[0]["symbol_type"] == "function"

    # 8. Retrieve dependencies via GET /api/v1/repositories/{id}/dependencies
    deps_res = client.get(f"/api/v1/repositories/{repo_id}/dependencies")
    assert deps_res.status_code == 200
    deps = deps_res.json()
    assert len(deps) > 0

    # Filter by CALL
    calls_res = client.get(f"/api/v1/repositories/{repo_id}/dependencies?relationship_type=CALL")
    assert calls_res.status_code == 200
    calls = calls_res.json()
    assert any(c["callee_name"] == "compute_tax" for c in calls)
    tax_call = next(c for c in calls if c["callee_name"] == "compute_tax")
    assert tax_call["resolution_status"] == "RESOLVED"
    assert tax_call["callee_symbol_id"] is not None

    # Filter by IMPORT
    imports_res = client.get(f"/api/v1/repositories/{repo_id}/dependencies?relationship_type=IMPORT")
    assert imports_res.status_code == 200
    imports = imports_res.json()
    assert any(i["imported_module"] == "app.tax" for i in imports)


def test_analysis_api_errors(client: TestClient):
    # Non-existent repository
    res = client.post("/api/v1/repositories/99999/analysis")
    assert res.status_code == 404

    res = client.get("/api/v1/repositories/99999/files")
    assert res.status_code == 404

    res = client.get("/api/v1/repositories/99999/symbols")
    assert res.status_code == 404

    res = client.get("/api/v1/repositories/99999/dependencies")
    assert res.status_code == 404

    res = client.get("/api/v1/repositories/99999/analysis/1")
    assert res.status_code == 404
