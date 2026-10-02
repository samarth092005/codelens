from pathlib import Path


class LanguageDetector:
    """Detect programming language of a source file based on extension and filename."""

    # Language identifiers
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    UNKNOWN = "unknown"

    SUPPORTED_LANGUAGES = {PYTHON, JAVASCRIPT, TYPESCRIPT}

    EXTENSION_MAP: dict[str, str] = {
        # Python
        ".py": PYTHON,
        ".pyi": PYTHON,
        # JavaScript
        ".js": JAVASCRIPT,
        ".jsx": JAVASCRIPT,
        ".mjs": JAVASCRIPT,
        ".cjs": JAVASCRIPT,
        # TypeScript
        ".ts": TYPESCRIPT,
        ".tsx": TYPESCRIPT,
        ".mts": TYPESCRIPT,
        ".cts": TYPESCRIPT,
    }

    def detect_language(self, path: Path | str) -> str:
        """Detect the language for a given file path.
        
        Returns the canonical language string (e.g. 'python', 'javascript', 'typescript')
        or 'unknown' if not recognized.
        """
        p = Path(path)
        ext = p.suffix.lower()
        return self.EXTENSION_MAP.get(ext, self.UNKNOWN)

    def is_supported(self, language: str) -> bool:
        """Check if a language is supported for parsing in Sprint 2."""
        return language in self.SUPPORTED_LANGUAGES


language_detector = LanguageDetector()
