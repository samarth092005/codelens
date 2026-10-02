from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractedSymbol:
    name: str
    qualified_name: str
    symbol_type: str  # function, class, method
    parent_name: str | None
    line_start: int
    line_end: int
    visibility: str | None = None  # public, private, protected


@dataclass
class ExtractedImport:
    source_file_rel_path: str
    imported_module: str
    imported_names: list[str] = field(default_factory=list)
    alias: str | None = None
    import_type: str = "module"  # module, from, named, default, require
    line_number: int = 1


@dataclass
class ExtractedCall:
    caller_name: str | None  # qualified_name of enclosing function/method
    callee_name: str
    line_number: int
    source_file_rel_path: str


@dataclass
class ParseResult:
    file_rel_path: str
    language: str
    status: str  # PARSED, UNSUPPORTED, PARSE_ERROR
    error_message: str | None = None
    symbols: list[ExtractedSymbol] = field(default_factory=list)
    imports: list[ExtractedImport] = field(default_factory=list)
    calls: list[ExtractedCall] = field(default_factory=list)


class CodeParser(ABC):
    """Abstract base class for language-specific Tree-sitter code parsers."""

    @abstractmethod
    def parse(self, source_code: bytes, file_rel_path: str) -> ParseResult:
        """Parse source code bytes and return extracted symbols, imports, and calls."""
        pass
