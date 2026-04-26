"""复用 preview_module_page 的全部前置流程，但**不调 LLM**——
只把构造好的 system + user prompt 写到 /tmp/module_0_prompt.txt，
让人类（或被限制为单次生成的 LLM）看到与 qwen-plus 完全相同的输入。
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "test" / "scripts"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")
os.environ.setdefault("QWEN_ENABLE_THINKING", "false")

from backend.config import (  # noqa: E402
    MODULE_CODE_BUDGET_CHARS,
    is_ast_file,
)
from backend.dao.ast_store import load_project_ast  # noqa: E402
from backend.dao.file_store import store_project  # noqa: E402
from backend.services.init_service import initialize_project  # noqa: E402
from backend.services.llm.prompts.wiki_prompts import build_module_page_prompt  # noqa: E402
from backend.services.module_service import generate_module_split  # noqa: E402
from backend.services.wiki.doc_collector import collect as collect_docs  # noqa: E402
from backend.services.wiki.module_page_generator import (  # noqa: E402
    _compute_cross_module_links,
    _fmt_cross_module_for_prompt,
    _pick_readme_for_module,
    build_module_code_text,
)
from backend.services.wiki.page_ids import module_id  # noqa: E402
from backend.utils.analysis.ast_service import get_or_build_ast  # noqa: E402

# 复用 preview 的工具
from preview_module_page import (  # noqa: E402
    filter_modules_to_ast,
    load_project_files,
    load_split_cache,
    _split_cache_key,
)


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    project_dir = REPO_ROOT / "test" / "TestProject"
    project_name = project_dir.name
    project_files = load_project_files(project_dir)
    store_project(project_name, project_files)

    loaded_ast_paths = {p for p in project_files if is_ast_file(p)}
    cached_ast = load_project_ast(project_name)
    if cached_ast is None or set(cached_ast.modules.keys()) != loaded_ast_paths:
        initialize_project(project_name)
    ast_model, _ = get_or_build_ast()

    cache_key = _split_cache_key(project_name, project_files)
    split = load_split_cache(project_name, cache_key)
    if split is None:
        print("[*] split cache miss; running...", file=sys.stderr)
        split = await generate_module_split()
    raw_modules = split.get("modules") or []
    modules = filter_modules_to_ast(raw_modules, set(ast_model.modules.keys()))

    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    target = modules[index]
    module_paths = list(target.get("paths", []))
    path_to_module_index = {p: i for i, m in enumerate(modules) for p in m.get("paths", [])}

    module_code_text = build_module_code_text(module_paths, project_files, MODULE_CODE_BUDGET_CHARS)
    out_links, in_links = _compute_cross_module_links(
        index, module_paths, ast_model, path_to_module_index
    )
    cross_text = _fmt_cross_module_for_prompt(out_links, in_links)
    doc_bundle = collect_docs(project_files)
    readme = _pick_readme_for_module(module_paths, doc_bundle)

    min_code_refs = max(2, math.ceil(len(module_paths) / 3))
    allowed = [module_id(i) for i in range(len(modules))]

    system, user = build_module_page_prompt(
        module_name=target["name"],
        module_description=target.get("description", ""),
        module_code_text=module_code_text,
        cross_module_interaction_text=cross_text,
        readme_snippet=readme,
        allowed_page_ids=allowed,
        module_paths=module_paths,
        min_code_refs=min_code_refs,
    )

    out = REPO_ROOT / "test" / ".cache" / f"module_{index}_prompt.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = (
        f"=== MODULE INFO ===\n"
        f"name = {target['name']}\n"
        f"description = {target.get('description', '')}\n"
        f"file_count = {len(module_paths)}\n"
        f"min_code_refs = {min_code_refs}\n"
        f"allowed_page_ids = {allowed}\n\n"
        f"=== SYSTEM PROMPT ===\n{system}\n\n"
        f"=== USER PROMPT ===\n{user}\n"
    )
    out.write_text(text, encoding="utf-8")
    print(f"[*] wrote {len(text)} chars to {out}", file=sys.stderr)
    print(f"[*] system: {len(system)} chars; user: {len(user)} chars", file=sys.stderr)
    print(f"[*] module_code_text: {len(module_code_text)} chars (budget={MODULE_CODE_BUDGET_CHARS})", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
