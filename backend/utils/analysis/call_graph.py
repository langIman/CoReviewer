"""针对Python项目的基于AST的调用图提取。
通过以下步骤构建完整的调用图：
1. 使用ast.parse()解析所有.py文件 
2. 提取函数/类/方法定义（SymbolDef） 
3. 提取调用关系（CallEdge） 
4. 通过导入分析将调用目标名称解析为项目内部定义 
5. 根据导入构建模块级依赖图
"""

import ast
import logging
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)

from backend.config import is_ast_file, get_file_language
from backend.models.graph_models import CallEdge, ProjectAST, ModuleNode, SymbolDef
from backend.utils.analysis.import_analysis import (
    extract_imports,
    resolve_imports_to_project_files,
)
from backend.utils.analysis.ts_parser import (
    get_lang_config,
    ts_extract_definitions,
    ts_extract_calls,
    ts_resolve_call_edges,
    ts_extract_imports,
    ts_resolve_imports_to_project_files,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _decorator_to_str(dec: ast.expr) -> str:
    """Best-effort conversion of a decorator node to readable string."""
    if isinstance(dec, ast.Name):
        return f"@{dec.id}"
    if isinstance(dec, ast.Attribute):
        parts: list[str] = []
        node = dec
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value  # type: ignore[assignment]
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return "@" + ".".join(reversed(parts))
    if isinstance(dec, ast.Call):
        func_str = _decorator_to_str(dec.func).lstrip("@")
        # Include simple string/keyword args
        arg_parts: list[str] = []
        for a in dec.args:
            if isinstance(a, ast.Constant):
                arg_parts.append(repr(a.value))
        for kw in dec.keywords:
            if isinstance(kw.value, ast.Constant):
                arg_parts.append(f"{kw.arg}={kw.value.value!r}")
        return f"@{func_str}({', '.join(arg_parts)})"
    return "@<unknown>"


def _params_to_list(args: ast.arguments) -> list[str]:
    """Extract parameter names (with type annotations if available)."""
    params: list[str] = []
    for arg in args.args:
        name = arg.arg
        if arg.annotation:
            try:
                name += f": {ast.unparse(arg.annotation)}"
            except Exception:
                pass
        params.append(name)
    return params


def _get_docstring(node: ast.AST) -> str | None:
    """Extract docstring from a function or class body."""
    if not hasattr(node, "body") or not node.body:  # type: ignore[union-attr]
        return None
    first = node.body[0]  # type: ignore[union-attr]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        val = first.value.value
        if isinstance(val, str):
            doc = val.strip()
            # Truncate very long docstrings
            if len(doc) > 200:
                doc = doc[:200] + "..."
            return doc
    return None


def _extract_callee_name(call_node: ast.Call) -> tuple[str, str] | None:
    """Extract (name, call_type) from a Call node's func.

    Returns:
        (callee_name, "direct" | "attribute") or None
    """
    func = call_node.func
    if isinstance(func, ast.Name):
        return (func.id, "direct")
    if isinstance(func, ast.Attribute):
        return (func.attr, "attribute")
    return None


# ---------------------------------------------------------------------------
# File-level extraction
# ---------------------------------------------------------------------------

def _extract_definitions_from_file(
    file_path: str, source: str
) -> list[SymbolDef]:
    """Parse a single file and extract all function/class definitions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    defs: list[SymbolDef] = []

    for node in ast.iter_child_nodes(tree):
        # Top-level functions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
            qname = f"{file_path}::{node.name}"
            defs.append(SymbolDef(
                qualified_name=qname,
                name=node.name,
                kind=kind,
                file=file_path,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                decorators=[_decorator_to_str(d) for d in node.decorator_list],
                docstring=_get_docstring(node),
                params=_params_to_list(node.args),
            ))

        # Top-level classes + their methods
        elif isinstance(node, ast.ClassDef):
            class_qname = f"{file_path}::{node.name}"
            defs.append(SymbolDef(
                qualified_name=class_qname,
                name=node.name,
                kind="class",
                file=file_path,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                decorators=[_decorator_to_str(d) for d in node.decorator_list],
                docstring=_get_docstring(node),
            ))

            # Methods inside the class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_name = f"{node.name}.{item.name}"
                    method_qname = f"{file_path}::{method_name}"
                    kind = "async_function" if isinstance(item, ast.AsyncFunctionDef) else "method"
                    defs.append(SymbolDef(
                        qualified_name=method_qname,
                        name=method_name,
                        kind=kind,
                        file=file_path,
                        line_start=item.lineno,
                        line_end=getattr(item, "end_lineno", item.lineno),
                        decorators=[_decorator_to_str(d) for d in item.decorator_list],
                        docstring=_get_docstring(item),
                        params=_params_to_list(item.args),
                    ))

    return defs


def _extract_calls_from_function(
    func_node: ast.AST, caller_qname: str, file_path: str
) -> list[CallEdge]:
    """Extract all function calls within a function/method body."""
    edges: list[CallEdge] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            result = _extract_callee_name(node)
            if result:
                callee_name, call_type = result
                edges.append(CallEdge(
                    caller=caller_qname,
                    callee_name=callee_name,
                    file=file_path,
                    line=getattr(node, "lineno", 0),
                    call_type=call_type,
                ))
    return edges


# ---------------------------------------------------------------------------
# Import-based call resolution
# ---------------------------------------------------------------------------

def _build_import_name_map(
    file_path: str,
    source: str,
    project_files: dict[str, str],
    all_defs: dict[str, SymbolDef],
) -> dict[str, str]:
    """Build a mapping: imported_name -> qualified_name in project.

    E.g. if file does `from backend.services.llm.llm_service import call_qwen`,
    maps "call_qwen" -> "backend/services/llm.py::call_qwen".
    """
    name_map: dict[str, str] = {}

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return name_map

    current_dir = str(PurePosixPath(file_path).parent)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            parts = module.replace(".", "/")

            if level > 0:
                base = PurePosixPath(current_dir)
                for _ in range(level - 1):
                    base = base.parent
                candidates = [str(base / f"{parts}.py"), str(base / parts / "__init__.py")]
            else:
                candidates = [f"{parts}.py", f"{parts}/__init__.py"]

            # Find matching project file (exact match, then suffix match for
            # projects uploaded with a root folder prefix, e.g. "TestProject/")
            target_file = None
            for c in candidates:
                normalized = str(PurePosixPath(c))
                if normalized in project_files:
                    target_file = normalized
                    break
                for pf in project_files:
                    if pf.endswith("/" + normalized):
                        target_file = pf
                        break
                if target_file:
                    break

            if not target_file:
                logger.debug("Import not resolved in %s: 'from %s import ...' (external or missing)", file_path, module)
                continue

            # Map each imported name
            for alias in node.names:
                imported_name = alias.asname or alias.name
                # Try to find exact definition
                qname = f"{target_file}::{alias.name}"
                if qname in all_defs:
                    name_map[imported_name] = qname
                else:
                    # Could be a class method, try ClassName.method pattern
                    name_map.setdefault(imported_name, qname)

    # Also map same-file definitions (direct calls within same file)
    file_prefix = f"{file_path}::"
    for qname, defn in all_defs.items():
        if qname.startswith(file_prefix):
            short_name = defn.name
            if short_name not in name_map:
                name_map[short_name] = qname

    return name_map


def _resolve_call_edges(
    edges: list[CallEdge],
    file_path: str,
    source: str,
    project_files: dict[str, str],
    all_defs: dict[str, SymbolDef],
) -> None:
    """Resolve callee_name to callee_resolved (qualified_name) where possible."""
    name_map = _build_import_name_map(file_path, source, project_files, all_defs)

    for edge in edges:
        if edge.callee_resolved:
            continue
        resolved = name_map.get(edge.callee_name)
        if resolved and resolved in all_defs:
            edge.callee_resolved = resolved


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_call_graph(project_files: dict[str, str]) -> ProjectAST:
    """Build a complete call graph from project source files.

    Returns a ProjectAST with:
    - definitions: all function/class/method definitions
    - edges: all call relationships with resolved targets
    - modules: module-level dependency graph

    Python 走原有 ast 管道，其他语言走 tree-sitter 统一管道。
    """
    graph = ProjectAST()

    # Step 1: Extract all definitions from all files
    for file_path, source in project_files.items():
        lang = get_file_language(file_path)
        if lang == "python":
            file_defs = _extract_definitions_from_file(file_path, source)
        elif lang and (config := get_lang_config(lang)):
            file_defs = ts_extract_definitions(file_path, source, config)
        else:
            continue
        for d in file_defs:
            graph.definitions[d.qualified_name] = d

    # Step 2: Extract call edges from each function body
    for file_path, source in project_files.items():
        lang = get_file_language(file_path)
        if lang == "python":
            try:
                tree = ast.parse(source)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    qname = f"{file_path}::{node.name}"
                    for dname, ddef in graph.definitions.items():
                        if ddef.file == file_path and ddef.line_start == node.lineno:
                            qname = dname
                            break
                    calls = _extract_calls_from_function(node, qname, file_path)
                    graph.edges.extend(calls)
        elif lang and (config := get_lang_config(lang)):
            calls = ts_extract_calls(file_path, source, graph.definitions, config)
            graph.edges.extend(calls)

    # Step 3: Resolve call edges using import analysis
    for file_path, source in project_files.items():
        lang = get_file_language(file_path)
        file_edges = [e for e in graph.edges if e.file == file_path]
        if not file_edges:
            continue
        if lang == "python":
            _resolve_call_edges(file_edges, file_path, source, project_files, graph.definitions)
        elif lang and (config := get_lang_config(lang)):
            ts_resolve_call_edges(file_edges, file_path, source, project_files, graph.definitions, config)

    # Step 4: Build module-level dependency graph
    for file_path, source in project_files.items():
        lang = get_file_language(file_path)
        if lang == "python":
            imports = extract_imports(source)
            import_paths = resolve_imports_to_project_files(imports, file_path, project_files)
        elif lang and (config := get_lang_config(lang)):
            imports = ts_extract_imports(source, config)
            import_paths = ts_resolve_imports_to_project_files(imports, file_path, project_files, config)
        else:
            continue
        line_count = source.count("\n") + 1
        symbol_count = sum(
            1 for d in graph.definitions.values() if d.file == file_path
        )
        graph.modules[file_path] = ModuleNode(
            path=file_path,
            line_count=line_count,
            symbol_count=symbol_count,
            imports=import_paths,
        )

    return graph
