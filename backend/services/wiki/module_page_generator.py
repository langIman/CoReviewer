"""模块页生成器。

单次 LLM 调用。上游（wiki_service）负责并发多个模块。
模块页是模块维度最末级的页面——文件级细节都在这里一并交代，
Wiki 不再单独有文件页。
"""

from __future__ import annotations

import logging
import math

from backend.config import MODULE_CODE_BUDGET_CHARS
from backend.models.graph_models import ProjectAST
from backend.models.wiki_models import ModuleInfo, PageMetadata, WikiPage
from backend.services.llm.llm_service import call_qwen
from backend.services.llm.prompts.wiki_prompts import build_module_page_prompt
from backend.services.wiki._postprocess import (
    extract_outgoing_links,
    parse_llm_module_page_output,
    resolve_code_refs,
    validate_module_page,
)
from backend.services.wiki.doc_collector import DocBundle
from backend.services.wiki.page_ids import module_id

logger = logging.getLogger(__name__)

# 跨模块交互列表的上限，避免 prompt 爆炸
MAX_INTERACTIONS = 30


async def generate_module_page(
    index: int,
    module: dict,                           # {"name", "description", "paths"}
    project_files: dict[str, str],          # 全量源码（path -> content）
    ast_model: ProjectAST,
    path_to_module_index: dict[str, int],   # 用来算跨模块交互
    doc_bundle: DocBundle,
    allowed_page_ids: list[str],
) -> WikiPage:
    module_paths = list(module.get("paths", []))
    mid = module_id(index)

    module_code_text = build_module_code_text(
        module_paths, project_files, MODULE_CODE_BUDGET_CHARS
    )
    outgoing_links, incoming_links = _compute_cross_module_links(
        index, module_paths, ast_model, path_to_module_index
    )
    cross_prompt_text = _fmt_cross_module_for_prompt(outgoing_links, incoming_links)
    cross_md = _render_cross_module_md(outgoing_links, incoming_links)
    readme = _pick_readme_for_module(module_paths, doc_bundle)

    # 代码锚点下限：max(3, ceil(file_count / 2))
    # 之前公式 ceil(n/3) 让 LLM 容易"踩在下限"，refs 偏少；上调到 ceil(n/2)
    # 对应规模：5 文件 → 3 refs；13 文件 → 7 refs；20 文件 → 10 refs
    min_code_refs = max(3, math.ceil(len(module_paths) / 2))

    logger.info(
        "module_page %s: code_text=%d chars across %d files (min_refs=%d)",
        mid, len(module_code_text), len(module_paths), min_code_refs,
    )

    system, user = build_module_page_prompt(
        module_name=module["name"],
        module_description=module.get("description", ""),
        module_code_text=module_code_text,
        cross_module_interaction_text=cross_prompt_text,
        readme_snippet=readme,
        allowed_page_ids=allowed_page_ids,
        module_paths=module_paths,
        min_code_refs=min_code_refs,
    )

    raw = await call_qwen(system, user, enable_thinking=False)
    parsed = parse_llm_module_page_output(raw)

    # 软校验（仅 warn，不阻塞）
    validate_module_page(
        detail_md=parsed["detail_md"],
        reading_guide=parsed["reading_guide"],
        file_roles=parsed["file_roles"],
        expected_paths=module_paths,
        min_code_refs=min_code_refs,
        log_prefix=f"module_page {mid}",
    )

    # 拼装最终 content_md：速览区（含计算渲染的跨模块表）+ 详解区
    content_md = _assemble_content_md(
        tagline=parsed["tagline"] or module.get("description", ""),
        file_roles=parsed["file_roles"],
        module_paths=module_paths,
        cross_module_md=cross_md,
        reading_guide=parsed["reading_guide"],
        detail_md=parsed["detail_md"],
    )

    code_refs = resolve_code_refs(parsed["code_refs"], ast_model)
    outgoing = extract_outgoing_links(content_md)

    metadata = PageMetadata(
        outgoing_links=outgoing,
        code_refs=code_refs,
        module_info=ModuleInfo(files=list(module_paths)),
    )

    return WikiPage(
        id=mid,
        type="module",
        title=module["name"],
        path=None,
        status="generated",
        content_md=content_md,
        metadata=metadata,
    )


def _assemble_content_md(
    tagline: str,
    file_roles: dict[str, str],
    module_paths: list[str],
    cross_module_md: str,
    reading_guide: str,
    detail_md: str,
) -> str:
    """把速览区与详解区拼成最终 markdown。

    速览区结构：
      ## 速览
      **定位**: <tagline>
      **文件清单**: 表格（按 path 字母序）
      <跨模块关系，代码侧渲染>
      <阅读建议>（可空，省略整节）
      ---
      <detail_md>
    """
    parts: list[str] = ["## 速览", ""]

    # 1. 定位
    if tagline:
        parts.append(f"**定位**：{tagline}")
        parts.append("")

    # 2. 文件清单表
    parts.append("**文件清单**")
    parts.append("")
    parts.append("| 路径 | 职责 |")
    parts.append("|---|---|")
    for path in sorted(module_paths):
        role = file_roles.get(path, "—")
        # markdown 表格里 pipe 字符要转义
        role_safe = role.replace("|", "\\|")
        parts.append(f"| `{path}` | {role_safe} |")
    parts.append("")

    # 3. 跨模块关系（计算渲染）
    parts.append(cross_module_md)
    parts.append("")

    # 4. 阅读建议（可省略）
    if reading_guide:
        parts.append("**阅读建议**")
        parts.append("")
        # 用引用块视觉上区分
        for line in reading_guide.splitlines():
            parts.append(f"> {line}" if line.strip() else ">")
        parts.append("")

    # 5. 分隔
    parts.append("---")
    parts.append("")

    # 6. 详解区
    parts.append(detail_md.strip())

    return "\n".join(parts).rstrip() + "\n"


