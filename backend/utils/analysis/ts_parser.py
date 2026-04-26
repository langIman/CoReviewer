"""统一多语言 AST 解析引擎。

基于 tree-sitter，通过 LangConfig 配置驱动，支持多种编程语言。
产出与 Python ast 管道完全一致的 SymbolDef / CallEdge / ModuleNode，
确保下游服务（流程图、摘要、Agent tools）零改动。

添加新语言步骤：
1. pip install tree-sitter-{lang}
2. 在 config.py 的 _LANG_MAP / AST_EXTENSIONS 中注册扩展名
3. 在本文件底部创建 LangConfig 并调用 register_language()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Callable

from tree_sitter import Language, Node, Parser

from backend.config import SUMMARY_FUNC_LINES, SUMMARY_TRUNCATION_PERCENT
from backend.models.graph_models import CallEdge, ModuleNode, SymbolDef

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# LangConfig: 语言配置
# ---------------------------------------------------------------------------

@dataclass
class LangConfig:
    """一种语言的 tree-sitter 解析配置。"""

    language: Language

    # 节点类型映射
    function_types: list[str]         # 函数/方法定义节点（Java 为 method_declaration/constructor_declaration）
    class_types: list[str]            # 类/结构体/枚举/trait/interface 等节点
    impl_type: str | None             # impl 块节点（如 Rust 的 impl_item）
    call_types: list[str]             # 调用表达式节点
    macro_call_type: str | None       # 宏调用节点（Rust 的 macro_invocation）
    import_types: list[str]           # 导入声明节点

    # 字段名
    name_field: str = "name"
    params_field: str = "parameters"
    body_field: str = "body"

    # 语言特有
    attr_type: str | None = None      # 属性/装饰器节点类型
    doc_comment_prefix: str | None = None  # 文档注释前缀（如 "///"）
    skip_macros: set[str] = field(default_factory=set)

    # 类内定义方法的语言（Java / TS / Kotlin）
    class_has_methods: bool = False                           # True 时遍历 class body 抽方法
    method_container_types: list[str] = field(default_factory=list)  # 类体中的中间容器（如 Java enum_body_declarations）

    # 语言特定回调
    format_signature: Callable[[SymbolDef], str] | None = None
    extract_imports: Callable | None = None
    resolve_imports: Callable | None = None
    detect_lang_entries: Callable | None = None
    extract_callee: Callable | None = None                    # 覆盖默认调用节点抽取（Java method_invocation 等）
    extract_decorators: Callable | None = None                # 覆盖默认装饰器收集（Java 注解在 modifiers 子节点里）


# ---------------------------------------------------------------------------
# 语言注册表
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, LangConfig] = {}


def register_language(name: str, config: LangConfig) -> None:
    _REGISTRY[name] = config


def get_lang_config(name: str) -> LangConfig | None:
    return _REGISTRY.get(name)


# ---------------------------------------------------------------------------
# 通用辅助函数
# ---------------------------------------------------------------------------

def _node_text(node: Node) -> str:
    """提取节点文本。"""
    return node.text.decode("utf-8", errors="replace")


def _find_child_by_type(node: Node, type_name: str) -> Node | None:
    """在直接子节点中查找指定类型的第一个节点。"""
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _collect_preceding_attrs(node: Node, attr_type: str) -> list[str]:
    """收集目标节点之前紧邻的属性/装饰器节点。"""
    parent = node.parent
    if not parent:
        return []
    attrs: list[str] = []
    for sibling in parent.children:
        if sibling.id == node.id:
            break
        if sibling.type == attr_type:
            attrs.append(_node_text(sibling).strip())
        elif sibling.is_named and sibling.type != attr_type:
            attrs.clear()  # 中间有其他节点，重置
    return attrs


def _collect_doc_comments(node: Node, prefix: str, attr_type: str | None = None) -> str | None:
    """收集目标节点之前紧邻的文档注释。

    属性节点（如 #[...]）不会打断注释收集链。
    """
    parent = node.parent
    if not parent:
        return None
    comments: list[str] = []
    for sibling in parent.children:
        if sibling.id == node.id:
            break
        if sibling.type == "line_comment":
            text = _node_text(sibling).strip()
            if text.startswith(prefix):
                stripped = text[len(prefix):].strip()
                comments.append(stripped)
            else:
                comments.clear()
        elif attr_type and sibling.type == attr_type:
            pass  # 属性不打断注释链
        elif sibling.is_named:
            comments.clear()
    if not comments:
        return None
    doc = "\n".join(comments).strip()
    return doc[:200] + "..." if len(doc) > 200 else doc


def _extract_params(node: Node, params_field: str) -> list[str]:
    """通用参数提取：遍历参数列表的命名子节点。"""
    params_node = node.child_by_field_name(params_field)
    if not params_node:
        return []
    params: list[str] = []
    for child in params_node.named_children:
        # 通用处理：取整个参数文本，去除换行
        text = _node_text(child).strip().replace("\n", " ")
        if text:
            params.append(text)
    return params


def _is_async_function(node: Node) -> bool:
    """检查函数是否为 async（通过查找 async 关键字子节点）。"""
    for child in node.children:
        if not child.is_named and _node_text(child) == "async":
            return True
    return False


# ---------------------------------------------------------------------------
# 统一 Walker：定义提取
# ---------------------------------------------------------------------------

def ts_extract_definitions(
    file_path: str, source: str, config: LangConfig
) -> list[SymbolDef]:
    """从源文件提取所有定义（函数/类/方法），产出 SymbolDef 列表。"""
    parser = Parser(config.language)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    defs: list[SymbolDef] = []

    for child in root.children:
        if not child.is_named:
            continue

        # 顶层函数
        if child.type in config.function_types:
            defn = _build_symbol_def(child, file_path, config, parent_name=None)
            if defn:
                defs.append(defn)

        # 类/结构体/枚举/trait/interface
        elif child.type in config.class_types:
            class_defn = _build_class_def(child, file_path, config)
            if class_defn:
                defs.append(class_defn)
                # Java 类系语言：类体内直接包含方法，需要递归抽取
                if config.class_has_methods:
                    defs.extend(
                        _extract_nested_methods(child, file_path, config, class_defn.name)
                    )

        # impl 块（如 Rust）
        elif config.impl_type and child.type == config.impl_type:
            defs.extend(_build_impl_defs(child, file_path, config))

    return defs


def _extract_nested_methods(
    class_node: Node, file_path: str, config: LangConfig, class_name: str
) -> list[SymbolDef]:
    """从类/接口/枚举体中抽取方法定义（Java 等类系语言）。

    处理 Java enum 的一层间接容器 `enum_body_declarations`。
    """
    body = class_node.child_by_field_name(config.body_field)
    if not body:
        return []
    defs: list[SymbolDef] = []
    for item in body.children:
        if not item.is_named:
            continue
        if item.type in config.function_types:
            defn = _build_symbol_def(item, file_path, config, parent_name=class_name)
            if defn:
                defs.append(defn)
        elif item.type in config.method_container_types:
            for sub in item.children:
                if sub.is_named and sub.type in config.function_types:
                    defn = _build_symbol_def(sub, file_path, config, parent_name=class_name)
                    if defn:
                        defs.append(defn)
    return defs


def _build_symbol_def(
    node: Node, file_path: str, config: LangConfig, parent_name: str | None
) -> SymbolDef | None:
    """从函数节点构建 SymbolDef。"""
    name_node = node.child_by_field_name(config.name_field)
    if not name_node:
        return None

    raw_name = _node_text(name_node)
    is_async = _is_async_function(node)

    if parent_name:
        full_name = f"{parent_name}.{raw_name}"
        kind = "method" if node.type != "constructor_declaration" else "constructor"
    else:
        full_name = raw_name
        kind = "async_function" if is_async else "function"

    decorators = _collect_decorators(node, config)

    docstring = None
    if config.doc_comment_prefix:
        docstring = _collect_doc_comments(node, config.doc_comment_prefix, config.attr_type)

    params = _extract_params(node, config.params_field)

    return SymbolDef(
        qualified_name=f"{file_path}::{full_name}",
        name=full_name,
        kind=kind,
        file=file_path,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        decorators=decorators,
        docstring=docstring,
        params=params,
    )


def _collect_decorators(node: Node, config: LangConfig) -> list[str]:
    """统一装饰器/注解收集。优先走语言特定回调，否则走前序兄弟节点收集。"""
    if config.extract_decorators:
        return config.extract_decorators(node, config)
    if config.attr_type:
        return _collect_preceding_attrs(node, config.attr_type)
    return []


def _build_class_def(
    node: Node, file_path: str, config: LangConfig
) -> SymbolDef | None:
    """从类/结构体/枚举/trait 节点构建 SymbolDef。"""
    name_node = node.child_by_field_name(config.name_field)
    if not name_node:
        return None

    name = _node_text(name_node)

    decorators = _collect_decorators(node, config)

    docstring = None
    if config.doc_comment_prefix:
        docstring = _collect_doc_comments(node, config.doc_comment_prefix, config.attr_type)

    return SymbolDef(
        qualified_name=f"{file_path}::{name}",
        name=name,
        kind="class",
        file=file_path,
        line_start=node.start_point[0] + 1,
        line_end=node.end_point[0] + 1,
        decorators=decorators,
        docstring=docstring,
    )


def _build_impl_defs(
    node: Node, file_path: str, config: LangConfig
) -> list[SymbolDef]:
    """从 impl 块提取方法定义。"""
    type_node = node.child_by_field_name("type")
    if not type_node:
        return []

    type_name = _node_text(type_node)
    # 去除泛型参数：AuthService<T> → AuthService
    if "<" in type_name:
        type_name = type_name[:type_name.index("<")]

    body = node.child_by_field_name(config.body_field)
    if not body:
        return []

    defs: list[SymbolDef] = []
    for item in body.children:
        if item.is_named and item.type in config.function_types:
            defn = _build_symbol_def(item, file_path, config, parent_name=type_name)
            if defn:
                defs.append(defn)
    return defs


# ---------------------------------------------------------------------------
# 统一 Walker：调用提取
# ---------------------------------------------------------------------------

def ts_extract_calls(
    file_path: str, source: str, definitions: dict[str, SymbolDef], config: LangConfig
) -> list[CallEdge]:
    """从源文件中每个已知函数/方法体内提取调用边。"""
    parser = Parser(config.language)
    tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node
    edges: list[CallEdge] = []

    def process_function_node(func_node: Node, qname: str) -> None:
        body = func_node.child_by_field_name(config.body_field)
        if not body:
            return
        _walk_for_calls(body, qname, file_path, config, edges)

    # 遍历所有顶层函数、impl 块和类内方法
    for child in root.children:
        if not child.is_named:
            continue

        if child.type in config.function_types:
            name_node = child.child_by_field_name(config.name_field)
            if name_node:
                qname = _match_definition_qname(
                    file_path, _node_text(name_node), child.start_point[0] + 1, definitions
                )
                process_function_node(child, qname)

        elif config.impl_type and child.type == config.impl_type:
            type_node = child.child_by_field_name("type")
            type_name = _node_text(type_node) if type_node else ""
            if "<" in type_name:
                type_name = type_name[:type_name.index("<")]

            body = child.child_by_field_name(config.body_field)
            if body:
                for item in body.children:
                    if item.is_named and item.type in config.function_types:
                        name_node = item.child_by_field_name(config.name_field)
                        if name_node:
                            method_name = f"{type_name}.{_node_text(name_node)}"
                            qname = _match_definition_qname(
                                file_path, method_name, item.start_point[0] + 1, definitions
                            )
                            process_function_node(item, qname)

        elif config.class_has_methods and child.type in config.class_types:
            class_name_node = child.child_by_field_name(config.name_field)
            if not class_name_node:
                continue
            class_name = _node_text(class_name_node)
            body = child.child_by_field_name(config.body_field)
            if not body:
                continue

            def _walk_methods(body_node: Node) -> None:
                for item in body_node.children:
                    if not item.is_named:
                        continue
                    if item.type in config.function_types:
                        name_node = item.child_by_field_name(config.name_field)
                        if name_node:
                            method_name = f"{class_name}.{_node_text(name_node)}"
                            qname = _match_definition_qname(
                                file_path, method_name, item.start_point[0] + 1, definitions
                            )
                            process_function_node(item, qname)
                    elif item.type in config.method_container_types:
                        _walk_methods(item)

            _walk_methods(body)

    return edges


def _match_definition_qname(
    file_path: str, name: str, line: int, definitions: dict[str, SymbolDef]
) -> str:
    """根据文件路径和行号匹配已知定义的 qualified_name。"""
    candidate = f"{file_path}::{name}"
    if candidate in definitions:
        return candidate
    # fallback: 按行号匹配
    for qname, defn in definitions.items():
        if defn.file == file_path and defn.line_start == line:
            return qname
    return candidate


def _walk_for_calls(
    node: Node, caller_qname: str, file_path: str,
    config: LangConfig, edges: list[CallEdge],
) -> None:
    """递归遍历函数体，收集调用边。"""
    # 函数调用
    if node.type in config.call_types:
        # 语言特定的调用节点（如 Java method_invocation）走回调
        callee_info = None
        if config.extract_callee:
            callee_info = config.extract_callee(node)
        else:
            func_node = node.child_by_field_name("function")
            if func_node:
                callee_info = _extract_callee_info(func_node)
        if callee_info:
            callee_name, call_type = callee_info
            if callee_name:
                edges.append(CallEdge(
                    caller=caller_qname,
                    callee_name=callee_name,
                    file=file_path,
                    line=node.start_point[0] + 1,
                    call_type=call_type,
                ))

    # 宏调用（如 Rust 的 macro_invocation）
    if config.macro_call_type and node.type == config.macro_call_type:
        macro_node = node.child_by_field_name("macro")
        if not macro_node:
            # fallback: 找第一个 identifier 子节点
            for c in node.children:
                if c.type == "identifier":
                    macro_node = c
                    break
        if macro_node:
            macro_name = _node_text(macro_node)
            if macro_name not in config.skip_macros:
                edges.append(CallEdge(
                    caller=caller_qname,
                    callee_name=macro_name,
                    file=file_path,
                    line=node.start_point[0] + 1,
                    call_type="direct",
                ))

    for child in node.children:
        _walk_for_calls(child, caller_qname, file_path, config, edges)


def _extract_callee_info(func_node: Node) -> tuple[str, str]:
    """从调用表达式的 function 子节点提取被调函数名和调用类型。"""
    if func_node.type == "identifier":
        return _node_text(func_node), "direct"
    if func_node.type == "field_expression":
        field = func_node.child_by_field_name("field")
        if field:
            return _node_text(field), "attribute"
    if func_node.type == "scoped_identifier":
        # Path::to::func → 取最后一段
        name_node = func_node.child_by_field_name("name")
        if name_node:
            return _node_text(name_node), "direct"
    # fallback: 取整个文本
    text = _node_text(func_node).split("::")[-1].split(".")[-1]
    return text, "direct"


# ---------------------------------------------------------------------------
# 统一 Walker：导入提取与解析
# ---------------------------------------------------------------------------

def ts_build_import_name_map(
    file_path: str, source: str,
    project_files: dict[str, str],
    all_defs: dict[str, SymbolDef],
    config: LangConfig,
) -> dict[str, str]:
    """构建 imported_name → qualified_name 映射。"""
    name_map: dict[str, str] = {}

    # 调用语言特定的导入解析
    if config.extract_imports and config.resolve_imports:
        parser = Parser(config.language)
        tree = parser.parse(source.encode("utf-8"))
        raw_imports = config.extract_imports(tree.root_node)
        resolved = config.resolve_imports(raw_imports, file_path, project_files)
        # resolved: list[(imported_name, target_file, symbol_name)]
        for imported_name, target_file, symbol_name in resolved:
            qname = f"{target_file}::{symbol_name}"
            if qname in all_defs:
                name_map[imported_name] = qname
            else:
                name_map.setdefault(imported_name, qname)

    # 同文件定义映射（所有语言通用）
    file_prefix = f"{file_path}::"
    for qname, defn in all_defs.items():
        if qname.startswith(file_prefix):
            short_name = defn.name
            if short_name not in name_map:
                name_map[short_name] = qname

    return name_map


def ts_resolve_call_edges(
    edges: list[CallEdge],
    file_path: str, source: str,
    project_files: dict[str, str],
    all_defs: dict[str, SymbolDef],
    config: LangConfig,
    language: str | None = None,
    simple_table: dict[str, list[str]] | None = None,
) -> None:
    """解析调用边中的 callee_name → callee_resolved。

    解析顺序：
    1. import 名查表（高置信，resolution_method='import'）
    2. naive 简单名匹配兜底（resolution_method='naive'，仅当 simple_table 提供）
    """
    name_map = ts_build_import_name_map(
        file_path, source, project_files, all_defs, config
    )
    # 延迟 import 避免循环依赖（call_graph 已经 import 了 ts_parser）
    from backend.utils.analysis.call_graph import naive_name_resolve

    for edge in edges:
        if edge.callee_resolved:
            continue
        # 1. 主路径
        resolved = name_map.get(edge.callee_name)
        if resolved and resolved in all_defs:
            edge.callee_resolved = resolved
            edge.resolution_method = "import"
            continue
        # 2. naive fallback
        if simple_table is not None:
            resolved = naive_name_resolve(edge.callee_name, language, simple_table)
            if resolved:
                edge.callee_resolved = resolved
                edge.resolution_method = "naive"


def ts_extract_imports(
    source: str, config: LangConfig
) -> list[tuple[str, str]]:
    """提取导入信息，返回 (module_path, kind) 列表。供模块依赖图使用。"""
    if not config.extract_imports:
        return []
    parser = Parser(config.language)
    tree = parser.parse(source.encode("utf-8"))
    return config.extract_imports(tree.root_node)


def ts_resolve_imports_to_project_files(
    imports: list[tuple[str, str]],
    file_path: str,
    project_files: dict[str, str],
    config: LangConfig,
) -> list[str]:
    """将导入列表映射到项目中实际存在的文件路径。"""
    if not config.resolve_imports:
        return []
    resolved = config.resolve_imports(imports, file_path, project_files)
    # resolved: list[(imported_name, target_file, symbol_name)]
    seen: set[str] = set()
    result: list[str] = []
    for _, target_file, _ in resolved:
        if target_file and target_file not in seen and target_file in project_files:
            seen.add(target_file)
            result.append(target_file)
    return result


# ---------------------------------------------------------------------------
# 统一 Walker：骨架提取（摘要服务用）
# ---------------------------------------------------------------------------

def ts_extract_skeleton(content: str, config: LangConfig) -> str:
    """提取文件骨架：每个函数/类/impl 的前 N 行。"""
    lines = content.split("\n")
    total_lines = len(lines)
    max_extract_lines = max(int(total_lines * SUMMARY_TRUNCATION_PERCENT), 10)

    parser = Parser(config.language)
    tree = parser.parse(content.encode("utf-8"))
    root = tree.root_node

    target_types = set(config.function_types + config.class_types)
    if config.impl_type:
        target_types.add(config.impl_type)

    extracted_ranges: list[tuple[int, int]] = []

    for child in root.children:
        if child.is_named and child.type in target_types:
            start = child.start_point[0]  # 0-indexed
            end = min(start + SUMMARY_FUNC_LINES, total_lines)
            extracted_ranges.append((start, end))

    if not extracted_ranges:
        return "\n".join(lines[:max_extract_lines])

    extracted_ranges.sort()
    merged: list[tuple[int, int]] = []
    for start, end in extracted_ranges:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))

    result_lines: list[str] = []
    for start, end in merged:
        for i in range(start, end):
            result_lines.append(lines[i])
            if len(result_lines) >= max_extract_lines:
                return "\n".join(result_lines)
        result_lines.append("...")

    return "\n".join(result_lines)


# ---------------------------------------------------------------------------
# 签名格式化辅助
# ---------------------------------------------------------------------------

def format_signature(defn: SymbolDef, lang: str | None) -> str:
    """根据语言生成函数签名字符串。"""
    config = get_lang_config(lang) if lang else None
    if config and config.format_signature:
        return config.format_signature(defn)
    # 默认 Python 风格
    params_str = ", ".join(defn.params)
    prefix = "async def" if defn.kind == "async_function" else "def"
    return f"{prefix} {defn.name}({params_str})"


# ===========================================================================
# Rust 语言配置
# ===========================================================================

def _format_rust_signature(defn: SymbolDef) -> str:
    params_str = ", ".join(defn.params)
    prefix = "async fn" if defn.kind == "async_function" else "fn"
    return f"{prefix} {defn.name}({params_str})"


def _extract_rust_imports(root_node: Node) -> list[tuple[str, str]]:
    """从 Rust CST 提取导入信息。

    返回 (path_string, kind) 列表。
    kind: "crate" / "super" / "self" / "external"

    同时提取 mod 声明（无 body 的 mod_item）。
    """
    imports: list[tuple[str, str]] = []

    for child in root_node.children:
        if child.type == "use_declaration":
            # 提取 use 路径文本
            arg = child.child_by_field_name("argument")
            if not arg:
                # fallback: 取除 use 和 ; 之外的内容
                parts = []
                for c in child.children:
                    if c.is_named:
                        parts.append(_node_text(c))
                path_text = "::".join(parts)
            else:
                path_text = _node_text(arg)

            kind = _classify_rust_import(path_text)
            imports.append((path_text, kind))

        elif child.type == "mod_item":
            # mod submodule; （无 body = 外部模块声明）
            body = child.child_by_field_name("body")
            if not body:
                name_node = child.child_by_field_name("name")
                if name_node:
                    mod_name = _node_text(name_node)
                    imports.append((f"self::{mod_name}", "self"))

    return imports


def _classify_rust_import(path: str) -> str:
    """分类 Rust 导入路径。"""
    if path.startswith("crate::") or path.startswith("crate::{"):
        return "crate"
    if path.startswith("super::"):
        return "super"
    if path.startswith("self::"):
        return "self"
    return "external"


def _resolve_rust_imports(
    imports: list[tuple[str, str]],
    current_file: str,
    project_files: dict[str, str],
) -> list[tuple[str, str, str]]:
    """Rust 导入路径 → 项目文件路径。

    返回 (imported_name, target_file, symbol_name) 列表。
    """
    current_dir = str(PurePosixPath(current_file).parent)
    results: list[tuple[str, str, str]] = []

    # 猜测 crate 根目录：找包含 src/ 或 Cargo.toml 旁的 src
    crate_root = _guess_rust_crate_root(current_file, project_files)

    for path_text, kind in imports:
        if kind == "external":
            continue

        # 解析路径段和导入的名称
        names_and_paths = _parse_rust_use_path(path_text, kind)

        for imported_name, module_segments in names_and_paths:
            target = _find_rust_module_file(
                module_segments, kind, current_dir, crate_root, project_files
            )
            if target:
                results.append((imported_name, target, imported_name))

    return results


def _guess_rust_crate_root(current_file: str, project_files: dict[str, str]) -> str:
    """猜测 Rust crate 的根目录（src/ 所在的目录）。"""
    # 策略：找到项目文件中 src/ 前缀最短的路径
    for pf in project_files:
        if "/src/" in pf:
            idx = pf.index("/src/")
            return pf[:idx + 4]  # 包含 src/
    # fallback: 用当前文件的最顶层目录
    parts = current_file.split("/")
    if len(parts) > 1:
        return parts[0]
    return ""


def _parse_rust_use_path(
    path_text: str, kind: str
) -> list[tuple[str, list[str]]]:
    """解析 Rust use 路径，返回 (imported_name, module_segments) 列表。

    处理：
    - use crate::foo::bar;          → [("bar", ["foo", "bar"])]
    - use crate::foo::{bar, baz};   → [("bar", ["foo", "bar"]), ("baz", ["foo", "baz"])]
    - use crate::foo::bar as b;     → [("b", ["foo", "bar"])]
    """
    # 去除前缀
    path = path_text
    for prefix in ("crate::", "super::", "self::"):
        if path.startswith(prefix):
            path = path[len(prefix):]
            break

    # 处理花括号组
    if "{" in path:
        base_part = path[:path.index("::{")] if "::{" in path else ""
        brace_content = path[path.index("{") + 1:path.rindex("}")]
        base_segments = base_part.split("::") if base_part else []
        results: list[tuple[str, list[str]]] = []
        for item in brace_content.split(","):
            item = item.strip()
            if not item:
                continue
            if " as " in item:
                real_name, alias = item.split(" as ", 1)
                results.append((alias.strip(), base_segments + [real_name.strip()]))
            else:
                results.append((item, base_segments + [item]))
        return results

    # 处理 as 别名
    if " as " in path:
        real_path, alias = path.split(" as ", 1)
        segments = real_path.strip().split("::")
        return [(alias.strip(), segments)]

    # 普通路径
    segments = path.split("::")
    imported_name = segments[-1] if segments else path
    return [(imported_name, segments)]


def _find_rust_module_file(
    segments: list[str],
    kind: str,
    current_dir: str,
    crate_root: str,
    project_files: dict[str, str],
) -> str | None:
    """根据模块路径段查找对应的项目文件。"""
    if not segments:
        return None

    # 构建基础路径
    if kind == "crate":
        base = crate_root
    elif kind == "super":
        base = str(PurePosixPath(current_dir).parent)
    elif kind == "self":
        base = current_dir
    else:
        return None

    # 模块段可能指向文件或文件中的符号
    # 尝试从完整路径开始，逐步缩短
    for depth in range(len(segments), 0, -1):
        module_path = "/".join(segments[:depth])
        candidates = [
            f"{base}/{module_path}.rs",
            f"{base}/{module_path}/mod.rs",
        ]
        for candidate in candidates:
            normalized = str(PurePosixPath(candidate))
            if normalized in project_files:
                return normalized
            # suffix 匹配（项目上传时可能带根目录前缀）
            for pf in project_files:
                if pf.endswith("/" + normalized) or pf == normalized:
                    return pf

    return None


def _detect_rust_entries(
    definitions: dict[str, SymbolDef],
    project_files: dict[str, str],
) -> list[str]:
    """检测 Rust 入口点：fn main、#[tokio::main]、路由属性等。"""
    entries: list[str] = []
    for qname, defn in definitions.items():
        if not defn.file.endswith(".rs"):
            continue

        # fn main
        if defn.name == "main" and defn.kind in ("function", "async_function"):
            entries.append(qname)
            continue

        for attr in defn.decorators:
            attr_lower = attr.lower()
            # async runtime main
            if "tokio::main" in attr or "actix_web::main" in attr or "actix_rt::main" in attr:
                entries.append(qname)
                break
            # 路由处理器
            if any(attr_lower.startswith(f"#[{method}(") for method in
                   ("get", "post", "put", "delete", "patch", "head")):
                entries.append(qname)
                break

    return entries


