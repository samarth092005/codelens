import subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.repository import Repository
from app.services.code_intelligence.evolution_service import git_evolution_service
from app.services.code_intelligence.ingestion_service import repository_ingestion_service


def _create_git_repo_with_history(repo_dir: Path) -> list[str]:
    """Helper creating a real multi-commit Git repository with various change types.
    
    Commit 1: Add math.py, logger.py, calc.py
    Commit 2: Modify calc.py (add function & modify function) and add helper.py
    Commit 3: Delete logger.py and rename helper.py to utils.py
    """
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "alice@codelens.io"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Alice Engineer"], cwd=str(repo_dir), check=True, capture_output=True)

    # Commit 1
    (repo_dir / "math_lib.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n",
        encoding="utf-8",
    )
    (repo_dir / "logger.py").write_text(
        "def log_msg(msg):\n    print(msg)\n",
        encoding="utf-8",
    )
    (repo_dir / "calc.py").write_text(
        "from math_lib import add\n\ndef calculate_total(x, y):\n    return add(x, y)\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit: math, logger, and calc"], cwd=str(repo_dir), check=True, capture_output=True)
    c1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), check=True, capture_output=True, text=True).stdout.strip()

    # Commit 2: Modify calc.py, add helper.py
    (repo_dir / "calc.py").write_text(
        "from math_lib import add, multiply\n\ndef calculate_total(x, y):\n    # Updated calculation with multiplier\n    return multiply(add(x, y), 2)\n\ndef square(n):\n    return multiply(n, n)\n",
        encoding="utf-8",
    )
    (repo_dir / "helper.py").write_text(
        "def format_result(val):\n    return f'Total: {val}'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Enhance calc and add helper"], cwd=str(repo_dir), check=True, capture_output=True)
    c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), check=True, capture_output=True, text=True).stdout.strip()

    # Commit 3: Delete logger.py and rename helper.py to utils.py
    (repo_dir / "logger.py").unlink()
    subprocess.run(["git", "rm", "logger.py"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "mv", "helper.py", "utils.py"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Remove logger and rename helper to utils"], cwd=str(repo_dir), check=True, capture_output=True)
    c3 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), check=True, capture_output=True, text=True).stdout.strip()

    return [c1, c2, c3]


