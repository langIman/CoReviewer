"""项目静态分析数据模型。"""

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
class ProjectAST:
    """项目静态分析模型：符号表 + 调用关系 + 模块依赖 + 入口函数。"""

    definitions: dict[str, SymbolDef] = field(default_factory=dict)
    edges: list[CallEdge] = field(default_factory=list)
    modules: dict[str, ModuleNode] = field(default_factory=dict)
    entry_points: list[str] = field(default_factory=list)
