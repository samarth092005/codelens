from pathlib import Path
import tree_sitter_typescript as tstypescript
from tree_sitter import Language, Parser

from app.services.code_intelligence.parser.base import ParseResult
from app.services.code_intelligence.parser.javascript_parser import JavaScriptParser


class TypeScriptParser(JavaScriptParser):
    """Tree-sitter parser for TypeScript and TSX source files."""

    def __init__(self) -> None:
        self.ts_language = Language(tstypescript.language_typescript())
        self.tsx_language = Language(tstypescript.language_tsx())
        self.ts_parser = Parser(self.ts_language)
        self.tsx_parser = Parser(self.tsx_language)
        super().__init__(language=self.ts_language)

    def parse(self, source_code: bytes, file_rel_path: str) -> ParseResult:
        # Select appropriate TS or TSX parser
        ext = Path(file_rel_path).suffix.lower()
        if ext == ".tsx":
            self.parser = self.tsx_parser
            self.language = self.tsx_language
        else:
            self.parser = self.ts_parser
            self.language = self.ts_language

        result = super().parse(source_code, file_rel_path)
        return ParseResult(
            file_rel_path=result.file_rel_path,
            language="typescript",
            status=result.status,
            error_message=result.error_message,
            symbols=result.symbols,
            imports=result.imports,
            calls=result.calls,
        )
