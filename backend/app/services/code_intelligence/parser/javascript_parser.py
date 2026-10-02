import tree_sitter_javascript as tsjavascript
from tree_sitter import Language, Node, Parser

from app.services.code_intelligence.parser.base import (
    CodeParser,
    ExtractedCall,
    ExtractedImport,
    ExtractedSymbol,
    ParseResult,
)


class JavaScriptParser(CodeParser):
    """Tree-sitter parser for JavaScript source files."""

    def __init__(self, language: Language | None = None) -> None:
        if language is None:
            self.language = Language(tsjavascript.language())
        else:
            self.language = language
        self.parser = Parser(self.language)

    def _node_text(self, node: Node, source_bytes: bytes) -> str:
        return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace").strip()

    def _strip_quotes(self, text: str) -> str:
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            return text[1:-1]
        if text.startswith("`") and text.endswith("`"):
            return text[1:-1]
        return text

    def parse(self, source_code: bytes, file_rel_path: str) -> ParseResult:
        try:
            tree = self.parser.parse(source_code)
            root = tree.root_node

            symbols: list[ExtractedSymbol] = []
            imports: list[ExtractedImport] = []
            calls: list[ExtractedCall] = []

            has_error = root.has_error

            self._extract_entities(
                node=root,
                source_bytes=source_code,
                file_rel_path=file_rel_path,
                current_caller=None,
                current_class=None,
                is_exported=False,
                symbols=symbols,
                imports=imports,
                calls=calls,
            )

            status = "PARSED"
            error_message = None
            if has_error and not symbols and not imports:
                status = "PARSE_ERROR"
                error_message = "File contains unrecoverable syntax errors"

            return ParseResult(
                file_rel_path=file_rel_path,
                language="javascript",
                status=status,
                error_message=error_message,
                symbols=symbols,
                imports=imports,
                calls=calls,
            )
        except Exception as e:
            return ParseResult(
                file_rel_path=file_rel_path,
                language="javascript",
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
        is_exported: bool,
        symbols: list[ExtractedSymbol],
        imports: list[ExtractedImport],
        calls: list[ExtractedCall],
    ) -> None:
        node_type = node.type

        # Export statements propagate exported visibility
        if node_type in ("export_statement", "export_default_statement"):
            for child in node.children:
                self._extract_entities(
                    node=child,
                    source_bytes=source_bytes,
                    file_rel_path=file_rel_path,
                    current_caller=current_caller,
                    current_class=current_class,
                    is_exported=True,
                    symbols=symbols,
                    imports=imports,
                    calls=calls,
                )
            return

        # 1. Imports
        if node_type == "import_statement":
            self._handle_import(node, source_bytes, file_rel_path, imports)
            return

        # 2. Classes
        if node_type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                class_name = self._node_text(name_node, source_bytes)
                qualified_name = f"{current_class}.{class_name}" if current_class else class_name
                symbols.append(
                    ExtractedSymbol(
                        name=class_name,
                        qualified_name=qualified_name,
                        symbol_type="class",
                        parent_name=current_class,
                        line_start=node.start_point.row + 1,
                        line_end=node.end_point.row + 1,
                        visibility="public" if is_exported else "private",
                    )
                )

                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._extract_entities(
                            node=child,
                            source_bytes=source_bytes,
                            file_rel_path=file_rel_path,
                            current_caller=current_caller,
                            current_class=qualified_name,
                            is_exported=False,
                            symbols=symbols,
                            imports=imports,
                            calls=calls,
                        )
                return

        # 3. Method definition in class
        if node_type == "method_definition":
            name_node = node.child_by_field_name("name")
            if name_node:
                method_name = self._node_text(name_node, source_bytes)
                qualified_name = f"{current_class}.{method_name}" if current_class else method_name
                
                # Check for visibility keyword
                visibility = "public"
                for child in node.children:
                    if child.type == "accessibility_modifier":
                        visibility = self._node_text(child, source_bytes)
                        break
                if method_name.startswith("#") or method_name.startswith("_"):
                    visibility = "private"

                symbols.append(
                    ExtractedSymbol(
                        name=method_name,
                        qualified_name=qualified_name,
                        symbol_type="method",
                        parent_name=current_class,
                        line_start=node.start_point.row + 1,
                        line_end=node.end_point.row + 1,
                        visibility=visibility,
                    )
                )

                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._extract_entities(
                            node=child,
                            source_bytes=source_bytes,
                            file_rel_path=file_rel_path,
                            current_caller=qualified_name,
                            current_class=current_class,
                            is_exported=False,
                            symbols=symbols,
                            imports=imports,
                            calls=calls,
                        )
                return

        # 4. Function declarations
        if node_type in ("function_declaration", "generator_function_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = self._node_text(name_node, source_bytes)
                qualified_name = f"{current_class}.{func_name}" if current_class else func_name
                symbols.append(
                    ExtractedSymbol(
                        name=func_name,
                        qualified_name=qualified_name,
                        symbol_type="function",
                        parent_name=current_class,
                        line_start=node.start_point.row + 1,
                        line_end=node.end_point.row + 1,
                        visibility="public" if is_exported else "private",
                    )
                )

                body_node = node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._extract_entities(
                            node=child,
                            source_bytes=source_bytes,
                            file_rel_path=file_rel_path,
                            current_caller=qualified_name,
                            current_class=current_class,
                            is_exported=False,
                            symbols=symbols,
                            imports=imports,
                            calls=calls,
                        )
                return

        # 5. Arrow functions / function expressions assigned to variables
        if node_type == "variable_declarator":
            name_node = node.child_by_field_name("name")
            value_node = node.child_by_field_name("value")
            if name_node and value_node and value_node.type in ("arrow_function", "function_expression"):
                var_name = self._node_text(name_node, source_bytes)
                qualified_name = f"{current_class}.{var_name}" if current_class else var_name
                symbols.append(
                    ExtractedSymbol(
                        name=var_name,
                        qualified_name=qualified_name,
                        symbol_type="function",
                        parent_name=current_class,
                        line_start=node.start_point.row + 1,
                        line_end=node.end_point.row + 1,
                        visibility="public" if is_exported else "private",
                    )
                )
                body_node = value_node.child_by_field_name("body")
                if body_node:
                    for child in body_node.children:
                        self._extract_entities(
                            node=child,
                            source_bytes=source_bytes,
                            file_rel_path=file_rel_path,
                            current_caller=qualified_name,
                            current_class=current_class,
                            is_exported=False,
                            symbols=symbols,
                            imports=imports,
                            calls=calls,
                        )
                return

        # 6. Call expressions (including require)
        if node_type == "call_expression":
            callee_node = node.child_by_field_name("function")
            if callee_node:
                callee_name = self._node_text(callee_node, source_bytes)
                # Check if it's require('./...')
                if callee_name == "require":
                    args_node = node.child_by_field_name("arguments")
                    if args_node and args_node.named_children:
                        mod_arg = args_node.named_children[0]
                        mod_path = self._strip_quotes(self._node_text(mod_arg, source_bytes))
                        imports.append(
                            ExtractedImport(
                                source_file_rel_path=file_rel_path,
                                imported_module=mod_path,
                                imported_names=[],
                                alias=None,
                                import_type="require",
                                line_number=node.start_point.row + 1,
                            )
                        )
                    return
                else:
                    # Regular function call
                    calls.append(
                        ExtractedCall(
                            caller_name=current_caller,
                            callee_name=callee_name,
                            line_number=node.start_point.row + 1,
                            source_file_rel_path=file_rel_path,
                        )
                    )

        # Recurse through children
        for child in node.children:
            self._extract_entities(
                node=child,
                source_bytes=source_bytes,
                file_rel_path=file_rel_path,
                current_caller=current_caller,
                current_class=current_class,
                is_exported=is_exported,
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
        source_node = node.child_by_field_name("source")
        if not source_node:
            return

        module_path = self._strip_quotes(self._node_text(source_node, source_bytes))
        line_num = node.start_point.row + 1
        imported_names: list[str] = []

        # Find import clause / specifiers
        for child in node.children:
            if child.type == "import_clause":
                for sub in child.children:
                    if sub.type == "identifier":
                        # default import: import React from 'react'
                        imported_names.append(self._node_text(sub, source_bytes))
                    elif sub.type == "named_imports":
                        for spec in sub.children:
                            if spec.type == "import_specifier":
                                name_sub = spec.child_by_field_name("name")
                                if name_sub:
                                    imported_names.append(self._node_text(name_sub, source_bytes))
                    elif sub.type == "namespace_import":
                        imported_names.append("*")

        imports.append(
            ExtractedImport(
                source_file_rel_path=file_rel_path,
                imported_module=module_path,
                imported_names=imported_names,
                alias=None,
                import_type="import",
                line_number=line_num,
            )
        )
