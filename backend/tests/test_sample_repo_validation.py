import subprocess
from pathlib import Path
from sqlalchemy.orm import Session

from app.models.repository import Repository
from app.services.code_intelligence.ingestion_service import repository_ingestion_service


def test_real_sample_repository_validation(db_session: Session, tmp_path: Path):
    """Real deterministic repository validation matching Section 22 specification.
    
    Structure:
    sample_repo/
    ├── app/
    │   ├── database.py
    │   ├── tax.py
    │   └── invoice.py
    ├── src/
    │   ├── utils.ts
    │   └── payment.ts
    └── tests/
        └── test_invoice.py
    
    Relationship chain:
    test_invoice.py calls invoice.py
        ↓ calls
    tax.py
        ↓ calls
    database.py
    """
    repo_root = tmp_path / "sample_repo"
    app_dir = repo_root / "app"
    src_dir = repo_root / "src"
    tests_dir = repo_root / "tests"

    app_dir.mkdir(parents=True)
    src_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)

    # 1. database.py
    (app_dir / "database.py").write_text(
        'def execute_query(sql_statement):\n    """Execute a raw SQL query against database."""\n    return [{"id": 1, "rate": 0.05}]\n',
        encoding="utf-8",
    )

    # 2. tax.py
    (app_dir / "tax.py").write_text(
        'from app.database import execute_query\n\ndef calculate_tax(amount):\n    """Calculate tax by fetching rates from database."""\n    rates = execute_query("SELECT rate FROM tax_rates")\n    rate = rates[0]["rate"]\n    return amount * rate\n',
        encoding="utf-8",
    )

    # 3. invoice.py
    (app_dir / "invoice.py").write_text(
        'from app.tax import calculate_tax\n\nclass InvoiceService:\n    def __init__(self, currency="USD"):\n        self.currency = currency\n\n    def process_invoice(self, amount):\n        tax = calculate_tax(amount)\n        return amount + tax\n',
        encoding="utf-8",
    )

    # 4. test_invoice.py
    (tests_dir / "test_invoice.py").write_text(
        'from app.invoice import InvoiceService\n\ndef test_process():\n    service = InvoiceService()\n    result = service.process_invoice(100)\n    return result\n',
        encoding="utf-8",
    )

    # 5. TypeScript files (multi-language validation)
    (src_dir / "utils.ts").write_text(
        'export function formatAmount(val: number): string {\n    return "$" + val.toFixed(2);\n}\n',
        encoding="utf-8",
    )
    (src_dir / "payment.ts").write_text(
        'import { formatAmount } from "./utils";\n\nexport function processPayment(amount: number): string {\n    return formatAmount(amount);\n}\n',
        encoding="utf-8",
    )

    # Initialize Git repository
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "eval@codelens.io"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "CodeLens Evaluation"], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=str(repo_root), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Deterministic validation repository"], cwd=str(repo_root), check=True, capture_output=True)

    git_sha_res = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_root), check=True, capture_output=True, text=True)
    expected_sha = git_sha_res.stdout.strip()

    # Create CodeLens repository record
    repo = Repository(
        name="sample-project",
        url=str(repo_root),
        default_branch="main",
        status="pending",
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)

    # Execute ingestion
    result = repository_ingestion_service.ingest_repository(
        db=db_session,
        repository=repo,
    )

    # Assert Ingestion summary stats
    assert result.commit_sha == expected_sha
    assert result.branch_name == "main"
    assert result.files_count == 6  # 4 Python files + 2 TypeScript files
    assert result.symbols_count >= 8
    assert result.dependencies_count > 0

    print(f"\nRepository analyzed successfully\n")
    print(f"Repository:\n    {repo.name}\n")
    print(f"Commit:\n    {result.commit_sha[:7]}...\n")
    print(f"Files:\n    {result.files_count}\n")
    print(f"Symbols:\n    {result.symbols_count}\n")
    print(f"Dependencies:\n    {result.dependencies_count}\n")
    print(f"Calls:\n    {result.calls_count}\n")
    print(f"Analysis:\n    COMPLETED\n")

    # Query Version
    version = repo.versions[0]
    assert version.commit_sha == expected_sha
    assert version.commit_message == "Deterministic validation repository"

    # Query Files
    files_by_path = {f.path: f for f in version.files}
    assert "app/database.py" in files_by_path
    assert "app/tax.py" in files_by_path
    assert "app/invoice.py" in files_by_path
    assert "tests/test_invoice.py" in files_by_path
    assert "src/utils.ts" in files_by_path
    assert "src/payment.ts" in files_by_path

    # Verify all files are PARSED
    for f in version.files:
        assert f.parsing_status == "PARSED", f"File {f.path} failed with {f.error_message}"

    # Query Symbols
    all_symbols = [s for f in version.files for s in f.symbols]
    symbols_by_qname = {s.qualified_name: s for s in all_symbols}

    assert "execute_query" in symbols_by_qname
    assert "calculate_tax" in symbols_by_qname
    assert "InvoiceService" in symbols_by_qname
    assert "InvoiceService.process_invoice" in symbols_by_qname
    assert "test_process" in symbols_by_qname
    assert "formatAmount" in symbols_by_qname
    assert "processPayment" in symbols_by_qname

    # Query Dependencies and Call Graph
    call_deps = [d for d in version.dependencies if d.relationship_type == "CALL"]
    resolved_calls = [d for d in call_deps if d.resolution_status == "RESOLVED"]

    # Map: caller symbol ID -> callee symbol ID
    call_pairs = {(d.caller_symbol_id, d.callee_symbol_id) for d in resolved_calls}

    # 1. invoice.py (InvoiceService.process_invoice) calls tax.py (calculate_tax)
    process_sym_id = symbols_by_qname["InvoiceService.process_invoice"].id
    tax_sym_id = symbols_by_qname["calculate_tax"].id
    assert (process_sym_id, tax_sym_id) in call_pairs, "InvoiceService.process_invoice must call calculate_tax"

    # 2. tax.py (calculate_tax) calls database.py (execute_query)
    db_sym_id = symbols_by_qname["execute_query"].id
    assert (tax_sym_id, db_sym_id) in call_pairs, "calculate_tax must call execute_query"

    # 3. TypeScript: payment.ts (processPayment) calls utils.ts (formatAmount)
    payment_sym_id = symbols_by_qname["processPayment"].id
    format_sym_id = symbols_by_qname["formatAmount"].id
    assert (payment_sym_id, format_sym_id) in call_pairs, "processPayment must call formatAmount"


