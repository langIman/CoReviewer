"""概览页生成器。

单次 LLM 调用，依赖所有子页（模块/章节/专题）已生成完毕，
以便概览中能引导读者到这些页面。
"""

from __future__ import annotations

import logging

from backend.models.graph_models import ProjectAST
from backend.models.wiki_models import PageMetadata, WikiPage
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.wiki_prompts import build_overview_page_prompt
from backend.services.wiki._postprocess import (
    extract_outgoing_links,
    parse_llm_page_output,
    resolve_code_refs,
)
from backend.services.wiki.doc_collector import DocBundle
from backend.services.wiki.page_ids import (
    OVERVIEW_ID,
    chapter_id,
    module_id,
    topic_id,
)

logger = logging.getLogger(__name__)


async def generate_overview_page(
    project_name: str,
    modules: list[dict],                     # module_split 输出的原始列表
    module_summaries: list[str],             # 每个模块的一句话摘要（与 modules 对齐）
    chapter_pages: list[WikiPage],           # 已生成的核心架构章节页
    topic_pages: list[WikiPage],             # 已生成的专题深入页
    project_summary: str | None,
    ast_model: ProjectAST,
    path_to_module_index: dict[str, int],
    doc_bundle: DocBundle,
    allowed_page_ids: list[str],
) -> WikiPage:
    modules_text = _fmt_modules(modules, module_summaries)
    module_deps_text = _fmt_module_deps(ast_model, path_to_module_index)
    chapters_text = _fmt_chapters(chapter_pages)
    topics_text = _fmt_topics(topic_pages)
    tech_stack_text = _fmt_configs(
        doc_bundle,
        kinds=("requirements.txt", "package.json", "pyproject.toml", "Cargo.toml"),
    )
    config_text = _fmt_configs(doc_bundle, kinds=(".env.example", "tsconfig.json"))
    run_hints_text = _fmt_run_hints(doc_bundle)
    stats_text = _fmt_stats(doc_bundle)

    system, user = build_overview_page_prompt(
        project_name=project_name,
        project_summary=project_summary,
        modules_text=modules_text,
        module_deps_text=module_deps_text,
        chapters_text=chapters_text,
        topics_text=topics_text,
        root_readme=doc_bundle.root_readme,
        tech_stack_text=tech_stack_text,
        config_text=config_text,
        run_hints_text=run_hints_text,
        stats_text=stats_text,
        allowed_page_ids=allowed_page_ids,
    )

    raw = await call_qwen(system, user, enable_thinking=False)
    content_md, raw_refs = parse_llm_page_output(raw)
    code_refs = resolve_code_refs(raw_refs, ast_model)
    outgoing = extract_outgoing_links(content_md)

    return WikiPage(
        id=OVERVIEW_ID,
        type="overview",
        title=project_name,
        path=None,
        status="generated",
        content_md=content_md,
        metadata=PageMetadata(outgoing_links=outgoing, code_refs=code_refs),
    )


# --------- 文本格式化 ---------


def _fmt_modules(modules: list[dict], summaries: list[str]) -> str:
    if not modules:
        return "（无）"
    lines = []
    for idx, m in enumerate(modules):
        s = summaries[idx] if idx < len(summaries) else ""
        s = s.strip() or m.get("description", "")
        pid = module_id(idx)
        lines.append(f"- `{pid}` **{m['name']}** — {s or '（暂无摘要）'}")
    return "\n".join(lines)


def _fmt_chapters(chapter_pages: list[WikiPage]) -> str:
    if not chapter_pages:
        return "（无核心架构章节）"
    lines = []
    for i, p in enumerate(chapter_pages):
        brief = (p.metadata.brief or "").strip()
        lines.append(f"- `{chapter_id(i)}` **{p.title}** — {brief or '（无说明）'}")
    return "\n".join(lines)


def _fmt_topics(topic_pages: list[WikiPage]) -> str:
    if not topic_pages:
        return "（本项目暂未识别出需要单独开专题的设计点）"
    lines = []
    for i, p in enumerate(topic_pages):
        brief = (p.metadata.brief or "").strip()
        lines.append(f"- `{topic_id(i)}` **{p.title}** — {brief or '（无说明）'}")
    return "\n".join(lines)


def _fmt_module_deps(ast_model: ProjectAST, path_to_module_index: dict[str, int]) -> str:
    """按 (src_module, dst_module) 聚合边数。"""
    pair_counts: dict[tuple[int, int], int] = {}
    for e in ast_model.edges:
        if not e.callee_resolved or e.callee_resolved not in ast_model.definitions:
            continue
        dst_file = ast_model.definitions[e.callee_resolved].file
        src_m = path_to_module_index.get(e.file)
        dst_m = path_to_module_index.get(dst_file)
        if src_m is None or dst_m is None or src_m == dst_m:
            continue
        pair_counts[(src_m, dst_m)] = pair_counts.get((src_m, dst_m), 0) + 1

    if not pair_counts:
        return "（无跨模块调用，可能是项目较小或静态分析不完整）"

    lines = []
    for (src, dst), cnt in sorted(pair_counts.items(), key=lambda x: -x[1])[:30]:
        lines.append(f"- `{module_id(src)}` → `{module_id(dst)}` ({cnt} 处)")
    return "\n".join(lines)


def _fmt_configs(doc_bundle: DocBundle, kinds: tuple[str, ...]) -> str:
    """从 configs 里挑出文件名匹配 kinds 的，原文输出。"""
    parts = []
    for path, content in doc_bundle.configs.items():
        if any(path.endswith(k) for k in kinds):
            parts.append(f"### {path}\n```\n{_truncate(content, 1500)}\n```")
    return "\n\n".join(parts) if parts else "（无）"


def _fmt_run_hints(doc_bundle: DocBundle) -> str:
    if not doc_bundle.run_hints:
        return "（未发现明显的运行线索）"
    parts = []
    for source, content in doc_bundle.run_hints.items():
        parts.append(f"### {source}\n```\n{_truncate(content, 1500)}\n```")
    return "\n\n".join(parts)


def _fmt_stats(doc_bundle: DocBundle) -> str:
    stats = doc_bundle.stats
    lang_dist = ", ".join(f"{lang} × {cnt}" for lang, cnt in stats.language_distribution.items()) or "（未识别语言）"
    return f"- 总文件数：{stats.total_files}\n- 总行数：{stats.total_lines}\n- 语言分布：{lang_dist}"


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "\n...（已截断）"