# ===========================================================================
# Java 语言配置
# ===========================================================================


def _format_java_signature(defn: SymbolDef) -> str:
    params_str = ", ".join(defn.params)
    return f"{defn.name}({params_str})"


def _extract_java_decorators(node: Node, config: LangConfig) -> list[str]:
    """Java 注解在 `modifiers` 子节点内，不是前序兄弟节点。"""
    decorators: list[str] = []
    for child in node.children:
        if child.type == "modifiers":
            for m in child.children:
                if m.type in ("annotation", "marker_annotation"):
                    text = _node_text(m).strip()
                    if text:
                        decorators.append(text)
            break
    return decorators


def _extract_java_callee(call_node: Node) -> tuple[str, str] | None:
    """Java method_invocation 没有 `function` 字段，用 `name` 字段直接取被调方法名。

    带 object 的调用视作 attribute，否则 direct。
    """
    if call_node.type != "method_invocation":
        return None
    name_node = call_node.child_by_field_name("name")
    if not name_node:
        return None
    method_name = _node_text(name_node)
    call_type = "attribute" if call_node.child_by_field_name("object") else "direct"
    return method_name, call_type


def _extract_java_imports(root_node: Node) -> list[tuple[str, str]]:
    """从 Java CST 提取 import 声明。

    返回 (fqn, kind) 列表。kind: "single" / "wildcard"
    """
    imports: list[tuple[str, str]] = []
    for child in root_node.children:
        if child.type != "import_declaration":
            continue
        # 取 import_declaration 下第一个命名子节点作为路径
        # 通常是 scoped_identifier 或 identifier（带 static 修饰时亦同）
        path_node = None
        has_asterisk = False
        for c in child.children:
            if c.is_named and c.type in ("scoped_identifier", "identifier"):
                path_node = c
            elif c.type == "asterisk":
                has_asterisk = True
        if not path_node:
            continue
        fqn = _node_text(path_node)
        kind = "wildcard" if has_asterisk else "single"
        imports.append((fqn, kind))
    return imports


