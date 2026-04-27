"""Wiki 生成编排层。

对外暴露一个入口 generate_wiki(project_name)：
1. 幂等判断（project_hash）
2. 确保 AST + 摘要就绪
3. 模块划分 + 过滤
4. 收集非代码数据（README / 配置 / 运行线索 / 统计）
5. Outliner 决定章节和专题
6. 并发生成模块页 / 章节页 / 专题页（共享信号量）
7. 概览页（引用所有子页）
8. 构建导航索引树（三层：overview → 3 个 category → 模块/章节/专题）
9. 持久化

所有页面都 eager 生成，不再有懒加载。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime

from fastapi import HTTPException

from backend.config import MAX_WORKER_CONCURRENCY
from backend.dao.file_store import get_project_files, get_project_name
from backend.dao.summary_store import get_summaries_by_type
from backend.dao.wiki_store import (
    get_project_hash,
    load_wiki_document,
    save_wiki_document,
)
from backend.models.wiki_models import (
    PageMetadata,
    WikiDocument,
    WikiIndex,
    WikiIndexNode,
    WikiPage,
)
from backend.services.module_service import generate_module_split
from backend.services.progress_reporter import get_reporter
from backend.services.summary_service import generate_hierarchical_summary
from backend.services.wiki.article_generator import (
    generate_chapter_page,
    generate_topic_page,
)
from backend.services.wiki.doc_collector import collect as collect_docs
from backend.services.wiki.module_page_generator import generate_module_page
from backend.services.wiki.outliner import OutlinePlan, generate_outline
from backend.services.wiki.overview_generator import generate_overview_page
from backend.services.wiki.page_ids import (
    CATEGORY_ARCHITECTURE_ID,
    CATEGORY_MODULES_ID,
    CATEGORY_TOPICS_ID,
    OVERVIEW_ID,
    chapter_id,
    module_id,
    topic_id,
)
from backend.utils.analysis.ast_service import get_or_build_ast

logger = logging.getLogger(__name__)


# ---------------------------- 主入口 ----------------------------


async def generate_wiki(project_name: str | None = None) -> WikiDocument:
    """Eager 流水线：AST → 摘要 → 模块划分 → 大纲 → 并发生成 → 概览 → 落盘。"""
    project_files = get_project_files()
    if not project_files:
        raise HTTPException(status_code=400, detail="No project loaded")
    project_name = project_name or get_project_name()
    if not project_name:
        raise HTTPException(status_code=400, detail="No project loaded")

    # 1. 幂等判断
    current_hash = _compute_project_hash(project_files)
    if get_project_hash(project_name) == current_hash:
        cached = load_wiki_document(project_name)
        if cached is not None:
            logger.info("Wiki hash hit, returning cached: %s", project_name)
            return cached

    # 2. 确保 AST + 摘要就绪
    ast_model, _ = get_or_build_ast()
    if not get_summaries_by_type(project_name, "file"):
        logger.info("Summaries missing, running hierarchical summary first")
        await generate_hierarchical_summary()

    file_summary_map = {
        row["path"]: row["summary"]
        for row in get_summaries_by_type(project_name, "file")
    }
    project_summary_rows = get_summaries_by_type(project_name, "project")
    project_summary = project_summary_rows[0]["summary"] if project_summary_rows else None

    # 3. 模块划分
    logger.info("Running module_split for: %s", project_name)
    async with get_reporter().track("module_split", None):
        split_result = await generate_module_split()
    raw_modules: list[dict] = split_result.get("modules") or []
    if not raw_modules:
        raise HTTPException(status_code=500, detail="module_split returned empty result")

    modules = _filter_modules_to_ast(raw_modules, set(ast_model.modules.keys()))
    if not modules:
        raise HTTPException(
            status_code=500,
            detail="module_split produced no modules with AST-covered files",
        )

    path_to_module_index: dict[str, int] = {}
    for i, m in enumerate(modules):
        for p in m.get("paths") or []:
            path_to_module_index[p] = i

    # 4. 收集非代码数据
    doc_bundle = collect_docs(project_files)

    # 5. Outliner
    logger.info("Generating outline")
    module_summaries_list = [m.get("description", "") for m in modules]
    async with get_reporter().track("outline", None):
        outline: OutlinePlan = await generate_outline(
            project_name=project_name,
            modules=modules,
            module_summaries=module_summaries_list,
            project_summary=project_summary,
            ast_model=ast_model,
            doc_bundle=doc_bundle,
        )
    logger.info(
        "Outline ready: chapters=%d topics=%d",
        len(outline.chapters), len(outline.topics),
    )

    # 6. 计算 allowed_page_ids
    # 全集（章节/专题/概览页用——它们需要引用各种类型）
    allowed_page_ids = [
        OVERVIEW_ID,
        CATEGORY_ARCHITECTURE_ID, CATEGORY_MODULES_ID, CATEGORY_TOPICS_ID,
    ]
    allowed_page_ids += [module_id(i) for i in range(len(modules))]
    allowed_page_ids += [chapter_id(i) for i in range(len(outline.chapters))]
    allowed_page_ids += [topic_id(i) for i in range(len(outline.topics))]
    # 模块页专用子集：只含 module_*——
    # 模块页"跨模块关系"段讲的是代码层面调用关系，
    # 让 LLM 只能引向其他模块，避免把 overview/category 当成消费方瞎指。
    allowed_page_ids_modules_only = [module_id(i) for i in range(len(modules))]

    # 7. 并发生成模块页 + 章节页 + 专题页
    sem = asyncio.Semaphore(MAX_WORKER_CONCURRENCY)

    async def _module_task(i: int, m: dict) -> WikiPage:
        async with sem:
            item = f"{m.get('name')} ({module_id(i)})"  # 防同名模块碰撞
            async with get_reporter().track("module_page", item):
                logger.info("Generating module page: %s (%s)", module_id(i), m.get("name"))
                return await generate_module_page(
                    index=i,
                    module=m,
                    project_files=project_files,
                    ast_model=ast_model,
                    path_to_module_index=path_to_module_index,
                    doc_bundle=doc_bundle,
                    allowed_page_ids=allowed_page_ids_modules_only,
                )

    async def _chapter_task(i: int, spec) -> WikiPage:
        async with sem:
            async with get_reporter().track("chapter_page", spec.title):
                logger.info("Generating chapter page: %s (%s)", chapter_id(i), spec.title)
                return await generate_chapter_page(
                    index=i,
                    spec=spec,
                    project_name=project_name,
                    project_summary=project_summary,
                    modules=modules,
                    module_summaries=module_summaries_list,
                    project_files=project_files,
                    ast_model=ast_model,
                    doc_bundle=doc_bundle,
                    allowed_page_ids=allowed_page_ids,
                )

    async def _topic_task(i: int, spec) -> WikiPage:
        async with sem:
            async with get_reporter().track("topic_page", spec.title):
                logger.info("Generating topic page: %s (%s)", topic_id(i), spec.title)
                return await generate_topic_page(
                    index=i,
                    spec=spec,
                    project_name=project_name,
                    project_summary=project_summary,
                    modules=modules,
                    module_summaries=module_summaries_list,
                    project_files=project_files,
                    ast_model=ast_model,
                    allowed_page_ids=allowed_page_ids,
                )

    all_tasks = [
        *(_module_task(i, m) for i, m in enumerate(modules)),
        *(_chapter_task(i, s) for i, s in enumerate(outline.chapters)),
        *(_topic_task(i, s) for i, s in enumerate(outline.topics)),
    ]
    results: list[WikiPage] = list(await asyncio.gather(*all_tasks))

    # 按 id 前缀分类（保序还原）
    module_pages = [p for p in results if p.id.startswith("module_")]
    chapter_pages = [p for p in results if p.id.startswith("chapter_")]
    topic_pages = [p for p in results if p.id.startswith("topic_")]
    # 按原始索引排序（asyncio.gather 返回顺序 == 输入顺序，但以防万一）
    module_pages.sort(key=lambda p: int(p.id.split("_", 1)[1]))
    chapter_pages.sort(key=lambda p: int(p.id.split("_", 1)[1]))
    topic_pages.sort(key=lambda p: int(p.id.split("_", 1)[1]))

    # 8. 概览页（所有子页生成完）
    logger.info("Generating overview page")
    async with get_reporter().track("overview", None):
        overview_page = await generate_overview_page(
            project_name=project_name,
            modules=modules,
            module_summaries=module_summaries_list,
            chapter_pages=chapter_pages,
            topic_pages=topic_pages,
            project_summary=project_summary,
            ast_model=ast_model,
            path_to_module_index=path_to_module_index,
            doc_bundle=doc_bundle,
            allowed_page_ids=allowed_page_ids,
        )

    # 9. 分类页（纯分组，无内容）
    category_pages = [
        _build_category_page(CATEGORY_ARCHITECTURE_ID, "核心架构"),
        _build_category_page(CATEGORY_MODULES_ID, "模块详解"),
        _build_category_page(CATEGORY_TOPICS_ID, "专题深入"),
    ]

    # 10. 索引树
    index = _build_index(
        overview_page=overview_page,
        chapter_pages=chapter_pages,
        module_pages=module_pages,
        topic_pages=topic_pages,
    )

    # 11. 落盘
    doc = WikiDocument(
        project_name=project_name,
        project_hash=current_hash,
        generated_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        pages=[overview_page, *category_pages, *chapter_pages, *module_pages, *topic_pages],
        index=index,
    )
    save_wiki_document(doc)
    logger.info(
        "Wiki generated: project=%s modules=%d chapters=%d topics=%d",
        project_name, len(module_pages), len(chapter_pages), len(topic_pages),
    )
    return doc


# ---------------------------- 内部工具 ----------------------------


def _build_category_page(page_id: str, title: str) -> WikiPage:
    """分类节点占位页——type='category'，无内容，仅作 sidebar 分组。"""
    return WikiPage(
        id=page_id,
        type="category",
        title=title,
        path=None,
        status="generated",
        content_md=None,
        metadata=PageMetadata(),
    )


def _filter_modules_to_ast(
    raw_modules: list[dict], ast_paths: set[str]
) -> list[dict]:
    """把每个模块的 paths 裁到 AST 集合内，保留原顺序，剔除空模块。"""
    filtered: list[dict] = []
    for m in raw_modules:
        kept = [p for p in (m.get("paths") or []) if p in ast_paths]
        if not kept:
            logger.info(
                "Module dropped (no AST paths left): name=%s orig_paths=%s",
                m.get("name"), m.get("paths"),
            )
            continue
        filtered.append({**m, "paths": kept})
    return filtered


def _compute_project_hash(project_files: dict[str, str]) -> str:
    """对文件内容做 SHA256，用于判断是否需要重新生成。"""
    h = hashlib.sha256()
    for path in sorted(project_files):
        h.update(path.encode("utf-8"))
        h.update(b"\0")
        h.update(project_files[path].encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def _build_index(
    *,
    overview_page: WikiPage,
    chapter_pages: list[WikiPage],
    module_pages: list[WikiPage],
    topic_pages: list[WikiPage],
) -> WikiIndex:
    """三层骨架：overview → 3 个 category → 各自的子页（末级）。"""
    tree: dict[str, WikiIndexNode] = {}

    tree[OVERVIEW_ID] = WikiIndexNode(
        title=overview_page.title,
        children=[CATEGORY_ARCHITECTURE_ID, CATEGORY_MODULES_ID, CATEGORY_TOPICS_ID],
    )

    # 核心架构
    tree[CATEGORY_ARCHITECTURE_ID] = WikiIndexNode(
        title="核心架构",
        children=[p.id for p in chapter_pages],
    )
    for p in chapter_pages:
        tree[p.id] = WikiIndexNode(title=p.title, children=[])

    # 模块详解（模块为末级，不再挂文件）
    tree[CATEGORY_MODULES_ID] = WikiIndexNode(
        title="模块详解",
        children=[p.id for p in module_pages],
    )
    for p in module_pages:
        tree[p.id] = WikiIndexNode(title=p.title, children=[])

    # 专题深入
    tree[CATEGORY_TOPICS_ID] = WikiIndexNode(
        title="专题深入",
        children=[p.id for p in topic_pages],
    )
    for p in topic_pages:
        tree[p.id] = WikiIndexNode(title=p.title, children=[])

    return WikiIndex(root=OVERVIEW_ID, tree=tree)
