from app.services.code_intelligence.parser.base import ExtractedCall, ExtractedImport
from app.services.code_intelligence.resolver import DependencyResolver


def test_dependency_resolver():
    resolver = DependencyResolver()

    # Files
    files_by_rel_path = {
        "app/invoice.py": 1,
        "app/tax.py": 2,
        "src/app.js": 3,
        "src/tax.js": 4,
    }
    file_languages = {
        1: "python",
        2: "python",
        3: "javascript",
        4: "javascript",
    }

    # Symbols: tax.py defines calculate_tax
    symbols_by_id = {
        10: {
            "name": "process_invoice",
            "qualified_name": "process_invoice",
            "file_id": 1,
            "parent_id": None,
        },
        20: {
            "name": "calculate_tax",
            "qualified_name": "calculate_tax",
            "file_id": 2,
            "parent_id": None,
        },
        30: {
            "name": "startApp",
            "qualified_name": "startApp",
            "file_id": 3,
            "parent_id": None,
        },
        40: {
            "name": "calculateTaxJS",
            "qualified_name": "calculateTaxJS",
            "file_id": 4,
            "parent_id": None,
        },
    }
    symbols_by_file = {
        1: [10],
        2: [20],
        3: [30],
        4: [40],
    }

    # Imports:
    # invoice.py imports app.tax (calculate_tax) and os (external)
    # src/app.js imports ./tax and lodash (external)
    raw_imports = [
        (1, ExtractedImport(source_file_rel_path="app/invoice.py", imported_module="app.tax", imported_names=["calculate_tax"], line_number=2)),
        (1, ExtractedImport(source_file_rel_path="app/invoice.py", imported_module="os", line_number=1)),
        (3, ExtractedImport(source_file_rel_path="src/app.js", imported_module="./tax", imported_names=["calculateTaxJS"], line_number=1)),
        (3, ExtractedImport(source_file_rel_path="src/app.js", imported_module="lodash", line_number=2)),
    ]

    # Calls:
    # invoice.py process_invoice calls calculate_tax (should resolve to symbol 20 in tax.py)
    # invoice.py process_invoice calls print (external)
    # invoice.py process_invoice calls unknown_function (unresolved)
    raw_calls = [
        (1, ExtractedCall(caller_name="process_invoice", callee_name="calculate_tax", line_number=5, source_file_rel_path="app/invoice.py")),
        (1, ExtractedCall(caller_name="process_invoice", callee_name="print", line_number=6, source_file_rel_path="app/invoice.py")),
        (1, ExtractedCall(caller_name="process_invoice", callee_name="unknown_external_func", line_number=7, source_file_rel_path="app/invoice.py")),
        (3, ExtractedCall(caller_name="startApp", callee_name="calculateTaxJS", line_number=4, source_file_rel_path="src/app.js")),
    ]

    resolved_imports, resolved_calls = resolver.resolve_dependencies(
        files_by_rel_path=files_by_rel_path,
        file_languages=file_languages,
        symbols_by_id=symbols_by_id,
        symbols_by_file=symbols_by_file,
        raw_imports=raw_imports,
        raw_calls=raw_calls,
    )

    # 1. Imports assertions
    imp_map = {i.imported_module: i for i in resolved_imports}
    assert imp_map["app.tax"].resolution_status == "RESOLVED"
    assert imp_map["app.tax"].target_file_id == 2

    assert imp_map["os"].resolution_status == "EXTERNAL"
    assert imp_map["os"].target_file_id is None

    assert imp_map["./tax"].resolution_status == "RESOLVED"
    assert imp_map["./tax"].target_file_id == 4

    assert imp_map["lodash"].resolution_status == "EXTERNAL"

    # 2. Calls assertions
    call_map = {c.callee_name: c for c in resolved_calls}

    # Python call resolution
    assert call_map["calculate_tax"].resolution_status == "RESOLVED"
    assert call_map["calculate_tax"].caller_symbol_id == 10
    assert call_map["calculate_tax"].callee_symbol_id == 20

    assert call_map["print"].resolution_status == "EXTERNAL"
    assert call_map["print"].callee_symbol_id is None

    assert call_map["unknown_external_func"].resolution_status == "UNRESOLVED"
    assert call_map["unknown_external_func"].callee_symbol_id is None

    # JS call resolution
    assert call_map["calculateTaxJS"].resolution_status == "RESOLVED"
    assert call_map["calculateTaxJS"].caller_symbol_id == 30
    assert call_map["calculateTaxJS"].callee_symbol_id == 40