def _resolve_java_imports(
    imports: list[tuple[str, str]],
    current_file: str,
    project_files: dict[str, str],
) -> list[tuple[str, str, str]]:
    """Java import → 项目文件。

    - `import com.example.Foo;` → 查找路径以 `com/example/Foo.java` 结尾的文件
    - `import com.example.*;`   → 查找该包下所有 .java 文件（返回每个类）
    返回 (imported_name, target_file, symbol_name) 列表。
    """
    results: list[tuple[str, str, str]] = []
    for fqn, kind in imports:
        if kind == "single":
            parts = fqn.split(".")
            if not parts:
                continue
            class_name = parts[-1]
            path_suffix = "/".join(parts) + ".java"
            target = _find_java_file_by_suffix(path_suffix, project_files)
            if target:
                results.append((class_name, target, class_name))
        elif kind == "wildcard":
            # import com.example.*;
            parts = fqn.split(".")
            dir_suffix = "/".join(parts) + "/"
            for pf in project_files:
                if not pf.endswith(".java"):
                    continue
                # 匹配：项目文件的父目录恰好以 dir_suffix 结尾
                parent_dir = pf.rsplit("/", 1)[0] + "/"
                if parent_dir.endswith(dir_suffix):
                    class_name = pf.rsplit("/", 1)[1][: -len(".java")]
                    results.append((class_name, pf, class_name))
    return results


