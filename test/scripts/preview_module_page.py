#!/usr/bin/env python3
"""单模块页快速预览脚本：绕过 HTTP/前端/wiki 缓存，迭代 generate_module_page。

用法:
    python test/preview_module_page.py <project_dir> [--module-idx N]
    python test/preview_module_page.py <project_dir> --list
    python test/preview_module_page.py <project_dir> --module-idx 0 --output out.md
    # 也可直接用仓库自带的小项目：
    python test/preview_module_page.py test/TestProject --list

行为:
- 装载文件 → store_project（与前端上传等价）
- 检查 AST 缓存：
  · 文件集对得上 → 直接复用（等价于生产 wiki gen 二次调用）
  · 对不上（新项目/同名串台/文件增减）→ initialize_project：清空旧 AST/摘要/wiki 并重建（等价于生产 upload）
- 摘要走 SQLite 缓存：有就用，没有就生成
- 模块划分按文件集缓存；--refresh-split 可强制重跑
- Qwen3.x 默认关闭思考以加快测试；--enable-thinking 可恢复慢速质量检查
- 模块页 LLM 原始响应按 prompt+model 缓存；prompt 改动会自动失效，--refresh-page 可强制重跑
- 跑一次 generate_module_page()；不跑章节/专题/概览页（这是本脚本与生产的唯一差别，目的是缩小迭代回路）

环境:
- 需要 .env 配好 QWEN_API_KEY 等
- 在仓库根目录下运行（脚本会把仓库根加入 sys.path）
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

SPLIT_CACHE_DIR = REPO_ROOT / "test" / ".cache"

# 必须在导入 backend.config 之前加载 .env（config 在 import 时读 os.getenv）
from dotenv import load_dotenv  # noqa: E402

load_dotenv(REPO_ROOT / ".env")

# 预览脚本优先服务快速迭代：Qwen3.x 默认关闭思考，最终质量检查可用
# --enable-thinking 或环境变量 QWEN_ENABLE_THINKING=true 打开。
if "--enable-thinking" in sys.argv:
    os.environ["QWEN_ENABLE_THINKING"] = "true"
else:
    os.environ.setdefault("QWEN_ENABLE_THINKING", "false")

from backend.config import (  # noqa: E402
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    QWEN_ENABLE_THINKING,
    QWEN_MODEL,
    is_ast_file,
)
from backend.dao.ast_store import load_project_ast  # noqa: E402
from backend.dao.file_store import store_project  # noqa: E402
from backend.dao.summary_store import get_summaries_by_type  # noqa: E402
from backend.services.init_service import initialize_project  # noqa: E402
from backend.services.module_service import generate_module_split  # noqa: E402
from backend.services.summary_service import generate_hierarchical_summary  # noqa: E402
from backend.services.wiki.doc_collector import collect as collect_docs  # noqa: E402
from backend.services.wiki.module_page_generator import generate_module_page  # noqa: E402
from backend.services.wiki.page_ids import module_id  # noqa: E402
from backend.utils.analysis.ast_service import get_or_build_ast  # noqa: E402

EXCLUDED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".next", ".cache", ".pytest_cache",
}
EXTRA_FILES = {"Makefile", "Dockerfile", "docker-compose.yml", "docker-compose.yaml"}


def load_project_files(project_dir: Path) -> dict[str, str]:
    """以 <project_dir.name>/<rel_path> 为 key 装载文件，镜像前端上传行为。"""
    project_files: dict[str, str] = {}
    project_name = project_dir.name
    for p in project_dir.rglob("*"):
        if not p.is_file():
            continue
        rel_parts = p.relative_to(project_dir).parts
        if any(part in EXCLUDED_DIRS for part in rel_parts):
            continue
        if p.suffix.lower() not in ALLOWED_EXTENSIONS and p.name not in EXTRA_FILES:
            continue
        try:
            stat = p.stat()
        except OSError:
            continue
        if stat.st_size > MAX_FILE_SIZE:
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        # key: "CoReviewer/backend/main.py"，与前端 webkitGetAsEntry 一致
        key = "/".join((project_name, *rel_parts))
        project_files[key] = content
    return project_files


def filter_modules_to_ast(
    raw_modules: list[dict], ast_paths: set[str]
) -> list[dict]:
    out: list[dict] = []
    for m in raw_modules:
        kept = [p for p in (m.get("paths") or []) if p in ast_paths]
        if kept:
            out.append({**m, "paths": kept})
    return out


def _split_cache_key(project_name: str, project_files: dict[str, str]) -> str:
    """文件集（path 字母序）的稳定 hash——内容变化不影响 split 结构。"""
    h = hashlib.sha256()
    for p in sorted(project_files.keys()):
        h.update(p.encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()[:16]


def _split_cache_path(project_name: str) -> Path:
    return SPLIT_CACHE_DIR / f"split_{project_name}.json"


def load_split_cache(project_name: str, key: str) -> dict | None:
    p = _split_cache_path(project_name)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if data.get("key") != key:
        return None
    return data.get("split")


def save_split_cache(project_name: str, key: str, split: dict) -> None:
    SPLIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"key": key, "project": project_name, "split": split}
    _split_cache_path(project_name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _page_llm_cache_key(system_prompt: str, user_prompt: str) -> str:
    payload = {
        "model": QWEN_MODEL,
        "enable_thinking": QWEN_ENABLE_THINKING,
        "system": system_prompt,
        "user": user_prompt,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def install_page_llm_cache(refresh: bool) -> None:
    """Cache only the raw module-page LLM response; postprocess still reruns."""
    import backend.services.wiki.module_page_generator as module_page_generator

    original_call_qwen = module_page_generator.call_qwen

    async def cached_call_qwen(system_prompt: str, user_prompt: str, **kwargs) -> str:
        key = _page_llm_cache_key(system_prompt, user_prompt)
        path = SPLIT_CACHE_DIR / f"module_page_llm_{key}.json"
        if path.exists() and not refresh:
            print(
                f"[*] Module page LLM: cached (key={key}; --refresh-page 重跑)",
                file=sys.stderr,
            )
            return path.read_text(encoding="utf-8")

        reason = "forced refresh" if refresh else "no cache or stale"
        print(f"[*] Module page LLM: running ({reason}; key={key})", file=sys.stderr)
        raw = await original_call_qwen(system_prompt, user_prompt, **kwargs)
        SPLIT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(raw, encoding="utf-8")
        return raw

    module_page_generator.call_qwen = cached_call_qwen


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project_dir", type=Path, help="本地项目根目录")
    ap.add_argument("--module-idx", type=int, default=0, help="生成第 N 个模块的页面（默认 0）")
    ap.add_argument("--list", action="store_true", help="只列出模块清单，不调用 LLM")
    ap.add_argument("--output", type=Path, help="输出 markdown 到文件（默认 stdout）")
    ap.add_argument("--verbose", "-v", action="store_true", help="DEBUG 日志")
    ap.add_argument(
        "--refresh-split", action="store_true",
        help="忽略 split 缓存强制重跑 module_split（默认若文件集未变就复用缓存）",
    )
    ap.add_argument(
        "--refresh-page", action="store_true",
        help="忽略模块页 LLM 响应缓存，强制重跑最后一次生成",
    )
    ap.add_argument(
        "--enable-thinking", action="store_true",
        help="保留 Qwen3.x 思考模式（更慢，适合最终质量检查）",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    project_dir = args.project_dir.resolve()
    if not project_dir.is_dir():
        print(f"ERROR: not a directory: {project_dir}", file=sys.stderr)
        return 1

    project_name = project_dir.name

    # 1. 装载文件
    print(f"[*] Loading from {project_dir} (as project '{project_name}')", file=sys.stderr)
    project_files = load_project_files(project_dir)
    if not project_files:
        print("ERROR: no valid files found", file=sys.stderr)
        return 1
    print(f"[*] Loaded {len(project_files)} files", file=sys.stderr)
    store_project(project_name, project_files)

    # 2. 校验 AST 缓存是否对得上当前 project_files：
    #    - 如果对得上：直接复用（等价于生产 wiki gen 二次调用走的路径）
    #    - 如果对不上（新项目 / 同名串台 / 文件增减）：调 initialize_project
    #      清缓存重建 AST + 摘要（等价于生产 upload）
    loaded_ast_paths = {p for p in project_files if is_ast_file(p)}
    cached_ast = load_project_ast(project_name)
    cache_valid = cached_ast is not None and set(cached_ast.modules.keys()) == loaded_ast_paths
    if cache_valid:
        print("[*] AST cache valid for current files; reusing", file=sys.stderr)
        ast_model, _ = get_or_build_ast()
    else:
        if cached_ast is None:
            reason = "no cache"
        else:
            cached_set = set(cached_ast.modules.keys())
            extra = len(cached_set - loaded_ast_paths)
            missing = len(loaded_ast_paths - cached_set)
            reason = f"stale (cache has {extra} obsolete paths, {missing} new files unindexed)"
        print(f"[*] initialize_project: {reason} → clearing + rebuilding...", file=sys.stderr)
        initialize_project(project_name)
        ast_model, _ = get_or_build_ast()
    print(
        f"[*] AST: {len(ast_model.definitions)} symbols across {len(ast_model.modules)} files",
        file=sys.stderr,
    )

    # 3. 摘要（已有就跳过）
    if not get_summaries_by_type(project_name, "file"):
        print("[*] Hierarchical summary: not cached, running (slow, many LLM calls)...", file=sys.stderr)
        await generate_hierarchical_summary()
    else:
        print("[*] Hierarchical summary: cached", file=sys.stderr)

    # 4. 模块划分（迭代测试加缓存——module_split 非确定性，
    #    每次重跑会让 A/B 对比不公平；--refresh-split 可强制重跑）
    cache_key = _split_cache_key(project_name, project_files)
    split_result: dict | None = None
    if not args.refresh_split:
        split_result = load_split_cache(project_name, cache_key)
    if split_result is not None:
        print(
            f"[*] Module split: cached (key={cache_key}; --refresh-split 重跑)",
            file=sys.stderr,
        )
    else:
        reason = "forced refresh" if args.refresh_split else "no cache or stale"
        print(f"[*] Module split: running ({reason})...", file=sys.stderr)
        split_result = await generate_module_split()
        save_split_cache(project_name, cache_key, split_result)
    raw_modules = split_result.get("modules") or []
    modules = filter_modules_to_ast(raw_modules, set(ast_model.modules.keys()))
    if not modules:
        print("ERROR: module_split produced no AST-covered modules", file=sys.stderr)
        return 1

    # 仅列出模式
    if args.list:
        for i, m in enumerate(modules):
            print(f"{i:>3}: {m['name']} ({len(m['paths'])} files) — {m.get('description', '')}")
        return 0

    if not 0 <= args.module_idx < len(modules):
        print(
            f"ERROR: module-idx must be 0..{len(modules) - 1}, got {args.module_idx}",
            file=sys.stderr,
        )
        return 1

    # 5. 拼装 generate_module_page 依赖
    path_to_module_index = {p: i for i, m in enumerate(modules) for p in m.get("paths", [])}
    doc_bundle = collect_docs(project_files)
    # 与 wiki_service 一致：模块页只允许引用其他模块，不引 overview/category
    allowed_page_ids = [module_id(i) for i in range(len(modules))]

    # 6. 生成单页
    target = modules[args.module_idx]
    print(
        f"[*] Generating module page #{args.module_idx}: {target['name']} ({len(target['paths'])} files)",
        file=sys.stderr,
    )
    install_page_llm_cache(args.refresh_page)
    page = await generate_module_page(
        index=args.module_idx,
        module=target,
        project_files=project_files,
        ast_model=ast_model,
        path_to_module_index=path_to_module_index,
        doc_bundle=doc_bundle,
        allowed_page_ids=allowed_page_ids,
    )

    output = page.content_md or "(no content)"
    if args.output:
        args.output.write_text(output, encoding="utf-8")
        print(f"[*] Wrote {len(output)} chars to {args.output}", file=sys.stderr)
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