# --------- 辅助 ---------


def build_module_code_text(
    module_paths: list[str],
    project_files: dict[str, str],
    budget_chars: int,
) -> str:
    """按路径字母序拼接全部模块文件源码；超出预算就硬截断。"""
    parts: list[str] = []
    used = 0
    sorted_paths = sorted(module_paths)
    for i, path in enumerate(sorted_paths):
        content = project_files.get(path, "")
        if not content:
            continue
        header = f"\n### {path}\n```\n"
        footer = "\n```\n"
        block = header + content + footer
        if used + len(block) <= budget_chars:
            parts.append(block)
            used += len(block)
        else:
            remaining = budget_chars - used - len(header) - len(footer) - 50
            if remaining > 500:
                parts.append(header + content[:remaining] + "\n...（已截断）" + footer)
                unshown = len(sorted_paths) - i - 1   # 当前文件部分展示
            else:
                unshown = len(sorted_paths) - i       # 当前文件完全没展示
            if unshown > 0:
                parts.append(f"\n（其余 {unshown} 个文件因预算限制未展示）\n")
            break
    return "".join(parts) or "（无源码内容）"


def _compute_cross_module_links(
    my_index: int,
    my_paths: list[str],
    ast_model: ProjectAST,
    path_to_module_index: dict[str, int],
) -> tuple[dict[int, int], dict[int, int]]:
    """聚合跨模块调用边，返回 (outgoing, incoming) 两个 dict：other_index -> count。"""
    my_paths_set = set(my_paths)
    outgoing: dict[int, int] = {}
    incoming: dict[int, int] = {}

    for e in ast_model.edges:
        if not e.callee_resolved or e.callee_resolved not in ast_model.definitions:
            continue
        target_file = ast_model.definitions[e.callee_resolved].file
        src_in = e.file in my_paths_set
        dst_in = target_file in my_paths_set
        if src_in and not dst_in:
            other = path_to_module_index.get(target_file)
            if other is not None and other != my_index:
                outgoing[other] = outgoing.get(other, 0) + 1
        elif dst_in and not src_in:
            other = path_to_module_index.get(e.file)
            if other is not None and other != my_index:
                incoming[other] = incoming.get(other, 0) + 1
    return outgoing, incoming


def _fmt_cross_module_for_prompt(
    outgoing: dict[int, int], incoming: dict[int, int]
) -> str:
    """喂给 LLM 看的版本（仅作上下文参考，最终渲染不依赖此输出）。"""
    if not outgoing and not incoming:
        return "（无跨模块调用）"
    lines = []
    if outgoing:
        lines.append("本模块调用其他模块：")
        for idx, cnt in sorted(outgoing.items(), key=lambda x: -x[1])[:MAX_INTERACTIONS]:
            lines.append(f"- → `{module_id(idx)}` (共 {cnt} 处调用)")
    if incoming:
        lines.append("本模块被其他模块调用：")
        for idx, cnt in sorted(incoming.items(), key=lambda x: -x[1])[:MAX_INTERACTIONS]:
            lines.append(f"- ← `{module_id(idx)}` (共 {cnt} 处调用)")
    return "\n".join(lines)


def _render_cross_module_md(
    outgoing: dict[int, int], incoming: dict[int, int]
) -> str:
    """直接拼到最终 content_md 的版本——以 wiki 链接形式渲染，前端可点击跳转。"""
    if not outgoing and not incoming:
        return "**跨模块关系**：无跨模块依赖。"
    lines = ["**跨模块关系**（由 AST 计算）", ""]
    if outgoing:
        lines.append("_本模块调用其他模块：_")
        for idx, cnt in sorted(outgoing.items(), key=lambda x: -x[1])[:MAX_INTERACTIONS]:
            mid = module_id(idx)
            lines.append(f"- → [{mid}](#wiki:{mid}) ({cnt} 处调用)")
        lines.append("")
    if incoming:
        lines.append("_本模块被其他模块调用：_")
        for idx, cnt in sorted(incoming.items(), key=lambda x: -x[1])[:MAX_INTERACTIONS]:
            mid = module_id(idx)
            lines.append(f"- ← [{mid}](#wiki:{mid}) ({cnt} 处调用)")
    return "\n".join(lines).rstrip()


def _pick_readme_for_module(paths: list[str], doc_bundle: DocBundle) -> str | None:
    """选离本模块最近的 README，多份合并时加来源前缀。"""
    if not paths:
        return None
    seen_contents: set[str] = set()
    fragments: list[str] = []
    for p in paths:
        folder, content = _readme_lookup_with_folder(p, doc_bundle)
        if not content or content in seen_contents:
            continue
        seen_contents.add(content)
        fragments.append(f"### README @ {folder}\n{content}")
        if len(fragments) >= 2:
            break
    return "\n\n---\n\n".join(fragments) if fragments else None


def _readme_lookup_with_folder(
    path_prefix: str, doc_bundle: DocBundle
) -> tuple[str, str | None]:
    """同 doc_bundle.readme_for()，但同时返回 README 来源目录（"/" 表示根）。"""
    candidates = [
        (folder, content)
        for folder, content in doc_bundle.folder_readmes.items()
        if path_prefix == folder or path_prefix.startswith(folder.rstrip("/") + "/")
    ]
    if candidates:
        candidates.sort(key=lambda x: len(x[0]), reverse=True)
        return candidates[0][0], candidates[0][1]
    return "/", doc_bundle.root_readme
