"""Data models for AST-based call graph analysis."""

from dataclasses import dataclass, field


@dataclass
class SymbolDef:
    """A function, class, or method definition in the project."""

    qualified_name: str   # "backend/routers/file.py::upload_file"
    name: str             # "upload_file"
    kind: str             # "function" | "async_function" | "class" | "method"
    file: str             # "backend/routers/file.py"
    line_start: int
    line_end: int
    decorators: list[str] = field(default_factory=list)
    docstring: str | None = None
    params: list[str] = field(default_factory=list)
    is_entry: bool = False


@dataclass
class CallEdge:
    """A call from one function to another."""

    caller: str            # qualified_name of caller
    callee_name: str       # raw function name being called
    callee_resolved: str | None = None  # resolved qualified_name (if in project)
    file: str = ""         # caller's file
    line: int = 0          # call site line number
    call_type: str = "direct"  # "direct" | "attribute"


@dataclass
class ModuleNode:
    """A module (file) in the module-level dependency graph."""

    path: str
    line_count: int = 0
    symbol_count: int = 0
    imports: list[str] = field(default_factory=list)


@dataclass
class CallGraph:
    """Complete call graph of a project."""

    definitions: dict[str, SymbolDef] = field(default_factory=dict)
    edges: list[CallEdge] = field(default_factory=list)
    modules: dict[str, ModuleNode] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to JSON-friendly dict for API response."""
        return {
            "modules": {
                path: {
                    "path": m.path,
                    "line_count": m.line_count,
                    "symbol_count": m.symbol_count,
                    "imports": m.imports,
                }
                for path, m in self.modules.items()
            },
            "definitions": {
                qname: {
                    "qualified_name": d.qualified_name,
                    "name": d.name,
                    "kind": d.kind,
                    "file": d.file,
                    "line_start": d.line_start,
                    "line_end": d.line_end,
                    "decorators": d.decorators,
                    "docstring": d.docstring,
                    "params": d.params,
                    "is_entry": d.is_entry,
                }
                for qname, d in self.definitions.items()
            },
            "edges": [
                {
                    "caller": e.caller,
                    "callee_name": e.callee_name,
                    "callee_resolved": e.callee_resolved,
                    "file": e.file,
                    "line": e.line,
                    "call_type": e.call_type,
                }
                for e in self.edges
            ],
        }
