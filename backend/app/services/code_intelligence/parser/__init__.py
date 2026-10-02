from app.services.code_intelligence.parser.base import (
    CodeParser,
    ExtractedCall,
    ExtractedImport,
    ExtractedSymbol,
    ParseResult,
)
from app.services.code_intelligence.parser.python_parser import PythonParser
from app.services.code_intelligence.parser.javascript_parser import JavaScriptParser
from app.services.code_intelligence.parser.typescript_parser import TypeScriptParser


class CompositeCodeParser:
    """Unified code parser dispatching to language-specific Tree-sitter parsers."""

    def __init__(self) -> None:
        self.parsers: dict[str, CodeParser] = {
            "python": PythonParser(),
            "javascript": JavaScriptParser(),
            "typescript": TypeScriptParser(),
        }

    def parse(self, source_bytes: bytes, file_rel_path: str, language: str) -> ParseResult:
        parser = self.parsers.get(language)
        if parser is None:
            return ParseResult(
                file_rel_path=file_rel_path,
                language=language,
                status="UNSUPPORTED",
                error_message=f"Language '{language}' is not supported for AST parsing",
                symbols=[],
                imports=[],
                calls=[],
            )

        try:
            return parser.parse(source_bytes, file_rel_path)
        except Exception as e:
            return ParseResult(
                file_rel_path=file_rel_path,
                language=language,
                status="PARSE_ERROR",
                error_message=f"Parser execution failed: {e}",
                symbols=[],
                imports=[],
                calls=[],
            )


composite_parser = CompositeCodeParser()

__all__ = [
    "CodeParser",
    "ExtractedSymbol",
    "ExtractedImport",
    "ExtractedCall",
    "ParseResult",
    "PythonParser",
    "JavaScriptParser",
    "TypeScriptParser",
    "CompositeCodeParser",
    "composite_parser",
]
