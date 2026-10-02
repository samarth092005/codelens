from dataclasses import dataclass
from pathlib import PurePosixPath
import sys

from app.services.code_intelligence.parser.base import ExtractedCall, ExtractedImport


@dataclass
class ResolvedImport:
    source_file_id: int
    target_file_id: int | None
    imported_module: str
    import_type: str
    line_number: int
    resolution_status: str  # RESOLVED, UNRESOLVED, EXTERNAL


@dataclass
class ResolvedCall:
    caller_symbol_id: int | None
    callee_symbol_id: int | None
    callee_name: str
    source_file_id: int
    line_number: int
    resolution_status: str  # RESOLVED, UNRESOLVED, EXTERNAL


class DependencyResolver:
    """Deterministically resolves imports to target files and function calls to target symbols."""

    PYTHON_STDLIB = (
        (set(sys.stdlib_module_names) | set(sys.builtin_module_names))
        if hasattr(sys, "stdlib_module_names")
        else {
            "os", "sys", "math", "datetime", "pathlib", "typing", "json", "collections",
            "itertools", "functools", "re", "subprocess", "time", "logging", "abc",
            "dataclasses", "enum", "copy", "io", "shutil", "tempfile", "unittest",
        }
    )

    COMMON_THIRD_PARTY_PACKAGES = {
        "numpy", "pandas", "scipy", "requests", "urllib3", "fastapi", "pydantic",
        "sqlalchemy", "pytest", "alembic", "uvicorn", "starlette", "httpx",
        "django", "flask", "celery", "redis", "click", "yaml", "jinja2", "boto3",
        "botocore", "torch", "tensorflow", "sklearn", "matplotlib", "PIL", "bs4",
        "cryptography", "psycopg", "psycopg2", "dotenv", "setuptools", "wheel",
        "pip", "tree_sitter",
    }

    COMMON_BUILTINS = {
        # Python builtins
        "print", "len", "range", "str", "int", "float", "bool", "dict", "list", "set",
        "tuple", "isinstance", "issubclass", "getattr", "setattr", "hasattr", "open",
        "sum", "min", "max", "any", "all", "zip", "enumerate", "map", "filter",
        "super", "type", "id", "hash", "repr", "next", "iter", "round", "abs",
        # JS/TS builtins
        "console.log", "console.error", "console.warn", "console.info",
        "parseInt", "parseFloat", "isNaN", "isFinite", "alert", "setTimeout",
        "setInterval", "clearTimeout", "clearInterval", "fetch", "require",
    }

    @property
    def _installed_packages(self) -> set[str]:
        if not hasattr(self, "_cached_installed"):
            try:
                import importlib.metadata
                dists = importlib.metadata.packages_distributions()
                self._cached_installed = set(dists.keys())
            except Exception:
                self._cached_installed = set()
        return self._cached_installed

    def _is_external_python_module(
        self, root_mod: str, files_by_rel_path: dict[str, int]
    ) -> bool:
        """Establish whether a Python root module is outside the repository."""
        if not root_mod or root_mod.startswith("."):
            return False

        # If root_mod matches an internal repository directory or file name,
        # it is internal, so it cannot be established as external.
        repo_top_levels = {
            PurePosixPath(p).parts[0].replace(".py", "")
            for p in files_by_rel_path.keys()
            if PurePosixPath(p).parts
        }
        if root_mod in repo_top_levels:
            return False

        # 1. Standard library
        if root_mod in self.PYTHON_STDLIB or root_mod in sys.builtin_module_names:
            return True

        # 2. Recognized common third-party package
        if root_mod in self.COMMON_THIRD_PARTY_PACKAGES:
            return True

        # 3. Environment-installed third-party distribution
        if root_mod in self._installed_packages:
            return True

        return False

    def resolve_dependencies(
        self,
        files_by_rel_path: dict[str, int],  # rel_path -> file_id
        file_languages: dict[int, str],     # file_id -> language
        symbols_by_id: dict[int, dict],     # symbol_id -> {name, qualified_name, file_id, parent_id}
        symbols_by_file: dict[int, list[int]], # file_id -> [symbol_ids]
        raw_imports: list[tuple[int, ExtractedImport]], # (file_id, ExtractedImport)
        raw_calls: list[tuple[int, ExtractedCall]],     # (file_id, ExtractedCall)
    ) -> tuple[list[ResolvedImport], list[ResolvedCall]]:
        """Resolve all imports and calls for a repository version."""
        resolved_imports: list[ResolvedImport] = []
        resolved_calls: list[ResolvedCall] = []

        # 1. Resolve Imports
        # Map: file_id -> dict of {imported_name: target_file_id}
        file_symbol_imports: dict[int, dict[str, int]] = {f_id: {} for f_id in files_by_rel_path.values()}
        # Map: file_id -> dict of {imported_module_alias: target_file_id}
        file_module_imports: dict[int, dict[str, int]] = {f_id: {} for f_id in files_by_rel_path.values()}

        for file_id, imp in raw_imports:
            source_lang = file_languages.get(file_id, "unknown")
            source_rel_path = imp.source_file_rel_path

            target_file_id, status = self._resolve_import_target(
                source_rel_path=source_rel_path,
                imported_module=imp.imported_module,
                language=source_lang,
                files_by_rel_path=files_by_rel_path,
            )

            resolved_imports.append(
                ResolvedImport(
                    source_file_id=file_id,
                    target_file_id=target_file_id,
                    imported_module=imp.imported_module,
                    import_type=imp.import_type,
                    line_number=imp.line_number,
                    resolution_status=status,
                )
            )

            if target_file_id:
                # Record specific symbol imports
                for name in imp.imported_names:
                    if name != "*":
                        file_symbol_imports[file_id][name] = target_file_id

                # Record module import
                last_part = imp.imported_module.split(".")[-1].split("/")[-1]
                file_module_imports[file_id][last_part] = target_file_id
                if imp.alias:
                    file_module_imports[file_id][imp.alias] = target_file_id

        # 2. Index symbols for fast lookup
        # (file_id, qualified_name) -> symbol_id
        symbol_by_file_qname: dict[tuple[int, str], int] = {}
        # (file_id, name) -> list[symbol_id]
        symbol_by_file_name: dict[tuple[int, str], list[int]] = {}

        for sym_id, s_data in symbols_by_id.items():
            f_id = s_data["file_id"]
            qname = s_data["qualified_name"]
            name = s_data["name"]

            symbol_by_file_qname[(f_id, qname)] = sym_id
            symbol_by_file_name.setdefault((f_id, name), []).append(sym_id)

        # 3. Resolve Calls
        for file_id, call in raw_calls:
            caller_sym_id: int | None = None
            if call.caller_name:
                caller_sym_id = symbol_by_file_qname.get((file_id, call.caller_name))

            callee_sym_id, status = self._resolve_call_target(
                file_id=file_id,
                caller_sym_id=caller_sym_id,
                callee_name=call.callee_name,
                symbols_by_id=symbols_by_id,
                symbol_by_file_qname=symbol_by_file_qname,
                symbol_by_file_name=symbol_by_file_name,
                file_symbol_imports=file_symbol_imports.get(file_id, {}),
                file_module_imports=file_module_imports.get(file_id, {}),
            )

            resolved_calls.append(
                ResolvedCall(
                    caller_symbol_id=caller_sym_id,
                    callee_symbol_id=callee_sym_id,
                    callee_name=call.callee_name,
                    source_file_id=file_id,
                    line_number=call.line_number,
                    resolution_status=status,
                )
            )

        return resolved_imports, resolved_calls

    def _resolve_import_target(
        self,
        source_rel_path: str,
        imported_module: str,
        language: str,
        files_by_rel_path: dict[str, int],
    ) -> tuple[int | None, str]:
        """Resolve an imported module to a project target file ID."""
        if not imported_module:
            return None, "UNRESOLVED"

        if language == "python":
            source_dir = PurePosixPath(source_rel_path).parent

            # 1. Relative import (e.g. from .tax import calculate_tax or from ..services import helper)
            if imported_module.startswith("."):
                dots = len(imported_module) - len(imported_module.lstrip("."))
                rem = imported_module[dots:]
                cur_dir = source_dir
                for _ in range(dots - 1):
                    cur_dir = cur_dir.parent
                sub_path = rem.replace(".", "/")
                base = (cur_dir / sub_path).as_posix() if sub_path else cur_dir.as_posix()
                candidates = [f"{base}.py", f"{base}/__init__.py"]
                for cand in candidates:
                    norm_cand = PurePosixPath(cand).as_posix()
                    if norm_cand in files_by_rel_path:
                        return files_by_rel_path[norm_cand], "RESOLVED"
                # Relative import targets repository; if not found, it is UNRESOLVED
                return None, "UNRESOLVED"

            # 2. Non-relative import: check if it resolves to an internal repository file
            mod_path = imported_module.replace(".", "/")
            candidates = [
                f"{mod_path}.py",
                f"{mod_path}/__init__.py",
                (source_dir / f"{mod_path}.py").as_posix(),
                (source_dir / f"{mod_path}/__init__.py").as_posix(),
            ]
            for cand in candidates:
                norm_cand = PurePosixPath(cand).as_posix()
                if norm_cand in files_by_rel_path:
                    return files_by_rel_path[norm_cand], "RESOLVED"

            # 3. Target cannot be found inside repository:
            # Preserve EXTERNAL only when the resolver can establish that the dependency
            # is outside the repository; otherwise use UNRESOLVED.
            root_mod = imported_module.split(".")[0]
            if self._is_external_python_module(root_mod, files_by_rel_path):
                return None, "EXTERNAL"

            return None, "UNRESOLVED"

        elif language in ("javascript", "typescript"):
            # Check if external package e.g. 'react', 'lodash'
            if not imported_module.startswith(".") and not imported_module.startswith("/"):
                return None, "EXTERNAL"

            # Relative path resolution
            source_dir = PurePosixPath(source_rel_path).parent
            clean_mod = imported_module.lstrip("./") if imported_module.startswith("./") else imported_module
            target_base = (source_dir / clean_mod).as_posix()

            possible_extensions = [
                "", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
                "/index.ts", "/index.tsx", "/index.js", "/index.jsx",
            ]
            for ext in possible_extensions:
                cand = target_base + ext
                cand_norm = PurePosixPath(cand).as_posix()
                if cand_norm in files_by_rel_path:
                    return files_by_rel_path[cand_norm], "RESOLVED"

            return None, "UNRESOLVED"

        return None, "UNRESOLVED"

    def _resolve_call_target(
        self,
        file_id: int,
        caller_sym_id: int | None,
        callee_name: str,
        symbols_by_id: dict[int, dict],
        symbol_by_file_qname: dict[tuple[int, str], int],
        symbol_by_file_name: dict[tuple[int, str], list[int]],
        file_symbol_imports: dict[str, int],  # symbol_name -> target_file_id
        file_module_imports: dict[str, int],  # module_name -> target_file_id
    ) -> tuple[int | None, str]:
        """Resolve a function or method call to a target Symbol ID."""
        clean_callee = callee_name.strip()

        # Check known builtins
        if clean_callee in self.COMMON_BUILTINS or clean_callee.split(".")[-1] in self.COMMON_BUILTINS:
            return None, "EXTERNAL"

        # 1. Method call on self/this: e.g. self.calculate_tax or this.save
        if clean_callee.startswith("self.") or clean_callee.startswith("this."):
            method_name = clean_callee.split(".", 1)[1]
            if caller_sym_id and caller_sym_id in symbols_by_id:
                parent_id = symbols_by_id[caller_sym_id].get("parent_id")
                if parent_id and parent_id in symbols_by_id:
                    class_qname = symbols_by_id[parent_id]["qualified_name"]
                    target_qname = f"{class_qname}.{method_name}"
                    found_id = symbol_by_file_qname.get((file_id, target_qname))
                    if found_id:
                        return found_id, "RESOLVED"

        # 2. Member call through imported module: e.g. tax.calculate_tax()
        if "." in clean_callee:
            parts = clean_callee.split(".")
            mod_alias = parts[0]
            func_name = parts[1]
            if mod_alias in file_module_imports:
                target_file_id = file_module_imports[mod_alias]
                # Look for func_name in target file
                matches = symbol_by_file_name.get((target_file_id, func_name), [])
                if len(matches) == 1:
                    return matches[0], "RESOLVED"

        # 3. Simple identifier call: e.g. calculate_tax()
        simple_name = clean_callee.split(".")[-1]

        # 3a. Same file definition
        same_file_matches = symbol_by_file_name.get((file_id, simple_name), [])
        if len(same_file_matches) == 1:
            return same_file_matches[0], "RESOLVED"

        # 3b. Explicitly imported symbol: e.g. from app.tax import calculate_tax
        if simple_name in file_symbol_imports:
            target_file_id = file_symbol_imports[simple_name]
            target_matches = symbol_by_file_name.get((target_file_id, simple_name), [])
            if len(target_matches) == 1:
                return target_matches[0], "RESOLVED"

        # If it looks like an external or unresolvable call
        if "." in clean_callee:
            return None, "EXTERNAL"

        return None, "UNRESOLVED"


dependency_resolver = DependencyResolver()