def test_git_commit_ingestion_and_ordering(db_session: Session, tmp_path: Path):
    """Test git commits ingestion, parent hashing, and reverse chronological ordering."""
    repo_dir = tmp_path / "repo1"
    commits = _create_git_repo_with_history(repo_dir)

    repo = Repository(
        name="test-repo-ordering",
        url=str(repo_dir),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    result = repository_ingestion_service.ingest_repository(db=db_session, repository=repo)
    assert result.repository_id == repo.id

    # Retrieve commits via service
    commit_list = git_evolution_service.list_commits(db_session, repository_id=repo.id)
    assert len(commit_list) == 3
    # Reverse chronological: most recent first
    assert commit_list[0].commit_hash == commits[2]
    assert commit_list[1].commit_hash == commits[1]
    assert commit_list[2].commit_hash == commits[0]

    # Verify commit metadata
    head_commit = commit_list[0]
    assert head_commit.author_name == "Alice Engineer"
    assert head_commit.author_email == "alice@codelens.io"
    assert head_commit.commit_message == "Remove logger and rename helper to utils"
    assert head_commit.parent_hash == commits[1]
    assert head_commit.repository_version_id == result.repository_version_id


def test_commit_detail_file_and_symbol_changes(db_session: Session, tmp_path: Path):
    """Test file change detection (A, M, D, R) and symbol changes (ADDED, MODIFIED, DELETED)."""
    repo_dir = tmp_path / "repo2"
    commits = _create_git_repo_with_history(repo_dir)

    repo = Repository(
        name="test-repo-details",
        url=str(repo_dir),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repository_ingestion_service.ingest_repository(db=db_session, repository=repo)

    # 1. Commit 1 details (Initial commit)
    c1_detail = git_evolution_service.get_commit_details(db_session, repo.id, commits[0])
    assert c1_detail.commit_hash == commits[0]
    assert c1_detail.parent_hash is None
    assert c1_detail.files_changed_count == 3
    added_files = {fc.file_path for fc in c1_detail.files}
    assert added_files == {"math_lib.py", "logger.py", "calc.py"}
    for fc in c1_detail.files:
        assert fc.change_type in ("A", "ADDED")

    c1_symbols = {sc.symbol_name: sc.change_type for sc in c1_detail.symbols}
    assert c1_symbols["add"] == "ADDED"
    assert c1_symbols["multiply"] == "ADDED"
    assert c1_symbols["log_msg"] == "ADDED"
    assert c1_symbols["calculate_total"] == "ADDED"

    # 2. Commit 2 details (Modify calc.py, add helper.py)
    c2_detail = git_evolution_service.get_commit_details(db_session, repo.id, commits[1])
    assert c2_detail.parent_hash == commits[0]
    file_changes_c2 = {fc.file_path: fc.change_type for fc in c2_detail.files}
    assert file_changes_c2["calc.py"] in ("M", "MODIFIED")
    assert file_changes_c2["helper.py"] in ("A", "ADDED")

    c2_symbols = {sc.symbol_name: sc.change_type for sc in c2_detail.symbols}
    assert c2_symbols["calculate_total"] == "MODIFIED"
    assert c2_symbols["square"] == "ADDED"
    assert c2_symbols["format_result"] == "ADDED"

    # 3. Commit 3 details (Delete logger.py, rename helper.py to utils.py)
    c3_detail = git_evolution_service.get_commit_details(db_session, repo.id, commits[2])
    deleted_files = [fc for fc in c3_detail.files if fc.change_type in ("D", "DELETED")]
    assert len(deleted_files) == 1
    assert deleted_files[0].file_path == "logger.py"

    renamed_files = [fc for fc in c3_detail.files if fc.change_type in ("R", "RENAMED")]
    assert len(renamed_files) == 1
    assert renamed_files[0].file_path == "utils.py"
    assert renamed_files[0].old_path == "helper.py"

    c3_symbols = {sc.symbol_name: sc.change_type for sc in c3_detail.symbols}
    assert c3_symbols["log_msg"] == "DELETED"


def test_file_history_query(db_session: Session, tmp_path: Path):
    """Test file history query returning commits, stats, and changed symbols."""
    repo_dir = tmp_path / "repo3"
    commits = _create_git_repo_with_history(repo_dir)

    repo = Repository(
        name="test-repo-file-history",
        url=str(repo_dir),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    result = repository_ingestion_service.ingest_repository(db=db_session, repository=repo)

    # Find calc.py FileRecord in DB
    calc_file = next(f for f in repo.versions[-1].files if f.path == "calc.py")

    file_history = git_evolution_service.get_file_history(db_session, file_id=calc_file.id)
    assert file_history.file_id == calc_file.id
    assert file_history.file_path == "calc.py"
    assert file_history.total_commits == 2
    assert file_history.history[0].commit_hash == commits[1]
    assert file_history.history[1].commit_hash == commits[0]

    # Verify changed symbols listed per commit
    c2_history = file_history.history[0]
    assert any("calculate_total" in s for s in c2_history.changed_symbols)
    assert any("square" in s for s in c2_history.changed_symbols)


def test_symbol_history_query(db_session: Session, tmp_path: Path):
    """Test symbol evolution history tracking introduction and modification."""
    repo_dir = tmp_path / "repo4"
    commits = _create_git_repo_with_history(repo_dir)

    repo = Repository(
        name="test-repo-sym-history",
        url=str(repo_dir),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repository_ingestion_service.ingest_repository(db=db_session, repository=repo)

    calc_file = next(f for f in repo.versions[-1].files if f.path == "calc.py")
    calc_total_sym = next(s for s in calc_file.symbols if s.name == "calculate_total")

    sym_history = git_evolution_service.get_symbol_history(db_session, symbol_id=calc_total_sym.id)
    assert sym_history.symbol_id == calc_total_sym.id
    assert sym_history.name == "calculate_total"
    assert sym_history.total_commits == 2
    assert sym_history.introduced_at is not None
    assert sym_history.last_modified_at is not None

    # History timeline: Commit 2 (MODIFIED), Commit 1 (ADDED)
    assert sym_history.history[0].commit_hash == commits[1]
    assert sym_history.history[0].change_type == "MODIFIED"
    assert sym_history.history[1].commit_hash == commits[0]
    assert sym_history.history[1].change_type == "ADDED"


def test_commit_impact_analysis(db_session: Session, tmp_path: Path):
    """Test commit-level impact analysis finding affected callers and files."""
    repo_dir = tmp_path / "repo5"
    repo_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "eval@codelens.io"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CodeLens Impact"], cwd=str(repo_dir), check=True, capture_output=True)

    # Commit 1: Base files
    (repo_dir / "db.py").write_text("def query(q):\n    return []\n", encoding="utf-8")
    (repo_dir / "service.py").write_text(
        "from db import query\n\ndef get_user():\n    return query('user')\n",
        encoding="utf-8",
    )
    (repo_dir / "controller.py").write_text(
        "from service import get_user\n\ndef handle_request():\n    return get_user()\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit 1: Initial service"], cwd=str(repo_dir), check=True, capture_output=True)
    c1 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), check=True, capture_output=True, text=True).stdout.strip()

    # Commit 2: Modify db.py query function
    (repo_dir / "db.py").write_text(
        "def query(q):\n    # Updated query with connection pool\n    return [{'data': q}]\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Commit 2: Update db query"], cwd=str(repo_dir), check=True, capture_output=True)
    c2 = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), check=True, capture_output=True, text=True).stdout.strip()

    repo = Repository(
        name="test-repo-commit-impact",
        url=str(repo_dir),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repository_ingestion_service.ingest_repository(db=db_session, repository=repo)

    # Analyze commit 2 impact
    impact = git_evolution_service.analyze_commit_impact(db_session, repository_id=repo.id, commit_hash=c2)
    assert impact.commit_hash == c2
    assert impact.changed_symbols_count >= 1

    changed_names = [sc.symbol_name for sc in impact.changed_symbols]
    assert "query" in changed_names

    # Direct callers: get_user (in service.py)
    # Transitive callers: handle_request (in controller.py)
    affected_symbol_names = [s.name for s in impact.affected_symbols]
    assert "get_user" in affected_symbol_names
    assert "handle_request" in affected_symbol_names

    get_user_item = next(s for s in impact.affected_symbols if s.name == "get_user")
    assert get_user_item.impact_type == "DIRECT"
    assert get_user_item.distance == 1

    handle_req_item = next(s for s in impact.affected_symbols if s.name == "handle_request")
    assert handle_req_item.impact_type == "TRANSITIVE"
    assert handle_req_item.distance == 2

    # Affected files
    affected_files = [f.path for f in impact.affected_files]
    assert "service.py" in affected_files
    assert "controller.py" in affected_files


def test_git_evolution_rest_apis(client: TestClient, db_session: Session, tmp_path: Path):
    """Test REST API endpoints for commits, commit details, commit impact, file history, and symbol history."""
    repo_dir = tmp_path / "repo_api"
    commits = _create_git_repo_with_history(repo_dir)

    repo = Repository(
        name="test-repo-api",
        url=str(repo_dir),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    repository_ingestion_service.ingest_repository(db=db_session, repository=repo)

    # 1. GET /api/v1/repositories/{id}/commits
    resp = client.get(f"/api/v1/repositories/{repo.id}/commits")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["commit_hash"] == commits[2]

    # 2. GET /api/v1/repositories/{id}/commits/{commit_hash}
    resp = client.get(f"/api/v1/repositories/{repo.id}/commits/{commits[1]}")
    assert resp.status_code == 200
    c_data = resp.json()
    assert c_data["commit_hash"] == commits[1]
    assert len(c_data["files"]) >= 2
    assert len(c_data["symbols"]) >= 3

    # 3. GET /api/v1/repositories/{id}/commits/{commit_hash}/impact
    resp = client.get(f"/api/v1/repositories/{repo.id}/commits/{commits[1]}/impact")
    assert resp.status_code == 200
    impact_data = resp.json()
    assert impact_data["commit_hash"] == commits[1]
    assert "affected_symbols" in impact_data
    assert "affected_files" in impact_data

    # 4. GET /api/v1/files/{file_id}/history
    calc_file = next(f for f in repo.versions[-1].files if f.path == "calc.py")
    resp = client.get(f"/api/v1/files/{calc_file.id}/history")
    assert resp.status_code == 200
    file_hist = resp.json()
    assert file_hist["file_id"] == calc_file.id
    assert file_hist["total_commits"] == 2

    # 5. GET /api/v1/symbols/{symbol_id}/history
    calc_sym = next(s for s in calc_file.symbols if s.name == "calculate_total")
    resp = client.get(f"/api/v1/symbols/{calc_sym.id}/history")
    assert resp.status_code == 200
    sym_hist = resp.json()
    assert sym_hist["symbol_id"] == calc_sym.id
    assert sym_hist["total_commits"] == 2

    # 6. 404 Error handling
    assert client.get(f"/api/v1/repositories/{repo.id}/commits/nonexistent").status_code == 404
    assert client.get("/api/v1/files/999999/history").status_code == 404
    assert client.get("/api/v1/symbols/999999/history").status_code == 404
    assert client.get("/api/v1/repositories/999999/commits").status_code == 404
