"""Wiki 生成器共用的 LLM 输出后处理。

三个 generator 拿到 LLM 的 JSON 后都要做：
1. 解析 JSON → 拿到 content_md 和原始 code_refs
2. 根据 AST 补齐 code_refs 的 line_start/line_end（LLM 只给 symbol，行号由我们填）
3. 正则扫 content_md，抽出所有 #wiki:<id> 作为 outgoing_links
"""

from __future__ import annotations

import logging
import re

from backend.models.graph_models import ProjectAST
from backend.models.wiki_models import CodeRef
from backend.utils.data_format import parse_llm_json

logger = logging.getLogger(__name__)

_WIKI_LINK_RE = re.compile(r"#wiki:([A-Za-z0-9_]+)")
_CODE_REF_RE = re.compile(r"#code:(ref_[A-Za-z0-9_]+)")
_GENERIC_H2_BLACKLIST = {
    "概述", "介绍", "详情", "详细介绍", "详细说明", "总结", "说明", "内容",
    "简介", "概览", "综述",
}
_READING_GUIDE_MAX_CHARS = 80


def parse_llm_page_output(raw: str) -> tuple[str, dict]:
    """LLM 原文 → (content_md, raw_code_refs)。异常时返回空字典，不抛出。"""
    try:
        data = parse_llm_json(raw)
    except Exception as e:
        logger.warning("LLM page output parse failed: %s; raw head: %r", e, raw[:200])
        return raw, {}
    md = data.get("content_md") or ""
    refs = data.get("code_refs") or {}
    if not isinstance(refs, dict):
        refs = {}
    return md, refs


def _unescape_newlines(s: str) -> str:
    """部分模型（如 qwen3.6-plus）输出 JSON 时把 `\\n` 双重转义，JSON 解析后
    字符串里残留字面 `\\n`（反斜杠+n）而非真换行。这里做一次反向修复。

    安全性：正确转义的 newline 在 JSON 解析阶段已变成真换行，不会留下字面 `\\n`；
    所以这个 replace 只对错误转义的产出生效，对正常产出无副作用。
    """
    if not s:
        return s
    return s.replace("\\n", "\n").replace("\\t", "\t")


def parse_llm_module_page_output(raw: str) -> dict:
    """模块页专用解析。返回字段：

    - tagline: str
    - file_roles: dict[str, str]（key=path, value=职责）
    - detail_md: str
    - code_refs: dict
    - reading_guide: str（可空）

    异常时返回安全默认值，不抛出。
    """
    try:
        data = parse_llm_json(raw)
    except Exception as e:
        logger.warning(
            "LLM module page output parse failed: %s; raw head: %r", e, raw[:200]
        )
        return {
            "tagline": "",
            "file_roles": {},
            "detail_md": raw,
            "code_refs": {},
            "reading_guide": "",
        }

    speed = data.get("speed_summary") or {}
    if not isinstance(speed, dict):
        speed = {}
    file_roles = speed.get("file_roles") or {}
    if not isinstance(file_roles, dict):
        file_roles = {}

    refs = data.get("code_refs") or {}
    if not isinstance(refs, dict):
        refs = {}

    return {
        "tagline": _unescape_newlines(str(speed.get("tagline") or "").strip()),
        "file_roles": {
            str(k): _unescape_newlines(str(v))
            for k, v in file_roles.items()
        },
        "detail_md": _unescape_newlines(data.get("detail_md") or ""),
        "code_refs": refs,
        "reading_guide": _unescape_newlines(
            str(data.get("reading_guide") or "").strip()
        ),
    }


