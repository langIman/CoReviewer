"""QAContextBuilder：把检索结果 + 项目知识装配成 Context。

对应 QA_REFACTOR_PLAN.md §2.9。设计动机：让 qa_service 保持"只管流程"，
Context 原语保持"只管消息历史"，业务装配集中在这里。
"""

from __future__ import annotations

import logging

from backend.dao.ast_store import load_project_ast
from backend.dao.summary_store import get_summaries_by_type
from backend.dao.wiki_store import load_wiki_document
from backend.models.qa_models import QAMode
from backend.services.agent.context.base import Context
from backend.services.llm.prompts.qa_prompts import (
    QA_FAST_USER_TEMPLATE,
    QA_SYSTEM_PROMPT_DEEP,
    QA_SYSTEM_PROMPT_FAST,
)
from backend.services.qa.retrieval import retrieve_symbols_with_source

logger = logging.getLogger(__name__)


# —— 可调参数 ——
K_SYMBOLS_FAST = 8           # 快速模式取的符号源码数
K_FILE_SUMMARIES_FAST = 20   # 快速模式取的文件摘要数
MAX_LINES_PER_SYMBOL = 80    # 单个符号源码截断行数
MAX_ITER_DEEP = 8             # 深度模式工具循环上限（与 qa_service 共享）


class QAContextBuilder:
    def __init__(self, project_name: str, question: str, mode: QAMode) -> None:
        self.project_name = project_name
        self.question = question
        self.mode = mode

    def build(self) -> Context:
        if self.mode == "fast":
            return self._build_fast()
        return self._build_deep()

    # --------- 快速模式 ---------

    def _build_fast(self) -> Context:
        """一次性装配：wiki 大纲 + 模块 + 相关文件摘要 + Top-K 符号源码。"""
        ctx = Context(QA_SYSTEM_PROMPT_FAST.format(project_name=self.project_name))

        top_symbols = retrieve_symbols_with_source(
            self.project_name, self.question,
            k=K_SYMBOLS_FAST, max_lines_per_symbol=MAX_LINES_PER_SYMBOL,
        )
        related_files = {r["symbol"].file for r in top_symbols}

        file_summaries = get_summaries_by_type(self.project_name, "file")
        ranked_summaries = _rank_file_summaries(
            file_summaries, self.question, related_files,
        )[:K_FILE_SUMMARIES_FAST]

        wiki_doc = load_wiki_document(self.project_name)
        outline = _render_outline(wiki_doc) if wiki_doc else "（未生成 Wiki）"
        modules = _render_modules(self.project_name)

        user_msg = QA_FAST_USER_TEMPLATE.format(
            outline=outline,
            modules=modules,
            file_summaries=_render_summaries(ranked_summaries),
            code_snippets=_render_symbol_sources(top_symbols),
            question=self.question,
        )
        ctx.add_user(user_msg)
        return ctx

    # --------- 深度模式 ---------

    def _build_deep(self) -> Context:
        """只给原问题，检索交给 Agent 工具循环。"""
        ctx = Context(QA_SYSTEM_PROMPT_DEEP.format(
            project_name=self.project_name,
            max_iter=MAX_ITER_DEEP,
        ))
        ctx.add_user(self.question)
        return ctx


# ---------------------------- 渲染辅助 ----------------------------


def _render_outline(wiki_doc) -> str:
    """把 WikiIndex 渲染成缩进的 Markdown 列表。每行带 page_id 便于 LLM 引用。"""
    tree = wiki_doc.index.tree
    root_id = wiki_doc.index.root
    if root_id not in tree:
        return "（索引为空）"

    lines: list[str] = []
    visited: set[str] = set()

    def walk(page_id: str, depth: int) -> None:
        if page_id in visited:
            return
        visited.add(page_id)
        node = tree.get(page_id)
        if node is None:
            return
        indent = "  " * depth
        lines.append(f"{indent}- {node.title}  `#wiki:{page_id}`")
        for child in node.children:
            walk(child, depth + 1)

    walk(root_id, 0)
    return "\n".join(lines) if lines else "（索引为空）"


def _render_modules(project_name: str) -> str:
    """从 AST modules 表渲染模块列表：``path (N 行, M 符号)``。"""
    ast_model = load_project_ast(project_name)
    if ast_model is None or not ast_model.modules:
        return "（无模块信息）"
    lines = []
    for path in sorted(ast_model.modules.keys()):
        m = ast_model.modules[path]
        lines.append(f"- `{path}` ({m.line_count} 行, {m.symbol_count} 符号)")
    return "\n".join(lines)


def _rank_file_summaries(
    summaries: list[dict], question: str, related_files: set[str],
) -> list[dict]:
    """把命中的符号所在文件置顶，其余保留原序。

    避免再建一份全文 BM25——符号检索已经从"相关度"维度给出了信号，
    文件摘要重排只需要"有命中符号 > 无命中"两档即可。
    """
    if not summaries:
        return []
    hit = [s for s in summaries if s["path"] in related_files]
    miss = [s for s in summaries if s["path"] not in related_files]
    return hit + miss


def _render_summaries(summaries: list[dict]) -> str:
    if not summaries:
        return "（无文件摘要）"
    out = []
    for s in summaries:
        out.append(f"#### `{s['path']}`\n> {s['summary']}\n")
    return "\n".join(out)


def _render_symbol_sources(top_symbols: list[dict]) -> str:
    if not top_symbols:
        return "（未检索到相关符号）"
    out = []
    for r in top_symbols:
        sym = r["symbol"]
        out.append(
            f"#### `{sym.qualified_name}`  (L{sym.line_start}-L{sym.line_end}, "
            f"score={r['score']:.2f})\n"
            f"```python\n{r['source_code']}\n```\n"
        )
    return "\n".join(out)