def _find_java_file_by_suffix(path_suffix: str, project_files: dict[str, str]) -> str | None:
    """查找 project_files 中以 path_suffix 结尾的文件（或完全匹配）。"""
    if path_suffix in project_files:
        return path_suffix
    # 精确后缀匹配（以 / 分隔避免 Foo.java 匹配到 BarFoo.java）
    needle = "/" + path_suffix
    for pf in project_files:
        if pf.endswith(needle) or pf == path_suffix:
            return pf
    return None


def _detect_java_entries(
    definitions: dict[str, SymbolDef],
    project_files: dict[str, str],
) -> list[str]:
    """检测 Java 入口点：`main` 方法、Spring/JAX-RS 等 Web 注解。"""
    entries: list[str] = []

    entry_annotations = {
        "@springbootapplication",
        "@restcontroller", "@controller", "@service", "@component",
        "@repository", "@configuration",
        "@requestmapping", "@getmapping", "@postmapping",
        "@putmapping", "@deletemapping", "@patchmapping",
        "@path",   # JAX-RS
        "@webservlet", "@weblistener", "@webfilter",
        "@scheduled",
    }

    for qname, defn in definitions.items():
        if not defn.file.endswith(".java"):
            continue

        # main 方法：名字以 .main 结尾且参数含 String[]
        if defn.kind in ("method",) and defn.name.endswith(".main"):
            params_text = " ".join(defn.params)
            if "String[]" in params_text or "String ..." in params_text:
                entries.append(qname)
                continue

        # 注解驱动的入口
        hit = False
        for attr in defn.decorators:
            # 去掉参数：@Foo(bar) → @foo
            attr_lower = attr.lower()
            attr_head = attr_lower.split("(", 1)[0].strip()
            if attr_head in entry_annotations:
                entries.append(qname)
                hit = True
                break
        if hit:
            continue

    return entries


