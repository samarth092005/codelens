import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from app.services.code_intelligence.parser.base import (
    CodeParser,
    ExtractedCall,
    ExtractedImport,
    ExtractedSymbol,
    ParseResult,
)


class PythonParser(CodeParser):
    """Tree-sitter parser for Python source files."""

    def __init__(self) -> None:
        self.language = Language(tspython.language())
        self.parser = Parser(self.language)

    def _determine_visibility(self, name: str) -> str:
        if name.startswith("__") and name.endswith("__"):
            return "public"  # Special dunder methods are public
        if name.startswith("__"):
            return "private"
        if name.startswith("_"):
            return "protected"
        return "public"

    def _node_text(self, node: Node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()

    def parse(self, source_code: bytes, file_rel_path: str) -> ParseResult:
        try:
            tree = self.parser.parse(source_code)
            root = tree.root_node

            symbols: list[ExtractedSymbol] = []
            imports: list[ExtractedImport] = []
            calls: list[ExtractedCall] = []

            # Check if root has errors or is empty
            has_error = root.has_error

            self._extract_entities(
                node=root,
                source_bytes=source_code,
                file_rel_path=file_rel_path,
                current_caller=None,
                current_class=None,
                symbols=symbols,
                imports=imports,
                calls=calls,
            )

            status = "PARSED"
            error_message = None
            if has_error and not symbols and not imports:
                # Completely unparseable file
                status = "PARSE_ERROR"
                error_message = "File contains unrecoverable syntax errors"

            return ParseResult(
                file_rel_path=file_rel_path,
                language="python",
                status=status,
                error_message=error_message,
                symbols=symbols,
                imports=imports,
                calls=calls,
            )
        except Exception as e:
            return ParseResult(
                file_rel_path=file_rel_path,
                language="python",
                status="PARSE_ERROR",
                error_message=f"Tree-sitter parse failed: {e}",
                symbols=[],
                imports=[],
                calls=[],
            )

    def _extract_entities(
        self,
        node: Node,
        source_bytes: bytes,
        file_rel_path: str,
        current_caller: str | None,
        current_class: str | None,
        symbols: list[ExtractedSymbol],
        imports: list[ExtractedImport],
        calls: list[ExtractedCall],
    ) -> None:
        node_type = node.type

        # 1. Imports
        if node_type == "import_statement":
            self._handle_import(node, source_bytes, file_rel_path, imports)
            return

        if node_type == "import_from_statement":
            self._handle_import_from(node, source_bytes, file_rel_path, imports)
            return

        # 2. Classes
        if node_type == "class_definition":
            class_name_node = node.child_by_field_name("name")
            if class_name_node:
                class_name = self._node_text(class_name_node, source_bytes)
                qualified_name = f"{current_class}.{class_name}" if current_class else class_name
                line_start = node.start_point.row + 1
                line_end = node.end_point.row + 1
                visibility = self._determine_visibility(class_name)

                symbols.append(
                    ExtractedSymbol(
                        name=class_name,
                        qualified_name=qualified_name,
                        symbol_type="class",
                        parent_name=current_class,
                        line_start=line_start,
                        line_end=line_end,
                        visibility=visibility,
                    )
                )

                # Process class body with updated class context
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._extract_entities(
                            node=child,
                            source_bytes=source_bytes,
                            file_rel_path=file_rel_path,
                            current_caller=current_caller,
                            current_class=qualified_name,
                            symbols=symbols,
                            imports=imports,
                            calls=calls,
                        )
                return

        # 3. Functions / Methods
        if node_type == "function_definition":
            func_name_node = node.child_by_field_name("name")
            if func_name_node:
                func_name = self._node_text(func_name_node, source_bytes)
                is_method = current_class is not None
                symbol_type = "method" if is_method else "function"
                qualified_name = f"{current_class}.{func_name}" if is_method else func_name
                parent_name = current_class
                line_start = node.start_point.row + 1
                line_end = node.end_point.row + 1
                visibility = self._determine_visibility(func_name)

                symbols.append(
                    ExtractedSymbol(
                        name=func_name,
                        qualified_name=qualified_name,
                        symbol_type=symbol_type,
                        parent_name=parent_name,
                        line_start=line_start,
                        line_end=line_end,
                        visibility=visibility,
                    )
                )

                # Process function body with caller context
                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._extract_entities(
                            node=child,
                            source_bytes=source_bytes,
                            file_rel_path=file_rel_path,
                            current_caller=qualified_name,
                            current_class=current_class,
                            symbols=symbols,
                            imports=imports,
                            calls=calls,
                        )
                return

        # 4. Calls
        if node_type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_name = self._node_text(func_node, source_bytes)
                line_num = node.start_point.row + 1
                calls.append(
                    ExtractedCall(
                        caller_name=current_caller,
                        callee_name=callee_name,
                        line_number=line_num,
                        source_file_rel_path=file_rel_path,
                    )
                )

        # Recurse for general children
        for child in node.children:
            self._extract_entities(
                node=child,
                source_bytes=source_bytes,
                file_rel_path=file_rel_path,
                current_caller=current_caller,
                current_class=current_class,
                symbols=symbols,
                imports=imports,
                calls=calls,
            )

    def _handle_import(
        self,
        node: Node,
        source_bytes: bytes,
        file_rel_path: str,
        imports: list[ExtractedImport],
    ) -> None:
        line_num = node.start_point.row + 1
        for child in node.children:
            if child.type == "dotted_name":
                mod_name = self._node_text(child, source_bytes)
                imports.append(
                    ExtractedImport(
                        source_file_rel_path=file_rel_path,
                        imported_module=mod_name,
                        imported_names=[],
                        alias=None,
                        import_type="module",
                        line_number=line_num,
                    )
                )
            elif child.type == "aliased_import":
                name_child = child.child_by_field_name("name")
                alias_child = child.child_by_field_name("alias")
                if name_child:
                    mod_name = self._node_text(name_child, source_bytes)
                    alias = self._node_text(alias_child, source_bytes) if alias_child else None
                    imports.append(
                        ExtractedImport(
                            source_file_rel_path=file_rel_path,
                            imported_module=mod_name,
                            imported_names=[],
                            alias=alias,
                            import_type="module",
                            line_number=line_num,
                        )
                    )

    def _handle_import_from(
        self,
        node: Node,
        source_bytes: bytes,
        file_rel_path: str,
        imports: list[ExtractedImport],
    ) -> None:
        line_num = node.start_point.row + 1
        module_name_node = node.child_by_field_name("module_name")
        module_name = self._node_text(module_name_node, source_bytes) if module_name_node else ""

        # Check for relative imports e.g. from . or from ..services
        if not module_name:
            for child in node.children:
                if child.type == "relative_import":
                    module_name = self._node_text(child, source_bytes)
                    break

        imported_names: list[str] = []
        for child in node.children:
            if child.type == "dotted_name" and child != module_name_node:
                imported_names.append(self._node_text(child, source_bytes))
            elif child.type == "aliased_import":
                name_child = child.child_by_field_name("name")
                if name_child:
                    imported_names.append(self._node_text(name_child, source_bytes))
            elif child.type == "wildcard_import":
                imported_names.append("*")

        imports.append(
            ExtractedImport(
                source_file_rel_path=file_rel_path,
                imported_module=module_name,
                imported_names=imported_names,
                alias=None,
                import_type="from",
                line_number=line_num,
            )
        )