def test_python_import_resolution_cases():
    """Focused test covering RESOLVED, EXTERNAL, and UNRESOLVED Python import cases."""
    resolver = DependencyResolver()

    files_by_rel_path = {
        "app/services/invoice.py": 1,
        "app/services/tax.py": 2,
        "app/utils.py": 3,
    }
    file_languages = {
        1: "python",
        2: "python",
        3: "python",
    }

    raw_imports = [
        # 1. RESOLVED cases:
        # 1a. Absolute internal import found in repo
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="app.services.tax", imported_names=["calculate_tax"], line_number=1)),
        # 1b. Relative internal import found in repo
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module=".tax", imported_names=["calculate_tax"], line_number=2)),
        # 1c. Parent-relative internal import found in repo
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="..utils", imported_names=["format_currency"], line_number=3)),

        # 2. EXTERNAL cases:
        # 2a. Python standard library module
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="os", line_number=4)),
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="json", line_number=5)),
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="datetime", line_number=6)),
        # 2b. Established third-party package
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="pandas", line_number=7)),
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="fastapi", line_number=8)),
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="requests", line_number=9)),

        # 3. UNRESOLVED cases:
        # 3a. Broken relative import (cannot be external)
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module=".missing_helper", line_number=10)),
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="..missing_util", line_number=11)),
        # 3b. Missing submodule from an internal repository package (e.g. app.services.nonexistent)
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="app.services.nonexistent", line_number=12)),
        # 3c. Arbitrary unknown package that cannot be established as outside repository
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="some_unregistered_custom_mod", line_number=13)),
        # 3d. Empty module
        (1, ExtractedImport(source_file_rel_path="app/services/invoice.py", imported_module="", line_number=14)),
    ]

    resolved_imports, _ = resolver.resolve_dependencies(
        files_by_rel_path=files_by_rel_path,
        file_languages=file_languages,
        symbols_by_id={},
        symbols_by_file={},
        raw_imports=raw_imports,
        raw_calls=[],
    )

    imp_map = {i.imported_module: i for i in resolved_imports}

    # Verify RESOLVED
    assert imp_map["app.services.tax"].resolution_status == "RESOLVED"
    assert imp_map["app.services.tax"].target_file_id == 2

    assert imp_map[".tax"].resolution_status == "RESOLVED"
    assert imp_map[".tax"].target_file_id == 2

    assert imp_map["..utils"].resolution_status == "RESOLVED"
    assert imp_map["..utils"].target_file_id == 3

    # Verify EXTERNAL
    assert imp_map["os"].resolution_status == "EXTERNAL"
    assert imp_map["os"].target_file_id is None

    assert imp_map["json"].resolution_status == "EXTERNAL"
    assert imp_map["json"].target_file_id is None

    assert imp_map["datetime"].resolution_status == "EXTERNAL"
    assert imp_map["datetime"].target_file_id is None

    assert imp_map["pandas"].resolution_status == "EXTERNAL"
    assert imp_map["pandas"].target_file_id is None

    assert imp_map["fastapi"].resolution_status == "EXTERNAL"
    assert imp_map["fastapi"].target_file_id is None

    assert imp_map["requests"].resolution_status == "EXTERNAL"
    assert imp_map["requests"].target_file_id is None

    # Verify UNRESOLVED
    assert imp_map[".missing_helper"].resolution_status == "UNRESOLVED"
    assert imp_map[".missing_helper"].target_file_id is None

    assert imp_map["..missing_util"].resolution_status == "UNRESOLVED"
    assert imp_map["..missing_util"].target_file_id is None

    assert imp_map["app.services.nonexistent"].resolution_status == "UNRESOLVED"
    assert imp_map["app.services.nonexistent"].target_file_id is None

    assert imp_map["some_unregistered_custom_mod"].resolution_status == "UNRESOLVED"
    assert imp_map["some_unregistered_custom_mod"].target_file_id is None

    assert imp_map[""].resolution_status == "UNRESOLVED"
    assert imp_map[""].target_file_id is None
