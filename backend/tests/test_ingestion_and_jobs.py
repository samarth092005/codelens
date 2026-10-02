import subprocess
from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.services.code_intelligence.analysis_service import repository_analysis_service
from app.services.code_intelligence.git_service import GitRepositoryError
from app.services.code_intelligence.ingestion_service import repository_ingestion_service


def _init_git_repo(repo_dir: Path) -> str:
    """Helper to initialize a real git repo and create an initial commit."""
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@codelens.io"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CodeLens Tester"], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Sprint 2 integration commit"], cwd=str(repo_dir), check=True, capture_output=True)
    res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_dir), check=True, capture_output=True, text=True)
    return res.stdout.strip()


def test_ingestion_and_persistence(db_session: Session, tmp_path: Path):
    # Set up sample repo files
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "database.py").write_text(
        "def query_db(sql):\n    return ['record1', 'record2']\n",
        encoding="utf-8",
    )
    (app_dir / "tax.py").write_text(
        "from app.database import query_db\n\ndef calculate_tax(amount):\n    query_db('SELECT tax')\n    return amount * 0.1\n",
        encoding="utf-8",
    )
    (app_dir / "invoice.py").write_text(
        "from app.tax import calculate_tax\n\nclass InvoiceProcessor:\n    def process(self, total):\n        tax = calculate_tax(total)\n        return total + tax\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text("# Test Repo\n", encoding="utf-8")

    commit_sha = _init_git_repo(tmp_path)

    # Create repository in DB
    repo = Repository(
        name="test-ingest-repo",
        url=str(tmp_path),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # Ingest repository
    result = repository_ingestion_service.ingest_repository(
        db=db_session,
        repository=repo,
    )

    assert result.repository_id == repo.id
    assert result.commit_sha == commit_sha
    assert result.branch_name == "main"
    assert result.files_count == 4  # 3 py files + 1 md file
    assert result.symbols_count >= 4  # query_db, calculate_tax, InvoiceProcessor, process
    assert result.dependencies_count > 0

    # Query DB entities directly
    version = repo.versions[0]
    assert version.commit_sha == commit_sha
    assert version.commit_message == "Sprint 2 integration commit"
    assert version.analyzed_at is not None

    # Check files stored in DB
    file_paths = {f.path for f in version.files}
    assert "app/database.py" in file_paths
    assert "app/tax.py" in file_paths
    assert "app/invoice.py" in file_paths
    assert "README.md" in file_paths

    # Check symbols stored in DB
    symbols_by_name = {s.name: s for f in version.files for s in f.symbols}
    assert "InvoiceProcessor" in symbols_by_name
    assert symbols_by_name["InvoiceProcessor"].symbol_type == "class"
    assert "process" in symbols_by_name
    assert symbols_by_name["process"].symbol_type == "method"
    assert symbols_by_name["process"].parent_symbol_id == symbols_by_name["InvoiceProcessor"].id

    # Check dependencies stored in DB
    call_deps = [d for d in version.dependencies if d.relationship_type == "CALL"]
    callee_names = [d.callee_name for d in call_deps]
    assert "calculate_tax" in callee_names
    assert "query_db" in callee_names

    # calculate_tax call was resolved to calculate_tax symbol!
    tax_call = next(d for d in call_deps if d.callee_name == "calculate_tax")
    assert tax_call.resolution_status == "RESOLVED"
    assert tax_call.callee_symbol_id == symbols_by_name["calculate_tax"].id


def test_analysis_job_lifecycle(db_session: Session, tmp_path: Path):
    # Setup git repo
    (tmp_path / "main.py").write_text("def hello(): pass", encoding="utf-8")
    _init_git_repo(tmp_path)

    repo = Repository(
        name="job-test-repo",
        url=str(tmp_path),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # Trigger analysis job
    job = repository_analysis_service.trigger_analysis(db_session, repository_id=repo.id)
    assert job.status == "COMPLETED"
    assert job.repository_version_id is not None
    assert job.started_at is not None
    assert job.completed_at is not None
    assert job.error_message is None


def test_ingestion_invalid_git_directory(db_session: Session, tmp_path: Path):
    # Directory exists but has no .git
    repo = Repository(
        name="non-git-repo",
        url=str(tmp_path),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()

    with pytest.raises(GitRepositoryError, match="not a valid Git repository"):
        repository_ingestion_service.ingest_repository(db_session, repository=repo)
