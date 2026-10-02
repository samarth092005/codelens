import os
from dataclasses import dataclass
from pathlib import Path
from app.services.code_intelligence.language_detector import LanguageDetector, language_detector


@dataclass(frozen=True)
class DiscoveredFile:
    path: Path
    relative_path: str
    extension: str
    language: str
    size_bytes: int
    is_supported: bool


class FileDiscoveryService:
    """Service to safely discover source files in a repository while ignoring build/cache/binary files."""

    IGNORED_DIRECTORIES: set[str] = {
        ".git",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        "coverage",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".idea",
        ".vscode",
        ".next",
        ".nuxt",
        "target",
        "vendor",
        ".system_generated",
    }

    BINARY_EXTENSIONS: set[str] = {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".exe", ".dll", ".so", ".dylib", ".bin",
        ".pdf", ".doc", ".docx", ".zip", ".tar", ".gz", ".7z",
        ".woff", ".woff2", ".ttf", ".eot",
        ".pyc", ".pyo", ".pyd", ".class",
        ".db", ".sqlite", ".sqlite3",
        ".pkl", ".pickle", ".npy", ".npz", ".whl",
        ".jar", ".war", ".lock",
    }

    # Maximum file size to parse (e.g. 5MB)
    MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024

    def __init__(self, detector: LanguageDetector = language_detector) -> None:
        self.detector = detector

    def is_binary_file(self, file_path: Path) -> bool:
        """Check if a file is binary using extension and byte inspection."""
        if file_path.suffix.lower() in self.BINARY_EXTENSIONS:
            return True
        try:
            with open(file_path, "rb") as f:
                chunk = f.read(1024)
                if b"\x00" in chunk:
                    return True
        except (OSError, PermissionError):
            return True
        return False

    def discover_files(self, repo_root: Path | str) -> list[DiscoveredFile]:
        """Discover all relevant source files in repository root safely.
        
        Guarantees:
        - Prevents directory traversal outside repo_root.
        - Excludes build, cache, test artifacts, and dependency directories.
        - Filters out binary files.
        - Detects programming language.
        """
        root = Path(repo_root).resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Repository directory does not exist or is not a directory: {repo_root}")

        discovered: list[DiscoveredFile] = []

        for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            # Prune ignored directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in self.IGNORED_DIRECTORIES and not d.startswith(".")
            ]

            current_dir = Path(dirpath).resolve()

            # Prevent traversal escapes
            try:
                current_dir.relative_to(root)
            except ValueError:
                continue

            for filename in filenames:
                file_path = current_dir / filename
                try:
                    resolved_file = file_path.resolve()
                    # Prevent symlink traversal outside root
                    resolved_file.relative_to(root)
                except (ValueError, RuntimeError):
                    continue

                if not resolved_file.is_file():
                    continue

                try:
                    stat_info = resolved_file.stat()
                except (OSError, PermissionError):
                    continue

                size = stat_info.st_size
                if size > self.MAX_FILE_SIZE_BYTES:
                    # Skip oversized generated files
                    continue

                if self.is_binary_file(resolved_file):
                    continue

                rel_path = resolved_file.relative_to(root).as_posix()
                ext = resolved_file.suffix.lower()
                lang = self.detector.detect_language(resolved_file)
                supported = self.detector.is_supported(lang)

                discovered.append(
                    DiscoveredFile(
                        path=resolved_file,
                        relative_path=rel_path,
                        extension=ext,
                        language=lang,
                        size_bytes=size,
                        is_supported=supported,
                    )
                )

        # Sort files deterministically by relative path
        discovered.sort(key=lambda f: f.relative_path)
        return discovered


file_discovery_service = FileDiscoveryService()
