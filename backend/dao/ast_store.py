"""ProjectAST 持久化存储。

将 ProjectAST 的三个组成部分（symbols, call_edges, modules）
存入 SQLite，支持按 project_name 存取和清除。
"""

import json

from backend.dao.database import get_connection
from backend.models.graph_models import ProjectAST, SymbolDef, CallEdge, ModuleNode


def save_project_ast(project_name: str, ast_model: ProjectAST) -> None:
    """清旧数据 + 批量写入 symbols/call_edges/modules。"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM symbols WHERE project_name = ?", (project_name,))
        conn.execute("DELETE FROM call_edges WHERE project_name = ?", (project_name,))
        conn.execute("DELETE FROM modules WHERE project_name = ?", (project_name,))

        # symbols
        for defn in ast_model.definitions.values():
            conn.execute(
                "INSERT INTO symbols (qualified_name, name, kind, file, line_start, line_end, "
                "decorators, docstring, params, is_entry, project_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    defn.qualified_name,
                    defn.name,
                    defn.kind,
                    defn.file,
                    defn.line_start,
                    defn.line_end,
                    json.dumps(defn.decorators, ensure_ascii=False),
                    defn.docstring,
                    json.dumps(defn.params, ensure_ascii=False),
                    1 if defn.is_entry else 0,
                    project_name,
                ),
            )

        # call_edges
        for edge in ast_model.edges:
            conn.execute(
                "INSERT INTO call_edges (caller, callee_name, callee_resolved, file, line, "
                "call_type, resolution_method, project_name) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    edge.caller,
                    edge.callee_name,
                    edge.callee_resolved,
                    edge.file,
                    edge.line,
                    edge.call_type,
                    edge.resolution_method,
                    project_name,
                ),
            )

        # modules
        for mod in ast_model.modules.values():
            conn.execute(
                "INSERT INTO modules (path, line_count, symbol_count, imports, project_name) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    mod.path,
                    mod.line_count,
                    mod.symbol_count,
                    json.dumps(mod.imports, ensure_ascii=False),
                    project_name,
                ),
            )

        conn.commit()
    finally:
        conn.close()


def load_project_ast(project_name: str) -> ProjectAST | None:
    """从 SQLite 重建 ProjectAST，无数据则返回 None。"""
    conn = get_connection()
    try:
        # symbols
        rows = conn.execute(
            "SELECT qualified_name, name, kind, file, line_start, line_end, "
            "decorators, docstring, params, is_entry "
            "FROM symbols WHERE project_name = ?",
            (project_name,),
        ).fetchall()

        if not rows:
            return None

        definitions: dict[str, SymbolDef] = {}
        for r in rows:
            defn = SymbolDef(
                qualified_name=r[0],
                name=r[1],
                kind=r[2],
                file=r[3],
                line_start=r[4],
                line_end=r[5],
                decorators=json.loads(r[6]) if r[6] else [],
                docstring=r[7],
                params=json.loads(r[8]) if r[8] else [],
                is_entry=bool(r[9]),
            )
            definitions[defn.qualified_name] = defn

        # call_edges
        rows = conn.execute(
            "SELECT caller, callee_name, callee_resolved, file, line, call_type, "
            "resolution_method FROM call_edges WHERE project_name = ?",
            (project_name,),
        ).fetchall()

        edges = [
            CallEdge(
                caller=r[0],
                callee_name=r[1],
                callee_resolved=r[2],
                file=r[3],
                line=r[4],
                call_type=r[5],
                resolution_method=r[6],
            )
            for r in rows
        ]

        # modules
        rows = conn.execute(
            "SELECT path, line_count, symbol_count, imports "
            "FROM modules WHERE project_name = ?",
            (project_name,),
        ).fetchall()

        modules = {
            r[0]: ModuleNode(
                path=r[0],
                line_count=r[1],
                symbol_count=r[2],
                imports=json.loads(r[3]) if r[3] else [],
            )
            for r in rows
        }

        # entry_points
        entry_points = [qn for qn, d in definitions.items() if d.is_entry]

        return ProjectAST(
            definitions=definitions,
            edges=edges,
            modules=modules,
            entry_points=entry_points,
        )
    finally:
        conn.close()


def clear_project_ast(project_name: str) -> None:
    """删除指定项目的所有 AST 数据。"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM symbols WHERE project_name = ?", (project_name,))
        conn.execute("DELETE FROM call_edges WHERE project_name = ?", (project_name,))
        conn.execute("DELETE FROM modules WHERE project_name = ?", (project_name,))
        conn.commit()
    finally:
        conn.close()


def has_project_ast(project_name: str) -> bool:
    """检查指定项目是否有 AST 数据。"""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM symbols WHERE project_name = ? LIMIT 1",
            (project_name,),
        ).fetchone()
        return row is not None
    finally:
        conn.close()
