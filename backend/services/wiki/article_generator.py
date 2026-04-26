"""核心架构章节 & 专题深入的页面生成器。

两者的上下文和输出格式高度相似——输入一个 spec（title + brief），
外加全局的项目元数据，生成一篇 600-1200 字的 Markdown 文章。
共用 _generate_article 走同一套后处理管线。
"""

from __future__ import annotations

import logging

from backend.models.graph_models import ProjectAST
from backend.models.wiki_models import PageMetadata, WikiPage
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.wiki_prompts import (
    build_chapter_page_prompt,
    build_topic_page_prompt,
)
from backend.services.wiki._postprocess import (
    extract_outgoing_links,
    parse_llm_page_output,
    resolve_code_refs,
)
from backend.services.wiki.doc_collector import DocBundle
from backend.services.wiki.outliner import ChapterSpec, TopicSpec
from backend.services.wiki.page_ids import chapter_id, module_id, topic_id

logger = logging.getLogger(__name__)


async def generate_chapter_page(
    *,
    index: int,
    spec: ChapterSpec,
    project_name: str,
    project_summary: str | None,
    modules: list[dict],
    module_summaries: list[str],
    ast_model: ProjectAST,
    doc_bundle: DocBundle,
    allowed_page_ids: list[str],
) -> WikiPage:
    system, user = build_chapter_page_prompt(
        chapter_title=spec.title,
        chapter_brief=spec.brief,
        project_name=project_name,
        project_summary=project_summary,
        modules_text=_fmt_modules(modules, module_summaries),
        module_deps_text=_fmt_module_deps(ast_model, modules),
        run_hints_text=_fmt_run_hints(doc_bundle),
        allowed_page_ids=allowed_page_ids,
    )
    return await _generate_article(
        page_id=chapter_id(index),
        page_type="chapter",
        title=spec.title,
        brief=spec.brief,
        system=system,
        user=user,
        ast_model=ast_model,
    )


async def generate_topic_page(
    *,
    index: int,
    spec: TopicSpec,
    project_name: str,
    project_summary: str | None,
    modules: list[dict],
    module_summaries: list[str],
    ast_model: ProjectAST,
    allowed_page_ids: list[str],
) -> WikiPage:
    system, user = build_topic_page_prompt(
        topic_title=spec.title,
        topic_brief=spec.brief,
        project_name=project_name,
        project_summary=project_summary,
        modules_text=_fmt_modules(modules, module_summaries),
        module_deps_text=_fmt_module_deps(ast_model, modules),
        allowed_page_ids=allowed_page_ids,
    )
    return await _generate_article(
        page_id=topic_id(index),
        page_type="topic",
        title=spec.title,
        brief=spec.brief,
        system=system,
        user=user,
        ast_model=ast_model,
    )


# --------- 共用调用 ---------


async def _generate_article(
    *,
    page_id: str,
    page_type: str,
    title: str,
    brief: str,
    system: str,
    user: str,
    ast_model: ProjectAST,
) -> WikiPage:
    raw = await call_qwen(system, user, enable_thinking=False)
    content_md, raw_refs = parse_llm_page_output(raw)
    code_refs = resolve_code_refs(raw_refs, ast_model)
    outgoing = extract_outgoing_links(content_md)

    return WikiPage(
        id=page_id,
        type=page_type,  # type: ignore[arg-type]
        title=title,
        path=None,
        status="generated",
        content_md=content_md,
        metadata=PageMetadata(
            outgoing_links=outgoing,
            code_refs=code_refs,
            brief=brief or None,
        ),
    )


# --------- 共用文本格式化 ---------


def _fmt_modules(modules: list[dict], summaries: list[str]) -> str:
    if not modules:
        return "（无模块）"
    lines = []
    for idx, m in enumerate(modules):
        s = (summaries[idx] if idx < len(summaries) else "").strip() or m.get("description", "")
        lines.append(f"- `{module_id(idx)}` **{m['name']}** — {s or '（暂无摘要）'}")
    return "\n".join(lines)


def _fmt_module_deps(ast_model: ProjectAST, modules: list[dict]) -> str:
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
        return "（无跨模块调用）"
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