# 注册 Java
try:
    import tree_sitter_java as _ts_java

    _JAVA_LANG = Language(_ts_java.language())
    _JAVA_CONFIG = LangConfig(
        language=_JAVA_LANG,
        function_types=["method_declaration", "constructor_declaration"],
        class_types=["class_declaration", "interface_declaration", "enum_declaration"],
        impl_type=None,
        call_types=["method_invocation"],
        macro_call_type=None,
        import_types=["import_declaration"],
        name_field="name",
        params_field="parameters",
        body_field="body",
        attr_type=None,                 # 注解在 modifiers 子节点里，不走默认前序兄弟逻辑
        doc_comment_prefix=None,        # Javadoc 暂未接入
        class_has_methods=True,
        method_container_types=["enum_body_declarations"],
        format_signature=_format_java_signature,
        extract_imports=_extract_java_imports,
        resolve_imports=_resolve_java_imports,
        detect_lang_entries=_detect_java_entries,
        extract_callee=_extract_java_callee,
        extract_decorators=_extract_java_decorators,
    )
    register_language("java", _JAVA_CONFIG)
    logger.info("Java language support registered via tree-sitter")
except ImportError:
    logger.warning("tree-sitter-java not installed, Java support disabled")


# 注册 Rust
try:
    import tree_sitter_rust as _ts_rust

    _RUST_LANG = Language(_ts_rust.language())
    _RUST_CONFIG = LangConfig(
        language=_RUST_LANG,
        function_types=["function_item"],
        class_types=["struct_item", "enum_item", "trait_item"],
        impl_type="impl_item",
        call_types=["call_expression"],
        macro_call_type="macro_invocation",
        import_types=["use_declaration"],
        name_field="name",
        params_field="parameters",
        body_field="body",
        attr_type="attribute_item",
        doc_comment_prefix="///",
        skip_macros={
            "println", "eprintln", "print", "eprint",
            "format", "format_args",
            "vec", "todo", "unimplemented", "unreachable",
            "panic", "assert", "assert_eq", "assert_ne",
            "debug_assert", "debug_assert_eq", "debug_assert_ne",
            "write", "writeln", "log", "info", "warn", "error", "debug", "trace",
        },
        format_signature=_format_rust_signature,
        extract_imports=_extract_rust_imports,
        resolve_imports=_resolve_rust_imports,
        detect_lang_entries=_detect_rust_entries,
    )
    register_language("rust", _RUST_CONFIG)
    logger.info("Rust language support registered via tree-sitter")
except ImportError:
    logger.warning("tree-sitter-rust not installed, Rust support disabled")
