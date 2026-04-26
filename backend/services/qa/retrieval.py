"""BM25 符号检索引擎。

对应 QA_REFACTOR_PLAN.md §2.7：
- 索引单位：SymbolDef（函数/类），已持久化在 symbols 表
- 检索文本：name + kind + file + docstring + 文件摘要
- 返回：Top-K 符号（可选带源码片段）

为什么独立于 Agent 工具？§2.7 开头：快速模式要走"纯函数"检索拼 prompt，
不依赖 Tool 类；工具壳（search_symbols.py）只是对本模块的薄适配。

缓存：进程内 dict，按 (project_name, fingerprint) 记忆 SymbolIndex；
指纹由当前符号表本身派生，AST 重建后自动失效。
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from dataclasses import dataclass

from rank_bm25 import BM25Okapi

from backend.dao.ast_store import load_project_ast
from backend.dao.file_store import get_project_file
from backend.dao.summary_store import get_summaries_by_type
from backend.models.graph_models import SymbolDef

logger = logging.getLogger(__name__)


# ---------------------------- tokenize ----------------------------

# 常见英文停用词 + 几个中文虚词。保持短，避免过度剪枝代码领域特定词
_STOPWORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "and", "or", "not", "of", "to", "in", "on", "for", "with", "by",
    "this", "that", "it", "as", "at", "from", "if", "else", "do", "does",
    "has", "have", "had", "but", "so",
    # 中文
    "的", "了", "是", "和", "或", "在", "与", "被", "会", "要", "就", "都",
})

_CAMEL_SPLIT_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _tokenize(text: str) -> list[str]:
    """驼峰 / 下划线 / 中英混合切分。

    - ``initApp`` → ``[init, app]``
    - ``load_config`` → ``[load, config]``
    - ``main函数`` → ``[main, 函, 数]``（中英混排时 ASCII run 仍按驼峰切，CJK 逐字切）
    - 统一小写，去停用词，去单字母英文
    """
    if not text:
        return []
    chunks: list[str] = []
    # 先按非单词字符和下划线整体切成 sub（\w 包含 _）
    for raw in _NON_WORD_RE.split(text):
        if not raw:
            continue
        for sub in raw.split("_"):
            if not sub:
                continue
            # 在 sub 内部：扫描连续 ASCII run vs CJK char
            ascii_run: list[str] = []
            for ch in sub:
                if _CJK_RE.match(ch):
                    if ascii_run:
                        chunks.extend(_split_camel("".join(ascii_run)))
                        ascii_run = []
                    chunks.append(ch)
                else:
                    ascii_run.append(ch)
            if ascii_run:
                chunks.extend(_split_camel("".join(ascii_run)))

    return [
        t for t in chunks
        if t and t not in _STOPWORDS and not (len(t) == 1 and t.isascii())
    ]


def _split_camel(s: str) -> list[str]:
    return [m.lower() for m in _CAMEL_SPLIT_RE.findall(s)]


def _symbol_to_search_text(d: SymbolDef, file_summary: str | None) -> str:
    parts = [d.name, d.kind, d.file]
    if d.docstring:
        parts.append(d.docstring)
    if file_summary:
        parts.append(file_summary)
    return " ".join(parts)


# ---------------------------- 索引 ----------------------------


@dataclass
class SymbolIndex:
    """BM25 索引：持有符号表 + 对应 BM25 语料。"""

    symbols: list[SymbolDef]
    bm25: BM25Okapi

    @classmethod
    def build(cls, project_name: str) -> "SymbolIndex | None":
        """读 AST + 文件摘要，构建索引。AST 缺失返回 None。"""
        ast_model = load_project_ast(project_name)
        if ast_model is None or not ast_model.definitions:
            return None

        file_summaries = {
            s["path"]: s["summary"]
            for s in get_summaries_by_type(project_name, "file")
        }
        symbols = list(ast_model.definitions.values())
        tokenized = [
            _tokenize(_symbol_to_search_text(s, file_summaries.get(s.file)))
            for s in symbols
        ]
        # rank_bm25 要求每个 doc 至少一个 token，否则除零
        tokenized = [t if t else ["_empty_"] for t in tokenized]
        bm25 = BM25Okapi(tokenized)
        logger.info(
            "BM25 index built: project=%s symbols=%d", project_name, len(symbols),
        )
        return cls(symbols=symbols, bm25=bm25)

    def top_k(self, query: str, k: int = 10) -> list[tuple[SymbolDef, float]]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        scores = self.bm25.get_scores(tokens)
        ranked = sorted(
            zip(self.symbols, scores), key=lambda x: x[1], reverse=True
        )
        # 过滤全零命中（查询与语料完全无交集时 BM25 返 0）
        return [(s, float(score)) for s, score in ranked[:k] if score > 0]


# ---------------------------- 缓存 ----------------------------

_cache: dict[str, tuple[str, SymbolIndex]] = {}
_cache_lock = threading.Lock()


def _symbols_fingerprint(project_name: str) -> str:
    """对当前 symbols 表取指纹。AST 重建后指纹变化 → 失效。

    比用 wiki hash 更可靠：QA 检索直接依赖 symbols 表，不依赖 wiki。
    """
    ast_model = load_project_ast(project_name)
    if ast_model is None:
        return ""
    h = hashlib.md5()
    for qn in sorted(ast_model.definitions.keys()):
        d = ast_model.definitions[qn]
        h.update(f"{qn}|{d.line_start}|{d.line_end}\n".encode("utf-8"))
    return h.hexdigest()


def get_or_build_index(project_name: str) -> SymbolIndex | None:
    """返回（构建/复用）指定项目的索引。AST 未就绪返回 None。"""
    fp = _symbols_fingerprint(project_name)
    if not fp:
        return None
    with _cache_lock:
        cached = _cache.get(project_name)
        if cached is not None and cached[0] == fp:
            return cached[1]
    # 构建发生在锁外（构建耗时可能稍长）
    index = SymbolIndex.build(project_name)
    if index is None:
        return None
    with _cache_lock:
        _cache[project_name] = (fp, index)
    return index


def invalidate(project_name: str) -> None:
    """显式失效（比如调用方已知 AST 被重建但还没重新 get_or_build）。"""
    with _cache_lock:
        _cache.pop(project_name, None)


# ---------------------------- 对外接口 ----------------------------


def retrieve_symbols_for_question(
    project_name: str,
    question: str,
    k: int = 10,
) -> list[SymbolDef]:
    """仅返回 Top-K SymbolDef 列表（供 search_symbols 工具使用）。"""
    index = get_or_build_index(project_name)
    if index is None:
        return []
    return [s for s, _ in index.top_k(question, k=k)]


def retrieve_symbols_with_source(
    project_name: str,
    question: str,
    k: int = 8,
    max_lines_per_symbol: int = 80,
) -> list[dict]:
    """返回 [{symbol, score, source_code}]。供快速模式打包 prompt。

    source_code 从 file_store 抓 line_start..line_end 的行范围；
    超过 max_lines_per_symbol 截断并追加 ``# ... (truncated)``。
    """
    index = get_or_build_index(project_name)
    if index is None:
        return []

    out: list[dict] = []
    for sym, score in index.top_k(question, k=k):
        source = _read_symbol_source(sym, max_lines_per_symbol)
        out.append({
            "symbol": sym,
            "score": score,
            "source_code": source,
        })
    return out


def _read_symbol_source(sym: SymbolDef, max_lines: int) -> str:
    """从 file_store 取符号的源码片段；读不到则返回提示串。"""
    content = get_project_file(sym.file)
    if content is None:
        return f"# <file not in memory: {sym.file}>"
    lines = content.splitlines()
    # line_start/line_end 按 1-indexed（AST 常用约定）
    start = max(sym.line_start - 1, 0)
    end = min(sym.line_end, len(lines))
    slice_ = lines[start:end]
    truncated = False
    if len(slice_) > max_lines:
        slice_ = slice_[:max_lines]
        truncated = True
    body = "\n".join(slice_)
    if truncated:
        body += "\n# ... (truncated)"
    return body
