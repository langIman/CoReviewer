"""将 LLM 返回的 symbol + code_snippet 解析为真实代码行号。

解析优先级（四级 fallback）：
1. code_snippet 精确匹配
2. code_snippet 模糊匹配（去空格）
3. symbol 调用点（AST ast.Call）
4. symbol 定义点（AST FunctionDef / ClassDef）
"""

import ast
from dataclasses import dataclass


@dataclass
class ResolvedLine:
    start: int
    end: int


def resolve_symbol(
    source: str,
    symbol: str | None = None,
    code_snippet: str | None = None,
) -> ResolvedLine | None:
    """在 source 中解析 symbol/code_snippet 对应的真实行号。

    Returns:
        ResolvedLine(start, end) 或 None（全部失败时）
    """
    lines = source.split("\n")

    # --- 1. code_snippet 精确匹配 ---
    if code_snippet:
        snippet_stripped = code_snippet.strip()
        for i, line in enumerate(lines):
            if snippet_stripped in line:
                return ResolvedLine(start=i + 1, end=i + 1)

    # --- 2. code_snippet 模糊匹配（去掉所有空格） ---
    if code_snippet:
        snippet_nospace = code_snippet.replace(" ", "").replace("\t", "")
        for i, line in enumerate(lines):
            if snippet_nospace in line.replace(" ", "").replace("\t", ""):
                return ResolvedLine(start=i + 1, end=i + 1)

    if not symbol:
        return None

    # --- 3 & 4. AST 解析 ---
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # AST 解析失败，退到纯文本搜索
        return _text_search_symbol(lines, symbol)

    # --- 3. symbol 调用点 ---
    call_line = _find_call_site(tree, symbol)
    if call_line is not None:
        return ResolvedLine(start=call_line, end=call_line)

    # --- 4. symbol 定义点 ---
    def_result = _find_definition(tree, symbol)
    if def_result is not None:
        return def_result

    # --- 兜底：纯文本搜索 ---
    return _text_search_symbol(lines, symbol)


def _find_call_site(tree: ast.Module, symbol: str) -> int | None:
    """在 AST 中找到 symbol 的第一个调用点行号。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # 直接调用: symbol(...)
        if isinstance(func, ast.Name) and func.id == symbol:
            return node.lineno
        # 属性调用: xxx.symbol(...)
        if isinstance(func, ast.Attribute) and func.attr == symbol:
            return node.lineno
    return None


def _find_definition(tree: ast.Module, symbol: str) -> ResolvedLine | None:
    """在 AST 中找到 symbol 的函数/类定义及其行范围。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                end_line = getattr(node, "end_lineno", node.lineno)
                return ResolvedLine(start=node.lineno, end=end_line)
    return None


def _text_search_symbol(lines: list[str], symbol: str) -> ResolvedLine | None:
    """纯文本兜底：搜索 symbol( 出现的位置。"""
    call_pattern = f"{symbol}("
    for i, line in enumerate(lines):
        if call_pattern in line:
            return ResolvedLine(start=i + 1, end=i + 1)

    # 再找定义
    for prefix in ("def ", "class "):
        pattern = f"{prefix}{symbol}"
        for i, line in enumerate(lines):
            if pattern in line:
                return ResolvedLine(start=i + 1, end=i + 1)

    return None
