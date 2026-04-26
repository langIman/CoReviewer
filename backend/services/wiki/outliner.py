"""Wiki 大纲生成器。

一次 LLM 调用，基于项目模块摘要 + 调用关系 + 运行线索，产出：
- chapters：核心架构下的 3-5 个章节（title + brief）
- topics：专题深入下的 2-4 个议题（title + brief）

brief 用作后续 chapter/topic 生成时 worker 的写作指引。
LLM 输出异常时降级到一个最小默认大纲，保证主流程不中断。
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from backend.models.graph_models import ProjectAST
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.wiki_prompts import build_outline_prompt
from backend.services.wiki.doc_collector import DocBundle
from backend.services.wiki.page_ids import module_id
from backend.utils.data_format import parse_llm_json

logger = logging.getLogger(__name__)


class ChapterSpec(BaseModel):
    title: str
    brief: str = ""


class TopicSpec(BaseModel):
    title: str
    brief: str = ""


class OutlinePlan(BaseModel):
    chapters: list[ChapterSpec] = Field(default_factory=list)
    topics: list[TopicSpec] = Field(default_factory=list)


_DEFAULT_PLAN = OutlinePlan(
    chapters=[
        ChapterSpec(
            title="1. 系统架构概述",
            brief="从整体视角介绍各模块如何协作，主要的数据流和控制流是什么。",
        ),
    ],
    topics=[],
)

MIN_CHAPTERS, MAX_CHAPTERS = 3, 5
MIN_TOPICS, MAX_TOPICS = 2, 4


async def generate_outline(
    *,
    project_name: str,
    modules: list[dict],
    module_summaries: list[str],
    project_summary: str | None,
    ast_model: ProjectAST,
    doc_bundle: DocBundle,
) -> OutlinePlan:
    """一次 LLM 调用，决定核心架构章节和专题深入议题。"""
    modules_text = _fmt_modules(modules, module_summaries)
    module_deps_text = _fmt_module_deps(ast_model, modules)
    run_hints_text = _fmt_run_hints(doc_bundle)
    stats_text = _fmt_stats(doc_bundle)

    system, user = build_outline_prompt(
        project_name=project_name,
        project_summary=project_summary,
        modules_text=modules_text,
        module_deps_text=module_deps_text,
        run_hints_text=run_hints_text,
        stats_text=stats_text,
    )

    try:
        raw = await call_qwen(system, user, enable_thinking=False)
        data = parse_llm_json(raw)
        plan = OutlinePlan.model_validate(data)
    except Exception as e:
        logger.warning("Outliner failed, falling back to default plan: %s", e)
        return _DEFAULT_PLAN

    # 长度约束 + 截断
    chapters = plan.chapters[:MAX_CHAPTERS]
    if len(chapters) < MIN_CHAPTERS:
        logger.info("Outliner returned %d chapters (<%d), keeping anyway", len(chapters), MIN_CHAPTERS)
    topics = plan.topics[:MAX_TOPICS]
    # topics 允许少于 MIN_TOPICS（提示里已说宁缺毋滥）

    return OutlinePlan(chapters=chapters, topics=topics)


# --------- 文本格式化 ---------


def _fmt_modules(modules: list[dict], summaries: list[str]) -> str:
    if not modules:
        return "（无模块）"
    lines = []
    for idx, m in enumerate(modules):
        s = (summaries[idx] if idx < len(summaries) else "").strip() or m.get("description", "")
        lines.append(f"- `{module_id(idx)}` **{m['name']}** — {s or '（暂无摘要）'}")
    return "\n".join(lines)


def _fmt_module_deps(ast_model: ProjectAST, modules: list[dict]) -> str:
    """聚合跨模块调用边的数量，输出 bullet 列表。"""
    path_to_idx: dict[str, int] = {}
    for i, m in enumerate(modules):
        for p in m.get("paths") or []:
            path_to_idx[p] = i

    pair_counts: dict[tuple[int, int], int] = {}
    for e in ast_model.edges:
        if not e.callee_resolved or e.callee_resolved not in ast_model.definitions:
            continue
        dst_file = ast_model.definitions[e.callee_resolved].file
        src_m = path_to_idx.get(e.file)
        dst_m = path_to_idx.get(dst_file)
        if src_m is None or dst_m is None or src_m == dst_m:
            continue
        pair_counts[(src_m, dst_m)] = pair_counts.get((src_m, dst_m), 0) + 1

    if not pair_counts:
        return "（无跨模块调用，可能项目较小或静态分析不完整）"
    lines = []
    for (src, dst), cnt in sorted(pair_counts.items(), key=lambda x: -x[1])[:30]:
        lines.append(f"- `{module_id(src)}` → `{module_id(dst)}` ({cnt} 处)")
    return "\n".join(lines)


def _fmt_run_hints(doc_bundle: DocBundle) -> str:
    if not doc_bundle.run_hints:
        return "（未发现明显的运行线索）"
    parts = []
    for source, content in doc_bundle.run_hints.items():
        truncated = content if len(content) <= 800 else content[:800] + "\n...（已截断）"
        parts.append(f"### {source}\n```\n{truncated}\n```")
    return "\n\n".join(parts)


def _fmt_stats(doc_bundle: DocBundle) -> str:
    stats = doc_bundle.stats
    lang_dist = ", ".join(f"{lang} × {cnt}" for lang, cnt in stats.language_distribution.items()) or "（未识别）"
    return f"- 总文件数：{stats.total_files}\n- 总行数：{stats.total_lines}\n- 语言分布：{lang_dist}"
