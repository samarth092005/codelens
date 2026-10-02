from pathlib import Path
import pytest
from app.services.code_intelligence.file_discovery import FileDiscoveryService


def test_file_discovery_filters_ignored_and_binary(tmp_path: Path):
    service = FileDiscoveryService()

    # Valid source files
    (tmp_path / "app").mkdir()
    py_file = tmp_path / "app" / "main.py"
    py_file.write_text("print('hello')", encoding="utf-8")

    ts_file = tmp_path / "app" / "service.ts"
    ts_file.write_text("export const x = 1;", encoding="utf-8")

    # Unsupported text file
    doc_file = tmp_path / "README.md"
    doc_file.write_text("# Readme", encoding="utf-8")

    # Ignored directories
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git config", encoding="utf-8")

    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "main.cpython-314.pyc").write_text("cache", encoding="utf-8")

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "package.js").write_text("pkg", encoding="utf-8")

    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("venv", encoding="utf-8")

    # Binary file with null bytes
    bin_file = tmp_path / "app" / "data.bin"
    bin_file.write_bytes(b"\x00\x01\x02\x03\x04")

    # Binary file by extension
    png_file = tmp_path / "app" / "logo.png"
    png_file.write_bytes(b"fake png header")

    discovered = service.discover_files(tmp_path)
    rel_paths = [f.relative_path for f in discovered]

    # Must contain valid source and markdown files
    assert "app/main.py" in rel_paths
    assert "app/service.ts" in rel_paths
    assert "README.md" in rel_paths

    # Must NOT contain ignored dirs or binaries
    assert not any(p.startswith(".git") for p in rel_paths)
    assert not any(p.startswith("__pycache__") for p in rel_paths)
    assert not any(p.startswith("node_modules") for p in rel_paths)
    assert not any(p.startswith(".venv") for p in rel_paths)
    assert "app/data.bin" not in rel_paths
    assert "app/logo.png" not in rel_paths

    # Check properties
    py_discovered = next(f for f in discovered if f.relative_path == "app/main.py")
    assert py_discovered.language == "python"
    assert py_discovered.is_supported is True
    assert py_discovered.size_bytes > 0


def test_file_discovery_invalid_path():
    service = FileDiscoveryService()
    with pytest.raises(ValueError, match="does not exist"):
        service.discover_files("C:/nonexistent_path_abc_123")
