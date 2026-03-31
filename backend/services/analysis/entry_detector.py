"""检测Python项目调用图中的入口点。
检测规则（按优先级排序）：
1. 带有路由修饰符（如@app.get、@router.post等）的函数 
2. 带有CLI修饰符（如@click.command、@app.command等）的函数 
3. 文件中带有`if __name__ == "__main__":`保护语句的函数 
4. 未被任何其他函数调用的顶级函数（孤立函数启发式）
"""

import ast
from backend.models.graph_models import CallGraph


# ---------------------------------------------------------------------------
# Decorator matching helpers
# ---------------------------------------------------------------------------

def _is_route_decorator(dec_str: str) -> bool:
    """Check if a decorator string looks like a web framework route."""
    dec_lower = dec_str.lower()
    route_patterns = [
        "@app.get", "@app.post", "@app.put", "@app.delete", "@app.patch",
        "@router.get", "@router.post", "@router.put", "@router.delete", "@router.patch",
        "@app.route", "@blueprint.route",
    ]
    return any(dec_lower.startswith(p) for p in route_patterns)


def _is_cli_decorator(dec_str: str) -> bool:
    """Check if a decorator string looks like a CLI command."""
    dec_lower = dec_str.lower()
    cli_patterns = [
        "@click.command", "@click.group", "@app.command",
        "@cli.command", "@cli.group",
    ]
    return any(dec_lower.startswith(p) for p in cli_patterns)


def _has_main_guard(source: str) -> bool:
    """Check if file has `if __name__ == '__main__':` block."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        # Check for: __name__ == "__main__" or "__main__" == __name__
        cmp = node.test
        if isinstance(cmp, ast.Compare) and len(cmp.ops) == 1:
            if isinstance(cmp.ops[0], ast.Eq):
                left = cmp.left
                right = cmp.comparators[0] if cmp.comparators else None
                if _is_name_main_pair(left, right):
                    return True
    return False


def _is_name_main_pair(left: ast.expr, right: ast.expr | None) -> bool:
    """Check if left/right form __name__ == "__main__" in either order."""
    if right is None:
        return False

    def is_name_var(n: ast.expr) -> bool:
        return isinstance(n, ast.Name) and n.id == "__name__"

    def is_main_str(n: ast.expr) -> bool:
        return isinstance(n, ast.Constant) and n.value == "__main__"

    return (is_name_var(left) and is_main_str(right)) or \
           (is_main_str(left) and is_name_var(right))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_entry_points(
    graph: CallGraph,
    project_files: dict[str, str],
) -> list[str]:
    """Detect entry points and mark them in the call graph.

    Returns list of qualified_names that are entry points.
    """
    entry_qnames: set[str] = set()

    # Collect all callees (functions that are called by someone)
    called_qnames: set[str] = set()
    for edge in graph.edges:
        if edge.callee_resolved:
            called_qnames.add(edge.callee_resolved)

    # Rule 1 & 2: Check decorators
    for qname, defn in graph.definitions.items():
        for dec in defn.decorators:
            if _is_route_decorator(dec):
                entry_qnames.add(qname)
                break
            if _is_cli_decorator(dec):
                entry_qnames.add(qname)
                break

    # Rule 3: Functions in files with __main__ guard
    main_guard_files: set[str] = set()
    for file_path, source in project_files.items():
        if file_path.endswith(".py") and _has_main_guard(source):
            main_guard_files.add(file_path)

    for qname, defn in graph.definitions.items():
        if defn.file in main_guard_files and defn.kind in ("function", "async_function"):
            # Only mark top-level functions (not methods)
            if "." not in defn.name:
                entry_qnames.add(qname)

    # Rule 4: Orphan functions (not called by anyone, top-level, non-private)
    for qname, defn in graph.definitions.items():
        if qname in entry_qnames:
            continue
        if defn.kind in ("method",):
            continue
        if defn.name.startswith("_") and not defn.name.startswith("__"):
            continue
        if qname not in called_qnames:
            entry_qnames.add(qname)

    # Mark is_entry on definitions
    for qname in entry_qnames:
        if qname in graph.definitions:
            graph.definitions[qname].is_entry = True

    graph.entry_points = sorted(entry_qnames)
    return graph.entry_points
