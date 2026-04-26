"""非代码数据收集：README 归属、配置、运行线索、项目统计。

对应 WIKI_REFACTOR_PLAN.md 第七节：把人类为人类准备的线索（README、Makefile、
scripts、约定入口文件）喂给概览/模块页生成器，让 LLM 有真实素材可用，而不是
靠硬匹配规则猜入口。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

from backend.config import get_file_language


# --------- 模式匹配常量 ---------

README_FILENAMES = {"README.md", "README.rst", "README.txt", "README"}

CONFIG_FILENAMES = {
    "requirements.txt",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "tsconfig.json",
    ".env.example",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
}

RUN_HINT_FILENAMES = {
    "Makefile",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
}

# 约定入口文件名；取前 ENTRY_FILE_HEAD_LINES 行，作为 LLM 推断数据流的线索
ENTRY_FILENAMES = {"main.py", "app.py", "server.ts", "index.ts", "index.js", "main.rs"}
ENTRY_FILE_HEAD_LINES = 50


# --------- 数据结构 ---------


@dataclass
class ProjectStats:
    total_files: int = 0
    total_lines: int = 0
    language_distribution: dict[str, int] = field(default_factory=dict)


@dataclass
class DocBundle:
    """收集结果的容器，直接传给各 generator。"""

    root_readme: str | None = None                       # 根 README 全文
    folder_readmes: dict[str, str] = field(default_factory=dict)  # folder_path -> content
    configs: dict[str, str] = field(default_factory=dict)          # filename -> content
    run_hints: dict[str, str] = field(default_factory=dict)        # source -> content
    stats: ProjectStats = field(default_factory=ProjectStats)

    def readme_for(self, path_prefix: str) -> str | None:
        """返回归属于给定路径前缀（一个文件/文件夹）的最近 README。"""
        candidates = [
            (folder, content)
            for folder, content in self.folder_readmes.items()
            if path_prefix == folder or path_prefix.startswith(folder.rstrip("/") + "/")
        ]
        if not candidates:
            return self.root_readme
        # 最深的归属路径优先
        candidates.sort(key=lambda x: len(x[0]), reverse=True)
        return candidates[0][1]


# --------- 收集入口 ---------


def collect(project_files: dict[str, str]) -> DocBundle:
    """扫一遍 project_files，分类抽取 README / 配置 / 运行线索 / 统计。"""
    bundle = DocBundle()
    lang_counts: dict[str, int] = {}

    for path, content in project_files.items():
        p = PurePosixPath(path)
        name = p.name

        # README 归属
        if name in README_FILENAMES or (name.lower().startswith("readme") and p.suffix.lower() in {".md", ".rst", ".txt", ""}):
            folder = str(p.parent)
            if folder in {".", ""}:
                bundle.root_readme = content
            else:
                bundle.folder_readmes[folder] = content
            # README 不计入统计

        # 配置文件
        elif name in CONFIG_FILENAMES:
            bundle.configs[path] = content

        # 运行线索（Makefile / Dockerfile / compose）
        elif name in RUN_HINT_FILENAMES:
            bundle.run_hints[path] = content

        # 入口文件（取前 N 行）
        if name in ENTRY_FILENAMES and path not in bundle.run_hints:
            bundle.run_hints[path] = _head(content, ENTRY_FILE_HEAD_LINES)

        # package.json 额外抽 scripts 片段放进 run_hints
        if name == "package.json":
            scripts = _extract_npm_scripts(content)
            if scripts:
                bundle.run_hints[f"{path}#scripts"] = scripts

        # 统计（所有文件计入 total_files，代码文件计入语言分布）
        bundle.stats.total_files += 1
        bundle.stats.total_lines += content.count("\n") + 1
        lang = get_file_language(path)
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

    bundle.stats.language_distribution = dict(
        sorted(lang_counts.items(), key=lambda x: -x[1])
    )
    return bundle


# --------- 私有工具 ---------


def _head(content: str, n: int) -> str:
    lines = content.split("\n")
    return "\n".join(lines[:n])


def _extract_npm_scripts(package_json_content: str) -> str | None:
    """从 package.json 文本里抽出 scripts 段落。解析失败就返回 None。"""
    import json

    try:
        data = json.loads(package_json_content)
    except json.JSONDecodeError:
        return None
    scripts = data.get("scripts")
    if not isinstance(scripts, dict) or not scripts:
        return None
    return json.dumps(scripts, ensure_ascii=False, indent=2)