def validate_module_page(
    detail_md: str,
    reading_guide: str,
    file_roles: dict[str, str],
    expected_paths: list[str],
    min_code_refs: int,
    *,
    log_prefix: str = "module_page",
) -> None:
    """对模块页 LLM 产出做软校验，仅 warn，不抛出、不阻塞生成。"""
    # 1. file_roles 路径覆盖
    expected_set = set(expected_paths)
    actual_set = set(file_roles.keys())
    missing = expected_set - actual_set
    extra = actual_set - expected_set
    if missing:
        logger.warning(
            "%s: file_roles missing %d path(s): %s",
            log_prefix, len(missing), sorted(missing)[:5],
        )
    if extra:
        logger.warning(
            "%s: file_roles has %d unexpected path(s) (likely hallucinated): %s",
            log_prefix, len(extra), sorted(extra)[:5],
        )

    # 2. detail_md 通用 H2 标题黑名单
    bad_h2 = _find_blacklisted_h2(detail_md)
    if bad_h2:
        logger.warning(
            "%s: detail_md contains blacklisted generic H2 heading(s): %s",
            log_prefix, bad_h2,
        )

    # 3. detail_md 代码锚点数量下限
    ref_count = len(set(_CODE_REF_RE.findall(detail_md)))
    if ref_count < min_code_refs:
        logger.warning(
            "%s: detail_md has %d unique code refs, below min=%d",
            log_prefix, ref_count, min_code_refs,
        )

    # 4. reading_guide 长度
    if reading_guide and len(reading_guide) > _READING_GUIDE_MAX_CHARS:
        logger.warning(
            "%s: reading_guide is %d chars, exceeds max=%d",
            log_prefix, len(reading_guide), _READING_GUIDE_MAX_CHARS,
        )


def _find_blacklisted_h2(md: str) -> list[str]:
    """扫描 detail_md 里的 H2 标题，返回命中黑名单的标题。"""
    bad: list[str] = []
    for line in md.splitlines():
        stripped = line.strip()
        if not stripped.startswith("## "):
            continue
        title = stripped[3:].strip()
        # 去掉前导编号、序号符号
        title_clean = re.sub(r"^[\d.、]+\s*", "", title).strip()
        if title_clean in _GENERIC_H2_BLACKLIST:
            bad.append(title)
    return bad


def resolve_code_refs(
    raw_refs: dict,
    ast_model: ProjectAST,
    default_file: str | None = None,
) -> dict[str, CodeRef]:
    """把 LLM 给的 {symbol, file?} 解析成 CodeRef（含行号）。

    查找顺序：
    1. 同时给了 file 和 symbol → 在该文件下精确查符号
    2. 只给 symbol → 全项目搜同名符号（取第一个）
    3. 只给 file → 返回整个文件（行号从 1 到 ModuleNode.line_count）
    """
    resolved: dict[str, CodeRef] = {}
    for ref_id, entry in raw_refs.items():
        if not isinstance(entry, dict):
            continue
        symbol = entry.get("symbol")
        file_path = entry.get("file") or default_file

        if symbol:
            defn = _find_symbol(ast_model, symbol, file_path)
            if defn:
                resolved[ref_id] = CodeRef(
                    file=defn.file,
                    start_line=defn.line_start,
                    end_line=defn.line_end,
                    symbol=defn.name,
                )
                continue

        if file_path and file_path in ast_model.modules:
            mod = ast_model.modules[file_path]
            resolved[ref_id] = CodeRef(
                file=file_path,
                start_line=1,
                end_line=max(mod.line_count, 1),
                symbol=None,
            )
            continue

        logger.debug("code_ref unresolved: id=%s entry=%s", ref_id, entry)
    return resolved


def extract_outgoing_links(content_md: str) -> list[str]:
    """抓取 content_md 中所有 #wiki:<id> 的目标 id，去重保序。"""
    seen: set[str] = set()
    out: list[str] = []
    for m in _WIKI_LINK_RE.finditer(content_md):
        pid = m.group(1)
        if pid not in seen:
            seen.add(pid)
            out.append(pid)
    return out


def _find_symbol(ast_model: ProjectAST, name: str, file_path: str | None):
    """先在指定文件里找，找不到再全项目找同名符号。"""
    if file_path:
        # 精确匹配优先
        qname = f"{file_path}::{name}"
        if qname in ast_model.definitions:
            return ast_model.definitions[qname]
        for defn in ast_model.definitions.values():
            if defn.file == file_path and defn.name == name:
                return defn
    for defn in ast_model.definitions.values():
        if defn.name == name:
            return defn
    return None