def test_real_sample_repository_graph_and_navigation(db_session: Session, tmp_path: Path):
    """Sprint 3 Phase 11: Validate Graph and Navigation on real ingested repository."""
    from app.services.code_intelligence.graph_service import graph_service

    # Ingest the real sample repo
    test_real_sample_repository_validation(db_session, tmp_path)

    repo = db_session.query(Repository).filter_by(name="sample-project").first()
    assert repo is not None
    version = repo.versions[0]

    # 1. Graph generation succeeds
    graph = graph_service.get_repository_graph(db_session, repository_id=repo.id)
    assert graph.repository_id == repo.id
    assert graph.total_nodes > 0
    assert graph.total_edges > 0
    assert any(n.type == "FILE" for n in graph.nodes)
    assert any(n.type == "SYMBOL" for n in graph.nodes)
    assert any(e.relationship == "IMPORT" for e in graph.edges)
    assert any(e.relationship == "CALL" for e in graph.edges)

    # Lookup symbols
    all_symbols = [s for f in version.files for s in f.symbols]
    symbols_by_name = {s.name: s for s in all_symbols}

    calc_tax_sym = symbols_by_name["calculate_tax"]
    proc_inv_sym = symbols_by_name["process_invoice"]
    exec_query_sym = symbols_by_name["execute_query"]
    test_proc_sym = symbols_by_name["test_process"]
    format_amt_sym = symbols_by_name["formatAmount"]

    # 2. Callers can be retrieved for a real function
    callers = graph_service.get_callers(db_session, symbol_id=calc_tax_sym.id)
    caller_ids = [c.caller_symbol_id for c in callers]
    assert proc_inv_sym.id in caller_ids

    # 3. Callees can be retrieved for a real function
    callees = graph_service.get_callees(db_session, symbol_id=proc_inv_sym.id)
    callee_ids = [c.callee_symbol_id for c in callees]
    assert calc_tax_sym.id in callee_ids

    # 4. Dependencies can be retrieved for a real file
    files_by_path = {f.path: f for f in version.files}
    inv_file = files_by_path["app/invoice.py"]
    tax_file = files_by_path["app/tax.py"]

    file_deps = graph_service.get_file_dependencies(db_session, file_id=inv_file.id)
    target_paths = [d.target_file_path for d in file_deps if d.target_file_path]
    assert "app/tax.py" in target_paths

    file_dependents = graph_service.get_file_dependents(db_session, file_id=tax_file.id)
    source_paths = [d.source_file_path for d in file_dependents]
    assert "app/invoice.py" in source_paths

    # 5. Path can be found between two known connected functions
    # process_invoice -> calculate_tax -> execute_query
    paths_res = graph_service.find_paths(
        db_session,
        source_symbol_id=proc_inv_sym.id,
        target_symbol_id=exec_query_sym.id,
    )
    assert paths_res.paths_count >= 1
    found_path = paths_res.paths[0]
    path_symbol_names = [step.name for step in found_path]
    assert path_symbol_names == ["process_invoice", "calculate_tax", "execute_query"]

    # 6. No path is reported between disconnected functions (Python test_process vs TS formatAmount)
    disconnected_paths = graph_service.find_paths(
        db_session,
        source_symbol_id=test_proc_sym.id,
        target_symbol_id=format_amt_sym.id,
    )
    assert disconnected_paths.paths_count == 0
    assert disconnected_paths.paths == []
